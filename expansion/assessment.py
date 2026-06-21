"""Intelligence Assessment Engine.

Provides evidence synthesis, confidence calculation, alternative hypotheses,
knowledge gap classification, future scenarios generation, and executive summaries.
"""

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select, func, and_, or_
from sqlalchemy.orm import Session

from models.news_intelligence import (
    Edge,
    Impact,
    InvestigationGoal,
    Node,
    NodeResearchProfile,
    Signal,
    IntelligenceAssessment,
    AssessmentQualityMetric,
)
from expansion.goals import (
    _find_goal_related_nodes,
    get_goal_knowledge_coverage,
    categorize_entity_or_lead,
    REQUIRED_KNOWLEDGE_CATEGORIES,
)
from evaluation.metrics import compute_goal_coverage

logger = logging.getLogger(__name__)


def synthesize_evidence_strength(db: Session, goal: InvestigationGoal, related_ids: list[int]) -> float:
    """Synthesize evidence strength across nodes, edges, coverage, impacts, and signals."""
    if not related_ids:
        return 0.0

    # 1. Average Node Confidence (30%)
    avg_node_conf = db.scalar(
        select(func.avg(Node.confidence_score)).where(Node.id.in_(related_ids))
    ) or 0.0

    # 2. Average Edge Confidence (25%)
    avg_edge_conf = db.scalar(
        select(func.avg(Edge.confidence_score))
        .where(Edge.from_node_id.in_(related_ids))
        .where(Edge.to_node_id.in_(related_ids))
    ) or 0.0

    # 3. Coverage (20%)
    cov = compute_goal_coverage(db, goal)

    # 4. Impacts (15%)
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
    impact_score = min(len(sectors) / 3.0, 1.0)

    # 5. Signals (10%)
    signals_count = db.scalar(
        select(func.count(Signal.id)).where(Signal.node_id.in_(related_ids))
    ) or 0
    signal_score = min(signals_count / 5.0, 1.0)

    ess = (
        0.30 * float(avg_node_conf)
        + 0.25 * float(avg_edge_conf)
        + 0.20 * cov
        + 0.15 * impact_score
        + 0.10 * signal_score
    )
    return round(min(ess, 1.0), 4)


def calculate_confidence(
    db: Session,
    goal: InvestigationGoal,
    related_ids: list[int],
    evidence_strength: float,
) -> tuple[float, str]:
    """Calculate the final confidence score and qualitative level."""
    if not related_ids:
        return 0.0, "LOW"

    # 1. Source Diversity (25%)
    distinct_clusters = db.scalar(
        select(func.count(func.distinct(Node.cluster_id))).where(Node.id.in_(related_ids))
    ) or 0
    source_div = min(distinct_clusters / 5.0, 1.0)

    # 2. Causal Consistency (20%)
    causal_consistency = 1.0

    # 3. Knowledge Coverage (15%)
    cov = compute_goal_coverage(db, goal)

    # 4. Signal Agreement (15%)
    signals = db.execute(
        select(Signal).where(Signal.node_id.in_(related_ids))
    ).scalars().all()
    if not signals:
        signal_agreement = 1.0
    else:
        sig_counts = {"risk": 0, "opportunity": 0, "transition": 0}
        for sig in signals:
            sig_type = sig.signal_type or "transition"
            if sig_type in sig_counts:
                sig_counts[sig_type] += 1
        max_type_count = max(sig_counts.values())
        signal_agreement = max_type_count / len(signals)

    # 5. Combine with ESS (25%)
    conf = (
        0.25 * evidence_strength
        + 0.25 * source_div
        + 0.20 * causal_consistency
        + 0.15 * cov
        + 0.15 * signal_agreement
    )
    conf = round(min(conf, 1.0), 4)

    if conf >= 0.75:
        level = "HIGH"
    elif conf >= 0.40:
        level = "MEDIUM"
    else:
        level = "LOW"

    return conf, level


def identify_alternative_explanations(db: Session, goal: InvestigationGoal, related_ids: list[int]) -> dict:
    """Identify and rank alternative explanations based on node categories."""
    if not related_ids:
        return {"primary": "No evidence gathered", "alternatives": []}

    req_cats = REQUIRED_KNOWLEDGE_CATEGORIES.get(goal.goal_type, REQUIRED_KNOWLEDGE_CATEGORIES["CUSTOM"])

    # Group nodes by category
    cat_scores = {cat: [] for cat in req_cats}
    nodes = db.execute(select(Node).where(Node.id.in_(related_ids))).scalars().all()
    
    for n in nodes:
        node_cats = categorize_entity_or_lead(n.entity, n.entity_type or "topic", n.description or "")
        for cat in req_cats:
            if cat in node_cats:
                # Score node contribution
                score = (n.importance_score or 0.5) * (n.confidence_score or 0.5)
                cat_scores[cat].append((n.entity, score))

    ranked_categories = []
    for cat, list_vals in cat_scores.items():
        if list_vals:
            avg_score = sum(val[1] for val in list_vals) / len(list_vals)
            entities = [val[0] for val in list_vals]
            ranked_categories.append({
                "explanation": f"Investigation focused on {cat.lower()} factors, driven by entities: {', '.join(entities[:3])}",
                "category": cat,
                "score": round(avg_score, 4)
            })

    # Sort descending
    ranked_categories.sort(key=lambda x: x["score"], reverse=True)

    if not ranked_categories:
        return {
            "primary": "No specific category explanation can be established.",
            "alternatives": []
        }

    return {
        "primary": ranked_categories[0]["explanation"],
        "alternatives": ranked_categories[1:]
    }


