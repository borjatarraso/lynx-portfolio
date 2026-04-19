"""
Logo loading helpers for Lynx Portfolio.

Provides paths to logo image files and an ASCII-art fallback for
terminal modes.
"""

import os

_PKG_DIR = os.path.dirname(os.path.abspath(__file__))
_IMG_DIR = os.path.join(os.path.dirname(_PKG_DIR), "img")


def _logo_path(filename: str) -> str:
    """Return the absolute path to a logo file, or '' if not found."""
    path = os.path.join(_IMG_DIR, filename)
    return path if os.path.isfile(path) else ""


def logo_small() -> str:
    """Path to the small logo (157x179) for About dialogs."""
    return _logo_path("logo_sm_green.png")


def logo_medium() -> str:
    """Path to the medium logo (267x317) for splash screens."""
    return _logo_path("logo_md_green.png")


def logo_quarter() -> str:
    """Path to the tiny logo (39x44) for toolbar icons."""
    return _logo_path("logo_sm_quarter_green.png")


# ---------------------------------------------------------------------------
# ASCII-art logo for terminal modes — loaded from img/logo_ascii.txt
# ---------------------------------------------------------------------------

_ASCII_FILE = os.path.join(_IMG_DIR, "logo_ascii.txt")


def load_logo_ascii() -> str:
    """Load the ASCII logo from img/logo_ascii.txt with green ANSI colouring."""
    try:
        with open(_ASCII_FILE) as f:
            text = f.read()
        return f"\033[32m{text}\033[0m"
    except OSError:
        return ""


# Keep a module-level constant for backward compatibility
LOGO_ASCII = load_logo_ascii()


def load_logo_ascii_rich() -> str:
    """Load the ASCII logo wrapped in Rich [green] markup (for TUI/Rich)."""
    try:
        with open(_ASCII_FILE) as f:
            text = f.read()
        return f"[green]{text}[/green]"
    except OSError:
        return ""
