# show_review_queue.py
"""
Prints the small list of products whose franchise couldn't be auto-confirmed
from their title text. Run this occasionally (e.g. monthly) to catch rare
lore-only terms (like "N7") that need a one-line manual mapping.
"""
import sqlite3

conn = sqlite3.connect("apparel_aggregator.db")
rows = conn.execute(
    "SELECT candidate, brand_name, sample_product, occurrences FROM franchise_review_queue "
    "ORDER BY occurrences DESC"
).fetchall()

if not rows:
    print("No items need review right now.")
else:
    print(f"{len(rows)} unresolved franchise candidate(s):\n")
    for candidate, brand, sample, count in rows:
        print(f"  [{count}x, {brand}] '{candidate}'  e.g. \"{sample}\"")
    print("\nTo fix one: add a row to DEFAULT_RULESET in database.py, e.g.:")
    print('    ("your keyword", "Correct Franchise Name"),')
    print("Then re-run scraper.py to apply it.")

conn.close()