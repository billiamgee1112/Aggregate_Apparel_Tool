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
        # Avoid hanging if elements are unresponsive 
        try:
            current_items = await locator.count()
        except Exception:
            current_items = 0
            
        print(f"Attempt {attempt + 1}: Live items found in browser DOM = {current_items}")

        if current_items > prev_item_count:
            no_change_runs = 0
            prev_item_count = current_items
            try:
                last_item = locator.last
                await last_item.scroll_into_view_if_needed(timeout=2000)
            except Exception:
                pass
        else:
            no_change_runs += 1

        if no_change_runs >= 3:
            print("All dynamic products appear to have loaded successfully!")
            break

        await page.wait_for_timeout(1500)


async def scrape_single_store(context: BrowserContext, parser: BaseParser) -> list[GamingClothingItem]:
    """Scrapes a single storefront using a dedicated page inside the shared browser context."""
    brand_name = parser.brand_name
    scraped_items = []
    
    # Spawn a dedicated page tab for this parser task with customized navigation limits
    page = await context.new_page()
    page.set_default_navigation_timeout(60000)  # Bump to 60 seconds limit for slower web servers
    page.set_default_timeout(30000)
    
    # Block heavy image/styling resources to speed up page parsing speed and prevent CDNs timeouts
    async def block_resources(route):
        if route.request.resource_type in ["image", "stylesheet", "media", "font"]:
            await route.abort()
        else:
            await route.continue_()
            
    await page.route("**/*", block_resources)
    print(f"[{brand_name}] Task Started: Initialized active page tab with resource filters.")

    try:
        if parser.pagination_type == "infinite_scroll":
            target_url = parser.url_pattern
            print(f"[{brand_name}] Opening target landing URL: {target_url}...")
            try:
                # Use "domcontentloaded" – much faster, doesn't wait for pixel loaders or tracking scripts
                await page.goto(target_url, wait_until="domcontentloaded")
                await scroll_page_to_end(page, parser.item_selector)
                page_content = await page.content()
                
                soup = BeautifulSoup(page_content, "html.parser")
                product_elements = soup.select(parser.item_selector)
                print(f"[{brand_name}] Found {len(product_elements)} raw elements.")
                
                for product_el in product_elements:
                    try:
                        name, price, orig_price, s_url, img_url, metadata = parser.parse_product(product_el, target_url)
                        if not name:
                            continue
                        
                        name_lower = name.lower()
                        is_clothing = any(clothing in name_lower for clothing in ["shirt", "hoodie", "jacket", "cardigan", "sweatshirt", "pants", "socks", "tee", "top", "outerwear", "loungewear"])
                        has_exclusion = any(re.search(rf"\b{term}\b", name_lower) for term in NON_CLOTHING_KEYWORDS)
                        
                        if has_exclusion and not is_clothing:
                            continue
                        
                        scraped_tag = metadata.get("scraped_tag", "") if isinstance(metadata, dict) else ""
                        franchise_tag = parser.extract_franchise_tag(
                            str(s_url), 
                            product_name=name, 
                            scraped_tag=scraped_tag, 
                            fallback=brand_name
                        )

                        item = GamingClothingItem(
                                product_name=name,
                                current_price=price,
                                original_price=orig_price,
                                store_url=s_url,
                                image_url=img_url,
                                brand_name=brand_name,
                                franchise_tags=[franchise_tag],
                                category=parser.deduce_category(name, str(s_url))
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
                    # Switch to "domcontentloaded" wait criteria for lightning fast scrape runs
                    response = await page.goto(target_url, wait_until="domcontentloaded")
                    
                    if response and response.status == 404:
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
                            name, price, orig_price, s_url, img_url, metadata = parser.parse_product(product_el, target_url)
                            if not name:
                                continue
                            
                            name_lower = name.lower()
                            is_clothing = any(clothing in name_lower for clothing in ["shirt", "hoodie", "jacket", "cardigan", "sweatshirt", "pants", "socks", "tee", "top", "outerwear", "loungewear"])
                            has_exclusion = any(re.search(rf"\b{term}\b", name_lower) for term in NON_CLOTHING_KEYWORDS)
                            
                            if has_exclusion and not is_clothing:
                                continue
                            
                            scraped_tag = metadata.get("scraped_tag", "") if isinstance(metadata, dict) else ""
                            franchise_tag = parser.extract_franchise_tag(
                                str(s_url), 
                                product_name=name, 
                                scraped_tag=scraped_tag, 
                                fallback=brand_name
                            )

                            item = GamingClothingItem(
                                product_name=name,
                                current_price=price,
                                original_price=orig_price,
                                store_url=s_url,
                                image_url=img_url,
                                brand_name=brand_name,
                                franchise_tags=[franchise_tag],
                                category=parser.deduce_category(name, str(s_url))
                            )
                            scraped_items.append(item)
                        except Exception:
                            continue
                        
                except Exception as e:
                    # Provide helpful log but allow loop navigation to retry next segment if hit transient glitched page
                    print(f"[{brand_name}] Warning/Timeout on page {page_num}: {e}")
                    # If page 1 completely times out, break so we don't spam 50 bad runs, otherwise try next
                    if page_num == 1:
                        break
                    continue

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
        
        for task_idx, parsed_list in enumerate(results):
            parser = ACTIVE_PARSERS[task_idx]
            if isinstance(parsed_list, Exception):
                print(f"CRITICAL: Concurrency execution failed for store task [{parser.brand_name}]: {parsed_list}")
            else:
                print(f"Concurrency Result: Gathered {len(parsed_list)} parsed items from [{parser.brand_name}].")
                all_scraped_items.extend(parsed_list)

        await browser.close()

    if all_scraped_items:
        save_products_to_db(all_scraped_items)
        print(f"Catalog Aggregation completed successfully! Added total of {len(all_scraped_items)} active garments.")
    else:
        print("Scraper warning: No valid apparel items extracted during concurrence session.")


if __name__ == "__main__":
    init_db()
    asyncio.run(scrape_store())