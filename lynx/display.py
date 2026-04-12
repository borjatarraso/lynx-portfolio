"""
Terminal display helpers using Rich.
"""

import io
import re
import sys
from typing import List, Dict, Optional, Tuple

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import box

from . import forex

console = Console()

# Regex to strip ANSI escape sequences when measuring rendered text width.
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def _flush_console() -> None:
    """Flush stdout so Rich output is fully written before readline takes over."""
    sys.stdout.flush()


def _measure_renderable_width(renderable) -> int:
    """Render *renderable* off-screen and return the width of the widest line."""
    buf = Console(file=io.StringIO(), width=9999, no_color=False)
    buf.print(renderable)
    return max(
        (len(_ANSI_RE.sub("", line).rstrip()) for line in buf.file.getvalue().splitlines() if line.strip()),
        default=0,
    )


# ---------------------------------------------------------------------------
# Generic formatters
# ---------------------------------------------------------------------------

def _pnl_markup(pnl: float, pct: float) -> str:
    color = "green" if pnl >= 0 else "red"
    sign = "+" if pnl >= 0 else ""
    return f"[{color}]{sign}{pnl:,.2f} ({sign}{pct:.2f}%)[/{color}]"


def _price_str(value: Optional[float]) -> str:
    return f"{value:,.2f}" if value is not None else "N/A"


def _truncate(text: str, width: int) -> str:
    return text if len(text) <= width else text[: width - 3] + "..."


# ---------------------------------------------------------------------------
# Share formatting
# ---------------------------------------------------------------------------

def _split_shares(shares: float, quote_type: Optional[str]) -> Tuple[str, str]:
    """
    Return (integer_part, decimal_part) for a share count.

    integer_part : formatted integer with thousand-separators, e.g. "1,000"
    decimal_part : ".5", ".25", ".141592" — or "" for whole numbers / equities

    Rules
    -----
    EQUITY        → integer only, no decimals (fractional rounds at input).
    ETF/fund/None → whole number? → no decimal part.
                    fractional?   → minimal decimal places, trailing zeros stripped.
    """
    qt = (quote_type or "").upper()

    if qt == "EQUITY":
        return f"{int(round(shares)):,}", ""

    frac = shares - int(shares)
    if abs(frac) < 1e-9:
        return f"{int(shares):,}", ""

    # Round to 6 dp to kill floating-point noise, then strip trailing zeros.
    raw = f"{round(shares, 6):.6f}".rstrip("0")   # e.g. "1000.5", "3.141592"
    int_s, dec_s = raw.split(".")
    return f"{int(int_s):,}", f".{dec_s}"


def _shares_str(shares: float, quote_type: Optional[str] = None) -> str:
    """Single-value formatter used in the instrument detail view."""
    i, d = _split_shares(shares, quote_type)
    return i + d


def _align_shares_column(instruments: List[Dict]) -> List[str]:
    """
    Format every share count so that integer digits align column-wide.

    Strategy
    --------
    1. Split every value into (integer_part, decimal_part).
    2. Find the widest integer part (max_int) and widest decimal part
       (max_dec, including the leading dot) across all rows.
    3. Each string becomes:
           integer_part.rjust(max_int)  +  decimal_part.ljust(max_dec)

    This makes the ones digit of every integer part fall at the same
    column position, while decimal digits extend to the right:

        6,789
          145
           23.5
        1,000.25

    The Shares column must use justify="left" so Rich does not strip the
    leading spaces that carry the alignment information.
    """
    parts: List[Tuple[str, str]] = [
        _split_shares(inst.get("shares") or 0.0, inst.get("quote_type"))
        for inst in instruments
    ]

    max_int = max((len(p[0]) for p in parts), default=1)
    max_dec = max((len(p[1]) for p in parts), default=0)

    return [
        int_s.rjust(max_int) + dec_s.ljust(max_dec)
        for int_s, dec_s in parts
    ]


# ---------------------------------------------------------------------------
# Portfolio table
# ---------------------------------------------------------------------------

