import json
from database.session import SessionLocal
from models.news_intelligence import Node
from research.engine import execute_node_research

db = SessionLocal()
node = db.query(Node).first()
if node:
    print(f'Testing research on Node {node.id} ({node.entity})...')
    try:
        profile = execute_node_research(db, node.id)
        print(json.dumps(profile, indent=2))
        print('SUCCESS!')
    except Exception as e:
        import traceback
        traceback.print_exc()
        print('FAILED:', e)
else:
    print('No nodes found to test.')
db.close()
