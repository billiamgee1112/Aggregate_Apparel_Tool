# parsers/franchise_map.py
import sqlite3
import re

# Standard base directory lookup for our database (modify if running path varies)
DB_PATH = "apparel_aggregator.db"

# Common English dictionary words / bare abbreviations that must never be used
# as franchise-matching keys, whether they come from a franchise_mappings
# "keyword" row or from a franchise's own canonical name (e.g. the indie game
# literally titled "OFF", or franchises named "Pure"/"PEAK"). Left unfiltered,
# these cause false-positive matches against completely unrelated product
# titles/descriptions ("10% OFF", "Blizzard brand merch", etc). Bad tags are
# worse than no tags, so this list is intentionally aggressive and should keep
# growing whenever a new collision is spotted via check_tags.py/show_review_queue.py.
# Kept in sync with franchise_enrichment.py's COMMON_WORD_BLOCKLIST.
COMMON_WORD_BLOCKLIST = {
    "off", "on", "in", "out", "up", "down", "re", "ac", "v",
    "league", "brand", "link", "heavy", "smoke", "scout", "sniper", "medic",
    "spy", "pyro", "reaper", "echo", "nova", "wizard", "queen", "player",
    "hero", "chaos", "beast", "comics", "granny", "meat", "sugar", "pure",
    "peak", "glitch", "may", "gen", "bill", "gears", "level", "world", "star",
}

def load_dynamic_mappings(db_path: str = DB_PATH) -> dict:
    """Loads matching rules directly from the database's taxonomy index,
    excluding any keyword that's too generic to safely auto-match on."""
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Check if table exists to prevent crash on fresh installs
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='franchise_mappings';")
        if not cursor.fetchone():
            conn.close()
            return {}
            
        cursor.execute("SELECT keyword, franchise_name FROM franchise_mappings")
        rules = {
            row[0].lower().strip(): row[1].strip()
            for row in cursor.fetchall()
            if row[0].lower().strip() not in COMMON_WORD_BLOCKLIST
        }
        conn.close()
        return rules
    except Exception:
        # Silently fail and return empty if DB hasn't been instantiated yet
        return {}

def clean_franchise_tag(product_name: str, store_url: str, fallback: str) -> str:
    """Standardizes franchise tags by checking database mappings against name and URL."""
    haystack = f"{product_name} {store_url}".lower()
    
    # Check our dynamic mappings table
    mappings = load_dynamic_mappings()
    
    for key, value in mappings.items():
        # Match as word boundaries, or regular substring if checking trailing hyphens
        pattern = rf"\b{re.escape(key)}\b" if not key.endswith("-") else rf"{re.escape(key)}"
        if re.search(pattern, haystack):
            return value
            
    return fallback