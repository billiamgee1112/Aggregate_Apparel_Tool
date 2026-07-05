import re
from parsers.shopify_base import ShopifyJsonParser


class IgnParser(ShopifyJsonParser):
    """IGN's official store apparel collection mixes anime, movies, TV shows,
    comics, and tabletop games alongside actual video games (e.g. Star Wars
    apparel here is tagged "genre : Movies"/"genre : TV Series", NOT video
    games, despite Star Wars games existing elsewhere). Only products tagged
    "genre : Video Games" are scraped. Those products also carry their own
    first-party "franchise : X" tag (e.g. "franchise : The Legend of Zelda"),
    which is trusted directly rather than guessed from the title.
    """

    brand_name = "IGN"
    store_root = "https://store.ign.com"
    url_pattern = "https://store.ign.com/collections/apparel/products.json?limit=250&page={page_num}"
    require_tags = ["genre : Video Games"]

    def _deduce_via_strategy(self, product) -> str:
        for t in (product.get("tags") or []):
            m = re.match(r"\s*franchise\s*:\s*(.+)$", str(t), re.IGNORECASE)
            if m:
                name = m.group(1).strip()
                # IGN's own generic merch line, not an actual game franchise -
                # let this fall through to the description-mining fallback
                # (and ultimately the brand_name fallback, which is "IGN"
                # anyway) rather than treating it as a resolved franchise.
                if name and name.lower() != "ign":
                    return name
        return ""
