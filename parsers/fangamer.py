# parsers/fangamer.py
import re
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from parsers.base import BaseParser

class FangamerParser(BaseParser):
    brand_name = "Fangamer"
    url_pattern = "https://www.fangamer.com/collections/apparel?page={page_num}"
    first_page_override = "https://www.fangamer.com/collections/apparel"
    item_selector = ".item-view, .product-card"
    pagination_type = "paginated"
    max_pages = 15

    def parse_product(self, product: BeautifulSoup, base_url: str) -> tuple:
        store_url = base_url
        link_el = product.select_one("a") or (product if product.name == "a" else None)
        if link_el and link_el.has_attr('href'):
            store_url = urljoin(base_url, link_el['href'])

        product_name_el = (
            product.select_one(".item-view-title")
            or product.select_one(".product-card-title")
            or product.select_one("h3")
            or product.select_one("h4")
            or product.select_one(".title")
        )
        
        product_name = ""
        if product_name_el:
            product_name = product_name_el.get_text(strip=True)
        else:
            img_el = product.select_one("img")
            if img_el and img_el.has_attr("alt"):
                product_name = img_el["alt"].strip()
                
        if " - " in product_name:
            product_name = product_name.split(" - ")[0].strip()

        # Extract Prices
        current_price = 0.0
        original_price = None

        if link_el and link_el.has_attr("aria-label"):
            aria_label = link_el["aria-label"]
            price_patterns = re.findall(r'[\$\£\€]\d+(?:\.\d+)?', aria_label)
            
            if len(price_patterns) == 1:
                current_price = self.clean_price(price_patterns[0])
            elif len(price_patterns) >= 2:
                original_price = self.clean_price(price_patterns[0])
                current_price = self.clean_price(price_patterns[1])

        if current_price == 0.0:
            price_el = (
                product.select_one(".item-view-price") 
                or product.select_one(".price") 
                or product.select_one(".product-card-price") 
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
                original_price_el = price_el.select_one("del") if price_el else None
                if original_price_el:
                    original_price = self.clean_price(original_price_el.get_text(strip=True))
                    price_text = price_text.replace(original_price_el.get_text(strip=True), "")
                    
                current_price = self.clean_price(price_text)

        img_el = product.select_one("img")
        raw_image_url = ""
        if img_el:
            raw_image_url = img_el.get("src") or img_el.get("data-src") or ""
            if raw_image_url.startswith("//"):
                raw_image_url = "https:" + raw_image_url

        image_url = urljoin(base_url, raw_image_url) if raw_image_url else "https://example.com/placeholder.jpg"

        return product_name, current_price, original_price, store_url, image_url