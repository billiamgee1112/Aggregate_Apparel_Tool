from parsers.shopify_base import ShopifyJsonParser


class SansheeParser(ShopifyJsonParser):
    """Sanshee's apparel collection covers licensed merch for many indie/mid-size
    publishers (BioWare, Atlus, ConcernedApe, Re-Logic, etc.) plus Sanshee's own
    generic branded apparel line (excluded - not tied to any game) and a handful
    of non-apparel accessories (lanyards/wrist straps) that slip into the
    collection despite carrying a generic "Apparel" marketing tag.

    Titles consistently follow a "Franchise - Item Name" pattern, but a few
    don't (e.g. "Anthem Emblem Tee - White" splits on color, not franchise;
    "Terraria Arcade Battle Tee" has no dash at all) - so keyword-mapping
    matching against the full title/tags is tried first, with the dash-prefix
    used only as a fallback for titles keyword matching can't resolve.
    """

    brand_name = "Sanshee"
    store_root = "https://sanshee.com"
    url_pattern = "https://sanshee.com/collections/apparel/products.json?limit=250&page={page_num}"
    require_in_stock = True

    # Sanshee's own generic branded apparel line - not a game franchise.
    exclude_vendors = {"sanshee"}
    # Lanyards/wrist straps carry a generic "Apparel" marketing tag that would
    # otherwise pass the shared apparel-type filter despite not being clothing.
    exclude_keywords = ["lanyard", "wrist strap"]

    def _deduce_via_strategy(self, product) -> str:
        matched = self._match_mappings(product)
        if matched:
            return matched

        title = product.get("title", "") or ""
        if " - " not in title:
            return ""
        prefix = title.split(" - ", 1)[0].strip()
        if prefix.lower() == "sanshee":
            return ""
        return prefix
