# api.py
import sqlite3
import json
import os
from collections import Counter
from contextlib import asynccontextmanager
from fastapi import FastAPI, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, PlainTextResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from markupsafe import Markup
from typing import Optional, List
from pydantic import BaseModel
from apscheduler.schedulers.background import BackgroundScheduler
from scraper import scrape_store
import asyncio
from urllib.parse import urlencode
from math import ceil
import re
from xml.sax.saxutils import escape as xml_escape

DB_NAME = "apparel_aggregator.db"

BASE_DOMAIN = "https://gamingapparel.gg"  # Single source of truth for the domain (canonicals, sitemap, OG tags)
PAGE_SIZE = 24  # Products per page

# Controls whether this process runs the heavy scrape/discovery job itself.
# LOCAL DEV (default): keep "true" — this machine is where scraping/Wikidata
#   calls should run, since that compute is free here.
# CLOUD DEPLOYMENT: set this env var to "false" so the hosted app only serves
#   read queries against a database synced up from local maintenance runs,
#   instead of re-running the scraper/discovery job on paid cloud compute.
ENABLE_SCRAPER_SCHEDULER = os.getenv("ENABLE_SCRAPER_SCHEDULER", "true").strip().lower() in ("1", "true", "yes")

# ==========================================
# BACKGROUND SCHEDULER CONFIGURATION
# ==========================================

def run_scraper_job():
    """Sync wrapper to execute the async crawler inside the scheduler thread."""
    print("Background Job: Triggering automatic catalog scraper...")
    try:
        asyncio.run(scrape_store())
    except Exception as e:
        print(f"Background Job Error: {e}")

