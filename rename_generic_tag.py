# rename_generic_tag.py
"""
One-time migration: renames any products currently tagged with an old
catch-all franchise label to the new one. Safe to run multiple times
(no-op if there's nothing to rename).

Usage:
    python rename_generic_tag.py
"""
import json
import sqlite3

DB_NAME = "apparel_aggregator.db"
OLD_TAG = "Gaming Merch"
NEW_TAG = "Gamer Culture"

conn = sqlite3.connect(DB_NAME)
cursor = conn.execute(
    "UPDATE products SET franchise_tags = ? WHERE franchise_tags = ?",
    (json.dumps([NEW_TAG]), json.dumps([OLD_TAG]))
)
conn.commit()
print(f"Renamed {cursor.rowcount} product(s) from '{OLD_TAG}' to '{NEW_TAG}'.")
conn.close()