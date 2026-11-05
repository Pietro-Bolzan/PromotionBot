from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.promotions import Promotion, PromotionStatus


class PromotionRepository:
    def __init__(self, db: Session):
        self.db = db

    def has_open_or_recent(self, asin: str, cutoff: datetime) -> bool:
        """Whether this ASIN must not be collected again right now.

        True when the product still has an open row (PENDING, of any age), or
        had any row created or sent inside the window. Status alone is never
        enough: a FAILED row inside the window also blocks a new one.
        """
        statement = select(Promotion.id).where(
            Promotion.asin == asin,
            or_(
                Promotion.status == PromotionStatus.PENDING,
                Promotion.created_at >= cutoff,
                Promotion.sent_at >= cutoff,
            ),
        )

        return self.db.execute(statement).first() is not None

    def save(self, promotion: Promotion) -> Promotion:
        self.db.add(promotion)
        self.db.commit()
        self.db.refresh(promotion)

        return promotion

    def save_unless_duplicate(self, promotion: Promotion) -> bool:
        """Insert a new PENDING promotion; False if the ASIN already has one.

        Catches the race the pre-check cannot: two runs checking at the same
        time and both inserting. The partial unique index rejects the second.
        """
        try:
            self.save(promotion)
        except IntegrityError as exc:
            self.db.rollback()
            if _constraint_name(exc) == PENDING_ASIN_CONSTRAINT:
                return False
            raise

        return True

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
        promotion.attempts += 1

        self.db.commit()
        self.db.refresh(promotion)

        return promotion

    def rollback(self) -> None:
        self.db.rollback()

    def record_failure(
        self,
        promotion: Promotion,
        attempts: int,
        error: str,
        give_up: bool,
    ) -> Promotion:
        """Record a failed delivery attempt.

        The promotion goes back to PENDING to be retried, or to FAILED, which
        is terminal, when give_up is True.
        """
        promotion.attempts = attempts
        promotion.last_error = error
        promotion.status = (
            PromotionStatus.FAILED if give_up else PromotionStatus.PENDING
        )

        self.db.commit()
        self.db.refresh(promotion)

        return promotion

    def list_pending(self, limit: int = 10) -> list[Promotion]:
        statement = (
            select(Promotion)
            .where(Promotion.status == PromotionStatus.PENDING)
            .order_by(Promotion.created_at.asc())
            .limit(limit)
        )

        return list(self.db.scalars(statement).all())


PENDING_ASIN_CONSTRAINT = "uq_promotions_pending_asin"


def _constraint_name(exc: IntegrityError) -> str | None:
    diag = getattr(exc.orig, "diag", None)
    return getattr(diag, "constraint_name", None)
