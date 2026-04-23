"""
Forex rate fetching for Lynx Portfolio.
Rates are fetched once per session using Yahoo Finance. Base currency: EUR.

Symbol format: {CCY}EUR=X  →  1 {CCY} expressed in EUR.
Example: USDEUR=X = 0.9234  means  1 USD = 0.9234 EUR.
"""

from typing import Dict, Optional, Set

import yfinance as yf

# ---------------------------------------------------------------------------
# Session-level cache (populated once at startup, reused for the whole run).
# ---------------------------------------------------------------------------

_session_rates: Dict[str, float] = {}


def fetch_session_rates(currencies: Set[str]) -> Dict[str, float]:
    """
    Fetch conversion rates to EUR for every currency in `currencies`.
    EUR always maps to 1.0.  Unknown / failed currencies are omitted.
    Results are stored in the module-level cache and returned.
    """
    global _session_rates

    rates: Dict[str, float] = {"EUR": 1.0}
    needed = sorted({c.upper() for c in currencies if c and c.upper() != "EUR"})

    for ccy in needed:
        symbol = f"{ccy}EUR=X"
        try:
            price = yf.Ticker(symbol).fast_info.last_price
            if price and price > 0:
                rates[ccy] = float(price)
                continue
        except Exception:
            pass
        # Fallback: historical close
        try:
            hist = yf.Ticker(symbol).history(period="5d")
            if not hist.empty:
                rates[ccy] = float(hist["Close"].iloc[-1])
        except Exception:
            pass  # Leave rate absent; caller will show "N/A" for EUR columns

    _session_rates = rates
    return rates


def get_session_rates() -> Dict[str, float]:
    """Return the currently cached session rates (may be empty before fetch)."""
    return _session_rates


def to_eur(amount: Optional[float], currency: Optional[str]) -> Optional[float]:
    """
    Convert `amount` in `currency` to EUR using the cached session rates.
    Returns None if the rate for `currency` is not available.
    """
    if amount is None:
        return None
    ccy = (currency or "EUR").upper()
    if ccy == "EUR":
        return amount
    rate = _session_rates.get(ccy)
    if rate is None:
        return None
    return amount * rate


# ---------------------------------------------------------------------------
# Multi-currency display support (v5.3)
#
# The dashboard / API / web UI show amounts in a **display currency** that
# the user can swap at runtime. Internally we still store and aggregate in
# EUR; on display we convert EUR → target via the inverse rate.
# ---------------------------------------------------------------------------

_DISPLAY_CURRENCY: str = "EUR"


def set_display_currency(currency: str) -> None:
    """Change the default display currency for this process."""
    global _DISPLAY_CURRENCY
    _DISPLAY_CURRENCY = (currency or "EUR").upper() or "EUR"


def get_display_currency() -> str:
    return _DISPLAY_CURRENCY


def from_eur(amount: Optional[float], currency: Optional[str] = None) -> Optional[float]:
    """Convert an EUR amount to *currency* (defaults to the display currency).

    Returns ``None`` when the rate is unknown.
    """
    if amount is None:
        return None
    ccy = (currency or _DISPLAY_CURRENCY or "EUR").upper()
    if ccy == "EUR":
        return amount
    rate = _session_rates.get(ccy)
    if rate is None or rate == 0:
        return None
    return amount / rate


def convert(amount: Optional[float], source_currency: str,
            target_currency: Optional[str] = None) -> Optional[float]:
    """Convert *amount* from *source_currency* to *target_currency*.

    Returns None when either rate is missing.
    """
    if amount is None:
        return None
    src = (source_currency or "EUR").upper()
    dst = (target_currency or _DISPLAY_CURRENCY or "EUR").upper()
    if src == dst:
        return amount
    # Route through EUR (our base).
    as_eur = to_eur(amount, src)
    if as_eur is None:
        return None
    return from_eur(as_eur, dst)


def available_currencies() -> list:
    """Return the set of currencies the forex cache knows about."""
    return sorted({"EUR", *_session_rates.keys()})
