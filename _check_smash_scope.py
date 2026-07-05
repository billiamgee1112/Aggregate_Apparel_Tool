import sqlite3
conn = sqlite3.connect("apparel_aggregator.db")

# Check for duplicate keyword entries (e.g. a correct mapping shadowed by a bad one)
suspects = ["donkey kong", "captain falcon", "fox mccloud", "ness", "pikachu", "jigglypuff", "princess zelda", "mii", "wii fit trainer", "master hand"]
for kw in suspects:
    rows = conn.execute("SELECT keyword, franchise_name FROM franchise_mappings WHERE keyword = ?", (kw,)).fetchall()
    print(kw, "->", rows)

print()
print("=== Products whose titles mention these character names ===")
for kw in suspects:
    rows = conn.execute(
        "SELECT product_name, brand_name, franchise_tags FROM products WHERE LOWER(product_name) LIKE ?",
        (f"%{kw}%",)
    ).fetchall()
    if rows:
        print(f"\n-- '{kw}' --")
        for r in rows:
            print(" ", r)
