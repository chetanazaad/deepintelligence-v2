"""API endpoints for System Evaluation.

Provides endpoints for fetching the dashboard, evaluation snapshots,
running benchmarks, and viewing trends.
"""

import logging
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, desc
from sqlalchemy.orm import Session

from api.deps import get_db
from evaluation.dashboard import build_dashboard, create_snapshot
from evaluation.benchmarks import seed_default_scenarios, run_benchmark, get_scenario_comparison
from evaluation.metrics import evaluate_goal, compute_metric_trend
from models.news_intelligence import (
    EvaluationSnapshot,
    GoalEvaluation,
    BenchmarkScenario,
    BenchmarkResult,
    InvestigationGoal,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["evaluation"])


# ---------------------------------------------------------------------------
# Request / Response Models
# ---------------------------------------------------------------------------

class CreateSnapshotRequest(BaseModel):
    snapshot_type: str = Field(default="manual", description="Type of snapshot (manual, pipeline_run, etc.)")
    system_version: str = Field(default="v1.0", description="Version of the system being evaluated")


class RunBenchmarkRequest(BaseModel):
    system_version: str = Field(default="v1.0", description="Version of the system being evaluated")
    expansion_cycles: int = Field(default=5, ge=1, le=20, description="Number of expansion cycles to run")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if isinstance(value, datetime) else None


def _snapshot_to_dict(snap: EvaluationSnapshot) -> dict:
    return {
        "id": snap.id,
        "snapshot_type": snap.snapshot_type,
        "system_version": snap.system_version,
        "benchmark_scenario_id": snap.benchmark_scenario_id,
        "total_nodes": snap.total_nodes,
        "total_edges": snap.total_edges,
        "total_goals": snap.total_goals,
        "total_leads_processed": snap.total_leads_processed,
        "goal_success_rate": snap.goal_success_rate,
        "avg_goal_completion": snap.avg_goal_completion,
        "avg_goal_coverage": snap.avg_goal_coverage,
        "avg_goal_efficiency": snap.avg_goal_efficiency,
        "avg_goal_confidence": snap.avg_goal_confidence,
        "expansion_success_rate": snap.expansion_success_rate,
        "useful_node_ratio": snap.useful_node_ratio,
        "rejected_lead_ratio": snap.rejected_lead_ratio,
        "merge_ratio": snap.merge_ratio,
        "enhancement_ratio": snap.enhancement_ratio,
        "avg_lead_contribution": snap.avg_lead_contribution,
        "avg_novelty": snap.avg_novelty,
        "knowledge_density": snap.knowledge_density,
        "knowledge_growth": snap.knowledge_growth,
        "evidence_density": snap.evidence_density,
        "connection_density": snap.connection_density,
        "research_density": snap.research_density,
        "compression_ratio": snap.compression_ratio,
        "explanation_score": snap.explanation_score,
        "reuse_ratio": snap.reuse_ratio,
        "link_ratio": snap.link_ratio,
        "duplicate_prevention_rate": snap.duplicate_prevention_rate,
        "avg_nodes_per_goal": snap.avg_nodes_per_goal,
        "avg_expansions_per_goal": snap.avg_expansions_per_goal,
        "budget_efficiency": snap.budget_efficiency,
        "graph_growth_rate": snap.graph_growth_rate,
        "knowledge_growth_rate": snap.knowledge_growth_rate,
        "avg_loop_risk": snap.avg_loop_risk,
        "created_at": _iso(snap.created_at),
        "metadata_json": snap.metadata_json,
    }


def _goal_eval_to_dict(ge: GoalEvaluation) -> dict:
    return {
        "id": ge.id,
        "goal_id": ge.goal_id,
        "snapshot_id": ge.snapshot_id,
        "completion_score": ge.completion_score,
        "coverage_score": ge.coverage_score,
        "efficiency_score": ge.efficiency_score,
        "confidence_score": ge.confidence_score,
        "satisfaction_score": ge.satisfaction_score,
        "explanation_score": ge.explanation_score,
        "nodes_created": ge.nodes_created,
        "nodes_enhanced": ge.nodes_enhanced,
        "nodes_linked": ge.nodes_linked,
        "leads_rejected": ge.leads_rejected,
        "leads_total": ge.leads_total,
        "expansions_used": ge.expansions_used,
        "expansion_budget": ge.expansion_budget,
        "knowledge_categories_required": ge.knowledge_categories_required,
        "knowledge_categories_covered": ge.knowledge_categories_covered,
        "causal_chain_depth": ge.causal_chain_depth,
        "created_at": _iso(ge.created_at),
        "evaluation_json": ge.evaluation_json,
    }


def _scenario_to_dict(sc: BenchmarkScenario) -> dict:
    return {
        "id": sc.id,
        "name": sc.name,
        "description": sc.description,
        "goal_question": sc.goal_question,
        "goal_type": sc.goal_type,
        "seed_entities": sc.seed_entities,
        "expected_categories": sc.expected_categories,
        "expected_min_completion": sc.expected_min_completion,
        "created_at": _iso(sc.created_at),
        "metadata_json": sc.metadata_json,
    }


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/evaluation/dashboard")
def get_dashboard(db: Session = Depends(get_db)) -> dict:
    """Fetch the full system health evaluation dashboard."""
    try:
        # Seed default benchmark scenarios if they aren't present
        seed_default_scenarios(db)
        return build_dashboard(db)
    except Exception as e:
        logger.exception("Error building evaluation dashboard")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/evaluation/snapshots")
