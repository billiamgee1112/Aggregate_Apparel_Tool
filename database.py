# database.py
import sqlite3
import json
from models import GamingClothingItem

DB_NAME = "apparel_aggregator.db"

def init_db():
    """Initializes the SQLite database and creates the products table."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # Store franchise_tags as a serialized JSON string in SQLite
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS products (
            store_url TEXT PRIMARY KEY,
            product_name TEXT NOT NULL,
            current_price REAL NOT NULL,
            original_price REAL,
            image_url TEXT NOT NULL,
            brand_name TEXT NOT NULL,
            franchise_tags TEXT NOT NULL,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()
    print("Database initialized successfully.")

def save_products_to_db(products: list[GamingClothingItem]):
    """Inserts or updates scraped products in the database."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    for product in products:
        cursor.execute("""
            INSERT INTO products (
                store_url, product_name, current_price, original_price, image_url, brand_name, franchise_tags, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(store_url) DO UPDATE SET
                product_name=excluded.product_name,
                current_price=excluded.current_price,
                original_price=excluded.original_price,
                image_url=excluded.image_url,
                updated_at=CURRENT_TIMESTAMP
        """, (
            str(product.store_url),
            product.product_name,
            product.current_price,
            product.original_price,
            str(product.image_url),
            product.brand_name,
            json.dumps(product.franchise_tags)  # Serialize list to JSON string
        ))
        
    conn.commit()
    conn.close()
    print(f"Successfully upserted {len(products)} products in the database.")