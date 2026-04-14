"""
First-time setup wizard for Lynx Portfolio.

Guides the user through:
1. Choosing a database directory
2. Optionally enabling encryption
3. Optionally adding the first instrument
"""

import os
from typing import Dict, Any

from rich.prompt import Prompt, Confirm

from . import APP_NAME, VERSION
from . import config, database


_DEFAULT_DB_DIR = os.path.expanduser("~/.local/share/lynx")


def run_wizard(console) -> Dict[str, Any]:
    """Run the interactive first-time setup wizard.

    Returns the final config dict (already saved to disk).
    """
    cfg = config.load_config()

    console.print(
        f"\n[bold cyan]{'─' * 50}[/bold cyan]"
        f"\n[bold cyan]  {APP_NAME} {VERSION} — Setup Wizard[/bold cyan]"
        f"\n[bold cyan]{'─' * 50}[/bold cyan]\n"
    )

    # ── Step 1: Database location ────────────────────────────────────────
    cfg = _step_db_location(console, cfg)
    db_path = cfg["db_path"]

    # Set up and initialise the database so later steps can use it
    database.set_db_path(db_path)
    database.init_db()

    # ── Step 2: Encryption ───────────────────────────────────────────────
    cfg = _step_encryption(console, cfg, db_path)

    # ── Step 3: Default mode ─────────────────────────────────────────────
    cfg = _step_default_mode(console, cfg)

    # ── Step 4: First instrument ─────────────────────────────────────────
    _step_first_instrument(console)

    # ── Done ─────────────────────────────────────────────────────────────
    console.print(
        f"\n[bold green]{'─' * 50}[/bold green]"
        f"\n[bold green]  Setup complete![/bold green]"
        f"\n[bold green]{'─' * 50}[/bold green]\n"
    )
    console.print(f"  Database:  [cyan]{db_path}[/cyan]")
    encrypted = cfg.get("encrypted", False)
    console.print(f"  Encrypted: [cyan]{'yes' if encrypted else 'no'}[/cyan]")
    console.print(f"  Config:    [dim]{config.CONFIG_FILE}[/dim]\n")
    console.print(
        "  Run [bold]lynx[/bold] to start the interactive REPL,\n"
        "  or  [bold]lynx -tui[/bold] for the full-screen TUI,\n"
        "  or  [bold]lynx -x[/bold] for the graphical interface.\n"
    )
    return cfg


# ---------------------------------------------------------------------------
# Steps
# ---------------------------------------------------------------------------

