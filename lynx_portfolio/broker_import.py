"""CSV import for popular broker exports (v5.0).

Reads a CSV file from a supported broker, normalizes every row into the
Suite's internal ``{ticker, trade_type, shares, price, fees, currency,
trade_date, note}`` shape, and writes one transaction per trade via
:mod:`.transactions`.

Supported brokers
-----------------

* **Interactive Brokers** (IBKR) — "Flex Query — Trades" export
  (WLPTICK-style headers). We accept the common ones:
  ``Symbol``, ``TradeDate``, ``Quantity``, ``TradePrice``,
  ``IBCommission``, ``CurrencyPrimary``.
* **Trading212** — "pies / history" export:
  ``Action``, ``Time``, ``Ticker``, ``No. of shares``, ``Price / share``,
  ``Currency (Price / share)``, ``Currency conversion fee``.
* **Degiro** — NL/PT export:
  ``Date``, ``Time``, ``Product``, ``ISIN``, ``Quantity``, ``Price``,
  ``Local value``, ``Value``, ``Exchange Rate``.
* **Fidelity** — standard "Activity" export:
  ``Run Date``, ``Action``, ``Symbol``, ``Quantity``, ``Price``,
  ``Commission``, ``Fees``.
* **Generic** — our own 7-column CSV:
  ``ticker,trade_type,shares,price,fees,currency,trade_date[,note]``.

The format is auto-detected from the header row. Use ``detect_broker``
to discover it without importing.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from . import transactions


__all__ = [
    "ImportResult",
    "detect_broker",
    "import_csv",
    "SUPPORTED_BROKERS",
]


SUPPORTED_BROKERS = ("ibkr", "trading212", "degiro", "fidelity", "generic")


@dataclass
class ImportResult:
    broker: str
    rows_read: int = 0
    imported: int = 0
    skipped: int = 0
    errors: List[str] = field(default_factory=list)
    new_tickers: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------

def _headers(path: Path) -> List[str]:
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        for row in reader:
            return [c.strip() for c in row]
    return []


def detect_broker(path: Path) -> str:
    """Return one of :data:`SUPPORTED_BROKERS` (``"generic"`` fallback)."""
    headers = {h.lower() for h in _headers(path)}
    if {"symbol", "tradedate", "tradeprice"} <= headers:
        return "ibkr"
    if {"action", "time", "ticker", "no. of shares", "price / share"} <= headers:
        return "trading212"
    if {"date", "product", "isin", "quantity", "price"} <= headers:
        return "degiro"
    if {"run date", "action", "symbol", "quantity"} <= headers:
        return "fidelity"
    if {"ticker", "trade_type", "shares", "price", "trade_date"} <= headers:
        return "generic"
    return "generic"


# ---------------------------------------------------------------------------
# Import
# ---------------------------------------------------------------------------

def import_csv(
    path: Path | str,
    *,
    broker: Optional[str] = None,
    dry_run: bool = False,
) -> ImportResult:
    """Import every trade from *path* into the transactions table.

    When *broker* is omitted the format is auto-detected. Set
    *dry_run=True* to parse and validate without writing. Returns an
    :class:`ImportResult` with counts and any per-row errors.
    """
    path = Path(path)
    if not path.exists():
        return ImportResult(
            broker=broker or "unknown",
            errors=[f"file not found: {path}"],
        )

    detected = broker or detect_broker(path)
    result = ImportResult(broker=detected)
    parser = _PARSERS.get(detected, _parse_generic)

    tickers_seen: set[str] = set()
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for lineno, raw in enumerate(reader, start=2):
            result.rows_read += 1
            try:
                entry = parser(raw)
            except Exception as exc:
                result.errors.append(f"line {lineno}: {exc}")
                result.skipped += 1
                continue
            if entry is None:
                result.skipped += 1
                continue

            if not dry_run:
                fn = (
                    transactions.record_buy
                    if entry["trade_type"] == "BUY"
                    else transactions.record_sell
                )
                try:
                    fn(
                        entry["ticker"],
                        shares=entry["shares"],
                        price=entry["price"],
                        fees=entry.get("fees", 0.0),
                        currency=entry.get("currency"),
                        trade_date=entry.get("trade_date"),
                        note=entry.get("note"),
                    )
                except Exception as exc:
                    result.errors.append(f"line {lineno}: db error {exc}")
                    result.skipped += 1
                    continue
            tickers_seen.add(entry["ticker"])
            result.imported += 1

    if not dry_run:
        for ticker in tickers_seen:
            try:
                transactions.rebuild_portfolio_summary(ticker)
            except Exception as exc:
                result.errors.append(f"rebuild {ticker}: {exc}")
    result.new_tickers = sorted(tickers_seen)
    return result


# ---------------------------------------------------------------------------
# Per-broker parsers
# ---------------------------------------------------------------------------

def _norm_ticker(raw: str) -> str:
    return (raw or "").strip().upper()


def _to_float(value: object, default: float = 0.0) -> float:
    if value is None or value == "":
        return default
    try:
        # Handle "1,234.56" / "1.234,56" variants
        s = str(value).replace(",", "") if str(value).count(",") == 1 and "." in str(value) else str(value).replace(",", ".")
        # Strip currency tails/prefixes like "EUR 12.34" or "12.34 €"
        s = "".join(ch for ch in s if ch.isdigit() or ch in ".-")
        return float(s) if s not in ("", "-", ".") else default
    except ValueError:
        return default


def _iso_date(value: object) -> str:
    if not value:
        return datetime.today().date().isoformat()
    s = str(value).strip()
    for fmt in ("%Y-%m-%d", "%Y%m%d", "%Y/%m/%d", "%d/%m/%Y",
                "%m/%d/%Y", "%d-%m-%Y", "%Y-%m-%dT%H:%M:%S",
                "%Y-%m-%dT%H:%M:%S.%f"):
        try:
            return datetime.strptime(s[:len(fmt) if "%" not in fmt else 32], fmt).date().isoformat()
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(s).date().isoformat()
    except ValueError:
        return datetime.today().date().isoformat()


def _parse_generic(row: Dict[str, str]) -> Optional[Dict]:
    ticker = _norm_ticker(row.get("ticker", ""))
    trade_type = (row.get("trade_type", "") or "").strip().upper()
    if trade_type not in ("BUY", "SELL"):
        return None
    return {
        "ticker": ticker,
        "trade_type": trade_type,
        "shares": abs(_to_float(row.get("shares"))),
        "price": _to_float(row.get("price")),
        "fees": _to_float(row.get("fees")),
        "currency": (row.get("currency") or "").upper() or None,
        "trade_date": _iso_date(row.get("trade_date")),
        "note": (row.get("note") or None),
    }


def _parse_ibkr(row: Dict[str, str]) -> Optional[Dict]:
    qty = _to_float(row.get("Quantity"))
    if qty == 0:
        return None
    return {
        "ticker": _norm_ticker(row.get("Symbol", "")),
        "trade_type": "BUY" if qty > 0 else "SELL",
        "shares": abs(qty),
        "price": _to_float(row.get("TradePrice")),
        "fees": abs(_to_float(row.get("IBCommission"))),
        "currency": (row.get("CurrencyPrimary") or "").upper() or None,
        "trade_date": _iso_date(row.get("TradeDate")),
        "note": "IBKR",
    }


def _parse_trading212(row: Dict[str, str]) -> Optional[Dict]:
    action = (row.get("Action") or "").strip().lower()
    if action.startswith("market buy") or action.startswith("limit buy"):
        trade_type = "BUY"
    elif action.startswith("market sell") or action.startswith("limit sell"):
        trade_type = "SELL"
    else:
        return None
    return {
        "ticker": _norm_ticker(row.get("Ticker", "")),
        "trade_type": trade_type,
        "shares": abs(_to_float(row.get("No. of shares"))),
        "price": _to_float(row.get("Price / share")),
        "fees": _to_float(row.get("Currency conversion fee")),
        "currency": (row.get("Currency (Price / share)") or "").upper() or None,
        "trade_date": _iso_date(row.get("Time")),
        "note": "Trading212",
    }


def _parse_degiro(row: Dict[str, str]) -> Optional[Dict]:
    qty = _to_float(row.get("Quantity"))
    if qty == 0:
        return None
    price = _to_float(row.get("Price"))
    # Degiro sometimes lists "Local value" which is signed
    return {
        "ticker": _norm_ticker(row.get("Product", ""))[:20],
        "trade_type": "BUY" if qty > 0 else "SELL",
        "shares": abs(qty),
        "price": price,
        "fees": 0.0,
        "currency": None,
        "trade_date": _iso_date(row.get("Date")),
        "note": f"Degiro {row.get('ISIN') or ''}".strip(),
    }


def _parse_fidelity(row: Dict[str, str]) -> Optional[Dict]:
    action = (row.get("Action") or "").lower()
    if "bought" in action or "buy" in action:
        trade_type = "BUY"
    elif "sold" in action or "sell" in action:
        trade_type = "SELL"
    else:
        return None
    fees = abs(_to_float(row.get("Commission"))) + abs(_to_float(row.get("Fees")))
    return {
        "ticker": _norm_ticker(row.get("Symbol", "")),
        "trade_type": trade_type,
        "shares": abs(_to_float(row.get("Quantity"))),
        "price": _to_float(row.get("Price")),
        "fees": fees,
        "currency": "USD",
        "trade_date": _iso_date(row.get("Run Date")),
        "note": "Fidelity",
    }


_PARSERS = {
    "ibkr": _parse_ibkr,
    "trading212": _parse_trading212,
    "degiro": _parse_degiro,
    "fidelity": _parse_fidelity,
    "generic": _parse_generic,
}
