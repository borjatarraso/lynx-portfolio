"""
CLI entry point: argument parsing, subcommand dispatch, auto-refresh thread.
"""

import atexit
import json
import os
import sys
import tempfile
import threading
import time
from typing import List

from . import APP_NAME, VERSION
from . import database, cache, config, display
from .operations import add_instrument, refresh_instrument, refresh_all


# ---------------------------------------------------------------------------
# Argv pre-processing
# Argparse does not support multi-character short options like -ni, -dc, etc.
# We rewrite them to their long equivalents before parsing.
# ---------------------------------------------------------------------------

_SHORT_MAP = {
    "-ni":  "--non-interactive",
    "-tui": "--textual-ui",
    "-dc":  "--delete-cache",
    "-rc":  "--refresh-cache",
}


def _preprocess_argv(argv: List[str]) -> List[str]:
    result = []
    for arg in argv:
        # -arc=300  →  --auto-refresh-cache=300
        if arg.startswith("-arc="):
            result.append("--auto-refresh-cache=" + arg[5:])
        elif arg == "-arc":
            result.append("--auto-refresh-cache")
        elif arg in _SHORT_MAP:
            result.append(_SHORT_MAP[arg])
        else:
            result.append(arg)
    return result


# ---------------------------------------------------------------------------
# Run-mode setup  (devel / production)
# ---------------------------------------------------------------------------

def _setup_devel_mode() -> None:
    """
    Switch to a fresh temporary SQLite file for this process.
    The file is deleted automatically when the process exits.
    """
    fd, tmp_path = tempfile.mkstemp(suffix=".db", prefix="lynx_devel_")
    os.close(fd)
    atexit.register(_cleanup_devel_db, tmp_path)
    database.set_db_path(tmp_path)

    display.console.print(
        "[bold yellow]⚠  DEVEL MODE[/bold yellow]  —  "
        "using a temporary, empty database.  "
        "[dim]No data will be persisted after this session.[/dim]"
    )


def _cleanup_devel_db(path: str) -> None:
    for suffix in ("", "-shm", "-wal"):
        try:
            os.unlink(path + suffix)
        except FileNotFoundError:
            pass


def _setup_production_mode() -> bool:
    """
    Set up production mode using the configured database path.
    Returns True on success, False if configuration is missing.
    """
    db_path = config.get_db_path()
    if not db_path:
        display.err(
            "No database path configured.\n"
            "  Run [bold]lynx --configure[/bold] first to set up your data directory."
        )
        return False

    database.set_db_path(db_path)
    display.console.print(
        "[bold green]✔  PRODUCTION MODE[/bold green]  —  "
        f"using persistent database at [cyan]{db_path}[/cyan]"
    )
    return True


# ---------------------------------------------------------------------------
# JSON import
# ---------------------------------------------------------------------------

def _import_from_json(filepath: str, preferred_exchange: str = None) -> None:
    """Import instruments from a JSON file."""
    try:
        with open(filepath, "r") as f:
            instruments = json.load(f)
    except FileNotFoundError:
        display.err(f"File not found: {filepath}")
        return
    except json.JSONDecodeError as exc:
        display.err(f"Invalid JSON: {exc}")
        return

    if not isinstance(instruments, list):
        display.err(
            "JSON file must contain an array of instrument objects. "
            "See 'lynx -ni import --help' for the expected format."
        )
        return

    total    = len(instruments)
    added    = 0
    skipped  = 0

    for i, entry in enumerate(instruments, 1):
        if not isinstance(entry, dict):
            display.warn(f"  [{i}/{total}] Skipping non-object entry.")
            skipped += 1
            continue

        ticker    = entry.get("ticker")
        shares    = entry.get("shares")
        avg_price = entry.get("avg_price")

        if not ticker or shares is None or avg_price is None:
            display.warn(
                f"  [{i}/{total}] Skipping entry — "
                f"'ticker', 'shares', and 'avg_price' are required."
            )
            skipped += 1
            continue

        try:
            shares    = float(shares)
            avg_price = float(avg_price)
        except (TypeError, ValueError):
            display.warn(f"  [{i}/{total}] Skipping '{ticker}' — invalid number.")
            skipped += 1
            continue

        display.info(f"[{i}/{total}] Importing {ticker}…")
        ok = add_instrument(
            ticker             = ticker,
            isin               = entry.get("isin"),
            shares             = shares,
            avg_purchase_price = avg_price,
            preferred_exchange = entry.get("exchange") or preferred_exchange,
        )
        if ok:
            added += 1
        else:
            skipped += 1

    display.console.print()
    display.ok(f"Import complete: {added} added, {skipped} skipped (of {total} total).")


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

