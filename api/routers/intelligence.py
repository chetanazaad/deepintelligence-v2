import logging
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from api.auth import verify_api_key
from api.deps import get_db
from models.news_intelligence import (
    CleanedNews,
    ClusterNewsMap,
    Edge,
    EventCluster,
    Impact,
    Node,
    RawNews,
    Signal,
    TimelineEntry,
)
from pipeline.main_pipeline import run_full_pipeline
from pipeline.validation import run_validation
from utils.datetime_helpers import ensure_utc

logger = logging.getLogger(__name__)

router = APIRouter(tags=["intelligence"])

# ---------------------------------------------------------------------------
# In-memory pipeline status tracker
# ---------------------------------------------------------------------------
_pipeline_status: dict[str, object] = {
    "state": "idle",
    "last_run_time": None,
    "last_result": None,
    "error": None,
}


def _run_pipeline_background() -> None:
    """Execute the full pipeline in a background thread with error handling."""
    global _pipeline_status
    _pipeline_status = {
        "state": "running",
        "last_run_time": datetime.now(timezone.utc).isoformat(),
        "last_result": None,
        "error": None,
    }
    try:
        result = run_full_pipeline()
        _pipeline_status["state"] = "completed"
        _pipeline_status["last_result"] = result
        logger.info("Pipeline completed successfully.")
    except Exception as exc:  # noqa: BLE001
        _pipeline_status["state"] = "failed"
        _pipeline_status["error"] = str(exc)
        logger.exception("Pipeline execution failed: %s", exc)


# ---------------------------------------------------------------------------
# Text / formatting helpers
# ---------------------------------------------------------------------------

def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if isinstance(value, datetime) else None


def _clean_description(raw: str | None, max_len: int = 200) -> str:
    """Clean pipe-delimited titles into a readable sentence."""
    if not raw:
        return ""
    # Split pipe-delimited titles and take unique ones
    parts = [p.strip() for p in raw.split("|") if p.strip()]
    if not parts:
        return ""
    joined = "; ".join(parts)
    if len(joined) > max_len:
        joined = joined[:max_len].rsplit(" ", 1)[0] + "…"
    return joined


_EVENT_TYPE_LABELS = {
    "trigger": "Triggering Event",
    "causal": "Causal Event",
    "reaction": "Reaction / Response",
    "update": "Development / Update",
}

_IMPACT_TYPE_LABELS = {
    "supply": "Supply Disruption",
    "demand": "Demand Shift",
    "policy": "Policy / Regulatory Change",
    "financial": "Financial / Monetary Event",
    "geopolitical": "Geopolitical Event",
    "technology": "Technology Shift",
}


def _parse_impact_entries(entries: list[str] | None) -> dict[str, list[str]]:
    """Parse DIRECT:/INDIRECT:/SECTOR: prefixed entries into groups."""
    direct: list[str] = []
    indirect: list[str] = []
    sector: list[str] = []

    for entry in entries or []:
        if entry.startswith("DIRECT:"):
            direct.append(entry[len("DIRECT:"):].strip())
        elif entry.startswith("INDIRECT (secondary):"):
            indirect.append(entry[len("INDIRECT (secondary):"):].strip())
        elif entry.startswith("INDIRECT:"):
            indirect.append(entry[len("INDIRECT:"):].strip())
        elif entry.startswith("SECTOR"):
            sector.append(entry.strip())
        else:
            # Legacy data without prefix
            direct.append(entry.strip())

    return {"direct": direct, "indirect": indirect, "sector": sector}


def _parse_signal_phrase(raw_phrase: str) -> dict[str, str]:
    """Parse structured phrase like '[STRONG] crisis (occurrences×4, sources×3)'."""
    strength = "unknown"
    keyword = raw_phrase

    if raw_phrase.startswith("["):
        bracket_end = raw_phrase.find("]")
        if bracket_end > 0:
            strength = raw_phrase[1:bracket_end].strip()
            rest = raw_phrase[bracket_end + 1:].strip()
            # Extract keyword (before parentheses)
            paren_start = rest.find("(")
            keyword = rest[:paren_start].strip() if paren_start > 0 else rest
    return {"strength": strength, "keyword": keyword}


# ---------------------------------------------------------------------------
# Unified payload builders
# ---------------------------------------------------------------------------

