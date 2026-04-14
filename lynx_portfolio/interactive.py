"""
Interactive REPL mode for Lynx Portfolio.
"""

import sys
from typing import Optional, List, Dict

from rich.table import Table
from rich import box

from . import ABOUT_LINES
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
    _rl.parse_and_bind("set editing-mode emacs")
    _rl.parse_and_bind("set horizontal-scroll-mode off")
    _HAS_READLINE = True
except ImportError:           # Windows without pyreadline
    _HAS_READLINE = False

# \001 / \002 = readline's RL_PROMPT_START_IGNORE / RL_PROMPT_END_IGNORE.
_REPL_PROMPT = "\n\001\033[1;36m\002lynx>\001\033[0m\002 "


def _flush() -> None:
    sys.stdout.flush()


def _read_command() -> str:
    """Read one REPL line with readline history support."""
    _flush()
    return input(_REPL_PROMPT).strip()


def _ask(label: str, default: str = "") -> str:
    """
    Print *label* via Rich (supports markup), then read input on a
    separate line using a plain '> ' prompt.  This keeps the question
    text immune to backspace / arrow-key corruption because only the
    '> ' prompt line is editable — readline never touches the label.
    """
    _flush()
    display.console.print(label)
    _flush()
    suffix = f" [{default}]" if default else ""
    raw = input(f"  \001\033[36m\002>\001\033[0m\002{suffix} ").strip()
    return raw if raw else default


def _ask_float(label: str, required: bool = True) -> Optional[float]:
    """
    Ask for a numeric value.  When *required* is False, an empty answer
    returns None.  On invalid input returns the sentinel string 'INVALID'
    so callers can distinguish "empty = None" from "garbage".
    """
    raw = _ask(label, default="" if required else "")
    if not raw:
        return None
    try:
        return float(raw)
    except ValueError:
        return "INVALID"          # type: ignore[return-value]


def _confirm(label: str, default: bool = False) -> bool:
    """Yes/No confirmation using plain input (no Rich Prompt)."""
    _flush()
    hint = "[Y/n]" if default else "[y/N]"
    display.console.print(label)
    _flush()
    raw = input(f"  \001\033[36m\002>\001\033[0m\002 {hint} ").strip().lower()
    if not raw:
        return default
    return raw in ("y", "yes")


_HELP = """
[bold cyan]Commands[/bold cyan]

  [bold]list[/bold]  /  [bold]ls[/bold]                List all portfolio positions
  [bold]add[/bold]                        Add a new instrument (guided prompt, supports name search)
  [bold]show[/bold]   <ticker>            Show detailed view for an instrument
  [bold]show[/bold]   --name <query>      Search by name and show instrument detail
  [bold]update[/bold] <ticker>            Update shares / average price
  [bold]delete[/bold] <ticker>            Remove an instrument from the portfolio
  [bold]refresh[/bold]                    Refresh live data for all instruments
  [bold]refresh[/bold] <ticker>           Refresh live data for one instrument
  [bold]import[/bold] <file.json>         Bulk-add instruments from a JSON file
  [bold]clear-cache[/bold]               Wipe all cached data
  [bold]markets[/bold] <ticker or ISIN>  List all exchanges where an instrument trades
  [bold]config[/bold]                     Show or update configuration
  [bold]about[/bold]                      Show application information
  [bold]help[/bold]                       Show this message
  [bold]quit[/bold]  /  [bold]exit[/bold]  /  [bold]q[/bold]    Exit
"""


def _show_empty_portfolio_hint() -> None:
    """Show a hint when quitting with an empty portfolio."""
    instruments = database.get_all_instruments()
    if not instruments:
        display.console.print(
            "\n[yellow]Your portfolio is empty.[/yellow]  "
            "You can re-run the setup wizard at any time with "
            "[bold]lynx-portfolio -w[/bold] or [bold]lynx-portfolio --wizard[/bold].\n"
        )


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
            _show_empty_portfolio_hint()
            break

        if not raw:
            continue

        parts = raw.split(None, 1)
        cmd   = parts[0].lower()
        arg   = parts[1].strip() if len(parts) > 1 else ""

        if cmd in ("quit", "exit", "q"):
            display.console.print("[cyan]Goodbye![/cyan]")
            _show_empty_portfolio_hint()
            break

        elif cmd == "help":
            display.console.print(_HELP)

        elif cmd in ("list", "ls"):
            display.display_portfolio(database.get_all_instruments())

        elif cmd == "add":
            _cmd_add()

        elif cmd == "show":
            if not arg:
                display.err("Usage: show <ticker>  or  show --name <query>")
            elif arg.lower().startswith(("--name", "-n ")):
                # Name search mode — strip the flag prefix to get the query
                parts = arg.split(None, 1)
                query = parts[1].strip() if len(parts) > 1 else ""
                if query:
                    from . import fetcher
                    display.info(f"Searching for '{query}'…")
                    results = fetcher.search_by_name(query)
                    if not results:
                        display.err(f"No instruments found matching '{query}'.")
                    else:
                        ticker_found = _pick_from_search_results(results)
                        if ticker_found:
                            _cmd_show(ticker_found)
                else:
                    display.err("Usage: show --name <query>")
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

        elif cmd == "about":
            for line in ABOUT_LINES:
                display.console.print(line)

        elif cmd == "lynx":
            from .egg import run_terminal_egg
            run_terminal_egg()

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

    valid = set(str(i) for i in range(len(markets) + 1))
    while True:
        answer = _ask(
            f"Select market number [dim](1–{len(markets)}, 0 to cancel)[/dim]"
        )
        if answer in valid:
            break
        display.warn(f"Enter a number between 0 and {len(markets)}.")
    if answer == "0":
        return None
    return markets[int(answer) - 1]


