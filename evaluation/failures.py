from evaluation.entity_quality import BLACKLIST

def run_failure_analysis(
    entity_results: list,
    goal_quality_score: float,
    scenario_quality_score: float,
    explanation_quality_score: float,
    evidence_strength: float,
    scenarios: dict,
    causal_depth: int
) -> dict:
    """Analyze assessment and associated models to detect failure codes.

    Returns:
        dict: failure codes list and combined severity level
    """
    failures = []

    # 1. Leaked tokens check
    has_leaked = any(ent.get("entity", "").lower() in BLACKLIST for ent in entity_results)
    if has_leaked:
        failures.append("ERR_LEAKED_TOKENS")

    # 2. Entity Quality check
    low_eq = any(ent.get("score", 0.0) < 0.5 for ent in entity_results)
    if low_eq:
        failures.append("ERR_LOW_ENTITY_QUALITY")

    # 3. Poor Goal check
    if goal_quality_score < 0.4:
        failures.append("ERR_POOR_GOAL")

    # 4. Weak Scenario check
    if scenario_quality_score < 0.4:
        failures.append("ERR_WEAK_SCENARIO")

    # 5. Generic Boilerplate scenario check
    from evaluation.scenario_quality import BLACKLIST_PHRASES
    combined_scenario_text = " ".join([str(v).lower() for v in (scenarios or {}).values()])
    if any(phrase in combined_scenario_text for phrase in BLACKLIST_PHRASES):
        failures.append("ERR_GENERIC_BOILERPLATE")

    # 6. Shallow Explanation check
    if causal_depth < 2:
        failures.append("ERR_SHALLOW_EXPLANATION")

    # 7. Unsupported Assessment check
    if evidence_strength < 0.3:
        failures.append("ERR_UNSUPPORTED_ASSESSMENT")

    # Calculate overall severity based on failure count
    count = len(failures)
    if count >= 4:
        severity = "HIGH"
    elif count >= 2:
        severity = "MEDIUM"
    else:
        severity = "LOW"

    return {
        "failures": failures,
        "severity": severity
    }
