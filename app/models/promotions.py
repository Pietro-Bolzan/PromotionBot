import enum
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, Enum, Index, Integer, Numeric, String, Text, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class PromotionStatus(str, enum.Enum):
    PENDING = "PENDING"
    SENT = "SENT"
    FAILED = "FAILED"
    

class Promotion(Base):
    __tablename__ = "promotions"
    __table_args__ = (
        # At most one open (PENDING) row per product, enforced by the database
        # itself so that two overlapping collection runs cannot both insert it.
        Index(
            "uq_promotions_pending_asin",
            "asin",
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
    
    asin: Mapped[str] = mapped_column(
      String(20),
      nullable=False,
      index=True
    )
    
    title: Mapped[str] = mapped_column(
      String(500),
      nullable=False
    )
    
    original_price: Mapped[Decimal] = mapped_column(
      Numeric(12, 2),
      nullable=False
    )
    
    discounted_price: Mapped[Decimal] = mapped_column(
      Numeric(12, 2),
      nullable=False
    )
    
    discount_percentage: Mapped[Decimal] = mapped_column(
      Numeric(5, 2),
      nullable=False
    )
    
    product_url: Mapped[str] = mapped_column(
      String(1200),
      nullable=False
    )
    
    image_url: Mapped[str | None] = mapped_column(
      String(1200),
      nullable=True
    )
    
    category: Mapped[str] = mapped_column(
      String(120),
      nullable=False
    )
    
    rating: Mapped[Decimal | None] = mapped_column(
      Numeric(3, 2),
      nullable=True
    )
    
    generated_message: Mapped[str | None] = mapped_column(
      Text,
      nullable=True
    )
    
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
      DateTime(timezone=True),
      nullable=True
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