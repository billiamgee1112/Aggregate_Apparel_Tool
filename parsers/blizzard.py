# parsers/blizzard.py
from parsers.shopify_base import ShopifyJsonParser


class BlizzardParser(ShopifyJsonParser):
    brand_name = "Blizzard"
    store_root = "https://gear.blizzard.com"
    url_pattern = "https://gear.blizzard.com/collections/apparel/products.json?limit=250&page={page_num}"
    franchise_source = "known_tag"

    # Blizzard's fixed, rarely-changing franchise set (longest matched first).
    # NOTE: "Overwatch" (the original 2016 game) was shut down and fully
    # replaced by "Overwatch 2" in 2022 - there is no active standalone
    # "Overwatch" game anymore, so we deliberately do NOT track it as a
    # separate franchise (avoids splitting one live game's merch into two
    # tags). Titles that only say "Overwatch" with no "2" still resolve
    # correctly via the body_html description-mining fallback in
    # shopify_base.py, which reliably mentions "Overwatch 2" branding.
    known_franchises = [
        "World of Warcraft",
        "Warcraft",
        "Overwatch 2",
        "Diablo IV",
        "Diablo",
        "StarCraft II",
        "StarCraft",
        "Hearthstone",
        "Heroes of the Storm",
    ]