def display_portfolio(instruments: List[Dict]) -> None:
    if not instruments:
        console.print(
            "[yellow]Portfolio is empty. "
            "Add instruments with: lynx -ni add --ticker AAPL --shares 10 "
            "--avg-price 150[/yellow]"
        )
        _flush_console()
        return

    # Determine whether any instrument uses a non-EUR currency.
    rates = forex.get_session_rates()
    non_eur_ccys = {
        (inst.get("currency") or "EUR").upper()
        for inst in instruments
        if (inst.get("currency") or "EUR").upper() != "EUR"
    }
    show_eur = bool(non_eur_ccys)

    # Pre-compute aligned share strings (two-pass: widths first, then format).
    shares_strs = _align_shares_column(instruments)
    # Min column width = widest share string or the header, whichever is larger.
    shares_min_w = max(
        (len(s) for s in shares_strs),
        default=len("Shares"),
    )
    shares_min_w = max(shares_min_w, len("Shares"))

    table = Table(
        title="[bold cyan]Lynx Portfolio[/bold cyan]",
        box=box.ROUNDED,
        header_style="bold cyan",
        show_lines=False,
    )

    # When EUR columns are added, narrow the text-heavy columns (Name, Exchange,
    # ISIN) so the table stays within a reasonable width.  Numeric columns keep
    # their full width because truncating numbers is worse than truncating names.
    if show_eur:
        table.add_column("Ticker",     style="bold white", width=10,  no_wrap=True)
        table.add_column("ISIN",                           width=13,  no_wrap=True)
        table.add_column("Name",                           width=18)
        table.add_column("Exchange",                       width=12)
    else:
        table.add_column("Ticker",     style="bold white", width=12,  no_wrap=True)
        table.add_column("ISIN",                           width=14,  no_wrap=True)
        table.add_column("Name",                           width=26)
        table.add_column("Exchange",                       width=16)

    # justify="left"  → preserves leading spaces that carry alignment.
    # min_width       → prevents Rich from collapsing the column below content width.
    # no_wrap=True    → safe here because min_width guarantees content always fits.
    table.add_column("Shares",     justify="left",
                     min_width=shares_min_w, no_wrap=True)
    table.add_column("Avg Price",  justify="right",     width=11)
    table.add_column("Curr Price", justify="right",     width=11)
    table.add_column("CCY",                             width=5,  no_wrap=True)
    table.add_column("Mkt Value",  justify="right",     width=13)
    if show_eur:
        table.add_column("EUR Val",    justify="right",  width=13)
        table.add_column("EUR P&L",    justify="right",  width=22)
    else:
        table.add_column("P&L",        justify="right",  width=22)

    total_invested     = 0.0
    total_market       = 0.0
    total_invested_eur = 0.0
    total_market_eur   = 0.0
    missing_prices     = 0
    has_eur_gap        = False   # True if any EUR conversion was unavailable

    for inst, shares_str in zip(instruments, shares_strs):
        shares    = inst.get("shares") or 0.0
        avg_price = inst.get("avg_purchase_price") or 0.0
        curr      = inst.get("current_price")
        ccy       = (inst.get("currency") or "EUR").upper()
        invested  = shares * avg_price
        total_invested += invested

        invested_eur = forex.to_eur(invested, ccy)
        if invested_eur is not None:
            total_invested_eur += invested_eur
        else:
            has_eur_gap = True

        if curr is not None:
            mkt_val = shares * curr
            pnl     = mkt_val - invested
            pct     = (pnl / invested * 100) if invested else 0.0
            total_market += mkt_val
            curr_str = f"{curr:,.2f}"
            mkt_str  = f"{mkt_val:,.2f}"

            if show_eur:
                mkt_eur = forex.to_eur(mkt_val, ccy)
                pnl_eur = forex.to_eur(pnl, ccy)
                if mkt_eur is not None:
                    total_market_eur += mkt_eur
                    eur_mkt_str = f"{mkt_eur:,.2f}"
                else:
                    has_eur_gap = True
                    eur_mkt_str = "[dim]N/A[/dim]"
                if pnl_eur is not None:
                    eur_pnl_str = _pnl_markup(pnl_eur, pct)
                else:
                    eur_pnl_str = "[dim]N/A[/dim]"
            else:
                pnl_str = _pnl_markup(pnl, pct)
        else:
            missing_prices += 1
            curr_str = "N/A"
            mkt_str  = "N/A"
            if show_eur:
                eur_mkt_str = "[dim]N/A[/dim]"
                eur_pnl_str = "[dim]N/A[/dim]"
            else:
                pnl_str = "[dim]N/A[/dim]"

        exch_disp = (
            inst.get("exchange_display")
            or inst.get("exchange_code")
            or "—"
        )

        name_w = 18 if show_eur else 26
        exch_w = 12 if show_eur else 16

        row = [
            inst.get("ticker") or "",
            inst.get("isin") or "—",
            _truncate(inst.get("name") or "—", name_w),
            _truncate(exch_disp, exch_w),
            shares_str,
            f"{avg_price:,.2f}",
            curr_str,
            inst.get("currency") or "—",
            mkt_str,
        ]
        if show_eur:
            row += [eur_mkt_str, eur_pnl_str]
        else:
            row.append(pnl_str)

        table.add_row(*row)

    # Measure the rendered table width so the Summary Panel can match it.
    table_width = _measure_renderable_width(table)
    panel_width = min(table_width, console.width) if table_width else None

    console.print(table)

    total_pnl = total_market - total_invested
    total_pct = (total_pnl / total_invested * 100) if total_invested else 0.0
    color     = "green" if total_pnl >= 0 else "red"
    sign      = "+" if total_pnl >= 0 else ""

    if show_eur:
        total_pnl_eur = total_market_eur - total_invested_eur
        total_pct_eur = (total_pnl_eur / total_invested_eur * 100) if total_invested_eur else 0.0
        eur_color = "green" if total_pnl_eur >= 0 else "red"
        eur_sign  = "+" if total_pnl_eur >= 0 else ""
        eur_note  = "[dim] (partial)[/dim]" if has_eur_gap else ""
        summary = (
            f"EUR Invested: [green]{total_invested_eur:,.2f}[/green]  |  "
            f"EUR Market Value: [green]{total_market_eur:,.2f}[/green]  |  "
            f"EUR P&L: [{eur_color}]{eur_sign}{total_pnl_eur:,.2f} "
            f"({eur_sign}{total_pct_eur:.2f}%)[/{eur_color}]{eur_note}"
        )
        # Exchange rates used
        rate_parts = []
        for ccy in sorted(non_eur_ccys):
            rate = rates.get(ccy)
            if rate is not None:
                rate_parts.append(f"{ccy}/EUR={rate:.4f}")
            else:
                rate_parts.append(f"{ccy}/EUR=N/A")
        if rate_parts:
            summary += f"\n[dim]Rates: {'  '.join(rate_parts)}[/dim]"
    else:
        summary = (
            f"Invested: [green]{total_invested:,.2f}[/green]  |  "
            f"Market Value: [green]{total_market:,.2f}[/green]  |  "
            f"P&L: [{color}]{sign}{total_pnl:,.2f} ({sign}{total_pct:.2f}%)[/{color}]"
        )

    if missing_prices:
        summary += (
            f"\n[dim]{missing_prices} position(s) excluded from "
            f"Market Value / P&L (no price available)[/dim]"
        )
    console.print(Panel(
        summary, title="Summary", border_style="cyan",
        padding=(0, 2), width=panel_width,
    ))
    _flush_console()


