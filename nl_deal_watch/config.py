"""Load config.toml and the Telegram credentials from the environment."""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    min_drop_percent: int
    deepen_points: int
    digest_limit: int
    poll_interval_minutes: int
    request_delay_seconds: float
    max_pages: int
    categories: tuple[str, ...]
    product_urls: tuple[str, ...]
    database_path: Path
    telegram_token: str | None
    telegram_chat_id: str | None

    @property
    def min_drop_ratio(self) -> float:
        return self.min_drop_percent / 100


def load_env_file(path: Path) -> None:
    """Load KEY=VALUE lines into the environment without overriding exports."""
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def load_settings(config_path: Path) -> Settings:
    load_env_file(config_path.parent / ".env")
    if not config_path.exists():
        raise FileNotFoundError(f"Config not found: {config_path}")
    with config_path.open("rb") as handle:
        raw = tomllib.load(handle)

    categories = tuple(str(item) for item in raw.get("categories", []))
    product_urls = tuple(str(item) for item in raw.get("product_urls", []))
    if not categories and not product_urls:
        raise ValueError("config.toml needs at least one category or product URL")

    min_drop = int(raw.get("min_drop_percent", 10))
    if min_drop < 1 or min_drop > 90:
        raise ValueError("min_drop_percent must be between 1 and 90")

    return Settings(
        min_drop_percent=min_drop,
        deepen_points=int(raw.get("deepen_points", 5)),
        digest_limit=int(raw.get("digest_limit", 8)),
        poll_interval_minutes=int(raw.get("poll_interval_minutes", 60)),
        request_delay_seconds=float(raw.get("request_delay_seconds", 1.0)),
        max_pages=int(raw.get("max_pages", 15)),
        categories=categories,
        product_urls=product_urls,
        database_path=config_path.parent / "data" / "deals.sqlite",
        telegram_token=_blank_to_none(os.environ.get("TELEGRAM_BOT_TOKEN")),
        telegram_chat_id=_blank_to_none(os.environ.get("TELEGRAM_CHAT_ID")),
    )


def _blank_to_none(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    if not stripped or stripped.startswith("replace-me") or stripped.startswith("123456:"):
        return None
    return stripped