def _step_db_location(console, cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Step 1 — choose where to store the database."""
    console.print("[bold]Step 1 · Database Location[/bold]\n")

    current_db = cfg.get("db_path")
    default_dir = (
        os.path.dirname(current_db) if current_db else _DEFAULT_DB_DIR
    )

    console.print(
        "  Choose a directory for the portfolio database.\n"
        f"  [dim]Default: {default_dir}[/dim]\n"
    )

    while True:
        db_dir = Prompt.ask(
            "  Database directory", default=default_dir,
        ).strip()
        db_dir = os.path.expanduser(os.path.expandvars(db_dir))

        db_path = os.path.join(db_dir, "portfolio.db")

        # Warn if a DB already exists
        if os.path.isfile(db_path) or os.path.isfile(db_path + ".enc"):
            console.print(
                f"\n  [yellow]⚠  A database already exists at {db_path}[/yellow]"
            )
            replace = Confirm.ask(
                "  Replace the existing database?", default=False,
            )
            if not replace:
                console.print("  Please choose a different directory.\n")
                continue

        try:
            os.makedirs(db_dir, exist_ok=True)
        except OSError as exc:
            console.print(f"  [red]Cannot create directory: {exc}[/red]\n")
            continue

        break

    cfg["db_path"] = db_path
    config.save_config(cfg)
    console.print(f"\n  [green]✓[/green] Database path set to [cyan]{db_path}[/cyan]\n")
    return cfg


def _step_encryption(
    console, cfg: Dict[str, Any], db_path: str,
) -> Dict[str, Any]:
    """Step 2 — optionally encrypt the database."""
    console.print("[bold]Step 2 · Encryption[/bold]\n")
    console.print(
        "  You can encrypt your portfolio database with a password.\n"
        "  [dim]This protects your investment data if the device is lost or shared.[/dim]\n"
    )

    use_vault = Confirm.ask("  Enable encryption?", default=False)
    if not use_vault:
        console.print("  [dim]Encryption skipped.[/dim]\n")
        return cfg

    from .vault import prompt_password, VaultSession

    console.print(
        "\n  [dim]Press * while typing to toggle password visibility.[/dim]\n"
    )
    password = prompt_password(confirm=True)

    from .backup import create_backup
    create_backup(db_path)

    VaultSession.setup_encryption(db_path, password)
    cfg["encrypted"] = True
    config.save_config(cfg)

    console.print(f"\n  [green]✓[/green] Database encrypted.\n")
    return cfg


def _step_default_mode(
    console, cfg: Dict[str, Any],
) -> Dict[str, Any]:
    """Step 3 — choose the default interface mode."""
    console.print("[bold]Step 3 · Default Interface Mode[/bold]\n")
    console.print(
        "  Choose which interface launches by default when no mode flag is given.\n"
    )
    console.print("  [bold cyan]1[/bold cyan]  Console (non-interactive)")
    console.print("  [bold cyan]2[/bold cyan]  Interactive REPL")
    console.print("  [bold cyan]3[/bold cyan]  Textual UI (full-screen TUI)")
    console.print("  [bold cyan]4[/bold cyan]  Graphical Interface\n")

    choices = {"1": "console", "2": "interactive", "3": "tui", "4": "gui"}
    from .config import VALID_MODES

    current = cfg.get("default_mode", "interactive")
    default_num = {"console": "1", "interactive": "2", "tui": "3", "gui": "4"}.get(
        current, "2"
    )

    choice = Prompt.ask(
        f"  Default mode [dim](1-4)[/dim]", default=default_num,
    ).strip()

    mode = choices.get(choice, "interactive")
    cfg["default_mode"] = mode
    config.save_config(cfg)

    console.print(
        f"\n  [green]✓[/green] Default mode set to "
        f"[cyan]{VALID_MODES[mode]}[/cyan]\n"
    )
    return cfg


def _step_first_instrument(console) -> None:
    """Step 4 — optionally add the first instrument."""
    console.print("[bold]Step 4 · Add Your First Instrument[/bold]\n")

    add_now = Confirm.ask(
        "  Would you like to add a stock or ETF now?", default=True,
    )
    if not add_now:
        console.print("  [dim]You can add instruments later.[/dim]\n")
        return

    console.print()

    ticker = Prompt.ask("  Ticker (e.g. AAPL, NESN.SW, VWCE.DE)").strip()
    if not ticker:
        console.print("  [dim]Skipped — no ticker entered.[/dim]\n")
        return

    isin = Prompt.ask("  ISIN (optional, press Enter to skip)", default="").strip() or None

    while True:
        shares_str = Prompt.ask("  Number of shares").strip()
        try:
            shares = float(shares_str)
            if shares <= 0:
                raise ValueError
            break
        except ValueError:
            console.print("  [red]Please enter a positive number.[/red]")

    avg_price_str = Prompt.ask(
        "  Average purchase price (optional, press Enter to skip)",
        default="",
    ).strip()
    avg_price = None
    if avg_price_str:
        try:
            avg_price = float(avg_price_str)
        except ValueError:
            console.print("  [yellow]Invalid number — skipping average price.[/yellow]")

    from .operations import add_instrument

    console.print()
    ok = add_instrument(
        ticker=ticker,
        isin=isin,
        shares=shares,
        avg_purchase_price=avg_price,
    )
    if ok:
        console.print()
