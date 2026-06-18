"""Entity extraction and Node Typing heuristics.

Provides rule-based classification of entities into strong
categories: COMPANY, COUNTRY, POLICY, SECTOR, PERSON, EVENT.
"""

from collections import Counter
from re import findall, IGNORECASE

# ---------------------------------------------------------------------------
# Dictionaries
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
    "their", "there", "other", "should", "world", "still", "here", "much",
    "only", "well", "very", "even", "most", "news", "report", "update",
    "breaking", "latest", "first", "last", "top", "big", "key", "live",
    "watch", "read", "full", "set", "gets", "got", "time", "says", "told",
}

_TYPE_CUES: dict[str, list[str]] = {
    "COMPANY": [
        "corp", "corporation", "inc", "incorporated", "llc", "ltd",
        "company", "group", "holdings", "bank", "technologies", "motors",
        "airlines", "energy", "ports", "systems",
    ],
    "COUNTRY": [
        "us", "usa", "america", "uk", "britain", "china", "russia", "india",
        "france", "germany", "japan", "brazil", "canada", "mexico", "iran",
        "israel", "saudi", "arabia", "turkey", "italy", "spain", "korea",
    ],
    "POLICY": [
        "act", "law", "bill", "treaty", "agreement", "pact", "sanction",
        "sanctions", "project", "initiative", "policy", "reform", "plan",
        "directive", "regulation", "framework",
    ],
    "EVENT": [
        "summit", "conference", "election", "war", "crisis", "attack",
        "strike", "protest", "riot", "festival", "olympics", "scandal",
        "crash", "spill", "earthquake", "hurricane", "flood",
    ],
    "PERSON": [
        "president", "minister", "ceo", "director", "governor", "senator",
        "mayor", "secretary", "ambassador", "general", "dr", "mr", "mrs",
    ],
    "SECTOR": [
        "tech", "technology", "finance", "banking", "healthcare", "energy",
        "oil", "gas", "agriculture", "retail", "infrastructure", "mining",
        "defense", "military", "education", "real", "estate", "automotive",
    ],
}


# ---------------------------------------------------------------------------
# Functions
# ---------------------------------------------------------------------------

def extract_proper_entities(text: str) -> list[str]:
    """Extract capitalized phrases that act as proper entities.
    
    E.g., "The Sagarmala Project is large" -> ["Sagarmala Project"]
    """
    if not text:
        return []
        
    # Match sequences of capitalized words (ignoring starting sentence cap unless it continues)
    # Simple heuristic: 1 or more capitalized words (length >= 3)
    matches = findall(r"\b([A-Z][a-z]{2,}(?:\s+[A-Z][a-z]{2,})*)\b", text)
    
    entities = []
    for match in matches:
        match_lower = match.lower()
        if match_lower not in _GENERIC_WORDS and len(match_lower) > 3:
            entities.append(match)
            
    return entities


def classify_entity_type(entity: str) -> str:
    """Classify an entity into one of the strongly-typed categories.
    
    Defaults to 'CONCEPT' if no cues match.
    """
    words = set(entity.lower().split())
    
    # 1. Direct matches in cues
    for category, cues in _TYPE_CUES.items():
        if any(cue in words for cue in cues):
            return category
            
    # 2. Heuristics for PERSON (usually 2 words, no trailing cues)
    if len(words) == 2 and not any(w in _GENERIC_WORDS for w in words):
        return "PERSON"
        
    # Default fallback
    return "CONCEPT"


def generate_candidates_from_text(text: str, top_n: int = 5) -> list[tuple[str, str]]:
    """Extract and classify the most frequent entities from a large text block.
    
    Returns: [(entity_name, type_label), ...]
    """
    raw_entities = extract_proper_entities(text)
    if not raw_entities:
        return []
        
    # Count frequencies
    counter = Counter(raw_entities)
    
    candidates = []
    for entity, _count in counter.most_common(top_n):
        node_type = classify_entity_type(entity)
        candidates.append((entity, node_type))
        
    return candidates
