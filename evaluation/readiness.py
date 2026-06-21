def compute_system_readiness(
    entity_quality: float,
    assessment_quality: float,
    explanation_quality: float,
    scenario_quality: float,
    goal_quality: float
) -> dict:
    """Compute overall System Readiness Score (SRS).

    Weights:
      - Entity Quality: 20%
      - Assessment Quality: 30%
      - Explanation Quality: 20%
      - Scenario Quality: 15%
      - Goal Quality: 15%

    Returns:
        dict: containing overall_score (0-100) and classification
    """
    # Weights sum to 1.0
    srs = (
        0.20 * entity_quality +
        0.30 * assessment_quality +
        0.20 * explanation_quality +
        0.15 * scenario_quality +
        0.15 * goal_quality
    )

    # Convert to 0-100 scale
    score = round(srs * 100, 2)

    # Classify readiness
    if score >= 85:
        classification = "PRODUCTION_READY"
    elif score >= 70:
        classification = "STABLE"
    elif score >= 50:
        classification = "LEARNING"
    else:
        classification = "EXPERIMENTAL"

    return {
        "overall_score": score,
        "classification": classification
    }
