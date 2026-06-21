"""System Evaluation Metrics Engine.

Computes all deterministic metrics for the evaluation framework:
goal success, expansion quality, knowledge quality, explanatory power,
knowledge reuse, investigation efficiency, and longitudinal learning.
"""

import logging
import re
from typing import Any

from sqlalchemy import select, func, and_
from sqlalchemy.orm import Session

from models.news_intelligence import (
    BenchmarkResult,
    Edge,
    EvaluationSnapshot,
    GoalEvaluation,
    Impact,
    InvestigationGoal,
    LeadQueue,
    Node,
    NodeResearchLog,
    NodeResearchProfile,
    Signal,
)
from expansion.goals import (
    compute_completion_score,
    get_goal_knowledge_coverage,
    _find_goal_related_nodes,
    REQUIRED_KNOWLEDGE_CATEGORIES,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Part 1: Goal Success Metrics
# ---------------------------------------------------------------------------

def compute_goal_coverage(db: Session, goal: InvestigationGoal) -> float:
    """Fraction of required knowledge categories that are covered."""
    coverage = get_goal_knowledge_coverage(db, goal)
    req = coverage["required"]
    covered = coverage["covered"]
    if not req:
        return 0.0
    return round(len(covered) / len(req), 4)


def compute_goal_efficiency(goal: InvestigationGoal) -> float:
    """Understanding gained per unit of budget spent."""
    if goal.expansions_used == 0:
        return 1.0 if goal.completion_score > 0 else 0.0
    budget_fraction = goal.expansions_used / max(goal.expansion_budget, 1)
    efficiency = goal.completion_score / max(budget_fraction, 0.01)
    return round(min(efficiency, 1.0), 4)


def compute_goal_confidence(db: Session, goal: InvestigationGoal) -> float:
    """Composite confidence from node scores, edge scores, research depth, sources, signals."""
    related_ids = _find_goal_related_nodes(db, goal)
    if not related_ids:
        return 0.0

    # Average node confidence
    avg_node_conf = db.scalar(
        select(func.avg(Node.confidence_score)).where(Node.id.in_(related_ids))
    ) or 0.0

    # Average edge confidence
    avg_edge_conf = db.scalar(
        select(func.avg(Edge.confidence_score))
        .where(Edge.from_node_id.in_(related_ids))
        .where(Edge.to_node_id.in_(related_ids))
    ) or 0.0

    # Research density (fraction researched)
    researched = db.scalar(
        select(func.count(Node.id))
        .where(Node.id.in_(related_ids))
        .where(Node.research_status == "completed")
    ) or 0
    research_frac = researched / len(related_ids) if related_ids else 0.0

    # Source diversity
    distinct_clusters = db.scalar(
        select(func.count(func.distinct(Node.cluster_id))).where(Node.id.in_(related_ids))
    ) or 0
    source_div = min(distinct_clusters / 5.0, 1.0)

    # Signal type coverage
    signal_types = db.execute(
        select(func.distinct(Signal.signal_type)).where(Signal.node_id.in_(related_ids))
    ).scalars().all()
    signal_coverage = min(len(signal_types) / 3.0, 1.0)

    confidence = (
        0.30 * float(avg_node_conf)
        + 0.25 * float(avg_edge_conf)
        + 0.20 * research_frac
        + 0.15 * source_div
        + 0.10 * signal_coverage
    )
    return round(min(confidence, 1.0), 4)


def compute_explanation_score_for_goal(db: Session, goal: InvestigationGoal) -> float:
    """Deterministic explanatory power metric for a single goal."""
    related_ids = _find_goal_related_nodes(db, goal)
    if not related_ids:
        return 0.0

    # 1. Research Profile Completeness (0.20)
    profiles = db.execute(
        select(NodeResearchProfile).where(NodeResearchProfile.node_id.in_(related_ids))
    ).scalars().all()

    if profiles:
        section_keys = ["summary", "causal_chain", "impact_profile", "signal_warnings", "research_leads"]
        completeness_scores = []
        for p in profiles:
            rj = p.research_json or {}
            non_empty = sum(1 for k in section_keys if rj.get(k))
            completeness_scores.append(non_empty / len(section_keys))
        profile_completeness = sum(completeness_scores) / len(completeness_scores)
    else:
        profile_completeness = 0.0

    # 2. Causal Chain Depth (0.25)
    max_depth = db.scalar(
        select(func.max(Node.expansion_depth)).where(Node.id.in_(related_ids))
    ) or 0
    causal_depth = min(max_depth / 4.0, 1.0)

    # 3. Causal Chain Breadth (0.15)
    causal_predecessors = set()
    for p in profiles:
        rj = p.research_json or {}
        caused_by = rj.get("causal_chain", {}).get("caused_by", [])
        causal_predecessors.update(caused_by)
    causal_breadth = min(len(causal_predecessors) / 5.0, 1.0)

    # 4. Signal Coverage (0.15)
    signal_types = db.execute(
        select(func.distinct(Signal.signal_type)).where(Signal.node_id.in_(related_ids))
    ).scalars().all()
    signal_cov = min(len(signal_types) / 3.0, 1.0)

    # 5. Impact Coverage (0.15)
    impacts = db.execute(
        select(Impact).where(Impact.node_id.in_(related_ids))
    ).scalars().all()
    sectors = set()
    for imp in impacts:
        for field in [imp.short_term_winners, imp.short_term_losers, imp.long_term_winners, imp.long_term_losers]:
            if field:
                for entry in field:
                    if isinstance(entry, str) and ":" in entry:
                        sectors.add(entry.split(":")[0].strip())
    impact_cov = min(len(sectors) / 3.0, 1.0)

    # 6. Knowledge Category Spread (0.10)
    coverage = compute_goal_coverage(db, goal)

    score = (
        0.20 * profile_completeness
        + 0.25 * causal_depth
        + 0.15 * causal_breadth
        + 0.15 * signal_cov
        + 0.15 * impact_cov
        + 0.10 * coverage
    )
    return round(min(score, 1.0), 4)


def compute_goal_satisfaction(
    completion: float, coverage: float, efficiency: float,
    confidence: float, explanation: float,
) -> float:
    """Composite satisfaction grade for an investigation."""
    score = (
        0.30 * completion
        + 0.25 * coverage
        + 0.20 * efficiency
        + 0.15 * confidence
        + 0.10 * explanation
    )
    return round(min(score, 1.0), 4)


def evaluate_goal(db: Session, goal: InvestigationGoal, snapshot_id: int | None = None) -> GoalEvaluation:
    """Create a full GoalEvaluation record for a single goal."""
    completion = compute_completion_score(db, goal)
    coverage_val = compute_goal_coverage(db, goal)
    efficiency = compute_goal_efficiency(goal)
    confidence = compute_goal_confidence(db, goal)
    explanation = compute_explanation_score_for_goal(db, goal)
    satisfaction = compute_goal_satisfaction(completion, coverage_val, efficiency, confidence, explanation)

    # Lead statistics for this goal
    leads_total = db.scalar(
        select(func.count(LeadQueue.id)).where(LeadQueue.goal_id == goal.id)
    ) or 0
    leads_rejected = db.scalar(
        select(func.count(LeadQueue.id))
        .where(LeadQueue.goal_id == goal.id)
        .where(LeadQueue.status == "rejected")
    ) or 0

    # Coverage categories
    cov = get_goal_knowledge_coverage(db, goal)

    # Causal chain depth
    related_ids = _find_goal_related_nodes(db, goal)
    max_depth = 0
    if related_ids:
        max_depth = db.scalar(
            select(func.max(Node.expansion_depth)).where(Node.id.in_(related_ids))
        ) or 0

    ge = GoalEvaluation(
        goal_id=goal.id,
        snapshot_id=snapshot_id,
        completion_score=completion,
        coverage_score=coverage_val,
        efficiency_score=efficiency,
        confidence_score=confidence,
        satisfaction_score=satisfaction,
        explanation_score=explanation,
        leads_total=leads_total,
        leads_rejected=leads_rejected,
        expansions_used=goal.expansions_used,
        expansion_budget=goal.expansion_budget,
        knowledge_categories_required=len(cov["required"]),
        knowledge_categories_covered=len(cov["covered"]),
        causal_chain_depth=max_depth,
    )
    db.add(ge)
    db.commit()
    return ge


# ---------------------------------------------------------------------------
# Part 2: Expansion Quality Metrics
# ---------------------------------------------------------------------------

def compute_expansion_metrics(db: Session) -> dict[str, float]:
    """Compute expansion quality metrics from the LeadQueue."""
    total = db.scalar(select(func.count(LeadQueue.id))) or 0
    if total == 0:
        return {
            "expansion_success_rate": 0.0, "useful_node_ratio": 0.0,
            "rejected_lead_ratio": 0.0, "merge_ratio": 0.0,
            "enhancement_ratio": 0.0, "avg_lead_contribution": 0.0,
            "avg_novelty": 0.0,
        }

    completed = db.scalar(
        select(func.count(LeadQueue.id)).where(LeadQueue.status == "completed")
    ) or 0
    rejected = db.scalar(
        select(func.count(LeadQueue.id)).where(LeadQueue.status == "rejected")
    ) or 0

    # Count investigation nodes (created by expansion)
    investigation_nodes = db.execute(
        select(Node).where(Node.event_type == "investigation")
    ).scalars().all()

    useful = sum(
        1 for n in investigation_nodes
        if n.research_status == "completed"
        and db.scalar(select(func.count(Edge.id)).where(Edge.from_node_id == n.id)) > 0
    )
    total_inv = len(investigation_nodes) if investigation_nodes else 1

    return {
        "expansion_success_rate": round(completed / total, 4),
        "useful_node_ratio": round(useful / total_inv, 4),
        "rejected_lead_ratio": round(rejected / total, 4),
        "merge_ratio": 0.0,  # Tracked per cycle in run_expansion_cycle metrics
        "enhancement_ratio": 0.0,  # Tracked per cycle
        "avg_lead_contribution": round(
            float(db.scalar(select(func.avg(LeadQueue.dynamic_score))) or 0.0), 4
        ),
        "avg_novelty": 0.0,  # Requires per-lead novelty tracking
    }


# ---------------------------------------------------------------------------
# Part 3: Knowledge Quality Metrics
# ---------------------------------------------------------------------------

def compute_knowledge_metrics(db: Session) -> dict[str, float]:
    """Compute knowledge quality metrics from the graph."""
    total_nodes = db.scalar(select(func.count(Node.id))) or 0
    total_edges = db.scalar(select(func.count(Edge.id))) or 0
    total_signals = db.scalar(select(func.count(Signal.id))) or 0
    total_impacts = db.scalar(select(func.count(Impact.id))) or 0
    total_profiles = db.scalar(select(func.count(NodeResearchProfile.id))) or 0

    researched_count = db.scalar(
        select(func.count(Node.id)).where(Node.research_status == "completed")
    ) or 0

    if total_nodes == 0:
        return {
            "knowledge_density": 0.0, "evidence_density": 0.0,
            "connection_density": 0.0, "research_density": 0.0,
            "compression_ratio": 0.0,
        }

    # Knowledge Density
    avg_edges = total_edges / total_nodes if total_nodes else 0
    kd = (researched_count * avg_edges + total_signals + total_impacts) / total_nodes

    # Evidence Density
    ed = total_profiles / researched_count if researched_count > 0 else 0.0

    # Connection Density
    max_possible = total_nodes * (total_nodes - 1) if total_nodes > 1 else 1
    cd = (2 * total_edges) / max_possible

    # Research Density
    rd = researched_count / total_nodes

    return {
        "knowledge_density": round(kd, 4),
        "evidence_density": round(ed, 4),
        "connection_density": round(cd, 6),
        "research_density": round(rd, 4),
        "compression_ratio": 0.0,  # Requires cycle-level merge/enhance tracking
    }


# ---------------------------------------------------------------------------
# Part 5: Knowledge Reuse Metrics
# ---------------------------------------------------------------------------

def compute_reuse_metrics(db: Session) -> dict[str, float]:
    """Compute knowledge reuse metrics."""
    total = db.scalar(select(func.count(LeadQueue.id))) or 0
    if total == 0:
        return {
            "reuse_ratio": 0.0, "link_ratio": 0.0,
            "duplicate_prevention_rate": 0.0,
        }

    rejected = db.scalar(
        select(func.count(LeadQueue.id)).where(LeadQueue.status == "rejected")
    ) or 0

    # Link edges created by expansion (relation_type = "links_to")
    link_edges = db.scalar(
        select(func.count(Edge.id)).where(Edge.relation_type == "links_to")
    ) or 0

    completed = db.scalar(
        select(func.count(LeadQueue.id)).where(LeadQueue.status == "completed")
    ) or 0

    return {
        "reuse_ratio": round(link_edges / max(completed, 1), 4),
        "link_ratio": round(link_edges / total, 4),
        "duplicate_prevention_rate": round(rejected / total, 4),
    }


# ---------------------------------------------------------------------------
# Part 6: Investigation Efficiency Metrics
# ---------------------------------------------------------------------------

def compute_efficiency_metrics(db: Session) -> dict[str, float]:
    """Compute investigation efficiency metrics."""
    completed_goals = db.execute(
        select(InvestigationGoal).where(InvestigationGoal.status == "completed")
    ).scalars().all()

    if not completed_goals:
        return {
            "avg_nodes_per_goal": 0.0,
            "avg_expansions_per_goal": 0.0,
            "budget_efficiency": 0.0,
        }

    total_expansions = sum(g.expansions_used for g in completed_goals)

    # Count nodes created during goal lifecycles
    goal_related_node_count = 0
    for g in completed_goals:
        related = _find_goal_related_nodes(db, g)
        goal_related_node_count += len(related)

    n_goals = len(completed_goals)
    avg_npg = goal_related_node_count / n_goals
    avg_epg = total_expansions / n_goals

    # Budget efficiency: avg of (completion * budget / used)
    efficiencies = []
    for g in completed_goals:
        if g.expansions_used > 0:
            be = (g.completion_score * g.expansion_budget) / g.expansions_used
            efficiencies.append(min(be, 1.0))
        else:
            efficiencies.append(1.0 if g.completion_score > 0 else 0.0)

    avg_be = sum(efficiencies) / len(efficiencies) if efficiencies else 0.0

    return {
        "avg_nodes_per_goal": round(avg_npg, 2),
        "avg_expansions_per_goal": round(avg_epg, 2),
        "budget_efficiency": round(avg_be, 4),
    }


# ---------------------------------------------------------------------------
# Part 7: Longitudinal Learning
# ---------------------------------------------------------------------------

def compute_learning_index(db: Session) -> dict[str, float]:
    """Compute growth rates and learning index from the two most recent snapshots."""
    snapshots = db.execute(
        select(EvaluationSnapshot)
        .order_by(EvaluationSnapshot.created_at.desc())
        .limit(2)
    ).scalars().all()

    if len(snapshots) < 2:
        return {
            "graph_growth_rate": 0.0,
            "knowledge_growth_rate": 0.0,
            "learning_index": 1.0,
        }

    current, previous = snapshots[0], snapshots[1]

    ggr = (current.total_nodes - previous.total_nodes) / max(previous.total_nodes, 1)
    kgr = (current.knowledge_density - previous.knowledge_density) / max(previous.knowledge_density, 0.01)
    li = kgr / max(ggr, 0.01) if ggr > 0 else (1.5 if kgr > 0 else 1.0)

    return {
        "graph_growth_rate": round(ggr, 4),
        "knowledge_growth_rate": round(kgr, 4),
        "learning_index": round(li, 4),
    }


def compute_metric_trend(db: Session, metric_name: str, window: int = 10) -> float:
    """Compute trend direction for a named metric over recent snapshots.

    Returns a value between -1.0 and +1.0.
    """
    snapshots = db.execute(
        select(EvaluationSnapshot)
        .order_by(EvaluationSnapshot.created_at.desc())
        .limit(window)
    ).scalars().all()

    if len(snapshots) < 2:
        return 0.0

    # Reverse to chronological order
    snapshots = list(reversed(snapshots))

    values = []
    for s in snapshots:
        val = getattr(s, metric_name, None)
        if val is not None:
            values.append(float(val))

    if len(values) < 2:
        return 0.0

    signs = []
    for i in range(1, len(values)):
        diff = values[i] - values[i - 1]
        if diff > 0:
            signs.append(1)
        elif diff < 0:
            signs.append(-1)
        else:
            signs.append(0)

    return round(sum(signs) / len(signs), 2) if signs else 0.0


# ---------------------------------------------------------------------------
# Part 4: Global Explanation Score
# ---------------------------------------------------------------------------

def compute_global_explanation_score(db: Session) -> float:
    """Average explanation score across all goals that have been evaluated."""
    goals = db.execute(
        select(InvestigationGoal).where(
            InvestigationGoal.status.in_(["completed", "active", "paused", "abandoned"])
        )
    ).scalars().all()

    if not goals:
        return 0.0

    scores = [compute_explanation_score_for_goal(db, g) for g in goals]
    return round(sum(scores) / len(scores), 4)
