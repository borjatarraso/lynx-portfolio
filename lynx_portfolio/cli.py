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

from . import APP_NAME, VERSION, ABOUT_LINES
from . import database, cache, config, display
from .operations import (
    add_instrument, refresh_instrument, refresh_all,
    refresh_instrument_quiet,
)


# ---------------------------------------------------------------------------
# Argv pre-processing
# Argparse does not support multi-character short options like -ni, -dc, etc.
# We rewrite them to their long equivalents before parsing.
# ---------------------------------------------------------------------------

_SHORT_MAP = {
    "-ni":  "--console",           # legacy alias
    "-tui": "--textual-ui",
    "-dc":  "--delete-cache",
    "-rc":  "--refresh-cache",
    "-en":  "--encrypt",
    "-de":  "--disable-encryption",
    "-dm":  "--default-mode",
}


def _preprocess_argv(argv: List[str]) -> List[str]:
    result = []
    for arg in argv:
        # -arc=300  →  --auto-refresh-cache=300  (only digits after =)
        if arg.startswith("-arc=") and arg[5:].isdigit():
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
            "  Run [bold]lynx -w[/bold] (setup wizard) or "
            "[bold]lynx --configure[/bold] first."
        )
        return False

    database.set_db_path(db_path)
    display.console.print(
        "[bold green]✔  PRODUCTION MODE[/bold green]  —  "
        f"using persistent database at [cyan]{db_path}[/cyan]"
    )
    return True


def _setup_default_mode() -> str:
    """
    Set up the default run mode: production if configured and DB exists.
    Returns "production" if a configured DB (or vault) exists, "first_run"
    if not (caller should launch the wizard).
    """
    db_path = config.get_db_path()
    if not db_path:
        return "first_run"

    # Check if the actual database or vault files exist on disk
    from .vault import is_vault_present
    db_exists = os.path.isfile(db_path)
    vault_exists = is_vault_present(db_path)
    if not db_exists and not vault_exists:
        return "first_run"

    database.set_db_path(db_path)
    display.console.print(
        "[bold green]✔  PRODUCTION MODE[/bold green]  —  "
        f"using persistent database at [cyan]{db_path}[/cyan]"
    )
    return "production"


# ---------------------------------------------------------------------------
# JSON import
# ---------------------------------------------------------------------------

