from datetime import datetime
from decimal import Decimal
from typing import Self
from uuid import UUID

from pydantic import BaseModel, Field, HttpUrl, field_validator, model_validator

from app.models.promotions import PromotionStatus, Store
from app.services.affiliate import parse_asin


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

    @model_validator(mode="after")
    def _tracked_link_outside_amazon(self) -> Self:
        # Amazon links are tagged at delivery; every other store's API returns
        # the tracked link, and without it the promotion earns nothing.
        if self.store != Store.AMAZON and self.affiliate_url is None:
            raise ValueError(f"a {self.store} promotion needs its affiliate_url")
        return self


class CuratedPromotionRequest(BaseModel):
    """An Amazon product picked by hand, to be posted without a price.

    The Associates rules only allow showing prices read from Amazon's API,
    so there are no price fields: sending one is rejected, not ignored.
    """

    model_config = {"extra": "forbid"}

    product: str = Field(
        min_length=10,
        max_length=1200,
        description="ASIN or amazon.com.br product page URL",
        examples=["B0CNOTE001"],
    )
    title: str = Field(min_length=1, max_length=500)
    category: str | None = Field(default=None, min_length=1, max_length=120)
    message: str | None = Field(
        default=None,
        min_length=1,
        max_length=900,
        description="Copy to post as is; without it, OpenAI writes one",
    )

    @field_validator("product")
    @classmethod
    def _amazon_product(cls, value: str) -> str:
        # Normalized to the ASIN, the product's id in the database.
        return parse_asin(value)


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
    fetched: int = 0
    saved: int = 0
    duplicates_skipped: int = 0
    below_min_discount: int = 0
    # Sources that could not be read this time; the others were still collected.
    failed_sources: list[str] = Field(default_factory=list)


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
    # Stores whose promotions stayed queued because their affiliate settings
    # are missing (AMAZON_PARTNER_TAG).
    skipped_stores: list[Store] = Field(default_factory=list)
