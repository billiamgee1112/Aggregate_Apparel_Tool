# parsers/glitch_gear.py
from parsers.shopify_base import ShopifyJsonParser


class GlitchGearParser(ShopifyJsonParser):
    brand_name = "Glitch Gear"
    store_root = "https://www.glitchgear.com"
    url_pattern = "https://www.glitchgear.com/collections/all/products.json?limit=250&page={page_num}"
    franchise_source = "mapping_tags"
    require_in_stock = True