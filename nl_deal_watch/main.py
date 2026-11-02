"""Command line entry point."""

from __future__ import annotations

import argparse
import logging
import time
from pathlib import Path

from nl_deal_watch.config import load_settings
from nl_deal_watch.telegram import TelegramError, send_message
from nl_deal_watch.watch import run_once


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Send a Telegram message when a Tweakers category goes on offer.",
    )
    parser.add_argument("--config", type=Path, default=Path("config.toml"))
    parser.add_argument("--once", action="store_true", help="Scan once and exit (default).")
    parser.add_argument("--loop", action="store_true", help="Keep scanning on the interval in config.toml.")
    parser.add_argument("--dry-run", action="store_true", help="Print alerts instead of sending or saving them.")
    parser.add_argument("--test-telegram", action="store_true", help="Send one test message and exit.")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    settings = load_settings(args.config)

    if args.test_telegram:
        if not settings.telegram_token or not settings.telegram_chat_id:
            logging.error("Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in .env first.")
            return 1
        try:
            send_message(
                settings.telegram_token,
                settings.telegram_chat_id,
                "nl-deal-watch is connected. Offer alerts will arrive in this chat.",
            )
        except TelegramError as exc:
            logging.error("%s", exc)
            return 1
        logging.info("Test message sent.")
        return 0

    if not args.loop:
        try:
            return run_once(settings, dry_run=args.dry_run)
        except TelegramError as exc:
            logging.error("Telegram send failed, this scan was not saved: %s", exc)
            return 1

    logging.info("Watching every %s minutes. Stop with Ctrl+C.", settings.poll_interval_minutes)
    while True:
        try:
            run_once(settings, dry_run=args.dry_run)
        except TelegramError as exc:
            logging.error("Telegram send failed, this scan was not saved: %s", exc)
        except Exception:
            logging.exception("Scan failed")
        time.sleep(settings.poll_interval_minutes * 60)
