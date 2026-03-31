from collections import defaultdict
from datetime import datetime, timezone
from re import findall

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from models.news_intelligence import CleanedNews, ClusterNewsMap, Node, RawNews, Signal


# ---------------------------------------------------------------------------
# Detection vocabulary — 3 categories with base strength weights
# ---------------------------------------------------------------------------

_RISK_PHRASES: dict[str, float] = {
    # Strong risk indicators
    "concerns": 0.80, "pressure": 0.75, "decline": 0.80, "drop": 0.75,
    "risk": 0.85, "weakness": 0.70, "vulnerable": 0.80, "downturn": 0.85,
    "default": 0.90, "bankruptcy": 0.95, "fraud": 0.90, "threat": 0.80,
    "crisis": 0.90, "warning": 0.75, "collapse": 0.90, "instability": 0.80,
    # Moderate risk indicators
    "uncertain": 0.55, "volatile": 0.60, "slowing": 0.55, "erosion": 0.60,
}

_OPPORTUNITY_PHRASES: dict[str, float] = {
    # Strong opportunity indicators
    "expected": 0.60, "growth": 0.70, "improve": 0.65, "upside": 0.75,
    "benefit": 0.65, "breakthrough": 0.80, "outperform": 0.75,
    "expansion": 0.70, "innovation": 0.70, "upgrade": 0.65,
    # Moderate opportunity indicators
    "could": 0.45, "may": 0.40, "potential": 0.50, "promising": 0.55,
    "momentum": 0.60, "emerging": 0.55, "recovery": 0.65, "bullish": 0.60,
}

_TRANSITION_PHRASES: dict[str, float] = {
    # Structural change indicators
    "restructuring": 0.75, "transformation": 0.70, "pivot": 0.65,
    "transition": 0.65, "merger": 0.80, "acquisition": 0.80,
    "spin-off": 0.70, "demerger": 0.70, "consolidation": 0.75,
    "disruption": 0.70, "regulation": 0.60, "reform": 0.65,
}

# Unified lookup: phrase → (signal_type, base_weight)
_ALL_PHRASES: dict[str, tuple[str, float]] = {
    **{k: ("risk", v) for k, v in _RISK_PHRASES.items()},
    **{k: ("opportunity", v) for k, v in _OPPORTUNITY_PHRASES.items()},
    **{k: ("transition", v) for k, v in _TRANSITION_PHRASES.items()},
}

# Minimum confidence to persist a signal (filters single-occurrence noise)
_MIN_CONFIDENCE = 0.25


# ---------------------------------------------------------------------------
# Text helpers
# ---------------------------------------------------------------------------

def _normalize_text(text: str) -> str:
    terms = findall(r"[a-zA-Z0-9']+", text or "")
    return " ".join(terms).lower().strip()


def detect_phrases(text: str) -> list[tuple[str, str, float]]:
    """Detect all matching phrases and return (phrase, signal_type, weight)."""
    normalized = _normalize_text(text)
    terms = set(normalized.split())
    results: list[tuple[str, str, float]] = []

    for phrase, (signal_type, weight) in _ALL_PHRASES.items():
        if phrase in terms:
            results.append((phrase, signal_type, weight))

    results.sort(key=lambda x: x[2], reverse=True)
    return results


# ---------------------------------------------------------------------------
# Strength scoring
# ---------------------------------------------------------------------------

def _compute_strength_score(
    frequency: int,
    source_count: int,
    time_persistence: float,
    phrase_weight: float,
) -> float:
    """Multi-signal strength score.

    Weights:
    - Frequency/repetition  (0.30): how often this signal appears
    - Source diversity       (0.25): how many independent sources
    - Time persistence      (0.25): how long the signal has been active
    - Phrase weight          (0.20): inherent strength of the cue word

    Returns a score in [0.0, 1.0].
    """
    freq_signal = min(frequency / 5.0, 1.0)
    source_signal = min(source_count / 4.0, 1.0)
    weight_signal = phrase_weight

    raw = (
        0.30 * freq_signal
        + 0.25 * source_signal
        + 0.25 * time_persistence
        + 0.20 * weight_signal
    )
    return round(min(max(raw, 0.0), 1.0), 3)


def _strength_label(score: float) -> str:
    """Bucket strength score into human-readable label."""
    if score >= 0.60:
        return "STRONG"
    if score >= 0.35:
        return "MEDIUM"
    return "WEAK"


