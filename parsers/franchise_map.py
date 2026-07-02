# parsers/franchise_map.py
import sqlite3
import re

# Standard base directory lookup for our database (modify if running path varies)
DB_PATH = "apparel_aggregator.db"

def load_dynamic_mappings(db_path: str = DB_PATH) -> dict:
    """Loads matching rules directly from the database's taxonomy index."""
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Check if table exists to prevent crash on fresh installs
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='franchise_mappings';")
        if not cursor.fetchone():
            conn.close()
            return {}
            
        cursor.execute("SELECT keyword, franchise_name FROM franchise_mappings")
        rules = {row[0].lower().strip(): row[1].strip() for row in cursor.fetchall()}
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