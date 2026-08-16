"""Shared bulk-import loader for JSON files and SQLite portfolio databases.

The CLI, GUI, and TUI all expose an "Import" surface and used to keep
their own copy of the JSON parsing loop. With the SQLite-database import
added, that triplication became too easy to drift, so the parsing /
file-format detection lives here and every surface calls
:func:`load_instruments_from_file` to get a normalised list of
instrument dicts.

Each returned row has the JSON-import shape:

    {"ticker": str, "shares": float, "avg_price": float | None,
     "isin": str | None, "exchange": str | None}

so consumers can run their existing add-instrument loops unchanged.
"""

from __future__ import annotations

import json
import os
import sqlite3
from typing import Any, Dict, List, Optional, Tuple


__all__ = [
    "is_sqlite_file",
    "load_instruments_from_file",
    "SUPPORTED_EXTENSIONS",
]


SUPPORTED_EXTENSIONS: tuple[str, ...] = (
    ".json",
    ".db",
    ".sqlite",
    ".sqlite3",
)


def is_sqlite_file(filepath: str) -> bool:
    """Return True if *filepath* is a SQLite database (magic-byte sniff).

    A valid SQLite 3 file always begins with the 16-byte literal
    ``b"SQLite format 3\\x00"``. This sniff trumps the file extension so
    a renamed ``.bak`` or extension-less DB still imports cleanly.
    """
    try:
        with open(filepath, "rb") as f:
            header = f.read(16)
    except OSError:
        return False
    return header.startswith(b"SQLite format 3\x00")


def _load_from_json(filepath: str) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            payload = json.load(f)
    except FileNotFoundError:
        return [], f"File not found: {filepath}"
    except json.JSONDecodeError as exc:
        return [], f"Invalid JSON: {exc}"
    except OSError as exc:
        return [], f"Could not read '{filepath}': {exc}"

    if not isinstance(payload, list):
        return [], "JSON file must contain an array of instrument objects."

    rows: List[Dict[str, Any]] = []
    for entry in payload:
        if not isinstance(entry, dict):
            # Caller's loop will skip + count.
            rows.append({})
            continue
        rows.append({
            "ticker":    entry.get("ticker"),
            "shares":    entry.get("shares"),
            "avg_price": entry.get("avg_price"),
            "isin":      entry.get("isin"),
            "exchange":  entry.get("exchange"),
        })
    return rows, None


def _exchange_from_sqlite_row(row: sqlite3.Row,
                                cols: set[str]) -> Optional[str]:
    code = (row["exchange_code"] if "exchange_code" in cols else None) or ""
    if code:
        return str(code)
    disp = (row["exchange_display"] if "exchange_display" in cols else None) or ""
    if disp and "." in disp:
        return disp.rsplit(".", 1)[-1]
    return None


def _load_from_sqlite(filepath: str) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    abs_path = os.path.abspath(filepath)
    try:
        conn = sqlite3.connect(
            f"file:{abs_path}?mode=ro", uri=True, timeout=10,
        )
    except sqlite3.OperationalError as exc:
        return [], f"Could not open '{filepath}': {exc}"

    try:
        conn.row_factory = sqlite3.Row
        try:
            cur = conn.execute("SELECT * FROM portfolio")
        except sqlite3.OperationalError:
            return [], (f"'{filepath}' has no 'portfolio' table — is this "
                          "really a Lynx-Portfolio database?")
        db_rows = cur.fetchall()
    finally:
        try:
            conn.close()
        except Exception:
            pass

    if not db_rows:
        return [], None  # Empty source: caller treats as "nothing to import".

    cols = set(db_rows[0].keys())
    rows: List[Dict[str, Any]] = []
    for r in db_rows:
        rows.append({
            "ticker":    r["ticker"]             if "ticker" in cols             else None,
            "shares":    r["shares"]             if "shares" in cols             else None,
            "avg_price": r["avg_purchase_price"] if "avg_purchase_price" in cols else None,
            "isin":      (r["isin"]              if "isin" in cols               else None) or None,
            "exchange":  _exchange_from_sqlite_row(r, cols),
        })
    return rows, None


def load_instruments_from_file(
    filepath: str,
) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """Load *filepath* as a JSON or SQLite source.

    Returns ``(rows, error)`` where *rows* is a list of normalised dicts
    (see module docstring) and *error* is None on success or a
    user-readable message on failure. An empty list with ``error=None``
    means the source file parsed cleanly but contained no instruments.

    Detection priority: magic bytes first (``SQLite format 3``), then
    extension as a fallback.
    """
    if not filepath:
        return [], "Please select a file."
    if not os.path.exists(filepath):
        return [], f"File not found: {filepath}"

    ext = os.path.splitext(filepath)[1].lower()
    if is_sqlite_file(filepath) or ext in (".db", ".sqlite", ".sqlite3"):
        return _load_from_sqlite(filepath)
    return _load_from_json(filepath)
