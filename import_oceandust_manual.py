# -*- coding: utf-8 -*-
"""One-off/periodic manual importer for OceanDust, since their Cloudflare
bot-challenge blocks the automated scraper from fetching products.json
directly (see parsers/oceandust.py's store_password/request_delay_range_ms
comments for background - pacing changes weren't enough to reliably get
past it).

This does NOT bypass any protection - it re-uses data YOU fetch yourself by
browsing the store normally in a real browser (which is exactly what
Cloudflare's challenge is designed to allow through). It only automates the
tedious "parse this data and get it into the database" part.

How to use this (repeat whenever you want to refresh OceanDust's listing):

1. Open a real browser and go to https://oceandust.co - enter the password
   shown on the landing page ("NOSTALGIA" as of writing) like a normal
   visitor would.
2. Once unlocked, navigate directly to each of these URLs in that same
   browser tab (increase `page=` until a page returns `{"products": []}`):
       https://oceandust.co/collections/video-games/products.json?limit=250&page=1
       https://oceandust.co/collections/video-games/products.json?limit=250&page=2
       ...
3. For each page that has products, save the raw JSON response to this
   project's root folder as oceandust_manual_page1.json,
   oceandust_manual_page2.json, etc. (Ctrl+A, Ctrl+C the raw JSON text off
   the page, paste into a new file, or use your browser's "Save As" on the
   raw JSON response.)
4. Run this script:
       python import_oceandust_manual.py
5. It reports how many products were added/updated, and marks any
   previously-imported OceanDust product not seen in this batch as inactive
   (so delisted items disappear from the site) - scoped ONLY to OceanDust,
   never touching any other store's rows.
6. Delete the oceandust_manual_page*.json files afterward (they're just
   scratch input, not meant to be committed) and push the updated database
   live as usual.
"""
import glob
import json
import sqlite3

from database import init_db, DB_NAME
from parsers.oceandust import OceanDustParser

init_db()
parser = OceanDustParser()

files = sorted(glob.glob("oceandust_manual_page*.json"))
if not files:
    print("No oceandust_manual_page*.json files found in the project root.")
    print("See the docstring at the top of this script for how to generate them.")
    raise SystemExit(1)

seen_store_urls = []
skipped = 0

for path in files:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    products = data.get("products", [])
    print(f"{path}: {len(products)} raw product(s)")

    for product in products:
        name, price, orig_price, store_url, image_url, metadata = parser.parse_product(product, parser.store_root)
        if not name or not store_url:
            skipped += 1
            continue

        product_type = metadata.get("product_type", "") if isinstance(metadata, dict) else ""
        category = parser.deduce_category(name, store_url, product_type)
        franchise_tag = metadata.get("scraped_tag", "") if isinstance(metadata, dict) else ""
        franchise_tags = [franchise_tag] if franchise_tag else []
        franchise_verified = bool(metadata.get("franchise_verified", True)) if isinstance(metadata, dict) else True
        description_snippet = metadata.get("description_snippet", "") if isinstance(metadata, dict) else ""

        seen_store_urls.append((
            store_url, name, price, orig_price, image_url, parser.brand_name,
            json.dumps(franchise_tags, ensure_ascii=False), category, description_snippet,
            1 if franchise_verified else 0, parser.currency
        ))

conn = sqlite3.connect(DB_NAME)
conn.execute("PRAGMA foreign_keys = ON;")
cur = conn.cursor()

# Scoped "clean sweep": only touches OceanDust rows, never any other store -
# safe, unlike scraper.save_products_to_db()'s global mark-inactive+purge.
cur.execute("UPDATE products SET is_active = 0 WHERE brand_name = ?", (parser.brand_name,))

inserted = 0
updated = 0
for row in seen_store_urls:
    store_url = row[0]
    existing = cur.execute("SELECT 1 FROM products WHERE store_url = ?", (store_url,)).fetchone()
    if existing:
        updated += 1
    else:
        inserted += 1
    cur.execute("""
        INSERT INTO products (
            store_url, product_name, current_price, original_price, image_url, brand_name,
            franchise_tags, is_active, category, description_snippet, franchise_verified, currency, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(store_url) DO UPDATE SET
            product_name=excluded.product_name,
            current_price=excluded.current_price,
            original_price=excluded.original_price,
            image_url=excluded.image_url,
            franchise_tags=excluded.franchise_tags,
            category=excluded.category,
            description_snippet=excluded.description_snippet,
            franchise_verified=excluded.franchise_verified,
            currency=excluded.currency,
            is_active=1,
            updated_at=CURRENT_TIMESTAMP
    """, row)

deactivated = cur.execute(
    "SELECT COUNT(*) FROM products WHERE brand_name = ? AND is_active = 0", (parser.brand_name,)
).fetchone()[0]

conn.commit()
conn.close()

print(f"\nInserted {inserted} new, updated {updated} existing OceanDust product(s).")
print(f"Skipped {skipped} non-apparel/invalid entries.")
print(f"{deactivated} previously-imported OceanDust product(s) no longer seen - marked inactive.")
