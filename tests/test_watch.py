"""Parser and alert-decision tests. No network."""

from __future__ import annotations

import unittest
from datetime import date
from pathlib import Path

from nl_deal_watch.parse import (
    ListingItem,
    drop_versus_previous_month,
    next_page_url,
    parse_dutch_price,
    parse_listing,
)
from nl_deal_watch.store import SavedOffer
from nl_deal_watch.watch import decide


FIXTURE = Path(__file__).parent / "fixtures" / "listing.html"


class ParseTests(unittest.TestCase):
    def test_listing_reads_drop_badge_and_dutch_price(self) -> None:
        items = parse_listing(FIXTURE.read_text(encoding="utf-8"))
        self.assertEqual(len(items), 2)
        item = items[0]
        self.assertEqual(item.product_id, 2322304)
        self.assertEqual(item.name, "Whirlpool WPM 97W ADS BE")
        self.assertEqual(item.price, 394)
        self.assertEqual(item.shop_count, 5)
        self.assertEqual(item.drop_percent, 22)
        encoded = items[1]
        self.assertEqual(encoded.name, "Black & Decker")

    def test_next_page_link(self) -> None:
        html = FIXTURE.read_text(encoding="utf-8")
        self.assertEqual(
            next_page_url(html),
            "https://tweakers.net/wasmachines/vergelijken/?page=2",
        )

    def test_dutch_prices(self) -> None:
        self.assertEqual(parse_dutch_price("1.299,-"), 1299)
        self.assertEqual(parse_dutch_price("244,99"), 244.99)

    def test_thirty_day_drop_matches_tweakers_badge(self) -> None:
        points = [
            ["2026-10-03", 505.42, 521.14],
            ["2026-11-02", 394, 489.17],
        ]
        compared = drop_versus_previous_month(points, today=date(2026, 11, 2))
        self.assertIsNotNone(compared)
        assert compared is not None
        price, drop = compared
        self.assertEqual(price, 394)
        self.assertEqual(drop, 22)

    def test_short_history_is_not_a_promotion(self) -> None:
        points = [["2026-10-20", 500, 500], ["2026-11-02", 400, 400]]
        self.assertIsNone(drop_versus_previous_month(points, today=date(2026, 11, 2)))


class DecisionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.item = ListingItem(
            product_id=1,
            name="Washer",
            url="https://tweakers.net/pricewatch/1/washer.html",
            price=400,
            shop_count=4,
            drop_percent=12,
        )

    def test_first_scan_is_a_baseline(self) -> None:
        self.assertEqual(
            decide(self.item, None, bootstrapped=False, deepen_points=5),
            "baseline",
        )

    def test_new_offer_after_baseline(self) -> None:
        self.assertEqual(
            decide(self.item, None, bootstrapped=True, deepen_points=5),
            "new",
        )

    def test_return_after_the_offer_ended(self) -> None:
        saved = SavedOffer(1, active=False, last_notified_percent=12, last_notified_price=400)
        self.assertEqual(
            decide(self.item, saved, bootstrapped=True, deepen_points=5),
            "new",
        )

    def test_same_deal_stays_quiet(self) -> None:
        saved = SavedOffer(1, active=True, last_notified_percent=12, last_notified_price=400)
        self.assertEqual(
            decide(self.item, saved, bootstrapped=True, deepen_points=5),
            "quiet",
        )

    def test_bigger_percent_notifies_again(self) -> None:
        saved = SavedOffer(1, active=True, last_notified_percent=12, last_notified_price=450)
        bigger = ListingItem(
            product_id=1,
            name="Washer",
            url=self.item.url,
            price=430,
            shop_count=4,
            drop_percent=18,
        )
        self.assertEqual(
            decide(bigger, saved, bootstrapped=True, deepen_points=5),
            "deeper",
        )


if __name__ == "__main__":
    unittest.main()
