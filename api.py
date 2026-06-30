# api.py
import sqlite3
import json
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional, List
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
    
    # Fetch total items
    cursor.execute("SELECT COUNT(*) FROM products")
    total_products = cursor.fetchone()[0]
    
    # Fetch count by brand
    cursor.execute("SELECT brand_name, COUNT(*) FROM products GROUP BY brand_name")
    brand_stats = {row[0]: row[1] for row in cursor.fetchall()}
    
    conn.close()
    return {
        "status": "online",
        "total_active_items": total_products,
        "brand_aggregations": brand_stats
    }


# api.py (Segment highlighting /products endpoint changes)

@app.get("/products")
def get_products(
    q: Optional[str] = Query(None, description="Search term for product names (using optimized FTS5)"),
    brand: Optional[str] = Query(None, description="Filter by brand"),
    max_price: Optional[float] = Query(None, description="Filter by maximum price"),
    tag: Optional[str] = Query(None, description="Filter by franchise tag"),
    sort: Optional[str] = Query("newest"),
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
            WHERE products_fts MATCH ?
        """
        params.append(fts_query_string)
    else:
        query = "SELECT * FROM products WHERE 1=1"
        
    if brand:
        query += " AND LOWER(p.brand_name) = ?" if q else " AND LOWER(brand_name) = ?"
        params.append(brand.lower())
        
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
            "franchise_tags": json.loads(row["franchise_tags"]),  # Deserialize JSON string
            "updated_at": row["updated_at"]
        })
        
    return {
        "count": len(products),
        "limit": limit,
        "offset": offset,
        "results": products
    }


@app.get("/franchises")
def get_franchises():
    """Returns a unique list of all franchise tags stored in the database."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT franchise_tags FROM products")
    rows = cursor.fetchall()
    conn.close()
    
    unique_tags = set()
    for row in rows:
        tags = json.loads(row[0])
        for tag in tags:
            if tag:
                unique_tags.add(tag)
                
    return sorted(list(unique_tags))