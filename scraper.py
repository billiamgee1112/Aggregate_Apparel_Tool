# scraper.py
import os
import asyncio
from dotenv import load_dotenv
from bs4 import BeautifulSoup
from models import GamingClothingItem
from playwright.async_api import async_playwright
from database import init_db, save_products_to_db
from parsers import ACTIVE_PARSERS

print("Script started.")
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
            except Exception:
                pass
        else:
            no_change_runs += 1

        if no_change_runs >= 3:
            print("All dynamic products appear to have loaded successfully!")
            break

        await page.wait_for_timeout(2000)


async def scrape_store():
    all_scraped_items = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": 1280, "height": 1000},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        for parser in ACTIVE_PARSERS:
            brand_name = parser.brand_name
            print(f"\n--- Scraping {brand_name} ---")

            if parser.pagination_type == "infinite_scroll":
                target_url = parser.url_pattern
                print(f"Opening {target_url}...")
                try:
                    await page.goto(target_url, wait_until="networkidle")
                    await scroll_page_to_end(page, parser.item_selector)
                    page_content = await page.content()
                    
                    soup = BeautifulSoup(page_content, "html.parser")
                    product_elements = soup.select(parser.item_selector)
                    print(f"Found {len(product_elements)} items for {brand_name}.")
                    
                    for idx, product_el in enumerate(product_elements):
                        try:
                            name, price, orig_price, s_url, img_url = parser.parse_product(product_el, target_url)
                            if not name or any(term in name.lower() for term in NON_CLOTHING_KEYWORDS):
                                continue
                            
                            item = GamingClothingItem(
                                product_name=name,
                                current_price=price,
                                original_price=orig_price,
                                store_url=s_url,
                                image_url=img_url,
                                brand_name=brand_name,
                                franchise_tags=[parser.extract_franchise_tag(s_url, fallback=brand_name)]
                            )
                            all_scraped_items.append(item)
                            print(f"[{brand_name}] Processed: {name} | Price: ${price}")
                        except Exception:
                            continue
                except Exception as e:
                    print(f"Error scraping {brand_name}: {e}")

            elif parser.pagination_type == "paginated":
                for page_num in range(1, parser.max_pages + 1):
                    if page_num == 1 and parser.first_page_override:
                        target_url = parser.first_page_override
                    else:
                        target_url = parser.url_pattern.format(page_num=page_num)
                        
                    print(f"Scraping Page {page_num}: {target_url}")
                    
                    try:
                        response = await page.goto(target_url, wait_until="load")
                        
                        if response.status == 404:
                            print("Reached last page (Page 404). Stopping pagination.")
                            break
                            
                        page_content = await page.content()
                        soup = BeautifulSoup(page_content, "html.parser")
                        product_elements = soup.select(parser.item_selector)
                        
                        if not product_elements:
                            print("No products found on page. Stopping pagination.")
                            break
                            
                        print(f"Found {len(product_elements)} items on Page {page_num}.")
                        
                        for idx, product_el in enumerate(product_elements):
                            try:
                                name, price, orig_price, s_url, img_url = parser.parse_product(product_el, target_url)
                                if not name or any(term in name.lower() for term in NON_CLOTHING_KEYWORDS):
                                    continue
                                
                                item = GamingClothingItem(
                                    product_name=name,
                                    current_price=price,
                                    original_price=orig_price,
                                    store_url=s_url,
                                    image_url=img_url,
                                    brand_name=brand_name,
                                    franchise_tags=[parser.extract_franchise_tag(s_url, fallback="Game Art")]
                                )
                                all_scraped_items.append(item)
                                print(f"[{brand_name} Page {page_num}] Processed: {name} | Price: ${price}")
                            except Exception:
                                continue
                            
                    except Exception as e:
                        print(f"Error scraping Page {page_num}: {e}")
                        break

        await browser.close()

    print(f"\nTotal merged aggregated products in pipeline: {len(all_scraped_items)}")
    
    try:
        save_products_to_db(all_scraped_items)
    except Exception as e:
        print(f"Error saving to database: {e}")


if __name__ == "__main__":
    try:
        init_db()
        asyncio.run(scrape_store())
    except Exception as e:
        print(f"Unhandled error: {e}")