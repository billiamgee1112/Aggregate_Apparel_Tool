# parsers/bethesda.py
import re
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from parsers.base import BaseParser

class BethesdaParser(BaseParser):
    brand_name = "Bethesda"
    url_pattern = "https://gear.bethesda.net/collections/apparel?page={page_num}"
    first_page_override = "https://gear.bethesda.net/collections/apparel"
    
    # THEME-AGNOSTIC SELECTOR: Target raw product links directly.
    # Bypasses complex grid layout structures across changing storefront themes.
    item_selector = "a[href*='/products/']"
    pagination_type = "paginated"
    max_pages = 50

    def __init__(self):
        super().__init__()
        self._seen_urls = set()

    def parse_product(self, product_el: BeautifulSoup, base_url: str) -> tuple:
        # 1. Extract Details and Deduplicate
        raw_href = product_el.get('href', '')
        store_url = urljoin(base_url, raw_href) if raw_href else base_url
        
        # Reset local cache state on first-page boundaries
        if "page=" not in base_url or "page=1" in base_url:
            self._seen_urls.clear()

        # Filter out gift card variations or pagination parameters
        if (store_url == base_url or 
            store_url in self._seen_urls or 
            "gift-card" in store_url.lower() or 
            "?variant=" in store_url):
            return "", 0.0, None, "", "", {}
        
        self._seen_urls.add(store_url)

        # 2. Walk up to locate the main product card container
        container = product_el.parent
        for _ in range(4):
            if container and container.name in ['div', 'li', 'section'] and (container.select_one("img") or container.select_one("[class*='price']")):
                break
            container = container.parent if container else None
            
        if not container:
            container = product_el

        # 3. Clean Product Name extraction
        product_name = ""
        
        # Look for explicit titles or headers
        name_el = (
            container.select_one(".product-card__title")
            or container.select_one(".card__heading")  # Standard for Shopify Dawn
            or container.select_one(".title")
            or container.select_one("[class*='title']")
        )
        if name_el:
            product_name = name_el.get_text(strip=True)
            
        # Refined text-scanning fallback ignoring promotional words
        if not product_name:
            raw_text = product_el.get_text(" ", strip=True)
            badge_texts = ["sale", "new", "sold out", "preorder", "exclusive"]
            words = [w for w in raw_text.split() if w.lower() not in badge_texts]
            product_name = " ".join(words)
            
        # Final image tag alt-attribute fallback lookup
        if not product_name or product_name.lower().strip() in ["sale", "new", "sold out", "preorder"]:
            img_el = container.select_one("img")
            if img_el and img_el.has_attr("alt"):
                product_name = img_el["alt"].strip()

        # Exclude nodes matching overlay badges
        if not product_name or product_name.lower().strip() in ["sale", "new", "sold out", "preorder"]:
            return "", 0.0, None, "", "", {}

        # Strip standard suffix labels
        if " - Bethesda Gear Store" in product_name:
            product_name = product_name.replace(" - Bethesda Gear Store", "").strip()

        # 4. Extract Pricing
        current_price = 0.0
        original_price = None

        # Look for Shopify price tags
        price_el = (
            container.select_one(".price-item--sale")
            or container.select_one(".price-item--regular")
            or container.select_one(".price")
            or container.select_one("[class*='price']")
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
                container.select_one(".price-item--regular")
                or container.select_one("del")
                or container.select_one(".original-price")
            )
            if original_price_el:
                original_price = self.clean_price(original_price_el.get_text(strip=True))
                # Only clean the parsed text output if regular price is concatenated inside the active node
                if price_el and original_price_el in price_el.children:
                    price_text = price_text.replace(original_price_el.get_text(strip=True), "")
            current_price = self.clean_price(price_text)

        # 5. Extract Image Thumbnail (sanitizing CDN relative protocols)
        img_el = container.select_one("img")
        raw_image_url = ""
        if img_el:
            raw_image_url = img_el.get("src") or img_el.get("data-src") or ""
            if raw_image_url.startswith("//"):
                raw_image_url = "https:" + raw_image_url

        image_url = urljoin(base_url, raw_image_url) if raw_image_url else "https://example.com/placeholder.jpg"

        return product_name, current_price, original_price, store_url, image_url, {}