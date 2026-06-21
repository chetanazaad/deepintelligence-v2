import random
from datetime import datetime, timezone
from database.session import SessionLocal, create_tables
from models.news_intelligence import SystemReadiness, ValidationSnapshot

# ... rest of file ...
from evaluation.entity_quality import evaluate_entity
from evaluation.goal_quality import evaluate_goal
from evaluation.scenario_quality import evaluate_scenario
from evaluation.explanation_quality import evaluate_explanation
from evaluation.failures import run_failure_analysis
from evaluation.readiness import compute_system_readiness

BENCHMARK_DATASET = [
    {
        "category": "Geopolitics",
        "headline": "U.S.-Iran Peace Talks Open in Switzerland Amid Rising Tension Over Proxies",
        "entities": ["US", "Iran", "Switzerland"],
        "goals": ["What geopolitical consequences may arise from renewed Iran-US negotiations?"],
        "scenarios": {"likely": "Interim sanctions relief is traded for regional proxy containment.", "possible": "Talks collapse after new drone strike allegations.", "unlikely": "Comprehensive nuclear treaty signed within a week."}
    },
    {
        "category": "Corporate acquisitions",
        "headline": "Tech Giant Acquires AI Infrastructure Startup to Expand GPU Hosting Capabilities",
        "entities": ["Tech Giant", "AI Startup"],
        "goals": ["What economic drivers led to the GPU hosting startup acquisition?"],
        "scenarios": {"likely": "Acquirer secures cloud computing dominance.", "possible": "Acquisition faces regulatory antitrust review.", "unlikely": "Startup founders resign immediately."}
    },
    {
        "category": "Financial markets",
        "headline": "Federal Reserve Hints at Policy Rate Cut Following Inflation Rate Slowdown",
        "entities": ["Federal Reserve", "US Treasury"],
        "goals": ["How does the treasury yield curve shift react to rate cut hints?"],
        "scenarios": {"likely": "Markets rally on rate cut expectations.", "possible": "Yield curve remains inverted temporarily.", "unlikely": "Reserve hikes rates by 50bps instead."}
    },
    {
        "category": "Energy",
        "headline": "OPEC+ Decides on Crude Oil Production Cuts to Offset Global Demand Reduction",
        "entities": ["OPEC+", "Crude Oil"],
        "goals": ["What market impacts will OPEC+ output restrictions generate?"],
        "scenarios": {"likely": "Oil prices stabilize above baseline.", "possible": "Non-OPEC producers expand supply market share.", "unlikely": "Crude oil demand surges to record highs."}
    },
    {
        "category": "Government policy",
        "headline": "European Union Mandates Localized Cloud Storage Regulations for Citizen Data Protection",
        "entities": ["European Union", "Data Protection Authority"],
        "goals": ["What policy drivers led to the localized EU storage mandates?"],
        "scenarios": {"likely": "US tech firms construct regional data centers.", "possible": "Small scale providers exit EU compliance market.", "unlikely": "EU repeals cloud localization act entirely."}
    },
    {
        "category": "Technology",
        "headline": "Solid State Battery Manufacturer Announces Breakthrough in Energy Density Metric",
        "entities": ["Battery Corp", "Lithium"],
        "goals": ["How does density scaling affect EV battery logistics?"],
        "scenarios": {"likely": "Automakers sign preliminary integration contracts.", "possible": "Mass production delayed due to lithium shortages.", "unlikely": "Solid state tech replaced by hydrogen fuel cells."}
    },
    {
        "category": "Elections",
        "headline": "Coalition Cabinet Formed Following General Election Shift in Coalition Alliance",
        "entities": ["Cabinet", "Prime Minister"],
        "goals": ["What are the policy impacts of the new coalition government?"],
        "scenarios": {"likely": "Legislative compromise slows tax reform bills.", "possible": "Alliance splits over budget allocations.", "unlikely": "Early snap elections called within 3 months."}
    },
    {
        "category": "Social issues",
        "headline": "Labor Union Announces Union Strikes Across Major Logistics Shipping Hubs",
        "entities": ["Union Alliance", "Shipping Hub"],
        "goals": ["What are the logistics consequences of ongoing labor disputes?"],
        "scenarios": {"likely": "Supply chains experience shipping delays.", "possible": "Arbitration brokers interim contract extension.", "unlikely": "Logistics hubs permanently automate all loading."}
    },
    {
        "category": "Healthcare",
        "headline": "FDA Grants Accelerated Clearance Status to Rare Disease Gene Therapy Treatment",
        "entities": ["FDA", "Biotech Inc"],
        "goals": ["What are the market impacts of accelerated gene therapy clearance?"],
        "scenarios": {"likely": "Biotech firm achieves first-mover advantages.", "possible": "Insurers contest premium drug pricing policies.", "unlikely": "FDA revokes approval due to late stage side effects."}
    },
    {
        "category": "Infrastructure",
        "headline": "High Speed Rail Network Project Expansion Receives Official Budget Approvals",
        "entities": ["Transit Corp", "Rail Authority"],
        "goals": ["How does transit network expansion affect regional growth?"],
        "scenarios": {"likely": "Suburban industrial logistics hubs expand.", "possible": "Construction costs exceed original budget parameters.", "unlikely": "Rail line abandoned halfway due to financial constraints."}
    }
]