scheduler = BackgroundScheduler()
if ENABLE_SCRAPER_SCHEDULER:
    scheduler.add_job(run_scraper_job, "interval", hours=24)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Starts/stops the background scheduler around the app's lifetime
    (replaces the deprecated on_event startup/shutdown handlers)."""
    if ENABLE_SCRAPER_SCHEDULER:
        if not scheduler.running:
            scheduler.start()
            print("FastAPI Startup: Background scheduler initiated (auto-scrape + discovery every 24h).")
    else:
        print("FastAPI Startup: Scraper scheduler disabled (ENABLE_SCRAPER_SCHEDULER=false). "
              "This instance will only serve reads; run scraper.py locally and sync the database instead.")
    yield
    if scheduler.running:
        scheduler.shutdown()

app = FastAPI(
    title="Geek Apparel Aggregator API",
    description="Queryable API endpoints for aggregated clothing items",
    version="1.0.0",
    lifespan=lifespan
)

# CORS: this is a read-only, cookie-free SSR site with no cross-origin API
# consumers, so credentials are never needed. Restricting to the real domain
# (rather than "*") avoids the insecure/invalid combo of wildcard origins with
# allow_credentials=True (browsers reject that combination anyway).
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://gamingapparel.gg", "https://www.gamingapparel.gg"],
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["*"],
)

# Serve static assets (favicon, compiled Tailwind CSS, OG images) from /static.
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")

def build_pagination(path: str, filters: dict, sort: str, page: int, total_count: int) -> dict:
    """Computes pagination state, link bases, and a canonical URL for SEO."""
    total_pages = max(1, ceil(total_count / PAGE_SIZE))
    page = max(1, min(page, total_pages))

    active_filters = {k: v for k, v in filters.items() if v}

    # Base for pagination links (keeps filters + sort, drops page)
    pag_params = dict(active_filters)
    if sort:
        pag_params["sort"] = sort
    pag_qs = urlencode(pag_params)
    base_url = f"{path}?{pag_qs}&" if pag_qs else f"{path}?"

    # Base for sort links (keeps filters, drops sort + page)
    sort_qs = urlencode(active_filters)
    sort_base_url = f"{path}?{sort_qs}&" if sort_qs else f"{path}?"

    # Base for category links (keeps sort + all OTHER filters, drops category + page)
    # so switching category doesn't lose the current sort/brand/franchise/search
    # selection, and vice versa. Two variants: one to append "category=X" to
    # (trailing separator), one clean (no separator) for the "All Categories" reset.
    non_category_filters = {k: v for k, v in active_filters.items() if k != "category"}
    if sort:
        non_category_filters["sort"] = sort
    cat_qs = urlencode(non_category_filters)
    category_base_url = f"{path}?{cat_qs}&" if cat_qs else f"{path}?"
    category_reset_url = f"{path}?{cat_qs}" if cat_qs else path

    # Canonical URL: content-defining filters + page, but NOT sort (dedupes sort variants)
    canon_params = dict(active_filters)
    if page > 1:
        canon_params["page"] = page
    canon_qs = urlencode(canon_params)
    canonical = f"{BASE_DOMAIN}{path}?{canon_qs}" if canon_qs else f"{BASE_DOMAIN}{path}"

    window = 2
    start = max(1, page - window)
    end = min(total_pages, page + window)

    return {
        "current_page": page,
        "total_pages": total_pages,
        "total_count": total_count,
        "has_prev": page > 1,
        "has_next": page < total_pages,
        "prev_page": page - 1,
        "next_page": page + 1,
        "page_range": list(range(start, end + 1)),
        "base_url": base_url,
        "sort_base_url": sort_base_url,
        "category_base_url": category_base_url,
        "category_reset_url": category_reset_url,
        "canonical": canonical,
        "start_index": (page - 1) * PAGE_SIZE + 1 if total_count else 0,
        "end_index": min(page * PAGE_SIZE, total_count),
    }

def _preserved_secondary_qs(category: Optional[str], sort: Optional[str], brand: Optional[str] = None, franchise: Optional[str] = None) -> str:
    """Builds a '?category=X&sort=Y[&brand=Z][&franchise=W]' suffix (or ''
    if nothing is set), used when switching the primary brand/franchise
    facet via a sidebar link so the OTHER active facets carry over instead
    of being reset. 'brand'/'franchise' let a link preserve the facet
    that ISN'T the one being switched (e.g. a brand link preserves the
    current franchise, and vice versa), so brand and franchise filters can
    be stacked together (e.g. "Final Fantasy items sold by Artsholic")."""
    parts = {k: v for k, v in {"category": category, "sort": sort, "brand": brand, "franchise": franchise}.items() if v}
    return f"?{urlencode(parts)}" if parts else ""

def _build_active_filters(category: Optional[str], brand: Optional[str], franchise: Optional[str], query: Optional[str], sort: Optional[str]) -> list:
    """Builds the 'active filters' bar shown above the product grid, so it's
    always obvious at a glance which facets are currently narrowing the
    listing (added after a user thought Genshin Impact products had
    vanished, when in fact an unnoticed filter was just still applied from
    an earlier click).

    Every chip's removal link points at '/' (home) with the OTHER active
    facets preserved as query params - one consistent mental model
    regardless of whether the current page is a dedicated /franchises/{x}
    or /brands/{x} route, or the home page with query-string filters.

    Includes 'sort' as a filter too: "Newest" is the default/no-op state
    (omitted), but "All", "Cheapest", and especially "🔥 Sales" all
    genuinely change what's visible - "Sales" specifically HIDES every
    non-discounted item (see _discount_filter_clause), which is exactly the
    kind of surprising, easy-to-forget-about restriction this bar exists to
    surface.
    """
    active = {"category": category, "brand": brand, "franchise": franchise, "q": query}
    if sort and sort != "newest":
        active["sort"] = sort

    chips = []
    for key, value in active.items():
        if not value:
            continue
        remaining = {k: v for k, v in active.items() if k != key and v}
        qs = urlencode(remaining)
        chips.append({
            "type": key,
            "value": value,
            "remove_url": f"/?{qs}" if qs else "/"
        })
    return chips

# Find templates relative to the current file
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

def _tojson_filter(value):
    """Safely serializes a Python value to JSON for embedding inside a
    <script type="application/ld+json"> block. Jinja2Templates (Starlette)
    doesn't register Flask's 'tojson' filter by default, and manually
    interpolating strings into JSON-LD in the template itself would be
    fragile/unsafe for franchise or product names containing quotes,
    apostrophes, or ampersands (e.g. "Assassin's Creed", "Tom Clancy's
    Splinter Cell: Blacklist", "Penn & Teller's Smoke and Mirrors").
    Escapes '<' to '\\u003c' as a standard mitigation against a value
    containing something like '</script>' breaking out of the tag.
    Returns a Markup instance so Jinja's autoescaping doesn't re-escape the
    JSON's own quote characters into HTML entities (&#34;), which would
    otherwise corrupt the JSON."""
    return Markup(json.dumps(value, ensure_ascii=False).replace("<", "\\u003c"))

templates.env.filters["tojson"] = _tojson_filter

def _build_product_item_list(products: list, base_domain: str) -> Optional[dict]:
    """Builds an ItemList JSON-LD payload (Product + Offer per item) for the
    current page of product cards, for potential rich product results.
    priceCurrency comes from each product's own stored `currency` column
    (defaults to USD - see BaseParser.currency for why that's accurate for
    every currently-tracked store).
    """
    if not products:
        return None
    elements = []
    for i, p in enumerate(products, start=1):
        elements.append({
            "@type": "ListItem",
            "position": i,
            "item": {
                "@type": "Product",
                "name": p["product_name"],
                "image": p["image_url"],
                "url": p["store_url"],
                "brand": {"@type": "Brand", "name": p["brand_name"]},
                "offers": {
                    "@type": "Offer",
                    "price": f"{p['current_price']:.2f}",
                    "priceCurrency": p.get("currency", "USD"),
                    "availability": "https://schema.org/InStock",
                    "url": p["store_url"]
                }
            }
        })
    return {
        "@context": "https://schema.org",
        "@type": "ItemList",
        "itemListElement": elements
    }

def _build_breadcrumbs(base_domain: str, crumbs: list) -> dict:
    """Builds a BreadcrumbList JSON-LD payload. 'crumbs' is a list of
    (name, url_or_None) tuples; url is None for the current/last page."""
    items = []
    for i, (name, url) in enumerate(crumbs, start=1):
        entry = {"@type": "ListItem", "position": i, "name": name}
        if url:
            entry["item"] = url
        items.append(entry)
    return {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": items
    }

def get_db_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

# Helper to extract generic stats on products
def fetch_common_stats(conn):
    cursor = conn.cursor()
    cursor.execute("SELECT brand_name, COUNT(*) FROM products WHERE is_active = 1 GROUP BY brand_name")
    brand_stats = {row[0]: row[1] for row in cursor.fetchall()}
    
    # Count how many active products carry each franchise tag (excluding raw
    # brand-name fallbacks and the "Gamer Culture" catch-all, which isn't a
    # real franchise so it shouldn't dominate a "popular franchises" ranking).
    cursor.execute("SELECT franchise_tags FROM products WHERE is_active = 1")
    excluded_tags = {"Geek Apparel", "Insert Coin", "Artsholic", "Fangamer", "Glitch Gear", "Eightysixed", "Xbox Game Studios", "Bethesda", "Blizzard", "Gamer Culture"}
    tag_counts = Counter()
    for row in cursor.fetchall():
        try:
            for tag in json.loads(row[0]):
                if tag and tag not in excluded_tags:
                    tag_counts[tag] += 1
        except Exception:
            continue

    all_franchises = sorted(tag_counts.keys())    # Full A-Z list (for the "Game Collections" directory)
    # Popular = ranked by actual catalog size (product count) rather than
    # alphabetical order, since a franchise with more listed products is a
    # reasonable proxy for real popularity. Ties broken alphabetically for a
    # stable, deterministic order across requests.
    popular_franchises = [
        name for name, _ in sorted(tag_counts.items(), key=lambda kv: (-kv[1], kv[0]))[:18]
    ]
    return brand_stats, popular_franchises, all_franchises

def _build_fts_query(raw: str) -> str:
    """Sanitizes user input into a safe FTS5 prefix-match query (AND semantics)."""
    # Strip FTS operators/punctuation, keep alphanumerics + spaces
    cleaned = re.sub(r"[^0-9A-Za-z\s]", " ", raw or "")
    tokens = [t for t in cleaned.split() if t]
    if not tokens:
        return ""
    # Prefix-match each token so "mass eff" still finds "Mass Effect"
    return " ".join(f"{t}*" for t in tokens)

def _match_franchises(conn, raw: str) -> set:
    """Finds canonical franchise names implied by a search query via the mappings table."""
    q = (raw or "").lower()
    matched = set()
    for keyword, name in conn.execute("SELECT keyword, franchise_name FROM franchise_mappings"):
        k = (keyword or "").lower().strip().strip("-")
        if not k:
            continue
        if re.search(rf"\b{re.escape(k)}\b", q) or name.lower() in q:
            matched.add(name)
    return matched

def _build_search_query(conn, raw: str) -> str:
    """Combines literal prefix matching with franchise-alias expansion (OR).

    Example: 'bonfire' -> 'bonfire* OR "Dark Souls"' so lore/alias searches
    surface correctly-tagged products even when the alias isn't in the product.
    """
    clauses = []
    base = _build_fts_query(raw)
    if base:
        clauses.append(base)
    for name in _match_franchises(conn, raw):
        clauses.append('"' + name.replace('"', '') + '"')
    return " OR ".join(clauses)

def _order_clause(sort: str) -> str:
    """Maps a sort keyword to an ORDER BY clause."""
    if sort == "cheapest":
        return " ORDER BY current_price ASC"
    elif sort == "highest":
        return " ORDER BY current_price DESC"
    elif sort == "discount":
        return """
            ORDER BY CASE WHEN original_price IS NOT NULL AND original_price > current_price 
            THEN ((original_price - current_price) / original_price) ELSE 0 END DESC
        """
    return " ORDER BY updated_at DESC"  # newest

def _discount_filter_clause(sort: str, prefix: str = "") -> str:
    """Restricts results to genuinely discounted items when sort == 'discount'.
    'prefix' lets callers using a table alias (e.g. 'p.') qualify the columns."""
    if sort != "discount":
        return ""
    return f" AND {prefix}original_price IS NOT NULL AND {prefix}original_price > {prefix}current_price"

def _rows_to_products(rows) -> list:
    """Serializes DB rows into template-friendly product dicts."""
    products = []
    for row in rows:
        products.append({
            "store_url": row["store_url"],
            "product_name": row["product_name"],
            "current_price": row["current_price"],
            "original_price": row["original_price"],
            "image_url": row["image_url"],
            "brand_name": row["brand_name"],
            "category": row["category"],
            "franchise_tags": json.loads(row["franchise_tags"]),
            "updated_at": row["updated_at"],
            "currency": row["currency"] if "currency" in row.keys() else "USD"
        })
    return products

# ==========================================
# CRAWLER-FRIENDLY SSR ENDPOINTS (SEO CORE)
# ==========================================

@app.get("/")
def home_index(
    request: Request,
    category: Optional[str] = Query(None),
    sort: Optional[str] = Query("newest"),
    brand: Optional[str] = Query(None),
    franchise: Optional[str] = Query(None),
    page: int = Query(1)
):
    """Prerenders crawler-friendly full-markup grid using Jinja2 templates."""
    conn = get_db_connection()
    brand_stats, popular_franchises, all_franchises = fetch_common_stats(conn)
    cursor = conn.cursor()

    # Build shared WHERE clause
    params = []
    where = " WHERE is_active = 1"
    if brand:
        where += " AND LOWER(brand_name) = ?"
        params.append(brand.lower())
    if category:
        where += " AND LOWER(category) = ?"
        params.append(category.lower())
    if franchise:
        where += " AND franchise_tags LIKE ?"
        params.append(f"%{franchise}%")

    # Restrict to genuinely discounted items when sorting by discount
    where += _discount_filter_clause(sort)

    # Total count for pagination
    total_count = cursor.execute("SELECT COUNT(*) FROM products" + where, tuple(params)).fetchone()[0]

    pagination = build_pagination(
        "/",
        {"category": category, "brand": brand, "franchise": franchise},
        sort, page, total_count
    )
    offset = (pagination["current_page"] - 1) * PAGE_SIZE

    cursor.execute(
        "SELECT * FROM products" + where + _order_clause(sort) + " LIMIT ? OFFSET ?",
        tuple(params) + (PAGE_SIZE, offset)
    )
    rows = cursor.fetchall()
    conn.close()

    products = _rows_to_products(rows)

    structured_data_ld = []
    item_list = _build_product_item_list(products, BASE_DOMAIN)
    if item_list:
        structured_data_ld.append(item_list)

    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "base_domain": BASE_DOMAIN,
            "products": products,
            "brand_stats": brand_stats,
            "popular_franchises": popular_franchises,
            "all_franchises": all_franchises,
            "current_brand": brand,
            "current_category": category,
            "current_franchise": franchise,
            "current_sort": sort,
            "pagination": pagination,
            "preserved_qs": _preserved_secondary_qs(category, sort),
            "preserved_qs_brand": _preserved_secondary_qs(category, sort, franchise=franchise),
            "preserved_qs_franchise": _preserved_secondary_qs(category, sort, brand=brand),
            "structured_data_ld": structured_data_ld,
            "active_filters": _build_active_filters(category, brand, franchise, None, sort)
        }
    )


@app.get("/about")
def about_page(request: Request):
    """Static page explaining the site's purpose. Still needs all_franchises
    so the shared header's Game Collections dropdown renders correctly."""
    conn = get_db_connection()
    _, _, all_franchises = fetch_common_stats(conn)
    conn.close()

    return templates.TemplateResponse(
        request=request,
        name="about.html",
        context={
            "base_domain": BASE_DOMAIN,
            "all_franchises": all_franchises
        }
    )


@app.get("/franchises/{franchise_slug}")
def franchise_landing_ssr(request: Request, franchise_slug: str, category: Optional[str] = Query(None), brand: Optional[str] = Query(None), sort: Optional[str] = Query("newest"), page: int = Query(1)):
    """URL Canonical Route targeting dedicated franchises like /franchises/halo or /franchises/fallout.
    Optionally stacks a 'brand' filter on top (e.g. /franchises/final-fantasy?brand=artsholic
    for "Final Fantasy items sold by Artsholic") - the franchise stays the
    primary/canonical facet (title, breadcrumbs, SEO intro), brand narrows further."""
    # Deduce slug to tag format: "final-fantasy" -> "final fantasy"
    cleaned_slug = franchise_slug.replace("-", " ").strip()

    conn = get_db_connection()
    brand_stats, popular_franchises, all_franchises = fetch_common_stats(conn)
    cursor = conn.cursor()

    where = " WHERE is_active = 1 AND LOWER(franchise_tags) LIKE ?"
    params = [f"%{cleaned_slug.lower()}%"]
    if brand:
        where += " AND LOWER(brand_name) = ?"
        params.append(brand.lower())
    if category:
        where += " AND LOWER(category) = ?"
        params.append(category.lower())
    where += _discount_filter_clause(sort)

    total_count = cursor.execute("SELECT COUNT(*) FROM products" + where, tuple(params)).fetchone()[0]

    pagination = build_pagination(f"/franchises/{franchise_slug}", {"category": category, "brand": brand}, sort, page, total_count)
    offset = (pagination["current_page"] - 1) * PAGE_SIZE

    cursor.execute(
        "SELECT * FROM products" + where + _order_clause(sort) + " LIMIT ? OFFSET ?",
        tuple(params) + (PAGE_SIZE, offset)
    )
    rows = cursor.fetchall()

    # Resolve the human-readable franchise title from the matched rows
    matched_title = cleaned_slug.title()
    if rows:
        try:
            matched_title = next(
                tag for row in rows for tag in json.loads(row["franchise_tags"])
                if tag.lower().strip() == cleaned_slug.lower()
            )
        except Exception:
            pass

    # Resolve the human-readable brand name (real DB casing, e.g. "Artsholic")
    matched_brand = None
    if brand:
        matched_brand = rows[0]["brand_name"] if rows else brand.title()

    # Curated SEO intro write-up for this franchise, if one exists yet (see
    # franchise_content table - populated manually/reviewed before publishing,
    # not auto-generated). Most franchises won't have one yet; that's fine,
    # the block simply doesn't render.
    intro_row = cursor.execute(
        "SELECT intro_text FROM franchise_content WHERE franchise_name = ?", (matched_title,)
    ).fetchone()
    franchise_intro = intro_row["intro_text"] if intro_row else None

    conn.close()

    products = _rows_to_products(rows)

    breadcrumb_items = [
        ("Home", BASE_DOMAIN),
        ("Game Collections", None),
        (matched_title, f"{BASE_DOMAIN}/franchises/{franchise_slug}" if matched_brand else None),
    ]
    if matched_brand:
        breadcrumb_items.append((matched_brand, None))
    structured_data_ld = [_build_breadcrumbs(BASE_DOMAIN, breadcrumb_items)]
    item_list = _build_product_item_list(products, BASE_DOMAIN)
    if item_list:
        structured_data_ld.append(item_list)

    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "base_domain": BASE_DOMAIN,
            "products": products,
            "brand_stats": brand_stats,
            "popular_franchises": popular_franchises,
            "all_franchises": all_franchises,
            "current_brand": matched_brand,
            "current_category": category,
            "current_franchise": matched_title,
            "current_sort": sort,
            "pagination": pagination,
            "preserved_qs": _preserved_secondary_qs(category, sort),
            "preserved_qs_brand": _preserved_secondary_qs(category, sort, franchise=matched_title),
            "preserved_qs_franchise": _preserved_secondary_qs(category, sort, brand=matched_brand),
            "structured_data_ld": structured_data_ld,
            "franchise_intro": franchise_intro,
            "active_filters": _build_active_filters(category, matched_brand, matched_title, None, sort)
        }
    )


