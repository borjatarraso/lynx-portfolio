"""
SQLite database layer for Lynx Portfolio.
Stores portfolio positions and instrument cache.
"""

import os
import sqlite3
from datetime import datetime
from typing import Optional, List, Dict, Any

# DB_PATH is set at runtime by cli.py (via set_db_path) before init_db().
# In production mode it comes from the config file; in devel mode (--devel)
# it's a temporary file.  The env-var override is kept as a last-resort escape hatch.
DB_PATH: Optional[str] = os.environ.get("LYNX_DB_PATH")

ALLOWED_UPDATE_FIELDS = {
    "isin", "name", "shares", "avg_purchase_price",
    "currency", "sector", "industry", "description",
    "current_price", "regular_market_change",
    "exchange_code", "exchange_display",
    "quote_type", "updated_at",
}


def set_db_path(path: str) -> None:
    """Set the database path.  Must be called before init_db()."""
    global DB_PATH
    DB_PATH = path


def get_db_path() -> str:
    if DB_PATH is None:
        raise RuntimeError(
            "Database path not configured. Run: lynx --configure"
        )
    return DB_PATH


def _ensure_dir() -> None:
    parent = os.path.dirname(get_db_path())
    if parent:
        os.makedirs(parent, exist_ok=True)


def get_connection() -> sqlite3.Connection:
    _ensure_dir()
    conn = sqlite3.connect(
        get_db_path(), timeout=30, check_same_thread=False,
    )
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 30000")
    return conn


