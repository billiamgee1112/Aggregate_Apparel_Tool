# tests/test_api.py
import pytest
from fastapi.testclient import TestClient
from api import app

client = TestClient(app)

def test_read_root():
    """Verify that the root endpoint is online and returns db statistics."""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "online"
    assert "total_active_items" in data
    assert "brand_aggregations" in data


def test_get_products_default_limit():
    """Verify products endpoint returns a list of items with the correct default size."""
    response = client.get("/products")
    assert response.status_code == 200
    data = response.json()
    assert "results" in data
    assert "count" in data
    assert data["limit"] == 24


def test_get_products_invalid_price():
    """Verify that using non-numeric price limits raises a validation error (422)."""
    response = client.get("/products?max_price=€30.0")
    assert response.status_code == 422


def test_get_products_filtering():
    """Verify that querying for a specific brand works cleanly."""
    response = client.get("/products?brand=Fangamer&limit=5")
    assert response.status_code == 200
    data = response.json()
    for product in data["results"]:
        assert product["brand_name"].lower() == "fangamer"


def test_get_franchises_list():
    """Verify the franchise aggregator endpoint returns a valid populated array."""
    response = client.get("/franchises")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)