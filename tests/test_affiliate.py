import pytest

from app.services.affiliate import build_affiliate_url, compose_with_link

TAG = "meutag-20"
LINK = "https://www.amazon.com.br/dp/B0CNOTE001?tag=meutag-20"


def utf16_len(text: str) -> int:
    return len(text.encode("utf-16-le")) // 2


# --- build_affiliate_url ---


def test_builds_url_from_asin():
    assert build_affiliate_url("B0CNOTE001", TAG) == LINK


def test_adds_tag_to_product_url():
    assert build_affiliate_url("https://www.amazon.com.br/dp/B0CNOTE001", TAG) == LINK


def test_replaces_existing_tag():
    url = "https://www.amazon.com.br/dp/B0CNOTE001?tag=someone-else-20"
    assert build_affiliate_url(url, TAG) == LINK


def test_preserves_other_query_parameters():
    # Product Advertising API links carry parameters Amazon uses for attribution.
    url = "https://www.amazon.com.br/dp/B0CNOTE001?linkCode=ogi&th=1&tag=other-20"
    assert build_affiliate_url(url, TAG) == (
        "https://www.amazon.com.br/dp/B0CNOTE001?linkCode=ogi&th=1&tag=meutag-20"
    )


@pytest.mark.parametrize("tag", ["", "   "])
def test_rejects_empty_tag(tag):
    with pytest.raises(ValueError):
        build_affiliate_url("B0CNOTE001", tag)


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com/dp/B0CNOTE001",
        "https://www.amazon.com.br.example.com/dp/B0CNOTE001",
        "https://notamazon.com.br/dp/B0CNOTE001",
    ],
)
def test_rejects_non_amazon_urls(url):
    with pytest.raises(ValueError):
        build_affiliate_url(url, TAG)


@pytest.mark.parametrize("asin", ["B0CNOTE00", "B0LOWDISC04", "B0CNOTE00!"])
def test_rejects_invalid_asin(asin):
    with pytest.raises(ValueError):
        build_affiliate_url(asin, TAG)


# --- compose_with_link ---


def test_appends_link_after_copy():
    assert compose_with_link("Oferta imperdível", LINK, 1024) == (
        f"Oferta imperdível\n\n{LINK}"
    )


def test_long_copy_is_shortened_and_link_survives():
    # Regression: sendPhoto cut the caption at 1024 characters, and since the
    # copy ended with the link, the link was exactly what got cut.
    message = compose_with_link("a" * 1500, LINK, 1024)

    assert message.endswith(f"…\n\n{LINK}")
    assert utf16_len(message) <= 1024


def test_emoji_count_as_two_units_against_the_limit():
    message = compose_with_link("\U0001f525" * 1000, LINK, 1024)

    assert message.endswith(LINK)
    assert utf16_len(message) <= 1024


def test_removes_urls_written_into_the_copy():
    copy = "Oferta!\nConfira: https://www.amazon.com.br/dp/B0CNOTE001"

    message = compose_with_link(copy, LINK, 1024)

    assert message.count("https://") == 1
    assert message.endswith(LINK)


def test_returns_only_the_link_when_copy_is_empty():
    assert compose_with_link("", LINK, 1024) == LINK


def test_rejects_link_that_does_not_fit():
    with pytest.raises(ValueError):
        compose_with_link("Oferta", LINK, 10)


def test_details_sit_before_the_link_and_are_never_cut():
    # The price and when it was checked must reach the group exactly as built.
    details = "R$ 49,90 (35% de desconto)\nPreço verificado em 09/11/2026 às 14:11"

    message = compose_with_link("a" * 1500, LINK, 1024, details=details)

    assert message.endswith(f"…\n\n{details}\n\n{LINK}")
    assert utf16_len(message) <= 1024
