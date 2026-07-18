# tests/test_api.py
"""
Tests for the SSR FastAPI app in api.py (Jinja2-rendered HTML pages, an XML
sitemap, robots.txt, and a JSON health check) - NOT a JSON REST API.

These assume a populated apparel_aggregator.db in the project root (run
scraper.py at least once beforehand). Tests intentionally avoid asserting on
specific product/franchise names, since the catalog changes over time.
"""
import pytest
from fastapi.testclient import TestClient
from api import app

client = TestClient(app)


def test_homepage_renders():
    """Homepage should render the SSR product grid with expected branding."""
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "GamingApparel" in response.text


def test_homepage_pagination_and_sort_params():
    """Homepage should accept pagination/sort query params without erroring."""
    response = client.get("/", params={"page": 1, "sort": "cheapest"})
    assert response.status_code == 200

    response = client.get("/", params={"page": 999, "sort": "newest"})
    assert response.status_code == 200


def test_homepage_discount_sort_succeeds():
    """Regression guard: sort=discount (restricted to genuinely discounted
    items) must not error out."""
    response = client.get("/", params={"sort": "discount"})
    assert response.status_code == 200


def test_franchise_landing_page():
    """Franchise landing pages should 404 for a franchise that doesn't exist
    in the catalog (e.g. a stale indexed URL for a tag that's since been
    merged/renamed - see franchise_mappings), but render normally (200) for
    a real one."""
    response = client.get("/franchises/some-unlikely-franchise-slug-zzz")
    assert response.status_code == 404

    import sqlite3
    import json
    conn = sqlite3.connect("apparel_aggregator.db")
    row = conn.execute("SELECT franchise_tags FROM products WHERE is_active = 1 LIMIT 1").fetchone()
    conn.close()
    real_franchise = json.loads(row[0])[0]
    slug = real_franchise.lower().replace(" ", "-")
    response = client.get(f"/franchises/{slug}")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]


def test_brand_landing_page():
    """Brand landing pages should 404 for a brand that doesn't exist in the
    catalog, but render normally (200) for a real one."""
    response = client.get("/brands/some-unlikely-brand-zzz")
    assert response.status_code == 404

    import sqlite3
    conn = sqlite3.connect("apparel_aggregator.db")
    row = conn.execute("SELECT DISTINCT brand_name FROM products WHERE is_active = 1 LIMIT 1").fetchone()
    conn.close()
    real_brand = row[0]
    response = client.get(f"/brands/{real_brand.lower()}")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]


def test_search_with_no_query_renders_empty_state():
    """Search with no query should render successfully with no results."""
    response = client.get("/search")
    assert response.status_code == 200


def test_search_with_query():
    """Search with a query should render successfully."""
    response = client.get("/search", params={"q": "mass effect"})
    assert response.status_code == 200


def test_sitemap_xml():
    """Sitemap should be valid-looking XML including the homepage URL."""
    response = client.get("/sitemap.xml")
    assert response.status_code == 200
    assert "xml" in response.headers["content-type"]
    assert "<urlset" in response.text
    assert "<loc>" in response.text


def test_robots_txt():
    """robots.txt should point crawlers at the sitemap and allow indexing."""
    response = client.get("/robots.txt")
    assert response.status_code == 200
    assert "User-agent:" in response.text
    assert "Sitemap:" in response.text
    assert "sitemap.xml" in response.text


def test_healthz():
    """Health check should report ok with a reachable database."""
    response = client.get("/healthz")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["database"] == "reachable"
