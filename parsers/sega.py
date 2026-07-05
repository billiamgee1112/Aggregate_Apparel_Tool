from parsers.shopify_base import ShopifyJsonParser


class SegaParser(ShopifyJsonParser):
    """Official SEGA shop. Uses the standard Shopify "game : <slug>" tags to
    identify the source franchise (Sonic, Jet Set Radio, Crazy Taxi, Shinobi,
    etc.), same as the default game_tag strategy. Many items in this
    collection are pre-order or permanently sold out, and the live collection
    page hides fully sold-out products, so only in-stock items are scraped.
    """

    brand_name = "SEGA"
    store_root = "https://shop.sega.com"
    url_pattern = "https://shop.sega.com/collections/clothing/products.json?limit=250&page={page_num}"
    require_in_stock = True
