# audit_franchise_keywords.py
"""
One-time (or periodic) audit of franchise_mappings using the local LLM
(Ollama) to catch overly-generic keywords that could cause false-positive
franchise tags on unrelated products - the same class of bug manually fixed
for keywords like 'off', 'league', 'brand', 'gears', etc.

READ-ONLY: this script only prints a report, it never modifies the database.
Review the flagged keywords yourself, then:
  1. Add real offenders to COMMON_WORD_BLOCKLIST in parsers/franchise_map.py
  2. Delete the corresponding row(s) from franchise_mappings (it won't be
     re-inserted once blocklisted, since franchise_enrichment.py checks the
     same blocklist before inserting new keywords)
  3. Re-run scraper.py to re-apply clean tags with the purged dictionary

Requires Ollama running locally (see llm_classifier.py). Checks single-word
keywords by default (highest false-positive risk); pass --all to also check
multi-word keywords (slower, lower risk).

Usage:
    python audit_franchise_keywords.py              # single-word keywords only
    python audit_franchise_keywords.py --all         # include multi-word keywords too
    python audit_franchise_keywords.py --limit 20    # only check the first N (for a quick test)
"""
import sys
import json
import sqlite3
import urllib.request
import urllib.error

from llm_classifier import is_available, OLLAMA_URL, OLLAMA_MODEL

DB_NAME = "apparel_aggregator.db"
REQUEST_TIMEOUT = 15

_AUDIT_PROMPT = """You help maintain a video-game-apparel website's franchise tagging system.

We use exact-match keyword matching: if the word "{keyword}" appears ANYWHERE in a product's title or description, that product gets tagged as belonging to the "{franchise_name}" franchise.

Only flag a keyword as risky if it is a common, ordinary ENGLISH DICTIONARY WORD, a generic abbreviation, or a very short/ambiguous fragment that has everyday meaning OUTSIDE gaming. Distinctive proper nouns, character names, and made-up/franchise-specific words are SAFE even if you don't personally recognize them - do NOT flag a word just because it's theoretically possible for it to appear elsewhere. When in doubt, prefer NOT flagging it (false negatives are fine; false positives waste review time).

Examples of RISKY keywords (common words/generic terms): "off", "league", "brand", "gears", "wizard", "queen", "hero", "ac", "re", "player", "level", "world", "star", "administrator", "spy", "heavy".

Examples of NOT risky keywords (distinctive proper nouns / character / franchise-specific names, even if uncommon or unfamiliar to you): "aatrox", "aerith", "ryu", "kazuma", "geralt", "n7", "hots", "totk".

Keyword to evaluate: "{keyword}"
Franchise it's mapped to: {franchise_name}

Respond with ONLY a JSON object, no other text: {{"risky": true or false, "reasoning": "<short reason>"}}"""


def _ask(keyword, franchise_name):
    """Returns (risky: bool|None, reasoning: str). risky is None on error."""
    prompt = _AUDIT_PROMPT.format(keyword=keyword, franchise_name=franchise_name)
    payload = json.dumps({
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "format": "json"
    }).encode("utf-8")

    try:
        req = urllib.request.Request(
            f"{OLLAMA_URL}/api/generate", data=payload,
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as r:
            data = json.loads(r.read().decode("utf-8"))
        result = json.loads(data.get("response", "{}"))
        return bool(result.get("risky")), str(result.get("reasoning", "")).strip()
    except Exception as e:
        return None, str(e)


def run(include_multi_word=False, limit=None):
    if not is_available():
        print("Ollama is not reachable (or ENABLE_LLM_TAGGING=false). This audit requires a running local LLM.")
        print(f"Expected at: {OLLAMA_URL} (model: {OLLAMA_MODEL})")
        return

    conn = sqlite3.connect(DB_NAME)
    if include_multi_word:
        query = "SELECT keyword, franchise_name FROM franchise_mappings ORDER BY keyword"
    else:
        query = "SELECT keyword, franchise_name FROM franchise_mappings WHERE keyword NOT LIKE '% %' ORDER BY keyword"
    rows = conn.execute(query).fetchall()
    conn.close()

    if limit:
        rows = rows[:limit]

    print(f"Auditing {len(rows)} keyword(s) via {OLLAMA_MODEL} (read-only, nothing is modified)...\n")

    flagged = []
    errors = 0
    for i, (keyword, franchise_name) in enumerate(rows, 1):
        risky, reasoning = _ask(keyword, franchise_name)
        if risky is None:
            errors += 1
            print(f"  [{i}/{len(rows)}] ! error checking '{keyword}': {reasoning}")
            continue
        if risky:
            flagged.append((keyword, franchise_name, reasoning))
            print(f"  [{i}/{len(rows)}] FLAGGED: '{keyword}' -> {franchise_name}  ({reasoning})")

    print(f"\nAudit done. {len(flagged)} of {len(rows)} keyword(s) flagged as risky ({errors} error(s)).")
    if flagged:
        print("\nTo fix a flagged keyword:")
        print("  1. Add it to COMMON_WORD_BLOCKLIST in parsers/franchise_map.py")
        print("  2. Delete the corresponding row(s) from franchise_mappings")
        print("  3. Re-run scraper.py to re-apply clean tags")


if __name__ == "__main__":
    args = sys.argv[1:]
    limit_arg = None
    if "--limit" in args:
        idx = args.index("--limit")
        if idx + 1 < len(args):
            limit_arg = int(args[idx + 1])
    run(include_multi_word="--all" in args, limit=limit_arg)
