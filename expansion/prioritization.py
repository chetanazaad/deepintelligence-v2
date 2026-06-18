"""Lead Prioritization Engine.

Recomputes dynamic scores for pending leads based on context decay (novelty and 
connection to current news), and selects the top leads for expansion 
using a threshold-based algorithm.
"""

import logging
from sqlalchemy import select, func, or_, desc
from sqlalchemy.orm import Session

from models.news_intelligence import LeadQueue, Node, CleanedNews, ClusterNewsMap, InvestigationGoal
from expansion.novelty import calculate_loop_risk
from expansion.goals import (
    compute_goal_relevance,
    compute_lead_contribution,
    get_goal_knowledge_coverage,
    categorize_entity_or_lead,
)

logger = logging.getLogger(__name__)

EXPANSION_THRESHOLD = 0.90
MAX_EXPANSIONS_PER_NODE = 3


def recompute_dynamic_scores(db: Session) -> None:
    """Recompute the dynamic_score for all pending leads.
    
    dynamic_score = base_score + context_bonus + novelty_bonus
    """
    pending_leads = db.execute(select(LeadQueue).where(LeadQueue.status == "pending")).scalars().all()
    
    if not pending_leads:
        return
        
    # Pre-calculate global novelty metric: total nodes
    total_nodes = db.scalar(select(func.count(Node.id))) or 1
    
    # Fetch active goals for relevance scoring
    active_goals = db.execute(
        select(InvestigationGoal).where(InvestigationGoal.status == "active")
    ).scalars().all()
    
    for lead in pending_leads:
        # 1. Novelty Bonus (Max 0.20)
        # How many times does this entity already exist as a Node?
        existing_nodes_count = db.scalar(
            select(func.count(Node.id)).where(func.lower(Node.entity) == lead.entity.lower())
        ) or 0
        
        # If it doesn't exist at all, high novelty
        # If it exists 5+ times, 0 novelty
        novelty_bonus = max(0.0, 0.20 - (existing_nodes_count * 0.05))
        
        # 2. Context Bonus (Max 0.15)
        context_count = db.scalar(
            select(func.count(CleanedNews.id))
            .where(CleanedNews.normalized_text.ilike(f"%{lead.entity}%"))
        ) or 0
        
        context_bonus = min((context_count / 20.0) * 0.15, 0.15)
        
        # 3. Loop Penalty
        loop_risk = calculate_loop_risk(db, lead.entity, lead.source_node_id)
        loop_penalty = loop_risk * 0.40  # Max 0.40 penalty
        
        # 4. Goal Relevance, Contribution & Gap Closure (Goal Intent Engine)
        best_relevance_bonus = 0.0
        best_contribution_score = 0.0
        best_gap_closure_bonus = 0.0
        best_goal_id = None

        for goal in active_goals:
            relevance = compute_goal_relevance(
                db, lead.entity, lead.entity_type, lead.source_node_id, goal
            )
            contribution = compute_lead_contribution(
                db, lead.entity, lead.entity_type, lead.reason or "", lead.source_node_id, goal
            )
            
            coverage = get_goal_knowledge_coverage(db, goal)
            missing = coverage["missing"]
            lead_cats = categorize_entity_or_lead(lead.entity, lead.entity_type, lead.reason or "")
            
            gap_bonus = 0.0
            if set(missing) & lead_cats:
                gap_bonus = 0.10

            goal_impact = relevance + contribution + gap_bonus
            if goal_impact > (best_relevance_bonus + best_contribution_score + best_gap_closure_bonus):
                best_relevance_bonus = relevance
                best_contribution_score = contribution
                best_gap_closure_bonus = gap_bonus
                best_goal_id = goal.id

        # Assign lead to the most relevant goal
        if best_goal_id is not None:
            lead.goal_id = best_goal_id

        # Update dynamic score using the new formula
        lead.dynamic_score = max(0.0, min(
            lead.base_score + novelty_bonus + context_bonus - loop_penalty + 
            best_relevance_bonus + best_contribution_score + best_gap_closure_bonus,
            1.0
        ))
        
    db.commit()
    logger.info("Recomputed dynamic scores for %d pending leads.", len(pending_leads))


def select_top_leads(db: Session) -> list[LeadQueue]:
    """Select the best leads for investigation.
    
    1. Filter out duplicates (already existing nodes or selected/completed leads).
    2. Apply EXPANSION_THRESHOLD (>= 0.90).
    3. Cap at MAX_EXPANSIONS_PER_NODE per source_node.
    4. Promote to 'selected'.
    """
    recompute_dynamic_scores(db)
    
    # Get all pending leads ordered by dynamic_score descending
    pending_leads = db.execute(
        select(LeadQueue)
        .where(LeadQueue.status == "pending")
        .order_by(desc(LeadQueue.dynamic_score))
    ).scalars().all()
    
    selected_leads = []
    expansions_per_source = {}
    
    for lead in pending_leads:
        # Check deduplication
        exists_as_node = db.scalar(
            select(func.count(Node.id)).where(func.lower(Node.entity) == lead.entity.lower())
        )
        if exists_as_node:
            lead.status = "rejected"
            continue
            
        exists_in_queue = db.scalar(
            select(func.count(LeadQueue.id))
            .where(func.lower(LeadQueue.entity) == lead.entity.lower())
            .where(LeadQueue.status.in_(["selected", "researched", "completed"]))
        )
        if exists_in_queue:
            lead.status = "rejected"
            continue
            
        # Check threshold
        if lead.dynamic_score < EXPANSION_THRESHOLD:
            continue
            
        # Check source limit
        source_id = lead.source_node_id
        if expansions_per_source.get(source_id, 0) >= MAX_EXPANSIONS_PER_NODE:
            continue
            
        # Select lead
        lead.status = "selected"
        selected_leads.append(lead)
        expansions_per_source[source_id] = expansions_per_source.get(source_id, 0) + 1
        
    db.commit()
    logger.info("Selected %d leads for investigation.", len(selected_leads))
    return selected_leads