def _build_event_payload(node: Node) -> dict[str, object]:
    """Build the 'event' section of the unified response."""
    return {
        "node_id": node.id,
        "entity": node.entity or "",
        "event_type": node.event_type or "update",
        "event_type_label": _EVENT_TYPE_LABELS.get(node.event_type or "", "Development / Update"),
        "impact_classification": _IMPACT_TYPE_LABELS.get(node.impact_type or "", node.impact_type or ""),
        "description": _clean_description(node.description),
        "timestamp": _iso(node.timestamp),
        "is_anchor": node.is_anchor,
        "confidence_score": node.confidence_score,
    }


def _build_timeline_payload(db: Session, node_id: int) -> dict[str, object]:
    """Build the 'timeline' section with causal connections."""
    group_id = db.scalar(
        select(TimelineEntry.timeline_group_id)
        .where(TimelineEntry.node_id == node_id)
        .limit(1)
    )
    if group_id is None:
        return {"timeline_group_id": None, "entries": [], "total_events": 0}

    rows = (
        db.execute(
            select(TimelineEntry, Node)
            .join(Node, Node.id == TimelineEntry.node_id)
            .where(TimelineEntry.timeline_group_id == group_id)
            .order_by(TimelineEntry.position_index.asc())
        )
        .all()
    )

    # Batch-load outgoing edges for all timeline nodes
    timeline_node_ids = [row[1].id for row in rows]
    edges_by_from: dict[int, list[Edge]] = {}
    if timeline_node_ids:
        all_edges = (
            db.execute(
                select(Edge)
                .where(Edge.from_node_id.in_(timeline_node_ids))
                .order_by(Edge.confidence_score.desc())
            )
            .scalars()
            .all()
        )
        for edge in all_edges:
            edges_by_from.setdefault(edge.from_node_id, []).append(edge)

    entries: list[dict[str, object]] = []
    for entry, node in rows:
        node_edges = edges_by_from.get(node.id, [])
        connections = [
            {
                "target_node_id": e.to_node_id,
                "relation": e.relation_type,
                "confidence": e.confidence_score,
            }
            for e in node_edges[:5]  # top 5 by confidence
        ]

        entries.append({
            "position": entry.position_index,
            "node_id": node.id,
            "entity": node.entity or "",
            "event_type": node.event_type or "update",
            "event_label": _EVENT_TYPE_LABELS.get(node.event_type or "", "Update"),
            "description": _clean_description(node.description),
            "timestamp": _iso(node.timestamp),
            "is_anchor": node.is_anchor,
            "causal_connections": connections,
        })

    return {
        "timeline_group_id": group_id,
        "entries": entries,
        "total_events": len(entries),
    }


def _build_impact_payload(db: Session, node_id: int) -> dict[str, object]:
    """Build the 'impact' section with direct/indirect/sector separation."""
    impact = db.scalar(select(Impact).where(Impact.node_id == node_id))
    if impact is None:
        return {"available": False}

    st_winners = _parse_impact_entries(impact.short_term_winners)
    st_losers = _parse_impact_entries(impact.short_term_losers)
    lt_winners = _parse_impact_entries(impact.long_term_winners)
    lt_losers = _parse_impact_entries(impact.long_term_losers)

    # Collect all sector entries
    all_sectors = (
        st_winners["sector"] + st_losers["sector"]
        + lt_winners["sector"] + lt_losers["sector"]
    )

    return {
        "available": True,
        "confidence_score": impact.confidence_score,
        "short_term": {
            "direct_winners": st_winners["direct"],
            "indirect_winners": st_winners["indirect"],
            "direct_losers": st_losers["direct"],
            "indirect_losers": st_losers["indirect"],
        },
        "long_term": {
            "direct_winners": lt_winners["direct"],
            "indirect_winners": lt_winners["indirect"],
            "direct_losers": lt_losers["direct"],
            "indirect_losers": lt_losers["indirect"],
        },
        "sector_impacts": sorted(set(all_sectors)),
    }


