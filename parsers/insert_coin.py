# parsers/insert_coin.py
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from parsers.base import BaseParser

class InsertCoinParser(BaseParser):
    brand_name = "Insert Coin"
    url_pattern = "https://www.insertcoinclothing.com/all-products.html?p=all"
    first_page_override = "https://www.insertcoinclothing.com/all-products.html?p=all"
    
    # STRICT SELECTOR: Restricting strictly to main clothing grid cards
    item_selector = ".m-listing-item"
    pagination_type = "paginated"
    max_pages = 1

    # Badge/UI text that sometimes appears as a stray text node and must never
    # be mistaken for a franchise/game label
    _BADGE_STOPWORDS = {
        "new", "sale", "sold out", "preorder", "available for preorder",
        "back in stock", "low stock", "coming soon",
        # SpecialEffect/GameBlast/OSD are real charity gaming-fundraiser event
        # tie-ins Insert Coin sometimes labels products with, not franchises.
        "specialeffect", "special effect", "gameblast", "osd"
    }

    def _extract_game_label(self, product_el: BeautifulSoup, product_name: str) -> str:
        """Extracts the store's own franchise/game label for this card.
        Insert Coin renders this as a bare <h3> tag (e.g.
        '<h3>Like A Dragon: Infinite Wealth</h3>') with no distinguishing class,
        separate from the product title. Tries class-based guesses first (in
        case a differently-styled card variant exists), then targets any <h3>
        whose text isn't the product name, then a conservative text heuristic."""
        class_candidates = [
            ".m-listing-item__game",
            ".m-listing-item__brand",
            ".m-listing-item__subtitle",
            ".m-listing-item__series",
            ".m-listing-item__category",
            "[class*='game']",
            "[class*='brand']",
            "[class*='subtitle']",
            "[class*='series']",
        ]
        for sel in class_candidates:
            el = product_el.select_one(sel)
            if el:
                text = el.get_text(strip=True)
                if text and text.lower() != product_name.lower():
                    return text

        # CONFIRMED PATTERN: the franchise/game name lives in a bare <h3> tag,
        # separate from the product title. Find any h3 whose text isn't the
        # product name itself.
        for h3 in product_el.find_all("h3"):
            text = h3.get_text(strip=True)
            if text and text.lower() != product_name.lower():
                return text

        # Conservative freeform fallback for any remaining card layout variants
        for el in product_el.find_all(["span", "div", "p", "h4", "h5", "h6"]):
            text = el.get_text(strip=True)
            if not text or len(text) > 60:
                continue
            low = text.lower()
            if low == product_name.lower():
                continue
            if low in self._BADGE_STOPWORDS:
                continue
            if any(sym in text for sym in ("$", "£", "€")):
                continue
            if len(text.split()) > 8:
                continue
            return text

        return ""

    def parse_product(self, product_el: BeautifulSoup, base_url: str) -> tuple:
        # 1. Extract Details link
        link_el = product_el.select_one("a[href*='.html']") or product_el.select_one("a")
        store_url = urljoin(base_url, link_el['href']) if link_el and link_el.has_attr('href') else base_url

        # 2. Extract Product Name cleanly using designated classes
        product_name = ""
        title_el = (
            product_el.select_one(".m-listing-item__title") 
            or product_el.select_one("[class*='title']")
            or product_el.select_one("h2")
        )
        
        if title_el:
            product_name = title_el.get_text(strip=True)
            
        if not product_name and link_el:
            raw_text = link_el.get_text(strip=True)
            product_name = raw_text
            
        if not product_name:
            img_el = product_el.select_one("img")
            if img_el and img_el.has_attr("alt"):
                product_name = img_el["alt"].strip()
                
        # Strip generic prefixes if necessary
        if "AVAILABLE FOR PREORDER" in product_name:
            product_name = product_name.replace("AVAILABLE FOR PREORDER", "").strip()

        # 3. Extract Price
        price_el = (
            product_el.select_one(".price") 
            or product_el.select_one(".amount")
            or product_el.select_one("[class*='price']")
        )
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

        # 5. Extract Dynamic Store Game Tag (the store's own franchise categorization).
        # Mystery/randomized bundle products (e.g. "Random Hoodie", "Random Tee"
        # under /bundles/) have no single real franchise by design - skip label
        # extraction entirely and pin them directly to the site's "Gamer
        # Culture" catch-all. (Previously left as "" to fall through to the
        # generic title-tokenizer/URL-slug guesser, but that naively grabbed
        # the literal leading word "Random" from the product name as if it
        # were a franchise - fixed by short-circuiting here instead.)
        if "/bundles/" in store_url:
            scraped_tag = "Gamer Culture"
        else:
            scraped_tag = self._extract_game_label(product_el, product_name)

        metadata = {"scraped_tag": scraped_tag}

        return product_name, current_price, original_price, store_url, image_url, metadata