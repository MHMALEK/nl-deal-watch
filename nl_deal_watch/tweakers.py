"""Small Tweakers client for category deal pages and price charts."""

from __future__ import annotations

import logging
import re
import time
from typing import Any
from urllib.parse import unquote, urljoin

import requests

from nl_deal_watch.parse import (
    ListingItem,
    PageError,
    drop_versus_previous_month,
    next_page_url,
    parse_listing,
    product_id_from_url,
    product_name_from_html,
)

log = logging.getLogger(__name__)

_BASE = "https://tweakers.net"
_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


class FetchError(Exception):
    """A Tweakers request failed."""


class TweakersClient:
    """Read-only client. One consent handshake, then paced listing requests."""

    def __init__(self, delay_seconds: float) -> None:
        self.delay_seconds = delay_seconds
        self._request_count = 0
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": _USER_AGENT,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "nl,en;q=0.9",
            }
        )
        self._consented = False

    def category_deals(
        self,
        slug: str,
        *,
        min_drop_ratio: float,
        max_pages: int,
    ) -> list[ListingItem]:
        """Collect every paged product at or above the Tweakers drop filter."""
        first_url = f"{_BASE}/{slug}/vergelijken/?minrpd={min_drop_ratio:.2f}"
        collected: list[ListingItem] = []
        seen_ids: set[int] = set()
        url: str | None = first_url
        pages = 0
        while url and pages < max_pages:
            html = self._get_html(url)
            pages += 1
            try:
                items = parse_listing(html)
            except PageError as exc:
                raise FetchError(f"{slug}: {exc}") from exc
            fresh = [item for item in items if item.product_id not in seen_ids]
            if not fresh:
                break
            seen_ids.update(item.product_id for item in fresh)
            collected.extend(fresh)
            log.info("%s page %s: %s offers", slug, pages, len(fresh))
            nxt = next_page_url(html)
            url = urljoin(_BASE, nxt) if nxt else None
        return collected

    def product_deal(self, product_url: str, *, min_drop_percent: int) -> ListingItem | None:
        """Return a watched product when it is cheaper than about 30 days ago."""
        product_id = product_id_from_url(product_url)
        page_url = f"{_BASE}/pricewatch/{product_id}/"
        name = product_name_from_html(self._get_html(page_url))
        chart = self._get_json(f"{_BASE}/ajax/price_chart/{product_id}/nl/")
        source = chart.get("dataset", {}).get("source", [])
        compared = drop_versus_previous_month(source)
        if compared is None:
            return None
        price, drop_percent = compared
        if drop_percent < min_drop_percent:
            return None
        return ListingItem(
            product_id=product_id,
            name=name,
            url=page_url,
            price=price,
            shop_count=None,
            drop_percent=drop_percent,
        )

    def _get_html(self, url: str) -> str:
        response = self._request(url)
        return response.text

    def _get_json(self, url: str) -> dict[str, Any]:
        response = self._request(
            url,
            headers={
                "Accept": "application/json",
                "X-Requested-With": "XMLHttpRequest",
                "Referer": _BASE + "/",
            },
        )
        try:
            payload = response.json()
        except ValueError as exc:
            raise FetchError(f"Tweakers did not return JSON for {url}") from exc
        if not isinstance(payload, dict):
            raise FetchError(f"Unexpected Tweakers payload for {url}")
        return payload

    def _request(self, url: str, headers: dict[str, str] | None = None) -> requests.Response:
        last_error: Exception | None = None
        for attempt in (1, 2):
            try:
                if self._request_count:
                    time.sleep(self.delay_seconds)
                self._request_count += 1
                response = self.session.get(url, timeout=25, allow_redirects=True, headers=headers)
                response.raise_for_status()
                return self._pass_consent(response)
            except (requests.RequestException, FetchError) as exc:
                last_error = exc
                log.warning("request failed (%s/2) %s: %s", attempt, url, exc)
                time.sleep(2)
        raise FetchError(f"Could not fetch {url}") from last_error

    def _pass_consent(self, response: requests.Response) -> requests.Response:
        if "myprivacy.dpgmedia.nl" not in response.url:
            return response
        match = re.search(r"decodeURIComponent\('([^']+)'\)", response.text)
        if match is None:
            raise FetchError("Tweakers consent page had no callback")
        callback = unquote(match.group(1))
        confirmed = self.session.get(callback, timeout=25, allow_redirects=True)
        confirmed.raise_for_status()
        if "myprivacy.dpgmedia.nl" in confirmed.url:
            raise FetchError("Tweakers consent redirect did not complete")
        return confirmed