def run_benchmark(num_items: int = 20) -> dict:
    """Run benchmark tests on validation dataset.

    Generates system readiness, quality scores, and failure reports.
    """
    create_tables()
    db = SessionLocal()
    try:
        items = []
        # Generate the requested count of items by cycling or selecting random variations
        for i in range(num_items):
            base_item = BENCHMARK_DATASET[i % len(BENCHMARK_DATASET)]
            items.append(base_item)

        entity_scores = []
        goal_scores = []
        scenario_scores = []
        explanation_scores = []
        assessment_scores = []

        total_failures = []

        for idx, item in enumerate(items):
            # 1. Entity Quality
            ent_results = [evaluate_entity(ent) for ent in item["entities"]]
            avg_ent_score = sum(e["score"] for e in ent_results) / len(ent_results) if ent_results else 0.8
            entity_scores.append(avg_ent_score)

            # 2. Goal Quality
            g_score = evaluate_goal(item["goals"][0])
            goal_scores.append(g_score)

            # 3. Scenario Quality
            s_score = evaluate_scenario(item["scenarios"], item["category"])
            scenario_scores.append(s_score)

            # 4. Explanation Quality
            # Use random mock data mimicking pipeline indicators
            causal_depth = random.choice([2, 3, 4])
            evidence_count = random.choice([3, 5, 6])
            gap_count = random.choice([0, 1, 2])
            entity_refs = len(item["entities"])
            cat_coverage = 0.8
            
            exp_res = evaluate_explanation(causal_depth, evidence_count, gap_count, entity_refs, cat_coverage)
            explanation_scores.append(exp_res["score"])

            # 5. Assessment Quality (Average of others as proxy)
            ass_score = (avg_ent_score + g_score + s_score + exp_res["score"]) / 4.0
            assessment_scores.append(ass_score)

            # 6. Failure Analysis
            fail_res = run_failure_analysis(
                entity_results=ent_results,
                goal_quality_score=g_score,
                scenario_quality_score=s_score,
                explanation_quality_score=exp_res["score"],
                evidence_strength=0.7,
                scenarios=item["scenarios"],
                causal_depth=causal_depth
            )
            total_failures.extend(fail_res["failures"])

        # Compute Aggregated Averages
        avg_eq = sum(entity_scores) / len(entity_scores)
        avg_gq = sum(goal_scores) / len(goal_scores)
        avg_sq = sum(scenario_scores) / len(scenario_scores)
        avg_exq = sum(explanation_scores) / len(explanation_scores)
        avg_aq = sum(assessment_scores) / len(assessment_scores)

        # Readiness
        readiness_res = compute_system_readiness(avg_eq, avg_aq, avg_exq, avg_sq, avg_gq)

        # Save System Readiness to database
        readiness_model = SystemReadiness(
            entity_quality=avg_eq,
            assessment_quality=avg_aq,
            explanation_quality=avg_exq,
            scenario_quality=avg_sq,
            goal_quality=avg_gq,
            overall_score=readiness_res["overall_score"],
            classification=readiness_res["classification"],
            created_at=datetime.now(timezone.utc)
        )
        db.add(readiness_model)
        db.commit()

        # Count Top Failures
        failure_counts = {}
        for fail in total_failures:
            failure_counts[fail] = failure_counts.get(fail, 0) + 1

        return {
            "num_items_processed": num_items,
            "overall_readiness_score": readiness_res["overall_score"],
            "readiness_classification": readiness_res["classification"],
            "quality_metrics": {
                "entity_quality": round(avg_eq * 100, 2),
                "goal_quality": round(avg_gq * 100, 2),
                "scenario_quality": round(avg_sq * 100, 2),
                "explanation_quality": round(avg_exq * 100, 2),
                "assessment_quality": round(avg_aq * 100, 2)
            },
            "failures": failure_counts
        }

    finally:
        db.close()

if __name__ == "__main__":
    print("Running benchmark of 20 headlines...")
    res = run_benchmark(20)
    print(res)
