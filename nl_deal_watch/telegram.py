"""Send alert text to a Telegram chat."""

from __future__ import annotations

import requests


class TelegramError(Exception):
    """Telegram rejected a message or the request failed."""


def send_message(token: str, chat_id: str, text: str) -> None:
    for part in _chunks(text):
        response = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": part,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            },
            timeout=20,
        )
        try:
            payload = response.json()
        except ValueError as exc:
            raise TelegramError(f"Telegram returned a non-JSON response ({response.status_code})") from exc
        if response.status_code != 200 or not payload.get("ok"):
            description = payload.get("description", response.text[:200])
            raise TelegramError(f"Telegram error: {description}")


def _chunks(text: str, limit: int = 3500) -> list[str]:
    if len(text) <= limit:
        return [text]
    parts: list[str] = []
    current: list[str] = []
    size = 0
    for line in text.splitlines(keepends=True):
        if size + len(line) > limit and current:
            parts.append("".join(current).strip())
            current = []
            size = 0
        current.append(line)
        size += len(line)
    if current:
        parts.append("".join(current).strip())
    return [part for part in parts if part]