def _search_and_select(name: str) -> str | None:
    """Search for instruments by name and let the user select one.

    Returns the chosen ticker symbol, or None if cancelled / no results.
    """
    from . import fetcher
    from .validation import sanitise_search_query
    name, err = sanitise_search_query(name)
    if err:
        display.err(err)
        return None
    display.info(f"Searching for '{name}'…")
    try:
        results = fetcher.search_by_name(name)
    except Exception as exc:
        display.err(f"Search failed: {exc}")
        return None
    if not results:
        display.err(f"No instruments found matching '{name}'.")
        return None

    display.console.print(f"\n[bold]Search results for '{name}':[/bold]\n")
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
        sys.stdout.flush()
        try:
            answer = input("Select [1-" + str(len(results)) + "]: ").strip()
        except (EOFError, KeyboardInterrupt):
            return None
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
            "See 'lynx-portfolio -c import --help' for the expected format."
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

        if not ticker or shares is None:
            display.warn(
                f"  [{i}/{total}] Skipping entry — "
                f"'ticker' and 'shares' are required."
            )
            skipped += 1
            continue

        # Validate ticker format
        from .validation import validate_ticker, validate_shares, validate_price
        ticker_v, err = validate_ticker(str(ticker))
        if err:
            display.warn(f"  [{i}/{total}] Skipping — {err}")
            skipped += 1
            continue
        ticker = ticker_v

        shares_v, err = validate_shares(shares)
        if err:
            display.warn(f"  [{i}/{total}] Skipping '{ticker}' — {err}")
            skipped += 1
            continue
        shares = shares_v

        avg_price_v, err = validate_price(avg_price)
        if err:
            display.warn(f"  [{i}/{total}] Skipping '{ticker}' — {err}")
            skipped += 1
            continue
        avg_price = avg_price_v

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
        prog="lynx-portfolio",
        description=f"{APP_NAME} — Investment Portfolio Manager",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=r"""
configuration:
  lynx-portfolio --configure   set up the database directory
  config file location:        $XDG_CONFIG_HOME/lynx/config.json
                               (default: ~/.config/lynx/config.json)

run modes (default: production — wizard runs automatically on first use):
  --devel                      fresh empty DB every run, nothing persisted
  --production                 use the configured persistent database (explicit)

json import format (for 'import --file'):
  [
    {"ticker": "AAPL",    "shares": 10,   "avg_price": 150.00},
    {"ticker": "NESN.SW", "shares": 50,   "avg_price": 110.00, "isin": "CH0038863350"},
    {"ticker": "VWCE.DE", "shares": 23.5, "avg_price": 70.00,  "exchange": "DE"}
  ]
  required fields: ticker, shares, avg_price
  optional fields: isin, exchange

interface modes (default: interactive REPL):
  -c,  --console         non-interactive one-shot commands (scriptable)
  -i,  --interactive     REPL with typed commands (default)
  -tui, --textual-ui     full-screen TUI (arrow keys, Enter, Esc)
  -x,  --gui             graphical interface (tkinter window)

vault / encryption:
  lynx-portfolio --encrypt                encrypt the database (asks password 3x)
  lynx-portfolio                          auto-detects encrypted DB and prompts
  lynx-portfolio -d "pass" -c list        decrypt inline (console mode)
  lynx-portfolio --disable-encryption     remove encryption permanently
  lynx-portfolio --restore                restore from most recent backup
  lynx-portfolio -w                       first-time setup wizard

examples:
  lynx-portfolio                          start interactive REPL (default)
  lynx-portfolio -tui                     start full-screen TUI
  lynx-portfolio -x                       start graphical interface
  lynx-portfolio -c add --ticker NESN.SW --shares 50 --avg-price 110
  lynx-portfolio -c add --isin CH0038863350 --shares 50 --avg-price 110
  lynx-portfolio --import portfolio.json
  lynx-portfolio -c list
  lynx-portfolio -c show --ticker NESN.SW
  lynx-portfolio -c update --ticker AAPL --shares 15
  lynx-portfolio -c delete --ticker AAPL
  lynx-portfolio -rc
  lynx-portfolio -dc
""",
    )

    parser.add_argument("-v", "--version", action="version", version=f"{APP_NAME} {VERSION}")
    parser.add_argument("--verbose", action="store_true",
                        help="Show detailed refresh progress at startup")
    parser.add_argument("--enforce-refresh", action="store_true",
                        dest="enforce_refresh",
                        help="Force a full refresh of all instruments on startup, "
                             "even if already refreshed today")

    # Configuration ────────────────────────────────────────────────────────────
    parser.add_argument(
        "--configure", action="store_true",
        help="Set up or update Lynx configuration (database directory, etc.).",
    )
    parser.add_argument(
        "--default-mode", "-dm", dest="default_mode",
        choices=["console", "interactive", "tui", "gui"],
        metavar="MODE",
        help="Set the default interface mode "
             "(console, interactive, tui, gui). "
             "Saved to config for future sessions.",
    )

    # Run-mode (devel vs production) ─────────────────────────────────────────
    run_mode = parser.add_mutually_exclusive_group()
    run_mode.add_argument(
        "--devel", action="store_true", dest="devel_mode",
        help="Use a temporary empty database. Nothing is persisted.",
    )
    run_mode.add_argument(
        "--production", action="store_true", dest="production_mode",
        help="Use the configured persistent database (run --configure first).",
    )

    # Interface mode ────────────────────────────────────────────────────────
    imode = parser.add_mutually_exclusive_group()
    imode.add_argument("-c",  "--console",         action="store_true", help="Console (non-interactive) mode for scripting")
    imode.add_argument("-i",  "--interactive",      action="store_true", help="Interactive REPL mode (default)")
    imode.add_argument("-tui", "--textual-ui",       action="store_true", dest="textual_ui", help="Full-screen TUI mode (keyboard-driven)")
    imode.add_argument("-x",  "--gui",               action="store_true", help="Graphical interface mode (tkinter)")
    imode.add_argument("--api",                      action="store_true", help="Start the REST API server")

    # API options ──────────────────────────────────────────────────────────
    parser.add_argument("--port", type=int, default=5000,
                        help="Port for the API server (default: 5000)")

    # Bulk import ──────────────────────────────────────────────────────────────
    parser.add_argument(
        "--import", metavar="FILE", dest="import_file_flag",
        help="Bulk-add instruments from a JSON file (works without -c/-i/-tui)",
    )
    parser.add_argument(
        "--exchange", "-e", metavar="SUFFIX", dest="import_exchange_flag",
        help="Default exchange suffix for --import (e.g. SW, DE, V, TO); "
             "overridden per-entry by the 'exchange' field inside the JSON",
    )

    # Vault / encryption ──────────────────────────────────────────────────────
    vault_grp = parser.add_argument_group("vault / encryption")
    vault_grp.add_argument(
        "--encrypt", action="store_true",
        help="Encrypt the portfolio database with a password vault",
    )
    vault_grp.add_argument(
        "--disable-encryption", action="store_true",
        dest="disable_encryption",
        help="Decrypt and remove encryption from the database",
    )
    vault_grp.add_argument(
        "--decrypt", "-d", nargs="?", const=True, default=None,
        dest="decrypt", metavar="PASSWORD",
        help="Open encrypted vault (prompts for password if none given)",
    )
    vault_grp.add_argument(
        "--restore", action="store_true",
        help="Restore database from the most recent backup",
    )
    vault_grp.add_argument(
        "--wizard", "-w", action="store_true",
        help="Run the first-time setup wizard",
    )

    parser.add_argument("--egg", action="store_true",
                        dest="egg", help=argparse.SUPPRESS)

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
    p_add.add_argument("--name", "-n", dest="search_name",
                       help="Search by instrument name (e.g. 'Apple', 'Vanguard FTSE')")
    p_add.add_argument("--isin",   help="ISIN code (e.g. CH0038863350)")
    p_add.add_argument("--exchange", "-e",
                       help="Preferred exchange suffix (e.g. SW, DE, PA, AS, MI, L)")
    p_add.add_argument("--shares",    "-s", type=float, required=True, help="Number of shares held")
    p_add.add_argument("--avg-price", "-p", type=float,
                       dest="avg_price",
                       help="Average purchase price per share (omit to skip cost tracking)")

    # import
    p_imp = sub.add_parser(
        "import",
        help="Bulk-add instruments from a JSON file",
        description=(
            "Import instruments from a JSON file.  The file must contain an array "
            "of objects with at least 'ticker' and 'shares'.  "
            "Optional fields: 'avg_price', 'isin', 'exchange'."
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
    p_show.add_argument("--ticker", "-t",
                        help="Ticker of the instrument to show")
    p_show.add_argument("--name", "-n", dest="search_name",
                        help="Search by instrument name (e.g. 'Apple')")

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

    # about
    sub.add_parser("about", help="Show application information")

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

    if getattr(args, "egg", False):
        from .egg import run_console_egg
        run_console_egg()
        return

    # ── --default-mode: save preference (skipped in devel mode) ─────────
    if args.default_mode and args.devel_mode:
        display.warn("--default-mode is ignored in --devel mode (not persisted).")
    elif args.default_mode:
        config.set_default_mode(args.default_mode)
        from .config import VALID_MODES
        display.ok(
            f"Default mode set to: "
            f"[bold]{VALID_MODES[args.default_mode]}[/bold]"
        )
        # If no other mode/command given, continue with the newly set mode
        _has_other = (
            args.command or args.interactive or args.textual_ui
            or args.gui or getattr(args, "api", False)
            or getattr(args, "console", False)
        )
        if not _has_other and not args.configure and not args.wizard:
            # Apply the new default mode immediately
            if args.default_mode == "interactive":
                args.interactive = True
            elif args.default_mode == "tui":
                args.textual_ui = True
            elif args.default_mode == "gui":
                args.gui = True
            elif args.default_mode == "console":
                args.console = True

    # ── Apply saved default mode when no explicit mode given ─────────────
    _no_mode = not (
        args.command or args.interactive or args.textual_ui
        or args.gui or getattr(args, "api", False)
        or getattr(args, "console", False)
    )
    if _no_mode and not args.configure and not args.wizard:
        saved_mode = config.get_default_mode() or "interactive"
        if saved_mode == "interactive":
            args.interactive = True
        elif saved_mode == "tui":
            args.textual_ui = True
        elif saved_mode == "gui":
            args.gui = True
        elif saved_mode == "console":
            args.console = True

    # ── --wizard: run first-time setup and exit ─────────────────────────
    if args.wizard:
        if args.gui:
            from .gui import run_wizard_gui
            run_wizard_gui()
        else:
            from .wizard import run_wizard
            run_wizard(display.console)
        return

    # ── --configure: run wizard and exit ─────────────────────────────────
    if args.configure:
        config.run_configure(display.console)
        return

    # ── run-mode setup (must happen before init_db) ───────────────────────
    # LYNX_DB_PATH env-var override takes precedence (used by tests).
    _wizard_just_ran = False
    if os.environ.get("LYNX_DB_PATH"):
        database.set_db_path(os.environ["LYNX_DB_PATH"])
    elif args.devel_mode:
        _setup_devel_mode()
    elif args.production_mode:
        if not _setup_production_mode():
            return
    else:
        # No explicit flag → production if configured, wizard if first run
        result = _setup_default_mode()
        if result == "first_run":
            if args.gui:
                from .gui import run_wizard_gui
                cfg = run_wizard_gui()
            else:
                display.console.print(
                    "\n[bold cyan]Welcome to Lynx Portfolio![/bold cyan]\n"
                    "No database configured — launching the setup wizard.\n"
                )
                from .wizard import run_wizard
                cfg = run_wizard(display.console)
            if not cfg.get("db_path"):
                return
            database.set_db_path(cfg["db_path"])
            _wizard_just_ran = True

    # ── vault / encryption operations ────────────────────────────────────
    from .vault import is_vault_present, VaultSession, prompt_password
    from .backup import create_backup, restore_backup, has_backup
    from cryptography.fernet import InvalidToken

    db_path = database.get_db_path()
    _is_env_db = bool(os.environ.get("LYNX_DB_PATH"))
    _requires_production = not _is_env_db and args.devel_mode

    # Validate mutually exclusive vault operations
    _vault_ops = sum([
        bool(args.encrypt),
        bool(args.disable_encryption),
        bool(args.restore),
    ])
    if _vault_ops > 1:
        display.err("Only one of --encrypt, --disable-encryption, --restore can be used at a time.")
        return

    # --encrypt: set up encryption on existing plain DB
    if args.encrypt:
        if _requires_production:
            display.err("--encrypt cannot be used with --devel.")
            return
        if is_vault_present(db_path):
            display.err("Database is already encrypted.")
            return
        database.init_db()  # ensure the DB exists
        display.console.print(
            "\n[bold cyan]Set a password to encrypt your portfolio database.[/bold cyan]"
            "\n[dim]Press * to toggle password visibility.[/dim]\n"
        )
        password = prompt_password(confirm=True)
        create_backup(db_path)
        VaultSession.setup_encryption(db_path, password)
        config.set_encrypted(True)
        display.ok("Database encrypted successfully.")
        display.info(f"  Vault file: [cyan]{db_path}.enc[/cyan]")
        return

    # --disable-encryption: remove encryption
    if args.disable_encryption:
        if _requires_production:
            display.err("--disable-encryption cannot be used with --devel.")
            return
        if not is_vault_present(db_path):
            display.err("Database is not encrypted.")
            return
        display.console.print(
            "\n[bold cyan]Enter your password to remove encryption.[/bold cyan]\n"
        )
        password = prompt_password(confirm=False)
        create_backup(db_path, encrypted=True)
        try:
            VaultSession.disable_encryption(db_path, password)
        except InvalidToken:
            display.err("Wrong password.")
            return
        config.set_encrypted(False)
        display.ok("Encryption removed. Database is now plain.")
        return

    # --restore: restore from backup
    if args.restore:
        if _requires_production:
            display.err("--restore cannot be used with --devel.")
            return
        if restore_backup(db_path):
            display.ok("Database restored from backup.")
        else:
            display.err("No backup found to restore.")
        return

    # Auto-detect encrypted DB and open vault session
    _vault_session = None
    if is_vault_present(db_path) and not _wizard_just_ran:
        # Determine the password
        if args.decrypt is not None:
            if isinstance(args.decrypt, str) and args.decrypt is not True:
                password = args.decrypt
            else:
                display.console.print(
                    "\n[bold cyan]Encrypted portfolio detected. Enter your password.[/bold cyan]"
                    "\n[dim]Press * to toggle password visibility.[/dim]\n"
                )
                password = prompt_password(confirm=False)
        else:
            display.console.print(
                "\n[bold cyan]Encrypted portfolio detected. Enter your password.[/bold cyan]"
                "\n[dim]Press * to toggle password visibility.[/dim]\n"
            )
            password = prompt_password(confirm=False)

        create_backup(db_path, encrypted=True)
        _vault_session = VaultSession(db_path)
        try:
            working_path = _vault_session.open(password)
        except InvalidToken:
            display.err("Wrong password or corrupted vault.")
            return
        except FileNotFoundError as exc:
            display.err(str(exc))
            return
        except Exception as exc:
            display.err(f"Vault error: {exc}")
            return
        database.set_db_path(working_path)
        display.ok("Vault unlocked.")
    else:
        # Plain DB: create a backup before opening
        if os.path.isfile(db_path):
            create_backup(db_path)

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
    _has_mode = (
        args.command or args.interactive or args.textual_ui
        or args.gui or getattr(args, "api", False)
        or getattr(args, "console", False)
    )

    if args.delete_cache:
        instruments = database.get_all_instruments()
        if display.confirm_clear_cache(instruments):
            n = cache.delete()
            display.ok(f"Cache cleared ({n} entries removed).")
        if not _has_mode:
            return

    if args.refresh_cache:
        refresh_all()
        if not _has_mode:
            return

    if args.auto_refresh:
        _start_auto_refresh(args.auto_refresh)

    # ── --import flag (works standalone, no subcommand or mode required) ──
    if args.import_file_flag:
        _import_from_json(
            args.import_file_flag,
            preferred_exchange=args.import_exchange_flag,
        )
        # Only exit here if no other mode / subcommand was also requested.
        if not args.command and not args.interactive and not args.textual_ui and not args.gui and not args.console:
            return

    # ── mode ─────────────────────────────────────────────────────────────
    if getattr(args, "api", False):
        from .api import run_api_server
        display.info(f"Starting REST API on port {args.port}…")
        run_api_server(port=args.port)
        return

    # Smart refresh: only refresh if the DB has not been updated today,
    # unless --enforce-refresh forces it.
    # --enforce-refresh always shows progress (implies verbose for refresh).
    verbose = args.verbose or args.enforce_refresh
    _needs_refresh = args.enforce_refresh or not database.was_refreshed_today()

    # Determine if console (non-interactive) mode is active
    _console_mode = args.console or args.command

    if not _console_mode:
        instruments = database.get_all_instruments()
        if instruments and _needs_refresh:
            if args.gui:
                # GUI handles refresh inside its splash screen
                pass
            else:
                display.startup_refresh(
                    instruments, refresh_instrument_quiet, verbose=verbose,
                )

    if args.textual_ui:
        from .tui import LynxApp
        try:
            LynxApp().run()
        finally:
            if _vault_session:
                _vault_session.close()
        return

    if args.gui:
        from .gui import run_gui
        try:
            run_gui(needs_refresh=_needs_refresh, verbose=verbose)
        finally:
            if _vault_session:
                _vault_session.close()
        return

    if args.console:
        # Console (non-interactive) mode: dispatch subcommands
        try:
            _dispatch_subcommand(args, parser, _needs_refresh, verbose)
        finally:
            if _vault_session:
                _vault_session.close()
        return

    # ── Default: interactive REPL ─────────────────────────────────────────
    from .interactive import run as run_interactive
    try:
        run_interactive()
    finally:
        if _vault_session:
            _vault_session.close()


def _dispatch_subcommand(args, parser, _needs_refresh, verbose) -> None:
    if args.command == "add":
        ticker = getattr(args, "ticker", None)
        search_name = getattr(args, "search_name", None)
        if search_name and not ticker:
            ticker = _search_and_select(search_name)
            if not ticker:
                return
        add_instrument(
            ticker             = ticker,
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
        instruments = database.get_all_instruments()
        if instruments and _needs_refresh:
            display.startup_refresh(
                instruments, refresh_instrument_quiet, verbose=verbose,
            )
        display.display_portfolio(database.get_all_instruments())

    elif args.command == "show":
        from .validation import validate_ticker
        ticker = getattr(args, "ticker", None)
        search_name = getattr(args, "search_name", None)
        if search_name and not ticker:
            ticker = _search_and_select(search_name)
            if not ticker:
                return
        if not ticker:
            display.err("Provide --ticker or --name.")
            return
        ticker, err = validate_ticker(ticker)
        if err:
            display.err(err)
            return
        inst = database.get_instrument(ticker)
        if inst:
            if _needs_refresh:
                display.startup_refresh(
                    [inst], refresh_instrument_quiet, verbose=verbose,
                )
                inst = database.get_instrument(ticker)
            display.display_instrument(inst)
        else:
            display.err(f"'{ticker}' not found in portfolio.")

    elif args.command == "delete":
        from .validation import validate_ticker
        ticker, err = validate_ticker(args.ticker)
        if err:
            display.err(err)
            return
        if args.force:
            if database.delete_instrument(ticker):
                display.ok(f"Deleted {ticker}.")
            else:
                display.err(f"'{ticker}' not found.")
        else:
            inst = database.get_instrument(ticker)
            if not inst:
                display.err(f"'{ticker}' not found.")
                return
            display.console.print(f"Delete [bold]{ticker}[/bold] from portfolio? [y/N]")
            sys.stdout.flush()
            answer = input("> ").strip().lower()
            if answer in ("y", "yes"):
                database.delete_instrument(ticker)
                display.ok(f"Deleted {ticker}.")

    elif args.command == "update":
        from .validation import validate_ticker, validate_shares, validate_price
        ticker, err = validate_ticker(args.ticker)
        if err:
            display.err(err)
            return
        kwargs: dict = {}
        if args.shares is not None:
            val, verr = validate_shares(args.shares)
            if verr:
                display.err(verr)
                return
            kwargs["shares"] = val
        if args.avg_price is not None:
            val, verr = validate_price(args.avg_price)
            if verr:
                display.err(verr)
                return
            kwargs["avg_purchase_price"] = val
        if kwargs:
            if database.update_instrument(ticker, **kwargs):
                display.ok(f"Updated {ticker}.")
            else:
                display.err(f"'{ticker}' not found.")
        else:
            display.err("Nothing to update. Use --shares and/or --avg-price.")

    elif args.command == "refresh":
        from .validation import validate_ticker as _vt
        t = getattr(args, "ticker", None)
        if t:
            t, _err = _vt(t)
            if _err:
                display.err(_err)
                return
            refresh_instrument(t.upper())
        else:
            refresh_all()

    elif args.command == "about":
        from .logo import LOGO_ASCII
        sys.stdout.write(LOGO_ASCII)
        sys.stdout.flush()
        for line in ABOUT_LINES:
            display.console.print(line)

    else:
        # No subcommand in console mode → show help
        parser.print_help()
