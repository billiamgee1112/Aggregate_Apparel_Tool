# scraper.py
import os
import json
import asyncio
from dotenv import load_dotenv
from bs4 import BeautifulSoup
from models import GamingClothingItem
from urllib.parse import urljoin, urlparse
from playwright.async_api import async_playwright
from database import init_db, save_products_to_db

print("Script started.")
# Load environment variables
load_dotenv()


async def scrape_store():
    print("Starting Playwright Scraper...")
    url = "https://www.insertcoinclothing.com/all-products.html"

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": 1280, "height": 1000},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        
        print(f"Opening {url}...")
        await page.goto(url, wait_until="networkidle")

        prev_item_count = 0
        no_change_runs = 0
        max_scroll_attempts = 15

        print("Executing target-oriented infinite scrolling loop...")
        for attempt in range(max_scroll_attempts):
            locator = page.locator(".m-listing-item")
            current_items = await locator.count()
            print(f"Attempt {attempt + 1}: Live items found in browser DOM = {current_items}")

            if current_items > prev_item_count:
                no_change_runs = 0
                prev_item_count = current_items
                try:
                    last_item = locator.last
                    await last_item.scroll_into_view_if_needed()
                    print("Scrolled last product card into view.")
                except Exception as e:
                    print(f"Error scrolling: {e}")
            else:
                no_change_runs += 1

            load_more_buttons = page.locator("button:has-text('More'), a:has-text('More'), [class*='load-more']")
            buttons_count = await load_more_buttons.count()
            if buttons_count > 0:
                for idx in range(buttons_count):
                    try:
                        btn = load_more_buttons.nth(idx)
                        if await btn.is_visible():
                            print("Found dynamic 'Load More' button. Clicking it...")
                            await btn.click()
                    except Exception:
                        pass

            if no_change_runs >= 3:
                print("All dynamic products appear to have loaded successfully!")
                break

            await page.wait_for_timeout(2000)

        page_content = await page.content()
        await browser.close()

    try:
        soup = BeautifulSoup(page_content, "html.parser")
        print("HTML parsed successfully.")
    except Exception as e:
        print(f"Error parsing HTML: {e}")
        return

    product_elements = soup.select(".m-listing-item")
    if not product_elements:
        print("Could not isolate any product items in the final document layout.")
        return

    print(f"Parsing extracted data for {len(product_elements)} total item card containers...")

    # Define non-clothing keywords to exclude
    NON_CLOTHING_KEYWORDS = [
        "pin", "magnet", "keyring", "mug", "umbrella", "blanket", 
        "cushion", "sticker", "badge", "poster", "towel", "socks"
    ]

    products = []
    for index, product in enumerate(product_elements):  
        try:
            # 1. Extract Store URL
            store_url = url
            link_el = (
                product.select_one(".m-listing-item-link") 
                or product.select_one("a") 
                or (product if product.name == "a" else None)
            )
            if link_el and link_el.has_attr('href'):
                store_url = urljoin(url, link_el['href'])
            
            if any(term in store_url.lower() for term in ["shopping", "bag", "cart", "account"]):
                continue

            # 2. Extract Product Name
            product_name = ""
            desc_el = product.select_one(".m-listing-item-desc")
            
            product_name_el = (
                product.select_one(".product-name")
                or (desc_el.select_one("h2") if desc_el else None)
                or (desc_el.select_one("h3") if desc_el else None)
                or (desc_el.select_one("h4") if desc_el else None)
                or product.select_one("h2") 
                or product.select_one("h3")
                or product.select_one(".title")
            )
            
            if product_name_el:
                product_name = product_name_el.get_text(strip=True)
            
            img_el = product.select_one("img")
            if not product_name and img_el and img_el.has_attr("alt"):
                product_name = img_el["alt"].strip()

            if not product_name and desc_el:
                text_lines = [line.strip() for line in desc_el.itertext() if line.strip()]
                if text_lines:
                    product_name = text_lines[0]

            if not product_name:
                continue

            # Filtering check: skip if any non-clothing term is found in the title
            if any(term in product_name.lower() for term in NON_CLOTHING_KEYWORDS):
                continue

            # 3. Extract Current and Original Prices
            price_el = (
                product.select_one(".price") 
                or product.select_one(".amount") 
                or product.select_one("[class*='price']")
                or desc_el
            )
            current_price = 0.0
            original_price = None

            if price_el:
                original_price_el = price_el.select_one("del") or product.select_one(".original-price")
                if original_price_el:
                    orig_text = original_price_el.get_text(strip=True).replace("£", "").replace("$", "").replace(",", "")
                    cleaned_orig_digits = ''.join(c for char in orig_text.split() for c in char if c.isdigit() or c == '.')
                    original_price = float(cleaned_orig_digits) if cleaned_orig_digits else None
                    
                    price_text = price_el.get_text(strip=True).replace(original_price_el.get_text(strip=True), "")
                else:
                    price_text = price_el.get_text(strip=True)

                price_text = price_text.replace(product_name, "")
                price_text = price_text.replace("£", "").replace("$", "").replace(",", "")
                cleaned_digits = ''.join(c for char in price_text.split() for c in char if c.isdigit() or c == '.')
                current_price = float(cleaned_digits) if cleaned_digits else 0.0

            # 4. Extract Image URL
            raw_image_url = ""
            if img_el:
                raw_image_url = img_el.get("src") or img_el.get("data-src") or ""
            
            if not raw_image_url:
                raw_image_url = "https://example.com/placeholder.jpg"
            else:
                raw_image_url = urljoin(url, raw_image_url)

            brand_name = "Insert Coin"
            
            # Generate clean franchise tag
            parsed_path = urlparse(store_url).path
            path_segments = [seg for segment in parsed_path.split('/') if (seg := segment.replace('.html', '').strip())]
            franchise_tag = "Geek Apparel"
            if path_segments:
                franchise_tag = " ".join(segment.capitalize() for segment in path_segments[0].split('-'))
            franchise_tags = [franchise_tag]

            item = GamingClothingItem(
                product_name=product_name,
                current_price=current_price,
                original_price=original_price,
                store_url=store_url, 
                image_url=raw_image_url, 
                brand_name=brand_name,
                franchise_tags=franchise_tags,
            )
            products.append(item)
            print(f"Processed: {product_name} | Price: £{current_price} | Original: £{original_price}")  
        except Exception as e:
            continue

    print(f"\nTotal products extracted: {len(products)}")  
    
    # Save output to SQLite Database
    try:
        save_products_to_db(products)
    except Exception as e:
        print(f"Error saving to database: {e}")

# Run the scraper
if __name__ == "__main__":
    try:
        init_db()  # Standardize DB on run
        asyncio.run(scrape_store())
    except Exception as e:
        print(f"Unhandled error: {e}")