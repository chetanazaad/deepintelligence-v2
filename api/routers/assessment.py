"""API endpoints for Intelligence Assessments.

Provides endpoints to trigger, view, list, and publish intelligence assessments.
"""

import logging
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, desc
from sqlalchemy.orm import Session

from api.deps import get_db
from expansion.assessment import create_or_update_assessment
from models.news_intelligence import IntelligenceAssessment, InvestigationGoal, LLMAssessment
from services.llm_service import generate_assessment as llm_generate_assessment

logger = logging.getLogger(__name__)

router = APIRouter(tags=["assessments"])



# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if isinstance(value, datetime) else None


def _assessment_to_dict(ass: IntelligenceAssessment) -> dict:
    return {
        "id": ass.id,
        "goal_id": ass.goal_id,
        "assessment_type": ass.assessment_type,
        "confidence_score": ass.confidence_score,
        "confidence_level": ass.confidence_level,
        "assessment_text": ass.assessment_text,
        "evidence_summary": ass.evidence_summary,
        "knowledge_gaps": ass.knowledge_gaps,
        "alternative_explanations": ass.alternative_explanations,
        "future_scenarios": ass.future_scenarios,
        "executive_summary": ass.executive_summary,
        "generated_at": _iso(ass.generated_at),
        "version": ass.version,
        "status": ass.status,
    }


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/goals/{goal_id}/assessments")
def generate_assessment(
    goal_id: int,
    db: Session = Depends(get_db),
) -> dict:
    """Generate or update an intelligence assessment draft for a goal."""
    goal = db.scalar(select(InvestigationGoal).where(InvestigationGoal.id == goal_id))
    if not goal:
        raise HTTPException(status_code=404, detail=f"Goal {goal_id} not found.")

    try:
        ass = create_or_update_assessment(db, goal_id, status="draft")
        return _assessment_to_dict(ass)
    except Exception as e:
        logger.exception("Error generating assessment for goal %d", goal_id)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/goals/{goal_id}/assessments")
def list_assessments(
    goal_id: int,
    db: Session = Depends(get_db),
) -> dict:
    """List all historical assessment versions for a goal."""
    goal = db.scalar(select(InvestigationGoal).where(InvestigationGoal.id == goal_id))
    if not goal:
        raise HTTPException(status_code=404, detail=f"Goal {goal_id} not found.")

    assessments = db.execute(
        select(IntelligenceAssessment)
        .where(IntelligenceAssessment.goal_id == goal_id)
        .order_by(desc(IntelligenceAssessment.version))
    ).scalars().all()

    return {
        "goal_id": goal_id,
        "count": len(assessments),
        "assessments": [_assessment_to_dict(a) for a in assessments]
    }


@router.get("/goals/{goal_id}/assessments/latest")
def get_latest_assessment(
    goal_id: int,
    db: Session = Depends(get_db),
) -> dict:
    """Get the latest active assessment version for a goal."""
    goal = db.scalar(select(InvestigationGoal).where(InvestigationGoal.id == goal_id))
    if not goal:
        raise HTTPException(status_code=404, detail=f"Goal {goal_id} not found.")

    ass = db.scalar(
        select(IntelligenceAssessment)
        .where(IntelligenceAssessment.goal_id == goal_id)
        .order_by(desc(IntelligenceAssessment.version))
        .limit(1)
    )
    if not ass:
        raise HTTPException(status_code=404, detail=f"No assessments found for goal {goal_id}.")

    return _assessment_to_dict(ass)


@router.get("/assessments/{assessment_id}")
def get_assessment(
    assessment_id: int,
    db: Session = Depends(get_db),
) -> dict:
    """Get a specific intelligence assessment by ID."""
    ass = db.scalar(select(IntelligenceAssessment).where(IntelligenceAssessment.id == assessment_id))
    if not ass:
        raise HTTPException(status_code=404, detail=f"Assessment {assessment_id} not found.")
    return _assessment_to_dict(ass)


@router.post("/assessments/{assessment_id}/publish")
def publish_assessment(
    assessment_id: int,
    db: Session = Depends(get_db),
) -> dict:
    """Transition assessment status from 'draft' to 'final'."""
    ass = db.scalar(select(IntelligenceAssessment).where(IntelligenceAssessment.id == assessment_id))
    if not ass:
        raise HTTPException(status_code=404, detail=f"Assessment {assessment_id} not found.")

    if ass.status != "draft":
        raise HTTPException(status_code=400, detail=f"Assessment is in status '{ass.status}', cannot publish.")

    ass.status = "final"
    db.commit()
    return _assessment_to_dict(ass)


@router.get("/goals/{goal_id}/assessments/llm")
def get_llm_assessment(
    goal_id: int,
    db: Session = Depends(get_db),
) -> dict:
    """Fetch or generate LLM augmented assessment for a given goal."""
    goal = db.scalar(select(InvestigationGoal).where(InvestigationGoal.id == goal_id))
    if not goal:
        raise HTTPException(status_code=404, detail=f"Goal {goal_id} not found.")

    ass = db.scalar(
        select(IntelligenceAssessment)
        .where(IntelligenceAssessment.goal_id == goal_id)
        .order_by(desc(IntelligenceAssessment.version))
        .limit(1)
    )
    if not ass:
        raise HTTPException(status_code=404, detail=f"No deterministic assessment found for goal {goal_id}.")

    # Check if we already have an LLM assessment stored for this version
    llm_ass = db.scalar(
        select(LLMAssessment).where(LLMAssessment.assessment_id == ass.id)
    )
    
    if llm_ass:
        return {
            "id": llm_ass.id,
            "assessment_id": llm_ass.assessment_id,
            "prompt": llm_ass.prompt,
            "response": llm_ass.response,
            "model": llm_ass.model,
            "latency": llm_ass.latency,
            "input_tokens": llm_ass.input_tokens,
            "output_tokens": llm_ass.output_tokens,
            "evaluation_score": llm_ass.evaluation_score,
            "created_at": _iso(llm_ass.created_at)
        }

    # Generate new LLM assessment
    prompt = f"Goal Question: {goal.goal_question}\nDeterministic Findings: {ass.assessment_text}"
    res = llm_generate_assessment(goal.goal_question, ass.assessment_text, ass.evidence_summary or {}, ass.knowledge_gaps or {})

    # Save to database
    llm_ass = LLMAssessment(
        assessment_id=ass.id,
        prompt=prompt,
        response=res["text"],
        model=res["model"],
        latency=res["latency"],
        input_tokens=res["input_tokens"],
        output_tokens=res["output_tokens"],
        evaluation_score=0.85, # Default evaluation
        created_at=datetime.utcnow()
    )
    db.add(llm_ass)
    db.commit()

    return {
        "id": llm_ass.id,
        "assessment_id": llm_ass.assessment_id,
        "prompt": llm_ass.prompt,
        "response": llm_ass.response,
        "model": llm_ass.model,
        "latency": llm_ass.latency,
        "input_tokens": llm_ass.input_tokens,
        "output_tokens": llm_ass.output_tokens,
        "evaluation_score": llm_ass.evaluation_score,
        "created_at": _iso(llm_ass.created_at)
    }

