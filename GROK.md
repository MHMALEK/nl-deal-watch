# Grok Bot routine

Run this repository. Do not rebuild the watcher.

Repository: https://github.com/MHMALEK/nl-deal-watch

Every 3 hours, Europe/Amsterdam:

1. Update a local checkout of this repo.
2. Install it once with `python3 -m venv .venv`, `.venv/bin/pip install -e .`.
3. Put `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` in `.env` in the checkout. They are not in git. If they are missing, ask once, then keep them only in that file.
4. Run `.venv/bin/python -m nl_deal_watch --once`.
5. Categories, the 10% line, and the "only new or bigger" rule already live in `config.toml` and the Python package. Follow those. Do not invent a second set of rules.
6. Keep `data/deals.sqlite` between runs so the same offer is not sent again.
7. If Tweakers answers with HTTP 403, stop and say so. Do not guess prices, and do not switch to another shop.

The Mac does not need to stay on. This routine runs on the Bot's cloud computer.
