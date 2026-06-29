# scraper.py
import os
import json
import asyncio
import re
from dotenv import load_dotenv
from bs4 import BeautifulSoup
from models import GamingClothingItem
from urllib.parse import urljoin, urlparse
from playwright.async_api import async_playwright
from database import init_db, save_products_to_db

print("Script started.")
# Load environment variables
load_dotenv()

NON_CLOTHING_KEYWORDS = [
    "pin", "magnet", "keyring", "mug", "umbrella", "blanket", 
    "cushion", "sticker", "badge", "poster", "towel", "socks"
]

async def scroll_page_to_end(page, item_selector, max_attempts=15):
    """Gradually scrolls the page to trigger infinite scrolling."""
    prev_item_count = 0
    no_change_runs = 0

    print("Executing target-oriented infinite scrolling loop...")
    for attempt in range(max_attempts):
        locator = page.locator(item_selector)
        current_items = await locator.count()
        print(f"Attempt {attempt + 1}: Live items found in browser DOM = {current_items}")

        if current_items > prev_item_count:
            no_change_runs = 0
            prev_item_count = current_items
            try:
                last_item = locator.last
                await last_item.scroll_into_view_if_needed()
            except Exception as e:
                print(f"Error scrolling: {e}")
        else:
            no_change_runs += 1

        # Stop scrolling if we reached the absolute bottom
        if no_change_runs >= 3:
            print("All dynamic products appear to have loaded successfully!")
            break

        await page.wait_for_timeout(2000)


def clean_price(price_text):
    """Parses decimal floats from string content."""
    price_text = price_text.replace("£", "").replace("$", "").replace(",", "").strip()
    cleaned_digits = ''.join(c for char in price_text.split() for c in char if c.isdigit() or c == '.')
    return float(cleaned_digits) if cleaned_digits else 0.0


def extract_franchise_tag(store_url, fallback="Geek Apparel"):
    """Deduces a clean franchise name using URL segments."""
    parsed_path = urlparse(store_url).path
    path_segments = [seg for segment in parsed_path.split('/') if (seg := segment.replace('.html', '').strip())]
    if path_segments:
        if path_segments[0].lower() in ["products", "collections", "product"] and len(path_segments) > 1:
            return " ".join(segment.capitalize() for segment in path_segments[1].split('-'))
        return " ".join(segment.capitalize() for segment in path_segments[0].split('-'))
    return fallback


