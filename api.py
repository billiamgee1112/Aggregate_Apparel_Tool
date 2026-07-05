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
from typing import Optional, List
from pydantic import BaseModel
from apscheduler.schedulers.background import BackgroundScheduler
from scraper import scrape_store
import asyncio
from urllib.parse import urlencode
from math import ceil
import re

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
        "canonical": canonical,
        "start_index": (page - 1) * PAGE_SIZE + 1 if total_count else 0,
        "end_index": min(page * PAGE_SIZE, total_count),
    }

# Find templates relative to the current file
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

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
            "updated_at": row["updated_at"]
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
            "pagination": pagination
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
def franchise_landing_ssr(request: Request, franchise_slug: str, sort: Optional[str] = Query("newest"), page: int = Query(1)):
    """URL Canonical Route targeting dedicated franchises like /franchises/halo or /franchises/fallout."""
    # Deduce slug to tag format: "final-fantasy" -> "final fantasy"
    cleaned_slug = franchise_slug.replace("-", " ").strip()

    conn = get_db_connection()
    brand_stats, popular_franchises, all_franchises = fetch_common_stats(conn)
    cursor = conn.cursor()

    where = " WHERE is_active = 1 AND LOWER(franchise_tags) LIKE ?"
    like_param = (f"%{cleaned_slug.lower()}%",)
    where += _discount_filter_clause(sort)

    total_count = cursor.execute("SELECT COUNT(*) FROM products" + where, like_param).fetchone()[0]

    pagination = build_pagination(f"/franchises/{franchise_slug}", {}, sort, page, total_count)
    offset = (pagination["current_page"] - 1) * PAGE_SIZE

    cursor.execute(
        "SELECT * FROM products" + where + _order_clause(sort) + " LIMIT ? OFFSET ?",
        like_param + (PAGE_SIZE, offset)
    )
    rows = cursor.fetchall()
    conn.close()

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

    products = _rows_to_products(rows)

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
            "current_category": None,
            "current_franchise": matched_title,
            "current_sort": sort,
            "pagination": pagination
        }
    )


@app.get("/brands/{brand_slug}")
def brand_landing_ssr(request: Request, brand_slug: str, sort: Optional[str] = Query("newest"), page: int = Query(1)):
    """URL Canonical Route targeting vendor profiles like /brands/bethesda or /brands/blizzard."""
    conn = get_db_connection()
    brand_stats, popular_franchises, all_franchises = fetch_common_stats(conn)
    cursor = conn.cursor()

    where = " WHERE is_active = 1 AND LOWER(brand_name) = ?"
    brand_param = (brand_slug.strip().lower(),)
    where += _discount_filter_clause(sort)

    total_count = cursor.execute("SELECT COUNT(*) FROM products" + where, brand_param).fetchone()[0]

    pagination = build_pagination(f"/brands/{brand_slug}", {}, sort, page, total_count)
    offset = (pagination["current_page"] - 1) * PAGE_SIZE

    cursor.execute(
        "SELECT * FROM products" + where + _order_clause(sort) + " LIMIT ? OFFSET ?",
        brand_param + (PAGE_SIZE, offset)
    )
    rows = cursor.fetchall()

    # Track real brand title
    matched_brand = brand_slug.title()
    if rows:
        matched_brand = rows[0]["brand_name"]
    conn.close()

    products = _rows_to_products(rows)

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
            "current_category": None,
            "current_franchise": None,
            "current_sort": sort,
            "pagination": pagination
        }
    )


# ==========================================
# SEARCH ENDPOINT (FTS5 + FRANCHISE ALIAS EXPANSION)
# ==========================================

@app.get("/search")
def search_ssr(request: Request, q: Optional[str] = Query(None), sort: Optional[str] = Query("newest"), page: int = Query(1)):
    """Full-text search across product names, brands, franchises, and categories via FTS5,
    with franchise-alias query expansion (e.g. 'bonfire' -> Dark Souls)."""
    conn = get_db_connection()
    brand_stats, popular_franchises, all_franchises = fetch_common_stats(conn)
    cursor = conn.cursor()

    match_query = _build_search_query(conn, q or "")
    products = []
    pagination = build_pagination("/search", {"q": q}, sort, page, 0)
    discount_filter = _discount_filter_clause(sort, prefix="p.")

    if match_query:
        total_count = cursor.execute(
            "SELECT COUNT(*) FROM products_fts "
            "JOIN products p ON p.rowid = products_fts.rowid "
            "WHERE products_fts MATCH ? AND p.is_active = 1" + discount_filter,
            (match_query,)
        ).fetchone()[0]

        pagination = build_pagination("/search", {"q": q}, sort, page, total_count)
        offset = (pagination["current_page"] - 1) * PAGE_SIZE

        cursor.execute(
            "SELECT p.* FROM products_fts "
            "JOIN products p ON p.rowid = products_fts.rowid "
            "WHERE products_fts MATCH ? AND p.is_active = 1" + discount_filter + _order_clause(sort) + " LIMIT ? OFFSET ?",
            (match_query, PAGE_SIZE, offset)
        )
        products = _rows_to_products(cursor.fetchall())

    conn.close()

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
            "current_category": None,
            "current_franchise": None,
            "current_query": q,
            "current_sort": sort,
            "pagination": pagination
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
                <loc>{base_domain}/brands/{brand_slug}</loc>
                <changefreq>weekly</changefreq>
                <priority>0.8</priority>
            </url>"""
        )

    # Append franchise tags
    for franchise in franchises:
        slug = franchise.lower().replace(" ", "-").strip()
        sitemap_entries.append(
            f"""<url>
                <loc>{base_domain}/franchises/{slug}</loc>
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