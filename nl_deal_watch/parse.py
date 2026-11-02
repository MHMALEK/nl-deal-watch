"""Parse Tweakers listing pages and price charts."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date, timedelta
from html import unescape


class PageError(Exception):
    """The response was not a usable Tweakers listing."""


@dataclass(frozen=True)
class ListingItem:
    product_id: int
    name: str
    url: str
    price: float | None
    shop_count: int | None
    drop_percent: int


_LISTING = re.compile(r'<ul\s+class="item-listing">(.*?)</ul>', re.DOTALL)
_LIST_ITEM = re.compile(r"<li\b[^>]*>(.*?)</li>", re.DOTALL)
_PRODUCT_DATA = re.compile(r'data-productdata="([^"]*)"')
_AMOUNT = re.compile(r'class="amount"[^>]*>(.*?)</span>', re.DOTALL)
_EURO = re.compile(r"€\s*([\d.]+(?:,\d+)?-?)")
_SHOPS = re.compile(r"bij\s+(\d+)\s+winkels?")
_DROP = re.compile(r"(\d+)\s*%\s*daling")
_NEXT_TAG = re.compile(r"<a\b[^>]*next-page[^>]*>", re.IGNORECASE)
_HREF = re.compile(r'href="([^"]+)"')
_TITLE = re.compile(r"<title>(.*?)</title>", re.DOTALL)
_PRODUCT_ID = re.compile(r"/pricewatch/(\d+)")


def parse_listing(html: str) -> list[ListingItem]:
    """Return products on a category page that carry a drop badge."""
    listing = _LISTING.search(html)
    if listing is None:
        if "myprivacy.dpgmedia.nl" in html or "privacy-gate" in html:
            raise PageError("Tweakers returned a consent wall instead of a listing")
        raise PageError("Tweakers listing markup was missing")

    items: list[ListingItem] = []
    for block_match in _LIST_ITEM.finditer(listing.group(1)):
        block = block_match.group(1)
        drop_match = _DROP.search(block)
        data_match = _PRODUCT_DATA.search(block)
        if drop_match is None or data_match is None:
            continue
        try:
            payload = json.loads(unescape(data_match.group(1)))
        except json.JSONDecodeError:
            continue
        product_id = payload.get("id")
        name = _decoded(str(payload.get("name") or ""))
        url = _decoded(str(payload.get("url") or ""))
        if not product_id or not name or not url:
            continue
        items.append(
            ListingItem(
                product_id=int(product_id),
                name=name,
                url=url,
                price=_price_from_block(block),
                shop_count=_shops_from_block(block),
                drop_percent=int(drop_match.group(1)),
            )
        )
    return items


def next_page_url(html: str) -> str | None:
    """Return the absolute or relative URL of the next results page."""
    tag = _NEXT_TAG.search(html)
    if tag is None:
        return None
    href = _HREF.search(tag.group(0))
    if href is None:
        return None
    return unescape(href.group(1))


def product_name_from_html(html: str) -> str:
    title_match = _TITLE.search(html)
    if title_match is None:
        raise PageError("Product page had no title")
    title = unescape(re.sub(r"\s+", " ", title_match.group(1))).strip()
    return title.split(":", 1)[0].strip()


def product_id_from_url(url: str) -> int:
    match = _PRODUCT_ID.search(url)
    if match is None:
        raise ValueError(f"No Tweakers product id in URL: {url}")
    return int(match.group(1))


def drop_versus_previous_month(
    points: list[list[object]],
    *,
    today: date | None = None,
) -> tuple[float, int] | None:
    """Compare the latest minimum with the price from about 30 days earlier.

    Tweakers' own badge uses that comparison. Returns the current price and
    the rounded drop percentage when the product is actually cheaper.
    """
    parsed = _chart_points(points)
    if len(parsed) < 2:
        return None
    current_day, current_price = parsed[-1]
    cutoff = (today or current_day) - timedelta(days=30)
    prior = [point for point in parsed if point[0] <= cutoff]
    if not prior:
        return None
    reference_price = prior[-1][1]
    if reference_price <= 0 or current_price >= reference_price:
        return None
    drop_percent = round((reference_price - current_price) / reference_price * 100)
    return current_price, int(drop_percent)


def _decoded(value: str) -> str:
    """Undo HTML escapes that Tweakers sometimes applies more than once."""
    current = value.strip()
    for _ in range(3):
        cleaned = unescape(current)
        if cleaned == current:
            break
        current = cleaned
    return current.strip()


def parse_dutch_price(raw: str) -> float | None:
    """Parse amounts such as ``1.299,-`` and ``244,99``."""
    text = raw.strip().rstrip("-").rstrip(",")
    text = text.replace(".", "").replace(",", ".")
    if not text:
        return None
    try:
        value = float(text)
    except ValueError:
        return None
    if value <= 0:
        return None
    return value


def _price_from_block(block: str) -> float | None:
    amount = _AMOUNT.search(block)
    if amount is None:
        return None
    euro = _EURO.search(unescape(amount.group(1)))
    if euro is None:
        return None
    return parse_dutch_price(euro.group(1))


def _shops_from_block(block: str) -> int | None:
    shops = _SHOPS.search(block)
    if shops is None:
        return None
    return int(shops.group(1))


def _chart_points(points: list[list[object]]) -> list[tuple[date, float]]:
    parsed: list[tuple[date, float]] = []
    for row in points:
        if len(row) < 2:
            continue
        try:
            parsed.append((date.fromisoformat(str(row[0])), float(row[1])))
        except (TypeError, ValueError):
            continue
    parsed.sort(key=lambda point: point[0])
    return parsed
