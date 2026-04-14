"""
Input validation helpers for Lynx Portfolio.

Centralised validation for tickers, ISINs, shares, prices, and other
user-supplied values. Used across CLI, interactive, TUI, and GUI modes
to ensure consistent error handling.
"""

import re
from typing import Optional, Tuple

# Maximum lengths for string inputs
MAX_TICKER_LEN = 20
MAX_ISIN_LEN = 12
MAX_EXCHANGE_LEN = 10
MAX_SEARCH_QUERY_LEN = 100
MAX_PATH_LEN = 500

# Ticker: alphanumeric, dots, hyphens, carets (e.g. BRK-B, VWCE.DE, ^GSPC)
_TICKER_RE = re.compile(r'^[A-Za-z0-9\.\-\^]{1,20}$')

# ISIN: 2 uppercase letters + 10 alphanumeric chars
_ISIN_RE = re.compile(r'^[A-Z]{2}[A-Z0-9]{10}$')

# Exchange suffix: 1-6 uppercase alphanumeric
_EXCHANGE_RE = re.compile(r'^[A-Za-z0-9]{1,6}$')


def validate_ticker(ticker: str) -> Tuple[Optional[str], Optional[str]]:
    """Validate and normalise a ticker symbol.

    Returns (normalised_ticker, error_message).
    If valid, error_message is None.
    """
    if not ticker or not ticker.strip():
        return None, "Ticker cannot be empty."
    ticker = ticker.strip()
    if len(ticker) > MAX_TICKER_LEN:
        return None, f"Ticker too long (max {MAX_TICKER_LEN} characters)."
    if not _TICKER_RE.match(ticker):
        return None, (
            "Invalid ticker format. Use letters, digits, dots, and hyphens "
            f"(e.g. AAPL, NESN.SW, BRK-B). Got: '{ticker}'"
        )
    return ticker.upper(), None


def validate_isin(isin: str) -> Tuple[Optional[str], Optional[str]]:
    """Validate and normalise an ISIN code.

    Returns (normalised_isin, error_message).
    """
    if not isin or not isin.strip():
        return None, "ISIN cannot be empty."
    isin = isin.strip().upper()
    if len(isin) != 12:
        return None, f"ISIN must be exactly 12 characters (got {len(isin)})."
    if not _ISIN_RE.match(isin):
        return None, (
            "Invalid ISIN format. Must be 2 letters + 10 alphanumeric "
            f"(e.g. US0378331005). Got: '{isin}'"
        )
    return isin, None


def validate_exchange(suffix: str) -> Tuple[Optional[str], Optional[str]]:
    """Validate an exchange suffix (e.g. SW, DE, AS).

    Returns (normalised_suffix, error_message).
    """
    if not suffix or not suffix.strip():
        return None, "Exchange suffix cannot be empty."
    suffix = suffix.strip().upper()
    if len(suffix) > MAX_EXCHANGE_LEN:
        return None, f"Exchange suffix too long (max {MAX_EXCHANGE_LEN})."
    if not _EXCHANGE_RE.match(suffix):
        return None, f"Invalid exchange suffix: '{suffix}'"
    return suffix, None


def validate_shares(value) -> Tuple[Optional[float], Optional[str]]:
    """Validate a share count.

    Returns (shares_float, error_message).
    """
    if value is None:
        return None, "Shares value is required."
    try:
        shares = float(value)
    except (TypeError, ValueError):
        return None, f"Invalid number for shares: '{value}'"
    if shares <= 0:
        return None, "Shares must be a positive number."
    if shares > 1_000_000_000:
        return None, "Shares value is unreasonably large."
    return shares, None


def validate_price(value) -> Tuple[Optional[float], Optional[str]]:
    """Validate a price value (avg purchase price, etc.).

    Returns (price_float, error_message). None value means "not provided"
    which is valid (optional cost tracking).
    """
    if value is None or (isinstance(value, str) and not value.strip()):
        return None, None  # not provided — valid
    try:
        price = float(value)
    except (TypeError, ValueError):
        return None, f"Invalid number for price: '{value}'"
    if price < 0:
        return None, "Price cannot be negative."
    if price > 1_000_000_000:
        return None, "Price value is unreasonably large."
    return price, None


def sanitise_search_query(query: str) -> Tuple[Optional[str], Optional[str]]:
    """Sanitise a search query string.

    Returns (cleaned_query, error_message).
    """
    if not query or not query.strip():
        return None, "Search query cannot be empty."
    query = query.strip()
    if len(query) > MAX_SEARCH_QUERY_LEN:
        return None, f"Search query too long (max {MAX_SEARCH_QUERY_LEN} chars)."
    # Remove control characters but keep unicode letters/digits/spaces/punctuation
    cleaned = re.sub(r'[\x00-\x1f\x7f]', '', query)
    if not cleaned:
        return None, "Search query contains only control characters."
    return cleaned, None