# ---------------------------------------------------------------------------
# Single instrument detail
# ---------------------------------------------------------------------------

def display_instrument(inst: Dict) -> None:
    ticker    = inst.get("ticker", "")
    shares    = inst.get("shares") or 0.0
    avg_price = inst.get("avg_purchase_price") or 0.0
    curr      = inst.get("current_price")
    ccy       = (inst.get("currency") or "EUR").upper()
    invested  = shares * avg_price

    t = Table(show_header=False, box=box.SIMPLE, padding=(0, 1), expand=False)
    t.add_column("Field", style="bold cyan", width=22)
    t.add_column("Value", width=55)

    exch_disp = (
        inst.get("exchange_display")
        or inst.get("exchange_code")
        or "—"
    )
    qt = inst.get("quote_type")

    t.add_row("Ticker",               ticker)
    t.add_row("ISIN",                 inst.get("isin") or "—")
    t.add_row("Name",                 inst.get("name") or "—")
    t.add_row("Exchange",             exch_disp)
    t.add_row("Currency",             inst.get("currency") or "—")
    t.add_row("Sector",               inst.get("sector") or "—")
    t.add_row("Industry",             inst.get("industry") or "—")
    t.add_row("Shares",               _shares_str(shares, qt))
    t.add_row("Avg Purchase Price",   f"{avg_price:,.2f}")
    t.add_row("Current Price",        _price_str(curr))
    t.add_row("Total Invested",       f"{invested:,.2f}")

    # EUR equivalent for invested (when non-EUR)
    if ccy != "EUR":
        invested_eur = forex.to_eur(invested, ccy)
        if invested_eur is not None:
            t.add_row("Total Invested (EUR)", f"{invested_eur:,.2f}")

    if curr is not None:
        mkt_val = shares * curr
        pnl     = mkt_val - invested
        pct     = (pnl / invested * 100) if invested else 0.0
        t.add_row("Market Value", f"{mkt_val:,.2f}")
        if ccy != "EUR":
            mkt_eur = forex.to_eur(mkt_val, ccy)
            if mkt_eur is not None:
                t.add_row("Market Value (EUR)", f"{mkt_eur:,.2f}")
        t.add_row("P&L", _pnl_markup(pnl, pct))
        if ccy != "EUR":
            pnl_eur = forex.to_eur(pnl, ccy)
            if pnl_eur is not None:
                t.add_row("P&L (EUR)", _pnl_markup(pnl_eur, pct))

    if inst.get("description"):
        t.add_row("Description", inst["description"])

    t.add_row("Added",   inst.get("created_at") or "—")
    t.add_row("Updated", inst.get("updated_at") or "—")

    console.print(Panel(t, title=f"[bold]{ticker}[/bold]", border_style="cyan"))
    _flush_console()


# ---------------------------------------------------------------------------
# Status helpers
# ---------------------------------------------------------------------------

def ok(msg: str)   -> None: console.print(f"[green]✓[/green] {msg}"); _flush_console()
def err(msg: str)  -> None: console.print(f"[red]✗[/red] {msg}"); _flush_console()
def info(msg: str) -> None: console.print(f"[cyan]ℹ[/cyan] {msg}"); _flush_console()
def warn(msg: str) -> None: console.print(f"[yellow]⚠[/yellow] {msg}"); _flush_console()
