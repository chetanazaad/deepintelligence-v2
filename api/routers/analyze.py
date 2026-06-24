"""Interactive Analysis Endpoint.

POST /analyze — User submits an article, the full deterministic pipeline runs
synchronously (~5s), and the LLM intelligence package is generated asynchronously
in the background.  The deterministic report is returned immediately so the UI
feels fast.  The frontend then polls GET /analyze/{id}/status to pick up the
LLM-enhanced intelligence when it is ready.

This is the ONLY endpoint an analyst needs.  Internal concepts (nodes, edges,
clusters, timelines, lead queues) are never exposed.
"""

import hashlib
import logging
import threading
import time
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from api.deps import get_db
from clustering.service import cluster_cleaned_news
from database.session import SessionLocal
from expansion.assessment import create_or_update_assessment
from expansion.goals import classify_goal_intent, extract_keywords
from expansion.service import expand_from_timeline
from impact.service import analyze_impact
from ingestion.service import insert_raw_news
from models.news_intelligence import (
    Edge,
    EventCluster,
    IntelligenceAssessment,
    InvestigationGoal,
    Node,
    RawNews,
    Signal,
)
from preprocessing.service import preprocess_and_store
from services.llm_service import generate_intelligence_package, LLM_SERVICE_MODE
from signal_detection.service import detect_and_store_signals
from timeline.service import build_timeline

logger = logging.getLogger(__name__)

router = APIRouter(tags=["analyze"])


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class AnalyzeRequest(BaseModel):
    title: str = Field(..., min_length=3, description="Article title / headline")
    content: str = Field(..., min_length=10, description="Full article text")
    source: str = Field(default="user", description="Source label")
    use_llm: bool = Field(default=True, description="Run LLM augmentation (async)")


# ---------------------------------------------------------------------------
# In-memory store for async LLM results
# ---------------------------------------------------------------------------

_analysis_store: dict[str, dict[str, Any]] = {}
_store_lock = threading.Lock()


def _generate_analysis_id(title: str) -> str:
    ts = datetime.now(timezone.utc).isoformat()
    return hashlib.sha256(f"{title}|{ts}".encode()).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Background LLM worker
# ---------------------------------------------------------------------------

def _run_llm_background(
    analysis_id: str,
    goal_question: str,
    assessment_text: str,
    evidence: dict | None,
    gaps: dict | None,
    scenarios: dict | None,
    alternatives: dict | None,
    confidence_score: float | None,
    confidence_level: str | None,
) -> None:
    """Run generate_intelligence_package() in a background thread."""
    try:
        with _store_lock:
            _analysis_store[analysis_id]["llm_status"] = "running"

        signals_list = []
        impacts_list = []

        # Extract evidence items for the prompt
        evidence_list = None
        if evidence and isinstance(evidence, dict):
            node_ids = evidence.get("related_nodes", [])
            evidence_list = [f"Node {nid}" for nid in node_ids]

        gaps_list = None
        if gaps and isinstance(gaps, dict):
            all_gaps = gaps.get("critical", []) + gaps.get("moderate", []) + gaps.get("minor", [])
            gaps_list = [
                g.get("reason", g.get("category", str(g))) if isinstance(g, dict) else str(g)
                for g in all_gaps
            ]

        result = generate_intelligence_package(
            goal_question=goal_question,
            deterministic_text=assessment_text,
            evidence=evidence_list,
            gaps=gaps_list,
            confidence_score=confidence_score,
            confidence_level=confidence_level,
            scenarios=scenarios,
            alternatives=alternatives,
        )

        with _store_lock:
            if result and result.get("success", False):
                _analysis_store[analysis_id]["llm_status"] = "completed"
                _analysis_store[analysis_id]["llm_result"] = result
                logger.info("LLM analysis completed successfully for %s", analysis_id)
            else:
                _analysis_store[analysis_id]["llm_status"] = "failed"
                _analysis_store[analysis_id]["llm_error"] = "LLM generation returned unsuccessful response (Ollama might be down or timed out)."
                logger.warning("LLM analysis failed for %s", analysis_id)

    except Exception as exc:
        logger.exception("LLM background analysis failed: %s", exc)
        with _store_lock:
            _analysis_store[analysis_id]["llm_status"] = "failed"
            _analysis_store[analysis_id]["llm_error"] = str(exc)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if isinstance(value, datetime) else None


