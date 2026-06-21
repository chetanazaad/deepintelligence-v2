import re

BLACKLIST = {
    "benchmark_seed",
    "expansion",
    "temp_node",
    "undefined",
    "null",
    "five",
    "test",
    "sample"
}

# A simple list of standard stopwords
STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for", "with", 
    "by", "of", "about", "as", "from", "into", "through", "during", "including",
    "until", "against", "among", "throughout", "despite", "towards", "upon", "concerning"
}

def evaluate_entity(entity: str) -> dict:
    """Evaluate quality of a given entity string.

    Returns:
        dict: EntityQualityResult containing entity, score, confidence, and accepted fields.
    """
    if not entity or not isinstance(entity, str):
        return {
            "entity": str(entity),
            "score": 0.0,
            "confidence": "LOW",
            "accepted": False
        }

    cleaned = entity.strip().lower()

    # Rule 1: Reject tokens shorter than 3 characters
    if len(cleaned) < 3:
        return {
            "entity": entity,
            "score": 0.0,
            "confidence": "LOW",
            "accepted": False
        }

    # Rule 2: Reject pure numbers
    if cleaned.isdigit() or re.match(r'^[\d\.\-\+]+$', cleaned):
        return {
            "entity": entity,
            "score": 0.0,
            "confidence": "LOW",
            "accepted": False
        }

    # Rule 3: Reject blacklist tokens / internal variables
    if cleaned in BLACKLIST:
        return {
            "entity": entity,
            "score": 0.0,
            "confidence": "LOW",
            "accepted": False
        }

    # Rule 4: Stopword filter
    if cleaned in STOPWORDS:
        return {
            "entity": entity,
            "score": 0.1,
            "confidence": "LOW",
            "accepted": False
        }

    # If it passes basic rejection rules, compute a quality score
    # Score is higher for capitalized proper nouns, multiple words (compounds)
    score = 0.5
    
    # Capitalization check (indicates proper nouns)
    if entity[0].isupper():
        score += 0.2
    
    # Word count check (compound nouns like 'Wall Street' or 'Adani Ports' carry higher specificity)
    words = cleaned.split()
    if len(words) > 1:
        score += 0.2
    
    # Clip score
    score = min(max(score, 0.0), 1.0)
    
    # Classify confidence
    if score >= 0.85:
        confidence = "HIGH"
    elif score >= 0.50:
        confidence = "MEDIUM"
    else:
        confidence = "LOW"

    return {
        "entity": entity,
        "score": score,
        "confidence": confidence,
        "accepted": True
    }