def identify_knowledge_gaps(db: Session, goal: InvestigationGoal) -> dict:
    """Identify knowledge gaps and classify them as critical, moderate, or minor."""
    coverage = get_goal_knowledge_coverage(db, goal)
    missing = coverage["missing"]
    
    gaps = {
        "critical": [],
        "moderate": [],
        "minor": []
    }
    
    priority = goal.priority or 1

    # Map missing categories to urgency
    for cat in missing:
        if priority >= 8 or cat in ["COMPANY", "POLICY"]:
            gaps["critical"].append({
                "category": cat,
                "reason": f"Required category '{cat}' is missing for a high-priority {goal.goal_type} goal."
            })
        elif 4 <= priority <= 7:
            gaps["moderate"].append({
                "category": cat,
                "reason": f"Required category '{cat}' is missing for this mid-priority goal."
            })
        else:
            gaps["minor"].append({
                "category": cat,
                "reason": f"Required category '{cat}' is missing for this low-priority goal."
            })

    return gaps


def generate_future_scenarios(db: Session, goal: InvestigationGoal, related_ids: list[int]) -> dict:
    """Generate likely, possible, and unlikely future scenarios based on signals and impacts."""
    if not related_ids:
        return {
            "likely": "Investigation still ongoing. Insufficient evidence for forecasting.",
            "possible": "N/A",
            "unlikely": "N/A"
        }

    # Fetch signals
    signals = db.execute(
        select(Signal).where(Signal.node_id.in_(related_ids))
    ).scalars().all()

    # Collect entities and descriptions
    nodes = db.execute(select(Node).where(Node.id.in_(related_ids))).scalars().all()
    entities = [n.entity for n in nodes[:3]]

    opp_signals = [s for s in signals if s.signal_type == "opportunity"]
    risk_signals = [s for s in signals if s.signal_type == "risk"]

    # Heuristically build scenario summaries
    if len(opp_signals) > len(risk_signals):
        likely_scen = f"Expansion and integration of {', '.join(entities)} accelerates, leading to positive market synergies."
        possible_scen = f"Competitors challenge the acquisition, resulting in regulatory reviews or delays."
        unlikely_scen = f"A major regional market collapse forces abandonment of the current logistics footprint."
    elif len(risk_signals) > len(opp_signals):
        likely_scen = f"Regulatory bottlenecks and rising operational costs of {', '.join(entities)} constrain project margins."
        possible_scen = f"Successful mitigation efforts stabilize the project, turning it into a slow-growth asset."
        unlikely_scen = f"Rapid structural deregulation leads to windfalls and extreme profits."
    else:
        likely_scen = f"The current status quo for {', '.join(entities)} persists, yielding moderate gains."
        possible_scen = f"A shift in maritime / trade route policies modifies the value proposition."
        unlikely_scen = f"Total failure or termination of associated policy subsidies."

    return {
        "likely": likely_scen,
        "possible": possible_scen,
        "unlikely": unlikely_scen
    }


def generate_executive_summary(
    goal: InvestigationGoal,
    confidence_level: str,
    confidence_score: float,
    evidence_strength: float,
    gaps: dict,
    related_ids: list[int]
) -> dict:
    """Compile executive summary of findings, risks, opportunities, and unknowns."""
    critical_unknowns = [gap["category"] for gap in gaps["critical"]]

    summary = {
        "key_findings": f"Investigation goal '{goal.goal_question}' evaluated with {confidence_level} confidence (score: {confidence_score}). Evidence Strength is {evidence_strength}.",
        "confidence": {
            "level": confidence_level,
            "score": confidence_score
        },
        "risks": f"Contains {len(gaps['critical'])} critical knowledge gaps. Risk variables exist across missing information.",
        "opportunities": "Further expansion cycles can resolve remaining unknowns.",
        "unknowns": critical_unknowns
    }
    return summary


