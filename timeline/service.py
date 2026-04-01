from collections import defaultdict
from datetime import datetime, timezone
from hashlib import sha256
from re import findall, search, IGNORECASE

from utils.datetime_helpers import ensure_utc

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from models.news_intelligence import (
    CleanedNews,
    ClusterNewsMap,
    Edge,
    EventCluster,
    Node,
    RawNews,
    TimelineEntry,
)


# ---------------------------------------------------------------------------
# Causal vocabulary — each keyword has a strength weight (0.0–1.0)
# ---------------------------------------------------------------------------

_CAUSAL_CUES: dict[str, dict[str, float]] = {
    # Strong explicit causation
    "caused": 0.95, "because": 0.90, "due": 0.85, "result": 0.80,
    "driven": 0.80, "blamed": 0.85, "attributed": 0.80,
    "stemmed": 0.75, "prompted": 0.80, "resulting": 0.80,
    "consequence": 0.85, "aftermath": 0.75, "outcome": 0.70,
    "fueled": 0.75, "sparked": 0.80,
}

_TRIGGER_CUES: dict[str, float] = {
    # Event initiation
    "launch": 0.70, "announce": 0.65, "surge": 0.75, "spike": 0.75,
    "breakout": 0.80, "sanction": 0.80, "impose": 0.75, "ban": 0.80,
    "declare": 0.75, "unveil": 0.65, "introduce": 0.60, "initiate": 0.70,
    "escalate": 0.80, "trigger": 0.85, "ignite": 0.80,
}

_REACTION_CUES: dict[str, float] = {
    # Response/reaction patterns
    "response": 0.75, "reacting": 0.70, "retaliate": 0.85,
    "counter": 0.70, "backlash": 0.75, "fallout": 0.80,
    "aftermath": 0.75, "ripple": 0.70, "spillover": 0.70,
    "respond": 0.70, "condemn": 0.65, "protest": 0.65,
}

_CONTEXT_CUES: dict[str, float] = {
    # Weaker contextual links
    "before": 0.40, "ahead": 0.40, "prior": 0.45, "prelude": 0.50,
    "amid": 0.45, "following": 0.55, "after": 0.50, "since": 0.45,
    "meanwhile": 0.35, "during": 0.40, "alongside": 0.35,
}

# Combined lookup for quick classification
_ALL_CUES = {
    **{k: ("causes", v) for k, v in _CAUSAL_CUES.items()},
    **{k: ("triggers", v) for k, v in _TRIGGER_CUES.items()},
    **{k: ("reacts_to", v) for k, v in _REACTION_CUES.items()},
    **{k: ("precedes", v) for k, v in _CONTEXT_CUES.items()},
}

# Minimum edge confidence to persist (filters out noise)
_EDGE_CONFIDENCE_THRESHOLD = 0.30


# ---------------------------------------------------------------------------
# General helpers
# ---------------------------------------------------------------------------

def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _extract_terms(text: str) -> set[str]:
    return {token.lower() for token in findall(r"[a-zA-Z0-9]{3,}", text or "")}


# ---------------------------------------------------------------------------
# Entity extraction & normalization (rule-based, no ML/LLM)
# ---------------------------------------------------------------------------

_GENERIC_WORDS = {
    "how", "what", "why", "this", "that", "which", "where", "when", "who",
    "the", "and", "for", "are", "but", "not", "you", "all", "can", "had",
    "her", "was", "one", "our", "out", "has", "his", "its", "new", "now",
    "old", "see", "way", "may", "day", "too", "use", "say", "says", "said",
    "will", "each", "make", "like", "long", "look", "many", "some", "than",
    "them", "then", "were", "been", "have", "from", "with", "they", "been",
    "more", "over", "such", "also", "back", "into", "year", "your", "just",
    "know", "take", "come", "could", "after", "about", "would", "being",
    "their", "there", "other", "should", "world", "still", "think", "here",
    "much", "only", "well", "very", "even", "most", "news", "report",
    "update", "breaking", "latest", "first", "last", "top", "big", "key",
    "live", "watch", "read", "full", "set", "gets", "got",
}

