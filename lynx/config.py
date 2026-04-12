"""
Configuration management for Lynx Portfolio.

Stores user preferences (e.g. database path) in an XDG-compliant
config file:  $XDG_CONFIG_HOME/lynx/config.json  (default ~/.config/lynx/).

The config file is a small JSON pointer — actual data (the SQLite DB)
lives wherever the user chooses during --configure.
"""

import json
import os
from typing import Optional, Dict, Any

from rich.prompt import Prompt

# ---------------------------------------------------------------------------
# Config location
# ---------------------------------------------------------------------------

_XDG_CONFIG_HOME = os.environ.get(
    "XDG_CONFIG_HOME",
    os.path.expanduser("~/.config"),
)
CONFIG_DIR = os.path.join(_XDG_CONFIG_HOME, "lynx")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")

_DEFAULT_DB_DIR = os.path.expanduser("~/.local/share/lynx")

# ---------------------------------------------------------------------------
# Load / save
# ---------------------------------------------------------------------------

def _ensure_config_dir() -> None:
    os.makedirs(CONFIG_DIR, exist_ok=True)


def load_config() -> Dict[str, Any]:
    """Return the saved config dict, or {} if no config file exists."""
    if not os.path.isfile(CONFIG_FILE):
        return {}
    try:
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def save_config(cfg: Dict[str, Any]) -> None:
    _ensure_config_dir()
    with open(CONFIG_FILE, "w") as f:
        json.dump(cfg, f, indent=2)
        f.write("\n")


# ---------------------------------------------------------------------------
# Derived helpers
# ---------------------------------------------------------------------------

def get_db_path() -> Optional[str]:
    """Return the configured database path, or None if not yet configured."""
    cfg = load_config()
    return cfg.get("db_path")


def is_configured() -> bool:
    return get_db_path() is not None


# ---------------------------------------------------------------------------
# Interactive configuration
# ---------------------------------------------------------------------------

def run_configure(console) -> Dict[str, Any]:
    """
    Run the interactive configuration wizard.
    Returns the updated config dict (already saved to disk).
    """
    cfg = load_config()
    current_db = cfg.get("db_path")

    console.print("\n[bold cyan]Lynx Portfolio — Configuration[/bold cyan]\n")

    if current_db:
        console.print(f"  Current database path: [cyan]{current_db}[/cyan]")
    else:
        console.print("  No database path configured yet.")

    console.print(
        f"\n  Enter the directory where the portfolio database will be stored."
        f"\n  [dim]The SQLite file 'portfolio.db' will be created inside it.[/dim]"
        f"\n  [dim]Default: {_DEFAULT_DB_DIR}[/dim]\n"
    )

    db_dir = Prompt.ask(
        "Database directory",
        default=os.path.dirname(current_db) if current_db else _DEFAULT_DB_DIR,
    ).strip()

    # Expand ~ and env vars
    db_dir = os.path.expanduser(os.path.expandvars(db_dir))

    # Ensure the directory exists
    try:
        os.makedirs(db_dir, exist_ok=True)
    except OSError as exc:
        console.print(f"[red]Cannot create directory: {exc}[/red]")
        return cfg

    db_path = os.path.join(db_dir, "portfolio.db")
    cfg["db_path"] = db_path
    save_config(cfg)

    console.print(f"\n[green]✓[/green] Configuration saved.")
    console.print(f"  Database path: [cyan]{db_path}[/cyan]")
    console.print(f"  Config file:   [dim]{CONFIG_FILE}[/dim]\n")

    return cfg
