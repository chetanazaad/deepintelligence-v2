from datetime import datetime
from re import findall

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from models.news_intelligence import CleanedNews, ClusterNewsMap, RawNews, Signal, Node

_DETECTION_PHRASES = ["may", "could", "expected", "concerns", "pressure"]
_RISK_CUES = {"concerns", "pressure", "decline", "drop", "risk", "weakness"}
_OPPORTUNITY_CUES = {"expected", "could", "growth", "improve", "upside", "benefit"}


def _normalize_text(text: str) -> str:
    terms = findall(r"[a-zA-Z0-9']+", text or "")
    return " ".join(terms).lower().strip()


def detect_phrases(text: str) -> list[str]:
    normalized = _normalize_text(text)
    matched = [phrase for phrase in _DETECTION_PHRASES if phrase in normalized]
    return sorted(set(matched))


def _signal_type(text: str, phrase: str) -> str:
    terms = set(_normalize_text(text).split())
    if phrase in {"concerns", "pressure"} or terms.intersection(_RISK_CUES):
        return "risk"
    if terms.intersection(_OPPORTUNITY_CUES):
        return "opportunity"
    # Signals are weak indications, not facts.
    return "risk" if phrase in {"may", "could"} else "opportunity"


def _confidence_score(source_count: int, phrase_hits: int) -> float:
    # Keep confidence moderate since signals are uncertain by nature.
    return min(0.35 + (0.08 * min(source_count, 5)) + (0.05 * min(phrase_hits, 3)), 0.75)


def _time_span_label(start_ts: datetime | None, end_ts: datetime | None) -> str:
    if start_ts is None or end_ts is None:
        return "unknown"
    return f"{start_ts.date().isoformat()}->{end_ts.date().isoformat()}"


def _cluster_source_time_stats(db: Session, cluster_id: int) -> tuple[int, datetime | None, datetime | None]:
    row = db.execute(
        select(
            func.count(func.distinct(RawNews.source)).label("source_count"),
            func.min(func.coalesce(RawNews.published_at, RawNews.created_at)).label("start_ts"),
            func.max(func.coalesce(RawNews.published_at, RawNews.created_at)).label("end_ts"),
        )
        .join(CleanedNews, CleanedNews.raw_news_id == RawNews.id)
        .join(ClusterNewsMap, ClusterNewsMap.cleaned_news_id == CleanedNews.id)
        .where(ClusterNewsMap.cluster_id == cluster_id)
    ).one()

    source_count = int(row.source_count or 0)
    start_ts = row.start_ts if isinstance(row.start_ts, datetime) else None
    end_ts = row.end_ts if isinstance(row.end_ts, datetime) else None
    return source_count, start_ts, end_ts


def detect_and_store_signals(db: Session, limit: int = 500) -> dict[str, int]:
    """
    Deterministic signal detection.
    Signals represent uncertain cues (not facts) such as: may/could/expected/concerns/pressure.
    """
    nodes = (
        db.execute(select(Node).order_by(Node.created_at.asc(), Node.id.asc()).limit(limit))
        .scalars()
        .all()
    )
    if not nodes:
        return {"processed_nodes": 0, "signals_written": 0}

    signals_written = 0

    for node in nodes:
        text = f"{node.entity or ''} {node.event_type or ''} {node.description or ''}"
        matched = detect_phrases(text)
        if not matched:
            continue

        source_count, start_ts, end_ts = _cluster_source_time_stats(db=db, cluster_id=node.cluster_id)
        time_span = _time_span_label(start_ts, end_ts)

        for phrase in matched:
            signal_type = _signal_type(text, phrase)
            confidence = _confidence_score(source_count=source_count, phrase_hits=len(matched))

            existing = db.scalar(
                select(Signal).where(
                    Signal.node_id == node.id,
                    Signal.phrase == phrase,
                    Signal.signal_type == signal_type,
                )
            )

            if existing is None:
                db.add(
                    Signal(
                        node_id=node.id,
                        signal_type=signal_type,
                        phrase=phrase,
                        entity=node.entity,
                        source_count=source_count,
                        time_span=time_span,
                        confidence_score=confidence,
                    )
                )
            else:
                existing.entity = node.entity
                existing.source_count = source_count
                existing.time_span = time_span
                existing.confidence_score = confidence

            signals_written += 1

    db.commit()
    return {"processed_nodes": len(nodes), "signals_written": signals_written}

