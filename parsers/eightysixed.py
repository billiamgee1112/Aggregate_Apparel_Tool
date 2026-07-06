# parsers/eightysixed.py
from parsers.base import BaseParser


class EightysixedParser(BaseParser):

    @property
    def brand_name(self) -> str:
        return "Eightysixed"

    @property
    def url_pattern(self) -> str:
        # Shopify's structured JSON product feed (bypasses JS-rendered HTML entirely)
        return "https://www.eightysixed.com/collections/all/products.json?limit=250&page={page_num}"

    @property
    def first_page_override(self) -> str:
        return None

    @property
    def item_selector(self) -> str:
        return ""  # Unused in JSON mode

    @property
    def pagination_type(self) -> str:
        return "shopify_json"

    @property
    def max_pages(self) -> int:
        return 10  # Stops automatically when the feed returns an empty product list

    # Product types worth keeping (wearable apparel only)
    _APPAREL_HINTS = [
        "shirt", "tee", "hoodie", "sweater", "sweatshirt", "jacket", "hat",
        "beanie", "cap", "sock", "short", "pant", "crewneck", "tank",
        "long sleeve", "apparel", "jersey", "pullover"
    ]

    def parse_product(self, product, base_url: str) -> tuple:
        # In JSON mode, 'product' is a dict from products.json (not a BeautifulSoup tag)
        if not isinstance(product, dict):
            return "", 0.0, None, "", "", {}

        product_type = (product.get("product_type") or "").strip().lower()
        title = (product.get("title") or "").strip()
        handle = product.get("handle", "")
        vendor = (product.get("vendor") or "").strip()

        # Keep only wearable apparel; reject stickers, pins, prints, accessories
        if not any(hint in product_type for hint in self._APPAREL_HINTS):
            return "", 0.0, None, "", "", {}

        if not title or not handle:
            return "", 0.0, None, "", "", {}

        store_url = f"https://www.eightysixed.com/products/{handle}"

        # Pricing from variants
        prices = []
        compare_prices = []
        for variant in product.get("variants", []) or []:
            try:
                raw_price = variant.get("price")
                if raw_price not in (None, ""):
                    prices.append(float(raw_price))
                raw_compare = variant.get("compare_at_price")
                if raw_compare not in (None, ""):
                    compare_prices.append(float(raw_compare))
            except (TypeError, ValueError):
                continue

        if not prices:
            return "", 0.0, None, "", "", {}

        current_price = min(prices)
        original_price = None
        if compare_prices:
            highest_compare = max(compare_prices)
            if highest_compare > current_price:
                original_price = highest_compare

        # Thumbnail image
        images = product.get("images", []) or []
        image_url = "https://example.com/placeholder.jpg"
        if images and images[0].get("src"):
            image_url = images[0]["src"]

        # 'vendor' is a clean, authoritative franchise signal (e.g. "Guilty Gear")
        metadata = {"scraped_tag": vendor, "product_type": product_type}

        return title, current_price, original_price, store_url, image_url, metadata