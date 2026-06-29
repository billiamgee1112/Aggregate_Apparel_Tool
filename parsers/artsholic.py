# parsers/artsholic.py
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from parsers.base import BaseParser

class ArtsholicParser(BaseParser):
    brand_name = "Artsholic"
    url_pattern = "https://www.artsholic.com/product-category/game-art/page/{page_num}/"
    first_page_override = "https://www.artsholic.com/product-category/game-art/"
    item_selector = "li.product, .product, .product-grid-item, .ast-article-single"
    pagination_type = "paginated"
    max_pages = 50

    def parse_product(self, product: BeautifulSoup, base_url: str) -> tuple:
        store_url = base_url
        link_el = product.select_one("a[href*='/product/']") or product.select_one("a")
        if link_el and link_el.has_attr('href'):
            store_url = urljoin(base_url, link_el['href'])

        product_name_el = (
            product.select_one(".woocommerce-loop-product__title")
            or product.select_one("h2")
            or product.select_one("h3")
        )
        product_name = product_name_el.get_text(strip=True) if product_name_el else ""

        price_el = product.select_one(".price")
        current_price = 0.0
        original_price = None

        if price_el:
            original_price_el = price_el.select_one("del")
            current_price_el = price_el.select_one("ins") or price_el
            
            if original_price_el:
                original_price = self.clean_price(original_price_el.get_text(strip=True))
            if current_price_el:
                current_price = self.clean_price(current_price_el.get_text(strip=True))

        img_el = product.select_one("img")
        raw_image_url = ""
        if img_el:
            raw_image_url = img_el.get("src") or img_el.get("data-src") or ""
            
        image_url = urljoin(base_url, raw_image_url) if raw_image_url else "https://example.com/placeholder.jpg"

        return product_name, current_price, original_price, store_url, image_url