"""Importance and candidate scoring for the recursive expansion engine.

Provides scoring functions that determine:
1. Which nodes are most valuable to expand (importance_score)
2. How strong a candidate cluster is relative to a seed node (candidate scoring)
"""

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from models.news_intelligence import (
    CleanedNews,
    ClusterNewsMap,
    Edge,
    Node,
    RawNews,
)


# ---------------------------------------------------------------------------
# Importance scoring — determines expansion priority
# ---------------------------------------------------------------------------

def compute_importance_score(
    db: Session,
    node: Node,
    max_depth: int = 10,
) -> float:
    """Compute how valuable it is to expand this node further.

    Formula:
      0.25 × confidence_score       — how reliable is this node's data
    + 0.25 × edge_connectivity      — how many causal edges connect to it
    + 0.20 × source_diversity        — how many independent sources back it
    + 0.15 × recency                 — how recent is this event
    + 0.15 × (1.0 - depth_decay)    — deeper nodes get lower priority

    Returns a score in [0.0, 1.0].
    """
    # Signal 1: confidence
    confidence = node.confidence_score or 0.5

    # Signal 2: edge connectivity (normalized)
    edge_count = db.scalar(
        select(func.count(Edge.id)).where(
            (Edge.from_node_id == node.id) | (Edge.to_node_id == node.id)
        )
    ) or 0
    edge_signal = min(edge_count / 10.0, 1.0)

    # Signal 3: source diversity
    source_count = db.scalar(
        select(func.count(func.distinct(RawNews.source)))
        .join(CleanedNews, CleanedNews.raw_news_id == RawNews.id)
        .join(ClusterNewsMap, ClusterNewsMap.cleaned_news_id == CleanedNews.id)
        .where(ClusterNewsMap.cluster_id == node.cluster_id)
    ) or 0
    source_signal = min(source_count / 5.0, 1.0)

    # Signal 4: recency
    recency_signal = 0.5  # default for nodes without timestamps
    if node.timestamp is not None:
        now = datetime.now(timezone.utc)
        ts = node.timestamp
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        age_days = max((now - ts).total_seconds() / 86400.0, 0.0)
        recency_signal = max(0.0, 1.0 - (age_days / 30.0))

    # Signal 5: depth decay — deeper nodes are less valuable to expand further
    depth = node.expansion_depth or 0
    safe_max = max(max_depth, 1)
    depth_decay = depth / safe_max
    depth_signal = 1.0 - depth_decay

    raw = (
        0.25 * confidence
        + 0.25 * edge_signal
        + 0.20 * source_signal
        + 0.15 * recency_signal
        + 0.15 * depth_signal
    )
    return round(min(max(raw, 0.0), 1.0), 4)


# ---------------------------------------------------------------------------
# Candidate scoring — how well does a cluster match a seed node
# ---------------------------------------------------------------------------

def score_candidate(
    entity_overlap: float,
    context_similarity: float,
    temporal_proximity: float,
) -> float:
    """Score a candidate cluster for expansion eligibility.

    Weights:
      0.40 × entity_overlap        — shared entities between seed and candidate
    + 0.35 × context_similarity    — text similarity of news content
    + 0.25 × temporal_proximity    — time closeness of events

    Returns a score in [0.0, 1.0].
    """
    raw = (
        0.40 * entity_overlap
        + 0.35 * context_similarity
        + 0.25 * temporal_proximity
    )
    return round(min(max(raw, 0.0), 1.0), 4)


# ---------------------------------------------------------------------------
# Confidence decay — child nodes get lower confidence than parents
# ---------------------------------------------------------------------------

def compute_child_confidence(
    parent_confidence: float,
    candidate_score: float,
    decay_factor: float = 0.85,
) -> float:
    """Compute confidence for a child node created during expansion.

    Child confidence = parent_confidence × decay_factor × candidate_score
    This ensures confidence degrades naturally with depth.

    Returns a score in [0.1, 1.0] (floored at 0.1 to avoid zero-confidence nodes).
    """
    raw = (parent_confidence or 0.5) * decay_factor * max(candidate_score, 0.1)
    return round(min(max(raw, 0.1), 1.0), 4)
