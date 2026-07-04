# llm_classifier.py
"""
Optional local-LLM-assisted franchise classification via Ollama.

Used as an additional signal by franchise_discovery.py: when a product's title
can't be resolved to any known franchise via keyword matching or leading-phrase
Wikidata search, this module asks a locally-running Ollama model to propose a
candidate franchise name from the title alone.

IMPORTANT: the LLM's suggestion is NEVER trusted directly. franchise_discovery.py
still verifies it against Wikidata before accepting it, exactly like every other
candidate source in this pipeline ("bad tags are worse than no tags").

Requires Ollama running locally (https://ollama.com) with a pulled model, e.g.:
    ollama pull qwen2.5:14b-instruct

This is fully optional and degrades silently: if Ollama isn't installed/running,
suggest_franchise() just returns "" so franchise_discovery.py falls back to its
existing Wikidata-only behavior. Disable explicitly with ENABLE_LLM_TAGGING=false.
"""
import os
import json
import urllib.request
import urllib.error

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434").rstrip("/")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:14b-instruct")
ENABLE_LLM_TAGGING = os.getenv("ENABLE_LLM_TAGGING", "true").strip().lower() in ("1", "true", "yes")

CONNECT_TIMEOUT = 2     # seconds; fast fail if Ollama isn't running
REQUEST_TIMEOUT = 15    # seconds; local inference on a 14B model is normally <2s

_PROMPT_TEMPLATE = """You are classifying a gaming-apparel product by video game franchise.

Store: {brand_name} (sells video-game-themed apparel)
Product title: "{product_name}"
{description_block}
Question: What specific, real, well-known video game franchise does this product most likely belong to? If you are not reasonably confident, answer null rather than guessing.

Respond with ONLY a JSON object, no other text: {{"franchise": "<name or null>", "confidence": "<high|medium|low>", "reasoning": "<short reason>"}}"""


def is_available() -> bool:
    """Quick check for whether Ollama is reachable at all. Cheap enough to
    call once per run rather than caching."""
    if not ENABLE_LLM_TAGGING:
        return False
    try:
        req = urllib.request.Request(f"{OLLAMA_URL}/api/version")
        with urllib.request.urlopen(req, timeout=CONNECT_TIMEOUT) as r:
            return r.status == 200
    except Exception:
        return False


def suggest_franchise(product_name: str, brand_name: str = "", description: str = "") -> str:
    """Asks the local LLM for a candidate franchise name based on the product
    title and, when available, a short description snippet. Returns "" if
    Ollama is unavailable, the model declines to guess, or confidence is low.

    This is a CANDIDATE only — callers must still verify it (e.g. against
    Wikidata) before trusting it, same as every other signal in this pipeline.
    """
    if not ENABLE_LLM_TAGGING:
        return ""

    description = (description or "").strip()
    description_block = f'Product description: "{description}"\n' if description else ""

    prompt = _PROMPT_TEMPLATE.format(
        brand_name=brand_name or "an online store",
        product_name=product_name,
        description_block=description_block
    )
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
    except Exception:
        return ""

    franchise = result.get("franchise")
    confidence = str(result.get("confidence", "")).strip().lower()

    if not franchise or str(franchise).strip().lower() == "null":
        return ""
    if confidence == "low":
        return ""
    return str(franchise).strip()
