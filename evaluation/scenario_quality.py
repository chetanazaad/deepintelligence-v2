import re

BLACKLIST_PHRASES = {
    "positive market synergies",
    "mutually beneficial outcomes",
    "expansion accelerates",
    "moderate gains continue"
}

CONFLICT_CATEGORIES = {"war", "conflict", "tension", "clash", "sanction", "election"}

def evaluate_scenario(scenarios: dict, category: str = "") -> float:
    """Evaluate quality of predictive scenarios.

    Args:
        scenarios: dict containing 'likely', 'possible', 'unlikely' keys.
        category: str representing the event category/domain.

    Returns:
        float: ScenarioQualityScore (0.0 to 1.0)
    """
    if not scenarios or not isinstance(scenarios, dict):
        return 0.0

    score = 0.7
    cat_lower = (category or "").strip().lower()

    # Get combined text to scan for quality
    scenario_texts = [str(v).lower() for v in scenarios.values()]
    combined_text = " ".join(scenario_texts)

    # 1. Boilerplate / Blacklist phrase check
    for phrase in BLACKLIST_PHRASES:
        if phrase in combined_text:
            score -= 0.3

    # 2. Reject mismatching scenarios
    # e.g., "positive market synergies" should not be applied to conflict contexts
    if "synergies" in combined_text or "gains" in combined_text:
        if any(conflict in cat_lower for conflict in CONFLICT_CATEGORIES) or "conflict" in cat_lower or "sanction" in cat_lower:
            score -= 0.4

    # 3. Scenario diversity check (ensure the texts are not identical or near-identical)
    likely_txt = scenarios.get("likely", "").strip()
    possible_txt = scenarios.get("possible", "").strip()
    
    if likely_txt and possible_txt and likely_txt == possible_txt:
        score -= 0.3

    # 4. Length check (ensure scenarios are detailed and explanatory)
    for text in scenario_texts:
        if len(text.split()) < 5:
            score -= 0.1

    return min(max(score, 0.0), 1.0)
