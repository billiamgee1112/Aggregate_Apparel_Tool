# database.py
import sqlite3
import json
from models import GamingClothingItem

DB_NAME = "apparel_aggregator.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # 1. Primary Relational Table with category and active states
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS products (
            store_url TEXT PRIMARY KEY,
            product_name TEXT NOT NULL,
            current_price REAL NOT NULL,
            original_price REAL,
            image_url TEXT NOT NULL,
            brand_name TEXT NOT NULL,
            franchise_tags TEXT NOT NULL,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            is_active INTEGER DEFAULT 1,
            category TEXT NOT NULL DEFAULT 'other'
        )
    """)
    
    # 2. Relational Price History Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS price_history (
            store_url TEXT NOT NULL,
            price REAL NOT NULL,
            recorded_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(store_url) REFERENCES products(store_url) ON DELETE CASCADE
        )
    """)
    
    # Create FTS5 Virtual Table for Search including category
    cursor.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS products_fts USING fts5(
            store_url UNINDEXED,
            product_name,
            brand_name,
            franchise_tags,
            category,
            content='products',
            content_rowid='rowid'
        )
    """)
    
    # Sync Triggers to automate FTS synchronizations including category syncing
    cursor.execute("""
        CREATE TRIGGER IF NOT EXISTS products_after_insert AFTER INSERT ON products BEGIN
            INSERT INTO products_fts(rowid, store_url, product_name, brand_name, franchise_tags, category)
            VALUES (new.rowid, new.store_url, new.product_name, new.brand_name, new.franchise_tags, new.category);
        END;
    """)
    
    cursor.execute("""
        CREATE TRIGGER IF NOT EXISTS products_after_delete AFTER DELETE ON products BEGIN
            INSERT INTO products_fts(products_fts, rowid, store_url, product_name, brand_name, franchise_tags, category)
            VALUES('delete', old.rowid, old.store_url, old.product_name, old.brand_name, old.franchise_tags, old.category);
        END;
    """)
    
    cursor.execute("""
        CREATE TRIGGER IF NOT EXISTS products_after_update AFTER UPDATE ON products BEGIN
            INSERT INTO products_fts(products_fts, rowid, store_url, product_name, brand_name, franchise_tags, category)
            VALUES('delete', old.rowid, old.store_url, old.product_name, old.brand_name, old.franchise_tags, old.category);
            INSERT INTO products_fts(rowid, store_url, product_name, brand_name, franchise_tags, category)
            VALUES(new.rowid, new.store_url, new.product_name, new.brand_name, new.franchise_tags, new.category);
        END;
    """)
    
    # Performance indices
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_products_brand ON products(brand_name);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_products_price ON products(current_price);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_products_name ON products(product_name);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_products_active ON products(is_active);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_products_category ON products(category);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_price_history_url ON price_history(store_url);")
    
    conn.commit()
    conn.close()
    print("Database structures, triggers, and price history indices initialized successfully.")

def save_products_to_db(products: list[GamingClothingItem]):
    """Inserts or updates scraped products, managing active in-stock statuses and price progression history."""
    conn = sqlite3.connect(DB_NAME)
    # Mandates cascade deletions on the price_history table
    conn.execute("PRAGMA foreign_keys = ON;")
    cursor = conn.cursor()
    
    # 1. Before saving new runs, mark existing database products to inactive (is_active = 0)
    cursor.execute("UPDATE products SET is_active = 0")
    conn.commit()
    
    # 2. Insert or update parsed elements, reactivating active products (is_active = 1)
    for product in products:
        # Check if product exists and if the price has shifted
        cursor.execute("SELECT current_price FROM products WHERE store_url = ?", (str(product.store_url),))
        row = cursor.fetchone()
        
        has_changed = False
        if row is None:
            # Brand-new product
            has_changed = True
        elif float(row[0]) != float(product.current_price):
            # Price movement!
            has_changed = True
            
        cursor.execute("""
            INSERT INTO products (
                store_url, product_name, current_price, original_price, image_url, brand_name, franchise_tags, is_active, category, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(store_url) DO UPDATE SET
                product_name=excluded.product_name,
                current_price=excluded.current_price,
                original_price=excluded.original_price,
                image_url=excluded.image_url,
                category=excluded.category,
                is_active=1,
                updated_at=CURRENT_TIMESTAMP
        """, (
            str(product.store_url),
            product.product_name,
            product.current_price,
            product.original_price,
            str(product.image_url),
            product.brand_name,
            json.dumps(product.franchise_tags),
            product.category
        ))
        
        # Log a price point into price progression history on changes
        if has_changed:
            cursor.execute("""
                INSERT INTO price_history (store_url, price)
                VALUES (?, ?)
            """, (str(product.store_url), product.current_price))
        
    conn.commit()
    
    # 3. Clean Sweep Cleanup:
    # Delete inactive products (Cascade deletes will automatically drop their tracking logs from price_history)
    cursor.execute("DELETE FROM products WHERE is_active = 0")
    deleted_count = cursor.rowcount
    conn.commit()
    
    conn.close()
    print(f"Successfully processed {len(products)} active products.")
    if deleted_count > 0:
        print(f"Clean Sweep: Purged {deleted_count} out-of-stock items no longer seen on storefronts.")