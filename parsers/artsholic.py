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

    # Artsholic's "game-art" category also carries pure-anime product lines
    # with no video game tie-in (unlike e.g. Dragon Ball Z, which has actual
    # games like Budokai Tenkaichi) - these don't belong on a gaming apparel
    # site and are excluded outright rather than tagged.
    _EXCLUDED_TAG_SLUGS = {"demon-slayer", "jujutsu-kaisen"}
    # Belt-and-suspenders: the product_tag-X CSS class isn't reliably present
    # on every archive layout/product variant (e.g. "Shorts" listings), so we
    # also exclude based on the product title text itself.
    _EXCLUDED_NAME_KEYWORDS = ("jujutsu kaisen", "demon slayer")

    def parse_product(self, product: BeautifulSoup, base_url: str) -> tuple:
        classes = product.get("class", [])
        if any(cls.startswith("product_tag-") and cls.replace("product_tag-", "") in self._EXCLUDED_TAG_SLUGS for cls in classes):
            return "", 0.0, None, "", "", {}

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

        if any(kw in product_name.lower() for kw in self._EXCLUDED_NAME_KEYWORDS):
            return "", 0.0, None, "", "", {}

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