def _safe_score(score: float | None) -> int:
    """Convert 0-1 float to 0-100 percentage."""
    if score is None:
        return 0
    return round(score * 100) if score <= 1 else round(score)


def _format_deterministic(ass: IntelligenceAssessment) -> dict:
    """Format deterministic assessment for the response."""
    exec_summary = ass.executive_summary or {}
    return {
        "confidence_score": _safe_score(ass.confidence_score),
        "confidence_level": ass.confidence_level or "LOW",
        "assessment_text": ass.assessment_text or "",
        "evidence_strength": _safe_score(
            ass.evidence_summary.get("evidence_strength")
            if isinstance(ass.evidence_summary, dict) else 0
        ),
        "knowledge_gaps": _format_gaps(ass.knowledge_gaps),
        "alternative_explanations": _format_alternatives(ass.alternative_explanations),
        "future_scenarios": _format_scenarios(ass.future_scenarios),
        "executive_summary": (
            exec_summary.get("key_findings", "")
            if isinstance(exec_summary, dict)
            else str(exec_summary)
        ),
        "risks": (
            exec_summary.get("risks", "")
            if isinstance(exec_summary, dict)
            else ""
        ),
        "opportunities": (
            exec_summary.get("opportunities", "")
            if isinstance(exec_summary, dict)
            else ""
        ),
        "unknowns": (
            exec_summary.get("unknowns", [])
            if isinstance(exec_summary, dict)
            else []
        ),
    }


def _format_gaps(gaps: dict | list | None) -> list[dict]:
    """Flatten knowledge gaps into a simple list."""
    if not gaps:
        return []
    if isinstance(gaps, list):
        return [{"category": str(g), "reason": "", "priority": "minor"} for g in gaps]
    result = []
    for priority in ["critical", "moderate", "minor"]:
        for gap in gaps.get(priority, []):
            if isinstance(gap, dict):
                result.append({
                    "category": gap.get("category", "Unknown"),
                    "reason": gap.get("reason", ""),
                    "priority": priority,
                })
            else:
                result.append({"category": str(gap), "reason": "", "priority": priority})
    return result


def _format_alternatives(alts: dict | list | None) -> list[dict]:
    """Format alternative explanations into a list."""
    if not alts:
        return []
    if isinstance(alts, list):
        return [{"hypothesis": str(a), "score": 50} for a in alts]

    result = []
    primary = alts.get("primary", "")
    if primary:
        result.append({"hypothesis": primary, "score": 80})
    for alt in alts.get("alternatives", []):
        if isinstance(alt, dict):
            result.append({
                "hypothesis": alt.get("explanation", str(alt)),
                "score": round(alt.get("score", 0.5) * 100) if alt.get("score", 0) <= 1 else alt.get("score", 50),
            })
        else:
            result.append({"hypothesis": str(alt), "score": 50})
    return result


def _format_scenarios(scenarios: dict | None) -> dict:
    """Ensure scenarios have likely/possible/unlikely as strings."""
    if not scenarios or not isinstance(scenarios, dict):
        return {"likely": "Insufficient data", "possible": "Insufficient data", "unlikely": "Insufficient data"}
    return {
        "likely": str(scenarios.get("likely", "Insufficient data")),
        "possible": str(scenarios.get("possible", "Insufficient data")),
        "unlikely": str(scenarios.get("unlikely", "Insufficient data")),
    }


