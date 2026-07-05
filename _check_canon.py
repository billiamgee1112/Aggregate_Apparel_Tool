import sqlite3
conn = sqlite3.connect("apparel_aggregator.db")
for term in ["pokemon", "pokémon", "zelda", "legend of zelda", "donkey kong"]:
    rows = conn.execute("SELECT keyword, franchise_name FROM franchise_mappings WHERE keyword LIKE ?", (f"%{term}%",)).fetchall()
    print(term, "->", rows)
