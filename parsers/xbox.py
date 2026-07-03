# parsers/xbox.py
import re
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from parsers.base import BaseParser

class XboxGameStudiosParser(BaseParser):
    brand_name = "Xbox Game Studios"
    url_pattern = "https://shop.xboxgamestudios.com/collections/apparel?page={page_num}"
    first_page_override = "https://shop.xboxgamestudios.com/collections/apparel"
    
    # Target grid card wrappers directly
    item_selector = "li.grid__item, .product-card, .card-wrapper"
    pagination_type = "paginated"
    max_pages = 50

    def __init__(self):
        super().__init__()
        self._seen_urls = set()

    def parse_product(self, product_el: BeautifulSoup, base_url: str) -> tuple:
        # Find the primary product link inside this card container
        link_el = product_el.select_one("a[href*='/products/']") or product_el.select_one("a")
        if not link_el:
            return "", 0.0, None, "", "", {}

        raw_href = link_el.get('href', '')
        store_url = urljoin(base_url, raw_href) if raw_href else base_url
        
        if "page=" not in base_url or "page=1" in base_url:
            self._seen_urls.clear()

        if (store_url == base_url or 
            store_url in self._seen_urls or 
            "gift-card" in store_url.lower() or 
            "?variant=" in store_url):
            return "", 0.0, None, "", "", {}
        
        self._seen_urls.add(store_url)

        product_name = ""
        name_el = (
            product_el.select_one(".card__heading")
            or product_el.select_one(".card-information__text")
            or product_el.select_one(".product-card__title")
            or product_el.select_one("[class*='title']")
        )
        if name_el:
            product_name = name_el.get_text(strip=True)
            
        if not product_name:
            raw_text = link_el.get_text(" ", strip=True)
            badge_texts = ["sale", "new", "sold out", "preorder", "featured"]
            words = [w for w in raw_text.split() if w.lower() not in badge_texts]
            product_name = " ".join(words)
            
        if not product_name or product_name.lower().strip() in ["sale", "new", "sold out", "preorder"]:
            img_el = product_el.select_one("img")
            if img_el and img_el.has_attr("alt"):
                product_name = img_el["alt"].strip()

        if not product_name or product_name.lower().strip() in ["sale", "new", "sold out", "preorder"]:
            return "", 0.0, None, "", "", {}

        if " - Xbox Official Gear" in product_name:
            product_name = product_name.replace(" - Xbox Official Gear", "").strip()

        current_price = 0.0
        original_price = None

        price_el = (
            product_el.select_one(".price-item--sale")
            or product_el.select_one(".price-item--regular")
            or product_el.select_one(".price")
            or product_el.select_one("[class*='price']")
        )
        price_text = ""
        if price_el:
            price_text = price_el.get_text(strip=True)
            
        if not price_text:
            for string in product_el.stripped_strings:
                if "$" in string or "£" in string or "€" in string:
                    price_text = string
                    break

        if price_text:
            original_price_el = (
                product_el.select_one(".price-item--regular")
                or product_el.select_one("del")
                or product_el.select_one(".original-price")
            )
            if original_price_el:
                original_price = self.clean_price(original_price_el.get_text(strip=True))
                if price_el and original_price_el in price_el.children:
                    price_text = price_text.replace(original_price_el.get_text(strip=True), "")
            current_price = self.clean_price(price_text)

        # RECURSIVE REGEX PRICE HARVESTER 
        if current_price == 0.0:
            found_prices = re.findall(r'[\$\£\€]\s*\d+(?:\.\d{2})?', product_el.get_text(" "))
            if found_prices:
                prices = sorted(list(set(self.clean_price(p) for p in found_prices)))
                if len(prices) == 1:
                    current_price = prices[0]
                elif len(prices) >= 2:
                    current_price = prices[0]
                    original_price = prices[-1]

        # Extract Image Thumbnail (sanitizing responsive lazy-loads)
        img_el = product_el.select_one("img")
        raw_image_url = ""
        if img_el:
            lazy_candidates = [
                img_el.get("data-srcset"),
                img_el.get("data-src"),
                img_el.get("srcset"),
                img_el.get("src")
            ]
            for candidate in lazy_candidates:
                if candidate and not candidate.strip().startswith("data:image"):
                    raw_image_url = candidate
                    break
            
            if "," in raw_image_url:
                raw_image_url = raw_image_url.split(",")[0].strip().split(" ")[0]
                
            if raw_image_url.startswith("//"):
                raw_image_url = "https:" + raw_image_url

        image_url = urljoin(base_url, raw_image_url) if raw_image_url else "https://example.com/placeholder.jpg"

        return product_name, current_price, original_price, store_url, image_url, {}