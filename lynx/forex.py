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
