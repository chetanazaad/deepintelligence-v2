"""Node Research Engine orchestrator.

Coordinates gathering data from the 5 pillars, synthesizing the profile,
generating investigation leads, and persisting the NodeResearchProfile.
"""

import logging
from sqlalchemy import select
from sqlalchemy.orm import Session

from models.news_intelligence import LeadQueue, Node, NodeResearchProfile, InvestigationGoal
from research.gather import gather_all_pillars
from research.synthesis import synthesize_profile
from expansion.goals import generate_sub_goals

logger = logging.getLogger(__name__)


def execute_node_research(db: Session, node_id: int) -> dict | None:
    """Execute deep research on a single node on-demand.
    
    1. Gather data from 5 graph pillars.
    2. Synthesize profile and extract typed Investigation Leads.
    3. Save JSON to NodeResearchProfile (upsert with version increment).
    4. Update core Node metadata (confidence, type, importance).
    
    Returns the generated research_json.
    """
    node = db.scalar(select(Node).where(Node.id == node_id))
    if not node:
        logger.error("Node %d not found for research", node_id)
        return None
        
    logger.info("Executing Node Research on %d: %s", node_id, node.entity)
    
    # 1. Gather
    data = gather_all_pillars(db, node)
    
    # 2. Synthesize
    research_json = synthesize_profile(node.entity, data)
    
    # 3. Persist Profile (Upsert)
    profile = db.scalar(select(NodeResearchProfile).where(NodeResearchProfile.node_id == node_id))
    if profile:
        profile.research_version += 1
        profile.research_json = research_json
    else:
        profile = NodeResearchProfile(
            node_id=node_id,
            research_version=1,
            research_json=research_json,
        )
        db.add(profile)
        
    # 4. Update Node Metadata
    # Adjust confidence if source diversity is high
    if data.source_count > 5:
        node.confidence_score = min((node.confidence_score or 0.5) + 0.1, 1.0)
        
    # Adjust importance if we have solid leads
    if research_json["research_leads"]:
        node.importance_score = min((node.importance_score or 0.5) + 0.15, 1.0)
        
    # Update entity type if we have a top lead that matches the node entity exactly
    # (or leave as is if already strongly typed)
    if node.entity_type in [None, "topic", "CONCEPT"]:
        for lead in research_json["research_leads"]:
            if lead["entity"].lower() == (node.entity or "").lower() and lead["type"] != "CONCEPT":
                node.entity_type = lead["type"]
                break
                
    # 5. Push to LeadQueue
    # Delete pending leads for this node to avoid duplicates if re-researched
    db.execute(LeadQueue.__table__.delete().where(LeadQueue.source_node_id == node_id).where(LeadQueue.status == 'pending'))
    
    for lead in research_json["research_leads"]:
        lead_entry = LeadQueue(
            source_node_id=node_id,
            entity=lead["entity"],
            entity_type=lead["type"],
            score_profile=lead,
            base_score=lead["base_score"],
            dynamic_score=lead["base_score"], # Initial dynamic score is just the base score
            status="pending"
        )
        db.add(lead_entry)
                
    node.research_status = "completed"
    
    # 6. Generate sub-goals if this node is associated with an active goal
    # Check if any active goal's origin_node_id matches this node or its ancestors
    active_goals = db.execute(
        select(InvestigationGoal).where(InvestigationGoal.status == "active")
    ).scalars().all()
    
    for goal in active_goals:
        # Check if this node is a descendant of the goal's origin
        current_id = node_id
        is_related = False
        for _ in range(5):  # Walk up to 5 ancestors
            if current_id == goal.origin_node_id:
                is_related = True
                break
            parent_id = db.scalar(select(Node.parent_node_id).where(Node.id == current_id))
            if parent_id is None:
                break
            current_id = parent_id
        
        if is_related:
            generate_sub_goals(db, goal, research_json)
    
    db.commit()
    logger.info("Node Research completed for %d. Profile updated (v%d)", node_id, profile.research_version)
    
    return research_json
