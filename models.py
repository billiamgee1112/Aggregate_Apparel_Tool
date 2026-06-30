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