@app.get("/brands/{brand_slug}")
def brand_landing_ssr(request: Request, brand_slug: str, category: Optional[str] = Query(None), franchise: Optional[str] = Query(None), sort: Optional[str] = Query("newest"), page: int = Query(1)):
    """URL Canonical Route targeting vendor profiles like /brands/bethesda or /brands/blizzard.
    Optionally stacks a 'franchise' filter on top (e.g. /brands/artsholic?franchise=final-fantasy
    for "Final Fantasy items sold by Artsholic") - the brand stays the
    primary/canonical facet (title, breadcrumbs), franchise narrows further."""
    conn = get_db_connection()
    brand_stats, popular_franchises, all_franchises = fetch_common_stats(conn)
    cursor = conn.cursor()

    where = " WHERE is_active = 1 AND LOWER(brand_name) = ?"
    params = [brand_slug.strip().lower()]
    cleaned_franchise_slug = ""
    if franchise:
        cleaned_franchise_slug = franchise.replace("-", " ").strip()
        where += " AND LOWER(franchise_tags) LIKE ?"
        params.append(f"%{cleaned_franchise_slug.lower()}%")
    if category:
        where += " AND LOWER(category) = ?"
        params.append(category.lower())
    where += _discount_filter_clause(sort)

    total_count = cursor.execute("SELECT COUNT(*) FROM products" + where, tuple(params)).fetchone()[0]

    pagination = build_pagination(f"/brands/{brand_slug}", {"category": category, "franchise": franchise}, sort, page, total_count)
    offset = (pagination["current_page"] - 1) * PAGE_SIZE

    cursor.execute(
        "SELECT * FROM products" + where + _order_clause(sort) + " LIMIT ? OFFSET ?",
        tuple(params) + (PAGE_SIZE, offset)
    )
    rows = cursor.fetchall()

    # Track real brand title
    matched_brand = brand_slug.title()
    if rows:
        matched_brand = rows[0]["brand_name"]

    # Resolve the human-readable franchise name from the matched rows
    matched_franchise = None
    if franchise:
        matched_franchise = cleaned_franchise_slug.title()
        if rows:
            try:
                matched_franchise = next(
                    tag for row in rows for tag in json.loads(row["franchise_tags"])
                    if tag.lower().strip() == cleaned_franchise_slug.lower()
                )
            except Exception:
                pass

    conn.close()

    products = _rows_to_products(rows)

    breadcrumb_items = [
        ("Home", BASE_DOMAIN),
        ("Brands", None),
        (matched_brand, f"{BASE_DOMAIN}/brands/{brand_slug}" if matched_franchise else None),
    ]
    if matched_franchise:
        breadcrumb_items.append((matched_franchise, None))
    structured_data_ld = [_build_breadcrumbs(BASE_DOMAIN, breadcrumb_items)]
    item_list = _build_product_item_list(products, BASE_DOMAIN)
    if item_list:
        structured_data_ld.append(item_list)

    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "base_domain": BASE_DOMAIN,
            "products": products,
            "brand_stats": brand_stats,
            "popular_franchises": popular_franchises,
            "all_franchises": all_franchises,
            "current_brand": matched_brand,
            "current_category": category,
            "current_franchise": matched_franchise,
            "current_sort": sort,
            "pagination": pagination,
            "preserved_qs": _preserved_secondary_qs(category, sort),
            "preserved_qs_brand": _preserved_secondary_qs(category, sort, franchise=matched_franchise),
            "preserved_qs_franchise": _preserved_secondary_qs(category, sort, brand=matched_brand),
            "structured_data_ld": structured_data_ld,
            "active_filters": _build_active_filters(category, matched_brand, matched_franchise, None, sort)
        }
    )


