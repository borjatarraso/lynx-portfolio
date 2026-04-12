"""
Terminal display helpers using Rich.
"""

from typing import List, Dict, Optional, Tuple

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import box

console = Console()


# ---------------------------------------------------------------------------
# Generic formatters
# ---------------------------------------------------------------------------

def _pnl_markup(pnl: float, pct: float) -> str:
    color = "green" if pnl >= 0 else "red"
    sign = "+" if pnl >= 0 else ""
    return f"[{color}]{sign}{pnl:,.2f} ({sign}{pct:.2f}%)[/{color}]"


def _price_str(value: Optional[float]) -> str:
    return f"{value:,.4f}" if value is not None else "N/A"


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
        return

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

    table.add_column("Ticker",     style="bold white",  width=12,            no_wrap=True)
    table.add_column("ISIN",                            width=14,            no_wrap=True)
    table.add_column("Name",                            width=26)
    table.add_column("Exchange",                        width=16)
    # justify="left"  → preserves leading spaces that carry alignment.
    # min_width       → prevents Rich from collapsing the column below content width.
    # no_wrap=True    → safe here because min_width guarantees content always fits.
    table.add_column("Shares",     justify="left",
                     min_width=shares_min_w, no_wrap=True)
    table.add_column("Avg Price",  justify="right",     width=11)
    table.add_column("Curr Price", justify="right",     width=11)
    table.add_column("CCY",                             width=5,             no_wrap=True)
    table.add_column("Mkt Value",  justify="right",     width=13)
    table.add_column("P&L",        justify="right",     width=22)

    total_invested = 0.0
    total_market   = 0.0

    for inst, shares_str in zip(instruments, shares_strs):
        shares    = inst.get("shares") or 0.0
        avg_price = inst.get("avg_purchase_price") or 0.0
        curr      = inst.get("current_price")
        invested  = shares * avg_price
        total_invested += invested

        if curr is not None:
            mkt_val = shares * curr
            pnl     = mkt_val - invested
            pct     = (pnl / invested * 100) if invested else 0.0
            total_market += mkt_val
            curr_str = f"{curr:,.2f}"
            mkt_str  = f"{mkt_val:,.2f}"
            pnl_str  = _pnl_markup(pnl, pct)
        else:
            total_market += invested
            curr_str = "N/A"
            mkt_str  = "N/A"
            pnl_str  = "[dim]N/A[/dim]"

        exch_disp = (
            inst.get("exchange_display")
            or inst.get("exchange_code")
            or "—"
        )

        table.add_row(
            inst.get("ticker") or "",
            inst.get("isin") or "—",
            _truncate(inst.get("name") or "—", 26),
            _truncate(exch_disp, 16),
            shares_str,
            f"{avg_price:,.2f}",
            curr_str,
            inst.get("currency") or "—",
            mkt_str,
            pnl_str,
        )

    console.print(table)

    total_pnl = total_market - total_invested
    total_pct = (total_pnl / total_invested * 100) if total_invested else 0.0
    color     = "green" if total_pnl >= 0 else "red"
    sign      = "+" if total_pnl >= 0 else ""
    summary   = (
        f"Invested: {total_invested:,.2f}  |  "
        f"Market Value: {total_market:,.2f}  |  "
        f"P&L: [{color}]{sign}{total_pnl:,.2f} ({sign}{total_pct:.2f}%)[/{color}]"
    )
    console.print(Panel(summary, title="Summary", border_style="cyan", padding=(0, 2)))


# ---------------------------------------------------------------------------
# Single instrument detail
# ---------------------------------------------------------------------------

def display_instrument(inst: Dict) -> None:
    ticker    = inst.get("ticker", "")
    shares    = inst.get("shares") or 0.0
    avg_price = inst.get("avg_purchase_price") or 0.0
    curr      = inst.get("current_price")
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

    if curr is not None:
        mkt_val = shares * curr
        pnl     = mkt_val - invested
        pct     = (pnl / invested * 100) if invested else 0.0
        t.add_row("Market Value", f"{mkt_val:,.2f}")
        t.add_row("P&L",         _pnl_markup(pnl, pct))

    if inst.get("description"):
        t.add_row("Description", inst["description"])

    t.add_row("Added",   inst.get("created_at") or "—")
    t.add_row("Updated", inst.get("updated_at") or "—")

    console.print(Panel(t, title=f"[bold]{ticker}[/bold]", border_style="cyan"))


# ---------------------------------------------------------------------------
# Status helpers
# ---------------------------------------------------------------------------

def ok(msg: str)   -> None: console.print(f"[green]✓[/green] {msg}")
def err(msg: str)  -> None: console.print(f"[red]✗[/red] {msg}")
def info(msg: str) -> None: console.print(f"[cyan]ℹ[/cyan] {msg}")
def warn(msg: str) -> None: console.print(f"[yellow]⚠[/yellow] {msg}")
