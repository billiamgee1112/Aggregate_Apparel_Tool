# parsers/glitch_gear.py
import re
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from parsers.base import BaseParser

class GlitchGearParser(BaseParser):
    brand_name = "Glitch Gear"
    url_pattern = "https://www.glitchgear.com/collections/all?page={page_num}"
    first_page_override = "https://www.glitchgear.com/collections/all"
    
    item_selector = "li.grid__item, .product-item, .product-card, [class*='product-grid'] .grid-item"
    pagination_type = "paginated"
    max_pages = 100

    def parse_product(self, product: BeautifulSoup, base_url: str) -> tuple:
        link_el = (
            product.select_one("a[href*='/products/']") 
            or product.select_one("a[class*='title']") 
            or product.select_one("a")
        )
        store_url = base_url
        if link_el and link_el.has_attr('href'):
            store_url = urljoin(base_url, link_el['href'])

        product_name_el = (
            product.select_one(".product-item-meta__title")
            or product.select_one(".product-card__title")
            or product.select_one(".grid-view-item__title")
            or product.select_one("h3")
            or product.select_one(".title")
        )
        
        product_name = ""
        if product_name_el:
            product_name = product_name_el.get_text(strip=True)
            
        if not product_name:
            img_el = product.select_one("img")
            if img_el and img_el.has_attr("alt"):
                product_name = img_el["alt"].strip()

        if " - Glitch Gear" in product_name:
            product_name = product_name.replace(" - Glitch Gear", "").strip()

        current_price = 0.0
        original_price = None

        price_el = (
            product.select_one(".price-item--sale") 
            or product.select_one(".price") 
            or product.select_one("[class*='price']")
        )
        price_text = ""
        if price_el:
            price_text = price_el.get_text(strip=True)
            
        if not price_text:
            for string in product.stripped_strings:
                if "$" in string or "£" in string or "€" in string:
                    price_text = string
                    break

        if price_text:
            original_price_el = product.select_one(".price-item--regular") or product.select_one("del")
            if original_price_el:
                original_price = self.clean_price(original_price_el.get_text(strip=True))
                if price_el and original_price_el in price_el.children:
                    price_text = price_text.replace(original_price_el.get_text(strip=True), "")
            current_price = self.clean_price(price_text)

        # RECURSIVE REGEX PRICE HARVESTER
        if current_price == 0.0:
            found_prices = re.findall(r'[\$\£\€]\s*\d+(?:\.\d{2})?', product.get_text(" "))
            if found_prices:
                prices = sorted(list(set(self.clean_price(p) for p in found_prices)))
                if len(prices) == 1:
                    current_price = prices[0]
                elif len(prices) >= 2:
                    current_price = prices[0]
                    original_price = prices[-1]

        # Extract Thumbnail Image (sanitizing responsive lazy-loads)
        img_el = product.select_one("img")
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