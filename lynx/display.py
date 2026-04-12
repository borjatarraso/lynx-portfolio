"""
Terminal display helpers using Rich.
"""

from typing import List, Dict, Optional

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import box

console = Console()


# ---------- formatters ----------

def _pnl_markup(pnl: float, pct: float) -> str:
    color = "green" if pnl >= 0 else "red"
    sign = "+" if pnl >= 0 else ""
    return f"[{color}]{sign}{pnl:,.2f} ({sign}{pct:.2f}%)[/{color}]"


def _price_str(value: Optional[float]) -> str:
    return f"{value:,.4f}" if value is not None else "N/A"


def _truncate(text: str, width: int) -> str:
    return text if len(text) <= width else text[: width - 3] + "..."


# ---------- portfolio table ----------

def display_portfolio(instruments: List[Dict]) -> None:
    if not instruments:
        console.print(
            "[yellow]Portfolio is empty. "
            "Add instruments with: lynx -ni add --ticker AAPL --shares 10 --avg-price 150[/yellow]"
        )
        return

    table = Table(
        title="[bold cyan]Lynx Portfolio[/bold cyan]",
        box=box.ROUNDED,
        header_style="bold cyan",
        show_lines=False,
    )

    table.add_column("Ticker",     style="bold white",  width=8,  no_wrap=True)
    table.add_column("ISIN",                            width=14, no_wrap=True)
    table.add_column("Name",                            width=28)
    table.add_column("Shares",     justify="right",     width=10)
    table.add_column("Avg Price",  justify="right",     width=11)
    table.add_column("Curr Price", justify="right",     width=11)
    table.add_column("CCY",                             width=5,  no_wrap=True)
    table.add_column("Mkt Value",  justify="right",     width=13)
    table.add_column("P&L",        justify="right",     width=22)
    table.add_column("Sector",                          width=18)

    total_invested = 0.0
    total_market = 0.0

    for inst in instruments:
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
            curr_str   = f"{curr:,.4f}"
            mkt_str    = f"{mkt_val:,.2f}"
            pnl_str    = _pnl_markup(pnl, pct)
        else:
            total_market += invested
            curr_str = "N/A"
            mkt_str  = "N/A"
            pnl_str  = "[dim]N/A[/dim]"

        table.add_row(
            inst.get("ticker") or "",
            inst.get("isin") or "—",
            _truncate(inst.get("name") or "—", 28),
            f"{shares:,.4f}",
            f"{avg_price:,.4f}",
            curr_str,
            inst.get("currency") or "—",
            mkt_str,
            pnl_str,
            _truncate(inst.get("sector") or "—", 18),
        )

    console.print(table)

    total_pnl = total_market - total_invested
    total_pct = (total_pnl / total_invested * 100) if total_invested else 0.0
    color     = "green" if total_pnl >= 0 else "red"
    sign      = "+" if total_pnl >= 0 else ""

    summary = (
        f"Invested: {total_invested:,.2f}  |  "
        f"Market Value: {total_market:,.2f}  |  "
        f"P&L: [{color}]{sign}{total_pnl:,.2f} ({sign}{total_pct:.2f}%)[/{color}]"
    )
    console.print(Panel(summary, title="Summary", border_style="cyan", padding=(0, 2)))


# ---------- single instrument ----------

def display_instrument(inst: Dict) -> None:
    ticker    = inst.get("ticker", "")
    shares    = inst.get("shares") or 0.0
    avg_price = inst.get("avg_purchase_price") or 0.0
    curr      = inst.get("current_price")
    invested  = shares * avg_price

    t = Table(show_header=False, box=box.SIMPLE, padding=(0, 1), expand=False)
    t.add_column("Field", style="bold cyan", width=22)
    t.add_column("Value", width=55)

    t.add_row("Ticker",               ticker)
    t.add_row("ISIN",                 inst.get("isin") or "—")
    t.add_row("Name",                 inst.get("name") or "—")
    t.add_row("Currency",             inst.get("currency") or "—")
    t.add_row("Sector",               inst.get("sector") or "—")
    t.add_row("Industry",             inst.get("industry") or "—")
    t.add_row("Shares",               f"{shares:,.4f}")
    t.add_row("Avg Purchase Price",   f"{avg_price:,.4f}")
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


# ---------- status helpers ----------

def ok(msg: str)   -> None: console.print(f"[green]✓[/green] {msg}")
def err(msg: str)  -> None: console.print(f"[red]✗[/red] {msg}")
def info(msg: str) -> None: console.print(f"[cyan]ℹ[/cyan] {msg}")
def warn(msg: str) -> None: console.print(f"[yellow]⚠[/yellow] {msg}")