def _build_signals_payload(db: Session, node_id: int) -> dict[str, object]:
    """Build the 'signals' section with parsed strength and clean output."""
    rows = (
        db.execute(
            select(Signal)
            .where(Signal.node_id == node_id)
            .order_by(Signal.confidence_score.desc(), Signal.created_at.asc())
        )
        .scalars()
        .all()
    )

    items: list[dict[str, object]] = []
    for signal in rows:
        parsed = _parse_signal_phrase(signal.phrase or "")
        items.append({
            "signal_type": signal.signal_type,
            "strength": parsed["strength"],
            "keyword": parsed["keyword"],
            "entity": signal.entity or "",
            "source_count": signal.source_count,
            "time_span": signal.time_span,
            "confidence_score": signal.confidence_score,
        })

    return {"count": len(items), "items": items}


def _build_metadata(
    db: Session,
    node: Node,
    impact: dict[str, object],
    signals: dict[str, object],
) -> dict[str, object]:
    """Build the 'metadata' section with confidence summary and source info."""
    # Collect all confidence scores
    scores: list[float] = []
    if node.confidence_score is not None:
        scores.append(node.confidence_score)
    if impact.get("available") and impact.get("confidence_score") is not None:
        scores.append(float(impact["confidence_score"]))
    for sig in signals.get("items", []):
        if sig.get("confidence_score") is not None:
            scores.append(float(sig["confidence_score"]))

    conf_summary = {}
    if scores:
        conf_summary = {
            "min": round(min(scores), 3),
            "max": round(max(scores), 3),
            "avg": round(sum(scores) / len(scores), 3),
            "data_points": len(scores),
        }

    # Source count for this node's cluster
    source_count = db.scalar(
        select(func.count(func.distinct(RawNews.source)))
        .join(CleanedNews, CleanedNews.raw_news_id == RawNews.id)
        .join(ClusterNewsMap, ClusterNewsMap.cleaned_news_id == CleanedNews.id)
        .where(ClusterNewsMap.cluster_id == node.cluster_id)
    ) or 0

    return {
        "confidence_summary": conf_summary,
        "data_sources": source_count,
        "last_updated": _iso(node.created_at) if hasattr(node, "created_at") else None,
    }


def _build_unified_response(db: Session, node: Node) -> dict[str, object]:
    """Build the complete unified response envelope for a node."""
    event = _build_event_payload(node)
    timeline = _build_timeline_payload(db, node.id)
    impact = _build_impact_payload(db, node.id)
    signals = _build_signals_payload(db, node.id)
    metadata = _build_metadata(db, node, impact, signals)

    return {
        "event": event,
        "timeline": timeline,
        "impact": impact,
        "signals": signals,
        "metadata": metadata,
    }


# ---------------------------------------------------------------------------
# Read endpoints — unified structured responses
# ---------------------------------------------------------------------------