# ==========================================
# SEARCH ENDPOINT (FTS5 + FRANCHISE ALIAS EXPANSION)
# ==========================================

@app.get("/search")
def search_ssr(request: Request, q: Optional[str] = Query(None), category: Optional[str] = Query(None), sort: Optional[str] = Query("newest"), page: int = Query(1)):
    """Full-text search across product names, brands, franchises, and categories via FTS5,
    with franchise-alias query expansion (e.g. 'bonfire' -> Dark Souls)."""
    conn = get_db_connection()
    brand_stats, popular_franchises, all_franchises = fetch_common_stats(conn)
    cursor = conn.cursor()

    match_query = _build_search_query(conn, q or "")
    products = []
    pagination = build_pagination("/search", {"q": q, "category": category}, sort, page, 0)
    discount_filter = _discount_filter_clause(sort, prefix="p.")
    category_filter = " AND LOWER(p.category) = ?" if category else ""

    if match_query:
        category_params = (category.lower(),) if category else ()

        total_count = cursor.execute(
            "SELECT COUNT(*) FROM products_fts "
            "JOIN products p ON p.rowid = products_fts.rowid "
            "WHERE products_fts MATCH ? AND p.is_active = 1" + category_filter + discount_filter,
            (match_query,) + category_params
        ).fetchone()[0]

        pagination = build_pagination("/search", {"q": q, "category": category}, sort, page, total_count)
        offset = (pagination["current_page"] - 1) * PAGE_SIZE

        cursor.execute(
            "SELECT p.* FROM products_fts "
            "JOIN products p ON p.rowid = products_fts.rowid "
            "WHERE products_fts MATCH ? AND p.is_active = 1" + category_filter + discount_filter + _order_clause(sort) + " LIMIT ? OFFSET ?",
            (match_query,) + category_params + (PAGE_SIZE, offset)
        )
        products = _rows_to_products(cursor.fetchall())

    conn.close()

    structured_data_ld = []
    item_list = _build_product_item_list(products, BASE_DOMAIN)
    if item_list:
        structured_data_ld.append(item_list)

    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "base_domain": BASE_DOMAIN,
            "products": products,
            "brand_stats": brand_stats,
            "popular_franchises": popular_franchises,
            "all_franchises": all_franchises,
            "current_brand": None,
            "current_category": category,
            "current_franchise": None,
            "current_query": q,
            "current_sort": sort,
            "pagination": pagination,
            "preserved_qs": _preserved_secondary_qs(category, sort),
            "preserved_qs_brand": _preserved_secondary_qs(category, sort),
            "preserved_qs_franchise": _preserved_secondary_qs(category, sort),
            "structured_data_ld": structured_data_ld,
            "active_filters": _build_active_filters(category, None, None, q, sort)
        }
    )