_LLM_DEFAULT_SUMMARY = "insufficient evidence"
_LLM_DEFAULT_ASSESSMENT = "insufficient evidence"
_LLM_DEFAULT_CONFIDENCE = "unknown"


def _is_llm_default(intelligence_response: dict, field: str) -> bool:
    """Check if an LLM field contains a hardcoded placeholder default."""
    value = intelligence_response.get(field)
    if isinstance(value, str) and value in (
        _LLM_DEFAULT_SUMMARY,
        _LLM_DEFAULT_ASSESSMENT,
        _LLM_DEFAULT_CONFIDENCE,
    ):
        return True
    return False


def _build_final_assessment(deterministic: dict, llm: dict | None) -> dict:
    """Merge deterministic + LLM into a final assessment object."""
    if not llm or not llm.get("success", False):
        return {
            "executive_summary": deterministic["executive_summary"],
            "assessment": deterministic["assessment_text"],
            "confidence": f"{deterministic['confidence_score']}% {deterministic['confidence_level']}",
            "risks": [deterministic["risks"]] if deterministic["risks"] else [],
            "opportunities": [deterministic["opportunities"]] if deterministic["opportunities"] else [],
            "alternative_explanations": [a["hypothesis"] for a in deterministic["alternative_explanations"]],
            "future_scenarios": [
                deterministic["future_scenarios"]["likely"],
                deterministic["future_scenarios"]["possible"],
                deterministic["future_scenarios"]["unlikely"],
            ],
            "knowledge_gaps": [f"{g['category']}: {g['reason']}" for g in deterministic["knowledge_gaps"]],
            "key_entities": [],
            "recommendations": [],
            "source": "deterministic",
        }

    rj = llm.get("response_json", {})
    return {
        "executive_summary": (
            deterministic["executive_summary"]
            if _is_llm_default(rj, "executive_summary")
            else rj.get("executive_summary", deterministic["executive_summary"])
        ),
        "assessment": (
            deterministic["assessment_text"]
            if _is_llm_default(rj, "assessment")
            else rj.get("assessment", deterministic["assessment_text"])
        ),
        "confidence": (
            f"{deterministic['confidence_score']}% {deterministic['confidence_level']}"
            if _is_llm_default(rj, "confidence")
            else rj.get("confidence", f"{deterministic['confidence_score']}% {deterministic['confidence_level']}")
        ),
        "risks": rj.get("risks", [deterministic["risks"]]),
        "opportunities": rj.get("opportunities", [deterministic["opportunities"]]),
        "alternative_explanations": rj.get("alternative_explanations", []),
        "future_scenarios": rj.get("future_scenarios", []),
        "knowledge_gaps": rj.get("knowledge_gaps", []),
        "key_entities": rj.get("key_entities", []),
        "recommendations": rj.get("recommendations", []),
        "source": "llm",
    }


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

_PIPELINE_STEPS = [
    "ingestion",
    "preprocessing",
    "clustering",
    "timeline",
    "expansion",
    "impact",
    "signals",
    "goal",
    "assessment",
]


def _step_pipeline_error(pipeline: dict, step: str, error: str) -> dict:
    """Return a structured failure response for the frontend."""
    return {
        "status": "failed",
        "failed_step": step,
        "error": error,
        "pipeline": pipeline,
    }


