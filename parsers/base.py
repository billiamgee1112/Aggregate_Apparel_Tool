# parsers/base.py
from abc import ABC, abstractmethod
from urllib.parse import urlparse
from bs4 import BeautifulSoup

class BaseParser(ABC):
    
    @property
    @abstractmethod
    def brand_name(self) -> str:
        pass

    @property
    @abstractmethod
    def url_pattern(self) -> str:
        pass

    @property
    @abstractmethod
    def item_selector(self) -> str:
        pass

    @property
    @abstractmethod
    def pagination_type(self) -> str:  # "infinite_scroll" or "paginated"
        pass

    @property
    def max_pages(self) -> int:
        return 1  # Default fallback for infinite_scroll with single landing URL

    @property
    def first_page_override(self) -> str:
        return None

    @abstractmethod
    def parse_product(self, product_el: BeautifulSoup, base_url: str) -> tuple:
        """Parses a raw product element.
        
        Returns:
            tuple: (product_name, current_price, original_price, store_url, image_url)
        """
        pass

    @staticmethod
    def clean_price(price_text: str) -> float:
        """Helper utility to parse decimal floats from string content."""
        price_text = price_text.replace("£", "").replace("$", "").replace(",", "").strip()
        cleaned_digits = ''.join(c for char in price_text.split() for c in char if c.isdigit() or c == '.')
        return float(cleaned_digits) if cleaned_digits else 0.0

    @staticmethod
    def extract_franchise_tag(store_url: str, fallback: str = "Geek Apparel") -> str:
        """Deduces a clean franchise name using URL segments."""
        parsed_path = urlparse(store_url).path
        path_segments = [seg for segment in parsed_path.split('/') if (seg := segment.replace('.html', '').strip())]
        if path_segments:
            if path_segments[0].lower() in ["products", "collections", "product", "collection"] and len(path_segments) > 1:
                return " ".join(segment.capitalize() for segment in path_segments[1].split('-'))
            return " ".join(segment.capitalize() for segment in path_segments[0].split('-'))
        return fallback