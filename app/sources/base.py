from typing import Protocol

from app.schemas.promotion_schema import PromotionCandidate


class PromotionSource(Protocol):
    """A store API (or the offline mock) offering products on sale.

    Sources only fetch: the minimum discount, deduplication and persistence are
    applied by PromotionService, the same way for every source.
    """

    # The value used in PROMOTION_SOURCES and in logs.
    name: str

    def fetch_promotions(self) -> list[PromotionCandidate]: ...
