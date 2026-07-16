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

# Blocker for genuine non-apparel accessories
NON_CLOTHING_KEYWORDS = [
    "pin", "magnet", "keyring", "mug", "umbrella", "blanket", 
    "cushion", "sticker", "badge", "poster", "towel", "socks"
]

# Curated list of high-reputation User-Agents
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_3_1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3 Safari/605.1.15",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36 Edg/122.0.0.0"
]

async def scroll_page_to_end(page, item_selector, max_attempts=40):
    """Gradually and persistently scrolls the page downward, bypassing cookie modals to load all products."""
    prev_item_count = 0
    no_change_runs = 0

    print("Running enhanced persistent infinite scrolling loops...")
    
    # Try to dismiss cookie overlays that block mouse scrolls
    try:
        cookie_selectors = [
            "button:has-text('Accept All')", 
            "button:has-text('Accept')", 
            ".cookie-accept", 
            "#cookie-accept",
            "button:has-text('Allow all')",
            "a:has-text('Accept All')"
        ]
        for sel in cookie_selectors:
            locator = page.locator(sel)
            if await locator.count() > 0:
                await locator.first.click(timeout=2000)
                print("Dismissed privacy cookie overlay banner successfully.")
                await page.wait_for_timeout(1000)
                break
    except Exception:
        pass

    for attempt in range(max_attempts):
        locator = page.locator(item_selector)
        try:
            current_items = await locator.count()
        except Exception:
            current_items = 0
            
        print(f"Scroll Attempt {attempt + 1}/{max_attempts}: Live items in browser DOM = {current_items}")

        # Programmatically scroll the page gradually to trigger intersection events reliably
        try:
            await page.evaluate("""
                (async () => {
                    // Gradual scrolling loop to trigger lazy observers
                    let totalHeight = 0;
                    let distance = 300;
                    let scrollHeight = document.body.scrollHeight;
                    
                    // Scroll down by step increments
                    for (let i = 0; i < 5; i++) {
                        window.scrollBy(0, distance);
                        await new Promise(resolve => setTimeout(resolve, 80));
                    }
                    
                    // Trigger scroll event manually
                    window.dispatchEvent(new Event('scroll'));
                    window.dispatchEvent(new Event('resize'));
                    
                    // Bounce at the very bottom
                    window.scrollTo(0, document.body.scrollHeight);
                    await new Promise(resolve => setTimeout(resolve, 100));
                    window.scrollBy(0, -200);
                    window.scrollTo(0, document.body.scrollHeight);
                })();
            """)
        except Exception as e:
            print(f"Programmative Scroll Evaluation warning: {e}")

        # If DOM grew, reset no-change counts
        if current_items > prev_item_count:
            no_change_runs = 0
            prev_item_count = current_items
        else:
            no_change_runs += 1

        # PERSISTENCE RULE: Never exit before at least 15 attempts, allowing background queries to resolve.
        if attempt > 15 and no_change_runs >= 5 and current_items > 30:
            print("Infinite scroll height is stable. Stopping scrolling loops.")
            break

        # Jitter delay
        jitter = random.uniform(1500, 2500)
        await page.wait_for_timeout(jitter)


