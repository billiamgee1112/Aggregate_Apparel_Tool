from pydantic import BaseModel, HttpUrl
from typing import List, Optional

class GamingClothingItem(BaseModel):
    product_name: str
    current_price: float
    original_price: Optional[float] = None
    store_url: HttpUrl
    image_url: HttpUrl
    brand_name: str
    franchise_tags: List[str]
    is_active: Optional[bool] = True
    category: str
    description_snippet: Optional[str] = None
    # Whether franchise_tags came from a trustworthy signal (store's own
    # scraped label, or a match against the curated/Wikidata-backed keyword
    # table) vs. a naive title-tokenizer/URL-slug guess with no independent
    # check. franchise_discovery.py uses this to find tags that still need a
    # Wikidata verification pass. Defaults to True so any code path that
    # doesn't explicitly set it isn't accidentally flooded into review.
    franchise_verified: bool = True