# Priority: 3 = location/region, 2 = country, 1 = organization
_KNOWN_ENTITIES: dict[str, tuple[str, int]] = {
    # --- Countries (priority 2) ---
    "india": ("India", 2), "iran": ("Iran", 2), "iraq": ("Iraq", 2),
    "israel": ("Israel", 2), "china": ("China", 2), "russia": ("Russia", 2),
    "ukraine": ("Ukraine", 2), "pakistan": ("Pakistan", 2),
    "japan": ("Japan", 2), "germany": ("Germany", 2), "france": ("France", 2),
    "brazil": ("Brazil", 2), "turkey": ("Turkey", 2), "egypt": ("Egypt", 2),
    "syria": ("Syria", 2), "yemen": ("Yemen", 2), "lebanon": ("Lebanon", 2),
    "afghanistan": ("Afghanistan", 2), "mexico": ("Mexico", 2),
    "canada": ("Canada", 2), "australia": ("Australia", 2),
    "indonesia": ("Indonesia", 2), "nigeria": ("Nigeria", 2),
    "bangladesh": ("Bangladesh", 2), "taiwan": ("Taiwan", 2),
    "myanmar": ("Myanmar", 2), "sudan": ("Sudan", 2),
    "ethiopia": ("Ethiopia", 2), "colombia": ("Colombia", 2),
    "argentina": ("Argentina", 2), "venezuela": ("Venezuela", 2),
    "libya": ("Libya", 2), "somalia": ("Somalia", 2),
    "thailand": ("Thailand", 2), "vietnam": ("Vietnam", 2),
    "korea": ("Korea", 2), "nepal": ("Nepal", 2),
    "sri lanka": ("Sri Lanka", 2),
    # --- Abbreviation countries (priority 2) ---
    "uae": ("United Arab Emirates", 2),
    "us": ("United States", 2), "usa": ("United States", 2),
    "uk": ("United Kingdom", 2),
    # --- Locations/Regions (priority 3 — highest) ---
    "hormuz": ("Strait of Hormuz", 3), "strait": ("Strait of Hormuz", 3),
    "gaza": ("Gaza", 3), "kashmir": ("Kashmir", 3),
    "crimea": ("Crimea", 3), "tibet": ("Tibet", 3),
    "arctic": ("Arctic", 3), "sahel": ("Sahel", 3),
    "balkans": ("Balkans", 3), "caucasus": ("Caucasus", 3),
    "gulf": ("Persian Gulf", 3), "persian": ("Persian Gulf", 3),
    "mediterranean": ("Mediterranean", 3), "atlantic": ("Atlantic", 3),
    "pacific": ("Pacific", 3), "suez": ("Suez Canal", 3),
    "taiwan strait": ("Taiwan Strait", 3),
    "south china sea": ("South China Sea", 3),
    "red sea": ("Red Sea", 3),
    "black sea": ("Black Sea", 3),
    "middle east": ("Middle East", 3),
    "southeast asia": ("Southeast Asia", 3),
    "central asia": ("Central Asia", 3),
    "east africa": ("East Africa", 3),
    "west africa": ("West Africa", 3),
    "europe": ("Europe", 3), "asia": ("Asia", 3), "africa": ("Africa", 3),
    "americas": ("Americas", 3),
    # --- Organizations (priority 1) ---
    "un": ("United Nations", 1), "nato": ("NATO", 1),
    "opec": ("OPEC", 1), "who": ("WHO", 1), "imf": ("IMF", 1),
    "fed": ("Federal Reserve", 1), "ecb": ("ECB", 1),
    "rbi": ("RBI", 1), "brics": ("BRICS", 1),
    "asean": ("ASEAN", 1), "g7": ("G7", 1), "g20": ("G20", 1),
    "hamas": ("Hamas", 1), "hezbollah": ("Hezbollah", 1),
    "taliban": ("Taliban", 1), "isis": ("ISIS", 1),
    "pentagon": ("Pentagon", 1), "kremlin": ("Kremlin", 1),
    "congress": ("US Congress", 1), "parliament": ("Parliament", 1),
    "supreme court": ("Supreme Court", 1),
    "white house": ("White House", 1),
}


