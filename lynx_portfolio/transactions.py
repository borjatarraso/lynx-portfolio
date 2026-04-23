"""Tax-lot transaction tracking for Lynx Portfolio (v5.0).

Every ``BUY`` / ``SELL`` the user records becomes one row in the
``transactions`` table. The *current* shares and average-cost values
shown on the summary card are still cached on the ``portfolio`` row
— transactions are the source of truth for *realized* P&L, *per-lot*
basis, and *FIFO / LIFO* tax-lot matching.

Key public functions:

* :func:`record_buy`, :func:`record_sell` — append a trade.
* :func:`list_transactions` — history for a ticker (or all).
* :func:`compute_open_lots_fifo` — return open (unsold) lots after
  matching sells against buys in FIFO order.
* :func:`realized_pnl` — realized gain/loss (FIFO) for a ticker.
* :func:`cost_basis` — weighted-average cost basis across open lots.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Dict, List, Optional, Tuple

from . import database


__all__ = [
    "Transaction",
    "Lot",
    "record_buy",
    "record_sell",
    "delete_transaction",
    "list_transactions",
    "compute_open_lots_fifo",
    "cost_basis",
    "realized_pnl",
    "rebuild_portfolio_summary",
]


@dataclass
class Transaction:
    """One recorded trade."""

    id: int
    ticker: str
    trade_type: str                    # "BUY" or "SELL"
    shares: float
    price: float
    fees: float
    currency: Optional[str]
    trade_date: str                    # YYYY-MM-DD
    note: Optional[str]
    created_at: str


@dataclass
class Lot:
    """An open tax lot after FIFO matching."""

    trade_id: int
    ticker: str
    shares_remaining: float
    unit_cost: float                   # price plus prorated fees
    currency: Optional[str]
    trade_date: str


# ---------------------------------------------------------------------------
# Record a trade
# ---------------------------------------------------------------------------

def _normalize_date(d: Optional[str]) -> str:
    if not d:
        return date.today().isoformat()
    try:
        return datetime.fromisoformat(d).date().isoformat()
    except ValueError:
        return date.today().isoformat()


def record_buy(
    ticker: str,
    *,
    shares: float,
    price: float,
    fees: float = 0.0,
    currency: Optional[str] = None,
    trade_date: Optional[str] = None,
    note: Optional[str] = None,
) -> int:
    """Append a BUY transaction. Returns the new row id."""
    return _insert(
        ticker=ticker.upper(),
        trade_type="BUY",
        shares=shares,
        price=price,
        fees=fees,
        currency=currency,
        trade_date=_normalize_date(trade_date),
        note=note,
    )


def record_sell(
    ticker: str,
    *,
    shares: float,
    price: float,
    fees: float = 0.0,
    currency: Optional[str] = None,
    trade_date: Optional[str] = None,
    note: Optional[str] = None,
) -> int:
    """Append a SELL transaction. Returns the new row id.

    No validation that shares sold are covered by open lots — callers
    should check :func:`cost_basis` first if they want to block
    short sales.
    """
    return _insert(
        ticker=ticker.upper(),
        trade_type="SELL",
        shares=shares,
        price=price,
        fees=fees,
        currency=currency,
        trade_date=_normalize_date(trade_date),
        note=note,
    )


def _insert(**kwargs) -> int:
    conn = database.get_connection()
    try:
        cursor = conn.execute(
            """
            INSERT INTO transactions
                (ticker, trade_type, shares, price, fees, currency, trade_date, note)
            VALUES
                (:ticker, :trade_type, :shares, :price, :fees, :currency, :trade_date, :note)
            """,
            kwargs,
        )
        conn.commit()
        return int(cursor.lastrowid)
    finally:
        conn.close()


def delete_transaction(tx_id: int) -> bool:
    conn = database.get_connection()
    try:
        cur = conn.execute("DELETE FROM transactions WHERE id = ?", (tx_id,))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------

def list_transactions(ticker: Optional[str] = None) -> List[Transaction]:
    conn = database.get_connection()
    try:
        if ticker:
            rows = conn.execute(
                "SELECT * FROM transactions WHERE ticker = ? "
                "ORDER BY trade_date, id",
                (ticker.upper(),),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM transactions ORDER BY trade_date, id",
            ).fetchall()
    finally:
        conn.close()
    return [Transaction(**dict(r)) for r in rows]


# ---------------------------------------------------------------------------
# FIFO matching
# ---------------------------------------------------------------------------

def compute_open_lots_fifo(ticker: str) -> List[Lot]:
    """Return open lots after matching sells against buys in FIFO order.

    Each lot's ``unit_cost`` includes the prorated portion of the BUY
    fees allocated by share count.
    """
    lots: List[Lot] = []
    for tx in list_transactions(ticker):
        if tx.trade_type == "BUY":
            # Per-share cost includes fees spread across the shares bought.
            cost = tx.price + (tx.fees / tx.shares if tx.shares else 0.0)
            lots.append(Lot(
                trade_id=tx.id,
                ticker=tx.ticker,
                shares_remaining=tx.shares,
                unit_cost=cost,
                currency=tx.currency,
                trade_date=tx.trade_date,
            ))
        elif tx.trade_type == "SELL":
            remaining = tx.shares
            while remaining > 1e-9 and lots:
                first = lots[0]
                if first.shares_remaining <= remaining + 1e-9:
                    remaining -= first.shares_remaining
                    lots.pop(0)
                else:
                    first.shares_remaining -= remaining
                    remaining = 0.0
            # Oversold positions: we just zero them out; user is told via
            # realized_pnl or UI if they want stricter tracking.
    return [l for l in lots if l.shares_remaining > 1e-9]


def cost_basis(ticker: str) -> Tuple[float, float]:
    """Return ``(total_shares_open, weighted_avg_cost)``.

    Both values are ``0.0`` when there are no open lots.
    """
    lots = compute_open_lots_fifo(ticker)
    total = sum(l.shares_remaining for l in lots)
    if total <= 0:
        return 0.0, 0.0
    total_cost = sum(l.shares_remaining * l.unit_cost for l in lots)
    return total, total_cost / total


def realized_pnl(ticker: str) -> Dict[str, float]:
    """Return realized cash gains for *ticker* after FIFO matching.

    Keys: ``sold_shares``, ``proceeds``, ``basis``, ``realized``.
    """
    open_lots: List[Lot] = []
    sold_shares = 0.0
    proceeds = 0.0
    basis = 0.0
    for tx in list_transactions(ticker):
        if tx.trade_type == "BUY":
            cost = tx.price + (tx.fees / tx.shares if tx.shares else 0.0)
            open_lots.append(Lot(
                trade_id=tx.id, ticker=tx.ticker,
                shares_remaining=tx.shares, unit_cost=cost,
                currency=tx.currency, trade_date=tx.trade_date,
            ))
        elif tx.trade_type == "SELL":
            remaining = tx.shares
            unit_sale = tx.price - (tx.fees / tx.shares if tx.shares else 0.0)
            while remaining > 1e-9 and open_lots:
                first = open_lots[0]
                take = min(first.shares_remaining, remaining)
                proceeds += take * unit_sale
                basis += take * first.unit_cost
                sold_shares += take
                first.shares_remaining -= take
                remaining -= take
                if first.shares_remaining <= 1e-9:
                    open_lots.pop(0)
    return {
        "sold_shares": round(sold_shares, 6),
        "proceeds": round(proceeds, 2),
        "basis": round(basis, 2),
        "realized": round(proceeds - basis, 2),
    }


# ---------------------------------------------------------------------------
# Rebuild the portfolio summary row from trades
# ---------------------------------------------------------------------------

def rebuild_portfolio_summary(ticker: str) -> None:
    """Recompute shares and avg_purchase_price on ``portfolio`` from trades.

    The ``portfolio`` row is kept as a cached summary so the existing
    display / API code continues to work without needing to reopen the
    transaction book on every read. When no ``portfolio`` row exists
    for the ticker, one is inserted (useful after bulk broker imports
    where the user hasn't manually added the position first).
    """
    ticker_u = ticker.upper()
    shares, avg = cost_basis(ticker_u)
    conn = database.get_connection()
    try:
        existing = conn.execute(
            "SELECT id FROM portfolio WHERE ticker = ?", (ticker_u,),
        ).fetchone()
        if existing is None:
            conn.execute(
                "INSERT INTO portfolio (ticker, shares, avg_purchase_price) "
                "VALUES (?, ?, ?)",
                (ticker_u, shares if shares > 0 else 0.0, avg if shares > 0 else None),
            )
        elif shares <= 0:
            conn.execute(
                "UPDATE portfolio SET shares = 0, avg_purchase_price = NULL, "
                "updated_at = datetime('now') WHERE ticker = ?",
                (ticker_u,),
            )
        else:
            conn.execute(
                "UPDATE portfolio SET shares = ?, avg_purchase_price = ?, "
                "updated_at = datetime('now') WHERE ticker = ?",
                (shares, avg, ticker_u),
            )
        conn.commit()
    finally:
        conn.close()
