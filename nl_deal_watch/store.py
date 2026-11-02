"""SQLite memory of offers we have already reported."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

from nl_deal_watch.parse import ListingItem


@dataclass(frozen=True)
class SavedOffer:
    product_id: int
    active: bool
    last_notified_percent: int | None
    last_notified_price: float | None


class Store:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(path)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS offers (
                product_id INTEGER PRIMARY KEY,
                category TEXT NOT NULL,
                name TEXT NOT NULL,
                url TEXT NOT NULL,
                price REAL,
                shop_count INTEGER,
                drop_percent INTEGER NOT NULL,
                active INTEGER NOT NULL,
                first_seen TEXT NOT NULL,
                last_seen TEXT NOT NULL,
                last_notified_percent INTEGER,
                last_notified_price REAL
            )
            """
        )
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS category_state (
                category TEXT PRIMARY KEY,
                bootstrapped INTEGER NOT NULL
            )
            """
        )
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def is_bootstrapped(self, category: str) -> bool:
        row = self._conn.execute(
            "SELECT bootstrapped FROM category_state WHERE category = ?",
            (category,),
        ).fetchone()
        return bool(row and row["bootstrapped"])

    def mark_bootstrapped(self, category: str) -> None:
        self._conn.execute(
            """
            INSERT INTO category_state (category, bootstrapped)
            VALUES (?, 1)
            ON CONFLICT(category) DO UPDATE SET bootstrapped = 1
            """,
            (category,),
        )
        self._conn.commit()

    def get(self, product_id: int) -> SavedOffer | None:
        row = self._conn.execute(
            """
            SELECT product_id, active, last_notified_percent, last_notified_price
            FROM offers WHERE product_id = ?
            """,
            (product_id,),
        ).fetchone()
        if row is None:
            return None
        return SavedOffer(
            product_id=row["product_id"],
            active=bool(row["active"]),
            last_notified_percent=row["last_notified_percent"],
            last_notified_price=row["last_notified_price"],
        )

    def save_seen(
        self,
        item: ListingItem,
        *,
        category: str,
        seen_at: str,
        notified: bool,
    ) -> None:
        existing = self.get(item.product_id)
        first_seen = seen_at
        notified_percent = item.drop_percent if notified else None
        notified_price = item.price if notified else None
        if existing is not None:
            row = self._conn.execute(
                "SELECT first_seen, last_notified_percent, last_notified_price FROM offers WHERE product_id = ?",
                (item.product_id,),
            ).fetchone()
            first_seen = row["first_seen"]
            if not notified:
                notified_percent = row["last_notified_percent"]
                notified_price = row["last_notified_price"]
        self._conn.execute(
            """
            INSERT INTO offers (
                product_id, category, name, url, price, shop_count, drop_percent,
                active, first_seen, last_seen, last_notified_percent, last_notified_price
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?)
            ON CONFLICT(product_id) DO UPDATE SET
                category = excluded.category,
                name = excluded.name,
                url = excluded.url,
                price = excluded.price,
                shop_count = excluded.shop_count,
                drop_percent = excluded.drop_percent,
                active = 1,
                last_seen = excluded.last_seen,
                last_notified_percent = excluded.last_notified_percent,
                last_notified_price = excluded.last_notified_price
            """,
            (
                item.product_id,
                category,
                item.name,
                item.url,
                item.price,
                item.shop_count,
                item.drop_percent,
                first_seen,
                seen_at,
                notified_percent,
                notified_price,
            ),
        )
        self._conn.commit()

    def deactivate_unseen(self, category: str, seen_ids: set[int]) -> None:
        rows = self._conn.execute(
            "SELECT product_id FROM offers WHERE category = ? AND active = 1",
            (category,),
        ).fetchall()
        stale = [row["product_id"] for row in rows if row["product_id"] not in seen_ids]
        if not stale:
            return
        self._conn.executemany(
            "UPDATE offers SET active = 0 WHERE product_id = ?",
            [(product_id,) for product_id in stale],
        )
        self._conn.commit()
