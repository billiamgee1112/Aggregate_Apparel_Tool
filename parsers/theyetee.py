from parsers.shopify_base import ShopifyJsonParser


class TheYeteeParser(ShopifyJsonParser):
    """The Yetee's apparel collection uses the vendor field as the franchise
    name directly for most products (e.g. vendor "Hollow Knight", "Stardew
    Valley"), which makes this store simple - EXCEPT: a chunk of the catalog
    is creator-owned art with no game tie-in at all (personal artist/brand
    names used as the vendor, e.g. "Miski", "Marc Junker", "ProZD",
    "SUPERJUMBO" - confirmed via the store's own "artist_X" tags), plus The
    Yetee's own generic brand line and Games Done Quick charity-event tees
    (not tied to one consistent franchise) - all excluded outright. A few
    publisher/studio vendors (Red Hook Studios, Heart Machine, Armor Games)
    aren't franchises themselves, so those are mapped to their flagship game
    via the store's own game-specific tags.
    """

    brand_name = "The Yetee"
    store_root = "https://theyetee.com"
    url_pattern = "https://theyetee.com/collections/apparel/products.json?limit=250&page={page_num}"
    require_in_stock = True

    # Creator-owned art / non-franchise brands (not tied to any game) and The
    # Yetee's own generic merch line - confirmed via the store's own
    # "artist_X" tags or clearly personal-name/meme-brand vendors.
    exclude_vendors = {
        "the yetee", "angyfrog", "astrawitch", "chilluminati", "gazola",
        "marc junker", "miski", "natasha petrovic", "pigboom", "pixel eyebat",
        "prozd", "sorry we're closed", "thanuki", "superjumbo",
        "sgdq 2026",
    }

    # Publisher/studio names (not franchises themselves) mapped to their
    # flagship game, confirmed via the store's own game-specific tags.
    _VENDOR_OVERRIDES = {
        "red hook studios": "Darkest Dungeon",
        "heart machine": "Hyper Light Drifter",
        "armor games": "In Stars and Time",
    }

    def _deduce_via_strategy(self, product) -> str:
        vendor = (product.get("vendor") or "").strip()
        override = self._VENDOR_OVERRIDES.get(vendor.lower())
        if override:
            return override
        return vendor