@router.post("/analyze")
def analyze_article(
    body: AnalyzeRequest,
    db: Session = Depends(get_db),
) -> dict:
    """Submit an article for full intelligence analysis.

    Runs the complete deterministic pipeline synchronously, returns the
    assessment immediately, and optionally kicks off LLM augmentation
    in the background.

    The frontend polls GET /analyze/{analysis_id}/status for LLM results.
    """
    start_time = time.time()
    analysis_id = _generate_analysis_id(body.title)
    pipeline = {}

    # --- Step 1: Ingestion ---
    try:
        article_item = {
            "title": body.title,
            "content": body.content,
            "source": body.source,
            "url": None,
            "published_at": datetime.now(timezone.utc),
        }
        inserted, skipped = insert_raw_news(db, [article_item])
        pipeline["ingestion"] = {"status": "ok", "inserted": inserted, "skipped": skipped}
    except Exception as e:
        logger.exception("Ingestion failed")
        return _step_pipeline_error(pipeline, "ingestion", str(e))

    # --- Step 2: Preprocessing ---
    try:
        prep = preprocess_and_store(db=db)
        pipeline["preprocessing"] = {"status": "ok", **prep}
    except Exception as e:
        logger.exception("Preprocessing failed")
        return _step_pipeline_error(pipeline, "preprocessing", str(e))

    # --- Step 3: Clustering ---
    try:
        clust = cluster_cleaned_news(db=db)
        pipeline["clustering"] = {"status": "ok", **clust}
    except Exception as e:
        logger.exception("Clustering failed")
        return _step_pipeline_error(pipeline, "clustering", str(e))

    # --- Step 4: Timeline ---
    try:
        tl = build_timeline(db=db)
        pipeline["timeline"] = {"status": "ok", **tl}
    except Exception as e:
        logger.exception("Timeline failed")
        return _step_pipeline_error(pipeline, "timeline", str(e))

    # --- Step 5: Expansion ---
    nodes_before = db.scalar(select(func.count()).select_from(Node)) or 0
    edges_before = db.scalar(select(func.count()).select_from(Edge)) or 0
    try:
        exp = expand_from_timeline(db=db)
        pipeline["expansion"] = {"status": "ok", **exp}
    except Exception as e:
        logger.exception("Expansion failed")
        return _step_pipeline_error(pipeline, "expansion", str(e))
    nodes_after = db.scalar(select(func.count()).select_from(Node)) or 0
    edges_after = db.scalar(select(func.count()).select_from(Edge)) or 0

    # --- Step 6: Impact ---
    try:
        imp = analyze_impact(db=db)
        pipeline["impact"] = {"status": "ok", **imp}
    except Exception as e:
        logger.exception("Impact failed")
        return _step_pipeline_error(pipeline, "impact", str(e))

    # --- Step 7: Signals ---
    signals_before = db.scalar(select(func.count()).select_from(Signal)) or 0
    try:
        sig = detect_and_store_signals(db=db)
        pipeline["signals"] = {"status": "ok", **sig}
    except Exception as e:
        logger.exception("Signal detection failed")
        return _step_pipeline_error(pipeline, "signals", str(e))
    signals_after = db.scalar(select(func.count()).select_from(Signal)) or 0

    # --- Step 8: Auto-create Investigation Goal ---
    goal = None
    try:
        goal_type = classify_goal_intent(body.title)
        keywords = extract_keywords(body.title + " " + body.content[:200])

        goal = InvestigationGoal(
            origin_node_id=1,  # Default anchor
            goal_type=goal_type,
            goal_question=body.title,
            keywords=keywords,
            expansion_budget=10,
            priority=5,
        )

        # Try to find a relevant node for the origin
        search_term = f"%{keywords[0]}%" if keywords else f"%{body.title[:30]}%"
        relevant_node = db.scalar(
            select(Node).where(Node.entity.ilike(search_term)).limit(1)
        )
        if relevant_node:
            goal.origin_node_id = relevant_node.id

        db.add(goal)
        db.commit()
        pipeline["goal"] = {"status": "ok", "goal_id": goal.id, "goal_type": goal_type}
    except Exception as e:
        logger.exception("Goal creation failed")
        return _step_pipeline_error(pipeline, "goal", str(e))

    # --- Step 9: Deterministic Assessment ---
    assessment = None
    deterministic_result = None
    if goal:
        try:
            assessment = create_or_update_assessment(db, goal.id, status="draft")
            deterministic_result = _format_deterministic(assessment)
            pipeline["assessment"] = {"status": "ok"}
        except Exception as e:
            logger.exception("Assessment failed")
            return _step_pipeline_error(pipeline, "assessment", str(e))

    if not deterministic_result:
        deterministic_result = {
            "confidence_score": 0,
            "confidence_level": "LOW",
            "assessment_text": "Pipeline could not generate an assessment for this article.",
            "evidence_strength": 0,
            "knowledge_gaps": [],
            "alternative_explanations": [],
            "future_scenarios": {"likely": "N/A", "possible": "N/A", "unlikely": "N/A"},
            "executive_summary": "Analysis could not be completed.",
            "risks": "",
            "opportunities": "",
            "unknowns": [],
        }

    # --- Compute stats ---
    processing_time = round(time.time() - start_time, 2)

    stats = {
        "nodes_created": max(0, nodes_after - nodes_before),
        "nodes_existing": nodes_before,
        "edges_created": max(0, edges_after - edges_before),
        "signals_detected": max(0, signals_after - signals_before),
        "processing_time": processing_time,
        "confidence_score": deterministic_result["confidence_score"],
    }

    # --- Build initial final assessment (deterministic only) ---
    final = _build_final_assessment(deterministic_result, None)

    # --- Store analysis & start LLM background ---
    llm_effectively_disabled = not body.use_llm or LLM_SERVICE_MODE == "disabled"

    with _store_lock:
        _analysis_store[analysis_id] = {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "title": body.title,
            "llm_status": "disabled" if llm_effectively_disabled else "pending",
            "llm_result": None,
            "llm_error": None,
            "deterministic": deterministic_result,
            "final": final,
        }

    if body.use_llm:
        if LLM_SERVICE_MODE == "disabled":
            pipeline["llm"] = {"status": "disabled", "message": "LLM service is disabled in configuration"}
            logger.info("LLM requested but service mode is 'disabled' — skipping background thread")
        else:
            pipeline["llm"] = {"status": "started", "message": "Running in background"}
            thread = threading.Thread(
                target=_run_llm_background,
                args=(
                    analysis_id,
                    body.title,
                    assessment.assessment_text if assessment else body.title,
                    assessment.evidence_summary if assessment else None,
                    assessment.knowledge_gaps if assessment else None,
                    assessment.future_scenarios if assessment else None,
                    assessment.alternative_explanations if assessment else None,
                    assessment.confidence_score if assessment else None,
                    assessment.confidence_level if assessment else None,
                ),
                daemon=True,
            )
            thread.start()
    else:
        pipeline["llm"] = {"status": "disabled"}

    return {
        "status": "completed",
        "analysis_id": analysis_id,
        "pipeline": pipeline,
        "assessment": {
            "deterministic": deterministic_result,
            "llm": None,
            "final": final,
        },
        "stats": stats,
    }


@router.get("/analyze/{analysis_id}/status")
def get_analysis_status(analysis_id: str) -> dict:
    """Poll for LLM analysis completion.

    Returns the current status and, when ready, the full intelligence
    package and merged final assessment.
    """
    with _store_lock:
        entry = _analysis_store.get(analysis_id)

    if not entry:
        raise HTTPException(status_code=404, detail="Analysis not found.")

    llm_status = entry["llm_status"]
    llm_intelligence = None
    final = entry["final"]

    if llm_status == "completed" and entry["llm_result"]:
        llm_result = entry["llm_result"]
        llm_intelligence = llm_result.get("response_json", {})

        # Build merged final assessment
        final = _build_final_assessment(entry["deterministic"], llm_result)

        # Update stored final
        with _store_lock:
            _analysis_store[analysis_id]["final"] = final

    return {
        "analysis_id": analysis_id,
        "llm_status": llm_status,
        "llm_error": entry.get("llm_error"),
        "assessment": {
            "deterministic": entry["deterministic"],
            "llm": llm_intelligence,
            "final": final,
        },
    }
