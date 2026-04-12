"""
Interactive REPL mode for Lynx Portfolio.
"""

from typing import Optional

from rich.prompt import Prompt, Confirm

from . import database, cache, display
from .operations import add_instrument, refresh_instrument, refresh_all


_HELP = """
[bold cyan]Commands[/bold cyan]

  [bold]list[/bold]  /  [bold]ls[/bold]             List all portfolio positions
  [bold]add[/bold]                     Add a new instrument (guided prompt)
  [bold]show[/bold]   <ticker>         Show detailed view for an instrument
  [bold]update[/bold] <ticker>         Update shares / average price
  [bold]delete[/bold] <ticker>         Remove an instrument from the portfolio
  [bold]refresh[/bold]                 Refresh live data for all instruments
  [bold]refresh[/bold] <ticker>        Refresh live data for one instrument
  [bold]clear-cache[/bold]             Wipe all cached data
  [bold]help[/bold]                    Show this message
  [bold]quit[/bold]  /  [bold]exit[/bold]  /  [bold]q[/bold]   Exit
"""


def run() -> None:
    display.console.print(
        "\n[bold cyan]Lynx Portfolio Manager[/bold cyan]  —  Interactive Mode\n"
        "Type [bold]help[/bold] for available commands or [bold]quit[/bold] to exit.\n"
    )

    while True:
        try:
            raw = Prompt.ask("\n[bold cyan]lynx>[/bold cyan]").strip()
        except (KeyboardInterrupt, EOFError):
            display.console.print("\n[cyan]Goodbye![/cyan]")
            break

        if not raw:
            continue

        parts  = raw.split(None, 1)
        cmd    = parts[0].lower()
        arg    = parts[1].strip() if len(parts) > 1 else ""

        if cmd in ("quit", "exit", "q"):
            display.console.print("[cyan]Goodbye![/cyan]")
            break

        elif cmd == "help":
            display.console.print(_HELP)

        elif cmd in ("list", "ls"):
            display.display_portfolio(database.get_all_instruments())

        elif cmd == "add":
            _cmd_add()

        elif cmd == "show":
            if not arg:
                display.err("Usage: show <ticker>")
            else:
                _cmd_show(arg.upper())

        elif cmd == "delete":
            if not arg:
                display.err("Usage: delete <ticker>")
            else:
                _cmd_delete(arg.upper())

        elif cmd == "update":
            if not arg:
                display.err("Usage: update <ticker>")
            else:
                _cmd_update(arg.upper())

        elif cmd == "refresh":
            if arg:
                refresh_instrument(arg.upper())
            else:
                refresh_all()

        elif cmd == "clear-cache":
            n = cache.delete()
            display.ok(f"Cache cleared ({n} entries removed).")

        else:
            display.warn(f"Unknown command '{cmd}'. Type 'help' for available commands.")


# ---------- sub-command helpers ----------

def _cmd_add() -> None:
    display.console.print("\n[bold]Add New Instrument[/bold]")
    ticker = Prompt.ask("Ticker symbol (e.g. AAPL)  [dim][Enter to skip if using ISIN][/dim]", default="").strip()
    isin   = Prompt.ask("ISIN  [dim][Enter to skip][/dim]", default="").strip()

    if not ticker and not isin:
        display.err("You must provide at least a ticker or an ISIN.")
        return

    try:
        shares    = float(Prompt.ask("Number of shares"))
        avg_price = float(Prompt.ask("Average purchase price"))
    except ValueError:
        display.err("Invalid number. Operation cancelled.")
        return

    add_instrument(
        ticker or None,
        isin   or None,
        shares,
        avg_price,
    )


def _cmd_show(ticker: str) -> None:
    inst = database.get_instrument(ticker)
    if inst:
        display.display_instrument(inst)
    else:
        display.err(f"'{ticker}' not found in portfolio.")


def _cmd_delete(ticker: str) -> None:
    inst = database.get_instrument(ticker)
    if not inst:
        display.err(f"'{ticker}' not found in portfolio.")
        return
    if Confirm.ask(f"Delete [bold]{ticker}[/bold] from portfolio?", default=False):
        if database.delete_instrument(ticker):
            display.ok(f"Deleted {ticker}.")
        else:
            display.err("Deletion failed.")


def _cmd_update(ticker: str) -> None:
    inst = database.get_instrument(ticker)
    if not inst:
        display.err(f"'{ticker}' not found in portfolio.")
        return

    display.console.print(
        f"\n[bold]Update {ticker}[/bold]  "
        f"(shares: {inst['shares']}, avg price: {inst['avg_purchase_price']})"
    )

    raw_shares = Prompt.ask("New shares  [dim][Enter to keep][/dim]", default="").strip()
    raw_price  = Prompt.ask("New avg price  [dim][Enter to keep][/dim]", default="").strip()

    kwargs: dict = {}
    try:
        if raw_shares:
            kwargs["shares"] = float(raw_shares)
        if raw_price:
            kwargs["avg_purchase_price"] = float(raw_price)
    except ValueError:
        display.err("Invalid number.")
        return

    if kwargs:
        database.update_instrument(ticker, **kwargs)
        display.ok(f"Updated {ticker}.")
    else:
        display.info("Nothing changed.")
