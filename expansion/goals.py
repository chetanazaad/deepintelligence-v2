"""Investigation Goal Engine.

Provides goal-directed intelligence: keyword extraction, lead relevance scoring,
completion tracking, stopping logic, and deterministic sub-goal generation.

All functions are designed as swappable interfaces for future LLM integration.
"""

import logging
import re
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select, func, and_, or_
from sqlalchemy.orm import Session

from models.news_intelligence import (
    Edge,
    Impact,
    InvestigationGoal,
    Node,
    NodeResearchProfile,
    Signal,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_STOP_WORDS = {
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "shall",
    "should", "may", "might", "can", "could", "must", "of", "in", "to",
    "for", "with", "on", "at", "from", "by", "about", "as", "into",
    "through", "during", "before", "after", "above", "below", "between",
    "and", "but", "or", "nor", "not", "so", "yet", "both", "either",
    "neither", "each", "every", "all", "any", "few", "more", "most",
    "other", "some", "such", "no", "only", "own", "same", "than", "too",
    "very", "just", "because", "if", "when", "where", "how", "what",
    "which", "who", "whom", "this", "that", "these", "those", "it", "its",
    "i", "me", "my", "we", "our", "you", "your", "he", "him", "his",
    "she", "her", "they", "them", "their",
    "why", "did",  # keep question context but remove from matching
}

# Lexical dictionaries for classification
INTENT_LEXICON = {
    "ROOT_CAUSE": {"cause", "origin", "source", "trigger", "because", "due", "root", "reason", "why", "how"},
    "ECONOMIC_DRIVER": {"profit", "loss", "revenue", "economic", "finance", "market", "valuation", "trade", "deal", "buy", "sell", "acquire", "merger", "transaction", "investment", "commercial", "cost", "financial"},
    "POLICY_DRIVER": {"policy", "regulation", "law", "act", "legislation", "bill", "mandate", "tariff", "subsidy", "ban", "reform", "government", "ministry", "directive", "decree", "compliance", "permit", "permitted", "sanctioned"},
    "GEOPOLITICAL_DRIVER": {"geopolitical", "foreign", "alliance", "border", "territory", "sovereignty", "sanctions", "military", "bloc", "defense", "treaty", "naval", "diplomatic", "state", "international", "dispute", "contesting", "control", "nation", "country"},
    "ACTOR_MOTIVATION": {"motivation", "intent", "incentive", "objective", "goal", "strategy", "purpose", "aim", "drive", "decision", "action", "threat", "positioning", "competitor", "motive", "desire", "ambition"},
    "FUTURE_CONSEQUENCES": {"consequence", "impact", "future", "forecast", "projection", "scenario", "outlook", "trend", "predict", "next", "aftermath", "fallout", "outcome", "result", "affect", "happen"},
    "RISK_ANALYSIS": {"risk", "threat", "vulnerability", "exposure", "hazard", "danger", "failure", "weakness", "contagion", "loss", "liability", "bottleneck", "choke", "downside"},
    "OPPORTUNITY_ANALYSIS": {"opportunity", "upside", "benefit", "advantage", "growth", "synergy", "efficiency", "leverage", "expansion", "profitability", "gain", "upside"}
}

# Syntactic prefix check rules
INTENT_PREFIXES = {
    "ROOT_CAUSE": ["why did", "what caused", "how did", "reason for", "origin of"],
    "ECONOMIC_DRIVER": ["who benefits economically", "what are the financial", "why did adani acquire", "what are the economic drivers"],
    "POLICY_DRIVER": ["what policy", "how does regulation", "what government action"],
    "GEOPOLITICAL_DRIVER": ["why is country", "what are the regional security", "geopolitical consequences"],
    "ACTOR_MOTIVATION": ["why did decide", "what is objective", "what motivates"],
    "FUTURE_CONSEQUENCES": ["what are the consequences", "what will happen", "what is the long-term impact"],
    "RISK_ANALYSIS": ["what are the risks", "is threat to", "how vulnerable"],
    "OPPORTUNITY_ANALYSIS": ["what are the opportunities", "how can benefit", "what is the upside"]
}

# Configurable required knowledge categories per intent
REQUIRED_KNOWLEDGE_CATEGORIES = {
    "ROOT_CAUSE": ["POLICY", "COMPANY", "COMPETITION", "MARKET", "LOGISTICS"],
    "ECONOMIC_DRIVER": ["COMPANY", "MARKET", "COMPETITION", "FINANCIAL", "TRADE"],
    "POLICY_DRIVER": ["POLICY", "GOVERNMENT", "REGULATION", "LAW", "GEOPOLITICS"],
    "GEOPOLITICAL_DRIVER": ["GEOPOLITICS", "POLICY", "COUNTRY", "MILITARY", "TRADE_ROUTE"],
    "ACTOR_MOTIVATION": ["COMPANY", "ACTOR_PROFILE", "COMPETITION", "DECISION_HISTORY", "STRATEGY"],
    "FUTURE_CONSEQUENCES": ["IMPACT", "SIGNAL", "TREND", "SCENARIO"],
    "RISK_ANALYSIS": ["RISK_FACTOR", "VULNERABILITY", "CHOKE_POINT", "LIABILITY", "SIGNAL"],
    "OPPORTUNITY_ANALYSIS": ["ADVANTAGE", "SYNERGY", "MARKET_ENTRY", "TREND", "FINANCIAL"],
    "CUSTOM": ["CONCEPT", "EVENT", "ORGANIZATION"]
}

CATEGORY_LEXICON = {
    "POLICY": {"policy", "regulation", "law", "act", "legislation", "bill", "mandate", "tariff", "subsidy", "ban", "reform", "decree", "directive"},
    "COMPANY": {"corp", "inc", "ltd", "co", "company", "corporation", "firm", "enterprise", "logistics", "shipping", "manufacturer", "adani", "cochin port authority"},
    "COMPETITION": {"rival", "compete", "competitor", "competition", "rivalry", "market share", "alternative", "duopoly", "monopoly"},
    "MARKET": {"price", "demand", "supply", "volume", "traffic", "cargo", "tonnage", "capacity", "trade", "market", "sector"},
    "LOGISTICS": {"port", "route", "rail", "shipping", "freight", "transit", "vessel", "infrastructure", "choke point", "canal", "terminal", "warehouse"},
    "FINANCIAL": {"financial", "investment", "capital", "revenue", "profit", "valuation", "cost", "debt", "leverage", "funding"},
    "TRADE": {"trade", "export", "import", "tariff", "cargo", "flow", "shipment"},
    "GOVERNMENT": {"government", "ministry", "minister", "state", "public", "official", "agency"},
    "REGULATION": {"regulation", "regulatory", "compliance", "rules", "oversight"},
    "LAW": {"law", "legal", "court", "judge", "constitution"},
    "GEOPOLITICS": {"geopolitical", "foreign", "alliance", "sanctions", "influence", "sovereignty", "diplomatic", "state", "bilateral", "regional"},
    "COUNTRY": {"india", "china", "usa", "us", "uk", "russia", "nation", "country", "state"},
    "MILITARY": {"military", "defense", "naval", "army", "navy", "force", "security", "conflict"},
    "TRADE_ROUTE": {"route", "lane", "choke point", "strait", "canal", "corridor", "transit"},
    "ACTOR_PROFILE": {"ceo", "founder", "chairman", "board", "executive", "profile", "leader"},
    "DECISION_HISTORY": {"history", "track record", "past", "decision", "acquisition", "purchase", "deal"},
    "STRATEGY": {"strategy", "strategic", "objective", "plan", "goal", "expansion", "growth"},
    "IMPACT": {"impact", "effect", "consequence", "outcome", "winner", "loser"},
    "SIGNAL": {"signal", "warning", "early", "indicator", "trend", "alert"},
    "TREND": {"trend", "forecast", "projection", "growth", "rise", "fall", "shift"},
    "SCENARIO": {"scenario", "analysis", "case", "simulation", "outcome"},
    "RISK_FACTOR": {"risk", "threat", "danger", "hazard", "exposure", "vulnerability"},
    "VULNERABILITY": {"vulnerability", "weakness", "exposure", "fragility"},
    "CHOKE_POINT": {"choke point", "bottleneck", "strait", "canal", "narrow"},
    "LIABILITY": {"liability", "debt", "obligation", "suit", "fine", "penalty"},
    "ADVANTAGE": {"advantage", "upside", "benefit", "strength", "edge", "opportunity"},
    "SYNERGY": {"synergy", "integration", "consolidation", "efficiency", "saving"},
    "MARKET_ENTRY": {"entry", "penetration", "expansion", "launch", "acquire", "acquisition"}
}

GOAL_TYPE_PREFERRED_ENTITY_TYPES = {
    "ROOT_CAUSE": {"EVENT", "POLICY", "COMPANY"},
    "ECONOMIC_DRIVER": {"COMPANY", "SECTOR"},
    "POLICY_DRIVER": {"POLICY"},
    "GEOPOLITICAL_DRIVER": {"COUNTRY", "POLICY"},
    "ACTOR_MOTIVATION": {"PERSON", "COMPANY"},
    "FUTURE_CONSEQUENCES": {"EVENT", "CONCEPT"},
    "RISK_ANALYSIS": {"EVENT", "CONCEPT"},
    "OPPORTUNITY_ANALYSIS": {"EVENT", "CONCEPT"},
    "CUSTOM": set(),
    # Legacy compatibility mapping
    "ECONOMIC_IMPACT": {"COMPANY", "SECTOR"},
    "GEOPOLITICAL_IMPACT": {"COUNTRY", "POLICY"},
    "POLICY_ANALYSIS": {"POLICY"},
    "ACTOR_ANALYSIS": {"PERSON", "COMPANY"},
    "FUTURE_SCENARIOS": {"EVENT", "CONCEPT"},
}

# Completion score dimension weights
COMPLETION_WEIGHTS = {
    "evidence_gathered": 0.25,
    "research_coverage": 0.20,
    "connected_concepts": 0.15,
    "supporting_signals": 0.15,
    "supporting_impacts": 0.15,
    "causal_chain_depth": 0.10,
}

# Completion targets (denominators for normalization)
COMPLETION_TARGETS = {
    "evidence_gathered": 10,
    "connected_concepts": 15,
    "supporting_signals": 5,
    "supporting_impacts": 5,
    "causal_chain_depth": 4,
}

STALL_THRESHOLD = 3  # cycles with < 0.05 progress → PAUSED


# ---------------------------------------------------------------------------
# Interface 1: Keyword Extraction
# ---------------------------------------------------------------------------

def extract_keywords(goal_question: str) -> list[str]:
    """Extract meaningful keywords from a goal question.

    Deterministic implementation: lowercase, tokenize, remove stop words.
    Future LLM insertion point: semantic key-phrase extraction.
    """
    tokens = re.findall(r"[a-z]{3,}", goal_question.lower())
    keywords = [t for t in tokens if t not in _STOP_WORDS]
    # Deduplicate while preserving order
    seen = set()
    result = []
    for kw in keywords:
        if kw not in seen:
            seen.add(kw)
            result.append(kw)
    return result


# ---------------------------------------------------------------------------
# Interface 2: Goal Relevance Scoring
# ---------------------------------------------------------------------------

def compute_goal_relevance(
    db: Session,
    lead_entity: str,
    lead_entity_type: str,
    lead_source_node_id: int,
    goal: InvestigationGoal,
) -> float:
    """Compute how relevant a lead is to the active investigation goal.

    Returns a bonus in range [0.0, 0.35].

    Deterministic implementation: keyword overlap + type alignment + proximity.
    Future LLM insertion point: semantic similarity between goal question and lead context.
    """
    # Step 1: Keyword Overlap (max 0.15)
    lead_tokens = set(re.findall(r"[a-z]{3,}", lead_entity.lower()))
    goal_tokens = set(goal.keywords) if goal.keywords else set()

    if not lead_tokens or not goal_tokens:
        keyword_overlap = 0.0
    else:
        intersection = len(lead_tokens & goal_tokens)
        union = len(lead_tokens | goal_tokens)
        keyword_overlap = (intersection / union) * 0.15 if union > 0 else 0.0

    # Step 2: Type Alignment (max 0.10)
    preferred = GOAL_TYPE_PREFERRED_ENTITY_TYPES.get(goal.goal_type, set())
    type_alignment = 0.10 if lead_entity_type in preferred else 0.0

    # Step 3: Evidence Proximity (max 0.10)
    # Walk from lead_source_node_id toward goal.origin_node_id
    proximity = 0.0
    proximity_map = {0: 0.10, 1: 0.07, 2: 0.04, 3: 0.02}
    current_id = lead_source_node_id
    for depth in range(4):
        if current_id == goal.origin_node_id:
            proximity = proximity_map[depth]
            break
        parent = db.scalar(select(Node.parent_node_id).where(Node.id == current_id))
        if parent is None:
            break
        current_id = parent

    return round(keyword_overlap + type_alignment + proximity, 4)


# ---------------------------------------------------------------------------
# Interface 3: Completion Score Computation
# ---------------------------------------------------------------------------

def _find_goal_related_nodes(db: Session, goal: InvestigationGoal) -> list[int]:
    """Find all node IDs that are related to this goal."""
    related_ids = set()

    # 1. Descendants of origin_node
    queue = [goal.origin_node_id]
    while queue:
        nid = queue.pop()
        related_ids.add(nid)
        children = db.execute(
            select(Node.id).where(Node.parent_node_id == nid)
        ).scalars().all()
        queue.extend(children)

    # 2. Nodes whose entity overlaps with goal keywords (Jaccard >= 0.30)
    goal_tokens = set(goal.keywords) if goal.keywords else set()
    if goal_tokens:
        all_nodes = db.execute(select(Node.id, Node.entity)).all()
        for nid, entity in all_nodes:
            if not entity:
                continue
            node_tokens = set(re.findall(r"[a-z]{3,}", entity.lower()))
            if not node_tokens:
                continue
            jaccard = len(node_tokens & goal_tokens) / len(node_tokens | goal_tokens)
            if jaccard >= 0.30:
                related_ids.add(nid)

    return list(related_ids)


def compute_completion_score(db: Session, goal: InvestigationGoal) -> float:
    """Compute how much of the investigation goal has been answered.

    Returns a float in [0.0, 1.0].

    Deterministic implementation: weighted composite of 6 evidence dimensions.
    Future LLM insertion point: evaluate whether evidence actually answers the question.
    """
    related_node_ids = _find_goal_related_nodes(db, goal)
    if not related_node_ids:
        return 0.0

    goal_tokens = set(goal.keywords) if goal.keywords else set()

    # Dimension 1: Evidence Gathered
    researched_count = db.scalar(
        select(func.count(Node.id))
        .where(Node.id.in_(related_node_ids))
        .where(Node.research_status == "completed")
    ) or 0
    evidence = min(researched_count / COMPLETION_TARGETS["evidence_gathered"], 1.0)

    # Dimension 2: Research Coverage (what fraction of keywords appear as node entities)
    if goal_tokens:
        entities_in_graph = db.execute(
            select(Node.entity).where(Node.id.in_(related_node_ids))
        ).scalars().all()
        covered = set()
        for entity in entities_in_graph:
            if entity:
                for kw in goal_tokens:
                    if kw in entity.lower():
                        covered.add(kw)
        coverage = len(covered) / len(goal_tokens)
    else:
        coverage = 0.0

    # Dimension 3: Connected Concepts (edges between related nodes)
    edge_count = db.scalar(
        select(func.count(Edge.id))
        .where(Edge.from_node_id.in_(related_node_ids))
        .where(Edge.to_node_id.in_(related_node_ids))
    ) or 0
    connected = min(edge_count / COMPLETION_TARGETS["connected_concepts"], 1.0)

    # Dimension 4: Supporting Signals
    signal_count = db.scalar(
        select(func.count(Signal.id)).where(Signal.node_id.in_(related_node_ids))
    ) or 0
    signals = min(signal_count / COMPLETION_TARGETS["supporting_signals"], 1.0)

    # Dimension 5: Supporting Impacts
    impact_count = db.scalar(
        select(func.count(Impact.id)).where(Impact.node_id.in_(related_node_ids))
    ) or 0
    impacts = min(impact_count / COMPLETION_TARGETS["supporting_impacts"], 1.0)

    # Dimension 6: Causal Chain Depth
    max_depth = db.scalar(
        select(func.max(Node.expansion_depth)).where(Node.id.in_(related_node_ids))
    ) or 0
    depth_score = min(max_depth / COMPLETION_TARGETS["causal_chain_depth"], 1.0)

    # Weighted sum
    score = (
        evidence * COMPLETION_WEIGHTS["evidence_gathered"]
        + coverage * COMPLETION_WEIGHTS["research_coverage"]
        + connected * COMPLETION_WEIGHTS["connected_concepts"]
        + signals * COMPLETION_WEIGHTS["supporting_signals"]
        + impacts * COMPLETION_WEIGHTS["supporting_impacts"]
        + depth_score * COMPLETION_WEIGHTS["causal_chain_depth"]
    )

    return round(min(score, 1.0), 3)


# ---------------------------------------------------------------------------
# Interface 4: Stopping Logic
# ---------------------------------------------------------------------------

def check_goal_state(db: Session, goal: InvestigationGoal) -> str:
    """Evaluate whether the goal should CONTINUE, PAUSE, COMPLETE, or ABANDON.

    Called after each expansion cycle.
    """
    old_score = goal.completion_score
    new_score = compute_completion_score(db, goal)
    goal.completion_score = new_score

    # COMPLETED
    if new_score >= 0.90:
        goal.status = "completed"
        goal.completed_at = datetime.now(timezone.utc)
        db.commit()
        logger.info("Goal %d COMPLETED (score=%.2f)", goal.id, new_score)
        return "COMPLETED"

    # ABANDONED (budget exhausted)
    if goal.expansions_used >= goal.expansion_budget:
        goal.status = "abandoned"
        db.commit()
        logger.info("Goal %d ABANDONED (budget exhausted: %d/%d)", goal.id, goal.expansions_used, goal.expansion_budget)
        return "ABANDONED"

    # STALL detection
    delta = abs(new_score - old_score)
    if delta < 0.05:
        goal.stall_counter += 1
    else:
        goal.stall_counter = 0

    if goal.stall_counter >= STALL_THRESHOLD:
        goal.status = "paused"
        db.commit()
        logger.info("Goal %d PAUSED (stalled for %d cycles)", goal.id, goal.stall_counter)
        return "PAUSED"

    db.commit()
    return "CONTINUE"


# ---------------------------------------------------------------------------
# Interface 5: Sub-Goal Generation
# ---------------------------------------------------------------------------

def generate_sub_goals(
    db: Session,
    goal: InvestigationGoal,
    research_profile: dict[str, Any],
) -> list[InvestigationGoal]:
    """Generate sub-goals deterministically from a research profile.

    Maps profile sections to goal types. Only creates sub-goals if
    the parent goal's completion is < 0.75 and sub-goal count < 5.

    Deterministic implementation: section-to-type mapping.
    Future LLM insertion point: LLM reads profile and proposes investigation questions.
    """
    if goal.completion_score >= 0.75:
        return []

    # Count existing sub-goals
    existing_count = db.scalar(
        select(func.count(InvestigationGoal.id))
        .where(InvestigationGoal.parent_goal_id == goal.id)
    ) or 0

    if existing_count >= 5:
        return []

    max_new = 5 - existing_count
    budget_per_sub = max(1, (goal.expansion_budget - goal.expansions_used) // (max_new + 1))
    created = []

    # Map causal predecessors → ROOT_CAUSE sub-goals
    causal_chain = research_profile.get("causal_chain", {})
    for cause in causal_chain.get("caused_by", [])[:1]:
        if len(created) >= max_new:
            break
        # Extract entity from "[relation] Node N: Entity" format
        entity = cause.split(":")[-1].strip() if ":" in cause else cause
        question = f"What role does {entity} play in {goal.goal_question}?"
        sub = InvestigationGoal(
            parent_goal_id=goal.id,
            origin_node_id=goal.origin_node_id,
            goal_type="ROOT_CAUSE",
            goal_question=question,
            keywords=extract_keywords(question) + list(goal.keywords or []),
            expansion_budget=budget_per_sub,
            priority=goal.priority + 1,
        )
        db.add(sub)
        created.append(sub)

    # Map primary_sectors → ECONOMIC_IMPACT sub-goals
    impact_profile = research_profile.get("impact_profile", {})
    for sector in impact_profile.get("primary_sectors", [])[:1]:
        if len(created) >= max_new:
            break
        question = f"How does {sector} relate to {goal.goal_question}?"
        sub = InvestigationGoal(
            parent_goal_id=goal.id,
            origin_node_id=goal.origin_node_id,
            goal_type="ECONOMIC_IMPACT",
            goal_question=question,
            keywords=extract_keywords(question) + list(goal.keywords or []),
            expansion_budget=budget_per_sub,
            priority=goal.priority + 1,
        )
        db.add(sub)
        created.append(sub)

    # Map research leads with POLICY type → POLICY_ANALYSIS sub-goals
    for lead in research_profile.get("research_leads", [])[:3]:
        if len(created) >= max_new:
            break
        if lead.get("type") == "POLICY":
            question = f"How does {lead['entity']} connect to {goal.goal_question}?"
            sub = InvestigationGoal(
                parent_goal_id=goal.id,
                origin_node_id=goal.origin_node_id,
                goal_type="POLICY_ANALYSIS",
                goal_question=question,
                keywords=extract_keywords(question) + list(goal.keywords or []),
                expansion_budget=budget_per_sub,
                priority=goal.priority + 1,
            )
            db.add(sub)
            created.append(sub)

    if created:
        db.commit()
        logger.info("Created %d sub-goals for goal %d", len(created), goal.id)

    return created


# ---------------------------------------------------------------------------
# Part 1: Goal Intent Classification
# ---------------------------------------------------------------------------

def classify_goal_intent(question: str) -> str:
    """Classify the goal question into one of the supported intents deterministically.

    Order of tie resolution: ROOT_CAUSE -> ACTOR_MOTIVATION -> ECONOMIC_DRIVER -> CUSTOM
    """
    q_lower = question.lower()

    # 1. Syntactic prefix check
    for intent, prefixes in INTENT_PREFIXES.items():
        for prefix in prefixes:
            if q_lower.startswith(prefix):
                return intent

    # 2. Lexical keyword score check
    scores = {intent: 0 for intent in INTENT_LEXICON}
    tokens = set(re.findall(r"[a-z]{3,}", q_lower))

    for intent, lexicon in INTENT_LEXICON.items():
        overlap = tokens & lexicon
        scores[intent] = len(overlap)

    # Get max score
    max_score = max(scores.values())
    if max_score > 0:
        candidates = [intent for intent, score in scores.items() if score == max_score]
        # Tie resolution
        for tie_breaker in ["ROOT_CAUSE", "ACTOR_MOTIVATION", "ECONOMIC_DRIVER"]:
            if tie_breaker in candidates:
                return tie_breaker
        return candidates[0]

    return "CUSTOM"


# ---------------------------------------------------------------------------
# Part 2: Knowledge Requirement Helper
# ---------------------------------------------------------------------------

def categorize_entity_or_lead(entity_name: str, entity_type: str, reason: str = "") -> set[str]:
    """Categorize an entity or lead into one or more Knowledge Categories deterministically."""
    categories = set()
    e_name_lower = entity_name.lower()
    e_type_upper = entity_type.upper()
    reason_lower = reason.lower() if reason else ""

    # 1. Type mapping
    if e_type_upper in CATEGORY_LEXICON:
        categories.add(e_type_upper)
    if e_type_upper == "COMPANY" or e_type_upper == "ORGANIZATION":
        categories.add("COMPANY")
    if e_type_upper == "PERSON":
        categories.add("ACTOR_PROFILE")
    if e_type_upper == "LOCATION" or e_type_upper == "COUNTRY":
        categories.add("COUNTRY")

    # 2. Lexical patterns
    for category, keywords in CATEGORY_LEXICON.items():
        # Check entity name
        for kw in keywords:
            if kw in e_name_lower:
                categories.add(category)
                break
        else:
            # Check reason/context
            if reason_lower:
                for kw in keywords:
                    if f" {kw} " in f" {reason_lower} " or reason_lower.startswith(kw) or reason_lower.endswith(kw):
                        categories.add(category)
                        break

    # Ensure fallback if empty
    if not categories:
        categories.add("CONCEPT")

    return categories


# ---------------------------------------------------------------------------
# Part 3: Lead Contribution Score
# ---------------------------------------------------------------------------

def compute_lead_contribution(
    db: Session,
    lead_entity: str,
    lead_entity_type: str,
    lead_reason: str,
    lead_source_node_id: int,
    goal: InvestigationGoal,
) -> float:
    """Compute how much a lead contributes to answering the active goal.

    CS(L, G) = 0.50 * A_cat + 0.30 * R_kw + 0.20 * P_struct
    """
    # 1. Category Alignment (A_cat)
    req_cats = REQUIRED_KNOWLEDGE_CATEGORIES.get(goal.goal_type, REQUIRED_KNOWLEDGE_CATEGORIES["CUSTOM"])
    if not req_cats:
        cat_alignment = 0.0
    else:
        lead_cats = categorize_entity_or_lead(lead_entity, lead_entity_type, lead_reason)
        matched = lead_cats & set(req_cats)
        
        # Calculate base match fraction
        cat_alignment = len(matched) / len(req_cats)
        
        # Prioritize core required pillar match by boosting if at least one is matched
        if len(matched) > 0:
            cat_alignment = max(cat_alignment, 0.50 + 0.10 * len(matched))
            cat_alignment = min(cat_alignment, 1.0)

    # 2. Keyword Overlap (R_kw)
    lead_text = f"{lead_entity} {lead_reason}".lower()
    lead_tokens = set(re.findall(r"[a-z]{3,}", lead_text))
    goal_tokens = set(goal.keywords) if goal.keywords else set()

    if not lead_tokens or not goal_tokens:
        keyword_overlap = 0.0
    else:
        keyword_overlap = len(lead_tokens & goal_tokens) / len(lead_tokens | goal_tokens)

    # 3. Structural Proximity (P_struct)
    distance = 999
    if lead_source_node_id == goal.origin_node_id:
        distance = 0
    else:
        current_id = lead_source_node_id
        for depth in range(1, 10):
            parent = db.scalar(select(Node.parent_node_id).where(Node.id == current_id))
            if parent is None:
                break
            if parent == goal.origin_node_id:
                distance = depth
                break
            current_id = parent

    if distance == 999:
        proximity = 0.0
    else:
        import math
        proximity = math.exp(-0.5 * distance)

    score = (0.50 * cat_alignment) + (0.30 * keyword_overlap) + (0.20 * proximity)
    return round(score, 4)


# ---------------------------------------------------------------------------
# Part 4: Goal Knowledge Coverage
# ---------------------------------------------------------------------------

def get_goal_knowledge_coverage(db: Session, goal: InvestigationGoal) -> dict[str, Any]:
    """Track which required knowledge categories are already covered and which are missing."""
    req_cats = REQUIRED_KNOWLEDGE_CATEGORIES.get(goal.goal_type, REQUIRED_KNOWLEDGE_CATEGORIES["CUSTOM"])
    related_node_ids = _find_goal_related_nodes(db, goal)

    covered_cats = set()
    if related_node_ids:
        nodes = db.execute(select(Node).where(Node.id.in_(related_node_ids))).scalars().all()
        for node in nodes:
            node_cats = categorize_entity_or_lead(node.entity, node.entity_type or "topic", node.description or "")
            covered_cats.update(node_cats)

    covered_required = covered_cats & set(req_cats)
    missing_required = set(req_cats) - covered_required

    return {
        "required": list(req_cats),
        "covered": list(covered_required),
        "missing": list(missing_required)
    }


# ---------------------------------------------------------------------------
# Part 5: Investigation Gap Analysis
# ---------------------------------------------------------------------------

def compute_knowledge_gap_score(db: Session, goal: InvestigationGoal) -> float:
    """Compute the Knowledge Gap Score: fraction of required categories that are missing."""
    coverage = get_goal_knowledge_coverage(db, goal)
    req = coverage["required"]
    missing = coverage["missing"]

    if not req:
        return 0.0
    return round(len(missing) / len(req), 4)


def generate_gap_report(db: Session, goal: InvestigationGoal) -> dict[str, Any]:
    """Generate a structured gap analysis report for a goal."""
    coverage = get_goal_knowledge_coverage(db, goal)
    gap_score = compute_knowledge_gap_score(db, goal)

    missing = coverage["missing"]
    under_researched = []
    covered = coverage["covered"]

    related_node_ids = _find_goal_related_nodes(db, goal)
    nodes_by_cat = {cat: 0 for cat in coverage["required"]}

    if related_node_ids:
        nodes = db.execute(select(Node).where(Node.id.in_(related_node_ids))).scalars().all()
        for node in nodes:
            node_cats = categorize_entity_or_lead(node.entity, node.entity_type or "topic", node.description or "")
            for cat in coverage["required"]:
                if cat in node_cats:
                    nodes_by_cat[cat] += 1

    for cat, count in nodes_by_cat.items():
        if cat in covered and count < 2:
            under_researched.append(cat)

    # Check edges between each pair of covered required categories to find causal gaps
    causal_gaps = []
    cat_nodes = {cat: [] for cat in coverage["required"]}
    if related_node_ids:
        nodes = db.execute(select(Node).where(Node.id.in_(related_node_ids))).scalars().all()
        for node in nodes:
            node_cats = categorize_entity_or_lead(node.entity, node.entity_type or "topic", node.description or "")
            for cat in coverage["required"]:
                if cat in node_cats:
                    cat_nodes[cat].append(node.id)

    req_list = coverage["required"]
    for i, cat1 in enumerate(req_list):
        for cat2 in req_list[i+1:]:
            if cat1 in covered and cat2 in covered:
                nodes1 = cat_nodes[cat1]
                nodes2 = cat_nodes[cat2]
                edge_exists = db.scalar(
                    select(func.count(Edge.id))
                    .where(
                        or_(
                            and_(Edge.from_node_id.in_(nodes1), Edge.to_node_id.in_(nodes2)),
                            and_(Edge.from_node_id.in_(nodes2), Edge.to_node_id.in_(nodes1))
                        )
                    )
                ) or 0
                if edge_exists == 0:
                    causal_gaps.append(f"{cat1} <-> {cat2}")

    return {
        "goal_id": goal.id,
        "goal_question": goal.goal_question,
        "goal_type": goal.goal_type,
        "knowledge_gap_score": gap_score,
        "missing_pillars": missing,
        "under_researched_pillars": under_researched,
        "causal_gaps": causal_gaps
    }
