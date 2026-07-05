from parsers.shopify_base import ShopifyJsonParser


class CultureKingsParser(ShopifyJsonParser):
    """Culture Kings is a general streetwear retailer, but curates a dedicated
    "gaming-merch" collection for its licensed video game collabs (73Studio,
    LOITER, Goat Crew, etc. collabs with Halo, Pokemon, Call of Duty, Star
    Wars Battlefront, Fallout, Warcraft, StarCraft, Mortal Kombat, and more).
    Vendor is just the collab print brand (not a franchise) and product_type
    is generic ("SS-Tees", "Hood"), so franchise resolution instead scans the
    title/tags against the shared franchise_mappings keyword table.
    """

    brand_name = "Culture Kings"
    store_root = "https://www.culturekings.com"
    url_pattern = "https://www.culturekings.com/collections/gaming-merch/products.json?limit=250&page={page_num}"
    franchise_source = "mapping_tags"

    # The "gaming-merch" collection also picks up a couple of non-gaming items:
    # New Era sports caps (a licensed baseball team snapback, not a game) and
    # Goat Crew's "Squid Game" tees (a Netflix show, not a video game).
    exclude_vendors = {"new era"}
    exclude_keywords = ["squid game"]

    # The live collection page hides sold-out items; the products.json feed
    # does not, so without this the site would show ~145 unpurchasable items.
    require_in_stock = True

