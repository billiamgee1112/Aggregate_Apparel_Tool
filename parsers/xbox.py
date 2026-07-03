# parsers/xbox.py
from parsers.shopify_base import ShopifyJsonParser


class XboxGameStudiosParser(ShopifyJsonParser):
    brand_name = "Xbox Game Studios"
    store_root = "https://shop.xboxgamestudios.com"
    url_pattern = "https://shop.xboxgamestudios.com/collections/apparel/products.json?limit=250&page={page_num}"
    franchise_source = "game_tag"