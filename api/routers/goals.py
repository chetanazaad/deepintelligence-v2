"""API endpoints for Investigation Goals.

Provides CRUD operations, progress tracking, goal hierarchy viewing,
and goal-aware dashboard metrics.
"""

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from api.deps import get_db
from expansion.goals import (
    extract_keywords,
    compute_completion_score,
    check_goal_state,
    classify_goal_intent,
    generate_gap_report,
)
from models.news_intelligence import InvestigationGoal, Node

logger = logging.getLogger(__name__)

router = APIRouter(tags=["goals"])


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------

class CreateGoalRequest(BaseModel):
    origin_node_id: int
    goal_type: str = Field(default="AUTO", description="ROOT_CAUSE | ECONOMIC_DRIVER | POLICY_DRIVER | GEOPOLITICAL_DRIVER | ACTOR_MOTIVATION | FUTURE_CONSEQUENCES | RISK_ANALYSIS | OPPORTUNITY_ANALYSIS | CUSTOM | AUTO")
    goal_question: str = Field(..., min_length=5, description="The investigation question")
    expansion_budget: int = Field(default=20, ge=1, le=100)
    priority: int = Field(default=1, ge=1, le=10)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if isinstance(value, datetime) else None


def _goal_to_dict(goal: InvestigationGoal) -> dict:
    return {
        "id": goal.id,
        "parent_goal_id": goal.parent_goal_id,
        "origin_node_id": goal.origin_node_id,
        "goal_type": goal.goal_type,
        "goal_question": goal.goal_question,
        "keywords": goal.keywords,
        "status": goal.status,
        "confidence": goal.confidence,
        "completion_score": goal.completion_score,
        "expansion_budget": goal.expansion_budget,
        "expansions_used": goal.expansions_used,
        "priority": goal.priority,
        "stall_counter": goal.stall_counter,
        "created_at": _iso(goal.created_at),
        "updated_at": _iso(goal.updated_at),
        "completed_at": _iso(goal.completed_at),
    }


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/goals")
def create_goal(
    body: CreateGoalRequest,
    db: Session = Depends(get_db),
) -> dict:
    """Create a new investigation goal anchored to a node."""
    node = db.scalar(select(Node).where(Node.id == body.origin_node_id))
    if node is None:
        raise HTTPException(status_code=404, detail="Origin node not found.")

    valid_types = {
        "ROOT_CAUSE", "ECONOMIC_DRIVER", "POLICY_DRIVER", "GEOPOLITICAL_DRIVER",
        "ACTOR_MOTIVATION", "FUTURE_CONSEQUENCES", "RISK_ANALYSIS", "OPPORTUNITY_ANALYSIS",
        "CUSTOM", "AUTO",
        # Legacy compatibility mapping
        "ECONOMIC_IMPACT", "GEOPOLITICAL_IMPACT", "POLICY_ANALYSIS", "ACTOR_ANALYSIS", "FUTURE_SCENARIOS"
    }
    if body.goal_type not in valid_types:
        raise HTTPException(status_code=400, detail=f"Invalid goal_type. Must be one of: {valid_types}")

    goal_type = body.goal_type
    if goal_type == "AUTO":
        goal_type = classify_goal_intent(body.goal_question)

    keywords = extract_keywords(body.goal_question)

    goal = InvestigationGoal(
        origin_node_id=body.origin_node_id,
        goal_type=goal_type,
        goal_question=body.goal_question,
        keywords=keywords,
        expansion_budget=body.expansion_budget,
        priority=body.priority,
    )
    db.add(goal)
    db.commit()

    logger.info("Created goal %d: '%s'", goal.id, body.goal_question)
    return _goal_to_dict(goal)


@router.get("/goals")
def list_goals(
    status: str | None = None,
    db: Session = Depends(get_db),
) -> dict:
    """List all investigation goals, optionally filtered by status."""
    query = select(InvestigationGoal).order_by(InvestigationGoal.priority.asc())
    if status:
        query = query.where(InvestigationGoal.status == status)

    goals = db.execute(query).scalars().all()
    return {
        "count": len(goals),
        "goals": [_goal_to_dict(g) for g in goals],
    }


@router.get("/goals/{goal_id}")
def get_goal(
    goal_id: int,
    db: Session = Depends(get_db),
) -> dict:
    """Get a single goal with current progress."""
    goal = db.scalar(select(InvestigationGoal).where(InvestigationGoal.id == goal_id))
    if goal is None:
        raise HTTPException(status_code=404, detail="Goal not found.")

    # Recompute completion score live
    goal.completion_score = compute_completion_score(db, goal)
    db.commit()

    # Fetch sub-goals
    sub_goals = db.execute(
        select(InvestigationGoal)
        .where(InvestigationGoal.parent_goal_id == goal_id)
        .order_by(InvestigationGoal.priority.asc())
    ).scalars().all()

    result = _goal_to_dict(goal)
    result["sub_goals"] = [_goal_to_dict(sg) for sg in sub_goals]
    result["gap_analysis"] = generate_gap_report(db, goal)
    return result


@router.get("/goals/{goal_id}/gap")
def get_goal_gap_analysis(
    goal_id: int,
    db: Session = Depends(get_db),
) -> dict:
    """Get the qualitative and quantitative gap analysis for a goal."""
    goal = db.scalar(select(InvestigationGoal).where(InvestigationGoal.id == goal_id))
    if goal is None:
        raise HTTPException(status_code=404, detail="Goal not found.")

    return generate_gap_report(db, goal)


@router.post("/goals/{goal_id}/pause")
def pause_goal(
    goal_id: int,
    db: Session = Depends(get_db),
) -> dict:
    """Manually pause an active goal."""
    goal = db.scalar(select(InvestigationGoal).where(InvestigationGoal.id == goal_id))
    if goal is None:
        raise HTTPException(status_code=404, detail="Goal not found.")
    if goal.status != "active":
        raise HTTPException(status_code=400, detail=f"Goal is '{goal.status}', not 'active'.")

    goal.status = "paused"
    db.commit()
    return _goal_to_dict(goal)


@router.post("/goals/{goal_id}/resume")
def resume_goal(
    goal_id: int,
    db: Session = Depends(get_db),
) -> dict:
    """Resume a paused goal."""
    goal = db.scalar(select(InvestigationGoal).where(InvestigationGoal.id == goal_id))
    if goal is None:
        raise HTTPException(status_code=404, detail="Goal not found.")
    if goal.status != "paused":
        raise HTTPException(status_code=400, detail=f"Goal is '{goal.status}', not 'paused'.")

    goal.status = "active"
    goal.stall_counter = 0
    db.commit()
    return _goal_to_dict(goal)


@router.post("/goals/{goal_id}/abandon")
def abandon_goal(
    goal_id: int,
    db: Session = Depends(get_db),
) -> dict:
    """Manually abandon a goal."""
    goal = db.scalar(select(InvestigationGoal).where(InvestigationGoal.id == goal_id))
    if goal is None:
        raise HTTPException(status_code=404, detail="Goal not found.")

    goal.status = "abandoned"
    db.commit()
    return _goal_to_dict(goal)
