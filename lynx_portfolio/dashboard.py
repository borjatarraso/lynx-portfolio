"""Portfolio dashboard analytics — shared by CLI, TUI, GUI, and Flask API.

Every dashboard feature lives here as a pure function so that the same
numbers power the terminal display, the JSON API, and any future mobile /
web client. The module reads the current portfolio state (from
:mod:`.database`) and optionally converts values to EUR via
:mod:`.forex`.

All public functions return plain dictionaries that serialize cleanly to
JSON. ``None`` values mean "insufficient data" — callers decide whether to
show ``"—"`` in a table or omit the row.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from . import database, forex


__all__ = [
    "compute_stats",
    "compute_sector_allocation",
    "compute_movers",
    "compute_income",
    "compute_alerts",
    "compute_benchmark",
    "compute_full_dashboard",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _eur(amount: Optional[float], currency: str) -> Optional[float]:
    if amount is None:
        return None
    return forex.to_eur(amount, (currency or "EUR").upper())


def _enrich(inst: Dict[str, Any]) -> Dict[str, Any]:
    """Attach market value, invested, pnl, pnl_pct to *inst* (non-mutating)."""
    out = dict(inst)
    shares = out.get("shares") or 0.0
    avg = out.get("avg_purchase_price")
    curr = out.get("current_price")
    ccy = (out.get("currency") or "EUR").upper()

    if curr is not None:
        mkt = shares * curr
        out["market_value"] = round(mkt, 2)
        out["market_value_eur"] = round(_eur(mkt, ccy) or 0.0, 2) if _eur(mkt, ccy) is not None else None
    else:
        out["market_value"] = None
        out["market_value_eur"] = None

    if avg is not None:
        invested = shares * avg
        out["total_invested"] = round(invested, 2)
        out["total_invested_eur"] = round(_eur(invested, ccy) or 0.0, 2) if _eur(invested, ccy) is not None else None
        if curr is not None:
            pnl = (shares * curr) - invested
            pct = (pnl / invested * 100.0) if invested else 0.0
            out["pnl"] = round(pnl, 2)
            out["pnl_pct"] = round(pct, 2)
            out["pnl_eur"] = round(_eur(pnl, ccy) or 0.0, 2) if _eur(pnl, ccy) is not None else None
        else:
            out["pnl"] = None
            out["pnl_pct"] = None
            out["pnl_eur"] = None
    else:
        out["total_invested"] = None
        out["total_invested_eur"] = None
        out["pnl"] = None
        out["pnl_pct"] = None
        out["pnl_eur"] = None
    return out


def _day_change_eur(inst: Dict[str, Any]) -> Optional[float]:
    """Portfolio day change in EUR for one position, or None if unknown."""
    change = inst.get("regular_market_change")
    shares = inst.get("shares") or 0.0
    ccy = (inst.get("currency") or "EUR").upper()
    if change is None:
        return None
    return _eur(change * shares, ccy)


# ---------------------------------------------------------------------------
# Core summary stats
# ---------------------------------------------------------------------------

def compute_stats() -> Dict[str, Any]:
    """Return the portfolio-level summary card.

    Fields: ``positions``, ``total_value_eur``, ``total_invested_eur``,
    ``total_pnl_eur``, ``total_pnl_pct``, ``day_change_eur``,
    ``day_change_pct``, ``generated_at``.
    """
    instruments = [_enrich(i) for i in database.get_all_instruments()]

    total_value = 0.0
    total_invested = 0.0
    day_change = 0.0
    day_change_known = False

    for inst in instruments:
        mv = inst.get("market_value_eur")
        ti = inst.get("total_invested_eur")
        if mv is not None:
            total_value += mv
        if ti is not None:
            total_invested += ti
        dc = _day_change_eur(inst)
        if dc is not None:
            day_change += dc
            day_change_known = True

    pnl = total_value - total_invested if total_invested else 0.0
    pnl_pct = (pnl / total_invested * 100.0) if total_invested else 0.0
    day_pct = (day_change / total_value * 100.0) if total_value else 0.0

    return {
        "positions": len(instruments),
        "total_value_eur": round(total_value, 2),
        "total_invested_eur": round(total_invested, 2),
        "total_pnl_eur": round(pnl, 2),
        "total_pnl_pct": round(pnl_pct, 2),
        "day_change_eur": round(day_change, 2) if day_change_known else None,
        "day_change_pct": round(day_pct, 2) if day_change_known and total_value else None,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


# ---------------------------------------------------------------------------
# Sector allocation
# ---------------------------------------------------------------------------

def compute_sector_allocation() -> List[Dict[str, Any]]:
    """Return sector buckets sorted by EUR market value (descending).

    Each row: ``sector``, ``positions``, ``value_eur``, ``pct_of_portfolio``.
    Positions with an unknown sector go into the ``"Unclassified"`` bucket.
    """
    instruments = [_enrich(i) for i in database.get_all_instruments()]

    total_value = sum(
        i.get("market_value_eur") or 0.0 for i in instruments
    )

    buckets: Dict[str, Dict[str, Any]] = defaultdict(
        lambda: {"positions": 0, "value_eur": 0.0}
    )
    for inst in instruments:
        sector = (inst.get("sector") or "Unclassified").strip() or "Unclassified"
        row = buckets[sector]
        row["positions"] += 1
        mv = inst.get("market_value_eur") or 0.0
        row["value_eur"] += mv

    rows: List[Dict[str, Any]] = []
    for sector, row in buckets.items():
        value = round(row["value_eur"], 2)
        pct = (value / total_value * 100.0) if total_value else 0.0
        rows.append({
            "sector": sector,
            "positions": row["positions"],
            "value_eur": value,
            "pct_of_portfolio": round(pct, 2),
        })
    rows.sort(key=lambda r: r["value_eur"], reverse=True)
    return rows


# ---------------------------------------------------------------------------
# Top gainers / losers for the day
# ---------------------------------------------------------------------------

def compute_movers(limit: int = 5) -> Dict[str, List[Dict[str, Any]]]:
    """Return the top-``limit`` gainers and losers by day change percentage.

    Requires ``regular_market_change`` and ``current_price`` on the
    instrument rows — positions missing either are excluded.
    """
    scored: List[Dict[str, Any]] = []
    for inst in database.get_all_instruments():
        change = inst.get("regular_market_change")
        curr = inst.get("current_price")
        if change is None or curr is None or curr <= 0:
            continue
        prev_close = curr - change
        pct = (change / prev_close * 100.0) if prev_close else 0.0
        scored.append({
            "ticker": inst.get("ticker"),
            "name": inst.get("name"),
            "sector": inst.get("sector"),
            "day_change_pct": round(pct, 2),
            "day_change_abs": round(change, 4),
            "current_price": round(curr, 4),
            "currency": (inst.get("currency") or "EUR").upper(),
        })

    gainers = sorted(
        [r for r in scored if r["day_change_pct"] > 0],
        key=lambda r: r["day_change_pct"], reverse=True,
    )[:limit]
    losers = sorted(
        [r for r in scored if r["day_change_pct"] < 0],
        key=lambda r: r["day_change_pct"],
    )[:limit]
    return {"gainers": gainers, "losers": losers}


# ---------------------------------------------------------------------------
# Dividend income projection
# ---------------------------------------------------------------------------

def compute_income() -> Dict[str, Any]:
    """Estimate annual dividend income across the portfolio.

    Uses each instrument's ``dividend_rate`` (annual $/share) and
    ``dividend_yield`` (expressed as percent) if present. Returns totals in
    EUR plus per-position contributions.
    """
    contributions: List[Dict[str, Any]] = []
    total_eur = 0.0
    for inst in database.get_all_instruments():
        shares = inst.get("shares") or 0.0
        ccy = (inst.get("currency") or "EUR").upper()
        rate = inst.get("dividend_rate")  # annual cash per share
        yld = inst.get("dividend_yield")  # percent or fraction
        curr = inst.get("current_price")

        annual = None
        if rate is not None and shares:
            annual = rate * shares
        elif yld is not None and curr is not None and shares:
            # yfinance emits dividendYield as a fraction (0.025 = 2.5%)
            yld_frac = yld if yld <= 1 else yld / 100.0
            annual = curr * yld_frac * shares

        if annual is None:
            continue
        annual_eur = _eur(annual, ccy)
        if annual_eur is None:
            continue
        contributions.append({
            "ticker": inst.get("ticker"),
            "annual_income": round(annual, 2),
            "annual_income_eur": round(annual_eur, 2),
            "currency": ccy,
        })
        total_eur += annual_eur

    contributions.sort(key=lambda r: r["annual_income_eur"], reverse=True)

    stats = compute_stats()
    portfolio_value = stats["total_value_eur"]
    yield_on_cost = None
    if stats["total_invested_eur"]:
        yield_on_cost = round(total_eur / stats["total_invested_eur"] * 100.0, 2)
    portfolio_yield = None
    if portfolio_value:
        portfolio_yield = round(total_eur / portfolio_value * 100.0, 2)

    return {
        "annual_income_eur": round(total_eur, 2),
        "monthly_income_eur": round(total_eur / 12.0, 2),
        "portfolio_yield_pct": portfolio_yield,
        "yield_on_cost_pct": yield_on_cost,
        "contributions": contributions,
    }


# ---------------------------------------------------------------------------
# Alerts (drawdown / concentration / stale)
# ---------------------------------------------------------------------------

def compute_alerts(
    *,
    drawdown_pct: float = 15.0,
    concentration_pct: float = 20.0,
    stale_days: int = 7,
) -> List[Dict[str, Any]]:
    """Return a list of actionable alerts about the portfolio.

    An alert dict has ``severity`` (``"info"|"warn"|"critical"``),
    ``kind``, ``ticker`` (optional), and ``message``. Alerts fired:

    * **drawdown** — position PnL % is below ``-drawdown_pct``.
    * **concentration** — position weight > ``concentration_pct`` of
      portfolio value.
    * **stale** — ``updated_at`` older than ``stale_days`` days.
    * **missing_avg_price** — position with shares but no cost basis.
    """
    alerts: List[Dict[str, Any]] = []
    instruments = [_enrich(i) for i in database.get_all_instruments()]
    total_value = sum(i.get("market_value_eur") or 0.0 for i in instruments)

    for inst in instruments:
        ticker = inst.get("ticker")
        pnl_pct = inst.get("pnl_pct")
        mv = inst.get("market_value_eur") or 0.0
        avg = inst.get("avg_purchase_price")

        if pnl_pct is not None and pnl_pct <= -drawdown_pct:
            alerts.append({
                "severity": "critical" if pnl_pct <= -2 * drawdown_pct else "warn",
                "kind": "drawdown",
                "ticker": ticker,
                "message": f"{ticker} is down {pnl_pct:.1f}% vs cost basis",
            })

        if total_value and (mv / total_value * 100.0) >= concentration_pct:
            pct = mv / total_value * 100.0
            alerts.append({
                "severity": "warn",
                "kind": "concentration",
                "ticker": ticker,
                "message": f"{ticker} is {pct:.1f}% of portfolio — concentrated",
            })

        if avg is None and (inst.get("shares") or 0.0) > 0:
            alerts.append({
                "severity": "info",
                "kind": "missing_avg_price",
                "ticker": ticker,
                "message": f"{ticker} has no recorded cost basis",
            })

        updated_at = inst.get("updated_at")
        if updated_at:
            try:
                last = datetime.fromisoformat(updated_at[:19])
                age_days = (datetime.now() - last).days
                if age_days >= stale_days:
                    alerts.append({
                        "severity": "info",
                        "kind": "stale",
                        "ticker": ticker,
                        "message": f"{ticker} last refreshed {age_days}d ago",
                    })
            except ValueError:
                pass

    return alerts


# ---------------------------------------------------------------------------
# Benchmark comparison (cost-basis relative performance)
# ---------------------------------------------------------------------------

def compute_benchmark(benchmark_ticker: str = "^GSPC") -> Dict[str, Any]:
    """Best-effort total-return comparison vs a market index.

    Only a coarse comparison: total portfolio PnL % since cost basis vs
    the benchmark's return over the same holding horizon (defaulting to
    the last 365 days if individual purchase dates are unavailable).
    """
    from . import fetcher

    stats = compute_stats()
    portfolio_return = stats.get("total_pnl_pct") or 0.0

    benchmark = None
    try:
        data = fetcher.fetch_instrument_data(benchmark_ticker)
    except Exception:
        data = None

    if data:
        curr = data.get("current_price")
        # Use year-ago price if fetcher exposes it; otherwise fall back to
        # the 52-week low / high as a rough anchor.
        yearly_change = data.get("fifty_two_week_change")
        if yearly_change is None and curr is not None:
            low = data.get("fifty_two_week_low")
            high = data.get("fifty_two_week_high")
            if low and high and low > 0:
                # Midpoint of the 52-wk band as a proxy
                mid = (low + high) / 2
                yearly_change = (curr - mid) / mid * 100.0 if mid else None
        benchmark = {
            "ticker": benchmark_ticker,
            "current_price": curr,
            "return_pct": round(yearly_change, 2) if yearly_change is not None else None,
        }

    alpha = None
    if benchmark and benchmark["return_pct"] is not None:
        alpha = round(portfolio_return - benchmark["return_pct"], 2)

    return {
        "portfolio_return_pct": portfolio_return,
        "benchmark": benchmark,
        "alpha_pct": alpha,
    }


# ---------------------------------------------------------------------------
# Full dashboard snapshot
# ---------------------------------------------------------------------------

def compute_full_dashboard() -> Dict[str, Any]:
    """Single call returning every dashboard section."""
    return {
        "stats": compute_stats(),
        "sectors": compute_sector_allocation(),
        "movers": compute_movers(),
        "income": compute_income(),
        "alerts": compute_alerts(),
    }
