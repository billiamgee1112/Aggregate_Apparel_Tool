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
    # Added 2026-07-04 via audit_franchise_keywords.py (LLM audit), filtered
    # against real DB impact first (see _debug_keyword_impact.py check) to
    # avoid removing keywords that legitimately-tagged products depend on
    # with no redundant fallback text. NOTE: deliberately did NOT include
    # "aperture" - Glitch Gear's real "Aperture Laboratories" Portal product
    # line depends on it with no other matching signal in the title.
    "ac1", "ds1", "fm1", "mh1", "mcu", "s.t.a.r.s.", "-no13-", "administrator",
    "traveler", "citadel", "normandy", "forerunner", "bastion", "riverside",
    "biohazard", "lol", "2b", "controller", "engineer", "soldier", "dwarf",
    "transistor", "justice", "valhalla", "testament",
    # Added 2026-07-05: IGN's "Atomfall - BARD Pullover - Hoodie" product URL
    # slug (.../atomfall-bard-pullover-hoodie-1) collided with the League of
    # Legends champion keyword "bard", overriding the correct first-party
    # "franchise : Atomfall" store tag with "League of Legends". "bard" is a
    # common English word (a poet/reciter) unrelated to the champion in most
    # contexts - checked against real DB impact first (see
    # _check_bard_impact.py), no existing League of Legends product relies on
    # "bard" alone with no redundant "league"/"legends" signal.
    "bard",
    # Added 2026-07-05: surfaced by the new franchise_verified re-check pass
    # (franchise_discovery.py verifying previously-unverified naive-tokenizer
    # tags) confirming "Mystery" against the real but irrelevant "Mystery
    # Tower" Wikidata entity for a generic "Mystery T-Shirt Bundle" grab-bag
    # product - the same class of collision as "Pure"/"PEAK" above.
    "mystery",
    # Added 2026-07-05: bare "heroes" (mapped to "Heroes of the Storm") was
    # colliding with unrelated products in two ways: (1) "Sonic Heroes" (a
    # completely different game) getting mistagged as Heroes of the Storm
    # purely because both titles contain the word "heroes", and (2) The
    # Yetee's "Heroes" (a Darkest Dungeon shirt, URL slug ".../heroes-1")
    # losing its correct scraped_tag to this same collision. The full phrase
    # "heroes of the storm" is mapped separately and unaffected by this
    # removal - checked existing DB impact first, the 6 real Heroes of the
    # Storm products all contain that full phrase in their title/URL already.
    "heroes",
    # Added 2026-07-05: franchise_discovery.py's Wikidata/LLM-assisted
    # candidate-phrase check (used for the Atari store's brand-fallback
    # nostalgia/lifestyle items) confirmed several badly-wrong matches this
    # run: "stitch" -> Lilo & Stitch (a shirt with a "stitched-on" LOGO
    # DESIGN effect, nothing to do with Disney's Lilo & Stitch), "atari
    # video" -> Atari Video Cube (wrong entity for the real 1977 Atari Video
    # Music console), "atari 2600" -> Atari 2600 Action Pack (a specific
    # cartridge compilation, not the plain console-branded tee it was
    # matched against), "intellivision" -> Intellivision Lives! (a specific
    # 2003 compilation re-release, not the console/brand itself),
    # "dusk" -> Dusk (the word just meant a color/time-of-day in "Dusk Fuji
    # Tee", unrelated to the 2018 FPS game of the same name), "golden key" ->
    # Golden Key (generic "unlock hidden adventures" marketing copy on a hat,
    # not tied to any real franchise called Golden Key). All 9 affected
    # products were reverted to the "Gamer Culture" catch-all (matching the
    # established precedent for similar generic Atari nostalgia merch, e.g.
    # "Red Fuji Block Zip Hoodie") - checked DB impact first, no other
    # product's tag depends on any of these six phrases.
    "stitch", "atari video", "atari 2600", "intellivision", "dusk",
    "golden key",
}

# Characters who guest-star in Super Smash Bros but have their own separate
# origin franchise (already the primary/canonical tag once matched via
# franchise_mappings, e.g. "samus aran" -> "Metroid"). Products naming one of
# these characters get "Super Smash Bros" appended as an ADDITIONAL tag
# (not a replacement), so they're discoverable from both the character's real
# franchise page and the Super Smash Bros page - see get_bonus_franchise_tags().
# Deliberately excludes "mii" (too generic/ambiguous - spans many Nintendo
# systems, not just Smash) and "master hand" (no separate origin franchise;
# he already IS the primary "Super Smash Bros" tag, so no bonus needed).
SMASH_ROSTER_KEYWORDS = {
    "samus aran", "donkey kong", "captain falcon", "fox mccloud", "ness",
    "pikachu", "jigglypuff", "princess zelda", "wii fit trainer", "bayonetta",
}

def get_bonus_franchise_tags(haystack: str, primary_tag: str) -> list:
    """Checks for known 'guest character' keywords (e.g. Super Smash Bros
    roster members) that warrant an ADDITIONAL franchise tag alongside the
    primary one. Returns a list of extra tags (usually empty or one item)."""
    haystack = (haystack or "").lower()
    for key in SMASH_ROSTER_KEYWORDS:
        if re.search(rf"\b{re.escape(key)}\b", haystack):
            if primary_tag != "Super Smash Bros":
                return ["Super Smash Bros"]
            break
    return []

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

    # IMPORTANT: check longer/more specific keywords first. Dict iteration
    # order is arbitrary (DB insertion order), so without this a short,
    # unrelated keyword elsewhere in the haystack (e.g. a character name from
    # an old/stale mapping, or matching part of the store URL) could win over
    # the correct, more specific match purely by chance of ordering. Bug
    # found 2026-07-04: "winston" -> stale "Overwatch" beat "overwatch" ->
    # "Overwatch 2" simply because it happened to be checked first.
    for key in sorted(mappings.keys(), key=len, reverse=True):
        value = mappings[key]
        # Match as word boundaries, or regular substring if checking trailing hyphens
        pattern = rf"\b{re.escape(key)}\b" if not key.endswith("-") else rf"{re.escape(key)}"
        if re.search(pattern, haystack):
            return value
            
    return fallback