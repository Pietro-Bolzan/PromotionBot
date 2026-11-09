import enum
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, Enum, Index, Integer, Numeric, String, Text, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class PromotionStatus(enum.StrEnum):
    PENDING = "PENDING"
    SENT = "SENT"
    FAILED = "FAILED"


class Store(enum.StrEnum):
    AMAZON = "amazon"
    SHOPEE = "shopee"
    ALIEXPRESS = "aliexpress"


class Promotion(Base):
    __tablename__ = "promotions"
    __table_args__ = (
        # Deduplication looks a product up by store and its id in that store.
        Index("ix_promotions_store_external_id", "store", "external_id"),
        # At most one open (PENDING) row per product, enforced by the database
        # itself so that two overlapping collection runs cannot both insert it.
        Index(
            "uq_promotions_pending_product",
            "store",
            "external_id",
            unique=True,
            postgresql_where=text("status = 'PENDING'"),
        ),
        # Serves list_pending(): WHERE status = 'PENDING' ORDER BY created_at.
        Index(
            "ix_promotions_pending_created_at",
            "created_at",
            postgresql_where=text("status = 'PENDING'"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    # Stored as text with a CHECK constraint rather than a Postgres enum type,
    # whose values cannot be removed and are awkward to add in a transaction.
    store: Mapped[Store] = mapped_column(
        Enum(
            Store,
            native_enum=False,
            length=20,
            create_constraint=True,
            name="promotion_store",
            values_callable=lambda stores: [store.value for store in stores],
        ),
        nullable=False,
    )

    # The product's id in its store: the ASIN on Amazon, the item id on Shopee,
    # the product id on AliExpress.
    external_id: Mapped[str] = mapped_column(String(64), nullable=False)

    title: Mapped[str] = mapped_column(String(500), nullable=False)

    # Prices are optional: a promotion curated by hand from Amazon has none,
    # because the Associates rules only allow prices read from their API.
    original_price: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 2), nullable=True
    )

    discounted_price: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 2), nullable=True
    )

    discount_percentage: Mapped[Decimal | None] = mapped_column(
        Numeric(5, 2), nullable=True
    )

    product_url: Mapped[str] = mapped_column(String(1200), nullable=False)

    # The tracked link returned by stores whose API builds it (Shopee,
    # AliExpress). Amazon links are tagged at delivery time instead.
    affiliate_url: Mapped[str | None] = mapped_column(String(1200), nullable=True)

    image_url: Mapped[str | None] = mapped_column(String(1200), nullable=True)

    category: Mapped[str | None] = mapped_column(String(120), nullable=True)

    rating: Mapped[Decimal | None] = mapped_column(Numeric(3, 2), nullable=True)

    generated_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    status: Mapped[PromotionStatus] = mapped_column(
        Enum(PromotionStatus),
        nullable=False,
        default=PromotionStatus.PENDING,
    )

    attempts: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )

    last_error: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