def parse_insert_coin_product(product, base_url):
    """Insert Coin custom parser."""
    store_url = base_url
    link_el = product.select_one(".m-listing-item-link") or product.select_one("a")
    if link_el and link_el.has_attr('href'):
        store_url = urljoin(base_url, link_el['href'])

    desc_el = product.select_one(".m-listing-item-desc")
    product_name_el = (
        product.select_one(".product-name")
        or (desc_el.select_one("h2") if desc_el else None)
        or (desc_el.select_one("h3") if desc_el else None)
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
            original_price = clean_price(original_price_el.get_text(strip=True))
            price_text = price_el.get_text(strip=True).replace(original_price_el.get_text(strip=True), "")
        else:
            price_text = price_el.get_text(strip=True)
        current_price = clean_price(price_text.replace(product_name, ""))

    img_el = product.select_one("img")
    raw_image_url = ""
    if img_el:
        raw_image_url = img_el.get("src") or img_el.get("data-src") or ""
    image_url = urljoin(base_url, raw_image_url) if raw_image_url else "https://example.com/placeholder.jpg"

    return product_name, current_price, original_price, store_url, image_url


def parse_artsholic_product(product, base_url):
    """Artsholic standard WooCommerce parser."""
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
            original_price = clean_price(original_price_el.get_text(strip=True))
        if current_price_el:
            current_price = clean_price(current_price_el.get_text(strip=True))

    img_el = product.select_one("img")
    raw_image_url = ""
    if img_el:
        raw_image_url = img_el.get("src") or img_el.get("data-src") or ""
        
    image_url = urljoin(base_url, raw_image_url) if raw_image_url else "https://example.com/placeholder.jpg"

    return product_name, current_price, original_price, store_url, image_url



def parse_fangamer_product(product, base_url):
    """Fangamer custom parser targeting .item-view cards."""
    store_url = base_url
    link_el = product.select_one("a") or (product if product.name == "a" else None)
    if link_el and link_el.has_attr('href'):
        store_url = urljoin(base_url, link_el['href'])

    # 1. Extract Product Name
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

    # 2. Extract Prices (Using high-reliability aria-label parsing)
    current_price = 0.0
    original_price = None

    if link_el and link_el.has_attr("aria-label"):
        aria_label = link_el["aria-label"]
        # Find all currency patterns (e.g., $32, $36$18, $36, $18, £40)
        price_patterns = re.findall(r'[\$\£\€]\d+(?:\.\d+)?', aria_label)
        
        if len(price_patterns) == 1:
            current_price = clean_price(price_patterns[0])
        elif len(price_patterns) >= 2:
            # Discount model: first price is original, second price is discounted current
            original_price = clean_price(price_patterns[0])
            current_price = clean_price(price_patterns[1])

    # Fallback to standard DOM search if aria-label extraction fails
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
                original_price = clean_price(original_price_el.get_text(strip=True))
                price_text = price_text.replace(original_price_el.get_text(strip=True), "")
                
            current_price = clean_price(price_text)

    # 3. Extract Image URL
    img_el = product.select_one("img")
    raw_image_url = ""
    if img_el:
        raw_image_url = img_el.get("src") or img_el.get("data-src") or ""
        if raw_image_url.startswith("//"):
            raw_image_url = "https:" + raw_image_url

    image_url = urljoin(base_url, raw_image_url) if raw_image_url else "https://example.com/placeholder.jpg"

    return product_name, current_price, original_price, store_url, image_url


async def scrape_store():
    stores_to_scrape = [
        {
            "brand_name": "Insert Coin",
            "url_pattern": "https://www.insertcoinclothing.com/all-products.html",
            "item_selector": ".m-listing-item",
            "parser": parse_insert_coin_product,
            "pagination_type": "infinite_scroll"
        },
        {
            "brand_name": "Artsholic",
            "url_pattern": "https://www.artsholic.com/product-category/game-art/page/{page_num}/",
            "first_page_override": "https://www.artsholic.com/product-category/game-art/",
            "item_selector": "li.product, .product, .product-grid-item, .ast-article-single", 
            "parser": parse_artsholic_product,
            "pagination_type": "paginated",
            "max_pages": 50
        },
        {
            "brand_name": "Fangamer",
            "url_pattern": "https://www.fangamer.com/collections/apparel?page={page_num}",
            "first_page_override": "https://www.fangamer.com/collections/apparel",
            "item_selector": ".item-view, .product-card",  # Updated to target .item-view
            "parser": parse_fangamer_product,
            "pagination_type": "paginated",
            "max_pages": 15
        }
    ]

    all_scraped_items = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": 1280, "height": 1000},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        for store in stores_to_scrape:
            print(f"\n--- Scraping {store['brand_name']} ---")
            
            if store["pagination_type"] == "infinite_scroll":
                target_url = store["url_pattern"]
                print(f"Opening {target_url}...")
                try:
                    await page.goto(target_url, wait_until="networkidle")
                    await scroll_page_to_end(page, store["item_selector"])
                    page_content = await page.content()
                    
                    soup = BeautifulSoup(page_content, "html.parser")
                    product_elements = soup.select(store["item_selector"])
                    print(f"Found {len(product_elements)} items for {store['brand_name']}.")
                    
                    for idx, product_el in enumerate(product_elements):
                        try:
                            name, price, orig_price, s_url, img_url = store["parser"](product_el, target_url)
                            if not name or any(term in name.lower() for term in NON_CLOTHING_KEYWORDS):
                                continue
                            
                            item = GamingClothingItem(
                                product_name=name,
                                current_price=price,
                                original_price=orig_price,
                                store_url=s_url,
                                image_url=img_url,
                                brand_name=store["brand_name"],
                                franchise_tags=[extract_franchise_tag(s_url, fallback=store["brand_name"])]
                            )
                            all_scraped_items.append(item)
                            print(f"[{store['brand_name']}] Processed: {name} | Price: ${price}")
                        except Exception:
                            continue
                except Exception as e:
                    print(f"Error scraping {store['brand_name']}: {e}")

            elif store["pagination_type"] == "paginated":
                for page_num in range(1, store["max_pages"] + 1):
                    if page_num == 1 and "first_page_override" in store:
                        target_url = store["first_page_override"]
                    else:
                        target_url = store["url_pattern"].format(page_num=page_num)
                        
                    print(f"Scraping Page {page_num}: {target_url}")
                    
                    try:
                        response = await page.goto(target_url, wait_until="load")
                        
                        if response.status == 404:
                            print("Reached last page (Page 404). Stopping pagination.")
                            break
                            
                        page_content = await page.content()
                        soup = BeautifulSoup(page_content, "html.parser")
                        product_elements = soup.select(store["item_selector"])
                        
                        if not product_elements and page_num == 1:
                            print("Diagnostic check: No items matched layout patterns. Scanning page layout...")
                            classes = set()
                            for tag in soup.find_all(class_=True):
                                for cls in tag["class"]:
                                    if any(x in cls.lower() for x in ["product", "item", "grid", "card", "thumb"]):
                                        classes.add(cls)
                            print(f"Discovered layout classes: {list(classes)[:15]}")
                            break
                        
                        if not product_elements:
                            print("No products found on page. Stopping pagination.")
                            break
                            
                        print(f"Found {len(product_elements)} items on Page {page_num}.")
                        
                        for idx, product_el in enumerate(product_elements):
                            try:
                                name, price, orig_price, s_url, img_url = store["parser"](product_el, target_url)
                                if not name or any(term in name.lower() for term in NON_CLOTHING_KEYWORDS):
                                    continue
                                
                                item = GamingClothingItem(
                                    product_name=name,
                                    current_price=price,
                                    original_price=orig_price,
                                    store_url=s_url,
                                    image_url=img_url,
                                    brand_name=store["brand_name"],
                                    franchise_tags=[extract_franchise_tag(s_url, fallback="Game Art")]
                                )
                                all_scraped_items.append(item)
                                print(f"[{store['brand_name']} Page {page_num}] Processed: {name} | Price: ${price}")
                            except Exception:
                                continue
                            
                    except Exception as e:
                        print(f"Error scraping Page {page_num}: {e}")
                        break

        await browser.close()

    print(f"\nTotal merged aggregated products in pipeline: {len(all_scraped_items)}")
    
    # Save output to SQLite Database
    try:
        save_products_to_db(all_scraped_items)
    except Exception as e:
        print(f"Error saving to database: {e}")


if __name__ == "__main__":
    try:
        init_db()  # Standardize DB on run
        asyncio.run(scrape_store())
    except Exception as e:
        print(f"Unhandled error: {e}")