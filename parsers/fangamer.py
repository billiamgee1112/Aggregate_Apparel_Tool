# parsers/fangamer.py
from parsers.shopify_base import ShopifyJsonParser


class FangamerParser(ShopifyJsonParser):
    brand_name = "Fangamer"
    store_root = "https://www.fangamer.com"
    url_pattern = "https://www.fangamer.com/collections/apparel/products.json?limit=250&page={page_num}"
    franchise_source = "vendor"