"""
Interactive REPL mode for Lynx Portfolio.
"""

import sys
from typing import Optional, List, Dict

from rich.prompt import Prompt, Confirm
from rich.table import Table
from rich import box

from . import database, cache, display
from .operations import add_instrument, refresh_instrument, refresh_all

# ---------------------------------------------------------------------------
# In-session readline history (↑/↓ arrow navigation).
# readline is imported for its side-effect: it hooks into Python's input()
# and enables history navigation automatically.  No history file is written,
# so nothing survives after the process exits.
# ---------------------------------------------------------------------------
try:
    import readline as _rl
    _rl.set_history_length(500)
    # Emacs editing mode: ← / → move within the input line, ↑ / ↓ navigate
    # history.  The cursor can never move past the prompt boundary — readline
    # manages the input buffer independently from the prompt string.
    _rl.parse_and_bind("set editing-mode emacs")
    # Disable horizontal scroll: if the line is longer than the terminal it
    # wraps to the next screen row instead of scrolling the prompt away.
    _rl.parse_and_bind("set horizontal-scroll-mode off")
    _HAS_READLINE = True
except ImportError:           # Windows without pyreadline
    _HAS_READLINE = False

# ANSI bold-cyan matches the Rich [bold cyan] style used elsewhere.
# \001 / \002 are readline's RL_PROMPT_START_IGNORE / RL_PROMPT_END_IGNORE
# markers. Without them readline miscounts the visible width of the prompt
# and arrow-key navigation corrupts the display.
_REPL_PROMPT = "\n\001\033[1;36m\002lynx>\001\033[0m\002 "


def _read_command() -> str:
    """Read one REPL line with readline history support (↑/↓ arrows)."""
    # Flush stdout so any pending Rich output (ANSI codes, tables) is fully
    # written before readline takes control of the terminal.  Without this,
    # residual ANSI state from Rich can confuse readline's cursor tracking.
    sys.stdout.flush()
    return input(_REPL_PROMPT).strip()


_HELP = """
[bold cyan]Commands[/bold cyan]

  [bold]list[/bold]  /  [bold]ls[/bold]                List all portfolio positions
  [bold]add[/bold]                        Add a new instrument (guided prompt)
  [bold]show[/bold]   <ticker>            Show detailed view for an instrument
  [bold]update[/bold] <ticker>            Update shares / average price
  [bold]delete[/bold] <ticker>            Remove an instrument from the portfolio
  [bold]refresh[/bold]                    Refresh live data for all instruments
  [bold]refresh[/bold] <ticker>           Refresh live data for one instrument
  [bold]import[/bold] <file.json>         Bulk-add instruments from a JSON file
  [bold]clear-cache[/bold]               Wipe all cached data
  [bold]markets[/bold] <ticker or ISIN>  List all exchanges where an instrument trades
  [bold]config[/bold]                     Show or update configuration
  [bold]help[/bold]                       Show this message
  [bold]quit[/bold]  /  [bold]exit[/bold]  /  [bold]q[/bold]    Exit
"""


def run() -> None:
    display.console.print(
        "\n[bold cyan]Lynx Portfolio Manager[/bold cyan]  —  Interactive Mode\n"
        "Type [bold]help[/bold] for available commands or [bold]quit[/bold] to exit.\n"
    )

    while True:
        try:
            raw = _read_command()
        except (KeyboardInterrupt, EOFError):
            display.console.print("\n[cyan]Goodbye![/cyan]")
            break

        if not raw:
            continue

        parts = raw.split(None, 1)
        cmd   = parts[0].lower()
        arg   = parts[1].strip() if len(parts) > 1 else ""

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

        elif cmd == "import":
            if not arg:
                display.err("Usage: import <file.json>")
            else:
                _cmd_import(arg)

        elif cmd == "clear-cache":
            instruments = database.get_all_instruments()
            if display.confirm_clear_cache(instruments):
                n = cache.delete()
                display.ok(f"Cache cleared ({n} entries removed).")

        elif cmd == "markets":
            if not arg:
                display.err("Usage: markets <ticker or ISIN>")
            else:
                _cmd_markets(arg)

        elif cmd == "config":
            from . import config as cfg
            cfg.run_configure(display.console)

        else:
            display.warn(f"Unknown command '{cmd}'. Type 'help' for available commands.")


# ---------------------------------------------------------------------------
# Market selection prompt (used as market_selector callback in add_instrument)
# ---------------------------------------------------------------------------

def _prompt_market_selection(markets: List[Dict]) -> Optional[Dict]:
    """Show a table of available markets and ask the user to pick one."""
    t = Table(
        title="Available Markets",
        box=box.ROUNDED,
        header_style="bold cyan",
        show_lines=False,
    )
    t.add_column("#",        width=4,  justify="right")
    t.add_column("Symbol",   width=16)
    t.add_column("Exchange", width=32)
    t.add_column("Suffix",   width=8)
    t.add_column("Type",     width=12)

    for i, m in enumerate(markets, 1):
        t.add_row(
            str(i),
            m["symbol"],
            m["exchange_display"] or m["exchange_code"],
            m["suffix"] or "(US)",
            m["quote_type"],
        )

    display.console.print(t)

    choices = [str(i) for i in range(1, len(markets) + 1)] + ["0"]
    answer  = Prompt.ask(
        "Select market number  [dim][0 to cancel][/dim]",
        choices=choices,
        show_choices=False,
    )
    if answer == "0":
        return None
    return markets[int(answer) - 1]


# ---------------------------------------------------------------------------
# Sub-command helpers
# ---------------------------------------------------------------------------

def _cmd_add() -> None:
    display.console.print("\n[bold]Add New Instrument[/bold]")

    ticker = Prompt.ask(
        "Ticker  [dim](e.g. AAPL, NESN.SW, VWCE.DE — include exchange suffix if known)[/dim]\n"
        "  [dim][Enter to skip if using ISIN][/dim]",
        default="",
    ).strip()
    isin = Prompt.ask(
        "ISIN  [dim][Enter to skip][/dim]", default=""
    ).strip()

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
        market_selector=_prompt_market_selection,
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

    raw_shares = Prompt.ask(
        "New shares  [dim][Enter to keep][/dim]", default=""
    ).strip()
    raw_price  = Prompt.ask(
        "New avg price  [dim][Enter to keep][/dim]", default=""
    ).strip()

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
        if database.update_instrument(ticker, **kwargs):
            display.ok(f"Updated {ticker}.")
        else:
            display.err(f"'{ticker}' not found.")
    else:
        display.info("Nothing changed.")


def _cmd_import(filepath: str) -> None:
    """Bulk-add instruments from a JSON file."""
    from .cli import _import_from_json
    _import_from_json(filepath)


def _cmd_markets(query: str) -> None:
    """Show all exchanges where a ticker/ISIN is listed."""
    from . import fetcher as f
    isin   = query if len(query) == 12 and query[:2].isalpha() else None
    ticker = query if not isin else None
    markets, _ = f.resolve_markets_for_input(ticker, isin)
    if not markets:
        display.warn(f"No markets found for '{query}'.")
        return
    _prompt_market_selection(markets)
