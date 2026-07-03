# parsers/blizzard.py
from parsers.shopify_base import ShopifyJsonParser


class BlizzardParser(ShopifyJsonParser):
    brand_name = "Blizzard"
    store_root = "https://gear.blizzard.com"
    url_pattern = "https://gear.blizzard.com/collections/apparel/products.json?limit=250&page={page_num}"
    franchise_source = "known_tag"

    # Blizzard's fixed, rarely-changing franchise set (longest matched first)
    known_franchises = [
        "World of Warcraft",
        "Warcraft",
        "Overwatch 2",
        "Overwatch",
        "Diablo IV",
        "Diablo",
        "StarCraft II",
        "StarCraft",
        "Hearthstone",
        "Heroes of the Storm",
    ]