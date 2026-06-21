"""Benchmark Engine.

Manages benchmark scenarios: seeding, execution, and version comparison.
Provides deterministic reproducible evaluation of system intelligence quality.
"""

import logging
from datetime import datetime, timezone

from sqlalchemy import select, desc
from sqlalchemy.orm import Session

from models.news_intelligence import (
    BenchmarkResult,
    BenchmarkScenario,
    EvaluationSnapshot,
    InvestigationGoal,
    Node,
    Edge,
    EventCluster,
)
from expansion.goals import extract_keywords, classify_goal_intent
from expansion.recursive_expander import run_expansion_cycle
from evaluation.metrics import evaluate_goal

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pre-Defined Benchmark Scenarios
# ---------------------------------------------------------------------------

DEFAULT_SCENARIOS = [
    {
        "name": "adani_acquisition",
        "description": "Tests ROOT_CAUSE investigation: why did Adani acquire Cochin Port?",
        "goal_question": "Why did Adani acquire Cochin Port?",
        "goal_type": "ROOT_CAUSE",
        "seed_entities": ["Adani Ports", "Cochin Port", "Maritime Policy"],
        "expected_categories": ["POLICY", "COMPANY", "COMPETITION", "MARKET", "LOGISTICS"],
        "expected_min_completion": 0.50,
    },
    {
        "name": "oil_price_shock",
        "description": "Tests ROOT_CAUSE investigation: what caused an oil price spike?",
        "goal_question": "What caused the oil price spike in Q2?",
        "goal_type": "ROOT_CAUSE",
        "seed_entities": ["OPEC", "Crude Oil", "Energy Market"],
        "expected_categories": ["POLICY", "MARKET", "GEOPOLITICS", "TRADE", "FINANCIAL"],
        "expected_min_completion": 0.50,
    },
    {
        "name": "war_event",
        "description": "Tests GEOPOLITICAL_DRIVER investigation: consequences of a conflict.",
        "goal_question": "What are the geopolitical consequences of the conflict?",
        "goal_type": "GEOPOLITICAL_DRIVER",
        "seed_entities": ["Country A", "Country B", "Regional Alliance"],
        "expected_categories": ["GEOPOLITICS", "MILITARY", "POLICY", "COUNTRY", "TRADE_ROUTE"],
        "expected_min_completion": 0.40,
    },
    {
        "name": "policy_announcement",
        "description": "Tests POLICY_DRIVER investigation: impact of a new tariff.",
        "goal_question": "How does the new tariff affect trade?",
        "goal_type": "POLICY_DRIVER",
        "seed_entities": ["Tariff Act", "Commerce Ministry"],
        "expected_categories": ["POLICY", "GOVERNMENT", "REGULATION", "TRADE", "MARKET"],
        "expected_min_completion": 0.45,
    },
    {
        "name": "corporate_merger",
        "description": "Tests ECONOMIC_DRIVER investigation: who benefits from a merger?",
        "goal_question": "Who benefits from the merger?",
        "goal_type": "ECONOMIC_DRIVER",
        "seed_entities": ["Company A", "Company B", "Industry Sector"],
        "expected_categories": ["COMPANY", "MARKET", "COMPETITION", "FINANCIAL", "STRATEGY"],
        "expected_min_completion": 0.45,
    },
    {
        "name": "tech_investment",
        "description": "Tests OPPORTUNITY_ANALYSIS investigation: opportunities in a technology.",
        "goal_question": "What are the opportunities in this technology?",
        "goal_type": "OPPORTUNITY_ANALYSIS",
        "seed_entities": ["Technology X", "Venture Fund"],
        "expected_categories": ["ADVANTAGE", "SYNERGY", "MARKET_ENTRY", "TREND", "FINANCIAL"],
        "expected_min_completion": 0.40,
    },
]


