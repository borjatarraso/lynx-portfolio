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
# ASCII-art logo for terminal modes (pre-rendered for consistency)
# ---------------------------------------------------------------------------

LOGO_ASCII = """\
\033[32m
               ▒▒▒
           ▒▒▒▒▓▓▒▒▒▒▒
    ▒▒▒▒▒▒▒▓▓▓▓▓▓▓▓▓▓▓▓▒▒▒▒▒▒
 ▒▒▒▒▒▓▓▓▓▓▓▓▓▓▓█▓▓▓▓▓▓▓▓▓▓▓▓▓▒▒
 ▒▒▓▓▓▓▓▒▒▒▓▓▒▓█▓██▒▒▓▓▓▓▓▓▓▓▓▓▒
 ▒▓▓▒▒▒▓▓▓▒▒▓▓▒██▓█▒░░▒▓▓▓▓▓▓▒▓▒
 ▒▒▓▒▓▓▒▒▓▓▒▒▓██▓▒▒░▒░░░▒▓▓▓▓▒▓▒
 ▒▒▓▒▓▓▓▒▒▓▓▓██░▓▓░░░░▒░░░▒▓▓▒▓▒
 ▒▒▓▓▓▓▓▓▓▒▓▓▒░░░▒▓▒░░▓█▓░░▒▓▓▒▒
 ▒▒▓▓▒▓▓▓▓▓▓█▓░▓▓▓▓▓▓▓░███░░░▒▓▒
  ▒▒▓▓▓▓▓▓▓███▓██░▒████▒▓█▒░░▒▓▒
   ▒▓▓▒▓▓▓▓▓█████▓█▓░▒██░█░░▒▓▒
   ▒▒▓▓▓▓▓▓▓▓▓▓▓▓▓▓▒░░▓░░░░▒▓▓▒
    ▒▒▒▓▓▓▓▓▓▓▓▒▓██▓▒▓▓▓▒▒▒▓▒▒
      ▒▒▓▓▓▒▒▓█▓▒▓██▓▒██▓▒▓▓▒
       ▒▒▒▓▓▓▒▒▒▒▒░░░▒▒▒▓▓▓▒
         ▒▒▒▓▓▓▒▒░░░▒▒▓▓▓▒▒
           ▒▒▒▓▓▓▓▓▓▓▓▓▒▒▒
              ▒▒▒▒▓▒▒▒▒
\033[0m"""
