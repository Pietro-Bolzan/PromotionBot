from decimal import Decimal
from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, Field, HttpUrl
from app.models.promotions import PromotionStatus


class PromotionCandidate(BaseModel):
    asin: str = Field(min_length=1, max_length=20)
    title: str = Field(min_length=1, max_length=500)
    original_price: Decimal = Field(ge=0)
    discounted_price: Decimal = Field(ge=0)
    discount_percentage: Decimal = Field(ge=0)
    product_url: HttpUrl
    image_url: HttpUrl | None = None
    category: str = Field(min_length=1, max_length=120)
    rating: Decimal | None = Field(default=None, ge=0, le=5)
    
class PromotionResponse(BaseModel):
    id: UUID
    asin: str
    title: str
    original_price: Decimal
    discounted_price: Decimal
    discount_percentage: Decimal
    product_url: str
    image_url: str | None
    category: str
    rating: Decimal | None
    status: PromotionStatus
    sent_at: datetime | None
    created_at: datetime
    updated_at: datetime
    generated_message: str | None

    model_config = {
        "from_attributes": True
    }
    
class PromotionProcessingResult(BaseModel):
    fetched: int
    saved: int
    duplicates_skipped: int
    
class GeneratedCopyResponse(BaseModel):
    promotion_id: UUID
    message: str
    
class PromotionDeliveryResponse(BaseModel):
    promotion_id: UUID
    status: str
    message: str