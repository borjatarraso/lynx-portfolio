"""
Data fetchers for Lynx Portfolio.

- Yahoo Finance via yfinance for instrument details + live prices.
- OpenFIGI (free, no key required) for ISIN → ticker resolution.
"""

import re
from typing import Optional, Dict, Tuple

import requests
import yfinance as yf

OPENFIGI_URL = "https://api.openfigi.com/v3/mapping"
_REQUEST_TIMEOUT = 12  # seconds


# ---------- ISIN resolution ----------

def isin_to_ticker(isin: str) -> Optional[str]:
    """
    Resolve an ISIN to a ticker symbol using the OpenFIGI API.
    Prefers US equities; falls back to the first match.
    """
    try:
        resp = requests.post(
            OPENFIGI_URL,
            json=[{"idType": "ID_ISIN", "idValue": isin.upper()}],
            headers={"Content-Type": "application/json"},
            timeout=_REQUEST_TIMEOUT,
        )
        if resp.status_code != 200:
            return None
        data = resp.json()
        if not data or not data[0].get("data"):
            return None
        items = data[0]["data"]
        # Prefer US/NASDAQ/NYSE equities
        for item in items:
            if item.get("exchCode") in ("US", "UW", "UN", "UA") and item.get("ticker"):
                return item["ticker"]
        # Fall back to first item with a ticker
        for item in items:
            if item.get("ticker"):
                return item["ticker"]
    except Exception:
        pass
    return None


# ---------- Yahoo Finance ----------

def _first_sentence(text: str) -> str:
    """Extract only the first sentence of a text block."""
    if not text:
        return ""
    # Split on period followed by whitespace (sentence boundary)
    parts = re.split(r"\.\s+", text, maxsplit=1)
    sentence = parts[0].strip()
    if not sentence:
        return ""
    return sentence if sentence.endswith(".") else sentence + "."


def fetch_instrument_data(ticker: str, isin: Optional[str] = None) -> Optional[Dict]:
    """
    Fetch instrument data from Yahoo Finance.

    Returns a dict with keys:
        name, current_price, currency, sector, industry, description, isin
    Returns None on failure.
    """
    try:
        stock = yf.Ticker(ticker)
        info = stock.info or {}

        # yfinance returns a near-empty dict for unknown tickers
        if not info.get("longName") and not info.get("shortName") and not info.get("regularMarketPrice"):
            return None

        # --- price ---
        current_price = (
            info.get("currentPrice")
            or info.get("regularMarketPrice")
            or info.get("navPrice")       # mutual fund NAV
            or info.get("previousClose")
        )

        # --- name ---
        name = info.get("longName") or info.get("shortName") or ticker

        # --- sector / industry (ETFs use category / fundFamily) ---
        quote_type = info.get("quoteType", "")
        if quote_type in ("ETF", "MUTUALFUND"):
            sector = info.get("fundFamily") or info.get("category")
            industry = info.get("category")
        else:
            sector = info.get("sector")
            industry = info.get("industry")

        # --- description (first sentence only) ---
        raw_desc = info.get("longBusinessSummary") or ""
        description = _first_sentence(raw_desc) or None

        return {
            "name": name,
            "current_price": current_price,
            "currency": info.get("currency"),
            "sector": sector,
            "industry": industry,
            "description": description,
            "isin": isin,
        }
    except Exception:
        return None


# ---------- combined helper ----------

def resolve_and_fetch(
    ticker: Optional[str], isin: Optional[str]
) -> Tuple[Optional[str], Optional[str], Optional[Dict]]:
    """
    Resolve ticker/ISIN and fetch instrument data.

    Returns (ticker, isin, data_dict).
    data_dict may be None if the API call failed.
    """
    isin = isin.upper() if isin else None
    ticker = ticker.upper() if ticker else None

    if not ticker and isin:
        ticker = isin_to_ticker(isin)

    if not ticker:
        return None, isin, None

    data = fetch_instrument_data(ticker, isin)
    return ticker, isin, data
