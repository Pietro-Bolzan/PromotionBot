from collections.abc import Collection, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.promotions import Promotion, PromotionStatus, Store

# Fixed, arbitrary key that identifies the delivery lock among the advisory
# locks of this database (shown in pg_locks).
DELIVERY_LOCK_KEY = 4_216_001


class PromotionRepository:
    def __init__(self, db: Session):
        self.db = db

    def has_open_or_recent(
        self, store: Store, external_id: str, cutoff: datetime
    ) -> bool:
        """Whether this product must not be collected again right now.

        True when the product still has an open row (PENDING, of any age), or
        had any row created or sent inside the window. Status alone is never
        enough: a FAILED row inside the window also blocks a new one.
        """
        statement = select(Promotion.id).where(
            Promotion.store == store,
            Promotion.external_id == external_id,
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
        """Insert a new PENDING promotion; False if the product already has one.

        Catches the race the pre-check cannot: two runs checking at the same
        time and both inserting. The partial unique index rejects the second.
        """
        try:
            self.save(promotion)
        except IntegrityError as exc:
            self.db.rollback()
            if _constraint_name(exc) == PENDING_PRODUCT_CONSTRAINT:
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

    def refresh(self, promotion: Promotion) -> None:
        self.db.refresh(promotion)

    @contextmanager
    def delivery_lock(self) -> Iterator[bool]:
        """Try to become the only delivery running; yields whether it did.

        A Postgres advisory lock, so it excludes deliveries in other threads,
        processes and machines alike. It lives in the transaction of a
        dedicated connection: released when the block ends, or by Postgres
        itself if the process dies, so it can never be left behind.
        """
        engine = self.db.get_bind().engine
        with engine.connect() as connection, connection.begin():
            yield bool(
                connection.scalar(
                    select(func.pg_try_advisory_xact_lock(DELIVERY_LOCK_KEY))
                )
            )

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

    def list_pending(
        self, limit: int = 10, exclude_stores: Collection[Store] = ()
    ) -> list[Promotion]:
        statement = (
            select(Promotion)
            .where(Promotion.status == PromotionStatus.PENDING)
            .order_by(Promotion.created_at.asc())
            .limit(limit)
        )
        if exclude_stores:
            statement = statement.where(Promotion.store.not_in(exclude_stores))

        return list(self.db.scalars(statement).all())


PENDING_PRODUCT_CONSTRAINT = "uq_promotions_pending_product"


def _constraint_name(exc: IntegrityError) -> str | None:
    diag = getattr(exc.orig, "diag", None)
    return getattr(diag, "constraint_name", None)
