from parsers.shopify_base import ShopifyJsonParser


class AtariParser(ShopifyJsonParser):
    """Atari's official apparel collection is mostly generic "Atari Club"
    branded nostalgia merch (Fuji logo, hardware references like Jaguar/2600/
    Intellivision/VCS) with no specific game tie-in - these fall back to the
    generic "Atari" brand tag. A smaller set of items reference specific
    classic games directly (Pong, Centipede, Bubsy, Missile Command, Yars'
    Revenge) or are RollerCoaster Tycoon merch (identified via vendor or the
    store's own "rct" tag, since not every RCT item is tagged consistently).
    A couple of "Footwear" (slides) products slip into the collection despite
    carrying a generic "Apparel & Accessories" marketing tag that would
    otherwise pass the shared apparel-type filter.
    """

    brand_name = "Atari"
    store_root = "https://atari.com"
    url_pattern = "https://atari.com/collections/all-apparel/products.json?limit=250&page={page_num}"
    require_in_stock = True

    def parse_product(self, product, base_url):
        if isinstance(product, dict) and (product.get("product_type") or "").strip().lower() == "footwear":
            return "", 0.0, None, "", "", {}
        return super().parse_product(product, base_url)

    def _deduce_via_strategy(self, product) -> str:
        tags = [str(t).lower() for t in (product.get("tags") or [])]
        vendor = (product.get("vendor") or "").strip()
        if "rct" in tags or vendor == "RollerCoaster Tycoon":
            return "RollerCoaster Tycoon"

        matched = self._match_mappings(product)
        if matched:
            return matched

        return "Atari"
