# parsers/base.py
import re
from abc import ABC, abstractmethod
from urllib.parse import urlparse, urljoin
from bs4 import BeautifulSoup
from parsers.franchise_map import clean_franchise_tag

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
            tuple: (product_name, current_price, original_price, store_url, image_url, metadata)
        """
        pass

    @staticmethod
    def clean_price(price_text: str) -> float:
        """Helper utility to parse decimal floats from string content."""
        price_text = price_text.replace("£", "").replace("$", "").replace(",", "").strip()
        cleaned_digits = ''.join(c for char in price_text.split() for c in char if c.isdigit() or c == '.')
        return float(cleaned_digits) if cleaned_digits else 0.0

    @staticmethod
    def deduce_franchise_from_title(product_name: str) -> str:
        """Deduces the franchise name dynamically by cutting off trailing e-commerce descriptors."""
        # Stop Words that signal the end of the Franchise Name and begining of product detail junk
        truncation_triggers = {
            "shirt", "hoodie", "jacket", "sweater", "sweatshirt", "top", "tee", 
            "t-shirt", "tshirt", "pants", "socks", "outerwear", "apparel", "game", 
            "streetwear", "vintage", "unisex", "oversized", "graphics", "graphic", 
            "casual", "clothing", "gear", "wear", "cap", "caps", "shorts", "tank", 
            "backpack", "bag", "bags", "crewneck", "pullover", "cardigan", "mens", 
            "womens", "kids", "embroided", "embroidery", "patch", "print", "printed", 
            "retro", "messenger", "flight", "collectible", "official", "officially", 
            "licensed", "unisex-adult", "father", "fathers", "dad", "animated"
        }
        
        # Parse tokens
        tokens = product_name.split()
        franchise_tokens = []
        
        for token in tokens:
            # Strip punctuation and lower-case to verify keywords
            clean_token = re.sub(r"[^\w\s-]", "", token).lower()
            if clean_token in truncation_triggers:
                break
            franchise_tokens.append(token)
            
        if franchise_tokens:
            return " ".join(franchise_tokens).strip(",- ")
        return product_name

    @staticmethod
    def extract_franchise_tag(store_url: str, product_name: str = "", scraped_tag: str = "", fallback: str = "Geek Apparel") -> tuple:
        """Deduces a clean franchise name using HTML markers, database mappings, and smart NLP tokenizing.

        Returns (tag: str, verified: bool). "verified" distinguishes trustworthy
        signals (the store's own scraped label, or a match against our curated/
        Wikidata-backed keyword table) from the naive title-tokenizer/URL-slug
        guesses, which are NEVER independently checked against anything and can
        silently produce confident-looking wrong tags (e.g. grabbing a
        character's name instead of the real franchise). franchise_discovery.py
        uses this flag to know which tags still need a Wikidata verification
        pass, in addition to its existing brand_name-fallback/Gamer Culture checks.
        """
        # 1. Prioritize DOM Tags extracted directly from the HTML product card!
        if scraped_tag:
            scraped_tag_clean = scraped_tag.replace("Game Art", "").strip()
            # Double-check it against dynamic custom mappings in the database (e.g. mapping abbreviation: "loz" -> "The Legend of Zelda")
            matched_tag = clean_franchise_tag(scraped_tag_clean, store_url, None)
            if matched_tag:
                return matched_tag, True
            # The store's own explicit label (e.g. a bare <h3> game/franchise
            # name) is first-party structured data, not a guess - trusted.
            return scraped_tag_clean, True

        # 2. Check explicitly against mapping rules table database-side
        matched_tag = clean_franchise_tag(product_name, store_url, None)
        if matched_tag:
            return matched_tag, True
            
        # 3. Apply the Smart Title Tokenizer on the Product Name
        deduced_tag = BaseParser.deduce_franchise_from_title(product_name)
        if deduced_tag and deduced_tag != product_name:
            matched_deduced = clean_franchise_tag(deduced_tag, store_url, None)
            if matched_deduced:
                return matched_deduced, True
            # UNVERIFIED: a naive leading-word guess with no keyword backing.
            return deduced_tag, False

        # 4. ADVANCED SYSTEM FALLBACK: Use URL Slug Parsing
        # This catches items like "Fractured" where URL is "expedition-33-shirt", separating game names automatically!
        parsed_url = urlparse(store_url)
        path_segments = [segment for segment in parsed_url.path.split('/') if segment.strip()]
        
        if path_segments:
            # Extract final trailing directory node (e.g. "expedition-33-shirt")
            last_segment = path_segments[-1].replace(".html", "").replace(".asp", "")
            spaced_segment = last_segment.replace("-", " ").replace("_", " ")
            
            # Feed segment back into stop-word truncation ("expedition 33 shirt" -> "expedition 33")
            deduced_url_tag = BaseParser.deduce_franchise_from_title(spaced_segment)
            
            if deduced_url_tag:
                final_candidate = " ".join(word.capitalize() for word in deduced_url_tag.split())
                
                # Exclude standard/plain path segment variables
                generic_exclusions = {"product", "apparel", "collections", "new", "all", "other", "item"}
                if final_candidate.lower() not in generic_exclusions:
                    # Double-check if the cleaned slug segment matches database mapping dictionary
                    matched_slug = clean_franchise_tag(final_candidate, store_url, None)
                    if matched_slug:
                        return matched_slug, True
                    # UNVERIFIED: a naive URL-slug guess with no keyword backing.
                    return final_candidate, False

        return fallback, True

    @staticmethod
    def deduce_category(product_name: str, store_url: str) -> str:
        """Categorizes clothing items dynamically using simple keyword heuristics."""
        text_to_search = f"{product_name} {store_url}".lower()
        
        # Mapping definitions
        mapping = {
            "jacket": ["jacket", "outerwear", "sukajan", "windbreaker", "coat"],
            "hoodie": ["hoodie", "hood"],
            "sweater": ["sweater", "sweatshirt", "crewneck", "pullover", "cardigan"],
            "pants": ["pants", "sweatpants", "joggers", "loungewear", "leggings", "jeans"],
            "t-shirt": ["t-shirt", "tshirt", "tee", "shirt", "tank top", "tank", "clovertop"]
        }
        
        for category, keywords in mapping.items():
            if any(kw in text_to_search for kw in keywords):
                return category
                
        return "other"