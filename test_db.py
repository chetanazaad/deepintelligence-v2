import sqlite3

conn = sqlite3.connect('d:/deepdive-intelligence/news_intelligence.db')
cur = conn.cursor()
cur.execute("SELECT id, title FROM raw_news WHERE title LIKE '%Hormuz%' OR title LIKE '%UAE%' LIMIT 5;")
rows = cur.fetchall()
print("ROWS IN DB matching Hormuz or UAE:")
for r in rows:
    print(r)
