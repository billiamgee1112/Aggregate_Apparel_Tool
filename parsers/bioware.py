from parsers.shopify_base import ShopifyJsonParser


class BioWareParser(ShopifyJsonParser):
    """Official BioWare gear store. Uses the standard "game : <slug>" tags to
    identify Mass Effect vs Dragon Age products (same default game_tag
    strategy as other Bethesda/Xbox-style storefronts - no custom logic
    needed). A large fraction of the catalog is permanently/temporarily sold
    out, so only in-stock items are scraped.
    """

    brand_name = "BioWare"
    store_root = "https://gear.bioware.com"
    url_pattern = "https://gear.bioware.com/collections/apparel-1/products.json?limit=250&page={page_num}"
    require_in_stock = True