def _build_parser():
    import argparse

    parser = argparse.ArgumentParser(
        prog="lynx",
        description=f"{APP_NAME} — Investment Portfolio Manager",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=r"""
configuration:
  lynx --configure           set up the database directory (required before
                             first use in production mode)
  config file location:      $XDG_CONFIG_HOME/lynx/config.json
                             (default: ~/.config/lynx/config.json)

run modes (default: --devel-mode):
  --devel-mode               fresh empty DB every run, nothing persisted
  --production-mode          use the configured persistent database

json import format (for 'import --file'):
  [
    {"ticker": "AAPL",    "shares": 10,   "avg_price": 150.00},
    {"ticker": "NESN.SW", "shares": 50,   "avg_price": 110.00, "isin": "CH0038863350"},
    {"ticker": "VWCE.DE", "shares": 23.5, "avg_price": 70.00,  "exchange": "DE"}
  ]
  required fields: ticker, shares, avg_price
  optional fields: isin, exchange

interface modes:
  -i,  --interactive     REPL with typed commands
  -tui, --textual-ui     full-screen TUI (arrow keys, Enter, Esc)
  -ni, --non-interactive one-shot commands (scriptable)

examples:
  lynx --configure
  lynx --production-mode -tui
  lynx --production-mode -i
  lynx --production-mode -ni add --ticker NESN.SW --shares 50 --avg-price 110
  lynx --production-mode -ni add --isin CH0038863350 --shares 50 --avg-price 110
  lynx --production-mode -ni add --isin IE00B4L5Y983 -s 15 -p 70 --exchange AS
  lynx --production-mode -ni import --file portfolio.json
  lynx --production-mode -ni list
  lynx --production-mode -ni show --ticker NESN.SW
  lynx --production-mode -ni update --ticker AAPL --shares 15
  lynx --production-mode -ni delete --ticker AAPL
  lynx --production-mode -ni refresh
  lynx --production-mode -rc
  lynx --production-mode -dc
  lynx --production-mode -arc=300 -i
""",
    )

    parser.add_argument("-v", "--version", action="version", version=f"{APP_NAME} {VERSION}")

    # Configuration ────────────────────────────────────────────────────────────
    parser.add_argument(
        "--configure", action="store_true",
        help="Set up or update Lynx configuration (database directory, etc.).",
    )

    # Run-mode (devel vs production) ─────────────────────────────────────────
    run_mode = parser.add_mutually_exclusive_group()
    run_mode.add_argument(
        "--devel-mode", action="store_true", dest="devel_mode",
        help="Use a temporary empty database (default). Nothing is persisted.",
    )
    run_mode.add_argument(
        "--production-mode", action="store_true", dest="production_mode",
        help="Use the configured persistent database (run --configure first).",
    )

    # Interactive / non-interactive ──────────────────────────────────────────
    imode = parser.add_mutually_exclusive_group()
    imode.add_argument("-i",  "--interactive",     action="store_true", help="Interactive REPL mode")
    imode.add_argument("-ni", "--non-interactive",  action="store_true", help="Non-interactive (command) mode")
    imode.add_argument("-tui", "--textual-ui",       action="store_true", dest="textual_ui", help="Full-screen TUI mode (keyboard-driven)")

    # Cache control ───────────────────────────────────────────────────────────
    parser.add_argument("-dc", "--delete-cache",  action="store_true",
                        help="Delete all cached instrument data")
    parser.add_argument("-rc", "--refresh-cache", action="store_true",
                        help="Re-fetch live data for every portfolio instrument")
    parser.add_argument(
        "--auto-refresh-cache", "-arc",
        metavar="SECONDS", type=int, dest="auto_refresh",
        help="Auto-refresh cache in background every SECONDS seconds",
    )

    # Sub-commands ────────────────────────────────────────────────────────────
    sub = parser.add_subparsers(dest="command", metavar="<command>")

    # add
    p_add = sub.add_parser("add", help="Add an instrument to the portfolio")
    p_add.add_argument("--ticker", "-t",
                       help="Ticker — include suffix for precision (e.g. NESN.SW, VWCE.DE, AAPL)")
    p_add.add_argument("--isin",   help="ISIN code (e.g. CH0038863350)")
    p_add.add_argument("--exchange", "-e",
                       help="Preferred exchange suffix (e.g. SW, DE, PA, AS, MI, L)")
    p_add.add_argument("--shares",    "-s", type=float, required=True, help="Number of shares held")
    p_add.add_argument("--avg-price", "-p", type=float, required=True,
                       dest="avg_price", help="Average purchase price per share")

    # import
    p_imp = sub.add_parser(
        "import",
        help="Bulk-add instruments from a JSON file",
        description=(
            "Import instruments from a JSON file.  The file must contain an array "
            "of objects with at least 'ticker', 'shares', and 'avg_price'.  "
            "Optional fields: 'isin', 'exchange'."
        ),
    )
    p_imp.add_argument(
        "--file", "-f", required=True, dest="import_file",
        help="Path to the JSON file containing instruments to import",
    )
    p_imp.add_argument(
        "--exchange", "-e",
        help="Default exchange suffix for all instruments (overridden by per-entry 'exchange')",
    )

    # list
    sub.add_parser("list", help="List all portfolio positions")

    # show
    p_show = sub.add_parser("show", help="Show detailed info for one instrument")
    p_show.add_argument("--ticker", "-t", required=True)

    # delete
    p_del = sub.add_parser("delete", help="Remove an instrument from the portfolio")
    p_del.add_argument("--ticker", "-t", required=True)
    p_del.add_argument("--force",  "-f", action="store_true", help="Skip confirmation prompt")

    # update
    p_upd = sub.add_parser("update", help="Update shares or average price for an instrument")
    p_upd.add_argument("--ticker",    "-t", required=True)
    p_upd.add_argument("--shares",    "-s", type=float, help="New share count")
    p_upd.add_argument("--avg-price", "-p", type=float, dest="avg_price",
                       help="New average purchase price")

    # refresh
    p_ref = sub.add_parser("refresh", help="Refresh live data from Yahoo Finance")
    p_ref.add_argument("--ticker", "-t", help="Single ticker to refresh (omit for all)")

    return parser


