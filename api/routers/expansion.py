"""API endpoints for recursive node expansion.

Provides on-demand expansion triggers, status checking,
graph traversal, and research history endpoints.
"""

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from api.deps import get_db
from expansion.recursive_expander import run_expansion_cycle
from models.news_intelligence import Edge, Node, NodeResearchLog, LeadQueue

logger = logging.getLogger(__name__)

router = APIRouter(tags=["expansion"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if isinstance(value, datetime) else None


def _build_node_summary(node: Node) -> dict[str, object]:
    """Build a compact node summary for API responses."""
    return {
        "node_id": node.id,
        "entity": node.entity or "",
        "event_type": node.event_type or "update",
        "expansion_depth": node.expansion_depth,
        "parent_node_id": node.parent_node_id,
        "research_status": node.research_status,
        "expansion_status": node.expansion_status,
        "importance_score": node.importance_score,
        "confidence_score": node.confidence_score,
        "is_anchor": node.is_anchor,
        "timestamp": _iso(node.timestamp),
        "expanded_at": _iso(node.expanded_at),
    }


def _build_graph_tree(
    db: Session,
    node: Node,
    max_depth: int,
    current_depth: int = 0,
) -> dict[str, object]:
    """Recursively build the expansion tree from a root node."""
    children_nodes = (
        db.execute(
            select(Node)
            .where(Node.parent_node_id == node.id)
            .order_by(Node.importance_score.desc())
        )
        .scalars()
        .all()
    )

    children = []
    if current_depth < max_depth:
        for child in children_nodes:
            # Get the edge connecting parent to child
            edge = db.scalar(
                select(Edge).where(
                    Edge.from_node_id == node.id,
                    Edge.to_node_id == child.id,
                )
            )
            child_tree = _build_graph_tree(db, child, max_depth, current_depth + 1)
            if edge is not None:
                child_tree["edge"] = {
                    "relation": edge.relation_type,
                    "confidence": edge.confidence_score,
                }
            children.append(child_tree)

    return {
        **_build_node_summary(node),
        "children_count": len(children_nodes),
        "children": children,
    }


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/expansion/cycle")
def trigger_expansion_cycle(
    db: Session = Depends(get_db),
) -> dict[str, object]:
    """Trigger a cycle of the Prioritization Engine.
    
    This consumes 'selected' leads from the LeadQueue, creates nodes,
    and runs the Node Research Engine on them recursively.
    """
    result = run_expansion_cycle(db)
    return result


@router.get("/expansion/queue")
def get_lead_queue(
    status: str | None = None,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    """Get the current state of the LeadQueue."""
    query = select(LeadQueue).order_by(LeadQueue.dynamic_score.desc())
    if status:
        query = query.where(LeadQueue.status == status)
        
    leads = db.execute(query).scalars().all()
    return {
        "count": len(leads),
        "leads": [
            {
                "id": lead.id,
                "source_node_id": lead.source_node_id,
                "entity": lead.entity,
                "entity_type": lead.entity_type,
                "base_score": lead.base_score,
                "dynamic_score": lead.dynamic_score,
                "status": lead.status,
            }
            for lead in leads
        ]
    }


@router.get("/expansion/dashboard")
def get_knowledge_health_dashboard(db: Session = Depends(get_db)) -> dict[str, object]:
    """Get the Knowledge Health Dashboard metrics."""
    total_nodes = db.scalar(select(func.count(Node.id))) or 1
    total_edges = db.scalar(select(func.count(Edge.id))) or 0
    
    unique_concepts = db.scalar(select(func.count(Node.id)).where(Node.entity != None)) or 0
    
    # We can infer merges/links/enhances from the lead queue status or edges, but 
    # to be simple we'll just pull the statuses from LeadQueue and relationships.
    rejected_leads = db.scalar(select(func.count(LeadQueue.id)).where(LeadQueue.status == "rejected")) or 0
    
    linked_concepts = db.scalar(select(func.count(Edge.id)).where(Edge.relation_type == "links_to")) or 0
    
    # Calculate density
    # A simple metric: (edges + nodes_with_profiles) / total_nodes
    nodes_with_profiles = db.scalar(select(func.count(NodeResearchProfile.id))) or 0
    knowledge_density = (total_edges + nodes_with_profiles) / total_nodes
    
    # Compression Ratio: 1 - (Total Nodes / (Total Nodes + Rejected + Enhanced + Linked))
    # We use a rough estimate if we don't have explicit columns for all
    total_intel_points = total_nodes + rejected_leads + linked_concepts
    compression_ratio = 1.0 - (total_nodes / total_intel_points) if total_intel_points > 0 else 0.0
    
    return {
        "total_nodes": total_nodes,
        "total_edges": total_edges,
        "unique_concepts": unique_concepts,
        "linked_concepts": linked_concepts,
        "rejected_leads": rejected_leads,
        "knowledge_density": round(knowledge_density, 3),
        "compression_ratio": round(compression_ratio, 3)
    }

@router.get("/graph/{node_id}")
def get_expansion_graph(
    node_id: int,
    depth: int = Query(default=3, ge=1, le=10, description="Max tree depth to return"),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    """Get the full expansion tree rooted at a node."""
    node = db.scalar(select(Node).where(Node.id == node_id))
    if node is None:
        raise HTTPException(status_code=404, detail="Node not found.")

    tree = _build_graph_tree(db, node, max_depth=depth)
    return {
        "root": tree,
        "requested_depth": depth,
    }