def _time_persistence_score(
    first_seen: datetime | None,
    last_seen: datetime | None,
) -> float:
    """Score based on how long a signal has been active.

    Full weight at 7+ days, linear ramp-up from 0.
    Signals older than 30 days from now get a decay penalty.
    """
    if first_seen is None or last_seen is None:
        return 0.15

    span_days = max((last_seen - first_seen).total_seconds() / 86400.0, 0.0)
    persistence = min(span_days / 7.0, 1.0)

    # Decay for stale signals
    now = datetime.now(timezone.utc)
    age_days = max((now - last_seen).total_seconds() / 86400.0, 0.0)
    decay = max(0.0, 1.0 - (age_days / 30.0))

    return round(persistence * decay, 3)


def _time_span_label(start_ts: datetime | None, end_ts: datetime | None) -> str:
    if start_ts is None or end_ts is None:
        return "unknown"
    return f"{start_ts.date().isoformat()}->{end_ts.date().isoformat()}"


# ---------------------------------------------------------------------------
# Batch cluster stats (eliminates N+1 queries)
# ---------------------------------------------------------------------------

def _batch_cluster_stats(
    db: Session,
    cluster_ids: list[int],
) -> dict[int, tuple[int, datetime | None, datetime | None]]:
    """Load source count + time range for ALL clusters in one query.

    Returns: {cluster_id: (source_count, first_ts, last_ts)}
    """
    if not cluster_ids:
        return {}

    rows = db.execute(
        select(
            ClusterNewsMap.cluster_id,
            func.count(func.distinct(RawNews.source)).label("source_count"),
            func.min(func.coalesce(RawNews.published_at, RawNews.created_at)).label("first_ts"),
            func.max(func.coalesce(RawNews.published_at, RawNews.created_at)).label("last_ts"),
        )
        .join(CleanedNews, CleanedNews.id == ClusterNewsMap.cleaned_news_id)
        .join(RawNews, RawNews.id == CleanedNews.raw_news_id)
        .where(ClusterNewsMap.cluster_id.in_(cluster_ids))
        .group_by(ClusterNewsMap.cluster_id)
    ).all()

    result: dict[int, tuple[int, datetime | None, datetime | None]] = {}
    for row in rows:
        result[row.cluster_id] = (
            int(row.source_count or 0),
            row.first_ts if isinstance(row.first_ts, datetime) else None,
            row.last_ts if isinstance(row.last_ts, datetime) else None,
        )
    return result


# ---------------------------------------------------------------------------
# Signal accumulation across nodes
# ---------------------------------------------------------------------------

def _accumulate_signals(
    nodes: list[Node],
    cluster_stats: dict[int, tuple[int, datetime | None, datetime | None]],
) -> list[dict[str, object]]:
    """Accumulate signal detections across all nodes, grouped by
    (entity, signal_type, phrase).

    For each unique signal key, tracks:
    - total occurrences (frequency)
    - max unique source count
    - first_seen / last_seen time range
    - best phrase weight
    - all contributing node_ids

    Returns a list of accumulated signal dicts ready for persistence.
    """

    # Accumulation key: (entity, signal_type, phrase)
    accumulator: dict[tuple[str, str, str], dict[str, object]] = {}

    for node in nodes:
        text = f"{node.entity or ''} {node.event_type or ''} {node.description or ''}"
        matched = detect_phrases(text)
        if not matched:
            continue

        entity = node.entity or "unknown"
        source_count, first_ts, last_ts = cluster_stats.get(
            node.cluster_id, (0, None, None)
        )

        for phrase, signal_type, weight in matched:
            key = (entity, signal_type, phrase)

            if key not in accumulator:
                accumulator[key] = {
                    "entity": entity,
                    "signal_type": signal_type,
                    "phrase": phrase,
                    "phrase_weight": weight,
                    "frequency": 0,
                    "max_source_count": 0,
                    "first_seen": first_ts,
                    "last_seen": last_ts,
                    "node_ids": [],
                }

            acc = accumulator[key]
            acc["frequency"] = int(acc["frequency"]) + 1
            acc["max_source_count"] = max(int(acc["max_source_count"]), source_count)

            # Expand time range
            if first_ts is not None:
                current_first = acc["first_seen"]
                if current_first is None or first_ts < current_first:
                    acc["first_seen"] = first_ts
            if last_ts is not None:
                current_last = acc["last_seen"]
                if current_last is None or last_ts > current_last:
                    acc["last_seen"] = last_ts

            acc["phrase_weight"] = max(float(acc["phrase_weight"]), weight)
            acc["node_ids"].append(node.id)

    return list(accumulator.values())


# ---------------------------------------------------------------------------
# Structured phrase builder
# ---------------------------------------------------------------------------