# ---------------------------------------------------------------------------
# Auto-refresh background thread
# ---------------------------------------------------------------------------

def _auto_refresh_worker(interval: int) -> None:
    while True:
        time.sleep(interval)
        display.info(f"[auto-refresh] Refreshing portfolio data (interval={interval}s)…")
        refresh_all()


def _start_auto_refresh(interval: int) -> None:
    t = threading.Thread(target=_auto_refresh_worker, args=(interval,), daemon=True)
    t.start()
    display.info(f"Auto-refresh enabled every {interval}s.")


# ---------------------------------------------------------------------------
# Main entry
# ---------------------------------------------------------------------------

def run() -> None:
    argv   = _preprocess_argv(sys.argv[1:])
    parser = _build_parser()
    args   = parser.parse_args(argv)

    # ── --configure: run wizard and exit ─────────────────────────────────
    if args.configure:
        config.run_configure(display.console)
        return

    # ── run-mode setup (must happen before init_db) ───────────────────────
    # Default to devel-mode when neither flag is given.
    if args.production_mode:
        if not _setup_production_mode():
            return
    else:
        # --devel-mode or no flag → devel
        _setup_devel_mode()

    database.init_db()

    # ── forex: fetch conversion rates once at session start ───────────────
    from . import forex
    _instruments_for_forex = database.get_all_instruments()
    _forex_ccys = {
        (inst.get("currency") or "EUR").upper()
        for inst in _instruments_for_forex
    }
    if _forex_ccys - {"EUR"}:
        forex.fetch_session_rates(_forex_ccys)

    # ── global cache flags ────────────────────────────────────────────────
    if args.delete_cache:
        n = cache.delete()
        display.ok(f"Cache cleared ({n} entries removed).")
        if not args.command and not args.interactive:
            return

    if args.refresh_cache:
        refresh_all()
        if not args.command and not args.interactive:
            return

    if args.auto_refresh:
        _start_auto_refresh(args.auto_refresh)

    # ── mode ─────────────────────────────────────────────────────────────
    if args.textual_ui:
        from .tui import LynxApp
        LynxApp().run()
        return

    if args.interactive:
        from .interactive import run as run_interactive
        run_interactive()
        return

    # ── subcommands ───────────────────────────────────────────────────────
    if args.command == "add":
        add_instrument(
            ticker             = getattr(args, "ticker", None),
            isin               = getattr(args, "isin", None),
            shares             = args.shares,
            avg_purchase_price = args.avg_price,
            preferred_exchange = getattr(args, "exchange", None),
        )

    elif args.command == "import":
        _import_from_json(
            args.import_file,
            preferred_exchange=getattr(args, "exchange", None),
        )

    elif args.command == "list":
        display.display_portfolio(database.get_all_instruments())

    elif args.command == "show":
        inst = database.get_instrument(args.ticker.upper())
        if inst:
            display.display_instrument(inst)
        else:
            display.err(f"'{args.ticker.upper()}' not found in portfolio.")

    elif args.command == "delete":
        ticker = args.ticker.upper()
        if args.force:
            if database.delete_instrument(ticker):
                display.ok(f"Deleted {ticker}.")
            else:
                display.err(f"'{ticker}' not found.")
        else:
            from rich.prompt import Confirm
            inst = database.get_instrument(ticker)
            if not inst:
                display.err(f"'{ticker}' not found.")
                return
            if Confirm.ask(f"Delete [bold]{ticker}[/bold] from portfolio?", default=False):
                database.delete_instrument(ticker)
                display.ok(f"Deleted {ticker}.")

    elif args.command == "update":
        ticker = args.ticker.upper()
        kwargs: dict = {}
        if args.shares    is not None: kwargs["shares"]             = args.shares
        if args.avg_price is not None: kwargs["avg_purchase_price"] = args.avg_price
        if kwargs:
            if database.update_instrument(ticker, **kwargs):
                display.ok(f"Updated {ticker}.")
            else:
                display.err(f"'{ticker}' not found.")
        else:
            display.err("Nothing to update. Use --shares and/or --avg-price.")

    elif args.command == "refresh":
        t = getattr(args, "ticker", None)
        if t:
            refresh_instrument(t.upper())
        else:
            refresh_all()

    else:
        # No subcommand, no mode flag → show help
        parser.print_help()
