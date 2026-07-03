# parsers/eightysixed.py
import re
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from parsers.base import BaseParser

class EightysixedParser(BaseParser):
    brand_name = "Eightysixed"
    url_pattern = "https://www.eightysixed.com/collections/all?page={page_num}"
    first_page_override = "https://www.eightysixed.com/collections/all"
    
    # THEME-AGNOSTIC SELECTOR: Target raw product links directly. 
    # This bypasses all custom compiled Tailwind classes completely!
    item_selector = "a[href*='/products/']"
    pagination_type = "paginated"
    max_pages = 100

    def __init__(self):
        super().__init__()
        self._seen_urls = set()

    def parse_product(self, product_el: BeautifulSoup, base_url: str) -> tuple:
        # 1. Deduplicate matching anchors pointing to the same product
        raw_href = product_el.get('href', '')
        store_url = urljoin(base_url, raw_href) if raw_href else base_url
        
        # Reset crawler memory state on page 1 runs
        if "page=" not in base_url or "page=1" in base_url:
            self._seen_urls.clear()

        # Reject standard gift card links and duplicate matches
        if store_url == base_url or store_url in self._seen_urls or "gift-card" in store_url.lower():
            return "", 0.0, None, "", "", {}
        
        self._seen_urls.add(store_url)

        # 2. Walk up to locate the closest product card div wrapper
        container = product_el.parent
        for _ in range(4):
            if container and container.name in ['div', 'li', 'section'] and (container.select_one("img") or container.select_one("[class*='price']")):
                break
            container = container.parent if container else None
            
        if not container:
            container = product_el

        # 3. Extract Product Name cleanly, avoiding badge overlays
        product_name = ""
        
        # Prioritize explicit title selectors first
        name_el = (
            container.select_one(".grid-product__title")
            or container.select_one(".product-card__title")
            or container.select_one(".product-item__title")
        )
        if name_el:
            product_name = name_el.get_text(strip=True)
            
        # If no explicit class titles found, grab text content of the primary anchor link
        if not product_name:
            raw_text = product_el.get_text(" ", strip=True)
            # Filter out badge elements nested inside the anchor text
            badge_texts = ["sale", "new", "sold out", "preorder"]
            words = [w for w in raw_text.split() if w.lower() not in badge_texts]
            product_name = " ".join(words)
            
        # Last resort fallback: Thumbnail Alt
        if not product_name or product_name.lower().strip() in ["sale", "new", "sold out", "preorder"]:
            img_el = container.select_one("img")
            if img_el and img_el.has_attr("alt"):
                product_name = img_el["alt"].strip()

        # Reject any residual dummy tags that slipped through name resolutions
        if not product_name or product_name.lower().strip() in ["sale", "new", "sold out", "preorder"]:
            return "", 0.0, None, "", "", {}

        # Clean brand suffixes
        if " - Eightysixed" in product_name:
            product_name = product_name.replace(" - Eightysixed", "").strip()

        # 4. Extract Price
        current_price = 0.0
        original_price = None

        price_el = (
            container.select_one(".grid-product__price")
            or container.select_one(".price-item--sale") 
            or container.select_one(".price") 
            or container.select_one("[class*='price']")
            or container.select_one("[class*='amount']")
        )
        price_text = ""
        if price_el:
            price_text = price_el.get_text(strip=True)
            
        if not price_text:
            for string in container.stripped_strings:
                if "$" in string or "£" in string or "€" in string:
                    price_text = string
                    break

        if price_text:
            original_price_el = (
                container.select_one(".grid-product__price--original") 
                or container.select_one(".price-item--regular") 
                or container.select_one("del")
            )
            if original_price_el:
                original_price = self.clean_price(original_price_el.get_text(strip=True))
                if original_price_el in price_el.children if price_el else False:
                    price_text = price_text.replace(original_price_el.get_text(strip=True), "")
            current_price = self.clean_price(price_text)

        # 5. Extract Thumbnail Image
        img_el = container.select_one("img")
        raw_image_url = ""
        if img_el:
            raw_image_url = img_el.get("src") or img_el.get("data-src") or ""
            if raw_image_url.startswith("//"):
                raw_image_url = "https:" + raw_image_url

        image_url = urljoin(base_url, raw_image_url) if raw_image_url else "https://example.com/placeholder.jpg"

        return product_name, current_price, original_price, store_url, image_url, {}