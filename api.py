# api.py
import sqlite3
import json
import os
from fastapi import FastAPI, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from fastapi.templating import Jinja2Templates
from typing import Optional, List
from pydantic import BaseModel
from apscheduler.schedulers.background import BackgroundScheduler
from scraper import scrape_store
import asyncio

app = FastAPI(
    title="Geek Apparel Aggregator API",
    description="Queryable API endpoints for aggregated clothing items",
    version="1.0.0"
)

# Enable CORS 
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DB_NAME = "apparel_aggregator.db"

# Find templates relative to the current file
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
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
    
    # Fetch a standard list of high-volume franchise tags for sidebar navigation
    cursor.execute("SELECT franchise_tags FROM products WHERE is_active = 1")
    unique_tags = set()
    for row in cursor.fetchall():
        try:
            for tag in json.loads(row[0]):
                if tag and tag not in ["Geek Apparel", "Insert Coin", "Artsholic", "Fangamer", "Glitch Gear", "Eightysixed", "Xbox Game Studios", "Bethesda", "Blizzard"]:
                    unique_tags.add(tag)
        except Exception:
            continue
    popular_franchises = sorted(list(unique_tags))[:18] # Top 18 index mappings
    return brand_stats, popular_franchises

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
scheduler.add_job(run_scraper_job, "interval", hours=24)

@app.on_event("startup")
def start_scheduler():
    if not scheduler.running:
        scheduler.start()
        print("FastAPI Startup: Background scheduler initiated.")

@app.on_event("shutdown")
def stop_scheduler():
    if scheduler.running:
        scheduler.shutdown()

# ==========================================
# CRAWLER-FRIENDLY SSR ENDPOINTS (SEO CORE)
# ==========================================

@app.get("/")
def home_index(
    request: Request,
    category: Optional[str] = Query(None),
    sort: Optional[str] = Query("newest"),
    brand: Optional[str] = Query(None),
    franchise: Optional[str] = Query(None)
):
    """Prerenders crawler-friendly full-markup grid using Jinja2 templates."""
    conn = get_db_connection()
    brand_stats, popular_franchises = fetch_common_stats(conn)
    cursor = conn.cursor()

    # Query with filter attributes
    params = []
    query = "SELECT * FROM products WHERE is_active = 1"

    if brand:
        query += " AND LOWER(brand_name) = ?"
        params.append(brand.lower())
    if category:
        query += " AND LOWER(category) = ?"
        params.append(category.lower())
    if franchise:
        query += " AND franchise_tags LIKE ?"
        params.append(f"%{franchise}%")

    # Apply Sorting
    if sort == "cheapest":
        query += " ORDER BY current_price ASC"
    elif sort == "highest":
        query += " ORDER BY current_price DESC"
    elif sort == "discount":
        query += """
            ORDER BY CASE WHEN original_price IS NOT NULL AND original_price > current_price 
            THEN ((original_price - current_price) / original_price) ELSE 0 END DESC
        """
    else:  # newest
        query += " ORDER BY updated_at DESC"

    cursor.execute(query, tuple(params))
    rows = cursor.fetchall()
    conn.close()

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

    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "products": products,
            "brand_stats": brand_stats,
            "popular_franchises": popular_franchises,
            "current_brand": brand,
            "current_category": category,
            "current_franchise": franchise,
            "current_sort": sort
        }
    )


@app.get("/franchises/{franchise_slug}")
def franchise_landing_ssr(request: Request, franchise_slug: str, sort: Optional[str] = Query("newest")):
    """URL Canonical Route targeting dedicated franchises like /franchises/halo or /franchises/fallout."""
    # Deduce slug to tag format: "final-fantasy" -> "final fantasy" but also check database mapping matches
    cleaned_slug = franchise_slug.replace("-", " ").strip()
    
    conn = get_db_connection()
    brand_stats, popular_franchises = fetch_common_stats(conn)
    cursor = conn.cursor()

    # Search for products with matching slug
    cursor.execute("""
        SELECT * FROM products 
        WHERE is_active = 1 AND LOWER(franchise_tags) LIKE ?
    """, (f"%{cleaned_slug}%",))
    rows = cursor.fetchall()
    conn.close()

    # Fallback to absolute closest title matches if mapping is unindexed
    matched_title = cleaned_slug.title()
    if rows:
        try:
            matched_title = next(
                tag for row in rows for tag in json.loads(row["franchise_tags"]) 
                if tag.lower().strip() == cleaned_slug
            )
        except Exception:
            pass

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

    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "products": products,
            "brand_stats": brand_stats,
            "popular_franchises": popular_franchises,
            "current_brand": None,
            "current_category": None,
            "current_franchise": matched_title,
            "current_sort": sort
        }
    )


@app.get("/brands/{brand_slug}")
def brand_landing_ssr(request: Request, brand_slug: str, sort: Optional[str] = Query("newest")):
    """URL Canonical Route targeting vendor profiles like /brands/bethesda or /brands/blizzard."""
    conn = get_db_connection()
    brand_stats, popular_franchises = fetch_common_stats(conn)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT * FROM products 
        WHERE is_active = 1 AND LOWER(brand_name) = ?
    """, (brand_slug.strip().lower(),))
    rows = cursor.fetchall()
    conn.close()

    # Track real brand title
    matched_brand = brand_slug.title()
    if rows:
        matched_brand = rows[0]["brand_name"]

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

    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "products": products,
            "brand_stats": brand_stats,
            "popular_franchises": popular_franchises,
            "current_brand": matched_brand,
            "current_category": None,
            "current_franchise": None,
            "current_sort": sort
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
    base_domain = "https://ggapparel.net" # Change to active domain name
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