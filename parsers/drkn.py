import re
from parsers.shopify_base import ShopifyJsonParser


class DrknParser(ShopifyJsonParser):
    """DRKN sells general streetwear/techwear AND licensed gaming collabs side
    by side in the same catalog - vendor is always just "DRKN" and
    product_type/tags are too generic ("T-shirt", "Hoodie", "ALL",
    "CLEARANCE") to reliably separate the two, so this parser does NOT scrape
    the full catalog. Instead it only fetches DRKN's own dedicated
    per-franchise gaming collections (confirmed via drkn.com/collections.json)
    and maps each collection directly to its known franchise - the store's
    own categorization is a first-party, trustworthy signal, and sidesteps
    having to guess from a mixed catalog of gaming and non-gaming apparel.
    """

    brand_name = "DRKN"
    store_root = "https://drkn.com"

    # Required by the ShopifyJsonParser interface, but unused directly here -
    # every actual fetch goes through collection_urls below instead.
    url_pattern = "https://drkn.com/collections/the-six-collection/products.json?limit=250&page={page_num}"

    _COLLECTION_FRANCHISES = {
        "the-six-collection": "Rainbow Six Siege",
        "6-siege-year-7": "Rainbow Six Siege",
        "drkn-x-sau-siege": "Rainbow Six Siege",
        "call-of-duty-1": "Call of Duty",
        "drkn-x-mwiii": "Call of Duty",
        "warzone": "Call of Duty",
        "drkn-x-diablo-iv": "Diablo",
        "drkn-x-pubg": "PUBG",
        "metal-hellsinger": "Metal: Hellsinger",
        "payday-3": "Payday",
        "watch-dogs-legion": "Watch Dogs",
    }

    collection_urls = [
        f"https://drkn.com/collections/{slug}/products.json?limit=250&page={{page_num}}"
        for slug in _COLLECTION_FRANCHISES
    ]

    _current_franchise = ""

    def parse_product(self, product, base_url):
        match = re.search(r"/collections/([a-z0-9\-]+)/", base_url or "")
        self._current_franchise = self._COLLECTION_FRANCHISES.get(match.group(1), "") if match else ""
        return super().parse_product(product, base_url)

    def _deduce_via_strategy(self, product) -> str:
        return self._current_franchise