def _extract_entities_from_text(text: str) -> list[tuple[str, int]]:
    """Extract entities from text using known-entity lookup + capitalized-word heuristic.

    Returns list of (normalized_entity, priority) tuples, deduplicated.
    """
    if not text:
        return []

    text_lower = text.lower()
    found: dict[str, int] = {}  # normalized_name -> priority

    # 1. Check multi-word known entities first (longest match)
    for key, (normalized, priority) in _KNOWN_ENTITIES.items():
        if " " in key and key in text_lower:
            if normalized not in found or priority > found[normalized]:
                found[normalized] = priority

    # 2. Check single-word known entities
    words_lower = findall(r"[a-z0-9]+", text_lower)
    for word in words_lower:
        if word in _KNOWN_ENTITIES:
            normalized, priority = _KNOWN_ENTITIES[word]
            if normalized not in found or priority > found[normalized]:
                found[normalized] = priority

    # 3. Capitalized-word heuristic for unknown entities (from original text)
    #    Captures proper nouns like "Modi", "Biden", "Samsung", "Gazprom"
    cap_words = findall(r"\b[A-Z][a-z]{2,}\b", text)
    for word in cap_words:
        wl = word.lower()
        if wl not in _GENERIC_WORDS and wl not in _KNOWN_ENTITIES:
            if word not in found:
                found[word] = 0  # priority 0 = generic proper noun

    return [(name, pri) for name, pri in found.items()]


def _select_primary_entity(entities: list[tuple[str, int]]) -> str:
    """Select the best entity by priority: location(3) > country(2) > org(1) > proper noun(0)."""
    if not entities:
        return "event"
    entities.sort(key=lambda x: x[1], reverse=True)
    return entities[0][0]


def _format_multi_entity(entities: list[tuple[str, int]], max_entities: int = 3) -> str:
    """Format multiple entities as comma-separated string, priority-sorted.

    Stored in the existing Node.entity field (no schema change).
    """
    if not entities:
        return "event"
    entities.sort(key=lambda x: x[1], reverse=True)
    unique = []
    seen = set()
    for name, _ in entities:
        if name not in seen:
            seen.add(name)
            unique.append(name)
            if len(unique) >= max_entities:
                break
    return ", ".join(unique)


def _entity_from_topic(topic: str) -> str:
    """Legacy wrapper — extract entity from topic string only.

    Used as fallback when no titles are available.
    """
    entities = _extract_entities_from_text(topic)
    if entities:
        return _format_multi_entity(entities)
    # Fallback: first non-generic word
    words = [w for w in topic.split() if w.strip().lower() not in _GENERIC_WORDS]
    return words[0] if words else "event"


def _extract_entity_for_node(main_topic: str, titles: list[str]) -> str:
    """Extract the best entity from titles + topic combined.

    Pipeline:
    1. Extract from all titles (richest source)
    2. Extract from cluster main_topic
    3. Merge, deduplicate, and priority-rank
    4. Return top entities as comma-separated string
    """
    all_entities: dict[str, int] = {}

    # Titles are the richest entity source
    for title in titles:
        for name, priority in _extract_entities_from_text(title):
            if name not in all_entities or priority > all_entities[name]:
                all_entities[name] = priority

    # Also check cluster topic
    for name, priority in _extract_entities_from_text(main_topic):
        if name not in all_entities or priority > all_entities[name]:
            all_entities[name] = priority

    entity_list = [(name, pri) for name, pri in all_entities.items()]

    if entity_list:
        return _format_multi_entity(entity_list)

    # Fallback to cluster topic's first non-generic word
    return _entity_from_topic(main_topic)


def _build_timeline_group_id(anchor_cluster_key: str) -> str:
    digest = sha256(anchor_cluster_key.encode("utf-8")).hexdigest()[:12]
    return f"timeline-{digest}"