async def apply_stealth_scripts(page):
    """Overrides automation properties in Javascript environment to bypass bot-detection firewalls."""
    await page.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', {
            get: () => undefined
        });
    """)
    await page.add_init_script("""
        Object.defineProperty(navigator, 'languages', {
            get: () => ['en-US', 'en']
        });
        Object.defineProperty(navigator, 'plugins', {
            get: () => [1, 2, 3, 4, 5]
        });
    """)
    await page.add_init_script("""
        window.chrome = {
            runtime: {},
            loadTimes: function() {},
            csi: function() {},
            app: {}
        };
    """)


async def unlock_shopify_password_page(page, parser: BaseParser):
    """Submits Shopify's native storefront password gate once per store
    scrape, so the rest of the session (same browser context/cookies) can
    reach products.json normally. Shopify sets a 'storefront_digest' cookie
    on success that persists for the context's lifetime - no need to repeat
    this per page request."""
    brand_name = parser.brand_name
    store_root = getattr(parser, "store_root", None)
    if not store_root:
        print(f"[{brand_name}] WARNING: store_password set but no store_root defined - skipping unlock.")
        return

    try:
        # Navigate to the dedicated /password route directly rather than the
        # store root - some themes only render the password form inside a
        # hidden modal on the homepage (triggered by a JS click), whereas
        # /password always renders it inline and visible.
        await page.goto(f"{store_root.rstrip('/')}/password", wait_until="domcontentloaded")
        password_input = page.locator('input[name="password"]')
        if await password_input.count() == 0:
            print(f"[{brand_name}] No password gate encountered (already unlocked or none present).")
            return

        print(f"[{brand_name}] Password gate detected - submitting stored password.")
        # Many themes (incl. this one) keep the password form hidden inside a
        # popup/modal shown only via a "#password-popup" anchor-link click
        # (a pure-CSS :target reveal) - click it first if present.
        popup_trigger = page.locator('a[href="#password-popup"]')
        if await popup_trigger.count() > 0:
            await popup_trigger.first.click()
        await password_input.first.wait_for(state="visible", timeout=10000)
        await password_input.first.fill(parser.store_password)
        await page.locator('form[action="/password"] button[type="submit"], form[action="/password"] input[type="submit"]').first.click()
        await page.wait_for_load_state("domcontentloaded")
        # Jumping straight from a form submit into rapid-fire JSON API
        # requests is a strong bot signal - pause like a real visitor would
        # before the pagination loop starts hammering the feed.
        await page.wait_for_timeout(random.uniform(3000, 6000))
        print(f"[{brand_name}] Password gate unlocked.")
    except Exception as e:
        print(f"[{brand_name}] WARNING: Failed to unlock password gate ({e}) - subsequent fetches may fail.")


async def scrape_single_store(browser: Browser, parser: BaseParser) -> list[GamingClothingItem]:
    """Scrapes a single storefront using a dedicated, isolated stealth context per domain."""
    brand_name = parser.brand_name
    scraped_items = []
    
    user_agent = random.choice(USER_AGENTS)
    
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
    
    # Block genuinely heavy rendering loads dynamically without obstructing layouts
    async def block_resources(route):
        # STABILITY KEYPOINT: We must allow stylesheets and images to load
        # so responsive layout structures and dynamic HTML hydration engines execute
        # and don't yield blank placeholder values.
        blocked_types = ["media", "font"]
            
        if route.request.resource_type in blocked_types:
            await route.abort()
        else:
            await route.continue_()
            
    await page.route("**/*", block_resources)
    
    # Inject stealth scripts before any page code loads
    await apply_stealth_scripts(page)
    print(f"[{brand_name}] Task Started: Opened secure, isolated context with User-Agent: {user_agent}")

    if parser.store_password:
        await unlock_shopify_password_page(page, parser)

    try:
        # CRITICAL FIX: Base routing purely on verified pagination types
        if parser.pagination_type == "infinite_scroll":
            target_url = parser.url_pattern
            print(f"[{brand_name}] Opening target landing URL: {target_url}...")
            try:
                # Use networkidle so lazy-loading JS events can register and bind fully
                await page.goto(target_url, wait_until="networkidle")
                await scroll_page_to_end(page, parser.item_selector)
                page_content = await page.content()
                
                soup = BeautifulSoup(page_content, "html.parser")
                product_elements = soup.select(parser.item_selector)
                print(f"[{brand_name}] Found {len(product_elements)} raw elements.")
                
                for product_el in product_elements:
                    try:
                        name, price, orig_price, s_url, img_url, metadata = parser.parse_product(product_el, target_url)
                        
                        # Guard against unpopulated partial link anchors, placeholders, or $0 prices
                        if not name or price == 0.0 or not img_url or "placeholder" in img_url or "data:image" in img_url:
                            continue
                        
                        text_to_check = f"{name} {s_url}".lower()
                        is_clothing = any(clothing in text_to_check for clothing in [
                            "shirt", "hoodie", "jacket", "cardigan", "sweatshirt", "pants", 
                            "socks", "tee", "top", "outerwear", "loungewear", "t-shirt", "tshirt", 
                            "sweater", "vest", "jersey", "shorts", "crewneck", "pullover", "coat",
                            "windbreaker", "bomber", "leggings", "trouser", "trousers"
                        ])
                        has_exclusion = any(re.search(rf"\b{term}\b", text_to_check) for term in NON_CLOTHING_KEYWORDS)
                        
                        if has_exclusion and not is_clothing:
                            continue
                        
                        if not is_clothing:
                            continue

                        scraped_tag = metadata.get("scraped_tag", "") if isinstance(metadata, dict) else ""
                        franchise_tags, franchise_verified = parser.extract_franchise_tag(
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
                                franchise_tags=franchise_tags,
                                franchise_verified=franchise_verified,
                                category=parser.deduce_category(name, str(s_url)),
                                description_snippet=metadata.get("description_snippet", "") if isinstance(metadata, dict) else "",
                                currency=parser.currency
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
                
                think_time = random.uniform(1500, 3000)
                await page.wait_for_timeout(think_time)

                try:
                    response = await page.goto(target_url, wait_until="domcontentloaded")
                    
                    if response and response.status == 404:
                        print(f"[{brand_name}] Reached last page (Status 404) at page {page_num}.")
                        break

                    # SCROLL THE PAGINATED PAGE TO FORCE LAZY HYDRATION
                    print(f"[{brand_name}] Hydrating page widgets via scroll actions...")
                    await page.evaluate("""
                        (async () => {
                            window.scrollBy(0, 800);
                            await new Promise(r => setTimeout(r, 200));
                            window.scrollBy(0, 1200);
                            await new Promise(r => setTimeout(r, 200));
                            window.scrollTo(0, document.body.scrollHeight);
                            await new Promise(r => setTimeout(r, 300));
                        })();
                    """)
                    await page.wait_for_timeout(500)
                        
                    page_content = await page.content()
                    soup = BeautifulSoup(page_content, "html.parser")
                    product_elements = soup.select(parser.item_selector)
                    
                    if not product_elements:
                        page_title = soup.title.get_text(strip=True) if soup.title else "No Title"
                        print(f"[{brand_name}] Selector '{parser.item_selector}' returned 0 products on Page {page_num}.")
                        print(f"[{brand_name}] Page Info -> Title: '{page_title}' | Current URL: {page.url}")
                        
                        # Scan for products strings inside standard hyperlinks to identify selector deviations
                        debug_links = [a['href'] for a in soup.select("a[href]") if "/products/" in a['href']][:3]
                        if debug_links:
                            print(f"[{brand_name}] Debug Match: Hyperlinks containing '/products/' exist on template but selector missed! Samples: {debug_links}")
                        break
                        
                    print(f"[{brand_name}] Found {len(product_elements)} items on Page {page_num}.")
                    
                    # Track starting count before adding page items
                    start_items_count = len(scraped_items)

                    for product_el in product_elements:
                        try:
                            name, price, orig_price, s_url, img_url, metadata = parser.parse_product(product_el, target_url)
                            
                            # Guard against unpopulated partial link anchors, placeholders, or $0 prices
                            if not name or price == 0.0 or not img_url or "placeholder" in img_url or "data:image" in img_url:
                                continue
                            
                            text_to_check = f"{name} {s_url}".lower()
                            is_clothing = any(clothing in text_to_check for clothing in [
                                "shirt", "hoodie", "jacket", "cardigan", "sweatshirt", "pants", 
                                "socks", "tee", "top", "outerwear", "loungewear", "t-shirt", "tshirt", 
                                "sweater", "vest", "jersey", "shorts", "crewneck", "pullover", "coat",
                                "windbreaker", "bomber", "leggings", "trouser", "trousers"
                            ])
                            has_exclusion = any(re.search(rf"\b{term}\b", text_to_check) for term in NON_CLOTHING_KEYWORDS)
                            
                            if has_exclusion and not is_clothing:
                                continue
                            
                            if not is_clothing:
                                continue

                            scraped_tag = metadata.get("scraped_tag", "") if isinstance(metadata, dict) else ""
                            franchise_tags, franchise_verified = parser.extract_franchise_tag(
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
                                franchise_tags=franchise_tags,
                                franchise_verified=franchise_verified,
                                category=parser.deduce_category(name, str(s_url)),
                                description_snippet=metadata.get("description_snippet", "") if isinstance(metadata, dict) else "",
                                currency=parser.currency
                            )
                            scraped_items.append(item)
                        except Exception:
                            continue
                    
                    # LOOP BREAK SECURITY POINT:
                    # If this page yielded exactly 0 brand new valid apparel items, 
                    # we have exhausted the page limits or reached the end of the collection!
                    new_items_added = len(scraped_items) - start_items_count
                    if page_num > 1 and new_items_added == 0:
                        print(f"[{brand_name}] Page {page_num} yielded 0 new unique apparel items. Reached end of catalog!")
                        break
                        
                except Exception as e:
                    print(f"[{brand_name}] Warning/Timeout on page {page_num}: {e}")
                    if page_num == 1:
                        break
                    continue

        elif parser.pagination_type == "shopify_json":
            import json
            # Most Shopify stores expose one single collection feed (url_pattern).
            # A few (e.g. DRKN, which mixes gaming and non-gaming apparel across
            # many separate per-franchise collections) instead set
            # collection_urls to a list of feed patterns to aggregate. Products
            # can legitimately appear in more than one of those collections
            # (e.g. a Rainbow Six item in both the umbrella and a seasonal
            # sub-collection), so seen_store_urls dedupes across all of them.
            collection_patterns = getattr(parser, "collection_urls", None) or [parser.url_pattern]
            seen_store_urls = set()
            for collection_pattern in collection_patterns:
                for page_num in range(1, parser.max_pages + 1):
                    target_url = collection_pattern.format(page_num=page_num)
                    print(f"[{brand_name}] Fetching JSON feed page {page_num}: {target_url}")

                    think_time = random.uniform(*parser.request_delay_range_ms)
                    await page.wait_for_timeout(think_time)

                    try:
                        response = await page.goto(target_url, wait_until="domcontentloaded")

                        if response and response.status == 404:
                            print(f"[{brand_name}] Reached last page (404) at page {page_num}.")
                            break

                        raw_text = await response.text()
                        data = json.loads(raw_text)
                        products = data.get("products", [])

                        if not products:
                            print(f"[{brand_name}] Feed empty at page {page_num}. Reached end of catalog.")
                            break

                        print(f"[{brand_name}] Found {len(products)} raw products on JSON page {page_num}.")

                        for product in products:
                            try:
                                name, price, orig_price, s_url, img_url, metadata = parser.parse_product(product, target_url)

                                # The parser already filters apparel via product_type, so no keyword gate here
                                if not name or price == 0.0 or not img_url or "placeholder" in img_url or "data:image" in img_url:
                                    continue

                                if s_url in seen_store_urls:
                                    continue
                                seen_store_urls.add(s_url)

                                scraped_tag = metadata.get("scraped_tag", "") if isinstance(metadata, dict) else ""
                                # Shopify stores already determine their own verified status
                                # internally (parsers/shopify_base.py); extract_franchise_tag is
                                # only used here for keyword-mapping string normalization and
                                # guest-character bonus-tag detection, so its own verified flag
                                # is ignored in favor of the parser's metadata.
                                franchise_tags, _ = parser.extract_franchise_tag(
                                    str(s_url),
                                    product_name=name,
                                    scraped_tag=scraped_tag,
                                    fallback=brand_name
                                )
                                franchise_verified = metadata.get("franchise_verified", True) if isinstance(metadata, dict) else True
                                product_type = metadata.get("product_type", "") if isinstance(metadata, dict) else ""

                                item = GamingClothingItem(
                                    product_name=name,
                                    current_price=price,
                                    original_price=orig_price,
                                    store_url=s_url,
                                    image_url=img_url,
                                    brand_name=brand_name,
                                    franchise_tags=franchise_tags,
                                    franchise_verified=franchise_verified,
                                    category=parser.deduce_category(name, str(s_url), product_type),
                                    description_snippet=metadata.get("description_snippet", "") if isinstance(metadata, dict) else "",
                                    currency=parser.currency
                                )
                                scraped_items.append(item)
                            except Exception:
                                continue

                    except Exception as e:
                        print(f"[{brand_name}] JSON fetch warning on page {page_num}: {e}")
                        if page_num == 1:
                            break
                        continue
    finally:
        await page.close()
        await context.close()
        print(f"[{brand_name}] Task Finished: Closed page and context. Found {len(scraped_items)} clothing items.")

    return scraped_items


async def scrape_store():
    all_scraped_items = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-setuid-sandbox"
            ]
        )

        tasks = [scrape_single_store(browser, parser) for parser in ACTIVE_PARSERS]
        
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

        print("Running automatic franchise discovery...")
        try:
            import franchise_discovery
            franchise_discovery.run()
        except Exception as e:
            print(f"Franchise Discovery Warning (non-fatal): {e}")
    else:
        print("Scraper warning: No valid apparel items extracted during concurrence session.")


if __name__ == "__main__":
    init_db()
    asyncio.run(scrape_store())