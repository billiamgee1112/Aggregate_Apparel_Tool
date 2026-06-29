# api.py
import sqlite3
import json
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional, List

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


# api.py
@app.get("/products")
def get_products(
    q: Optional[str] = Query(None, description="Search term for product names (inexact)"),
    brand: Optional[str] = Query(None, description="Filter by brand"),
    max_price: Optional[float] = Query(None, description="Filter by maximum price"),
    tag: Optional[str] = Query(None, description="Filter by franchise tag"),
    sort: Optional[str] = Query("newest"),
    limit: int = Query(24, ge=1, le=100),
    offset: int = Query(0, ge=0)
):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    query = "SELECT * FROM products WHERE 1=1"
    params = []
    
    # Inexact search using SQL LIKE
    if q:
        query += " AND product_name LIKE ?"
        params.append(f"%{q}%") # Matches any name containing the query term
        
    if brand:
        query += " AND LOWER(brand_name) = ?"
        params.append(brand.lower())
        
    if max_price is not None:
        query += " AND current_price <= ?"
        params.append(max_price)
        
    if tag:
        query += " AND franchise_tags LIKE ?"
        params.append(f"%{tag}%")
        
    # Apply Sorting and Pagination ...
        
    # Apply Sorting
    if sort == "cheapest":
        query += " ORDER BY current_price ASC"
    elif sort == "highest":
        query += " ORDER BY current_price DESC"
    else:  # newest
        query += " ORDER BY updated_at DESC"
        
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