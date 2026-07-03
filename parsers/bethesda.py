# parsers/bethesda.py
from parsers.shopify_base import ShopifyJsonParser


class BethesdaParser(ShopifyJsonParser):
    brand_name = "Bethesda"
    store_root = "https://gear.bethesda.net"
    url_pattern = "https://gear.bethesda.net/collections/apparel/products.json?limit=250&page={page_num}"
    franchise_source = "game_tag"