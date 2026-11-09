"""Affiliate link handling.

The affiliate link is the only part of a promotion that earns money, so it never
goes through the LLM: the copy is generated without links, and the tagged link
is appended deterministically right before the message is sent.
"""

import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

AMAZON_DOMAIN = "amazon.com.br"
LINK_SEPARATOR = "\n\n"
ELLIPSIS = "\u2026"

_ASIN_PATTERN = re.compile(r"[A-Z0-9]{10}")
_URL_PATTERN = re.compile(r"https?://\S+", re.IGNORECASE)
# Where the ASIN sits in the product URLs Amazon itself links to.
_ASIN_IN_PATH = re.compile(
    r"/(?:dp|gp/product|gp/aw/d)/([A-Z0-9]{10})(?:/|$)", re.IGNORECASE
)


def parse_asin(asin_or_url: str) -> str:
    """Return the ASIN of an amazon.com.br product, given it or its URL.

    Short links (amzn.to) are refused rather than followed: resolving them
    would mean the bot requesting Amazon pages, which the Associates rules
    forbid to automated tools.
    """
    value = asin_or_url.strip()
    if "://" not in value:
        asin = value.upper()
        if not _ASIN_PATTERN.fullmatch(asin):
            raise ValueError(f"invalid ASIN: {asin_or_url!r}")
        return asin

    parts = urlsplit(value)
    _require_amazon_host(parts.hostname, asin_or_url)

    match = _ASIN_IN_PATH.search(parts.path)
    if not match:
        raise ValueError(
            f"no ASIN in {asin_or_url!r}; use the product page URL "
            "(…/dp/ASIN) or the ASIN itself"
        )
    return match.group(1).upper()


def _require_amazon_host(hostname: str | None, original: str) -> None:
    host = (hostname or "").lower()
    if host != AMAZON_DOMAIN and not host.endswith(f".{AMAZON_DOMAIN}"):
        raise ValueError(f"not an {AMAZON_DOMAIN} URL: {original!r}")


def build_affiliate_url(asin_or_url: str, partner_tag: str) -> str:
    """Return the product URL carrying the Amazon Associates partner tag.

    Accepts an ASIN or a product URL. Other query parameters (such as the
    linkCode the Product Advertising API returns) are preserved, and an existing
    tag is replaced so the configured one always wins.
    """
    tag = partner_tag.strip()
    if not tag:
        raise ValueError("partner tag must not be empty")

    value = asin_or_url.strip()
    if "://" not in value:
        asin = value.upper()
        if not _ASIN_PATTERN.fullmatch(asin):
            raise ValueError(f"invalid ASIN: {asin_or_url!r}")
        value = f"https://www.{AMAZON_DOMAIN}/dp/{asin}"

    parts = urlsplit(value)
    _require_amazon_host(parts.hostname, asin_or_url)

    query = [
        (key, val)
        for key, val in parse_qsl(parts.query, keep_blank_values=True)
        if key != "tag"
    ]
    query.append(("tag", tag))

    return urlunsplit(
        (parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment)
    )


def compose_with_link(text: str, link: str, max_length: int, details: str = "") -> str:
    """Build the final message: the copy, the details, then the affiliate link.

    Guarantees that the affiliate link is the only URL in the message, that it
    sits at the end, and that neither it nor the details (the price and when it
    was checked) are ever cut: when the message would exceed max_length, the
    copy is shortened instead.

    Lengths are measured in UTF-16 code units, the unit Telegram uses for text.
    It is never smaller than the character count, so emoji-heavy copy cannot
    overflow the limit whichever way the API counts.
    """
    tail = f"{details}{LINK_SEPARATOR}{link}" if details else link
    budget = max_length - _utf16_len(LINK_SEPARATOR) - _utf16_len(tail)
    if budget <= 0:
        raise ValueError("details and link do not fit within max_length")

    copy = _URL_PATTERN.sub("", text)
    copy = "\n".join(line.rstrip() for line in copy.strip().splitlines())

    if _utf16_len(copy) > budget:
        copy = _truncate_utf16(copy, budget - _utf16_len(ELLIPSIS)).rstrip() + ELLIPSIS

    if not copy:
        return tail

    return f"{copy}{LINK_SEPARATOR}{tail}"


def _utf16_len(text: str) -> int:
    return len(text.encode("utf-16-le")) // 2


def _truncate_utf16(text: str, limit: int) -> str:
    units = 0
    for index, char in enumerate(text):
        units += 2 if ord(char) > 0xFFFF else 1
        if units > limit:
            return text[:index]
    return text
