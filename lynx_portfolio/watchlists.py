"""Watchlist CRUD for Lynx Portfolio (v5.0).

A **watchlist** is a set of tickers the user wants to follow without
owning any shares. Watchlists are grouped by name — the default
``"default"`` list is used when no name is provided. The dashboard and
movers endpoints can read watchlist membership to decide which tickers
to refresh beyond the actual portfolio.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from . import database


__all__ = [
    "WatchItem",
    "add",
    "remove",
    "list_all",
    "list_tickers",
    "list_names",
]


@dataclass
class WatchItem:
    id: int
    name: str
    ticker: str
    note: Optional[str]
    created_at: str


def add(ticker: str, *, name: str = "default", note: Optional[str] = None) -> Optional[int]:
    """Add *ticker* to the named watchlist. Returns new row id, or None
    if the ticker is already on the list."""
    ticker = ticker.upper()
    name = (name or "default").strip() or "default"
    conn = database.get_connection()
    try:
        cursor = conn.execute(
            "INSERT OR IGNORE INTO watchlists (name, ticker, note) "
            "VALUES (?, ?, ?)",
            (name, ticker, note),
        )
        conn.commit()
        return int(cursor.lastrowid) if cursor.rowcount else None
    finally:
        conn.close()


def remove(ticker: str, *, name: str = "default") -> bool:
    """Remove *ticker* from the named watchlist. Returns ``True`` when
    an entry existed."""
    ticker = ticker.upper()
    name = (name or "default").strip() or "default"
    conn = database.get_connection()
    try:
        cur = conn.execute(
            "DELETE FROM watchlists WHERE name = ? AND ticker = ?",
            (name, ticker),
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def list_all(name: Optional[str] = None) -> List[WatchItem]:
    conn = database.get_connection()
    try:
        if name:
            rows = conn.execute(
                "SELECT * FROM watchlists WHERE name = ? ORDER BY ticker",
                (name,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM watchlists ORDER BY name, ticker",
            ).fetchall()
    finally:
        conn.close()
    return [WatchItem(**dict(r)) for r in rows]


def list_tickers(name: str = "default") -> List[str]:
    return [i.ticker for i in list_all(name)]


def list_names() -> List[str]:
    conn = database.get_connection()
    try:
        rows = conn.execute(
            "SELECT DISTINCT name FROM watchlists ORDER BY name",
        ).fetchall()
    finally:
        conn.close()
    return [r["name"] for r in rows]
