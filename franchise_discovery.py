# franchise_discovery.py
"""
Automatically discovers new franchises from products that fell back to their
brand name (i.e., no franchise was recognized), by extracting a candidate name
from the product title and verifying it against Wikidata before accepting it.

Design notes (rate-limit safety):
- Every candidate phrase is verified against Wikidata AT MOST ONCE, EVER, via a
  persistent cache table (wikidata_verify_cache). Repeated runs never re-ask
  the same question.
- Each run only performs a small, bounded number of NEW live checks
  (DEFAULT_BUDGET). Anything beyond that is deferred to the next scheduled run.
- A circuit breaker halts further live checks for the rest of the run if
  Wikidata appears to be throttling.

Products confirmed to have NO specific franchise (fully evaluated, nothing
verified) are automatically tagged with GENERIC_MERCH_TAG so they remain fully
browsable on the site instead of sitting unlabeled. They're logged to
franchise_review_queue ONLY the first time they're classified this way — once
logged, re-evaluating them on later runs (to catch newly-added Wikidata data)
won't spam the queue again.

Usage:
    python franchise_discovery.py
"""
import re
import json
import time
import sqlite3

from franchise_enrichment import _search_qids, _get_entities, _pick_game, API_DELAY

DB_NAME = "apparel_aggregator.db"

# Catch-all category for confirmed non-franchise gaming merch (mystery boxes,
# store-branded items, identity/lifestyle apparel, etc.) so it stays browsable
# instead of being left unlabeled.
GENERIC_MERCH_TAG = "Gamer Culture"

IGNORE_NAMES = {
    "Geek Apparel", "Insert Coin", "Artsholic", "Fangamer", "Glitch Gear",
    "Eightysixed", "Xbox Game Studios", "Bethesda", "Blizzard", GENERIC_MERCH_TAG
}

DEFAULT_BUDGET = 25          # max NEW (uncached) Wikidata checks per run
SLOW_CALL_THRESHOLD = 15     # seconds; a normal call is <2s, this means backoff kicked in
CIRCUIT_BREAKER_LIMIT = 3    # consecutive slow/failed calls before we stop for this run


