"""Tests for watchlists, price_alerts, and broker_import."""

from __future__ import annotations

from pathlib import Path

import pytest

from lynx_portfolio import database, watchlists, price_alerts, transactions, broker_import


@pytest.fixture()
def tmp_db(tmp_path: Path):
    db = tmp_path / "portfolio.db"
    database.set_db_path(str(db))
    database.init_db()
    yield db


class TestWatchlists:
    def test_add_and_list_default(self, tmp_db) -> None:
        wid = watchlists.add("AAPL")
        assert wid is not None
        assert watchlists.list_tickers() == ["AAPL"]

    def test_dedupe(self, tmp_db) -> None:
        watchlists.add("AAPL")
        assert watchlists.add("AAPL") is None
        assert len(watchlists.list_all()) == 1

    def test_named_lists(self, tmp_db) -> None:
        watchlists.add("AAPL", name="tech")
        watchlists.add("JNJ", name="pharma")
        assert set(watchlists.list_names()) == {"tech", "pharma"}
        assert watchlists.list_tickers("tech") == ["AAPL"]
        assert watchlists.list_tickers("pharma") == ["JNJ"]

    def test_remove(self, tmp_db) -> None:
        watchlists.add("AAPL")
        assert watchlists.remove("AAPL")
        assert watchlists.list_tickers() == []


class TestPriceAlerts:
    def test_create_and_list(self, tmp_db) -> None:
        aid = price_alerts.create("AAPL", condition=">=", threshold=200)
        alerts = price_alerts.list_all()
        assert len(alerts) == 1
        assert alerts[0].id == aid
        assert alerts[0].threshold == 200.0

    def test_invalid_condition_raises(self, tmp_db) -> None:
        with pytest.raises(ValueError):
            price_alerts.create("AAPL", condition="!=", threshold=100)

    def test_negative_threshold_raises(self, tmp_db) -> None:
        with pytest.raises(ValueError):
            price_alerts.create("AAPL", condition="<=", threshold=-1)

    def test_evaluate_fires_once(self, tmp_db) -> None:
        aid = price_alerts.create("NVDA", condition=">=", threshold=500)
        fired = price_alerts.evaluate({"NVDA": 510.0})
        assert len(fired) == 1
        assert fired[0]["ticker"] == "NVDA"
        # Second evaluation does not fire again because triggered_at is set.
        fired2 = price_alerts.evaluate({"NVDA": 600.0})
        assert fired2 == []

    def test_evaluate_reset(self, tmp_db) -> None:
        aid = price_alerts.create("X", condition=">=", threshold=100)
        price_alerts.evaluate({"X": 200.0})
        price_alerts.reset(aid)
        fired = price_alerts.evaluate({"X": 201.0})
        assert len(fired) == 1

    def test_below_condition(self, tmp_db) -> None:
        price_alerts.create("AMD", condition="<=", threshold=100)
        fired = price_alerts.evaluate({"AMD": 90.0})
        assert len(fired) == 1

    def test_disabled_not_fired(self, tmp_db) -> None:
        aid = price_alerts.create("X", condition="<=", threshold=100)
        price_alerts.set_enabled(aid, False)
        fired = price_alerts.evaluate({"X": 50.0})
        assert fired == []

    def test_delete(self, tmp_db) -> None:
        aid = price_alerts.create("X", condition=">=", threshold=1)
        assert price_alerts.delete(aid)
        assert price_alerts.list_all() == []


class TestBrokerImportDetection:
    def _write(self, path: Path, headers: list[str], rows: list[list[str]]) -> Path:
        import csv as _csv
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = _csv.writer(f)
            w.writerow(headers)
            for row in rows:
                w.writerow(row)
        return path

    def test_detect_ibkr(self, tmp_path: Path) -> None:
        p = self._write(
            tmp_path / "ibkr.csv",
            ["Symbol", "TradeDate", "Quantity", "TradePrice", "IBCommission", "CurrencyPrimary"],
            [],
        )
        assert broker_import.detect_broker(p) == "ibkr"

    def test_detect_trading212(self, tmp_path: Path) -> None:
        p = self._write(
            tmp_path / "t212.csv",
            ["Action", "Time", "Ticker", "No. of shares", "Price / share",
             "Currency (Price / share)", "Exchange rate"],
            [],
        )
        assert broker_import.detect_broker(p) == "trading212"

    def test_detect_generic(self, tmp_path: Path) -> None:
        p = self._write(
            tmp_path / "generic.csv",
            ["ticker", "trade_type", "shares", "price", "fees", "currency", "trade_date", "note"],
            [],
        )
        assert broker_import.detect_broker(p) == "generic"


class TestBrokerImportGeneric:
    def test_imports_rows(self, tmp_db, tmp_path: Path) -> None:
        import csv as _csv
        p = tmp_path / "trades.csv"
        with open(p, "w", newline="", encoding="utf-8") as f:
            w = _csv.writer(f)
            w.writerow(["ticker", "trade_type", "shares", "price", "fees", "currency", "trade_date", "note"])
            w.writerow(["AAPL", "BUY", "10", "150", "1", "USD", "2026-01-01", "seed"])
            w.writerow(["AAPL", "SELL", "5", "200", "1", "USD", "2026-02-01", ""])
        # Need a portfolio row so rebuild can update it
        database.add_instrument(ticker="AAPL", shares=0.0)
        result = broker_import.import_csv(p)
        assert result.broker == "generic"
        assert result.rows_read == 2
        assert result.imported == 2
        assert result.skipped == 0
        assert "AAPL" in result.new_tickers

    def test_dry_run_does_not_write(self, tmp_db, tmp_path: Path) -> None:
        import csv as _csv
        p = tmp_path / "trades.csv"
        with open(p, "w", newline="", encoding="utf-8") as f:
            w = _csv.writer(f)
            w.writerow(["ticker", "trade_type", "shares", "price", "fees", "currency", "trade_date"])
            w.writerow(["AAPL", "BUY", "10", "150", "1", "USD", "2026-01-01"])
        result = broker_import.import_csv(p, dry_run=True)
        assert result.imported == 1
        # No rows actually written
        assert transactions.list_transactions("AAPL") == []

    def test_missing_file(self, tmp_db, tmp_path: Path) -> None:
        result = broker_import.import_csv(tmp_path / "does-not-exist.csv")
        assert result.imported == 0
        assert any("not found" in e for e in result.errors)


class TestBrokerImportIBKR:
    def test_parses_buy_and_sell(self, tmp_db, tmp_path: Path) -> None:
        import csv as _csv
        p = tmp_path / "ibkr.csv"
        with open(p, "w", newline="", encoding="utf-8") as f:
            w = _csv.writer(f)
            w.writerow(["Symbol", "TradeDate", "Quantity", "TradePrice",
                        "IBCommission", "CurrencyPrimary"])
            w.writerow(["AAPL", "2026-01-02", "10", "150.0", "-1.5", "USD"])
            w.writerow(["AAPL", "2026-02-02", "-5", "200.0", "-1.5", "USD"])
        database.add_instrument(ticker="AAPL", shares=0.0)
        result = broker_import.import_csv(p)
        assert result.imported == 2
        assert result.broker == "ibkr"
        types = [t.trade_type for t in transactions.list_transactions("AAPL")]
        assert types == ["BUY", "SELL"]