@router.get("/event")
def get_event(
    query: str = Query(..., min_length=2, description="Search term for entity, event, or topic"),
    limit: int = Query(10, ge=1, le=50, description="Maximum results to return"),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    """Search events with improved relevance ranking.

    Searches across: entity, event_type, description, AND cluster main_topic.
    Results ranked by: exact entity match > keyword match > recency.
    """
    search_term = query.strip().lower()
    pattern = f"%{search_term}%"

    # Broader search: join through cluster to catch topic matches
    nodes = (
        db.execute(
            select(Node)
            .outerjoin(EventCluster, EventCluster.id == Node.cluster_id)
            .where(
                or_(
                    Node.entity.ilike(pattern),
                    Node.event_type.ilike(pattern),
                    Node.description.ilike(pattern),
                    EventCluster.main_topic.ilike(pattern),
                )
            )
            .order_by(Node.timestamp.desc(), Node.id.desc())
            .limit(limit * 2)  # fetch extra for re-ranking
        )
        .scalars()
        .all()
    )

    # Relevance ranking
    scored: list[tuple[float, Node]] = []
    for node in nodes:
        score = 0.0
        entity_lower = (node.entity or "").lower()
        desc_lower = (node.description or "").lower()

        # Exact entity match is strongest signal
        if entity_lower == search_term:
            score += 10.0
        elif search_term in entity_lower:
            score += 5.0

        # Description match
        if search_term in desc_lower:
            score += 2.0

        # Recency bonus
        if node.timestamp:
            age_days = (datetime.now(timezone.utc) - ensure_utc(node.timestamp)).total_seconds() / 86400.0
            score += max(0.0, 3.0 - (age_days / 10.0))

        # Anchor bonus
        if node.is_anchor:
            score += 1.0

        scored.append((score, node))

    scored.sort(key=lambda x: x[0], reverse=True)
    top_nodes = [node for _, node in scored[:limit]]

    results = [_build_unified_response(db, node) for node in top_nodes]

    return {
        "query": query,
        "count": len(results),
        "results": results,
    }


@router.get("/timeline/{id}")
def get_timeline(id: int, db: Session = Depends(get_db)) -> dict[str, object]:
    """Get timeline for a specific node with causal connections."""
    node = db.scalar(select(Node).where(Node.id == id))
    if node is None:
        raise HTTPException(status_code=404, detail="Node not found.")

    event = _build_event_payload(node)
    timeline = _build_timeline_payload(db, id)

    # Full edge details for this specific node
    outgoing = (
        db.execute(
            select(Edge, Node)
            .join(Node, Node.id == Edge.to_node_id)
            .where(Edge.from_node_id == id)
            .order_by(Edge.confidence_score.desc())
        )
        .all()
    )
    incoming = (
        db.execute(
            select(Edge, Node)
            .join(Node, Node.id == Edge.from_node_id)
            .where(Edge.to_node_id == id)
            .order_by(Edge.confidence_score.desc())
        )
        .all()
    )

    connections = {
        "causes": [
            {
                "node_id": n.id,
                "entity": n.entity or "",
                "event_type": n.event_type or "",
                "description": _clean_description(n.description, 100),
                "relation": e.relation_type,
                "confidence": e.confidence_score,
            }
            for e, n in outgoing
        ],
        "caused_by": [
            {
                "node_id": n.id,
                "entity": n.entity or "",
                "event_type": n.event_type or "",
                "description": _clean_description(n.description, 100),
                "relation": e.relation_type,
                "confidence": e.confidence_score,
            }
            for e, n in incoming
        ],
    }

    return {
        "event": event,
        "timeline": timeline,
        "connections": connections,
    }


@router.get("/impact/{id}")
def get_impact(id: int, db: Session = Depends(get_db)) -> dict[str, object]:
    """Get structured impact analysis for a specific node."""
    node = db.scalar(select(Node).where(Node.id == id))
    if node is None:
        raise HTTPException(status_code=404, detail="Node not found.")

    return {
        "event": _build_event_payload(node),
        "impact": _build_impact_payload(db, id),
    }


@router.get("/signals/{id}")
def get_signals(id: int, db: Session = Depends(get_db)) -> dict[str, object]:
    """Get early-warning signals for a specific node."""
    node = db.scalar(select(Node).where(Node.id == id))
    if node is None:
        raise HTTPException(status_code=404, detail="Node not found.")

    return {
        "event": _build_event_payload(node),
        "signals": _build_signals_payload(db, id),
    }


# ---------------------------------------------------------------------------
# Pipeline endpoints (protected + async)
# ---------------------------------------------------------------------------

@router.post("/pipeline/run", dependencies=[Depends(verify_api_key)])
def trigger_pipeline(background_tasks: BackgroundTasks) -> dict[str, object]:
    """
    Trigger full deterministic pipeline in the background.

    Protected by API key (X-API-Key header).
    Returns immediately; poll GET /pipeline/status for progress.
    """
    if _pipeline_status["state"] == "running":
        return {
            "message": "Pipeline is already running. Please wait for it to finish.",
            "status": dict(_pipeline_status),
        }

    background_tasks.add_task(_run_pipeline_background)
    return {
        "message": "Pipeline started in background.",
        "explanation": "Poll GET /pipeline/status to monitor progress.",
    }


@router.get("/pipeline/status")
def get_pipeline_status() -> dict[str, object]:
    """Return the current pipeline execution status."""
    return {"status": dict(_pipeline_status)}


@router.get("/pipeline/validate")
def validate_pipeline(db: Session = Depends(get_db)) -> dict[str, object]:
    """Run all validation checks on the current pipeline data.

    Returns a structured report with:
    - health: 'healthy' | 'warnings' | 'errors'
    - stats: row counts for all tables
    - issues: detailed list of every issue found
    """
    report = run_validation(db=db)
    return {"validation": report}