def seed_default_scenarios(db: Session) -> list[BenchmarkScenario]:
    """Insert default benchmark scenarios if they don't already exist."""
    created = []
    for scenario_def in DEFAULT_SCENARIOS:
        existing = db.scalar(
            select(BenchmarkScenario).where(BenchmarkScenario.name == scenario_def["name"])
        )
        if existing:
            continue

        scenario = BenchmarkScenario(
            name=scenario_def["name"],
            description=scenario_def["description"],
            goal_question=scenario_def["goal_question"],
            goal_type=scenario_def["goal_type"],
            seed_entities=scenario_def["seed_entities"],
            expected_categories=scenario_def["expected_categories"],
            expected_min_completion=scenario_def["expected_min_completion"],
        )
        db.add(scenario)
        created.append(scenario)

    db.commit()
    logger.info("Seeded %d benchmark scenarios.", len(created))
    return created


def _ensure_cluster_exists(db: Session) -> int:
    """Ensure a benchmark cluster exists and return its ID."""
    cluster = db.scalar(
        select(EventCluster).where(EventCluster.cluster_key == "benchmark_cluster")
    )
    if not cluster:
        cluster = EventCluster(
            cluster_key="benchmark_cluster",
            main_topic="Benchmark Evaluation",
        )
        db.add(cluster)
        db.flush()
    return cluster.id


