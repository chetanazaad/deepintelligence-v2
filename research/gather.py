"""Data gathering for the Node Research Engine.

Traverses the 5 pillars of the intelligence graph:
1. Source Material (News)
2. Causal Context (Edges)
3. Consequence Profiling (Impacts)
4. Early-Warning Metrics (Signals)
5. Chronological Context (Timelines)
"""

from typing import Any
from sqlalchemy import select, func
from sqlalchemy.orm import Session

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

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

class PillarData:
    """Holds all gathered data across the 5 pillars."""
    def __init__(self):
        self.source_texts: list[str] = []
        self.source_count: int = 0
        self.news_velocity: int = 0
        self.predecessors: list[dict[str, Any]] = []
        self.successors: list[dict[str, Any]] = []
        self.impacts: list[dict[str, Any]] = []
        self.signals: list[dict[str, Any]] = []
        self.timeline_context: dict[str, Any] = {}

# ---------------------------------------------------------------------------
# Gather Functions
# ---------------------------------------------------------------------------

def _gather_source_material(db: Session, node: Node, data: PillarData) -> None:
    """Pillar 1: Gather cluster and news data."""
    if not node.cluster_id:
        return
        
    # Get all cleaned texts and raw sources
    rows = (
        db.execute(
            select(CleanedNews.normalized_text, RawNews.source)
            .join(ClusterNewsMap, ClusterNewsMap.cleaned_news_id == CleanedNews.id)
            .join(RawNews, RawNews.id == CleanedNews.raw_news_id)
            .where(ClusterNewsMap.cluster_id == node.cluster_id)
        )
        .all()
    )
    
    unique_sources = set()
    for row in rows:
        text, source = row
        data.source_texts.append(text)
        unique_sources.add(source)
        data.news_velocity += 1
        
    data.source_count = len(unique_sources)


def _gather_causal_context(db: Session, node: Node, data: PillarData) -> None:
    """Pillar 2: Gather predecessors and successors."""
    # Predecessors (Incoming edges)
    in_edges = (
        db.execute(
            select(Edge.relation_type, Node.id, Node.entity, Node.description)
            .join(Node, Node.id == Edge.from_node_id)
            .where(Edge.to_node_id == node.id)
        )
        .all()
    )
    for row in in_edges:
        data.predecessors.append({
            "relation": row.relation_type,
            "node_id": row.id,
            "entity": row.entity,
            "description": row.description,
        })
        
    # Successors (Outgoing edges)
    out_edges = (
        db.execute(
            select(Edge.relation_type, Node.id, Node.entity, Node.description)
            .join(Node, Node.id == Edge.to_node_id)
            .where(Edge.from_node_id == node.id)
        )
        .all()
    )
    for row in out_edges:
        data.successors.append({
            "relation": row.relation_type,
            "node_id": row.id,
            "entity": row.entity,
            "description": row.description,
        })


def _gather_impacts(db: Session, node: Node, data: PillarData) -> None:
    """Pillar 3: Gather consequence profiling."""
    impacts = db.execute(select(Impact).where(Impact.node_id == node.id)).scalars().all()
    for impact in impacts:
        data.impacts.append({
            "short_winners": impact.short_term_winners or [],
            "short_losers": impact.short_term_losers or [],
            "long_winners": impact.long_term_winners or [],
            "long_losers": impact.long_term_losers or [],
            "confidence": impact.confidence_score,
        })


def _gather_signals(db: Session, node: Node, data: PillarData) -> None:
    """Pillar 4: Gather early-warning signals."""
    signals = db.execute(select(Signal).where(Signal.node_id == node.id)).scalars().all()
    for signal in signals:
        data.signals.append({
            "type": signal.signal_type,
            "phrase": signal.phrase,
            "entity": signal.entity,
            "strength": signal.confidence_score,
        })


def _gather_timeline_context(db: Session, node: Node, data: PillarData) -> None:
    """Pillar 5: Gather chronological timeline context."""
    entry = db.scalar(select(TimelineEntry).where(TimelineEntry.node_id == node.id).limit(1))
    if entry:
        # Get total entries in this timeline group
        group_size = db.scalar(
            select(func.count(TimelineEntry.id))
            .where(TimelineEntry.timeline_group_id == entry.timeline_group_id)
        ) or 0
        
        data.timeline_context = {
            "group_id": entry.timeline_group_id,
            "position": entry.position_index,
            "is_anchor": node.is_anchor,
            "group_size": group_size,
        }
    else:
        data.timeline_context = {
            "group_id": "isolated",
            "position": 0,
            "is_anchor": node.is_anchor,
            "group_size": 1,
        }

# ---------------------------------------------------------------------------
# Main Gather Function
# ---------------------------------------------------------------------------

def gather_all_pillars(db: Session, node: Node) -> PillarData:
    """Traverse all 5 pillars and compile data for a specific node."""
    data = PillarData()
    _gather_source_material(db, node, data)
    _gather_causal_context(db, node, data)
    _gather_impacts(db, node, data)
    _gather_signals(db, node, data)
    _gather_timeline_context(db, node, data)
    return data
