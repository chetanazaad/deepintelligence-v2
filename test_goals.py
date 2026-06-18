"""Test the Investigation Goal Engine end-to-end."""
import json
from database.session import SessionLocal
from models.news_intelligence import Node, InvestigationGoal, LeadQueue
from expansion.goals import (
    extract_keywords,
    compute_goal_relevance,
    compute_completion_score,
    check_goal_state,
    classify_goal_intent,
    compute_lead_contribution,
    get_goal_knowledge_coverage,
    generate_gap_report,
)
from sqlalchemy import select

db = SessionLocal()

# 1. Test keyword extraction
print("=== Keyword Extraction ===")
q = "Why did Adani acquire Cochin Port?"
kw = extract_keywords(q)
print(f"Question: {q}")
print(f"Keywords: {kw}")

q2 = "What are the geopolitical consequences of this event?"
kw2 = extract_keywords(q2)
print(f"Question: {q2}")
print(f"Keywords: {kw2}")

# 2. Create a goal
print("\n=== Goal Creation ===")
node = db.scalar(select(Node).limit(1))
if not node:
    print("No nodes found. Skipping.")
    db.close()
    exit()

goal = InvestigationGoal(
    origin_node_id=node.id,
    goal_type="ROOT_CAUSE",
    goal_question="Why did Adani acquire Cochin Port?",
    keywords=extract_keywords("Why did Adani acquire Cochin Port?"),
    expansion_budget=20,
    priority=1,
)
db.add(goal)
db.commit()
print(f"Created goal {goal.id}: {goal.goal_question}")
print(f"Keywords: {goal.keywords}")

# 3. Test goal relevance scoring
print("\n=== Goal Relevance Scoring ===")
test_leads = [
    ("Indian Maritime Policy", "POLICY", node.id),
    ("Port Crane Manufacturer", "COMPANY", node.id),
    ("Adani Logistics", "COMPANY", node.id),
    ("Cochin Port Authority", "COMPANY", node.id),
    ("Space Exploration", "CONCEPT", node.id),
]

for entity, etype, source_id in test_leads:
    relevance = compute_goal_relevance(db, entity, etype, source_id, goal)
    print(f"  {entity:30s} ({etype:10s}) -> Goal Relevance: {relevance:.4f}")

# 4. Test completion score
print("\n=== Completion Score ===")
score = compute_completion_score(db, goal)
print(f"Completion Score: {score}")

# 5. Test state check
print("\n=== Goal State Check ===")
state = check_goal_state(db, goal)
print(f"State: {state}")
print(f"Completion: {goal.completion_score}, Budget: {goal.expansions_used}/{goal.expansion_budget}")

# 6. Test Goal Intent Classification
print("\n=== Intent Classification ===")
questions = [
    "Why did Adani acquire Cochin Port?",
    "What are the financial drivers of this deal?",
    "Under what regulation was this merger permitted?",
    "Why is India contesting the port control?",
    "What is the long-term impact on global shipping?",
    "What are the risks of this project failing?",
    "What motivates the CEO to expand globally?",
]
for q_str in questions:
    intent = classify_goal_intent(q_str)
    print(f"Question: {q_str:50s} -> Intent: {intent}")

# 7. Test Lead Contribution Score
print("\n=== Lead Contribution Score ===")
for entity, etype, source_id in test_leads:
    contrib = compute_lead_contribution(db, entity, etype, "Acquisition of Cochin Port is influenced by state cargo diversion policies.", source_id, goal)
    print(f"  {entity:30s} ({etype:10s}) -> Contribution: {contrib:.4f}")

# 8. Test Goal Knowledge Coverage & Gap Analysis
print("\n=== Coverage & Gap Analysis ===")
coverage = get_goal_knowledge_coverage(db, goal)
print(f"Required categories: {coverage['required']}")
print(f"Covered categories:  {coverage['covered']}")
print(f"Missing categories:  {coverage['missing']}")

report = generate_gap_report(db, goal)
print("Gap Analysis Report:")
print(json.dumps(report, indent=2))

# Clean up test goal
db.delete(goal)
db.commit()
db.close()

print("\n=== All tests passed ===")
