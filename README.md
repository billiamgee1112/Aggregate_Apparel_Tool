# Gaming & Geek Apparel Aggregator Scraper

A robust, asynchronous web scraping pipeline built with Python, Playwright, and Pydantic. It extracts structured product data from e-commerce apparel sites while filtering out non-clothing accessories.

## Project Structure

```
AggregateSite/
│
├── .env                  # Local environment variables (API keys, etc.)
├── .gitignore            # Git exclusion rules
├── models.py             # Pydantic data schemas
├── scraper.py            # Playwright + BeautifulSoup dynamic parser
├── requirements.txt      # Python package dependencies
├── products.json         # Extracted output dataset
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

- **Targeted Infinite Scrolling**: Uses direct element-scrolling targets via Playwright to reliably bypass lazy-loading blocks on dynamic grids.
- **Smart Apparel Filtering**: Pre-filters catalog objects using name-based keyword exclusions to drop accessories (pins, magnets, mugs) prior to processing.
- **Strict Data Validation**: Validates all parsed outputs against a strict Pydantic model (`GamingClothingItem`) to ensure data types, formatted floats, and URL structures are clean.
- **Local JSON Export**: Persists clean structured records into output files (`products.json`) on run completion.

## Data Schema (`models.py`)

The pipeline maps the parsed HTML payloads directly to the schema definition:

- `product_name` (str): Title of the apparel.
- `current_price` (float): Live retail price (parsed to float).
- `original_price` (float, optional): Before-discount price (if applicable).
- `store_url` (HttpUrl): Enforced absolute product detail page url.
- `image_url` (HttpUrl): Enforced absolute product thumbnail image url.
- `brand_name` (str): Origin store name ("Insert Coin").
- `franchise_tags` (list[str]): Dynamically generated tags mapped from product routes.