# ---------------------------------------------------------------------------
# Causal Event Extraction & Backward Inference (New Intelligence Paradigm)
# ---------------------------------------------------------------------------

_CAUSAL_PATTERNS = [
    # (Regex pattern, Relation Type, Position of Effect vs Cause)
    (r"\b(due to)\b", "caused_by", "left_effect"),
    (r"\b(because of)\b", "caused_by", "left_effect"),
    (r"\b(after)\b", "precedes", "left_effect"),
    (r"\b(following)\b", "precedes", "left_effect"),
    (r"\b(triggered by)\b", "triggered_by", "left_effect"),
    (r"\b(sparked by)\b", "triggered_by", "left_effect"),
    (r"\b(amid)\b", "enables", "left_effect"),
    (r"\b(as a result of)\b", "caused_by", "left_effect"),
    (r"\b(caused by)\b", "caused_by", "left_effect"),
    (r"\b(leads to)\b", "causes", "right_effect"),
    (r"\b(sparks)\b", "triggers", "right_effect"),
    (r"\b(triggers)\b", "triggers", "right_effect"),
    (r"\b(escalates)\b", "amplifies", "right_effect"),
    (r"\b(prompts)\b", "triggers", "right_effect"),
    (r"\b(fuels)\b", "amplifies", "right_effect"),
]

def _extract_causal_primitives(titles: list[str], entity: str) -> dict[str, str | float]:
    """Extract causal primitives (Actor, Target, Trigger, Predecessor) from text.
    Works backward from surfaced news to find the true causal chain.
    """
    best_extraction = None
    best_score = 0.0

    for title in titles:
        for pattern, rel_type, format_dir in _CAUSAL_PATTERNS:
            match = search(pattern, title, IGNORECASE)
            if match:
                trigger_phrase = match.group(1).lower()
                left_part = title[:match.start()].strip()
                right_part = title[match.end():].strip()

                if format_dir == "left_effect":
                    event = left_part
                    predecessor = right_part
                else:
                    event = right_part
                    predecessor = left_part
                
                # We prioritize titles that contain the extracted entity
                score = 0.8
                if entity and entity.lower() in event.lower():
                    score += 0.15
                
                if score > best_score:
                    best_score = score
                    best_extraction = {
                        "event": event or title,
                        "actor": entity,
                        "trigger_phrase": trigger_phrase,
                        "predecessor": predecessor,
                        "confidence": score,
                        "raw_evidence": title
                    }
                    
    if not best_extraction:
        # Fallback: Treat the whole string as an atomic event with no known predecessor
        best_title = titles[0] if titles else "Unknown Event"
        best_extraction = {
            "event": best_title,
            "actor": entity,
            "trigger_phrase": "N/A",
            "predecessor": "N/A",
            "confidence": 0.5,
            "raw_evidence": best_title
        }
        
    return best_extraction

def _format_node_description(primitives: dict[str, str | float], all_titles: list[str]) -> str:
    """Format structured debug output mapping the causal logic.
    Provides explainability constraints for the intelligence graph.
    """
    lines = [
        f"EVENT: {primitives.get('event', '')}",
        f"ACTOR: {primitives.get('actor', '')}",
        f"TRIGGER: {primitives.get('trigger_phrase', 'N/A')}",
        f"PREDECESSOR: {primitives.get('predecessor', 'N/A')}",
        f"CONFIDENCE: {float(primitives.get('confidence', 0.0)):.2f}",
        f"EVIDENCE: \"{primitives.get('raw_evidence', '')}\"",
        "---",
        "ORIGINAL TITLES:",
    ]
    lines.extend([f"- {t}" for t in all_titles[:3]])
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Event-type classification (improved)
# ---------------------------------------------------------------------------

def _event_type(text: str) -> str:
    """Classify node event type using strongest matching cue word."""
    terms = _extract_terms(text)
    best_type = "update"
    best_weight = 0.0

    for term in terms:
        if term in _ALL_CUES:
            relation, weight = _ALL_CUES[term]
            if weight > best_weight:
                best_weight = weight
                if relation == "causes":
                    best_type = "causal"
                elif relation == "triggers":
                    best_type = "trigger"
                elif relation == "reacts_to":
                    best_type = "reaction"
                else:
                    best_type = "update"

    return best_type


