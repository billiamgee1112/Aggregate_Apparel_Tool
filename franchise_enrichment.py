# franchise_enrichment.py
"""
Auto-populates franchise_mappings with aliases + character keywords from Wikidata's
action API (free, no API key, no SPARQL/WDQS). Serial, batched, and rate-limit safe.

This script ONLY grows the franchise dictionary. It does NOT retag products.
After running, re-run scraper.py to re-apply clean tags using the enriched dictionary.

Usage (from project root):
    python franchise_enrichment.py            # enrich franchises not yet processed
    python franchise_enrichment.py --force    # re-process every franchise
"""
import sys
import re
import json
import time
import sqlite3
import urllib.parse
import urllib.request
import urllib.error

from parsers.franchise_map import COMMON_WORD_BLOCKLIST

DB_NAME = "apparel_aggregator.db"
WD_API = "https://www.wikidata.org/w/api.php"   # action API only — NO WDQS/SPARQL
USER_AGENT = "GamingApparelAggregator/1.0 (franchise-enrichment)"

API_DELAY = 0.3            # polite pause between API calls
PER_FRANCHISE_DELAY = 0.4
MAX_BACKOFF = 30           # never wait longer than this on a 429/503
RETRIES = 3

GAME_TYPES = {
    "Q7889",      # video game
    "Q7058673",   # video game series
    "Q16070115",  # video game franchise
    "Q196600",    # media franchise
}

GENERIC = {
    "the", "of", "and", "a", "an", "for", "new", "game", "games", "video",
    "series", "official", "logo", "shirt", "tee", "hoodie", "character", "list"
}

# COMMON_WORD_BLOCKLIST (common English dictionary words / bare abbreviations
# that are far too generic to use as standalone franchise keywords, e.g. the
# League of Legends champion "Brand" or the game literally titled "OFF") is
# imported from parsers.franchise_map to keep a single source of truth shared
# with the runtime matching code in parsers/shopify_base.py.

IGNORE_NAMES = {
    "Geek Apparel", "Insert Coin", "Artsholic", "Fangamer", "Glitch Gear",
    "Eightysixed", "Xbox Game Studios", "Bethesda", "Blizzard"
}

MIN_PRODUCTS_FOR_FRANCHISE = 3
MAX_FRANCHISE_WORDS = 4
MAX_CHARACTERS = 40


def _get_json(url):
    """GET JSON from the Wikidata action API with capped exponential backoff."""
    delay = 5
    for attempt in range(RETRIES):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code in (429, 503) and attempt < RETRIES - 1:
                retry_after = e.headers.get("Retry-After")
                wait = int(retry_after) if (retry_after and retry_after.isdigit()) else delay
                wait = min(wait, MAX_BACKOFF)   # never park for a 1000s ban
                print(f"    (rate-limited {e.code}; waiting {wait}s)")
                time.sleep(wait)
                delay = min(delay * 3, MAX_BACKOFF)
                continue
            raise
    return {}


def _api(params):
    params.setdefault("format", "json")
    params.setdefault("maxlag", 5)  # be a polite API citizen
    return _get_json(f"{WD_API}?{urllib.parse.urlencode(params)}")


# ------------------------------------------------------------------
# Wikidata action-API lookups (batched, no SPARQL)
# ------------------------------------------------------------------
def _search_qids(name, limit=5):
    data = _api({
        "action": "wbsearchentities", "search": name,
        "language": "en", "type": "item", "limit": limit
    })
    return [h["id"] for h in data.get("search", [])]


def _get_entities(qids, props):
    if not qids:
        return {}
    data = _api({
        "action": "wbgetentities", "ids": "|".join(qids),
        "props": props, "languages": "en"
    })
    return data.get("entities", {})


def _pick_game(entities, qids):
    for qid in qids:
        ent = entities.get(qid, {})
        p31 = set()
        for c in ent.get("claims", {}).get("P31", []):
            try:
                p31.add(c["mainsnak"]["datavalue"]["value"]["id"])
            except (KeyError, TypeError):
                continue
        if p31 & GAME_TYPES:
            return qid, ent
    return None, None


def _character_qids(ent):
    out = []
    for c in ent.get("claims", {}).get("P674", []):  # P674 = characters
        try:
            out.append(c["mainsnak"]["datavalue"]["value"]["id"])
        except (KeyError, TypeError):
            continue
        if len(out) >= MAX_CHARACTERS:
            break
    return out


