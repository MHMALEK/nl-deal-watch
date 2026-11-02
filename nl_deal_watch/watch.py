"""Decide which offers are new and turn them into Telegram messages."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from html import escape

from nl_deal_watch.config import Settings
from nl_deal_watch.parse import ListingItem, product_id_from_url
from nl_deal_watch.store import SavedOffer, Store
from nl_deal_watch.telegram import send_message
from nl_deal_watch.tweakers import FetchError, TweakersClient

log = logging.getLogger(__name__)

_LABELS = {
    "beamers": "Beamers",
    "wasmachines": "Wasmachines",
    "stofzuigers": "Stofzuigers",
    "robotstofzuigers": "Robotstofzuigers",
    "watched": "Watched products",
}


def run_once(settings: Settings, *, dry_run: bool) -> int:
    """Scan every configured category once. Returns a process exit code."""
    if not dry_run and (not settings.telegram_token or not settings.telegram_chat_id):
        log.error(
            "Add TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID to .env first. "
            "See .env.example. You can preview with --dry-run."
        )
        return 1

    client = TweakersClient(settings.request_delay_seconds)
    store = Store(settings.database_path)
    failures = 0
    try:
        for slug in settings.categories:
            try:
                items = client.category_deals(
                    slug,
                    min_drop_ratio=settings.min_drop_ratio,
                    max_pages=settings.max_pages,
                )
            except FetchError as exc:
                failures += 1
                log.error("Skipped %s: %s", slug, exc)
                continue
            qualifying = [item for item in items if item.drop_percent >= settings.min_drop_percent]
            _report_category(settings, store, slug, qualifying, dry_run=dry_run)

        if settings.product_urls:
            watched, checked, watch_failures = _watched_deals(client, settings)
            failures += watch_failures
            if checked:
                _report_category(
                    settings,
                    store,
                    "watched",
                    watched,
                    dry_run=dry_run,
                    seen_scope_ids=checked,
                )
    finally:
        store.close()
    return 1 if failures else 0


def _watched_deals(
    client: TweakersClient,
    settings: Settings,
) -> tuple[list[ListingItem], set[int], int]:
    """Check explicit product URLs. Failed fetches are not treated as ended offers."""
    found: list[ListingItem] = []
    checked: set[int] = set()
    failures = 0
    for product_url in settings.product_urls:
        try:
            product_id = product_id_from_url(product_url)
            item = client.product_deal(product_url, min_drop_percent=settings.min_drop_percent)
        except (FetchError, ValueError) as exc:
            failures += 1
            log.error("Skipped %s: %s", product_url, exc)
            continue
        checked.add(product_id)
        if item is not None:
            found.append(item)
    return found, checked, failures


def decide(
    item: ListingItem,
    saved: SavedOffer | None,
    *,
    bootstrapped: bool,
    deepen_points: int,
) -> str:
    """Classify one offer as baseline, new, deeper, or quiet."""
    if not bootstrapped:
        return "baseline"
    if saved is None or not saved.active or saved.last_notified_percent is None:
        return "new"
    if item.drop_percent >= saved.last_notified_percent + deepen_points:
        return "deeper"
    if (
        item.price is not None
        and saved.last_notified_price
        and item.price <= saved.last_notified_price * (1 - deepen_points / 100)
    ):
        return "deeper"
    return "quiet"


def format_eur(amount: float | None) -> str:
    if amount is None:
        return "unknown"
    if abs(amount - round(amount)) < 0.001:
        return f"€{int(round(amount))}"
    return f"€{amount:.2f}".replace(".", ",")


def category_label(slug: str) -> str:
    return _LABELS.get(slug, slug.replace("-", " ").capitalize())


def _report_category(
    settings: Settings,
    store: Store,
    slug: str,
    items: list[ListingItem],
    *,
    dry_run: bool,
    seen_scope_ids: set[int] | None = None,
    deactivate: bool = True,
) -> None:
    bootstrapped = store.is_bootstrapped(slug)
    ranked = sorted(items, key=lambda item: (-item.drop_percent, item.price or 0))
    decisions = [
        (decide(item, store.get(item.product_id), bootstrapped=bootstrapped, deepen_points=settings.deepen_points), item)
        for item in ranked
    ]
    messages = _messages(settings, slug, decisions, bootstrapped=bootstrapped)
    for message in messages:
        if dry_run:
            print(message, flush=True)
            print("---", flush=True)
        else:
            assert settings.telegram_token and settings.telegram_chat_id
            send_message(settings.telegram_token, settings.telegram_chat_id, message)

    if dry_run:
        log.info("%s: %s offers, dry-run so nothing was stored", slug, len(items))
        return

    seen_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    alerted = {item.product_id for kind, item in decisions if kind != "quiet"}
    for _kind, item in decisions:
        store.save_seen(item, category=slug, seen_at=seen_at, notified=item.product_id in alerted)
    if deactivate:
        seen_ids = seen_scope_ids if seen_scope_ids is not None else {item.product_id for item in items}
        store.deactivate_unseen(slug, seen_ids)
    if not bootstrapped:
        store.mark_bootstrapped(slug)
    log.info("%s: %s offers, %s messages", slug, len(items), len(messages))


def _messages(
    settings: Settings,
    slug: str,
    decisions: list[tuple[str, ListingItem]],
    *,
    bootstrapped: bool,
) -> list[str]:
    label = category_label(slug)
    if not bootstrapped:
        return [_baseline_message(settings, slug, label, [item for _kind, item in decisions])]
    fresh = [item for kind, item in decisions if kind in {"new", "deeper"}]
    if not fresh:
        return []
    return [_fresh_message(label, decisions)]


def _baseline_message(
    settings: Settings,
    slug: str,
    label: str,
    items: list[ListingItem],
) -> str:
    if slug == "watched":
        if not items:
            return "<b>Watched products</b>\nNone of the product URLs are on offer right now."
        lines = ["<b>Watched products already on offer</b>"]
        lines.extend(_offer_lines(items))
        lines.append("Next runs only message a new offer or a clearly bigger drop.")
        return "\n".join(lines)

    threshold = settings.min_drop_percent
    if not items:
        return (
            f"<b>{escape(label)}</b>\n"
            f"Nothing is {threshold}% or more below the price of 30 days ago."
        )
    shown = items[: settings.digest_limit]
    lines = [
        f"<b>{escape(label)}</b>",
        f"{len(items)} products are at least {threshold}% below the price of 30 days ago.",
        "Largest drops right now:",
    ]
    lines.extend(_offer_lines(shown))
    hidden = len(items) - len(shown)
    if hidden:
        lines.append(f"{hidden} more are on offer too.")
    ratio = settings.min_drop_ratio
    lines.append(
        f'<a href="https://tweakers.net/{escape(slug)}/vergelijken/?minrpd={ratio:.2f}">'
        "Open the category on Tweakers</a>"
    )
    lines.append("Next runs only message a new offer or a clearly bigger drop.")
    return "\n".join(lines)


def _fresh_message(label: str, decisions: list[tuple[str, ListingItem]]) -> str:
    new_items = [item for kind, item in decisions if kind == "new"]
    deeper_items = [item for kind, item in decisions if kind == "deeper"]
    lines = [f"<b>{escape(label)}</b>"]
    if new_items:
        lines.append("New offers:")
        lines.extend(_offer_lines(new_items))
    if deeper_items:
        lines.append("Bigger drops:")
        lines.extend(_offer_lines(deeper_items))
    return "\n".join(lines)


def _offer_lines(items: list[ListingItem]) -> list[str]:
    lines: list[str] = []
    for item in items:
        if item.shop_count == 1:
            shops = " · 1 shop"
        elif item.shop_count:
            shops = f" · {item.shop_count} shops"
        else:
            shops = ""
        lines.append(
            f"• {item.drop_percent}% — {escape(item.name)} — {format_eur(item.price)}{shops}"
        )
        lines.append(f'<a href="{escape(item.url)}">Tweakers</a>')
    return lines