# ---------------------------------------------------------------------------
# Multi-signal causal edge scoring
# ---------------------------------------------------------------------------

def _keyword_signal(from_text: str, to_text: str) -> tuple[str, float]:
    """Detect the strongest causal keyword and its relation type.

    Checks BOTH node descriptions independently to capture directional cues.
    Returns (relation_type, keyword_strength).
    """
    from_terms = _extract_terms(from_text)
    to_terms = _extract_terms(to_text)

    best_relation = "precedes"
    best_strength = 0.0

    # Check from_node (the more recent event) for reaction/result cues
    for term in from_terms:
        if term in _ALL_CUES:
            relation, weight = _ALL_CUES[term]
            if weight > best_strength:
                best_strength = weight
                best_relation = relation

    # Check to_node (the older event) for trigger/causal cues
    for term in to_terms:
        if term in _ALL_CUES:
            relation, weight = _ALL_CUES[term]
            if weight > best_strength:
                best_strength = weight
                best_relation = relation

    return best_relation, best_strength


def _temporal_signal(from_ts: datetime | None, to_ts: datetime | None) -> float:
    """Score based on time gap — closer events have stronger causal link.

    Uses exponential decay: full strength at 0 days, ~0 at 30+ days.
    """
    if from_ts is None or to_ts is None:
        return 0.15  # unknown — small default

    gap_days = abs((ensure_utc(from_ts) - ensure_utc(to_ts)).total_seconds()) / 86400.0
    return max(0.0, 1.0 - (gap_days / 30.0))


def _entity_signal(from_text: str, to_text: str) -> float:
    """Jaccard similarity of entity terms — shared entities suggest connection."""
    from_terms = _extract_terms(from_text)
    to_terms = _extract_terms(to_text)
    if not from_terms or not to_terms:
        return 0.0

    intersection = len(from_terms & to_terms)
    union = len(from_terms | to_terms)
    return intersection / union if union else 0.0


