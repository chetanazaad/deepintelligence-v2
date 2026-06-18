"""Research engine for the recursive expansion system.

Given a node, finds and scores expansion candidates by applying the
3-gate filter (entity overlap, context similarity, time proximity)
against all available clusters.

This module performs the RESEARCH phase of the recursive lifecycle:
    research_node(db, node_id, config) → ResearchResult

After research completes, candidates are stored in the node's
research_summary and a NodeResearchLog entry is written.
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from difflib import SequenceMatcher
from re import findall

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from models.news_intelligence import (
    CleanedNews,
    ClusterNewsMap,
    EventCluster,
    Node,
    NodeResearchLog,
    RawNews,
)
from expansion.scoring import score_candidate

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class CandidateResult:
    """A single expansion candidate identified during research."""
    cluster_id: int
    main_topic: str
    score: float
    entity_overlap: float
    context_similarity: float
    temporal_proximity: float
    latest_ts: datetime | None = None


@dataclass(slots=True)
class ResearchResult:
    """Complete result of researching a node for expansion candidates."""
    node_id: int
    candidates: list[CandidateResult] = field(default_factory=list)
    candidates_found: int = 0
    candidates_qualified: int = 0
    best_score: float = 0.0
    status: str = "completed"
    error_message: str | None = None
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: datetime | None = None


# ---------------------------------------------------------------------------
# Gate functions (reusing patterns from existing expansion/service.py)
# ---------------------------------------------------------------------------

def _tokens(text: str) -> set[str]:
    """Extract alphanumeric tokens (3+ chars) from text."""
    return {t.lower() for t in findall(r"[a-zA-Z0-9]{3,}", text or "")}


def _compute_entity_overlap(node_entity: str, cluster_topic: str) -> float:
    """Jaccard-like overlap between node entity tokens and cluster topic tokens."""
    a = _tokens(node_entity)
    b = _tokens(cluster_topic)
    if not a or not b:
        return 0.0
    intersection = len(a & b)
    union = len(a | b)
    return intersection / union if union else 0.0


def _compute_context_similarity(a: str, b: str) -> float:
    """SequenceMatcher similarity between two text blocks."""
    return SequenceMatcher(None, (a or "").lower()[:2000], (b or "").lower()[:2000]).ratio()


def _compute_temporal_proximity(
    seed_ts: datetime | None,
    candidate_ts: datetime | None,
    max_days: int,
) -> float:
    """Score temporal proximity — 1.0 for same-day, 0.0 for beyond max_days."""
    if seed_ts is None or candidate_ts is None:
        return 0.0
    # Ensure UTC
    if seed_ts.tzinfo is None:
        seed_ts = seed_ts.replace(tzinfo=timezone.utc)
    if candidate_ts.tzinfo is None:
        candidate_ts = candidate_ts.replace(tzinfo=timezone.utc)
    gap_days = abs((seed_ts - candidate_ts).total_seconds()) / 86400.0
    if gap_days > max_days:
        return 0.0
    return max(0.0, 1.0 - (gap_days / max_days))


# ---------------------------------------------------------------------------
# Cluster data loader
# ---------------------------------------------------------------------------

def _load_cluster_contexts(db: Session) -> dict[int, dict[str, object]]:
    """Load all cluster contexts for candidate matching.

    Returns: {cluster_id: {"main_topic": str, "latest_ts": datetime|None, "context_text": str}}
    """
    rows = db.execute(
        select(
            EventCluster.id,
            EventCluster.main_topic,
            func.max(func.coalesce(RawNews.published_at, RawNews.created_at)).label("latest_ts"),
        )
        .join(ClusterNewsMap, ClusterNewsMap.cluster_id == EventCluster.id)
        .join(CleanedNews, CleanedNews.id == ClusterNewsMap.cleaned_news_id)
        .join(RawNews, RawNews.id == CleanedNews.raw_news_id)
        .group_by(EventCluster.id, EventCluster.main_topic)
    ).all()

    result: dict[int, dict[str, object]] = {}
    for row in rows:
        result[int(row.id)] = {
            "main_topic": str(row.main_topic),
            "latest_ts": row.latest_ts if isinstance(row.latest_ts, datetime) else None,
        }
    return result


def _load_cluster_text(db: Session, cluster_id: int) -> str:
    """Load concatenated normalized text for a specific cluster."""
    rows = db.execute(
        select(CleanedNews.normalized_text)
        .join(ClusterNewsMap, ClusterNewsMap.cleaned_news_id == CleanedNews.id)
        .where(ClusterNewsMap.cluster_id == cluster_id)
        .limit(5)
    ).scalars().all()
    return " ".join(rows) if rows else ""


# ---------------------------------------------------------------------------
# Main research function
# ---------------------------------------------------------------------------

def research_node(
    db: Session,
    node_id: int,
    *,
    similarity_threshold: float = 0.35,
    max_time_gap_days: int = 7,
    max_candidates: int = 10,
) -> ResearchResult:
    """Research a node for expansion candidates.

    Steps:
    1. Load the node and its cluster context
    2. Load all cluster snapshots
    3. Apply 3-gate filter: entity overlap, context similarity, time proximity
    4. Score qualified candidates
    5. Update node.research_status and node.research_summary
    6. Write NodeResearchLog entry

    Returns:
        ResearchResult with scored candidates.
    """
    result = ResearchResult(node_id=node_id)

    # Load the node
    node = db.scalar(select(Node).where(Node.id == node_id))
    if node is None:
        result.status = "failed"
        result.error_message = f"Node {node_id} not found"
        return result

    # Mark as researching
    node.research_status = "in_progress"
    db.flush()

    try:
        # Load seed context
        seed_context = _load_cluster_text(db, node.cluster_id)
        seed_entity = node.entity or ""
        seed_ts = node.timestamp

        # Get IDs of clusters that already have nodes (to track, not exclude)
        existing_node_clusters = {
            row[0] for row in db.execute(select(Node.cluster_id)).all()
        }

        # Load all clusters
        cluster_data = _load_cluster_contexts(db)
        if not cluster_data:
            node.research_status = "completed"
            node.research_summary = json.dumps({
                "candidates_found": 0,
                "candidates_qualified": 0,
                "message": "No clusters available for expansion",
            })
            result.completed_at = datetime.now(timezone.utc)
            _write_log(db, result, node.expansion_depth)
            db.commit()
            return result

        # Score all candidates through 3-gate filter
        candidates: list[CandidateResult] = []
        rejected = {"low_entity_overlap": 0, "low_similarity": 0, "time_gap_exceeded": 0}

        for cluster_id, info in cluster_data.items():
            # Skip own cluster
            if cluster_id == node.cluster_id:
                continue

            topic = str(info["main_topic"])
            latest_ts = info["latest_ts"]

            # Gate 1: entity overlap
            entity_overlap = _compute_entity_overlap(seed_entity, topic)
            if entity_overlap < 0.05:
                rejected["low_entity_overlap"] += 1
                continue

            # Gate 2: context similarity (lazy-load candidate text)
            candidate_text = _load_cluster_text(db, cluster_id)
            context_sim = _compute_context_similarity(seed_context, candidate_text)
            if context_sim < similarity_threshold:
                rejected["low_similarity"] += 1
                continue

            # Gate 3: temporal proximity
            temporal_prox = _compute_temporal_proximity(
                seed_ts, latest_ts, max_days=max_time_gap_days
            )
            if temporal_prox <= 0.0:
                rejected["time_gap_exceeded"] += 1
                continue

            # All 3 gates passed — score the candidate
            overall_score = score_candidate(
                entity_overlap=entity_overlap,
                context_similarity=context_sim,
                temporal_proximity=temporal_prox,
            )

            candidates.append(CandidateResult(
                cluster_id=cluster_id,
                main_topic=topic,
                score=overall_score,
                entity_overlap=entity_overlap,
                context_similarity=context_sim,
                temporal_proximity=temporal_prox,
                latest_ts=latest_ts,
            ))

        # Sort by score descending and limit
        candidates.sort(key=lambda c: c.score, reverse=True)
        result.candidates_found = len(candidates)
        result.candidates = candidates[:max_candidates]
        result.candidates_qualified = len(result.candidates)
        result.best_score = result.candidates[0].score if result.candidates else 0.0
        result.status = "completed"
        result.completed_at = datetime.now(timezone.utc)

        # Update node
        node.research_status = "completed"
        node.research_summary = json.dumps({
            "candidates_found": result.candidates_found,
            "candidates_qualified": result.candidates_qualified,
            "best_score": result.best_score,
            "research_timestamp": result.completed_at.isoformat(),
            "entity_matches": list({
                c.main_topic.split()[0] for c in result.candidates if c.main_topic
            }),
            "rejected_reasons": rejected,
            "candidates": [
                {
                    "cluster_id": c.cluster_id,
                    "topic": c.main_topic,
                    "score": c.score,
                    "entity_overlap": c.entity_overlap,
                    "context_similarity": c.context_similarity,
                    "temporal_proximity": c.temporal_proximity,
                }
                for c in result.candidates
            ],
        })

    except Exception as exc:
        result.status = "failed"
        result.error_message = str(exc)
        result.completed_at = datetime.now(timezone.utc)
        node.research_status = "failed"
        logger.exception("Research failed for node %d: %s", node_id, exc)

    _write_log(db, result, node.expansion_depth)
    db.commit()
    return result


def _write_log(db: Session, result: ResearchResult, depth: int) -> None:
    """Persist a NodeResearchLog entry for auditing."""
    db.add(NodeResearchLog(
        node_id=result.node_id,
        research_depth=depth,
        candidates_found=result.candidates_found,
        candidates_qualified=result.candidates_qualified,
        best_score=result.best_score if result.best_score > 0 else None,
        gate_results=None,  # detailed gate_results can be stored from research_summary
        status=result.status,
        error_message=result.error_message,
        started_at=result.started_at,
        completed_at=result.completed_at,
    ))