def init_db() -> None:
    conn = get_connection()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS portfolio (
            id                    INTEGER PRIMARY KEY AUTOINCREMENT,
            isin                  TEXT,
            ticker                TEXT NOT NULL,
            name                  TEXT,
            shares                REAL NOT NULL,
            avg_purchase_price    REAL,
            current_price         REAL,
            regular_market_change REAL,
            currency              TEXT,
            sector                TEXT,
            industry              TEXT,
            description           TEXT,
            exchange_code         TEXT,
            exchange_display      TEXT,
            quote_type            TEXT,
            created_at            TEXT DEFAULT (datetime('now')),
            updated_at            TEXT DEFAULT (datetime('now'))
        );

        CREATE UNIQUE INDEX IF NOT EXISTS idx_portfolio_ticker
            ON portfolio(ticker);

        CREATE TABLE IF NOT EXISTS instrument_cache (
            ticker                TEXT PRIMARY KEY,
            isin                  TEXT,
            name                  TEXT,
            price                 REAL,
            regular_market_change REAL,
            currency              TEXT,
            sector                TEXT,
            industry              TEXT,
            description           TEXT,
            exchange_code         TEXT,
            exchange_display      TEXT,
            cached_at             TEXT DEFAULT (datetime('now'))
        );
    """)
    # Migrations: add columns to existing tables if they are absent
    existing = {
        row[1]
        for row in conn.execute("PRAGMA table_info(portfolio)").fetchall()
    }
    for col, definition in [
        ("exchange_code",         "TEXT"),
        ("exchange_display",      "TEXT"),
        ("quote_type",            "TEXT"),
        ("regular_market_change", "REAL"),
    ]:
        if col not in existing:
            conn.execute(f"ALTER TABLE portfolio ADD COLUMN {col} {definition}")

    cache_existing = {
        row[1]
        for row in conn.execute("PRAGMA table_info(instrument_cache)").fetchall()
    }
    for col, definition in [
        ("exchange_code",         "TEXT"),
        ("exchange_display",      "TEXT"),
        ("regular_market_change", "REAL"),
    ]:
        if col not in cache_existing:
            conn.execute(
                f"ALTER TABLE instrument_cache ADD COLUMN {col} {definition}"
            )

    # Migration: allow NULL in avg_purchase_price for existing databases.
    # SQLite doesn't support ALTER COLUMN, so we rebuild the table if needed.
    for col_info in conn.execute("PRAGMA table_info(portfolio)").fetchall():
        if col_info[1] == "avg_purchase_price" and col_info[3] == 1:  # notnull=1
            conn.executescript("""
                CREATE TABLE portfolio_new (
                    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
                    isin                  TEXT,
                    ticker                TEXT NOT NULL,
                    name                  TEXT,
                    shares                REAL NOT NULL,
                    avg_purchase_price    REAL,
                    current_price         REAL,
                    regular_market_change REAL,
                    currency              TEXT,
                    sector                TEXT,
                    industry              TEXT,
                    description           TEXT,
                    exchange_code         TEXT,
                    exchange_display      TEXT,
                    quote_type            TEXT,
                    created_at            TEXT DEFAULT (datetime('now')),
                    updated_at            TEXT DEFAULT (datetime('now'))
                );
                INSERT INTO portfolio_new SELECT * FROM portfolio;
                DROP TABLE portfolio;
                ALTER TABLE portfolio_new RENAME TO portfolio;
                CREATE UNIQUE INDEX idx_portfolio_ticker ON portfolio(ticker);
            """)
            break

    conn.commit()
    conn.close()


def add_instrument(
    ticker: str,
    shares: float,
    avg_purchase_price: Optional[float] = None,
    isin: Optional[str] = None,
    name: Optional[str] = None,
    current_price: Optional[float] = None,
    regular_market_change: Optional[float] = None,
    currency: Optional[str] = None,
    sector: Optional[str] = None,
    industry: Optional[str] = None,
    description: Optional[str] = None,
    exchange_code: Optional[str] = None,
    exchange_display: Optional[str] = None,
    quote_type: Optional[str] = None,
) -> bool:
    """Returns True on success, False if ticker already exists."""
    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO portfolio
                (ticker, isin, name, shares, avg_purchase_price, current_price,
                 regular_market_change,
                 currency, sector, industry, description,
                 exchange_code, exchange_display, quote_type)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (ticker.upper(), isin, name, shares, avg_purchase_price,
             current_price, regular_market_change,
             currency, sector, industry, description,
             exchange_code, exchange_display, quote_type),
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()


def update_instrument(ticker: str, **kwargs: Any) -> bool:
    """Update arbitrary fields on an instrument row."""
    if not kwargs:
        return False
    invalid = set(kwargs) - ALLOWED_UPDATE_FIELDS
    if invalid:
        raise ValueError(f"Invalid field(s) for update: {invalid}")
    kwargs["updated_at"] = datetime.now().isoformat(timespec="seconds")
    conn = get_connection()
    try:
        fields = ", ".join(f"{k} = ?" for k in kwargs)
        values = list(kwargs.values()) + [ticker.upper()]
        conn.execute(f"UPDATE portfolio SET {fields} WHERE ticker = ?", values)
        conn.commit()
        return conn.total_changes > 0
    finally:
        conn.close()


def get_all_instruments() -> List[Dict]:
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM portfolio ORDER BY ticker"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def was_refreshed_today() -> bool:
    """Return True if any instrument was updated today (local date).

    The ``updated_at`` column may contain UTC timestamps (from the SQLite
    ``datetime('now')`` default) or local timestamps (written explicitly by
    ``update_instrument``).  We compare the raw date string against today's
    date string — after a real refresh, ``update_instrument`` writes local
    time so this comparison is accurate.
    """
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT MAX(updated_at) AS last_update FROM portfolio"
        ).fetchone()
        if not row or not row["last_update"]:
            return False
        # Compare the date portion (YYYY-MM-DD) of the most recent
        # updated_at against today's local date.
        last_date_str = row["last_update"][:10]   # "2026-04-14"
        today_str = datetime.now().strftime("%Y-%m-%d")
        return last_date_str == today_str
    finally:
        conn.close()


def get_instrument(ticker: str) -> Optional[Dict]:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM portfolio WHERE ticker = ?", (ticker.upper(),)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def delete_instrument(ticker: str) -> bool:
    conn = get_connection()
    try:
        conn.execute("DELETE FROM portfolio WHERE ticker = ?", (ticker.upper(),))
        conn.commit()
        return conn.total_changes > 0
    finally:
        conn.close()


def apply_cache_to_portfolio(ticker: str, data: Dict) -> None:
    """Push fetched data into the portfolio row."""
    kwargs: Dict[str, Any] = {
        k: data[k]
        for k in ("name", "current_price", "regular_market_change",
                  "currency", "sector", "industry", "description",
                  "exchange_code", "exchange_display", "quote_type", "isin")
        if data.get(k) is not None
    }
    if kwargs:
        update_instrument(ticker, **kwargs)


# ---------- cache table ----------

def cache_get(ticker: str) -> Optional[Dict]:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM instrument_cache WHERE ticker = ?", (ticker.upper(),)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def cache_put(ticker: str, data: Dict) -> None:
    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT OR REPLACE INTO instrument_cache
                (ticker, isin, name, price, regular_market_change,
                 currency, sector, industry,
                 description, exchange_code, exchange_display, cached_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                ticker.upper(),
                data.get("isin"),
                data.get("name"),
                data.get("current_price"),
                data.get("regular_market_change"),
                data.get("currency"),
                data.get("sector"),
                data.get("industry"),
                data.get("description"),
                data.get("exchange_code"),
                data.get("exchange_display"),
                datetime.now().isoformat(timespec="seconds"),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def cache_delete(ticker: Optional[str] = None) -> int:
    """Delete cache for one ticker or all. Returns rows deleted."""
    conn = get_connection()
    try:
        if ticker:
            conn.execute(
                "DELETE FROM instrument_cache WHERE ticker = ?", (ticker.upper(),)
            )
        else:
            conn.execute("DELETE FROM instrument_cache")
        conn.commit()
        return conn.total_changes
    finally:
        conn.close()


def checkpoint_wal() -> None:
    """Force a WAL checkpoint so all data is in the main DB file.

    Must be called before encrypting the database file, otherwise the
    WAL sidecar (which is a separate file) would not be included in the
    encrypted archive.
    """
    conn = get_connection()
    try:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    finally:
        conn.close()


def cache_age_seconds(ticker: str) -> Optional[float]:
    """Seconds since this ticker was cached, or None if not cached."""
    row = cache_get(ticker)
    if not row or not row.get("cached_at"):
        return None
    cached_at = datetime.fromisoformat(row["cached_at"])
    return (datetime.now() - cached_at).total_seconds()