def create_or_update_assessment(db: Session, goal_id: int, status: str = "draft") -> IntelligenceAssessment:
    """Create or update an IntelligenceAssessment record for a given goal."""
    goal = db.scalar(select(InvestigationGoal).where(InvestigationGoal.id == goal_id))
    if not goal:
        raise ValueError(f"Goal {goal_id} not found.")

    related_ids = _find_goal_related_nodes(db, goal)

    # 1. Synthesize evidence
    evidence_strength = synthesize_evidence_strength(db, goal, related_ids)

    # 2. Confidence
    confidence_score, confidence_level = calculate_confidence(db, goal, related_ids, evidence_strength)

    # 3. Alternatives
    alternatives = identify_alternative_explanations(db, goal, related_ids)

    # 4. Gaps
    gaps = identify_knowledge_gaps(db, goal)

    # 5. Scenarios
    scenarios = generate_future_scenarios(db, goal, related_ids)

    # 6. Executive summary
    exec_summary = generate_executive_summary(
        goal, confidence_level, confidence_score, evidence_strength, gaps, related_ids
    )

    # Build qualitative text
    primary_expl = alternatives.get("primary", "N/A")
    gaps_str = ", ".join([g["category"] for g in gaps["critical"] + gaps["moderate"]])
    assessment_text = (
        f"INTELLIGENCE REPORT (v{goal.id}):\n"
        f"Goal Question: {goal.goal_question}\n"
        f"Main Hypothesis: {primary_expl}\n"
        f"Likely Future Scenario: {scenarios['likely']}\n"
        f"Critical/Moderate Gaps: {gaps_str if gaps_str else 'None'}\n"
    )

    # Check if there is an existing assessment for this goal
    existing = db.scalar(
        select(IntelligenceAssessment)
        .where(IntelligenceAssessment.goal_id == goal_id)
        .order_by(IntelligenceAssessment.version.desc())
        .limit(1)
    )

    if existing and existing.status == "draft":
        # Update in-place
        existing.confidence_score = confidence_score
        existing.confidence_level = confidence_level
        existing.assessment_text = assessment_text
        existing.evidence_summary = {
            "related_nodes": related_ids,
            "evidence_strength": evidence_strength
        }
        existing.knowledge_gaps = gaps
        existing.alternative_explanations = alternatives
        existing.future_scenarios = scenarios
        existing.executive_summary = exec_summary
        existing.generated_at = datetime.now(timezone.utc)
        existing.status = status
        db.commit()
        
        # Track quality
        _track_quality_metric(db, existing, evidence_strength, related_ids)
        return existing
    else:
        # Create a new version
        version = (existing.version + 1) if existing else 1
        
        # Mark previous final assessments as superseded
        if existing and existing.status == "final":
            existing.status = "superseded"
            db.commit()

        new_assessment = IntelligenceAssessment(
            goal_id=goal_id,
            assessment_type=goal.goal_type,
            confidence_score=confidence_score,
            confidence_level=confidence_level,
            assessment_text=assessment_text,
            evidence_summary={
                "related_nodes": related_ids,
                "evidence_strength": evidence_strength
            },
            knowledge_gaps=gaps,
            alternative_explanations=alternatives,
            future_scenarios=scenarios,
            executive_summary=exec_summary,
            version=version,
            status=status,
        )
        db.add(new_assessment)
        db.commit()

        _track_quality_metric(db, new_assessment, evidence_strength, related_ids)
        return new_assessment


def _track_quality_metric(
    db: Session,
    assessment: IntelligenceAssessment,
    evidence_strength: float,
    related_ids: list[int]
) -> AssessmentQualityMetric:
    """Compute and store AssessmentQualityMetric for version tracking."""
    causal_consistency = 1.0
    completeness = 1.0 if assessment.executive_summary and assessment.future_scenarios else 0.5

    stability = 1.0
    prior = db.scalar(
        select(IntelligenceAssessment)
        .where(IntelligenceAssessment.goal_id == assessment.goal_id)
        .where(IntelligenceAssessment.id != assessment.id)
        .order_by(IntelligenceAssessment.version.desc())
        .limit(1)
    )
    if prior:
        len_prior = len(prior.assessment_text or "")
        len_curr = len(assessment.assessment_text or "")
        if len_prior > 0:
            stability = round(min(len_curr, len_prior) / max(len_curr, len_prior), 4)

    # Find latest snapshot
    from models.news_intelligence import EvaluationSnapshot
    latest_snapshot = db.scalar(
        select(EvaluationSnapshot).order_by(EvaluationSnapshot.created_at.desc()).limit(1)
    )
    snapshot_id = latest_snapshot.id if latest_snapshot else None

    metric = AssessmentQualityMetric(
        assessment_id=assessment.id,
        snapshot_id=snapshot_id,
        evidence_strength=evidence_strength,
        causal_consistency=causal_consistency,
        completeness=completeness,
        stability_score=stability
    )
    db.add(metric)
    db.commit()
    return metric
