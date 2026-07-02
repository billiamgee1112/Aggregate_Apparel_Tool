# scraper.py
import os
import random
import asyncio
from dotenv import load_dotenv
from bs4 import BeautifulSoup
from models import GamingClothingItem
from playwright.async_api import async_playwright, Browser, BrowserContext
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

# A curated list of real, modern, high-reputation User-Agents 
USER_AGENTS = [
    # Chrome on Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    # Firefox on Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
    # Safari on macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_3_1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3 Safari/605.1.15",
    # Chrome on macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    # Edge on Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36 Edg/122.0.0.0"
]

async def scroll_page_to_end(page, item_selector, max_attempts=15):
    """Gradually scrolls the page with human-like timing increments."""
    prev_item_count = 0
    no_change_runs = 0

    print("Executing target-oriented infinite scrolling loop...")
    for attempt in range(max_attempts):
        locator = page.locator(item_selector)
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

        # Introducing randomized human "jitter" scroll intervals (1.2s - 2.8s)
        jitter = random.uniform(1200, 2800)
        await page.wait_for_timeout(jitter)


async def apply_stealth_scripts(page):
    """Overrides automation properties in Javascript environment to bypass bot-detection firewalls."""
    
    # 1. Override the navigator.webdriver property (Cloudflare's #1 check!)
    await page.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', {
            get: () => undefined
        });
    """)

    # 2. Fake standard browser languages and platform properties
    await page.add_init_script("""
        Object.defineProperty(navigator, 'languages', {
            get: () => ['en-US', 'en']
        });
        Object.defineProperty(navigator, 'plugins', {
            get: () => [1, 2, 3, 4, 5]
        });
    """)

    # 3. Prevent chrome-specific variables leak
    await page.add_init_script("""
        window.chrome = {
            runtime: {},
            loadTimes: function() {},
            csi: function() {},
            app: {}
        };
    """)


async def scrape_single_store(browser: Browser, parser: BaseParser) -> list[GamingClothingItem]:
    """Scrapes a single storefront using a dedicated, isolated stealth context per domain."""
    brand_name = parser.brand_name
    scraped_items = []
    
    # Select a random User-Agent for this specific retail store traversal
    user_agent = random.choice(USER_AGENTS)
    
    # Dynamic, real browser headers mapping modern expectations
    extra_headers = {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Sec-Ch-Ua-Mobile": "?0",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Upgrade-Insecure-Requests": "1"
    }

    # Optional proxy setup (checks your .env for ROTATING_PROXY_URL)
    proxy_url = os.getenv("ROTATING_PROXY_URL")
    proxy_config = {"server": proxy_url} if proxy_url else None

    # Spawn an isolated browser context per store to avoid cookie cross-contamination blocks
    context = await browser.new_context(
        viewport={"width": 1280, "height": 1000},
        user_agent=user_agent,
        extra_http_headers=extra_headers,
        proxy=proxy_config,
        device_scale_factor=1,
        locale="en-US"
    )

    page = await context.new_page()
    page.set_default_navigation_timeout(60000)
    page.set_default_timeout(30000)
    
    # Block heavy rendering loads to save CPU and speed up extraction times
    async def block_resources(route):
        if route.request.resource_type in ["image", "stylesheet", "media", "font"]:
            await route.abort()
        else:
            await route.continue_()
            
    await page.route("**/*", block_resources)
    
    # Inject our dynamic stealth scripts onto the window before any page code loads!
    await apply_stealth_scripts(page)
    print(f"[{brand_name}] Task Started: Opened secure, isolated context with User-Agent: {user_agent}")

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
                
                # Introduce human "think-time" jitter before landing on next pagination screen (1.5s - 3s)
                think_time = random.uniform(1500, 3000)
                await page.wait_for_timeout(think_time)

                try:
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
                    print(f"[{brand_name}] Warning/Timeout on page {page_num}: {e}")
                    if page_num == 1:
                        break
                    continue

    finally:
        # Prevent page/tab leaks by closing the tab once done
        await page.close()
        await context.close()
        print(f"[{brand_name}] Task Finished: Closed page and context. Found {len(scraped_items)} clothing items.")

    return scraped_items


async def scrape_store():
    all_scraped_items = []

    async with async_playwright() as p:
        # Launch Chromium headless with sandbox features optimized
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled", # Hides standard Chromium automation variables
                "--no-sandbox",
                "--disable-setuid-sandbox"
            ]
        )

        # Create task coroutines for all active scraper engines (passing browser instead of context)
        tasks = [scrape_single_store(browser, parser) for parser in ACTIVE_PARSERS]
        
        # Run all scraping tasks in parallel concurrently!
        print(f"Launching {len(tasks)} store scrape tasks concurrently with User-Agent & Context isolation...")
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