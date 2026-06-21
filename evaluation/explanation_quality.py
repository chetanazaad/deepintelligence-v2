def evaluate_explanation(
    causal_depth: int,
    evidence_count: int,
    gap_count: int,
    entity_references: int,
    category_coverage: float
) -> dict:
    """Evaluate quality of causal explanations.

    Returns:
        dict: ExplanationScore detailing score (0.0-1.0) and classification (POOR|WEAK|GOOD|STRONG)
    """
    score = 0.4

    # 1. Causal Depth check
    if causal_depth >= 4:
        score += 0.20
    elif causal_depth >= 2:
        score += 0.10
    else:
        score -= 0.15  # Penalty for extremely shallow explanations

    # 2. Evidence Usage check
    if evidence_count >= 5:
        score += 0.15
    elif evidence_count >= 2:
        score += 0.05

    # 3. Gap Awareness (acknowledging what is NOT known is crucial for intelligence quality)
    if gap_count > 0:
        score += 0.10

    # 4. Entity references specificity
    if entity_references >= 3:
        score += 0.10

    # 5. Category Coverage ratio
    score += (category_coverage * 0.15)

    # Clean score boundary
    score = min(max(score, 0.0), 1.0)

    # Classify rating
    if score >= 0.80:
        classification = "STRONG"
    elif score >= 0.60:
        classification = "GOOD"
    elif score >= 0.40:
        classification = "WEAK"
    else:
        classification = "POOR"

    return {
        "score": score,
        "classification": classification
    }