def _build_structured_phrase(
    phrase: str,
    strength_label: str,
    frequency: int,
    source_count: int,
) -> str:
    """Build a self-explanatory structured phrase string.

    Example: "[STRONG] crisis (occurrences×4, sources×3)"
    """
    return f"[{strength_label}] {phrase} (occurrences×{frequency}, sources×{source_count})"


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def detect_and_store_signals(db: Session, limit: int = 500) -> dict[str, int]:
    """
    Structured early-warning signal detection (incremental).

    Steps:
    1) Fetch nodes WITHOUT existing signal entries
    2) Batch-load cluster stats (source count + time range)
    3) Detect phrases across all nodes
    4) Accumulate signals by (entity, signal_type, phrase)
    5) Compute multi-signal strength score for each accumulated signal
    6) Filter noise (single-occurrence weak signals below threshold)
    7) Build structured phrase output with strength label
    8) Persist or update signal records (evolution tracking)
    """
    nodes = (
        db.execute(
            select(Node)
            .outerjoin(Signal, Signal.node_id == Node.id)
            .where(Signal.id.is_(None))
            .order_by(Node.created_at.asc(), Node.id.asc())
            .limit(limit)
        )
        .scalars()
        .all()
    )
    if not nodes:
        return {
            "processed_nodes": 0,
            "signals_written": 0,
            "signals_updated": 0,
            "signals_filtered": 0,
        }

    # ---- Step 2: Batch cluster stats ----
    cluster_ids = list({n.cluster_id for n in nodes})
    cluster_stats = _batch_cluster_stats(db, cluster_ids)

    # ---- Step 3+4: Detect and accumulate ----
    accumulated = _accumulate_signals(nodes, cluster_stats)

    # ---- Step 5+6+7+8: Score, filter, persist ----
    signals_written = 0
    signals_updated = 0
    signals_filtered = 0

    for acc in accumulated:
        frequency = int(acc["frequency"])
        source_count = int(acc["max_source_count"])
        first_seen = acc["first_seen"]
        last_seen = acc["last_seen"]
        phrase_weight = float(acc["phrase_weight"])

        # Time persistence
        persistence = _time_persistence_score(first_seen, last_seen)

        # Strength scoring
        strength = _compute_strength_score(
            frequency=frequency,
            source_count=source_count,
            time_persistence=persistence,
            phrase_weight=phrase_weight,
        )
        label = _strength_label(strength)

        # Noise filter: skip single-occurrence weak signals
        if strength < _MIN_CONFIDENCE:
            signals_filtered += 1
            continue

        # Build structured output
        structured_phrase = _build_structured_phrase(
            phrase=str(acc["phrase"]),
            strength_label=label,
            frequency=frequency,
            source_count=source_count,
        )
        time_span = _time_span_label(first_seen, last_seen)
        entity = str(acc["entity"])
        signal_type = str(acc["signal_type"])

        # Persist: one signal per contributing node (traceable)
        node_ids = acc["node_ids"]
        primary_node_id = node_ids[0]

        # Check if this entity+type+phrase already has a signal on this node
        existing = db.scalar(
            select(Signal).where(
                Signal.node_id == primary_node_id,
                Signal.entity == entity,
                Signal.signal_type == signal_type,
            )
        )

        if existing is None:
            db.add(
                Signal(
                    node_id=primary_node_id,
                    signal_type=signal_type,
                    phrase=structured_phrase,
                    entity=entity,
                    source_count=source_count,
                    time_span=time_span,
                    confidence_score=strength,
                )
            )
            signals_written += 1
        else:
            # Evolution: update existing signal with accumulated data
            existing.phrase = structured_phrase
            existing.source_count = max(existing.source_count or 0, source_count)
            existing.time_span = time_span
            existing.confidence_score = max(existing.confidence_score or 0.0, strength)
            signals_updated += 1

        # Additional signals for secondary nodes (smaller set)
        for extra_node_id in node_ids[1:]:
            extra_existing = db.scalar(
                select(Signal).where(
                    Signal.node_id == extra_node_id,
                    Signal.entity == entity,
                    Signal.signal_type == signal_type,
                )
            )

            if extra_existing is None:
                db.add(
                    Signal(
                        node_id=extra_node_id,
                        signal_type=signal_type,
                        phrase=structured_phrase,
                        entity=entity,
                        source_count=source_count,
                        time_span=time_span,
                        confidence_score=strength,
                    )
                )
                signals_written += 1
            else:
                extra_existing.phrase = structured_phrase
                extra_existing.source_count = max(extra_existing.source_count or 0, source_count)
                extra_existing.time_span = time_span
                extra_existing.confidence_score = max(extra_existing.confidence_score or 0.0, strength)
                signals_updated += 1

    db.commit()
    return {
        "processed_nodes": len(nodes),
        "signals_written": signals_written,
        "signals_updated": signals_updated,
        "signals_filtered": signals_filtered,
    }

