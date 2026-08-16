"""Tests for the bulk import dispatcher (_import_from_file) and the
shared loader (lynx_portfolio.imports.load_instruments_from_file) used
by the GUI and TUI surfaces.

Covers:
- File-type detection by magic bytes (a SQLite file is detected even
  without a .db extension; a JSON file is detected even without .json)
- SQLite import reads the 'portfolio' table and invokes add_instrument
  with the right kwargs (ticker, isin, shares, avg_price, exchange)
- Edge cases: missing table, empty DB, missing required columns,
  per-row override of preferred_exchange
- Shared loader returns the JSON-shaped dict for both source types
"""

from __future__ import annotations

import json
import os
import sqlite3
import tempfile
from typing import List

import pytest

from lynx_portfolio import cli
from lynx_portfolio import imports as imports_mod


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

@pytest.fixture
def tmpdir_path():
    with tempfile.TemporaryDirectory(prefix="lynx_imp_") as d:
        yield d


def _make_source_db(path: str, rows: list[dict],
                     *, include_exchange_cols: bool = True) -> None:
    """Create a small SQLite file mirroring the portfolio schema."""
    extra = (
        ", exchange_code TEXT, exchange_display TEXT"
        if include_exchange_cols else ""
    )
    conn = sqlite3.connect(path)
    try:
        conn.execute(
            f"CREATE TABLE portfolio ("
            f" id INTEGER PRIMARY KEY,"
            f" ticker TEXT NOT NULL,"
            f" isin TEXT,"
            f" shares REAL NOT NULL,"
            f" avg_purchase_price REAL"
            f"{extra}"
            f")"
        )
        for r in rows:
            cols = ", ".join(r.keys())
            placeholders = ", ".join("?" for _ in r)
            conn.execute(
                f"INSERT INTO portfolio ({cols}) VALUES ({placeholders})",
                tuple(r.values()),
            )
        conn.commit()
    finally:
        conn.close()


@pytest.fixture
def capture_add_calls(monkeypatch):
    """Replace cli.add_instrument with a capture-only stub."""
    calls: List[dict] = []

    def fake_add_instrument(**kwargs):
        calls.append(kwargs)
        return True

    monkeypatch.setattr(cli, "add_instrument", fake_add_instrument)
    return calls


# ---------------------------------------------------------------------------
# Magic-byte detection
# ---------------------------------------------------------------------------

class TestIsSqliteFile:
    def test_detects_real_sqlite_file(self, tmpdir_path):
        path = os.path.join(tmpdir_path, "real.db")
        conn = sqlite3.connect(path)
        conn.execute("CREATE TABLE t (x INTEGER)")
        conn.commit()
        conn.close()
        assert cli._is_sqlite_file(path) is True

    def test_rejects_json(self, tmpdir_path):
        path = os.path.join(tmpdir_path, "data.json")
        with open(path, "w") as f:
            json.dump([], f)
        assert cli._is_sqlite_file(path) is False

    def test_rejects_missing_file(self, tmpdir_path):
        assert cli._is_sqlite_file(os.path.join(tmpdir_path, "nope")) is False

    def test_detects_sqlite_with_unusual_extension(self, tmpdir_path):
        """Magic-byte sniff trumps the file extension."""
        path = os.path.join(tmpdir_path, "portfolio.bak")
        conn = sqlite3.connect(path)
        conn.execute("CREATE TABLE t (x INTEGER)")
        conn.commit()
        conn.close()
        assert cli._is_sqlite_file(path) is True


# ---------------------------------------------------------------------------
# SQLite import end-to-end
# ---------------------------------------------------------------------------