# ---------------------------------------------------------------------------
# Sub-command helpers
# ---------------------------------------------------------------------------

def _pick_from_search_results(results: List[Dict]) -> Optional[str]:
    """Display search results and let the user pick one. Returns ticker or None."""
    display.console.print(f"\n[bold]Search results:[/bold]\n")
    for i, r in enumerate(results, 1):
        display.console.print(
            f"  [bold cyan]{i:>2}[/bold cyan]  "
            f"[bold]{r['symbol']:<14}[/bold]  "
            f"{(r['longname'] or r['shortname']):<35}  "
            f"[dim]{r['exchange_display']:<20}  "
            f"{r['quote_type']}[/dim]"
        )
    display.console.print(f"\n   [dim]0  Cancel[/dim]\n")

    while True:
        answer = _ask(f"Select [dim](1–{len(results)}, 0 to cancel)[/dim]")
        if not answer:
            continue
        try:
            idx = int(answer)
        except ValueError:
            display.warn(f"Enter a number between 0 and {len(results)}.")
            continue
        if idx == 0:
            return None
        if 1 <= idx <= len(results):
            return results[idx - 1]["symbol"]
        display.warn(f"Enter a number between 0 and {len(results)}.")


def _search_instrument_by_name() -> Optional[str]:
    """Search for instruments by name and let the user select one."""
    from . import fetcher
    name = _ask("Search by name [dim](e.g. 'Apple', 'Vanguard FTSE')[/dim]")
    if not name:
        return None
    display.info(f"Searching for '{name}'…")
    results = fetcher.search_by_name(name)
    if not results:
        display.err(f"No instruments found matching '{name}'.")
        return None
    return _pick_from_search_results(results)


def _cmd_add() -> None:
    display.console.print("\n[bold]Add New Instrument[/bold]")

    ticker = _ask(
        "Ticker [dim](e.g. AAPL, NESN.SW, VWCE.DE — include exchange suffix "
        "if known, Enter to skip if using ISIN or name search)[/dim]"
    )
    isin = None
    if not ticker:
        # Offer name search or ISIN
        display.console.print(
            "  [dim]No ticker given. You can search by name or provide an ISIN.[/dim]"
        )
        choice = _ask("Search by [bold]name[/bold] or enter [bold]ISIN[/bold]? [dim](name/isin)[/dim]")
        if choice and choice.lower().startswith("n"):
            ticker = _search_instrument_by_name()
            if not ticker:
                display.info("Cancelled.")
                return
        else:
            isin = _ask("ISIN [dim](Enter to cancel)[/dim]")

    if not ticker and not isin:
        display.err("You must provide at least a ticker, name search, or an ISIN.")
        return

    shares = _ask_float("Number of shares")
    if shares is None or shares == "INVALID":
        display.err("Invalid number. Operation cancelled.")
        return

    avg_price = _ask_float(
        "Average purchase price [dim](Enter to skip — position won't track cost/P&L)[/dim]",
        required=False,
    )
    if avg_price == "INVALID":
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
    if _confirm(f"Delete [bold]{ticker}[/bold] from portfolio?"):
        if database.delete_instrument(ticker):
            display.ok(f"Deleted {ticker}.")
        else:
            display.err("Deletion failed.")


def _cmd_update(ticker: str) -> None:
    inst = database.get_instrument(ticker)
    if not inst:
        display.err(f"'{ticker}' not found in portfolio.")
        return

    cur_price = inst.get("avg_purchase_price")
    price_disp = f"{cur_price:,.2f}" if cur_price is not None else "not tracked"
    display.console.print(
        f"\n[bold]Update {ticker}[/bold]  "
        f"(shares: {inst['shares']}, avg price: {price_disp})"
    )

    raw_shares = _ask("New shares [dim](Enter to keep)[/dim]")
    raw_price  = _ask("New avg price [dim](Enter to keep)[/dim]")

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
