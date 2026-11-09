from typing import get_args

from app.core.config import SourceName
from app.sources.mock import MockSource
from app.sources.registry import SOURCE_FACTORIES, build_sources


def test_every_configurable_source_can_be_built():
    # Settings accepts exactly the names the registry knows how to build.
    assert set(get_args(SourceName)) == set(SOURCE_FACTORIES)


def test_sources_are_built_in_the_configured_order():
    sources = build_sources(["mock"])

    assert [source.name for source in sources] == ["mock"]


def test_mock_offers_products_on_both_sides_of_the_default_minimum():
    discounts = [
        candidate.discount_percentage for candidate in MockSource().fetch_promotions()
    ]

    assert any(discount >= 20 for discount in discounts)
    assert any(discount < 20 for discount in discounts)