def run_benchmark(
    db: Session,
    scenario_id: int,
    system_version: str = "v1.0",
    expansion_cycles: int = 5,
) -> BenchmarkResult:
    """Execute a full benchmark: seed → goal → expand → evaluate → compare.

    1. Load BenchmarkScenario
    2. Inject seed entities as Nodes
    3. Create InvestigationGoal
    4. Run N expansion cycles
    5. Create EvaluationSnapshot
    6. Create GoalEvaluation
    7. Create BenchmarkResult with comparison to previous run
    """
    scenario = db.scalar(
        select(BenchmarkScenario).where(BenchmarkScenario.id == scenario_id)
    )
    if not scenario:
        raise ValueError(f"Benchmark scenario {scenario_id} not found")

    logger.info("Running benchmark '%s' (v%s, %d cycles)", scenario.name, system_version, expansion_cycles)

    # 1. Inject seed entities
    cluster_id = _ensure_cluster_exists(db)
    seed_nodes = []
    for entity_name in scenario.seed_entities:
        existing = db.scalar(
            select(Node).where(Node.entity == entity_name).where(Node.cluster_id == cluster_id)
        )
        if not existing:
            node = Node(
                cluster_id=cluster_id,
                entity=entity_name,
                entity_type="CONCEPT",
                event_type="benchmark_seed",
                description=f"Benchmark seed for '{scenario.name}'",
                timestamp=datetime.now(timezone.utc),
                confidence_score=0.5,
                is_anchor=True,
                importance_score=0.7,
            )
            db.add(node)
            db.flush()
            seed_nodes.append(node)
        else:
            seed_nodes.append(existing)

    # 2. Create investigation goal
    origin_node = seed_nodes[0] if seed_nodes else None
    if not origin_node:
        raise ValueError("No seed nodes could be created for benchmark")

    goal = InvestigationGoal(
        origin_node_id=origin_node.id,
        goal_type=scenario.goal_type,
        goal_question=scenario.goal_question,
        keywords=extract_keywords(scenario.goal_question),
        expansion_budget=expansion_cycles * 3,
        priority=1,
    )
    db.add(goal)
    db.commit()

    # 3. Run expansion cycles
    cycle_results = []
    for i in range(expansion_cycles):
        try:
            result = run_expansion_cycle(db)
            cycle_results.append(result)
            logger.info("Benchmark cycle %d/%d: %s", i + 1, expansion_cycles, result.get("status"))
        except Exception as e:
            logger.error("Benchmark cycle %d failed: %s", i + 1, e)

    # 4. Create snapshot (delegated to dashboard module)
    from evaluation.dashboard import create_snapshot
    snapshot = create_snapshot(db, snapshot_type="benchmark", system_version=system_version)
    snapshot.benchmark_scenario_id = scenario.id
    db.commit()

    # 5. Create goal evaluation
    goal_eval = evaluate_goal(db, goal, snapshot_id=snapshot.id)

    # 6. Compare with previous run
    previous = db.scalar(
        select(BenchmarkResult)
        .where(BenchmarkResult.scenario_id == scenario_id)
        .order_by(desc(BenchmarkResult.created_at))
        .limit(1)
    )

    comparison = None
    if previous:
        comparison = {
            "previous_version": previous.system_version,
            "completion_score": {
                "current": goal_eval.completion_score,
                "previous": previous.completion_score,
                "delta": round(goal_eval.completion_score - previous.completion_score, 4),
                "improved": goal_eval.completion_score > previous.completion_score,
            },
            "coverage_score": {
                "current": goal_eval.coverage_score,
                "previous": previous.coverage_score,
                "delta": round(goal_eval.coverage_score - previous.coverage_score, 4),
                "improved": goal_eval.coverage_score > previous.coverage_score,
            },
            "efficiency_score": {
                "current": goal_eval.efficiency_score,
                "previous": previous.efficiency_score,
                "delta": round(goal_eval.efficiency_score - previous.efficiency_score, 4),
                "improved": goal_eval.efficiency_score > previous.efficiency_score,
            },
            "explanation_score": {
                "current": goal_eval.explanation_score,
                "previous": previous.explanation_score,
                "delta": round(goal_eval.explanation_score - previous.explanation_score, 4),
                "improved": goal_eval.explanation_score > previous.explanation_score,
            },
        }
        # Determine verdict
        improvements = sum(
            1 for k in ["completion_score", "coverage_score", "efficiency_score", "explanation_score"]
            if comparison[k]["improved"]
        )
        comparison["verdict"] = "IMPROVED" if improvements >= 3 else ("MIXED" if improvements >= 2 else "REGRESSED")

    # Determine pass/fail
    passed = goal_eval.completion_score >= scenario.expected_min_completion

    result = BenchmarkResult(
        scenario_id=scenario.id,
        snapshot_id=snapshot.id,
        system_version=system_version,
        completion_score=goal_eval.completion_score,
        coverage_score=goal_eval.coverage_score,
        efficiency_score=goal_eval.efficiency_score,
        explanation_score=goal_eval.explanation_score,
        knowledge_density=snapshot.knowledge_density,
        passed=passed,
        comparison_json=comparison,
    )
    db.add(result)
    db.commit()

    logger.info(
        "Benchmark '%s' complete: completion=%.2f, passed=%s",
        scenario.name, goal_eval.completion_score, passed,
    )

    return result


def get_scenario_comparison(db: Session, scenario_id: int) -> dict:
    """Get the latest version comparison for a benchmark scenario."""
    results = db.execute(
        select(BenchmarkResult)
        .where(BenchmarkResult.scenario_id == scenario_id)
        .order_by(desc(BenchmarkResult.created_at))
        .limit(2)
    ).scalars().all()

    scenario = db.scalar(
        select(BenchmarkScenario).where(BenchmarkScenario.id == scenario_id)
    )

    if not results:
        return {"scenario": scenario.name if scenario else "unknown", "runs": 0, "comparison": None}

    current = results[0]
    payload = {
        "scenario": scenario.name if scenario else "unknown",
        "runs": len(results),
        "current_version": current.system_version,
        "current_scores": {
            "completion": current.completion_score,
            "coverage": current.coverage_score,
            "efficiency": current.efficiency_score,
            "explanation": current.explanation_score,
            "knowledge_density": current.knowledge_density,
            "passed": current.passed,
        },
    }

    if current.comparison_json:
        payload["comparison"] = current.comparison_json

    return payload
