import sqlite3
from database.config import get_settings

db_url = get_settings().database_url
db_path = db_url.replace('sqlite:///', '')

print('Path:', db_path)
conn = sqlite3.connect(db_path)
try:
    conn.execute("ALTER TABLE nodes ADD COLUMN expansion_depth INTEGER DEFAULT 0 NOT NULL")
    conn.execute("ALTER TABLE nodes ADD COLUMN parent_node_id INTEGER REFERENCES nodes(id) ON DELETE SET NULL")
    conn.execute("ALTER TABLE nodes ADD COLUMN research_status VARCHAR(50) DEFAULT 'not_started' NOT NULL")
    conn.execute("ALTER TABLE nodes ADD COLUMN expansion_status VARCHAR(50) DEFAULT 'not_started' NOT NULL")
    conn.execute("ALTER TABLE nodes ADD COLUMN importance_score FLOAT DEFAULT 0.5 NOT NULL")
    conn.execute("ALTER TABLE nodes ADD COLUMN research_summary TEXT")
    conn.execute("ALTER TABLE nodes ADD COLUMN expanded_at DATETIME")
    conn.commit()
    print("Altered nodes table.")
except Exception as e:
    print("Exception altering:", e)

conn.close()
