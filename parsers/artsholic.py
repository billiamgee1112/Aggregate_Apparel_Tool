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

    # NOTE (2026-07-06): Artsholic's "game-art" category also carries some
    # pure-anime product lines with no video game tie-in (e.g. Demon Slayer,
    # Jujutsu Kaisen, Akira, One Piece, Black Clover, Solo Leveling have all
    # shown up here at various points). A previous automated exclusion list
    # was tried here and reverted per user preference - an "anime" pattern
    # is too easy to over-broaden and risks catching legitimate anime-styled
    # GAMES (e.g. Genshin Impact) as false positives. Non-game anime items
    # are now removed manually (direct DB delete) as they're spotted,
    # instead of being auto-excluded at scrape time.

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

        # WooCommerce Deep-Category Class Hack (Auto-mapping!)
        scraped_tag = ""
        classes = product.get("class", [])
        for cls in classes:
            if cls.startswith("product_tag-"):
                tag_slug = cls.replace("product_tag-", "")
                
                # Filter out generic tags so we lock onto actual game names
                generic_tags = {
                    "shirt", "hoodie", "jacket", "sweater", "sweatshirt", "top", "tee", 
                    "shorts", "pants", "caps", "clothing", "apparel", "game-art", "art"
                }
                if tag_slug not in generic_tags:
                    # e.g., product_tag-doom-eternal -> "Doom Eternal"
                    scraped_tag = " ".join(part.capitalize() for part in tag_slug.split("-"))
                    break

        metadata = {"scraped_tag": scraped_tag}

        return product_name, current_price, original_price, store_url, image_url, metadata