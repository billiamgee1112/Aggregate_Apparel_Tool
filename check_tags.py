# check_tags.py
import sqlite3

conn = sqlite3.connect("apparel_aggregator.db")

brands = ["Xbox Game Studios", "Bethesda", "Blizzard", "Fangamer", "Glitch Gear"]
for brand in brands:
    print(f"\n===== {brand} =====")
    rows = conn.execute(
        "SELECT franchise_tags, product_name FROM products "
        "WHERE brand_name = ? ORDER BY product_name LIMIT 10",
        (brand,)
    ).fetchall()
    if not rows:
        print("  (no rows)")
    for tags, name in rows:
        print(f"  {tags} -> {name}")

conn.close()