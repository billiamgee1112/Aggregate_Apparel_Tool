# parsers/insert_coin.py
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from parsers.base import BaseParser

class InsertCoinParser(BaseParser):
    brand_name = "Insert Coin"
    url_pattern = "https://www.insertcoinclothing.com/all-products.html"
    item_selector = ".m-listing-item"
    pagination_type = "infinite_scroll"

    def parse_product(self, product: BeautifulSoup, base_url: str) -> tuple:
        store_url = base_url
        link_el = product.select_one(".m-listing-item-link") or product.select_one("a")
        if link_el and link_el.has_attr('href'):
            store_url = urljoin(base_url, link_el['href'])

        desc_el = product.select_one(".m-listing-item-desc")
        product_name_el = (
            product.select_one(".product-name")
            or (desc_el.select_one("h2") if desc_el else None)
            or (desc_el.select_one("h3") if desc_el else None)
            or (desc_el.select_one("h4") if desc_el else None)
            or product.select_one("h2")
            or product.select_one("h3")
        )
        product_name = product_name_el.get_text(strip=True) if product_name_el else ""

        price_el = product.select_one(".price") or product.select_one(".amount") or desc_el
        current_price = 0.0
        original_price = None

        if price_el:
            original_price_el = price_el.select_one("del") or product.select_one(".original-price")
            if original_price_el:
                original_price = self.clean_price(original_price_el.get_text(strip=True))
                price_text = price_el.get_text(strip=True).replace(original_price_el.get_text(strip=True), "")
            else:
                price_text = price_el.get_text(strip=True)
            current_price = self.clean_price(price_text.replace(product_name, ""))

        img_el = product.select_one("img")
        raw_image_url = ""
        if img_el:
            raw_image_url = img_el.get("src") or img_el.get("data-src") or ""
        image_url = urljoin(base_url, raw_image_url) if raw_image_url else "https://example.com/placeholder.jpg"

        return product_name, current_price, original_price, store_url, image_url