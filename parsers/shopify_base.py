# parsers/shopify_base.py
import re
from bs4 import BeautifulSoup
from parsers.base import BaseParser


class ShopifyJsonParser(BaseParser):
    """Shared parser for Shopify stores using the public products.json feed.

    Subclasses set:
        brand_name       - display name
        store_root       - e.g. "https://shop.xboxgamestudios.com"
        url_pattern      - ".../collections/apparel/products.json?limit=250&page={page_num}"
        franchise_source - "game_tag" | "vendor" | "known_tag" | "mapping_tags"
        known_franchises - (only for "known_tag") list of canonical franchise names
    """

    # Satisfy BaseParser's abstract members with fixed values
    item_selector = ""
    pagination_type = "shopify_json"
    first_page_override = None
    max_pages = 20

    # Overridable by subclasses
    store_root = ""
    franchise_source = "game_tag"
    known_franchises = []

    _APPAREL_HINTS = [
        "shirt", "tee", "hoodie", "sweater", "sweatshirt", "jacket", "hat",
        "beanie", "cap", "sock", "short", "pant", "crewneck", "tank",
        "long sleeve", "apparel", "jersey", "pullover", "outerwear"
    ]

    # Vendors that are fulfillment providers / store names, never franchises
    _VENDOR_IGNORE = {
        "printful", "bestlink", "lgm", "king graphics", "glitchgear.com",
        "fangamer", "shopify"
    }

    # Shopify collection handles that are generic layout buckets, never franchises
    _GENERIC_COLLECTION_SLUGS = {
        "all", "apparel", "accessories", "hoodies", "hoodies-jackets", "t-shirts",
        "shirts", "tops", "bottoms", "outerwear", "sale", "new-arrivals",
        "featured", "frontpage", "home-page", "clothing", "mens", "womens",
        "unisex", "gifts", "home-office", "specialty-apparel", "collectibles",
        "best-sellers"
    }

    # Lazy per-instance cache of the franchise dictionary (keyword/name -> franchise)
    _franchise_index = None

    # ------------------------------------------------------------------
    # Franchise resolution
    # ------------------------------------------------------------------
    @staticmethod
    def _game_slug_from_tags(tags):
        for t in tags or []:
            m = re.match(r"\s*game\s*:\s*(.+)$", str(t), re.IGNORECASE)
            if m:
                return re.sub(r"[^0-9a-z]", "", m.group(1).lower())
        return ""

    @staticmethod
    def _franchise_from_title(slug, title):
        if not slug or not title:
            return ""
        words = title.split()
        start = 0
        if words and words[0].lower() == "the" and not slug.startswith("the"):
            start = 1
        acc = ""
        for i in range(start, len(words)):
            acc += re.sub(r"[^0-9a-z]", "", words[i].lower())
            if acc == slug:
                name = " ".join(words[start:i + 1])
                return re.sub(r"[:\-–—]+$", "", name).strip(" -:–—")
            if not slug.startswith(acc):
                break
        return ""

    def _match_known(self, product):
        title = product.get("title", "") or ""
        haystacks = [title] + [str(t) for t in (product.get("tags") or [])]
        for fr in sorted(self.known_franchises, key=len, reverse=True):
            frl = fr.lower()
            if any(frl in h.lower() for h in haystacks):
                return fr
        return ""

    def _load_franchise_index(self):
        """Builds a {searchable_key -> franchise_name} map from franchise_mappings,
        including both alias keywords and the canonical franchise names."""
        if self._franchise_index is None:
            index = {}
            try:
                from parsers.franchise_map import load_dynamic_mappings
                mappings = load_dynamic_mappings()  # {keyword_lower: franchise_name}
                for kw, fr in mappings.items():
                    if kw:
                        index[kw.lower().strip()] = fr
                    if fr:
                        index[fr.lower().strip()] = fr
            except Exception:
                pass
            self._franchise_index = index
        return self._franchise_index

    def _match_text_against_index(self, haystack: str) -> str:
        """Scans arbitrary text (title, tags, or description) for known franchise
        keywords/names via the franchise_mappings dictionary."""
        index = self._load_franchise_index()
        if not index or not haystack:
            return ""
        haystack = haystack.lower()
        for key in sorted(index.keys(), key=len, reverse=True):
            if not key:
                continue
            pattern = rf"\b{re.escape(key)}\b" if not key.endswith("-") else re.escape(key)
            if re.search(pattern, haystack):
                return index[key]
        return ""

    def _match_mappings(self, product):
        haystack = " ".join(
            [product.get("title", "") or ""] + [str(t) for t in (product.get("tags") or [])]
        )
        return self._match_text_against_index(haystack)

    @staticmethod
    def _looks_plausible_franchise(name: str) -> bool:
        """Light sanity check for candidates sourced from the store's own
        collection links (already a trustworthy signal, so this is deliberately
        lenient compared to the stricter title-guessing heuristics elsewhere)."""
        n = (name or "").strip()
        if len(n) < 3 or n.isdigit():
            return False
        if len(n.split()) > 5:
            return False
        return bool(re.search(r"[a-zA-Z]", n))

    def _extract_collection_candidates(self, body_html: str) -> list:
        """Finds /collections/{slug} links embedded in the product description.
        Many stores include 'Related Links: X Gear Collection' style references
        that directly name the franchise even when the product title doesn't."""
        slugs = re.findall(r"/collections/([a-z0-9\-]+)", body_html or "", re.IGNORECASE)
        seen = set()
        candidates = []
        for slug in slugs:
            slug_lower = slug.lower()
            if slug_lower in self._GENERIC_COLLECTION_SLUGS or slug_lower in seen:
                continue
            seen.add(slug_lower)
            candidates.append(" ".join(w.capitalize() for w in slug_lower.split("-")))
        return candidates

    def _match_description(self, product) -> str:
        """Mines the product's full description (body_html) for franchise signals:
        first checks any embedded /collections/ links (the store's own authoritative
        categorization), then falls back to scanning the description's plain text
        for known franchise keywords/aliases."""
        body_html = product.get("body_html", "") or ""
        if not body_html:
            return ""

        for candidate in self._extract_collection_candidates(body_html):
            matched = self._match_text_against_index(candidate)
            if matched:
                return matched
            if self._looks_plausible_franchise(candidate):
                return candidate

        text = BeautifulSoup(body_html, "html.parser").get_text(" ")
        return self._match_text_against_index(text)

    def _deduce_via_strategy(self, product) -> str:
        """Runs the store-specific franchise resolution strategy. Returns ""
        (not brand_name) when nothing is found, so the caller can still try the
        description-mining fallback before giving up entirely."""
        if self.franchise_source == "vendor":
            v = (product.get("vendor") or "").strip()
            if v and v.lower() not in self._VENDOR_IGNORE:
                return v
            return ""
        if self.franchise_source == "known_tag":
            return self._match_known(product)
        if self.franchise_source == "mapping_tags":
            return self._match_mappings(product)
        # default: game_tag
        slug = self._game_slug_from_tags(product.get("tags"))
        name = self._franchise_from_title(slug, product.get("title", ""))
        if name:
            return name
        if slug:
            return slug.title()
        return ""

    def _deduce_franchise(self, product):
        """Resolves the franchise for a product. Order of signals:
        1. The store-specific strategy (game tag / vendor / known list / tag mapping).
        2. The product's own description text and any embedded collection links
           (mines data we already fetch but previously ignored).
        3. Falls back to the store's brand_name (handled later by
           franchise_discovery.py via Wikidata verification + the 'Gamer Culture'
           catch-all)."""
        resolved = self._deduce_via_strategy(product)
        if resolved:
            return resolved

        from_description = self._match_description(product)
        if from_description:
            return from_description

        return self.brand_name

    # ------------------------------------------------------------------
    # Product parsing (product is a dict from products.json)
    # ------------------------------------------------------------------
    def parse_product(self, product, base_url):
        if not isinstance(product, dict):
            return "", 0.0, None, "", "", {}

        product_type = (product.get("product_type") or "").strip().lower()
        title = (product.get("title") or "").strip()
        handle = product.get("handle", "")

        if not any(h in product_type for h in self._APPAREL_HINTS):
            return "", 0.0, None, "", "", {}
        if not title or not handle:
            return "", 0.0, None, "", "", {}

        store_url = f"{self.store_root}/products/{handle}"

        prices, compares = [], []
        for v in product.get("variants", []) or []:
            try:
                if v.get("price") not in (None, ""):
                    prices.append(float(v["price"]))
                if v.get("compare_at_price") not in (None, ""):
                    compares.append(float(v["compare_at_price"]))
            except (TypeError, ValueError):
                continue
        if not prices:
            return "", 0.0, None, "", "", {}
        current_price = min(prices)
        original_price = None
        if compares:
            highest = max(compares)
            if highest > current_price:
                original_price = highest

        images = product.get("images", []) or []
        image_url = "https://example.com/placeholder.jpg"
        if images and images[0].get("src"):
            image_url = images[0]["src"]

        metadata = {"scraped_tag": self._deduce_franchise(product)}
        return title, current_price, original_price, store_url, image_url, metadata