def _compute_edge_score(
    from_node: Node,
    to_node: Node,
) -> tuple[str, float]:
    """Compute backward-link reasoning from effect (from_node) to cause (to_node).

    1. EXPLICIT: Checks for backward trigger phrases parsed from the text.
    2. IMPLICIT: Infers missing predecessors using temporal + semantic + entity logic.
    """
    from_text = from_node.description or ""
    to_text = to_node.description or ""
    
    # 1. Parse structured debug output to check for explicit predecessors
    pred_match = search(r"PREDECESSOR:\s*(.+)", from_text)
    predecessor = pred_match.group(1).strip() if pred_match else "N/A"
    
    if predecessor != "N/A" and not predecessor.startswith("[INFERRED]") and len(predecessor) > 4:
        # Does the older node's content describe this predecessor event?
        pred_terms = _extract_terms(predecessor)
        to_terms = _extract_terms(to_text)
        
        overlap_factor = len(pred_terms & to_terms)
        trigger_match = search(r"TRIGGER:\s*(.+)", from_text)
        trigger_phrase = trigger_match.group(1).strip() if trigger_match else ""
        
        # We also check if the older node contains the predecessor string directly
        direct_match = predecessor.lower() in to_text.lower()
        
        if overlap_factor > 1 or direct_match:
            # We found a strong back-link matching the text's stated cause!
            rel = "causes"
            if trigger_phrase in ["triggered by", "sparked by"]:
                rel = "triggers"
            elif trigger_phrase in ["after", "following"]:
                rel = "precedes"
            elif trigger_phrase in ["amid"]:
                rel = "enables"
            
            temporal = _temporal_signal(from_node.timestamp, to_node.timestamp)
            confidence = min(0.99, 0.70 + (0.1 * overlap_factor) + (0.15 * temporal))
            return rel, round(confidence, 3)

    # 2. IMPLICIT Causal Inference (Multi-Node / Multi-Hop Bridging)
    relation_type, keyword_strength = _keyword_signal(from_text, to_text)
    temporal = _temporal_signal(from_node.timestamp, to_node.timestamp)
    entity_val = _entity_signal(from_text, to_text)
    
    # If no explicit predecessor is stated, actively try to infer one
    if predecessor == "N/A" or predecessor.startswith("[INFERRED]"):
        # If they share entities strongly and occurred closely in time
        if entity_val > 0.05 and temporal > 0.5:
            is_logical_flow = False
            inferred_rel = relation_type
            
            # Check Semantic Similarity / Causal Directionality (Action -> Reaction)
            if from_node.event_type in ["reaction", "update"] and to_node.event_type in ["trigger", "causal"]:
                is_logical_flow = True
                inferred_rel = "causes"
            elif keyword_strength > 0.6:
                is_logical_flow = True
                
            if is_logical_flow:
                confidence = min(0.90, 0.40 + (0.2 * keyword_strength) + (0.25 * temporal) + (0.2 * entity_val))
                
                # Minimum threshold for confirming an implicit deduction
                if confidence > 0.45:
                    to_event_match = search(r"EVENT:\s*(.+)", to_text)
                    to_event = to_event_match.group(1).strip() if to_event_match else "Previous linked event"
                    
                    # Replace PREDECESSOR and TRIGGER with inferred links & debug info!
                    new_pred_text = f"PREDECESSOR: [INFERRED] {to_event}"
                    new_trig_text = f"TRIGGER: [IMPLICIT LOGIC: temporal={temporal:.2f}, entity={entity_val:.2f}]"
                    
                    # Update Node metadata inline (persisted via db.commit at end of build_timeline)
                    from_node.description = from_text.replace(
                        f"PREDECESSOR: {predecessor}", new_pred_text
                    ).replace(
                        "TRIGGER: N/A", new_trig_text
                    )
                    
                    return inferred_rel, round(confidence, 3)

    # 3. Fallback Filter (Drop basic keyword noise, heavily penalize random topical overlap)
    confidence = (0.2 * keyword_strength) + (0.15 * temporal) + (0.15 * entity_val)
    if confidence < 0.35:
        confidence = 0.0 # prune weak connections that aren't causal
        
    return relation_type, round(confidence, 3)


# ---------------------------------------------------------------------------
# Anchor scoring (improved)
# ---------------------------------------------------------------------------

def _compute_anchor_score(
    frequency: int,
    source_count: int,
    recency_score: float,
    main_topic: str,
) -> float:
    """Weighted anchor score: source diversity and keyword importance
    matter more than raw frequency.

    Formula:
      frequency × 1.5
    + source_count × 2.0   (multi-source = higher signal)
    + recency × 1.0
    + keyword_importance × 1.0  (trigger/causal cues boost)
    """
    topic_terms = _extract_terms(main_topic)
    keyword_importance = 0.0
    for term in topic_terms:
        if term in _ALL_CUES:
            _, weight = _ALL_CUES[term]
            keyword_importance = max(keyword_importance, weight)

    return (
        frequency * 1.5
        + source_count * 2.0
        + recency_score
        + keyword_importance * 1.0
    )


# ---------------------------------------------------------------------------
# Batch node creation (eliminates N+1 lookups)
# ---------------------------------------------------------------------------

