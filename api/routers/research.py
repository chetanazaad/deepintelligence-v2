"""API endpoints for the Node Research Engine.

Provides strictly on-demand deep research profiles and
investigation leads for nodes.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import select

from api.deps import get_db
from models.news_intelligence import Node, NodeResearchProfile
from research.engine import execute_node_research

router = APIRouter(tags=["research"])


@router.post("/research/{node_id}")
def trigger_node_research(
    node_id: int,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    """Trigger an on-demand deep research pass for a node.
    
    This executes the Research Engine, synthesizing data across
    all 5 pillars, generating Investigation Leads, and saving
    the result to the NodeResearchProfile table.
    """
    node = db.scalar(select(Node).where(Node.id == node_id))
    if not node:
        raise HTTPException(status_code=404, detail="Node not found.")
        
    research_json = execute_node_research(db, node_id)
    if not research_json:
        raise HTTPException(status_code=500, detail="Failed to compile research.")
        
    return {
        "status": "success",
        "node_id": node_id,
        "entity": node.entity,
        "research_profile": research_json,
    }


@router.get("/research/{node_id}")
def get_node_research_profile(
    node_id: int,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    """Fetch the latest compiled research profile for a node without re-running the engine."""
    profile = db.scalar(select(NodeResearchProfile).where(NodeResearchProfile.node_id == node_id))
    if not profile:
        raise HTTPException(status_code=404, detail="Research profile not found. Run POST /research/{node_id} first.")
        
    return {
        "node_id": node_id,
        "research_version": profile.research_version,
        "last_updated": profile.updated_at.isoformat(),
        "research_profile": profile.research_json,
    }
