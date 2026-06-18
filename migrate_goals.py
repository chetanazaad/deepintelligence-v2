import sqlite3

conn = sqlite3.connect("news_intelligence.db")
cur = conn.cursor()

# Check existing tables
cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = [r[0] for r in cur.fetchall()]
print("Tables:", tables)

# Check if goal_id column exists in lead_queue
if "lead_queue" in tables:
    cur.execute("PRAGMA table_info(lead_queue)")
    cols = [r[1] for r in cur.fetchall()]
    print("lead_queue columns:", cols)
    if "goal_id" not in cols:
        cur.execute("ALTER TABLE lead_queue ADD COLUMN goal_id INTEGER REFERENCES investigation_goals(id) ON DELETE SET NULL")
        conn.commit()
        print("Added goal_id column to lead_queue")
    else:
        print("goal_id already exists")

# Verify investigation_goals table exists
if "investigation_goals" in tables:
    cur.execute("PRAGMA table_info(investigation_goals)")
    cols = [r[1] for r in cur.fetchall()]
    print("investigation_goals columns:", cols)
else:
    print("investigation_goals table NOT found - will be created by create_tables()")

conn.close()
