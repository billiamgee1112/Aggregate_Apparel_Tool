from urllib.parse import urljoin
from bs4 import BeautifulSoup
from parsers.base import BaseParser


class SquareEnixParser(BaseParser):
    """Official Square Enix NA store (BigCommerce/Stencil platform, not
    Shopify - no public products.json feed, so this uses standard paginated
    HTML scraping). Product titles consistently lead with the franchise name
    (e.g. "FINAL FANTASY XIV T-Shirt - GUESS WHO'S BACK?", "UNDERTALE x
    SQUARE ENIX - Sans and Chocobo Tee", "CHRONO TRIGGER x Lit Baff Apt. -
    Fade Black Tee"), so the shared franchise_mappings keyword substring
    match (via BaseParser's cascade) is sufficient without a custom title
    parser here.
    """

    brand_name = "Square Enix"
    url_pattern = "https://na.store.square-enix-games.com/merchandise/apparel?page={page_num}"
    first_page_override = "https://na.store.square-enix-games.com/merchandise/apparel"
    item_selector = "article.card"
    pagination_type = "paginated"
    max_pages = 6

    def parse_product(self, product: BeautifulSoup, base_url: str) -> tuple:
        store_url = base_url
        title_el = product.select_one("h3.prod-name a")
        link_el = title_el or product.select_one(".card-img-container a")
        if link_el and link_el.has_attr("href"):
            store_url = urljoin(base_url, link_el["href"])

        product_name = title_el.get_text(strip=True) if title_el else ""

        price_el = product.select_one(".price--withoutTax")
        current_price = self.clean_price(price_el.get_text(strip=True)) if price_el else 0.0

        original_price = None
        rrp_el = product.select_one(".price--non-sale, [data-product-non-sale-price-without-tax]")
        if rrp_el:
            rrp_text = rrp_el.get_text(strip=True)
            if rrp_text:
                original_price = self.clean_price(rrp_text)

        img_el = product.select_one("img.card-image")
        raw_image_url = ""
        if img_el:
            raw_image_url = img_el.get("data-src") or img_el.get("src") or ""
        image_url = urljoin(base_url, raw_image_url) if raw_image_url else "https://example.com/placeholder.jpg"

        metadata = {"scraped_tag": ""}

        return product_name, current_price, original_price, store_url, image_url, metadata