def list_snapshots(
    limit: int = Query(default=10, ge=1, le=100),
    db: Session = Depends(get_db),
) -> dict:
    """List recent evaluation snapshots."""
    snaps = db.execute(
        select(EvaluationSnapshot).order_by(desc(EvaluationSnapshot.created_at)).limit(limit)
    ).scalars().all()
    return {
        "count": len(snaps),
        "snapshots": [_snapshot_to_dict(s) for s in snaps]
    }


@router.get("/evaluation/snapshots/{snapshot_id}")
def get_snapshot(
    snapshot_id: int,
    db: Session = Depends(get_db),
) -> dict:
    """Get a single evaluation snapshot by ID."""
    snap = db.scalar(select(EvaluationSnapshot).where(EvaluationSnapshot.id == snapshot_id))
    if not snap:
        raise HTTPException(status_code=404, detail=f"Snapshot {snapshot_id} not found.")
    return _snapshot_to_dict(snap)


@router.post("/evaluation/snapshot")
def trigger_snapshot(
    body: CreateSnapshotRequest = CreateSnapshotRequest(),
    db: Session = Depends(get_db),
) -> dict:
    """Create a new point-in-time evaluation snapshot."""
    try:
        snap = create_snapshot(
            db,
            snapshot_type=body.snapshot_type,
            system_version=body.system_version,
        )
        return _snapshot_to_dict(snap)
    except Exception as e:
        logger.exception("Error triggering snapshot")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/evaluation/goals/{goal_id}")
def evaluate_goal_endpoint(
    goal_id: int,
    db: Session = Depends(get_db),
) -> dict:
    """Get or compute evaluation metrics for a specific goal."""
    goal = db.scalar(select(InvestigationGoal).where(InvestigationGoal.id == goal_id))
    if not goal:
        raise HTTPException(status_code=404, detail=f"Goal {goal_id} not found.")

    # Find existing or evaluate fresh
    ge = db.scalar(
        select(GoalEvaluation)
        .where(GoalEvaluation.goal_id == goal_id)
        .order_by(desc(GoalEvaluation.created_at))
        .limit(1)
    )
    if not ge:
        ge = evaluate_goal(db, goal)

    return _goal_eval_to_dict(ge)


@router.get("/evaluation/trends")
def get_trends(
    metric: str = Query(..., description="Name of the metric in EvaluationSnapshot to analyze"),
    window: int = Query(default=10, ge=2, le=50, description="Number of snapshots to look back"),
    db: Session = Depends(get_db),
) -> dict:
    """Compute trend direction (-1.0 to 1.0) and fetch history for a specific metric."""
    # Verify metric field exists
    if not hasattr(EvaluationSnapshot, metric):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid metric '{metric}'. Field does not exist on EvaluationSnapshot."
        )

    trend = compute_metric_trend(db, metric, window=window)

    # Fetch recent snapshots
    snapshots = db.execute(
        select(EvaluationSnapshot)
        .order_by(desc(EvaluationSnapshot.created_at))
        .limit(window)
    ).scalars().all()

    history = [
        {
            "snapshot_id": s.id,
            "created_at": _iso(s.created_at),
            "system_version": s.system_version,
            "value": getattr(s, metric)
        }
        for s in reversed(snapshots)
    ]

    return {
        "metric": metric,
        "trend_score": trend,
        "history": history,
    }


@router.get("/evaluation/benchmarks")
def list_benchmarks(db: Session = Depends(get_db)) -> dict:
    """List all available benchmark scenarios."""
    seed_default_scenarios(db)
    scenarios = db.execute(select(BenchmarkScenario)).scalars().all()
    return {
        "count": len(scenarios),
        "scenarios": [_scenario_to_dict(s) for s in scenarios]
    }


@router.post("/evaluation/benchmarks/{scenario_id}/run")
def run_benchmark_endpoint(
    scenario_id: int,
    body: RunBenchmarkRequest = RunBenchmarkRequest(),
    db: Session = Depends(get_db),
) -> dict:
    """Run a specific benchmark scenario."""
    scenario = db.scalar(select(BenchmarkScenario).where(BenchmarkScenario.id == scenario_id))
    if not scenario:
        raise HTTPException(status_code=404, detail=f"Benchmark scenario {scenario_id} not found.")

    try:
        result = run_benchmark(
            db,
            scenario_id=scenario_id,
            system_version=body.system_version,
            expansion_cycles=body.expansion_cycles,
        )
        return {
            "id": result.id,
            "scenario_id": result.scenario_id,
            "snapshot_id": result.snapshot_id,
            "system_version": result.system_version,
            "completion_score": result.completion_score,
            "coverage_score": result.coverage_score,
            "efficiency_score": result.efficiency_score,
            "explanation_score": result.explanation_score,
            "knowledge_density": result.knowledge_density,
            "passed": result.passed,
            "created_at": _iso(result.created_at),
            "comparison": result.comparison_json,
        }
    except Exception as e:
        logger.exception("Error running benchmark scenario %d", scenario_id)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/evaluation/benchmarks/{scenario_id}/compare")
def compare_benchmark(
    scenario_id: int,
    db: Session = Depends(get_db),
) -> dict:
    """Get the latest version comparison for a benchmark scenario."""
    scenario = db.scalar(select(BenchmarkScenario).where(BenchmarkScenario.id == scenario_id))
    if not scenario:
        raise HTTPException(status_code=404, detail=f"Benchmark scenario {scenario_id} not found.")

    return get_scenario_comparison(db, scenario_id)
