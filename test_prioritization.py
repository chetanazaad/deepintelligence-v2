import json
from database.session import SessionLocal
from models.news_intelligence import LeadQueue, Node
from expansion.prioritization import recompute_dynamic_scores, select_top_leads
from expansion.recursive_expander import run_expansion_cycle
from sqlalchemy import select

db = SessionLocal()

# 1. Manually add some test leads to the queue to simulate research output
node = db.scalar(select(Node).limit(1))
if node:
    db.execute(LeadQueue.__table__.delete()) # Clear queue for test
    
    # High value lead
    lead1 = LeadQueue(
        source_node_id=node.id,
        entity="Test Maritime Policy",
        entity_type="POLICY",
        score_profile={"reason": "Testing"},
        base_score=0.85,
        dynamic_score=0.85,
        status="pending"
    )
    # Low value lead
    lead2 = LeadQueue(
        source_node_id=node.id,
        entity="Some Concept",
        entity_type="CONCEPT",
        score_profile={"reason": "Testing low"},
        base_score=0.20,
        dynamic_score=0.20,
        status="pending"
    )
    db.add_all([lead1, lead2])
    db.commit()

    print("--- Before Prioritization ---")
    for q in db.execute(select(LeadQueue)).scalars().all():
        print(f"Lead: {q.entity}, Base: {q.base_score}, Dynamic: {q.dynamic_score}, Status: {q.status}")
        
    print("\n--- Running Prioritization Cycle ---")
    result = run_expansion_cycle(db)
    print(json.dumps(result, indent=2))
    
    print("\n--- After Prioritization ---")
    for q in db.execute(select(LeadQueue)).scalars().all():
        print(f"Lead: {q.entity}, Base: {q.base_score}, Dynamic: {q.dynamic_score}, Status: {q.status}")

db.close()