# ==========================================
# DYNAMIC SITEMAP ENGINE (THE SEO SECRET WEAPON)
# ==========================================

@app.get("/sitemap.xml")
def generate_sitemap():
    """Generates an XML sitemap of every active listing and landing path."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 1. Fetch active deep-links
    cursor.execute("SELECT store_url, updated_at FROM products WHERE is_active = 1")
    products = cursor.fetchall()
    
    # 2. Fetch distinct brands
    cursor.execute("SELECT DISTINCT brand_name FROM products WHERE is_active = 1")
    brands = [row[0] for row in cursor.fetchall()]
    
    # 3. Fetch popular franchises
    cursor.execute("SELECT DISTINCT franchise_tags FROM products WHERE is_active = 1")
    franchises = set()
    for row in cursor.fetchall():
        try:
            for tag in json.loads(row[0]):
                if tag:
                    franchises.add(tag)
        except Exception:
            continue
            
    conn.close()

    # Format Sitemap markup elements
    base_domain = BASE_DOMAIN # Change to active domain name
    sitemap_entries = [
        f"""<url>
            <loc>{base_domain}/</loc>
            <changefreq>daily</changefreq>
            <priority>1.0</priority>
        </url>"""
    ]

    # Append brand profiles
    for brand in brands:
        brand_slug = brand.lower().replace(" ", "-").strip()
        sitemap_entries.append(
            f"""<url>
                <loc>{xml_escape(f"{base_domain}/brands/{brand_slug}")}</loc>
                <changefreq>weekly</changefreq>
                <priority>0.8</priority>
            </url>"""
        )

    # Append franchise tags
    for franchise in franchises:
        slug = franchise.lower().replace(" ", "-").strip()
        sitemap_entries.append(
            f"""<url>
                <loc>{xml_escape(f"{base_domain}/franchises/{slug}")}</loc>
                <changefreq>weekly</changefreq>
                <priority>0.8</priority>
            </url>"""
        )

    # Assemble wrapper sitemap response
    xml_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
{"".join(sitemap_entries)}
</urlset>"""

    return Response(content=xml_content, media_type="application/xml")


@app.get("/robots.txt")
def generate_robots_txt():
    """Points crawlers at the dynamic sitemap and allows full indexing."""
    lines = [
        "User-agent: *",
        "Allow: /",
        f"Sitemap: {BASE_DOMAIN}/sitemap.xml",
    ]
    return PlainTextResponse("\n".join(lines))


# ==========================================
# HEALTH CHECK (UPTIME MONITORING)
# ==========================================

@app.get("/healthz")
def healthz():
    """Lightweight liveness/readiness check for uptime monitors and the cloud
    host's load balancer. Verifies the SQLite database is actually reachable
    (not just that the process is running) without doing any heavy work."""
    try:
        conn = get_db_connection()
        conn.execute("SELECT 1").fetchone()
        conn.close()
        db_ok = True
    except Exception:
        db_ok = False

    status_code = 200 if db_ok else 503
    return JSONResponse(
        status_code=status_code,
        content={"status": "ok" if db_ok else "error", "database": "reachable" if db_ok else "unreachable"}
    )