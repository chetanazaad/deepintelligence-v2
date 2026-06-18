import json
from database.session import SessionLocal
from models.news_intelligence import Node, LeadQueue, NodeResearchProfile
from expansion.novelty import compute_novelty_score, make_knowledge_decision, calculate_loop_risk
from sqlalchemy import select

db = SessionLocal()

print("--- Testing Loop Risk ---")
# Let's say we have a lineage: Node A (Adani) -> Node B (Adani Ports) -> Node C (Adani Group)
# We will simulate this by checking calculate_loop_risk
print("Loop risk for completely unrelated entity:", calculate_loop_risk(db, "Global Maritime Policy", 1))

# Manually insert some nodes with a lineage
n1 = Node(cluster_id=1, entity="Adani", importance_score=1.0)
db.add(n1)
db.commit()

n2 = Node(cluster_id=1, entity="Adani Ports", parent_node_id=n1.id, importance_score=0.9)
db.add(n2)
db.commit()

n3 = Node(cluster_id=1, entity="Adani Logistics", parent_node_id=n2.id, importance_score=0.8)
db.add(n3)
db.commit()

print("Loop risk for 'Adani Group' starting from Adani Logistics:", calculate_loop_risk(db, "Adani Group", n3.id))

print("\n--- Testing Novelty Score ---")
# Test exact match
score, closest = compute_novelty_score(db, "Adani Ports", n1.id)
print(f"Novelty against 'Adani Ports': {score} (closest: {closest.entity if closest else None})")
print(f"Decision: {make_knowledge_decision(score)}")

# Test partial match
score, closest = compute_novelty_score(db, "Adani Port Terminals", n1.id)
print(f"Novelty against 'Adani Port Terminals': {score} (closest: {closest.entity if closest else None})")
print(f"Decision: {make_knowledge_decision(score)}")

# Test completely new
score, closest = compute_novelty_score(db, "Space Exploration Technologies", n1.id)
print(f"Novelty against 'Space Exploration Technologies': {score} (closest: {closest.entity if closest else None})")
print(f"Decision: {make_knowledge_decision(score)}")

db.close()
