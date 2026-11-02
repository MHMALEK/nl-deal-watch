# nl-deal-watch

Telegram alerts when a product category on [Tweakers Pricewatch](https://tweakers.net/pricewatch/) goes on offer. Tweakers already compares Coolblue, bol, MediaMarkt, Amazon.nl and the other shops it tracks. A product counts as on offer when its cheapest price is at least 10% below the price of 30 days ago. That is the same "daling" badge on the category page.

The first run sends one digest per category (beamers, washing machines, vacuum cleaners, and robot vacuums) and remembers those offers. Later runs only message you when something new crosses that line, or an offer you already heard about gets at least 5 points bigger.

## Set up Telegram

1. In Telegram, open [@BotFather](https://t.me/BotFather) and send `/newbot`. Copy the token.
2. Open the bot you just created and send it any message, for example `hi`.
3. Visit `https://api.telegram.org/bot<token>/getUpdates` in a browser. Copy the `chat.id` from the result. It is a number.
4. Copy the example env file and fill in both values:

```bash
cp .env.example .env
```

## Run

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
python -m nl_deal_watch --test-telegram
python -m nl_deal_watch --dry-run
python -m nl_deal_watch --once
```

`--dry-run` prints the messages and does not save state, so the next real run is still the baseline digest.

Leave it running:

```bash
python -m nl_deal_watch --loop
```

Or scan once an hour with cron. The path below is an example:

```cron
0 * * * * cd /Users/you/Projects/nl-deal-watch && .venv/bin/python -m nl_deal_watch --once
```

## Free hosting

The code is public at [MHMALEK/nl-deal-watch](https://github.com/MHMALEK/nl-deal-watch). GitHub’s own computers are blocked by Tweakers, so the hourly scan runs on this Mac through a launch agent at `~/Library/LaunchAgents/nl.deal-watch.plist`. It runs while you are logged in and the Mac is awake.

Logs go to `data/watch.log`.

## Change what it watches

Edit `config.toml`.

- `categories` uses Tweakers slugs: `beamers`, `wasmachines`, `stofzuigers`, `robotstofzuigers`.
- `product_urls` is for specific models. Paste the Tweakers product page. Those use the price chart and the same 30-day comparison.
- `min_drop_percent` is the promotion line. `10` means 10% under the price of 30 days ago.

State lives in `data/deals.sqlite`. Delete that file if you want the next run to send a fresh digest.

This is a personal watcher. It waits a second between Tweakers requests. It is not affiliated with Tweakers or the shops.
