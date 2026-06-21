"""Dashboard Aggregation Engine.

Creates EvaluationSnapshot records and builds the system health dashboard payload.
"""

import logging
from datetime import datetime, timezone

from sqlalchemy import select, func, desc
from sqlalchemy.orm import Session

from models.news_intelligence import (
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
from evaluation.metrics import (
    compute_expansion_metrics,
    compute_knowledge_metrics,
    compute_reuse_metrics,
    compute_efficiency_metrics,
    compute_learning_index,
    compute_metric_trend,
    compute_global_explanation_score,
    compute_goal_coverage,
    compute_goal_efficiency,
    compute_goal_confidence,
    compute_goal_satisfaction,
    compute_completion_score,
    evaluate_goal,
)
from expansion.goals import compute_completion_score

logger = logging.getLogger(__name__)


def create_snapshot(
    db: Session,
    snapshot_type: str = "manual",
    system_version: str = "v1.0",
) -> EvaluationSnapshot:
    """Create a point-in-time EvaluationSnapshot with all metrics."""

    # --- Graph totals ---
    total_nodes = db.scalar(select(func.count(Node.id))) or 0
    total_edges = db.scalar(select(func.count(Edge.id))) or 0
    total_goals = db.scalar(select(func.count(InvestigationGoal.id))) or 0
    total_leads = db.scalar(select(func.count(LeadQueue.id))) or 0

    # --- Goal metrics ---
    completed_goals = db.execute(
        select(InvestigationGoal).where(InvestigationGoal.status == "completed")
    ).scalars().all()
    all_goals = db.execute(
        select(InvestigationGoal)
    ).scalars().all()

    goal_success_rate = len(completed_goals) / len(all_goals) if all_goals else 0.0

    if all_goals:
        completions = [compute_completion_score(db, g) for g in all_goals]
        coverages = [compute_goal_coverage(db, g) for g in all_goals]
        efficiencies = [compute_goal_efficiency(g) for g in all_goals]
        confidences = [compute_goal_confidence(db, g) for g in all_goals]
        avg_completion = sum(completions) / len(completions)
        avg_coverage = sum(coverages) / len(coverages)
        avg_efficiency = sum(efficiencies) / len(efficiencies)
        avg_confidence = sum(confidences) / len(confidences)
    else:
        avg_completion = avg_coverage = avg_efficiency = avg_confidence = 0.0

    # --- Expansion metrics ---
    expansion = compute_expansion_metrics(db)

    # --- Knowledge metrics ---
    knowledge = compute_knowledge_metrics(db)

    # --- Reuse metrics ---
    reuse = compute_reuse_metrics(db)

    # --- Efficiency metrics ---
    efficiency = compute_efficiency_metrics(db)

    # --- Explanation score ---
    explanation = compute_global_explanation_score(db)

    # --- Learning index ---
    learning = compute_learning_index(db)

    # --- Loop risk ---
    avg_loop_risk = 0.0  # Requires per-lead tracking; use 0.0 for now

    snapshot = EvaluationSnapshot(
        snapshot_type=snapshot_type,
        system_version=system_version,
        total_nodes=total_nodes,
        total_edges=total_edges,
        total_goals=total_goals,
        total_leads_processed=total_leads,

        goal_success_rate=round(goal_success_rate, 4),
        avg_goal_completion=round(avg_completion, 4),
        avg_goal_coverage=round(avg_coverage, 4),
        avg_goal_efficiency=round(avg_efficiency, 4),
        avg_goal_confidence=round(avg_confidence, 4),

        expansion_success_rate=expansion["expansion_success_rate"],
        useful_node_ratio=expansion["useful_node_ratio"],
        rejected_lead_ratio=expansion["rejected_lead_ratio"],
        merge_ratio=expansion["merge_ratio"],
        enhancement_ratio=expansion["enhancement_ratio"],
        avg_lead_contribution=expansion["avg_lead_contribution"],
        avg_novelty=expansion["avg_novelty"],

        knowledge_density=knowledge["knowledge_density"],
        knowledge_growth=0.0,
        evidence_density=knowledge["evidence_density"],
        connection_density=knowledge["connection_density"],
        research_density=knowledge["research_density"],
        compression_ratio=knowledge["compression_ratio"],

        explanation_score=explanation,

        reuse_ratio=reuse["reuse_ratio"],
        link_ratio=reuse["link_ratio"],
        duplicate_prevention_rate=reuse["duplicate_prevention_rate"],

        avg_nodes_per_goal=efficiency["avg_nodes_per_goal"],
        avg_expansions_per_goal=efficiency["avg_expansions_per_goal"],
        budget_efficiency=efficiency["budget_efficiency"],

        graph_growth_rate=learning["graph_growth_rate"],
        knowledge_growth_rate=learning["knowledge_growth_rate"],
        avg_loop_risk=avg_loop_risk,
    )

    db.add(snapshot)
    db.commit()

    logger.info("Created EvaluationSnapshot %d (type=%s)", snapshot.id, snapshot_type)
    return snapshot


def compute_diagnosis(learning_index: float, avg_satisfaction: float) -> str:
    """Compute single-word system diagnosis."""
    if learning_index > 1.5 and avg_satisfaction > 0.70:
        return "THRIVING"
    elif learning_index > 1.0 and avg_satisfaction > 0.50:
        return "LEARNING"
    elif learning_index >= 0.8 and avg_satisfaction > 0.30:
        return "GROWING"
    elif learning_index < 0.8:
        return "INFLATING"
    else:
        return "STRUGGLING"


def build_dashboard(db: Session) -> dict:
    """Build the full system health dashboard payload."""

    # Get latest snapshot or create one
    latest = db.scalar(
        select(EvaluationSnapshot).order_by(desc(EvaluationSnapshot.created_at)).limit(1)
    )
    if not latest:
        latest = create_snapshot(db, snapshot_type="manual")

    # Learning index
    learning = compute_learning_index(db)

    # Goal satisfaction (use latest goal evaluations)
    goal_evals = db.execute(
        select(GoalEvaluation).order_by(desc(GoalEvaluation.created_at)).limit(20)
    ).scalars().all()

    avg_satisfaction = 0.0
    if goal_evals:
        avg_satisfaction = sum(ge.satisfaction_score for ge in goal_evals) / len(goal_evals)

    # Trends
    trends = {
        "completion_trend": compute_metric_trend(db, "avg_goal_completion"),
        "density_trend": compute_metric_trend(db, "knowledge_density"),
        "reuse_trend": compute_metric_trend(db, "reuse_ratio"),
        "efficiency_trend": compute_metric_trend(db, "budget_efficiency"),
    }

    diagnosis = compute_diagnosis(learning["learning_index"], avg_satisfaction)

    return {
        "system_health": {
            "total_nodes": latest.total_nodes,
            "total_edges": latest.total_edges,
            "total_goals": latest.total_goals,
            "total_leads_processed": latest.total_leads_processed,
            "graph_growth_rate": latest.graph_growth_rate,
            "learning_index": learning["learning_index"],
        },
        "knowledge_quality": {
            "knowledge_density": latest.knowledge_density,
            "evidence_density": latest.evidence_density,
            "connection_density": latest.connection_density,
            "research_density": latest.research_density,
            "compression_ratio": latest.compression_ratio,
        },
        "goal_performance": {
            "goal_success_rate": latest.goal_success_rate,
            "avg_completion": latest.avg_goal_completion,
            "avg_coverage": latest.avg_goal_coverage,
            "avg_efficiency": latest.avg_goal_efficiency,
            "avg_confidence": latest.avg_goal_confidence,
            "avg_satisfaction": round(avg_satisfaction, 4),
        },
        "expansion_quality": {
            "expansion_success_rate": latest.expansion_success_rate,
            "useful_node_ratio": latest.useful_node_ratio,
            "rejected_lead_ratio": latest.rejected_lead_ratio,
            "merge_ratio": latest.merge_ratio,
            "enhancement_ratio": latest.enhancement_ratio,
            "avg_lead_contribution": latest.avg_lead_contribution,
            "avg_novelty": latest.avg_novelty,
        },
        "intelligence_quality": {
            "explanation_score": latest.explanation_score,
            "reuse_ratio": latest.reuse_ratio,
            "link_ratio": latest.link_ratio,
            "duplicate_prevention_rate": latest.duplicate_prevention_rate,
            "avg_loop_risk": latest.avg_loop_risk,
        },
        "trend": trends,
        "diagnosis": diagnosis,
    }
