from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field, HttpUrl

from app.models.promotions import PromotionStatus, Store


class PromotionCandidate(BaseModel):
    """A product offered by a source, before deduplication."""

    store: Store
    external_id: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=1, max_length=500)
    original_price: Decimal | None = Field(default=None, ge=0)
    discounted_price: Decimal | None = Field(default=None, ge=0)
    discount_percentage: Decimal | None = Field(default=None, ge=0, le=100)
    product_url: HttpUrl
    affiliate_url: HttpUrl | None = None
    image_url: HttpUrl | None = None
    category: str | None = Field(default=None, min_length=1, max_length=120)
    rating: Decimal | None = Field(default=None, ge=0, le=5)


class PromotionResponse(BaseModel):
    id: UUID
    store: Store
    external_id: str
    title: str
    original_price: Decimal | None
    discounted_price: Decimal | None
    discount_percentage: Decimal | None
    product_url: str
    affiliate_url: str | None
    image_url: str | None
    category: str | None
    rating: Decimal | None
    status: PromotionStatus
    attempts: int
    last_error: str | None
    sent_at: datetime | None
    created_at: datetime
    updated_at: datetime
    generated_message: str | None

    model_config = {"from_attributes": True}


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


class PendingDeliveryResponse(BaseModel):
    processed: int
    sent: int
    failed: int
