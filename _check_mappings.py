import sqlite3
conn = sqlite3.connect("apparel_aggregator.db")
cur = conn.cursor()
for kw in ["halo", "star wars", "battlefront", "pokemon", "pokémon", "kingdom hearts",
           "mewtwo", "squirtle", "call of duty", "black ops", "mickey", "disney"]:
    rows = cur.execute("SELECT keyword, franchise_name FROM franchise_mappings WHERE keyword = ?", (kw,)).fetchall()
    print(kw, "->", rows)