def _batch_get_or_create_nodes(
    db: Session,
    cluster_infos: list[dict[str, object]],
    titles_by_cluster: dict[int, list[str]],
    anchor_cluster_id: int,
) -> list[Node]:
    """Load or create nodes for all clusters in a single batch.

    1) Loads all existing nodes for the cluster set in one query.
    2) Creates missing nodes and updates existing ones.
    3) Returns the full node list.
    """
    cluster_ids = [int(info["cluster_id"]) for info in cluster_infos]

    # Single query: load all existing nodes for these clusters
    existing_nodes = {
        node.cluster_id: node
        for node in db.execute(
            select(Node).where(Node.cluster_id.in_(cluster_ids))
        ).scalars().all()
    }

    nodes: list[Node] = []
    for info in cluster_infos:
        cluster_id = int(info["cluster_id"])
        titles = titles_by_cluster.get(cluster_id, [])

        main_topic = str(info["main_topic"])
        entity = _extract_entity_for_node(main_topic, titles)
        
        # Replace article-summary logic with causal primitive extraction
        primitives = _extract_causal_primitives(titles, entity)
        description = _format_node_description(primitives, titles)
        
        # Classify the primary event type based on the extracted event and cause strings
        event_type = _event_type(f"{primitives['event']} {primitives['predecessor']}")
        timestamp = info["latest_ts"] if isinstance(info["latest_ts"], datetime) else None
        is_anchor = (cluster_id == anchor_cluster_id)

        node = existing_nodes.get(cluster_id)
        if node is None:
            node = Node(
                cluster_id=cluster_id,
                entity=entity,
                entity_type="topic",
                event_type=event_type,
                description=description,
                timestamp=timestamp,
                impact_type="neutral",
                confidence_score=0.7,
                is_anchor=is_anchor,
            )
            db.add(node)
        else:
            node.entity = entity
            node.entity_type = "topic"
            node.event_type = event_type
            node.description = description
            node.timestamp = timestamp
            node.impact_type = "neutral"
            node.confidence_score = 0.7
            node.is_anchor = is_anchor

        nodes.append(node)

    db.flush()
    return nodes


# ---------------------------------------------------------------------------
# Main timeline builder
# ---------------------------------------------------------------------------

