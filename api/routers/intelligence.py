from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from api.deps import get_db
from models.news_intelligence import Edge, Impact, Node, Signal, TimelineEntry
from pipeline.main_pipeline import run_full_pipeline

router = APIRouter(tags=["intelligence"])


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if isinstance(value, datetime) else None


def _timeline_payload(db: Session, node_id: int) -> dict[str, object]:
    group_id = db.scalar(select(TimelineEntry.timeline_group_id).where(TimelineEntry.node_id == node_id).limit(1))
    if group_id is None:
        return {
            "timeline_group_id": None,
            "items": [],
            "explanation": "No timeline group found for this node.",
        }

    rows = (
        db.execute(
            select(TimelineEntry, Node)
            .join(Node, Node.id == TimelineEntry.node_id)
            .where(TimelineEntry.timeline_group_id == group_id)
            .order_by(TimelineEntry.position_index.asc())
        )
        .all()
    )

    items: list[dict[str, object]] = []
    for entry, node in rows:
        items.append(
            {
                "position_index": entry.position_index,
                "node_id": node.id,
                "entity": node.entity,
                "event_type": node.event_type,
                "description": node.description,
                "timestamp": _iso(node.timestamp),
                "is_anchor": node.is_anchor,
            }
        )

    return {
        "timeline_group_id": group_id,
        "items": items,
        "explanation": "Ordered chronologically using stored timeline positions.",
    }


def _impact_payload(db: Session, node_id: int) -> dict[str, object]:
    impact = db.scalar(select(Impact).where(Impact.node_id == node_id))
    if impact is None:
        return {
            "node_id": node_id,
            "available": False,
            "explanation": "No impact analysis exists for this node.",
        }

    return {
        "node_id": node_id,
        "available": True,
        "short_term_winners": impact.short_term_winners or [],
        "short_term_losers": impact.short_term_losers or [],
        "long_term_winners": impact.long_term_winners or [],
        "long_term_losers": impact.long_term_losers or [],
        "confidence_score": impact.confidence_score,
        "explanation": "Rule-based impact buckets derived from node context.",
    }


def _signals_payload(db: Session, node_id: int) -> dict[str, object]:
    rows = db.execute(select(Signal).where(Signal.node_id == node_id).order_by(Signal.created_at.asc())).scalars().all()
    items = [
        {
            "id": signal.id,
            "type": signal.signal_type,
            "phrase": signal.phrase,
            "entity": signal.entity,
            "source_count": signal.source_count,
            "time_span": signal.time_span,
            "confidence_score": signal.confidence_score,
            "note": "Signal indicates uncertainty and is not a confirmed fact.",
        }
        for signal in rows
    ]

    return {
        "node_id": node_id,
        "count": len(items),
        "items": items,
        "explanation": "Detected from uncertainty phrases and cross-source frequency.",
    }


@router.get("/event")
def get_event(
    query: str = Query(..., min_length=2, description="Search term for entity, event type, or description"),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    pattern = f"%{query.strip()}%"
    nodes = (
        db.execute(
            select(Node)
            .where(
                or_(
                    Node.entity.ilike(pattern),
                    Node.event_type.ilike(pattern),
                    Node.description.ilike(pattern),
                )
            )
            .order_by(Node.timestamp.desc(), Node.id.desc())
            .limit(20)
        )
        .scalars()
        .all()
    )

    results: list[dict[str, object]] = []
    for node in nodes:
        results.append(
            {
                "node_id": node.id,
                "entity": node.entity,
                "event_type": node.event_type,
                "description": node.description,
                "timestamp": _iso(node.timestamp),
                "timeline": _timeline_payload(db, node.id),
                "impact": _impact_payload(db, node.id),
                "signals": _signals_payload(db, node.id),
                "explanation": "Matched query against entity, event_type, or description fields.",
            }
        )

    return {
        "query": query,
        "count": len(results),
        "results": results,
    }


@router.get("/timeline/{id}")
def get_timeline(id: int, db: Session = Depends(get_db)) -> dict[str, object]:
    node = db.scalar(select(Node).where(Node.id == id))
    if node is None:
        raise HTTPException(status_code=404, detail="Node not found.")

    outgoing = (
        db.execute(select(Edge).where(Edge.from_node_id == id).order_by(Edge.created_at.asc()))
        .scalars()
        .all()
    )
    incoming = (
        db.execute(select(Edge).where(Edge.to_node_id == id).order_by(Edge.created_at.asc()))
        .scalars()
        .all()
    )

    return {
        "node_id": id,
        "entity": node.entity,
        "timeline": _timeline_payload(db, id),
        "connections": {
            "outgoing": [
                {"to_node_id": edge.to_node_id, "relation_type": edge.relation_type, "confidence_score": edge.confidence_score}
                for edge in outgoing
            ],
            "incoming": [
                {"from_node_id": edge.from_node_id, "relation_type": edge.relation_type, "confidence_score": edge.confidence_score}
                for edge in incoming
            ],
        },
        "explanation": "Timeline order is deterministic and based on stored position_index and edge relations.",
    }


@router.get("/impact/{id}")
def get_impact(id: int, db: Session = Depends(get_db)) -> dict[str, object]:
    node = db.scalar(select(Node).where(Node.id == id))
    if node is None:
        raise HTTPException(status_code=404, detail="Node not found.")
    return {"node_id": id, "impact": _impact_payload(db, id)}


@router.get("/signals/{id}")
def get_signals(id: int, db: Session = Depends(get_db)) -> dict[str, object]:
    node = db.scalar(select(Node).where(Node.id == id))
    if node is None:
        raise HTTPException(status_code=404, detail="Node not found.")
    return {"node_id": id, "signals": _signals_payload(db, id)}


@router.post("/pipeline/run")
def run_pipeline() -> dict[str, object]:
    """
    Trigger full deterministic pipeline execution and return step-by-step status.
    """
    result = run_full_pipeline()
    return {
        "message": "Pipeline execution finished.",
        "result": result,
        "explanation": "Runs ingestion -> preprocessing -> clustering -> timeline -> expansion -> impact -> signals.",
    }
