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
import urllib.request
import urllib.error
from bs4 import BeautifulSoup

from franchise_enrichment import _search_qids, _get_entities, _pick_game, API_DELAY
from llm_classifier import is_available as llm_is_available, suggest_franchise
from parsers.franchise_map import COMMON_WORD_BLOCKLIST

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

DESCRIPTION_FETCH_TIMEOUT = 8
DESCRIPTION_FETCH_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)


def _fetch_page_description(url: str, max_len: int = 400) -> str:
    """Lightweight on-demand fetch of a single product page's SEO meta
    description (plain HTTP GET, no browser, no CSS-selector guessing).

    Used only as a last resort for stores that don't already have a
    description_snippet from the main scrape (i.e. Insert Coin/Artsholic,
    which are HTML-scraped from listing pages only and never visit individual
    product pages). Bounded to the same small handful of unresolved items
    that reach the LLM step each run — never touches the full catalog, so it
    doesn't add meaningful time/load to routine scraping.
    """
    if not url:
        return ""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": DESCRIPTION_FETCH_USER_AGENT})
        with urllib.request.urlopen(req, timeout=DESCRIPTION_FETCH_TIMEOUT) as r:
            html = r.read().decode("utf-8", errors="ignore")
        soup = BeautifulSoup(html, "html.parser")
        tag = soup.find("meta", attrs={"name": "description"}) or soup.find("meta", attrs={"property": "og:description"})
        content = (tag.get("content") or "").strip() if tag else ""
        return content[:max_len]
    except Exception:
        return ""


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

    Skips any candidate that's in COMMON_WORD_BLOCKLIST: some common English
    words happen to ALSO be real (but obscure/irrelevant) Wikidata game
    titles (e.g. "Pure", a 2008 racing game), which would otherwise slip
    through Wikidata verification despite being blocklisted for keyword
    matching elsewhere - this closes that loophole.
    """
    cleaned = re.sub(r"[^0-9A-Za-z\s]", " ", title)
    words = cleaned.split()
    seen = set()
    for end in range(min(len(words), 6), 0, -1):
        phrase = " ".join(words[:end])
        key = phrase.lower()
        if key not in seen and key not in COMMON_WORD_BLOCKLIST:
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


def _verify_phrase(conn, phrase, state):
    """Verifies a single arbitrary phrase (e.g. an LLM suggestion) against
    Wikidata, using the same cache/budget/circuit-breaker machinery as normal
    candidates. Returns the canonical Wikidata label if confirmed, else None.
    Never trusts the phrase itself — only the verified Wikidata result."""
    name, _fully_evaluated = _verify_phrase_ex(conn, phrase, state)
    return name


def _verify_phrase_ex(conn, phrase, state):
    """Same as _verify_phrase, but also returns whether the phrase was
    actually evaluated (cache hit or live check performed) vs. skipped due to
    budget/circuit-breaker exhaustion. Returns (name_or_None, fully_evaluated)."""
    key = (phrase or "").strip().lower()
    if not key or key in COMMON_WORD_BLOCKLIST:
        return None, True

    row = conn.execute(
        "SELECT franchise_name FROM wikidata_verify_cache WHERE phrase = ?", (key,)
    ).fetchone()
    if row is not None:
        return row[0], True

    if state["budget"] <= 0 or state["tracker"]["slow_calls"] >= CIRCUIT_BREAKER_LIMIT:
        return None, False

    name = _live_verify(key, state["tracker"])
    conn.execute(
        "INSERT OR REPLACE INTO wikidata_verify_cache (phrase, franchise_name, checked_at) "
        "VALUES (?, ?, CURRENT_TIMESTAMP)",
        (key, name)
    )
    conn.commit()
    state["budget"] -= 1
    state["checked"] += 1
    return name, True


def run(budget=DEFAULT_BUDGET):
    conn = sqlite3.connect(DB_NAME)
    _ensure_tables(conn)

    rows = conn.execute(
        "SELECT store_url, product_name, brand_name, franchise_tags, description_snippet, franchise_verified FROM products"
    ).fetchall()

    unresolved = []
    unverified = []
    for store_url, product_name, brand_name, franchise_tags_json, description_snippet, franchise_verified in rows:
        try:
            current_tags = json.loads(franchise_tags_json)
        except Exception:
            current_tags = []
        # Reconsider both "still just the brand name" AND previously auto-tagged
        # generic items (in case a later Wikidata addition now resolves them)
        already_generic = (current_tags == [GENERIC_MERCH_TAG])
        is_brand_fallback = (current_tags == [brand_name])
        if is_brand_fallback or already_generic:
            unresolved.append((store_url, product_name, brand_name, already_generic, description_snippet or ""))
        elif not franchise_verified and current_tags:
            # A genuine architectural blind spot: this tag came from the naive
            # title-tokenizer or URL-slug fallback (parsers/base.py) or a
            # lenient collection-link guess (shopify_base.py), so it looks
            # "confident" (a specific-looking name, not the brand or generic
            # catch-all) but was NEVER independently checked against Wikidata.
            # That's how a character name like "Gabimaru" could sit there
            # unnoticed instead of the real franchise. Route it through the
            # same verification machinery as brand-fallback items.
            unverified.append((store_url, product_name, brand_name, description_snippet or "", current_tags[0]))

    print(f"Found {len(unresolved)} unresolved product(s) and {len(unverified)} unverified tag(s). "
          f"Budget: {budget} new Wikidata check(s) this run.")

    llm_ok = llm_is_available()
    print(f"LLM-assisted classification: {'ENABLED' if llm_ok else 'disabled (Ollama not reachable, or ENABLE_LLM_TAGGING=false)'}")

    state = {"budget": budget, "checked": 0, "tracker": {"slow_calls": 0}}
    retagged = 0
    llm_assisted = 0
    generic_tagged_new = 0
    still_generic = 0
    deferred = 0
    verified_confirmed = 0
    verified_unconfirmed = 0
    breaker_tripped = False

    def _breaker_check():
        nonlocal breaker_tripped
        if state["tracker"]["slow_calls"] >= CIRCUIT_BREAKER_LIMIT and not breaker_tripped:
            breaker_tripped = True
            print("  ! Wikidata appears to be rate-limiting this session. "
                  "Pausing further live checks; remaining items will retry next run.")

    for store_url, product_name, brand_name, already_generic, description_snippet in unresolved:
        _breaker_check()

        resolved_name, resolved_phrase, fully_evaluated = _resolve_product(conn, product_name, state)

        # Last resort before giving up to the generic catch-all: ask the local
        # LLM for a candidate, but ONLY trust it if Wikidata independently
        # confirms the candidate is a real game/franchise entity.
        used_llm = False
        if not resolved_name and fully_evaluated and llm_ok:
            description_for_llm = description_snippet or _fetch_page_description(store_url)
            suggestion = suggest_franchise(product_name, brand_name, description_for_llm)
            if suggestion:
                confirmed = _verify_phrase(conn, suggestion, state)
                if confirmed and confirmed not in IGNORE_NAMES:
                    resolved_name, resolved_phrase = confirmed, suggestion.lower()
                    used_llm = True

        if resolved_name and resolved_name not in IGNORE_NAMES:
            conn.execute(
                "INSERT OR IGNORE INTO franchise_mappings (keyword, franchise_name) VALUES (?, ?)",
                (resolved_phrase, resolved_name)
            )
            conn.execute(
                "UPDATE products SET franchise_tags = ?, franchise_verified = 1 WHERE store_url = ?",
                (json.dumps([resolved_name]), store_url)
            )
            retagged += 1
            if used_llm:
                llm_assisted += 1
                print(f"  discovered (LLM-assisted): '{resolved_phrase}' -> {resolved_name}  ({product_name})")
            else:
                print(f"  discovered: '{resolved_phrase}' -> {resolved_name}  ({product_name})")
        elif fully_evaluated:
            # Confirmed: no specific franchise. Ensure it's classified (no-op if already tagged).
            if not already_generic:
                conn.execute(
                    "UPDATE products SET franchise_tags = ?, franchise_verified = 1 WHERE store_url = ?",
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

    for store_url, product_name, brand_name, description_snippet, current_tag in unverified:
        _breaker_check()

        # First, try to confirm the EXISTING tag directly against Wikidata —
        # cheap (cached) and it might already be exactly right, just never
        # checked. Only if that fails do we fall back to re-deriving
        # candidates from the title from scratch.
        resolved_name, fully_evaluated = _verify_phrase_ex(conn, current_tag, state)
        resolved_phrase = current_tag.lower() if resolved_name else None
        if not resolved_name and fully_evaluated:
            resolved_name, resolved_phrase, fully_evaluated = _resolve_product(conn, product_name, state)

        used_llm = False
        if not resolved_name and fully_evaluated and llm_ok:
            description_for_llm = description_snippet or _fetch_page_description(store_url)
            suggestion = suggest_franchise(product_name, brand_name, description_for_llm)
            if suggestion:
                confirmed = _verify_phrase(conn, suggestion, state)
                if confirmed and confirmed not in IGNORE_NAMES:
                    resolved_name, resolved_phrase = confirmed, suggestion.lower()
                    used_llm = True

        if resolved_name and resolved_name not in IGNORE_NAMES:
            conn.execute(
                "INSERT OR IGNORE INTO franchise_mappings (keyword, franchise_name) VALUES (?, ?)",
                (resolved_phrase, resolved_name)
            )
            conn.execute(
                "UPDATE products SET franchise_tags = ?, franchise_verified = 1 WHERE store_url = ?",
                (json.dumps([resolved_name]), store_url)
            )
            verified_confirmed += 1
            if used_llm:
                llm_assisted += 1
            print(f"  verified: '{current_tag}' -> {resolved_name}  ({product_name})")
        elif fully_evaluated:
            # Wikidata couldn't confirm anything - don't destroy a possibly-
            # legitimate niche/indie tag by demoting it to Gamer Culture.
            # Mark it processed (so the budget isn't spent re-checking it every
            # run) and surface it for a human via the review queue instead.
            conn.execute(
                "UPDATE products SET franchise_verified = 1 WHERE store_url = ?",
                (store_url,)
            )
            verified_unconfirmed += 1
            existing = conn.execute(
                "SELECT occurrences FROM franchise_review_queue WHERE candidate = ?",
                (current_tag.lower(),)
            ).fetchone()
            if existing:
                conn.execute(
                    "UPDATE franchise_review_queue SET occurrences = occurrences + 1 WHERE candidate = ?",
                    (current_tag.lower(),)
                )
            else:
                conn.execute(
                    "INSERT INTO franchise_review_queue (candidate, brand_name, sample_product) VALUES (?, ?, ?)",
                    (current_tag.lower(), brand_name, product_name)
                )
        else:
            deferred += 1

    conn.commit()
    print(f"\nDiscovery done. Performed {state['checked']} live Wikidata check(s) this run.")
    print(f"Auto-retagged {retagged} product(s) with a confirmed franchise.")
    if llm_assisted:
        print(f"  ({llm_assisted} of those were LLM-suggested and Wikidata-confirmed.)")
    if generic_tagged_new:
        print(f"Newly classified {generic_tagged_new} product(s) as '{GENERIC_MERCH_TAG}'.")
    if still_generic:
        print(f"{still_generic} product(s) remain correctly classified as '{GENERIC_MERCH_TAG}' (no change needed).")
    if verified_confirmed:
        print(f"Confirmed and upgraded {verified_confirmed} previously-unverified tag(s).")
    if verified_unconfirmed:
        print(f"{verified_unconfirmed} previously-unverified tag(s) left as-is (unconfirmed either way) "
              f"and logged to the review queue.")
    if deferred:
        print(f"{deferred} product(s) deferred (budget/rate-limit reached) — will be retried on the next run.")
    conn.close()


if __name__ == "__main__":
    run()