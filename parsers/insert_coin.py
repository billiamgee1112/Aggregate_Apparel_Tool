# parsers/insert_coin.py
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from parsers.base import BaseParser

class InsertCoinParser(BaseParser):
    brand_name = "Insert Coin"
    url_pattern = "https://www.insertcoinclothing.com/all-products.html"
    item_selector = ".m-listing-item"
    pagination_type = "infinite_scroll"

    def parse_product(self, product_el: BeautifulSoup, base_url: str) -> tuple:
        # 1. Extract Details link
        link_el = product_el.select_one("a[href*='.html']") or product_el.select_one("a")
        store_url = urljoin(base_url, link_el['href']) if link_el and link_el.has_attr('href') else base_url

        # 2. Extract Product Name
        # Fall back to image alt or text of the first link if explicit elements don't exist
        product_name = ""
        if link_el:
            product_name = link_el.get_text(strip=True)
            
        if not product_name:
            img_el = product_el.select_one("img")
            if img_el and img_el.has_attr("alt"):
                product_name = img_el["alt"].strip()
                
        # Strip generic prefixes if necessary
        if "AVAILABLE FOR PREORDER" in product_name:
            product_name = product_name.replace("AVAILABLE FOR PREORDER", "").strip()

        # 3. Extract Price
        price_el = product_el.select_one(".price") or product_el.select_one(".amount")
        current_price = 0.0
        original_price = None

        if price_el:
            original_price_el = price_el.select_one("del") or price_el.select_one(".original-price")
            if original_price_el:
                original_price = self.clean_price(original_price_el.get_text(strip=True))
                price_text = price_el.get_text(strip=True).replace(original_price_el.get_text(strip=True), "")
            else:
                price_text = price_el.get_text(strip=True)
            current_price = self.clean_price(price_text)
        else:
            # Clean backup text matches inside the element strings
            for string in product_el.stripped_strings:
                if "$" in string or "£" in string or "€" in string:
                    current_price = self.clean_price(string)
                    break

        # 4. Extract Thumbnail
        img_el = product_el.select_one("img")
        raw_image_url = ""
        if img_el:
            raw_image_url = img_el.get("src") or img_el.get("data-src") or ""
        image_url = urljoin(base_url, raw_image_url) if raw_image_url else "https://example.com/placeholder.jpg"

        # 5. Extract Dynamic Store Game Tag (Solves automatic tracking!)
        scraped_tag = ""
        game_el = product_el.select_one(".m-listing-item__game") or product_el.select_one("[class*='game']")
        if game_el:
            scraped_tag = game_el.get_text(strip=True)

        metadata = {"scraped_tag": scraped_tag}

        return product_name, current_price, original_price, store_url, image_url, metadata