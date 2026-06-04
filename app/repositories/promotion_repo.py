from datetime import datetime, UTC
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models.promotions import Promotion, PromotionStatus


class PromotionRepository:
    from uuid import UUID
    
    def __init__(self, db: Session):
        self.db = db


    def exists_recently_sent(self, asin: str, cutoff: datetime) -> bool:
        statement = select(Promotion.id).where(
            Promotion.asin == asin,
            Promotion.sent_at >= cutoff,
        )

        return self.db.execute(statement).first() is not None


    def exists_recently_pending(self, asin: str, cutoff: datetime) -> bool:
        statement = select(Promotion.id).where(
            Promotion.asin == asin,
            Promotion.status == PromotionStatus.PENDING,
            Promotion.created_at >= cutoff,
        )

        return self.db.execute(statement).first() is not None


    def save(self, promotion: Promotion) -> Promotion:
        self.db.add(promotion)
        self.db.commit()
        self.db.refresh(promotion)
        
        return promotion
    
    
    def list_all(self, limit: int = 20, offset: int = 0) -> list[Promotion]:
        statement = (
            select(Promotion)
            .order_by(Promotion.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(self.db.scalars(statement).all())
    
    
    def get_by_id(self, promotion_id: UUID) -> Promotion | None:
        return self.db.get(Promotion, promotion_id)
    
    
    def update_generated_message(
        self,
        promotion: Promotion,
        generated_message: str,
    ) -> Promotion:
        promotion.generated_message = generated_message
        self.db.commit()
        self.db.refresh(promotion)
        return promotion

    def mark_as_sent(self, promotion: Promotion) -> Promotion:
        promotion.status = PromotionStatus.SENT
        promotion.sent_at = datetime.now(UTC)

        self.db.commit()
        self.db.refresh(promotion)

        return promotion
    
    def mark_as_failed(self, promotion: Promotion) -> Promotion:
        promotion.status = PromotionStatus.FAILED

        self.db.commit()
        self.db.refresh(promotion)

        return promotion
    
    