def _labels_for(qids):
    ents = _get_entities(qids, props="labels")
    labels = []
    for qid in qids:
        lbl = ents.get(qid, {}).get("labels", {}).get("en", {}).get("value")
        if lbl:
            labels.append(lbl)
    return labels


def _to_keyword(text):
    k = re.sub(r"[^0-9a-z\s-]", "", text.lower()).strip()
    return re.sub(r"\s+", " ", k)


# ------------------------------------------------------------------
# Candidate selection
# ------------------------------------------------------------------
def _looks_like_franchise(name):
    n = (name or "").strip()
    low = n.lower()
    if len(n) < 3 or n.isdigit():
        return False
    if len(n.split()) > MAX_FRANCHISE_WORDS:
        return False
    if not re.search(r"[a-z]", low):
        return False
    if low.startswith(("a ", "an ", "a composite", "a mockup", "a short", "a view", "the composite")):
        return False
    return True


def _candidate_franchises(conn):
    candidates = set()
    for (fn,) in conn.execute("SELECT DISTINCT franchise_name FROM franchise_mappings"):
        if fn and fn.strip() not in IGNORE_NAMES:
            candidates.add(fn.strip())

    counts = {}
    for (tags,) in conn.execute("SELECT franchise_tags FROM products"):
        try:
            for t in json.loads(tags):
                t = (t or "").strip()
                if t:
                    counts[t] = counts.get(t, 0) + 1
        except Exception:
            continue
    for name, c in counts.items():
        if name in IGNORE_NAMES:
            continue
        if c >= MIN_PRODUCTS_FOR_FRANCHISE and _looks_like_franchise(name):
            candidates.add(name)
    return candidates


def _ensure_log_table(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS franchise_enrichment_log (
            franchise_name TEXT PRIMARY KEY,
            enriched_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)


def enrich_franchise(conn, name):
    try:
        qids = _search_qids(name)                          # API call 1
        if not qids:
            return 0
        time.sleep(API_DELAY)
        entities = _get_entities(qids, props="labels|aliases|claims")  # API call 2
        qid, ent = _pick_game(entities, qids)
        if not qid:
            return 0

        terms = []
        lbl = ent.get("labels", {}).get("en", {}).get("value")
        if lbl:
            terms.append(lbl)
        for a in ent.get("aliases", {}).get("en", []):
            if a.get("value"):
                terms.append(a["value"])

        char_qids = _character_qids(ent)
        if char_qids:
            time.sleep(API_DELAY)
            terms += _labels_for(char_qids)                # API call 3 (only if characters)
    except Exception as e:
        print(f"  ! {name}: {e}")
        return 0

    inserted, seen = 0, set()
    for t in terms:
        kw = _to_keyword(t)
        if not kw or kw in seen:
            continue
        seen.add(kw)
        if kw in GENERIC or kw in COMMON_WORD_BLOCKLIST or (len(kw) < 3 and " " not in kw):
            continue
        cur = conn.execute(
            "INSERT OR IGNORE INTO franchise_mappings (keyword, franchise_name) VALUES (?, ?)",
            (kw, name)
        )
        inserted += cur.rowcount
    return inserted


def run(force=False):
    conn = sqlite3.connect(DB_NAME)
    _ensure_log_table(conn)

    done = set()
    if not force:
        done = {r[0] for r in conn.execute("SELECT franchise_name FROM franchise_enrichment_log")}

    targets = sorted(_candidate_franchises(conn) - done)
    print(f"Enriching {len(targets)} plausible franchise(s) from Wikidata action API...")

    total = 0
    for name in targets:
        added = enrich_franchise(conn, name)
        total += added
        print(f"  + {name}: {added} new keyword(s)")
        conn.execute(
            "INSERT OR REPLACE INTO franchise_enrichment_log (franchise_name, enriched_at) VALUES (?, CURRENT_TIMESTAMP)",
            (name,)
        )
        conn.commit()
        time.sleep(PER_FRANCHISE_DELAY)

    conn.close()
    print(f"\nEnrichment done. Added {total} keyword(s) total.")
    print("Next: re-run 'python scraper.py' to re-apply franchise tags using the enriched dictionary.")


if __name__ == "__main__":
    run(force="--force" in sys.argv)