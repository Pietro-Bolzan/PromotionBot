from collections.abc import Callable, Iterable

from app.sources.base import PromotionSource
from app.sources.mock import MockSource
from app.sources.shopee import ShopeeSource

# How to build each source accepted in PROMOTION_SOURCES. Settings validates
# the names (SourceName), so the configuration fails at startup, not here.
SOURCE_FACTORIES: dict[str, Callable[[], PromotionSource]] = {
    "mock": MockSource,
    "shopee": ShopeeSource,
}


def build_sources(names: Iterable[str]) -> tuple[PromotionSource, ...]:
    """Build the configured sources, in the configured order."""
    return tuple(SOURCE_FACTORIES[name]() for name in names)
