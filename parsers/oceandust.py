# parsers/oceandust.py
import re
from parsers.shopify_base import ShopifyJsonParser


class OceanDustParser(ShopifyJsonParser):
    brand_name = "OceanDust"
    store_root = "https://oceandust.co"
    url_pattern = "https://oceandust.co/collections/video-games/products.json?limit=250&page={page_num}"

    # Site relaunched behind Shopify's native password-gate page (the
    # password itself is displayed openly on the landing page as a
    # marketing "unlock the archive" gimmick, not real access control).
    # scraper.py submits this once per run before fetching any JSON feeds.
    store_password = "NOSTALGIA"

    # The relaunch also added Cloudflare bot-challenge protection in front
    # of products.json (seen returning a "Just a moment..." 429 challenge
    # page instead of JSON). A much slower, more human-paced request cadence
    # is less likely to trip it than the default 1-2.5s used by other stores.
    request_delay_range_ms = (5000, 9000)

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
