"""Recursive expansion orchestrator.

Implements the Prioritization Engine loop:
1. Poll the LeadQueue for selected leads.
2. Create Nodes and Edges.
3. Trigger the Node Research Engine.
4. Mark leads as completed.
"""

import logging
from datetime import datetime, timezone
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from models.news_intelligence import Edge, Node, LeadQueue, NodeResearchProfile, InvestigationGoal
from expansion.prioritization import select_top_leads
from expansion.novelty import compute_novelty_score, make_knowledge_decision
from expansion.goals import check_goal_state
from research.engine import execute_node_research

logger = logging.getLogger(__name__)


def run_expansion_cycle(db: Session) -> dict:
    """Run one full cycle of the expansion loop.
    
    1. Triggers Prioritization Engine to select top leads.
    2. Routes selected leads through the Knowledge Novelty Engine.
    3. Executes MERGE, ENHANCE, LINK, or CREATE decisions.
    4. Runs Node Research Engine on new Nodes.
    """
    # 1. Prioritize and select
    selected_leads = select_top_leads(db)
    if not selected_leads:
        logger.info("No leads met the expansion threshold. Cycle complete.")
        return {"status": "no_action", "metrics": {}}
        
    metrics = {
        "created": 0,
        "enhanced": 0,
        "linked": 0,
        "merged": 0,
    }
    
    created_nodes = []
    
    # 2. Consume leads
    for lead in selected_leads:
        # Mark as researched (we are investigating it now)
        lead.status = "researched"
        db.commit()
        
        # 3. Novelty Gate
        novelty_score, closest_node = compute_novelty_score(db, lead.entity, lead.source_node_id)
        decision = make_knowledge_decision(novelty_score)
        logger.info("Lead '%s' novelty=%.2f -> Decision: %s", lead.entity, novelty_score, decision)
        
        if decision == "MERGE" or not closest_node:
            if decision == "MERGE":
                lead.status = "rejected" # Semantic duplicate
                metrics["merged"] += 1
            else:
                decision = "CREATE" # Fallback if graph is empty
                
        if decision == "ENHANCE" and closest_node:
            # Append evidence to existing profile
            profile = db.scalar(select(NodeResearchProfile).where(NodeResearchProfile.node_id == closest_node.id))
            if profile:
                evidence = profile.research_json.get("supporting_evidence", [])
                evidence.append({
                    "source_node_id": lead.source_node_id,
                    "date_added": datetime.now(timezone.utc).isoformat(),
                    "context": f"Reinforced by lead '{lead.entity}' (score: {lead.dynamic_score})"
                })
                profile.research_json["supporting_evidence"] = evidence
                profile.research_version += 1
                
                # Boost confidence due to corroboration
                closest_node.confidence_score = min((closest_node.confidence_score or 0.5) + 0.1, 1.0)
                
            lead.status = "completed"
            metrics["enhanced"] += 1
            # Goal budget accounting
            if lead.goal_id:
                goal = db.scalar(select(InvestigationGoal).where(InvestigationGoal.id == lead.goal_id))
                if goal:
                    goal.expansions_used += 1
            db.commit()
            continue
            
        if decision == "LINK" and closest_node:
            # Draw an edge to the existing node
            existing_edge = db.scalar(
                select(Edge).where(Edge.from_node_id == lead.source_node_id).where(Edge.to_node_id == closest_node.id)
            )
            if not existing_edge:
                edge = Edge(
                    from_node_id=lead.source_node_id,
                    to_node_id=closest_node.id,
                    relation_type="links_to",
                    confidence_score=lead.dynamic_score,
                )
                db.add(edge)
            lead.status = "completed"
            metrics["linked"] += 1
            # Goal budget accounting
            if lead.goal_id:
                goal = db.scalar(select(InvestigationGoal).where(InvestigationGoal.id == lead.goal_id))
                if goal:
                    goal.expansions_used += 1
            db.commit()
            continue
            
        if decision == "CREATE":
            source_node = db.scalar(select(Node).where(Node.id == lead.source_node_id))
            depth = (source_node.expansion_depth if source_node else 0) + 1
            
            new_node = Node(
                cluster_id=source_node.cluster_id if source_node else 1,
                entity=lead.entity,
                entity_type=lead.entity_type,
                event_type="investigation",
                description=f"Investigated from lead ({lead.score_profile.get('reason', 'High priority')})",
                timestamp=datetime.now(timezone.utc),
                impact_type="neutral",
                confidence_score=0.5,
                is_anchor=False,
                expansion_depth=depth,
                parent_node_id=lead.source_node_id,
                research_status="not_started",
                expansion_status="not_started",
                importance_score=lead.dynamic_score,
            )
            db.add(new_node)
            db.flush()
            
            if source_node:
                edge = Edge(
                    from_node_id=source_node.id,
                    to_node_id=new_node.id,
                    relation_type="investigates",
                    confidence_score=lead.dynamic_score,
                )
                db.add(edge)
                db.flush()
                
            logger.info("Created new Node %d for lead '%s'", new_node.id, lead.entity)
            
            # Trigger Research Engine
            try:
                execute_node_research(db, new_node.id)
                lead.status = "completed"
                metrics["created"] += 1
                created_nodes.append({"id": new_node.id, "entity": new_node.entity})
                # Goal budget accounting
                if lead.goal_id:
                    goal = db.scalar(select(InvestigationGoal).where(InvestigationGoal.id == lead.goal_id))
                    if goal:
                        goal.expansions_used += 1
            except Exception as e:
                logger.error("Research failed for node %d: %s", new_node.id, e)
                lead.status = "rejected"
                
            db.commit()
    # After processing all leads, evaluate goal state transitions
    active_goals = db.execute(
        select(InvestigationGoal).where(InvestigationGoal.status == "active")
    ).scalars().all()
    
    goal_states = {}
    for goal in active_goals:
        state = check_goal_state(db, goal)
        goal_states[goal.id] = {
            "question": goal.goal_question[:80],
            "state": state,
            "completion": goal.completion_score,
            "budget": f"{goal.expansions_used}/{goal.expansion_budget}",
        }
        
    return {
        "status": "success",
        "metrics": metrics,
        "nodes": created_nodes,
        "goal_states": goal_states,
    }
