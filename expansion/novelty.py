"""Knowledge Novelty Engine.

Evaluates selected leads against the existing graph to determine if they represent
new knowledge (CREATE), existing connections (LINK), deeper context (ENHANCE), 
or semantic duplicates (MERGE/REJECT). Also provides Loop Prevention heuristics.
"""

import logging
from sqlalchemy import select
from sqlalchemy.orm import Session

from models.news_intelligence import LeadQueue, Node, NodeResearchProfile

logger = logging.getLogger(__name__)

# Configurable Thresholds
MERGE_THRESHOLD = 0.20
ENHANCE_THRESHOLD = 0.40
LINK_THRESHOLD = 0.65


def _jaccard_similarity(str1: str, str2: str) -> float:
    """Calculate character n-gram (trigram) Jaccard similarity between two strings."""
    s1, s2 = str1.lower().strip(), str2.lower().strip()
    if not s1 or not s2:
        return 0.0
        
    def get_trigrams(text: str) -> set[str]:
        # pad string to handle short words
        text = f"  {text}  "
        return {text[i:i+3] for i in range(len(text)-2)}
        
    set1 = get_trigrams(s1)
    set2 = get_trigrams(s2)
    
    intersection = len(set1 & set2)
    union = len(set1 | set2)
    return intersection / union if union > 0 else 0.0


def compute_novelty_score(db: Session, lead_entity: str, source_node_id: int) -> tuple[float, Node | None]:
    """Compute how novel a lead is compared to existing nodes.
    
    Returns (novelty_score, closest_node).
    0.0 = exact duplicate
    1.0 = completely new
    """
    # Fetch all nodes (for a massive graph, we'd use vector search or inverted index, 
    # but for deterministic DB logic we can fetch a subset or all entities)
    all_nodes = db.execute(select(Node)).scalars().all()
    
    if not all_nodes:
        return 1.0, None
        
    max_similarity = 0.0
    closest_node = None
    
    for node in all_nodes:
        if not node.entity:
            continue
            
        sim = _jaccard_similarity(lead_entity, node.entity)
        
        # Lineage Penalty / Boost: If they share the same parent, they are more likely siblings, 
        # but if the similarity is very high, they might be exact duplicates.
        if node.parent_node_id == source_node_id and sim > 0.5:
            sim += 0.1 # Boost similarity (reduce novelty) if it's born from the same source
            
        if sim > max_similarity:
            max_similarity = sim
            closest_node = node
            
    # Cap similarity at 1.0
    max_similarity = min(max_similarity, 1.0)
    novelty_score = 1.0 - max_similarity
    
    return novelty_score, closest_node


def make_knowledge_decision(novelty_score: float) -> str:
    """Map novelty score to an actionable decision."""
    if novelty_score < MERGE_THRESHOLD:
        return "MERGE"
    elif novelty_score < ENHANCE_THRESHOLD:
        return "ENHANCE"
    elif novelty_score < LINK_THRESHOLD:
        return "LINK"
    else:
        return "CREATE"


def calculate_loop_risk(db: Session, lead_entity: str, source_node_id: int) -> float:
    """Detect circular investigations by traversing lineage up to depth 5.
    
    Returns a Loop Risk Score (0.0 to 1.0).
    """
    risk = 0.0
    current_node_id = source_node_id
    depth = 0
    
    lead_root_word = lead_entity.split()[0].lower() if lead_entity else ""
    if not lead_root_word or len(lead_root_word) < 4:
        return 0.0  # Too generic to risk penalize based on first word
        
    while current_node_id and depth < 5:
        parent = db.scalar(select(Node).where(Node.id == current_node_id))
        if not parent:
            break
            
        # Check if ancestor shares the same root word
        if parent.entity and parent.entity.lower().startswith(lead_root_word):
            # The closer the ancestor, the higher the risk
            risk += (1.0 - (depth * 0.2))
            
        current_node_id = parent.parent_node_id
        depth += 1
        
    return min(risk, 1.0)
