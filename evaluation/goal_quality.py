import re

DOMAIN_KEYWORDS = {
    "geopolitical", "economic", "policy", "actor", "motivation", "consequences",
    "financial", "market", "acquisition", "energy", "infrastructure", "regulatory"
}

def evaluate_goal(goal_question: str) -> float:
    """Evaluate quality of an investigation goal question.

    Returns:
        float: GoalQualityScore (0.0 to 1.0)
    """
    if not goal_question or not isinstance(goal_question, str):
        return 0.0

    score = 0.5
    cleaned = goal_question.strip().lower()

    # Rule 1: Specificity (Length penalty/bonus)
    words = cleaned.split()
    if len(words) < 5:
        score -= 0.2  # Vague short queries
    elif len(words) > 10:
        score += 0.15 # Detailed queries

    # Rule 2: Domain Clarity (Bonus for targeting specific dimensions)
    matches = [word for word in DOMAIN_KEYWORDS if word in cleaned]
    if len(matches) > 0:
        score += 0.20
        # Additional bonus for compound domain phrases
        if re.search(r'(geopolitical|economic|policy|financial|regulatory|actor)\s+(consequences|drivers|implications|motivations|impacts)', cleaned):
            score += 0.10

    # Rule 3: Question Quality Check
    # Penalty for generic "implications of [single word/entity]"
    if re.match(r'^what\s+are\s+the\s+implications\s+of\s+\w+\??$', cleaned):
        score -= 0.25

    # Ensure score stays in 0.0 to 1.0 range
    return min(max(score, 0.0), 1.0)
