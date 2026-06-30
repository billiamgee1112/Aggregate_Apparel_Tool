# scraper.py
import os
import asyncio
from dotenv import load_dotenv
from bs4 import BeautifulSoup
from models import GamingClothingItem
from playwright.async_api import async_playwright, BrowserContext
from database import init_db, save_products_to_db
from parsers import ACTIVE_PARSERS
from parsers.base import BaseParser
import re

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


async def scrape_single_store(context: BrowserContext, parser: BaseParser) -> list[GamingClothingItem]:
    """Scrapes a single storefront using a dedicated page inside the shared browser context."""
    brand_name = parser.brand_name
    scraped_items = []
    
    # Spawn a dedicated page tab for this parser task
    page = await context.new_page()
    print(f"[{brand_name}] Task Started: Initialized active page tab.")

    try:
        if parser.pagination_type == "infinite_scroll":
            target_url = parser.url_pattern
            print(f"[{brand_name}] Opening target landing URL: {target_url}...")
            try:
                await page.goto(target_url, wait_until="networkidle")
                await scroll_page_to_end(page, parser.item_selector)
                page_content = await page.content()
                
                soup = BeautifulSoup(page_content, "html.parser")
                product_elements = soup.select(parser.item_selector)
                print(f"[{brand_name}] Found {len(product_elements)} raw elements.")
                
                for product_el in product_elements:
                    try:
                        name, price, orig_price, s_url, img_url = parser.parse_product(product_el, target_url)
                        if not name:
                            continue
                        
                        name_lower = name.lower()
                        is_clothing = any(clothing in name_lower for clothing in ["shirt", "hoodie", "jacket", "cardigan", "sweatshirt", "pants", "socks", "tee", "top", "outerwear", "loungewear"])
                        has_exclusion = any(re.search(rf"\b{term}\b", name_lower) for term in NON_CLOTHING_KEYWORDS)
                        
                        if has_exclusion and not is_clothing:
                            continue
                        
                        item = GamingClothingItem(
                                product_name=name,
                                current_price=price,
                                original_price=orig_price,
                                store_url=s_url,
                                image_url=img_url,
                                brand_name=brand_name,
                                franchise_tags=[parser.extract_franchise_tag(s_url, fallback=brand_name)],
                                category=parser.deduce_category(name, str(s_url)) # Categorization hook!
                            )
                        scraped_items.append(item)
                    except Exception:
                        continue
            except Exception as e:
                print(f"[{brand_name}] Error scraping infinite scroll page: {e}")

        elif parser.pagination_type == "paginated":
            for page_num in range(1, parser.max_pages + 1):
                if page_num == 1 and parser.first_page_override:
                    target_url = parser.first_page_override
                else:
                    target_url = parser.url_pattern.format(page_num=page_num)
                    
                print(f"[{brand_name}] Scraping Page {page_num}: {target_url}")
                
                try:
                    response = await page.goto(target_url, wait_until="load")
                    
                    if response.status == 404:
                        print(f"[{brand_name}] Reached last page (Status 404) at page {page_num}.")
                        break
                        
                    page_content = await page.content()
                    soup = BeautifulSoup(page_content, "html.parser")
                    product_elements = soup.select(parser.item_selector)
                    
                    if not product_elements:
                        print(f"[{brand_name}] No products found on page {page_num}. Stopping pagination.")
                        break
                        
                    print(f"[{brand_name}] Found {len(product_elements)} items on Page {page_num}.")
                    
                    for product_el in product_elements:
                        try:
                            name, price, orig_price, s_url, img_url = parser.parse_product(product_el, target_url)
                            if not name:
                                continue
                            
                            name_lower = name.lower()
                            is_clothing = any(clothing in name_lower for clothing in ["shirt", "hoodie", "jacket", "cardigan", "sweatshirt", "pants", "socks", "tee", "top", "outerwear", "loungewear"])
                            has_exclusion = any(re.search(rf"\b{term}\b", name_lower) for term in NON_CLOTHING_KEYWORDS)
                            
                            if has_exclusion and not is_clothing:
                                continue
                            
                            item = GamingClothingItem(
                                product_name=name,
                                current_price=price,
                                original_price=orig_price,
                                store_url=s_url,
                                image_url=img_url,
                                brand_name=brand_name,
                                franchise_tags=[parser.extract_franchise_tag(s_url, fallback=brand_name)],
                                category=parser.deduce_category(name, str(s_url)) # Categorization hook!
                            )
                            scraped_items.append(item)
                        except Exception:
                            continue
                        
                except Exception as e:
                    print(f"[{brand_name}] Error on page {page_num}: {e}")
                    break

    finally:
        # Prevent page/tab leaks by closing the tab once done
        await page.close()
        print(f"[{brand_name}] Task Finished: Closed page tab. Found {len(scraped_items)} clothing items.")

    return scraped_items


async def scrape_store():
    all_scraped_items = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": 1280, "height": 1000},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )

        # Create task coroutines for all active scraper engines
        tasks = [scrape_single_store(context, parser) for parser in ACTIVE_PARSERS]
        
        # Run all scraping tasks in parallel concurrently!
        print(f"Launching {len(tasks)} store scrape tasks concurrently...")
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Merge and aggregate collected items from each task
        for result in results:
            if isinstance(result, list):
                all_scraped_items.extend(result)
            elif isinstance(result, Exception):
                print(f"Parallel Task Error occurred: {result}")

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