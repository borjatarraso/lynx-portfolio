"""
CLI entry point: argument parsing, subcommand dispatch, auto-refresh thread.
"""

import sys
import threading
import time
from typing import List

from . import APP_NAME, VERSION
from . import database, cache, display
from .operations import add_instrument, refresh_instrument, refresh_all


# ---------------------------------------------------------------------------
# Argv pre-processing
# Argparse does not support multi-character short options like -ni, -dc, etc.
# We rewrite them to their long equivalents before parsing.
# ---------------------------------------------------------------------------

_SHORT_MAP = {
    "-ni":  "--non-interactive",
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
# Parser
# ---------------------------------------------------------------------------

def _build_parser():
    import argparse

    parser = argparse.ArgumentParser(
        prog="lynx",
        description=f"{APP_NAME} — Investment Portfolio Manager",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=r"""
examples:
  lynx -i                                          interactive mode
  lynx -ni add --ticker AAPL --shares 10 --avg-price 172.50
  lynx -ni add --isin US0231351067 --shares 5 --avg-price 3200
  lynx -ni list
  lynx -ni show --ticker AAPL
  lynx -ni update --ticker AAPL --shares 15
  lynx -ni delete --ticker AAPL
  lynx -ni refresh --ticker AAPL
  lynx -ni refresh
  lynx -rc                                         refresh all cache
  lynx -dc                                         delete all cache
  lynx -arc=300 -i                                 interactive + auto-refresh every 5 min
""",
    )

    parser.add_argument("-v", "--version", action="version", version=f"{APP_NAME} {VERSION}")

    # Mode
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("-i",  "--interactive",     action="store_true", help="Interactive mode")
    mode.add_argument("-ni", "--non-interactive",  action="store_true", help="Non-interactive (command) mode")

    # Cache control
    parser.add_argument("-dc", "--delete-cache",       action="store_true",
                        help="Delete all cached instrument data")
    parser.add_argument("-rc", "--refresh-cache",      action="store_true",
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
    p_add.add_argument("--ticker", "-t", help="Ticker symbol (e.g. AAPL)")
    p_add.add_argument("--isin",         help="ISIN code (e.g. US0378331005)")
    p_add.add_argument("--shares",  "-s", type=float, required=True, help="Number of shares held")
    p_add.add_argument("--avg-price", "-p", type=float, required=True,
                       dest="avg_price", help="Average purchase price per share")

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
    database.init_db()

    argv = _preprocess_argv(sys.argv[1:])
    parser = _build_parser()
    args   = parser.parse_args(argv)

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
    if args.interactive:
        from .interactive import run as run_interactive
        run_interactive()
        return

    # ── subcommands ───────────────────────────────────────────────────────
    if args.command == "add":
        add_instrument(
            ticker            = getattr(args, "ticker", None),
            isin              = getattr(args, "isin", None),
            shares            = args.shares,
            avg_purchase_price= args.avg_price,
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
