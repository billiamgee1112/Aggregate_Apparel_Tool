# Gaming & Geek Apparel Aggregator Scraper

A robust, asynchronous multi-store web scraping pipeline built with Python, Playwright, and Pydantic. It extracts structured product data from various e-commerce apparel sites into a relational SQLite database while filtering out non-clothing accessories.

## Project Structure

```
AggregateSite/
│
├── parsers/              # Extensible parser plugin package
│   ├── __init__.py       # Registry of active storefront scraper plugins
│   ├── base.py           # Abstract Base Parser interface
│   ├── insert_coin.py    # Insert Coin site custom parser
│   ├── artsholic.py      # Artsholic custom WooCommerce parser
│   └── fangamer.py       # Fangamer custom Shopify parser
│
├── .env                  # Local environment variables
├── .gitignore            # Git exclusion rules
├── database.py           # SQLite database schema and upsert pipeline
├── models.py             # Pydantic data schemas
├── scraper.py            # Playwright browser orchestrator and task runner
├── requirements.txt      # Python package dependencies
└── README.md             # Project documentation
```

## Setup Instructions

### 1. Prerequisites
Ensure you have **Python 3.11** or **3.12** installed on your system.

### 2. Environment Setup
Create a virtual environment and load dependencies:

```powershell
# Create and activate virtual environment (Windows)
python -m venv venv
.\venv\Scripts\activate

# Upgrade pip and install packages
python -m pip install --upgrade pip setuptools wheel
pip install -r requirements.txt

# Install Playwright browser binaries
playwright install
```

### 3. Run the Scraper
Execute the pipeline:
```powershell
python scraper.py
```

## Core Features (MVP)

- **Scalable Plugin Architecture**: Modular, object-oriented parser design. Adding a new store scraper does not require modifying the orchestrator.
- **Dynamic Session Reuse**: Shared single headless Playwright browser session across all scraping engines for optimal performance.
- **Pagination & Infinite Scroll Handlers**: Supports sequential page traversal (WooCommerce/Shopify) and dynamic last-card DOM target scrolling.
- **Deduplicated Relational DB**: Raw products are upserted into an SQLite database (`apparel_aggregator.db`) with an `ON CONFLICT` strategy to update fields without duplicate entries.
- **Smart Apparel Filtering**: Explicitly filters catalog listings using name-based keyword exclusions to drop accessories (pins, magnets, mugs, etc.) prior to database saving.

## Data Schema (`models.py`)

The pipeline maps the parsed HTML payloads directly to the schema definition:

- `product_name` (str): Title of the apparel item.
- `current_price` (float): Live retail price (parsed to float).
- `original_price` (float, optional): Before-discount price (if applicable).
- `store_url` (HttpUrl): Enforced absolute product detail page url.
- `image_url` (HttpUrl): Enforced absolute product thumbnail image url.
- `brand_name` (str): Origin store name (e.g., "Insert Coin", "Artsholic", "Fangamer").
- `franchise_tags` (list[str]): Dynamically generated tags mapped from product routes.

## How to Add a New Store Parser

Adding support for an additional clothing retailer is highly modular:

1. Create a new class file inside the `parsers/` directory (e.g., `parsers/new_store.py`).
2. Subclass `BaseParser` and implement the required abstract properties and methods:

   ```python
   from parsers.base import BaseParser
   from bs4 import BeautifulSoup

   class NewStoreParser(BaseParser):
       brand_name = "New Store"
       url_pattern = "https://www.newstore.com/clothing?page={page_num}"
       item_selector = ".product-card"
       pagination_type = "paginated"  # or "infinite_scroll"
       max_pages = 5

       def parse_product(self, product: BeautifulSoup, base_url: str) -> tuple:
           # Implement selector parsing logic
           # Must return a tuple of: (product_name, current_price, original_price, store_url, image_url)
           return product_name, current_price, original_price, store_url, image_url
   ```

3. Register your new class in `parsers/__init__.py`:

   ```python
   from .new_store import NewStoreParser
   
   ACTIVE_PARSERS = [
       ...
       NewStoreParser()
   ]
   ```

4. Run standard runtime commands. The orchestrator will automatically pick up and execute the new plugin block. These steps ensure zero modifications are made to `scraper.py`.