class TestImportFromSqlite:
    def test_imports_each_row(self, tmpdir_path, capture_add_calls):
        path = os.path.join(tmpdir_path, "src.db")
        _make_source_db(path, [
            {"ticker": "AAPL",     "shares": 10, "avg_purchase_price": 150.0,
             "isin": "US0378331005", "exchange_code": ""},
            {"ticker": "NESN.SW",  "shares": 50, "avg_purchase_price": 110.0,
             "isin": "CH0038863350", "exchange_code": "SW"},
        ])

        cli._import_from_sqlite(path)

        assert len(capture_add_calls) == 2
        a, b = capture_add_calls
        assert a["ticker"] == "AAPL"
        assert a["shares"] == 10
        assert a["avg_purchase_price"] == 150.0
        assert a["isin"] == "US0378331005"
        assert b["ticker"] == "NESN.SW"
        assert b["preferred_exchange"] == "SW"

    def test_dispatcher_routes_db_extension(self, tmpdir_path, capture_add_calls):
        """_import_from_file picks the SQLite path for *.db files."""
        path = os.path.join(tmpdir_path, "legacy.db")
        _make_source_db(path, [
            {"ticker": "MSFT", "shares": 5, "avg_purchase_price": 300.0},
        ])
        cli._import_from_file(path)
        assert len(capture_add_calls) == 1
        assert capture_add_calls[0]["ticker"] == "MSFT"

    def test_dispatcher_falls_back_to_json(self, tmpdir_path, capture_add_calls):
        path = os.path.join(tmpdir_path, "src.json")
        with open(path, "w") as f:
            json.dump([{"ticker": "GOOG", "shares": 3, "avg_price": 140.0}], f)
        cli._import_from_file(path)
        assert len(capture_add_calls) == 1
        assert capture_add_calls[0]["ticker"] == "GOOG"

    def test_uses_preferred_exchange_when_row_has_none(
        self, tmpdir_path, capture_add_calls,
    ):
        path = os.path.join(tmpdir_path, "src.db")
        _make_source_db(path, [
            {"ticker": "VWCE", "shares": 23, "avg_purchase_price": 70.0},
        ])
        cli._import_from_sqlite(path, preferred_exchange="DE")
        assert capture_add_calls[0]["preferred_exchange"] == "DE"

    def test_extracts_suffix_from_exchange_display(
        self, tmpdir_path, capture_add_calls,
    ):
        path = os.path.join(tmpdir_path, "src.db")
        # Source DB has exchange_display="Swiss.SW" but no exchange_code.
        _make_source_db(path, [
            {"ticker": "ROG", "shares": 1, "avg_purchase_price": 250.0,
             "exchange_display": "Swiss.SW"},
        ])
        cli._import_from_sqlite(path)
        assert capture_add_calls[0]["preferred_exchange"] == "SW"

    def test_missing_portfolio_table(self, tmpdir_path, capture_add_calls):
        path = os.path.join(tmpdir_path, "weird.db")
        sqlite3.connect(path).execute(
            "CREATE TABLE other_thing (x INTEGER)"
        ).connection.commit()
        cli._import_from_sqlite(path)
        assert capture_add_calls == []

    def test_missing_file(self, tmpdir_path, capture_add_calls):
        cli._import_from_file(os.path.join(tmpdir_path, "nope.db"))
        assert capture_add_calls == []

    def test_empty_portfolio_table(self, tmpdir_path, capture_add_calls):
        path = os.path.join(tmpdir_path, "empty.db")
        _make_source_db(path, [])
        cli._import_from_sqlite(path)
        assert capture_add_calls == []

    def test_skips_rows_with_missing_ticker(
        self, tmpdir_path, capture_add_calls,
    ):
        path = os.path.join(tmpdir_path, "src.db")
        # Use a schema that allows NULL ticker for the test row.
        conn = sqlite3.connect(path)
        conn.execute("CREATE TABLE portfolio (ticker TEXT, shares REAL, "
                     "isin TEXT, avg_purchase_price REAL)")
        conn.execute("INSERT INTO portfolio VALUES (NULL, 10, NULL, 150)")
        conn.execute("INSERT INTO portfolio VALUES ('AAPL', 5, NULL, 150)")
        conn.commit()
        conn.close()
        cli._import_from_sqlite(path)
        assert len(capture_add_calls) == 1
        assert capture_add_calls[0]["ticker"] == "AAPL"


# ---------------------------------------------------------------------------
# Shared loader (used by GUI + TUI)
# ---------------------------------------------------------------------------

class TestSharedLoader:
    def test_loads_json_into_normalised_dicts(self, tmpdir_path):
        path = os.path.join(tmpdir_path, "p.json")
        with open(path, "w") as f:
            json.dump([
                {"ticker": "AAPL", "shares": 10, "avg_price": 150.0,
                 "isin": "US...", "exchange": "US"},
            ], f)
        rows, err = imports_mod.load_instruments_from_file(path)
        assert err is None
        assert rows == [{
            "ticker": "AAPL", "shares": 10, "avg_price": 150.0,
            "isin": "US...", "exchange": "US",
        }]

    def test_loads_sqlite_into_normalised_dicts(self, tmpdir_path):
        path = os.path.join(tmpdir_path, "p.db")
        _make_source_db(path, [
            {"ticker": "MSFT", "shares": 5, "avg_purchase_price": 300.0,
             "isin": "US594918104", "exchange_code": "US"},
        ])
        rows, err = imports_mod.load_instruments_from_file(path)
        assert err is None
        assert rows == [{
            "ticker": "MSFT", "shares": 5.0, "avg_price": 300.0,
            "isin": "US594918104", "exchange": "US",
        }]

    def test_missing_file_returns_error(self, tmpdir_path):
        rows, err = imports_mod.load_instruments_from_file(
            os.path.join(tmpdir_path, "nope.json"),
        )
        assert rows == []
        assert err is not None and "not found" in err.lower()

    def test_empty_path_returns_error(self):
        rows, err = imports_mod.load_instruments_from_file("")
        assert rows == []
        assert err is not None

    def test_missing_portfolio_table_returns_error(self, tmpdir_path):
        path = os.path.join(tmpdir_path, "weird.db")
        conn = sqlite3.connect(path)
        conn.execute("CREATE TABLE other_thing (x INTEGER)")
        conn.commit()
        conn.close()
        rows, err = imports_mod.load_instruments_from_file(path)
        assert rows == []
        assert err is not None and "portfolio" in err.lower()

    def test_invalid_json_returns_error(self, tmpdir_path):
        path = os.path.join(tmpdir_path, "bad.json")
        with open(path, "w") as f:
            f.write("not valid json {{")
        rows, err = imports_mod.load_instruments_from_file(path)
        assert rows == []
        assert err is not None and "invalid json" in err.lower()