def _ensure_tables(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS franchise_review_queue (
            candidate TEXT PRIMARY KEY,
            brand_name TEXT,
            sample_product TEXT,
            occurrences INTEGER DEFAULT 1,
            first_seen DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS wikidata_verify_cache (
            phrase TEXT PRIMARY KEY,
            franchise_name TEXT,
            checked_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)


def _candidate_phrases(title):
    """Generates shrinking leading-phrase candidates from a title, e.g.
    'DOOM: The Dark Ages Slayer Moto Jacket' ->
    ['doom the dark ages slayer moto', ..., 'doom the dark ages', 'doom the dark', 'doom']
    """
    cleaned = re.sub(r"[^0-9A-Za-z\s]", " ", title)
    words = cleaned.split()
    seen = set()
    for end in range(min(len(words), 6), 0, -1):
        phrase = " ".join(words[:end])
        key = phrase.lower()
        if key not in seen:
            seen.add(key)
            yield key


def _live_verify(phrase, tracker):
    """Performs the actual Wikidata lookup, tracking slow/failed calls for the
    circuit breaker."""
    start = time.time()
    try:
        qids = _search_qids(phrase, limit=3)
        if not qids:
            return None
        time.sleep(API_DELAY)
        entities = _get_entities(qids, props="labels|claims")
        qid, ent = _pick_game(entities, qids)
        if not qid:
            return None
        return ent.get("labels", {}).get("en", {}).get("value") or phrase
    except Exception:
        return None
    finally:
        if time.time() - start > SLOW_CALL_THRESHOLD:
            tracker["slow_calls"] += 1
        else:
            tracker["slow_calls"] = 0


def _resolve_product(conn, product_name, state):
    """Attempts to resolve a franchise for a product using cached results first,
    then live Wikidata checks (bounded by state['budget'] and the circuit breaker).

    Returns (resolved_name_or_None, resolved_phrase_or_None, fully_evaluated: bool)
    """
    fully_evaluated = True
    for phrase in _candidate_phrases(product_name):
        row = conn.execute(
            "SELECT franchise_name FROM wikidata_verify_cache WHERE phrase = ?", (phrase,)
        ).fetchone()

        if row is not None:
            name = row[0]
        else:
            if state["budget"] <= 0 or state["tracker"]["slow_calls"] >= CIRCUIT_BREAKER_LIMIT:
                fully_evaluated = False
                continue
            name = _live_verify(phrase, state["tracker"])
            conn.execute(
                "INSERT OR REPLACE INTO wikidata_verify_cache (phrase, franchise_name, checked_at) "
                "VALUES (?, ?, CURRENT_TIMESTAMP)",
                (phrase, name)
            )
            conn.commit()
            state["budget"] -= 1
            state["checked"] += 1

        if name:
            return name, phrase, True

    return None, None, fully_evaluated


def run(budget=DEFAULT_BUDGET):
    conn = sqlite3.connect(DB_NAME)
    _ensure_tables(conn)

    rows = conn.execute(
        "SELECT store_url, product_name, brand_name, franchise_tags FROM products"
    ).fetchall()

    unresolved = []
    for store_url, product_name, brand_name, franchise_tags_json in rows:
        try:
            current_tags = json.loads(franchise_tags_json)
        except Exception:
            current_tags = []
        # Reconsider both "still just the brand name" AND previously auto-tagged
        # generic items (in case a later Wikidata addition now resolves them)
        already_generic = (current_tags == [GENERIC_MERCH_TAG])
        if current_tags == [brand_name] or already_generic:
            unresolved.append((store_url, product_name, brand_name, already_generic))

    print(f"Found {len(unresolved)} unresolved product(s). Budget: {budget} new Wikidata check(s) this run.")

    state = {"budget": budget, "checked": 0, "tracker": {"slow_calls": 0}}
    retagged = 0
    generic_tagged_new = 0
    still_generic = 0
    deferred = 0
    breaker_tripped = False

    for store_url, product_name, brand_name, already_generic in unresolved:
        if state["tracker"]["slow_calls"] >= CIRCUIT_BREAKER_LIMIT and not breaker_tripped:
            breaker_tripped = True
            print("  ! Wikidata appears to be rate-limiting this session. "
                  "Pausing further live checks; remaining items will retry next run.")

        resolved_name, resolved_phrase, fully_evaluated = _resolve_product(conn, product_name, state)

        if resolved_name and resolved_name not in IGNORE_NAMES:
            conn.execute(
                "INSERT OR IGNORE INTO franchise_mappings (keyword, franchise_name) VALUES (?, ?)",
                (resolved_phrase, resolved_name)
            )
            conn.execute(
                "UPDATE products SET franchise_tags = ? WHERE store_url = ?",
                (json.dumps([resolved_name]), store_url)
            )
            retagged += 1
            print(f"  discovered: '{resolved_phrase}' -> {resolved_name}  ({product_name})")
        elif fully_evaluated:
            # Confirmed: no specific franchise. Ensure it's classified (no-op if already tagged).
            if not already_generic:
                conn.execute(
                    "UPDATE products SET franchise_tags = ? WHERE store_url = ?",
                    (json.dumps([GENERIC_MERCH_TAG]), store_url)
                )
                generic_tagged_new += 1

                # Log to the queue only the FIRST time this happens — an audit trail,
                # not a repeating nag for items already classified.
                candidate_guess = " ".join(product_name.split()[:3]).lower()
                existing = conn.execute(
                    "SELECT occurrences FROM franchise_review_queue WHERE candidate = ?",
                    (candidate_guess,)
                ).fetchone()
                if existing:
                    conn.execute(
                        "UPDATE franchise_review_queue SET occurrences = occurrences + 1 WHERE candidate = ?",
                        (candidate_guess,)
                    )
                else:
                    conn.execute(
                        "INSERT INTO franchise_review_queue (candidate, brand_name, sample_product) VALUES (?, ?, ?)",
                        (candidate_guess, brand_name, product_name)
                    )
            else:
                still_generic += 1
        else:
            deferred += 1

    conn.commit()
    print(f"\nDiscovery done. Performed {state['checked']} live Wikidata check(s) this run.")
    print(f"Auto-retagged {retagged} product(s) with a confirmed franchise.")
    if generic_tagged_new:
        print(f"Newly classified {generic_tagged_new} product(s) as '{GENERIC_MERCH_TAG}'.")
    if still_generic:
        print(f"{still_generic} product(s) remain correctly classified as '{GENERIC_MERCH_TAG}' (no change needed).")
    if deferred:
        print(f"{deferred} product(s) deferred (budget/rate-limit reached) — will be retried on the next run.")
    conn.close()


if __name__ == "__main__":
    run()