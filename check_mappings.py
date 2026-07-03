# check_mappings.py
import sqlite3

conn = sqlite3.connect("apparel_aggregator.db")
total = conn.execute("SELECT COUNT(*) FROM franchise_mappings").fetchone()[0]
print(f"Total franchise_mappings rows: {total}")

sample = conn.execute(
    "SELECT keyword, franchise_name FROM franchise_mappings "
    "WHERE franchise_name IN ('Dark Souls', 'The Legend of Zelda', 'Mass Effect') "
    "ORDER BY franchise_name"
).fetchall()
for kw, fr in sample:
    print(f"  {kw!r} -> {fr}")
conn.close()