def build_timeline(db: Session, max_clusters: int = 200) -> dict[str, int | str]:
    """
    Deterministic timeline builder with causal intelligence.

    Steps:
    1) Score clusters by frequency + source diversity + recency + keyword importance
    2) Choose anchor via weighted scoring (not just frequency)
    3) Batch-create/update nodes for scored clusters
    4) Build causal edges with 3-signal confidence scoring
    5) Enforce temporal causality + minimum confidence gate
    6) Order timeline with causal-aware positioning
    """
    # ---- Step 1: Aggregate cluster statistics ----
    stats_rows = db.execute(
        select(
            EventCluster.id,
            EventCluster.cluster_key,
            EventCluster.main_topic,
            func.count(ClusterNewsMap.id).label("frequency"),
            func.max(func.coalesce(RawNews.published_at, RawNews.created_at)).label("latest_ts"),
            func.count(func.distinct(RawNews.source)).label("source_count"),
        )
        .join(ClusterNewsMap, ClusterNewsMap.cluster_id == EventCluster.id)
        .join(CleanedNews, CleanedNews.id == ClusterNewsMap.cleaned_news_id)
        .join(RawNews, RawNews.id == CleanedNews.raw_news_id)
        .group_by(EventCluster.id, EventCluster.cluster_key, EventCluster.main_topic)
    ).all()

    if not stats_rows:
        return {
            "anchor_cluster_id": "",
            "nodes_created_or_updated": 0,
            "edges_created": 0,
            "edges_filtered": 0,
            "timeline_entries": 0,
        }

    now = _now_utc()
    cluster_stats: list[dict[str, object]] = []
    for row in stats_rows[:max_clusters]:
        latest = row.latest_ts
        if isinstance(latest, datetime):
            age_days = max((now - ensure_utc(latest)).total_seconds() / 86400.0, 0.0)
        else:
            age_days = 365.0

        recency_score = max(0.0, 30.0 - age_days) / 30.0

        # ---- Step 2: Improved anchor scoring ----
        score = _compute_anchor_score(
            frequency=int(row.frequency),
            source_count=int(row.source_count),
            recency_score=recency_score,
            main_topic=row.main_topic or "",
        )

        cluster_stats.append(
            {
                "cluster_id": row.id,
                "cluster_key": row.cluster_key,
                "main_topic": row.main_topic,
                "frequency": int(row.frequency),
                "source_count": int(row.source_count),
                "latest_ts": latest if isinstance(latest, datetime) else None,
                "score": score,
            }
        )

    cluster_stats.sort(
        key=lambda x: (
            float(x["score"]),
            int(x["frequency"]),
            int(x["source_count"]),
            x["latest_ts"] or datetime.min.replace(tzinfo=timezone.utc),
        ),
        reverse=True,
    )

    anchor_cluster_id = int(cluster_stats[0]["cluster_id"])
    anchor_cluster_key = str(cluster_stats[0]["cluster_key"])

    # ---- Batch-fetch titles for all clusters in one query ----
    all_cluster_ids = [int(info["cluster_id"]) for info in cluster_stats]
    title_rows = db.execute(
        select(ClusterNewsMap.cluster_id, RawNews.title)
        .join(CleanedNews, CleanedNews.id == ClusterNewsMap.cleaned_news_id)
        .join(RawNews, RawNews.id == CleanedNews.raw_news_id)
        .where(ClusterNewsMap.cluster_id.in_(all_cluster_ids))
        .order_by(ClusterNewsMap.cluster_id, RawNews.created_at.desc())
    ).all()

    titles_by_cluster: dict[int, list[str]] = defaultdict(list)
    for row in title_rows:
        if len(titles_by_cluster[row[0]]) < 3:
            titles_by_cluster[row[0]].append(row[1])

    # ---- Step 3: Batch node creation ----
    nodes = _batch_get_or_create_nodes(
        db=db,
        cluster_infos=cluster_stats,
        titles_by_cluster=titles_by_cluster,
        anchor_cluster_id=anchor_cluster_id,
    )

    # ---- Chronological order: newest first ----
    nodes.sort(key=lambda n: n.timestamp or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    anchor_index = next((i for i, n in enumerate(nodes) if n.cluster_id == anchor_cluster_id), 0)
    if anchor_index != 0:
        anchor_node = nodes.pop(anchor_index)
        nodes.insert(0, anchor_node)

    # ---- Step 4+5: Causal edge creation with scoring + filtering ----
    current_node_ids = [n.id for n in nodes]
    existing_edges = {
        (from_id, to_id)
        for from_id, to_id in db.execute(
            select(Edge.from_node_id, Edge.to_node_id)
            .where(Edge.from_node_id.in_(current_node_ids))
        ).all()
    }

    edges_created = 0
    edges_filtered = 0

    for i in range(len(nodes)):
        from_node = nodes[i]
        # Compare with nearby nodes (window of 5 for efficiency)
        for j in range(i + 1, min(i + 6, len(nodes))):
            to_node = nodes[j]

            # Skip if edge already exists (any relation)
            if (from_node.id, to_node.id) in existing_edges:
                continue

            # Temporal causality: from_node should be more recent
            if (
                from_node.timestamp is not None
                and to_node.timestamp is not None
                and from_node.timestamp < to_node.timestamp
            ):
                continue  # cause can't happen after effect

            # Multi-signal scoring
            relation, confidence = _compute_edge_score(from_node, to_node)

            # Confidence gate
            if confidence < _EDGE_CONFIDENCE_THRESHOLD:
                edges_filtered += 1
                continue

            db.add(
                Edge(
                    from_node_id=from_node.id,
                    to_node_id=to_node.id,
                    relation_type=relation,
                    confidence_score=confidence,
                )
            )
            existing_edges.add((from_node.id, to_node.id))
            edges_created += 1

    # ---- Step 6: Persist timeline entries ----
    timeline_group_id = _build_timeline_group_id(anchor_cluster_key)
    db.execute(delete(TimelineEntry).where(TimelineEntry.timeline_group_id == timeline_group_id))

    for position, node in enumerate(nodes):
        db.add(
            TimelineEntry(
                node_id=node.id,
                position_index=position,
                timeline_group_id=timeline_group_id,
            )
        )

    db.commit()
    return {
        "anchor_cluster_id": anchor_cluster_id,
        "nodes_created_or_updated": len(nodes),
        "edges_created": edges_created,
        "edges_filtered": edges_filtered,
        "timeline_entries": len(nodes),
        "timeline_group_id": timeline_group_id,
    }
