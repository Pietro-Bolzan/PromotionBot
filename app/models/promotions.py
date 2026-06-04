import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class PromotionStatus(str, enum.Enum):
    PENDING = "PENDING"
    SENT = "SENT"
    FAILED = "FAILED"
    

class Promotion(Base):
    __tablename__ = "promotions"
    
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
    
    original_price: Mapped[float] = mapped_column(
      Numeric(12, 2),
      nullable=False
    )
    
    discounted_price: Mapped[float] = mapped_column(
      Numeric(12, 2),
      nullable=False
    )
    
    discount_percentage: Mapped[float] = mapped_column(
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
    
    rating: Mapped[float | None] = mapped_column(
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