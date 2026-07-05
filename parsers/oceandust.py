# parsers/oceandust.py
import re
from parsers.shopify_base import ShopifyJsonParser


class OceanDustParser(ShopifyJsonParser):
    brand_name = "OceanDust"
    store_root = "https://oceandust.co"
    url_pattern = "https://oceandust.co/collections/video-games/products.json?limit=250&page={page_num}"

    # Titles follow a strict "Video Games '<Franchise Name>' <Product Type>"
    # pattern (e.g. "Video Games 'Bayonetta' T-Shirt", "Video Games 'Crash
    # Bandicoot: Warped' Oversized Hoodie") - the franchise name is always
    # wrapped in single quotes. None of the base class's built-in strategies
    # fit here: 'vendor' is just "ODMPOD" (the print-on-demand fulfillment
    # platform, not a franchise), and 'tags' are only generic ("T-Shirt",
    # "Video Game") with zero franchise info. So we override the strategy
    # dispatch entirely with a title-regex extraction instead.
    franchise_source = "game_tag"  # unused - _deduce_via_strategy is overridden below

    # Greedy match: some franchise names contain an apostrophe themselves
    # (e.g. "Dante's Inferno"), so greedy .+ extends to the LAST quote in the
    # title (the closing delimiter) rather than stopping at the first one.
    _TITLE_PATTERN = re.compile(r"Video Games\s*'(.+)'")

    def _deduce_via_strategy(self, product) -> str:
        title = (product.get("title") or "").strip()
        m = self._TITLE_PATTERN.search(title)
        if m:
            return m.group(1).strip()
        return ""
