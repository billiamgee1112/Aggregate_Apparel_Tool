# api.py
import sqlite3
import json
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
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

# Enable CORS so your future frontend (React, Next.js, etc.) can contact this API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DB_NAME = "apparel_aggregator.db"

def get_db_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row  # Returns query attributes mapped as dictionaries
    return conn

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

# Initialize Background Scheduler
scheduler = BackgroundScheduler()

# Schedule the scraper to run automatically every 24 hours
scheduler.add_job(run_scraper_job, "interval", hours=24)

@app.on_event("startup")
def start_scheduler():
    """Starts the scheduler when the FastAPI application boots."""
    if not scheduler.running:
        scheduler.start()
        print("FastAPI Startup: Background scheduler initiated.")
        
        # Trigger the scraper once immediately for testing/verification
        print("FastAPI Startup: Queueing immediate one-off scrape task...")
        scheduler.add_job(run_scraper_job)

@app.on_event("shutdown")
def stop_scheduler():
    """Gracefully shuts down the scheduler when the server stops."""
    if scheduler.running:
        scheduler.shutdown()
        print("FastAPI Shutdown: Background scheduler stopped.")
        
# ==========================================
# API ENDPOINTS
# ==========================================

@app.get("/")
def read_root():
    """Returns database metadata and system stats."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Fetch total active items
    cursor.execute("SELECT COUNT(*) FROM products WHERE is_active = 1")
    total_products = cursor.fetchone()[0]
    
    # Fetch count by active brand
    cursor.execute("SELECT brand_name, COUNT(*) FROM products WHERE is_active = 1 GROUP BY brand_name")
    brand_stats = {row[0]: row[1] for row in cursor.fetchall()}
    
    conn.close()
    return {
        "status": "online",
        "total_active_items": total_products,
        "brand_aggregations": brand_stats
    }

@app.get("/products")
def get_products(
    q: Optional[str] = Query(None, description="Search term for product names (using optimized FTS5)"),
    brand: Optional[str] = Query(None, description="Filter by brand"),
    category: Optional[str] = Query(None, description="Filter by category (e.g. t-shirt, hoodie, sweater, jacket, pants)"),
    max_price: Optional[float] = Query(None, description="Filter by maximum price"),
    tag: Optional[str] = Query(None, description="Filter by franchise tag"),
    sort: Optional[str] = Query("newest", description="Sort products (newest, cheapest, highest, discount)"),
    limit: int = Query(24, ge=1, le=100),
    offset: int = Query(0, ge=0)
):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    params = []
    
    if q:
        # Format search term to match multiple partial words: e.g. "zelda hoo" -> "zelda* AND hoo*"
        search_terms = [f"{term.strip()}*" for term in q.split() if term.strip()]
        fts_query_string = " AND ".join(search_terms)
        
        # Query utilizing index match and joining primary table data
        query = """
            SELECT p.* FROM products p
            JOIN products_fts f ON p.rowid = f.rowid
            WHERE products_fts MATCH ? AND p.is_active = 1
        """
        params.append(fts_query_string)
    else:
        query = "SELECT * FROM products WHERE is_active = 1"
        
    if brand:
        query += " AND LOWER(p.brand_name) = ?" if q else " AND LOWER(brand_name) = ?"
        params.append(brand.lower())
        
    if category:
        query += " AND LOWER(p.category) = ?" if q else " AND LOWER(category) = ?"
        params.append(category.lower())
        
    if max_price is not None:
        query += " AND p.current_price <= ?" if q else " AND current_price <= ?"
        params.append(max_price)
        
    if tag:
        query += " AND p.franchise_tags LIKE ?" if q else " AND franchise_tags LIKE ?"
        params.append(f"%{tag}%")
        
    # Apply Sorting
    if sort == "cheapest":
        query += " ORDER BY p.current_price ASC" if q else " ORDER BY current_price ASC"
    elif sort == "highest":
        query += " ORDER BY p.current_price DESC" if q else " ORDER BY current_price DESC"
    elif sort == "discount":
        # Orders highest-percentage discounts first (only evaluates items where original_price exists and exceeds selling price)
        query += """
            ORDER BY CASE WHEN p.original_price IS NOT NULL AND p.original_price > p.current_price 
            THEN ((p.original_price - p.current_price) / p.original_price) ELSE 0 END DESC
        """ if q else """
            ORDER BY CASE WHEN original_price IS NOT NULL AND original_price > current_price 
            THEN ((original_price - current_price) / original_price) ELSE 0 END DESC
        """
    else:  # newest
        query += " ORDER BY p.updated_at DESC" if q else " ORDER BY updated_at DESC"
        
    # Apply Pagination
    query += " LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    
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
            "franchise_tags": json.loads(row["franchise_tags"]),  # Deserialize JSON string
            "updated_at": row["updated_at"]
        })
        
    return {
        "count": len(products),
        "limit": limit,
        "offset": offset,
        "results": products
    }


@app.get("/products/price-history")
def get_price_history(store_url: str):
    """Returns the full chronological price tracking timeline for a specific item url."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT price, recorded_at 
        FROM price_history 
        WHERE store_url = ? 
        ORDER BY recorded_at ASC
    """, (store_url,))
    rows = cursor.fetchall()
    conn.close()
    
    return [
        {"price": row["price"], "recorded_at": row["recorded_at"]}
        for row in rows
    ]


@app.get("/franchises")
def get_franchises():
    """Returns a unique list of all franchise tags stored in the database."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT franchise_tags FROM products WHERE is_active = 1")
    rows = cursor.fetchall()
    conn.close()
    
    unique_tags = set()
    for row in rows:
        tags = json.loads(row[0])
        for tag in tags:
            if tag:
                unique_tags.add(tag)
                
    return sorted(list(unique_tags))


# ==========================================
# ADMINISTRATIVE METADATA MANAGEMENT (DYNAMIC TAXONOMY)
# ==========================================

class TaxonomyMappingRequest(BaseModel):
    keyword: str
    franchise_name: str


@app.post("/admin/mappings")
def add_new_franchise_mapping(payload: TaxonomyMappingRequest):
    """Creates or replaces a dynamic keyword-to-franchise map on the database level."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT OR REPLACE INTO franchise_mappings (keyword, franchise_name)
            VALUES (?, ?)
        """, (payload.keyword.lower().strip(), payload.franchise_name.strip()))
        conn.commit()
        return {"status": "success", "message": f"Mapped '{payload.keyword.lower()}' to '{payload.franchise_name}'"}
    except Exception as e:
        return {"status": "error", "message": str(e)}
    finally:
        conn.close()


@app.get("/admin/unmapped")
def get_unmapped_products():
    """Identifies products currently fallback tagged with their vendor brand name."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT DISTINCT product_name, store_url, brand_name 
        FROM products 
        WHERE is_active = 1 
          AND (
            franchise_tags LIKE '%"' || brand_name || '"%' 
            OR franchise_tags LIKE '%"Geek Apparel"%'
            OR franchise_tags = '[]'
          )
    """)
    rows = cursor.fetchall()
    conn.close()
    
    results = [dict(row) for row in rows]
    return {
        "unmapped_count": len(results),
        "results": results
    }