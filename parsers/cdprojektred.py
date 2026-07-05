from parsers.shopify_base import ShopifyJsonParser


class CdProjektRedParser(ShopifyJsonParser):
    """Official CD Projekt Red gear store. Products carry multiple overlapping
    "game : X" tags per franchise (e.g. "game : cyberpunk", "game :
    cyberpunk2077", "game : cyberpunk_edgerunners" all on Cyberpunk items;
    plain "game : TheWitcher" regardless of which numbered Witcher game) -
    the default game_tag title-matching strategy would produce inconsistent
    per-tag results, so franchise is resolved directly from the tag family
    instead. "Cyberpunk: Edgerunners" is the anime tie-in to the game (not an
    unrelated franchise, unlike anime excluded at other stores), so it's
    folded into the same "Cyberpunk 2077" tag as the game itself.
    """

    brand_name = "CD Projekt Red"
    store_root = "https://gear.cdprojektred.com"
    url_pattern = "https://gear.cdprojektred.com/collections/apparel/products.json?limit=250&page={page_num}"
    require_in_stock = True

    def _deduce_via_strategy(self, product) -> str:
        game_tags_text = " ".join(
            str(t).lower() for t in (product.get("tags") or []) if str(t).lower().strip().startswith("game")
        ).replace(" ", "")

        if "thewitcher" in game_tags_text:
            return "The Witcher"
        if "cyberpunk" in game_tags_text:
            return "Cyberpunk 2077"
        return ""
