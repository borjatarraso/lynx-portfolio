"""
Core portfolio operations shared between interactive, non-interactive, TUI,
and API modes.
"""

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional, List, Dict, Callable
from . import database, cache, fetcher


# ---------------------------------------------------------------------------
# Notifier abstraction — decouples operations from display
# ---------------------------------------------------------------------------

class Notifier:
    """Base notifier — all methods are no-ops.  Override to customise."""
    def info(self, msg: str) -> None: pass
    def ok(self, msg: str) -> None: pass
    def err(self, msg: str) -> None: pass
    def warn(self, msg: str) -> None: pass
    def show_instrument(self, inst: dict) -> None: pass


class DisplayNotifier(Notifier):
    """Default notifier — delegates to the Rich display module."""
    def info(self, msg: str) -> None:
        from . import display; display.info(msg)
    def ok(self, msg: str) -> None:
        from . import display; display.ok(msg)
    def err(self, msg: str) -> None:
        from . import display; display.err(msg)
    def warn(self, msg: str) -> None:
        from . import display; display.warn(msg)
    def show_instrument(self, inst: dict) -> None:
        from . import display; display.display_instrument(inst)


_notifier: Notifier = DisplayNotifier()


def set_notifier(n: Notifier) -> None:
    """Replace the global notifier (e.g. for headless API mode)."""
    global _notifier
    _notifier = n


# ---------------------------------------------------------------------------
# Cache-aware data fetch
# ---------------------------------------------------------------------------

def _fetch_with_cache(
    yahoo_symbol: str, isin: Optional[str] = None
) -> Optional[dict]:
    cached = cache.get(yahoo_symbol)
    if cached:
        _notifier.info(f"Using cached data for {yahoo_symbol}")
        return cached
    _notifier.info(f"Fetching data for {yahoo_symbol} from Yahoo Finance…")
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
    avg_purchase_price: Optional[float] = None,
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
    from .validation import (
        validate_ticker, validate_isin, validate_shares, validate_price,
        validate_exchange,
    )

    if not ticker and not isin:
        _notifier.err("Provide at least --ticker or --isin.")
        return False

    # Validate inputs
    if ticker:
        ticker, err = validate_ticker(ticker)
        if err:
            _notifier.err(err)
            return False

    if isin:
        isin, err = validate_isin(isin)
        if err:
            _notifier.err(err)
            return False

    shares, err = validate_shares(shares)
    if err:
        _notifier.err(err)
        return False

    if avg_purchase_price is not None:
        avg_purchase_price, err = validate_price(avg_purchase_price)
        if err:
            _notifier.err(err)
            return False

    if preferred_exchange:
        preferred_exchange, err = validate_exchange(preferred_exchange)
        if err:
            _notifier.err(err)
            return False

    # 1 ─ Resolve all available markets
    try:
        markets, base_ticker = fetcher.resolve_markets_for_input(ticker, isin)
    except Exception as exc:
        _notifier.err(f"Failed to resolve instrument: {exc}")
        return False

    # 2 ─ Pick one market
    chosen: Optional[Dict] = None

    if not markets:
        _notifier.err(
            "Could not find any market listing for this instrument. "
            "Check the ticker/ISIN and try again."
        )
        return False

    if len(markets) == 1:
        chosen = markets[0]
    elif market_selector is not None:
        chosen = market_selector(markets)
        if chosen is None:
            _notifier.info("Cancelled.")
            return False
    else:
        chosen = fetcher.pick_best_market(markets, isin, preferred_exchange)

    yahoo_symbol = chosen["symbol"]
    _notifier.info(
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
            _notifier.warn(
                f"Stocks cannot have fractional shares "
                f"({shares} → rounded to {rounded})."
            )
            shares = float(rounded)

    # 4 ─ Persist
    success = database.add_instrument(
        ticker                = yahoo_symbol,
        isin                  = isin or data.get("isin"),
        shares                = shares,
        avg_purchase_price    = avg_purchase_price,
        name                  = data.get("name"),
        current_price         = data.get("current_price"),
        regular_market_change = data.get("regular_market_change"),
        currency              = data.get("currency") or chosen.get("currency"),
        sector                = data.get("sector"),
        industry              = data.get("industry"),
        description           = data.get("description"),
        exchange_code         = data.get("exchange_code") or chosen.get("exchange_code"),
        exchange_display      = chosen.get("exchange_display"),
        quote_type            = data.get("quote_type"),
    )

    if success:
        _notifier.ok(f"Added {yahoo_symbol} to portfolio.")
        inst = database.get_instrument(yahoo_symbol)
        if inst:
            _notifier.show_instrument(inst)
        return True
    else:
        _notifier.err(
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
    _notifier.info(f"Refreshing {ticker}…")
    try:
        data = fetcher.fetch_instrument_data(ticker, isin)
    except Exception as exc:
        _notifier.err(f"Failed to fetch data for {ticker}: {exc}")
        return False
    if not data:
        _notifier.err(f"Failed to fetch data for {ticker}.")
        return False
    cache.put(ticker, data)
    database.apply_cache_to_portfolio(ticker, data)
    _notifier.ok(f"Refreshed {ticker}.")
    return True


def refresh_all(max_workers: int = 4) -> None:
    instruments = database.get_all_instruments()
    if not instruments:
        _notifier.info("Portfolio is empty.")
        return
    if len(instruments) <= 2:
        for inst in instruments:
            refresh_instrument(inst["ticker"])
        return
    # Parallel refresh for larger portfolios
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {
            pool.submit(refresh_instrument, inst["ticker"]): inst["ticker"]
            for inst in instruments
        }
        for future in as_completed(futures):
            try:
                future.result()
            except Exception:
                _notifier.err(f"Failed to refresh {futures[future]}.")


def refresh_instrument_quiet(ticker: str) -> bool:
    """Refresh a single instrument without any notifier output."""
    try:
        inst = database.get_instrument(ticker)
        isin = inst.get("isin") if inst else None
        cache.delete(ticker)
        data = fetcher.fetch_instrument_data(ticker, isin)
        if not data:
            return False
        cache.put(ticker, data)
        database.apply_cache_to_portfolio(ticker, data)
        return True
    except Exception:
        return False
