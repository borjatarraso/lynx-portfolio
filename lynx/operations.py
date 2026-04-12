"""
Core portfolio operations shared between interactive and non-interactive modes.
"""

from typing import Optional, List, Dict, Callable
from . import database, cache, fetcher, display


# ---------------------------------------------------------------------------
# Cache-aware data fetch
# ---------------------------------------------------------------------------

def _fetch_with_cache(
    yahoo_symbol: str, isin: Optional[str] = None
) -> Optional[dict]:
    cached = cache.get(yahoo_symbol)
    if cached:
        display.info(f"Using cached data for {yahoo_symbol}")
        return cached
    display.info(f"Fetching data for {yahoo_symbol} from Yahoo Finance…")
    data = fetcher.fetch_instrument_data(yahoo_symbol, isin)
    if data:
        cache.put(yahoo_symbol, data)
    return data


# ---------------------------------------------------------------------------
# Add instrument (with market selection)
# ---------------------------------------------------------------------------

def add_instrument(
    ticker: Optional[str],
    isin: Optional[str],
    shares: float,
    avg_purchase_price: float,
    preferred_exchange: Optional[str] = None,
    market_selector: Optional[Callable[[List[Dict]], Optional[Dict]]] = None,
) -> bool:
    """
    Resolve the instrument to a specific Yahoo Finance symbol, fetch data,
    and persist to the DB.

    Parameters
    ----------
    ticker            : raw ticker (may already include suffix, e.g. NESN.SW)
    isin              : ISIN code
    shares            : position size
    avg_purchase_price: average cost per share
    preferred_exchange: suffix hint (e.g. 'SW', 'DE') from --exchange flag
    market_selector   : callable(markets) → chosen market dict; used by
                        interactive mode to show a selection prompt.
                        When None, auto-picks via pick_best_market().

    Returns True on success.
    """
    if not ticker and not isin:
        display.err("Provide at least --ticker or --isin.")
        return False

    # 1 ─ Resolve all available markets
    markets, base_ticker = fetcher.resolve_markets_for_input(ticker, isin)

    # 2 ─ Pick one market
    chosen: Optional[Dict] = None

    if not markets:
        display.err(
            "Could not find any market listing for this instrument. "
            "Check the ticker/ISIN and try again."
        )
        return False

    if len(markets) == 1:
        chosen = markets[0]
    elif market_selector is not None:
        chosen = market_selector(markets)
        if chosen is None:
            display.info("Cancelled.")
            return False
    else:
        chosen = fetcher.pick_best_market(markets, isin, preferred_exchange)

    yahoo_symbol = chosen["symbol"]
    display.info(
        f"Using {yahoo_symbol}  ({chosen['exchange_display'] or chosen['exchange_code']})"
    )

    # 3 ─ Fetch instrument details
    data = _fetch_with_cache(yahoo_symbol, isin) or {}

    # Supplement with search metadata if API returned nothing
    if not data.get("name"):
        data["name"] = chosen.get("longname") or chosen.get("shortname") or yahoo_symbol
    if not data.get("sector"):
        data["sector"] = chosen.get("sector")
    if not data.get("industry"):
        data["industry"] = chosen.get("industry")
    if not data.get("quote_type"):
        data["quote_type"] = chosen.get("quote_type")

    # 3b ─ Validate / normalise share count based on instrument type
    qt = (data.get("quote_type") or "").upper()
    if qt == "EQUITY":
        frac = shares - int(shares)
        if abs(frac) > 1e-9:
            rounded = round(shares)
            display.warn(
                f"Stocks cannot have fractional shares "
                f"({shares} → rounded to {rounded})."
            )
            shares = float(rounded)

    # 4 ─ Persist
    success = database.add_instrument(
        ticker             = yahoo_symbol,
        isin               = isin or data.get("isin"),
        shares             = shares,
        avg_purchase_price = avg_purchase_price,
        name               = data.get("name"),
        current_price      = data.get("current_price"),
        currency           = data.get("currency") or chosen.get("currency"),
        sector             = data.get("sector"),
        industry           = data.get("industry"),
        description        = data.get("description"),
        exchange_code      = data.get("exchange_code") or chosen.get("exchange_code"),
        exchange_display   = chosen.get("exchange_display"),
        quote_type         = data.get("quote_type"),
    )

    if success:
        display.ok(f"Added {yahoo_symbol} to portfolio.")
        inst = database.get_instrument(yahoo_symbol)
        if inst:
            display.display_instrument(inst)
        return True
    else:
        display.err(
            f"{yahoo_symbol} already exists. Use 'update' to change shares/price."
        )
        return False


# ---------------------------------------------------------------------------
# Refresh
# ---------------------------------------------------------------------------

def refresh_instrument(ticker: str) -> bool:
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
