"""
Core portfolio operations shared between interactive and non-interactive modes.
"""

from typing import Optional
from . import database, cache, fetcher, display


def _fetch_with_cache(ticker: str, isin: Optional[str] = None) -> Optional[dict]:
    """Return cached data or fetch fresh, updating cache on success."""
    cached = cache.get(ticker)
    if cached:
        display.info(f"Using cached data for {ticker}")
        return cached
    display.info(f"Fetching data for {ticker} from Yahoo Finance…")
    data = fetcher.fetch_instrument_data(ticker, isin)
    if data:
        cache.put(ticker, data)
    return data


def add_instrument(
    ticker: Optional[str],
    isin: Optional[str],
    shares: float,
    avg_purchase_price: float,
) -> bool:
    """
    Resolve ticker/ISIN, fetch instrument data, persist to DB.
    Returns True on success.
    """
    # Resolve
    if not ticker and not isin:
        display.err("Provide at least --ticker or --isin.")
        return False

    if not ticker:
        display.info(f"Resolving ISIN {isin} via OpenFIGI…")
        resolved = fetcher.isin_to_ticker(isin)
        if resolved:
            ticker = resolved
            display.info(f"Resolved to ticker: {ticker}")
        else:
            display.warn(f"Could not resolve ISIN {isin} to a ticker. Saving with ISIN only.")

    ticker = ticker.upper() if ticker else None
    isin   = isin.upper()   if isin   else None

    # Fetch market data
    data = _fetch_with_cache(ticker, isin) if ticker else {}
    data = data or {}

    success = database.add_instrument(
        ticker             = ticker or isin,   # fallback key
        isin               = isin or data.get("isin"),
        shares             = shares,
        avg_purchase_price = avg_purchase_price,
        name               = data.get("name"),
        current_price      = data.get("current_price"),
        currency           = data.get("currency"),
        sector             = data.get("sector"),
        industry           = data.get("industry"),
        description        = data.get("description"),
    )

    if success:
        display.ok(f"Added {ticker or isin} to portfolio.")
        inst = database.get_instrument(ticker or isin)
        if inst:
            display.display_instrument(inst)
        return True
    else:
        display.err(f"{ticker or isin} already exists. Use 'update' to change shares/price.")
        return False


def refresh_instrument(ticker: str) -> bool:
    """Delete cache for ticker, re-fetch, update portfolio row."""
    inst = database.get_instrument(ticker)
    isin = inst.get("isin") if inst else None

    cache.delete(ticker)
    display.info(f"Refreshing {ticker}…")
    data = fetcher.fetch_instrument_data(ticker, isin)
    if not data:
        display.err(f"Failed to fetch data for {ticker}.")
        return False
    cache.put(ticker, data)
    database.apply_cache_to_portfolio(ticker, data)
    display.ok(f"Refreshed {ticker}.")
    return True


def refresh_all() -> None:
    instruments = database.get_all_instruments()
    if not instruments:
        display.info("Portfolio is empty.")
        return
    for inst in instruments:
        refresh_instrument(inst["ticker"])
