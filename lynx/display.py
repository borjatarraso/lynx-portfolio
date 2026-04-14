"""
Terminal display helpers using Rich.
"""

import io
import re
import sys
import time
from typing import List, Dict, Optional, Tuple, Callable

from rich.console import Console
from rich.live import Live
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
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
            "Add instruments with: lynx -c add --ticker AAPL --shares 10 "
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
        table.add_column("Name",                           width=26)
        table.add_column("Exchange",                       width=18)
    else:
        table.add_column("Ticker",     style="bold white", width=12,  no_wrap=True)
        table.add_column("ISIN",                           width=14,  no_wrap=True)
        table.add_column("Name",                           width=30)
        table.add_column("Exchange",                       width=20)

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
    total_today_eur    = 0.0     # sum of (regularMarketChange * shares) in EUR
    has_today_data     = False   # True if at least one instrument has 1d change
    missing_prices     = 0
    untracked_cost     = 0       # positions without avg_purchase_price
    has_eur_gap        = False   # True if any EUR conversion was unavailable

    for inst, shares_str in zip(instruments, shares_strs):
        shares    = inst.get("shares") or 0.0
        avg_price = inst.get("avg_purchase_price")   # may be None
        curr      = inst.get("current_price")
        ccy       = (inst.get("currency") or "EUR").upper()

        has_cost = avg_price is not None
        if has_cost:
            invested = shares * avg_price
            total_invested += invested
            invested_eur = forex.to_eur(invested, ccy)
            if invested_eur is not None:
                total_invested_eur += invested_eur
            else:
                has_eur_gap = True
        else:
            untracked_cost += 1

        # Accumulate today's change in EUR
        rmc = inst.get("regular_market_change")
        if rmc is not None:
            day_change = rmc * shares
            day_change_eur = forex.to_eur(day_change, ccy)
            if day_change_eur is not None:
                total_today_eur += day_change_eur
                has_today_data = True

        if curr is not None:
            mkt_val = shares * curr
            total_market += mkt_val
            curr_str = f"{curr:,.2f}"
            mkt_str  = f"{mkt_val:,.2f}"

            if has_cost:
                pnl = mkt_val - invested
                pct = (pnl / invested * 100) if invested else 0.0
            else:
                pnl = None
                pct = None

            if show_eur:
                mkt_eur = forex.to_eur(mkt_val, ccy)
                if mkt_eur is not None:
                    total_market_eur += mkt_eur
                    eur_mkt_str = f"{mkt_eur:,.2f}"
                else:
                    has_eur_gap = True
                    eur_mkt_str = "[dim]N/A[/dim]"
                if pnl is not None:
                    pnl_eur = forex.to_eur(pnl, ccy)
                    eur_pnl_str = _pnl_markup(pnl_eur, pct) if pnl_eur is not None else "[dim]N/A[/dim]"
                else:
                    eur_pnl_str = "[dim]—[/dim]"
            else:
                pnl_str = _pnl_markup(pnl, pct) if pnl is not None else "[dim]—[/dim]"
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

        name_w = 26 if show_eur else 30
        exch_w = 18 if show_eur else 20

        row = [
            inst.get("ticker") or "",
            inst.get("isin") or "—",
            _truncate(inst.get("name") or "—", name_w),
            _truncate(exch_disp, exch_w),
            shares_str,
            f"{avg_price:,.2f}" if has_cost else "[dim]—[/dim]",
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
        today_color = "green" if total_today_eur >= 0 else "red"
        today_sign  = "+" if total_today_eur >= 0 else ""
        today_str   = (
            f"[{today_color}]{today_sign}{total_today_eur:,.2f}[/{today_color}]"
            if has_today_data else "[dim]N/A[/dim]"
        )
        summary = (
            f"EUR Invested: [green]{total_invested_eur:,.2f}[/green]  |  "
            f"EUR Market Value: [green]{total_market_eur:,.2f}[/green]  |  "
            f"EUR P&L: [{eur_color}]{eur_sign}{total_pnl_eur:,.2f} "
            f"({eur_sign}{total_pct_eur:.2f}%)[/{eur_color}]{eur_note}  |  "
            f"EUR Market Today: {today_str}"
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
        today_color = "green" if total_today_eur >= 0 else "red"
        today_sign  = "+" if total_today_eur >= 0 else ""
        today_str   = (
            f"[{today_color}]{today_sign}{total_today_eur:,.2f}[/{today_color}]"
            if has_today_data else "[dim]N/A[/dim]"
        )
        summary = (
            f"Invested: [green]{total_invested:,.2f}[/green]  |  "
            f"Market Value: [green]{total_market:,.2f}[/green]  |  "
            f"P&L: [{color}]{sign}{total_pnl:,.2f} ({sign}{total_pct:.2f}%)[/{color}]  |  "
            f"EUR Market Today: {today_str}"
        )

    if missing_prices:
        summary += (
            f"\n[dim]{missing_prices} position(s) excluded from "
            f"Market Value / P&L (no price available)[/dim]"
        )
    if untracked_cost:
        summary += (
            f"\n[dim]{untracked_cost} position(s) without cost basis "
            f"(not tracked)[/dim]"
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
    avg_price = inst.get("avg_purchase_price")   # may be None
    curr      = inst.get("current_price")
    ccy       = (inst.get("currency") or "EUR").upper()
    has_cost  = avg_price is not None

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
    t.add_row("Avg Purchase Price",   f"{avg_price:,.2f}" if has_cost else "[dim]Not tracked[/dim]")
    t.add_row("Current Price",        _price_str(curr))

    if has_cost:
        invested = shares * avg_price
        t.add_row("Total Invested", f"{invested:,.2f}")
        if ccy != "EUR":
            invested_eur = forex.to_eur(invested, ccy)
            if invested_eur is not None:
                t.add_row("Total Invested (EUR)", f"{invested_eur:,.2f}")
    else:
        t.add_row("Total Invested", "[dim]Not tracked[/dim]")

    if curr is not None:
        mkt_val = shares * curr
        t.add_row("Market Value", f"{mkt_val:,.2f}")
        if ccy != "EUR":
            mkt_eur = forex.to_eur(mkt_val, ccy)
            if mkt_eur is not None:
                t.add_row("Market Value (EUR)", f"{mkt_eur:,.2f}")
        if has_cost:
            pnl = mkt_val - invested
            pct = (pnl / invested * 100) if invested else 0.0
            t.add_row("P&L", _pnl_markup(pnl, pct))
            if ccy != "EUR":
                pnl_eur = forex.to_eur(pnl, ccy)
                if pnl_eur is not None:
                    t.add_row("P&L (EUR)", _pnl_markup(pnl_eur, pct))
        else:
            t.add_row("P&L", "[dim]Not tracked[/dim]")

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


# ---------------------------------------------------------------------------
# Elegant startup refresh with inline progress
# ---------------------------------------------------------------------------

def startup_refresh(
    instruments: List[Dict],
    refresh_fn: Callable[[str], bool],
    verbose: bool = False,
) -> int:
    """
    Refresh instruments with elegant two-line progress display.

    When *verbose* is True, shows animated "Refreshing [TIKR]…" /
    "Refreshed [TIKR] ✓" progress, overwriting in place.
    When *verbose* is False, runs silently.

    Returns the number of instruments successfully refreshed.
    """
    if not instruments:
        return 0

    if not verbose:
        ok_count = 0
        for inst in instruments:
            if refresh_fn(inst["ticker"]):
                ok_count += 1
        return ok_count

    total = len(instruments)
    ok_count = 0

    def _make_display(idx: int, ticker: str, state: str) -> Text:
        """Build a two-line Text renderable for the current progress."""
        t = Text()
        # Line 1: overall progress bar
        filled = int((idx / total) * 20)
        bar = "━" * filled + "╺" + "─" * (19 - filled)
        t.append("  ")
        t.append(bar, style="cyan")
        t.append(f"  {idx}/{total}\n", style="dim")
        # Line 2: current ticker status
        if state == "refreshing":
            t.append("  ⟳ ", style="bold cyan")
            t.append("Refreshing ", style="cyan")
            t.append(f"[{ticker}]", style="bold white")
            t.append(" …", style="dim")
        elif state == "done":
            t.append("  ✓ ", style="bold green")
            t.append("Refreshed  ", style="green")
            t.append(f"[{ticker}]", style="bold white")
        elif state == "fail":
            t.append("  ✗ ", style="bold red")
            t.append("Failed     ", style="red")
            t.append(f"[{ticker}]", style="bold white")
        return t

    with Live(_make_display(0, instruments[0]["ticker"], "refreshing"),
              console=console, refresh_per_second=12, transient=True) as live:
        for idx, inst in enumerate(instruments):
            ticker = inst["ticker"]
            live.update(_make_display(idx, ticker, "refreshing"))
            try:
                success = refresh_fn(ticker)
            except Exception:
                success = False
            if success:
                ok_count += 1
                live.update(_make_display(idx + 1, ticker, "done"))
            else:
                live.update(_make_display(idx + 1, ticker, "fail"))
            # Brief pause so the user can see the "done" state before next
            time.sleep(0.15)

    # Final summary line (persisted after Live clears)
    console.print(
        f"  [green]✓[/green] Refreshed {ok_count}/{total} instruments"
    )
    _flush_console()
    return ok_count


# ---------------------------------------------------------------------------
# Clear-cache safety confirmation (used by interactive + CLI modes)
# ---------------------------------------------------------------------------

def confirm_clear_cache(instruments: List[Dict]) -> bool:
    """
    Show a blinking red warning listing all portfolio instruments, ask the user
    to press Enter to continue, then require explicit confirmation (default is
    Abort).  Returns True only if the user confirms.
    """
    if not instruments:
        console.print("[yellow]Portfolio is empty — clearing cache.[/yellow]")
        _flush_console()
        return True  # no positions to list, safe to proceed

    # ── Blinking red warning ─────────────────────────────────────────────
    console.print()
    console.print(
        "[blink bold red]⚠  WARNING: YOU ARE ABOUT TO WIPE ALL CACHED DATA  ⚠[/blink bold red]"
    )
    console.print()
    console.print(
        "[bold red]The following instruments will have their cached live data removed:[/bold red]"
    )
    for inst in instruments:
        ticker = inst.get("ticker", "?")
        name   = inst.get("name") or "—"
        console.print(f"  [red]•[/red]  {ticker:14s}  {name}")
    console.print()
    console.print(
        "[bold red]Cached prices, names, and market data will need to be "
        "re-fetched from Yahoo Finance.[/bold red]"
    )
    console.print()
    _flush_console()

    # ── Press Enter to continue (Esc or Ctrl-C cancels) ──────────────────
    try:
        input("[Press Enter to continue or Ctrl-C to cancel] ")
    except (KeyboardInterrupt, EOFError):
        console.print("\n[cyan]Aborted.[/cyan]")
        _flush_console()
        return False

    # ── Final confirmation — default is Abort ────────────────────────────
    console.print("\n[bold red]Confirm cache wipe?[/bold red]  (abort/continue, default: abort)")
    _flush_console()
    answer = input("> ").strip().lower()

    if answer != "continue":
        console.print("[cyan]Aborted — cache was NOT cleared.[/cyan]")
        _flush_console()
        return False

    return True
