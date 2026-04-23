"""Tests for :mod:`lynx_portfolio.transactions`."""

from __future__ import annotations

from pathlib import Path

import pytest

from lynx_portfolio import database, transactions


@pytest.fixture()
def tmp_db(tmp_path: Path):
    db = tmp_path / "portfolio.db"
    database.set_db_path(str(db))
    database.init_db()
    # Seed a portfolio row so rebuild_portfolio_summary can update it.
    database.add_instrument(ticker="AAPL", shares=0.0)
    yield db


class TestRecordAndList:
    def test_record_buy(self, tmp_db) -> None:
        tid = transactions.record_buy(
            "AAPL", shares=10, price=150.0, fees=1.0,
            trade_date="2026-01-15",
        )
        assert tid > 0
        txs = transactions.list_transactions("AAPL")
        assert len(txs) == 1
        assert txs[0].trade_type == "BUY"
        assert txs[0].shares == 10.0
        assert txs[0].trade_date == "2026-01-15"

    def test_record_sell(self, tmp_db) -> None:
        transactions.record_buy("AAPL", shares=10, price=150, trade_date="2026-01-01")
        transactions.record_sell("AAPL", shares=4, price=180, trade_date="2026-02-01")
        txs = transactions.list_transactions("AAPL")
        assert [t.trade_type for t in txs] == ["BUY", "SELL"]

    def test_delete(self, tmp_db) -> None:
        tid = transactions.record_buy("AAPL", shares=5, price=100)
        assert transactions.delete_transaction(tid)
        assert transactions.list_transactions("AAPL") == []


class TestFIFOCostBasis:
    def test_simple_buy(self, tmp_db) -> None:
        transactions.record_buy("AAPL", shares=10, price=100, fees=10)
        total, cost = transactions.cost_basis("AAPL")
        assert total == 10
        assert cost == pytest.approx(101.0)  # price + prorated fee

    def test_fifo_partial_sell(self, tmp_db) -> None:
        transactions.record_buy("AAPL", shares=10, price=100, trade_date="2026-01-01")
        transactions.record_buy("AAPL", shares=10, price=200, trade_date="2026-02-01")
        transactions.record_sell("AAPL", shares=5, price=250, trade_date="2026-03-01")
        lots = transactions.compute_open_lots_fifo("AAPL")
        # First lot is partially consumed (5 left at $100), second untouched.
        assert len(lots) == 2
        assert lots[0].shares_remaining == pytest.approx(5)
        assert lots[0].unit_cost == pytest.approx(100)
        assert lots[1].shares_remaining == pytest.approx(10)
        assert lots[1].unit_cost == pytest.approx(200)

    def test_fifo_full_first_lot(self, tmp_db) -> None:
        transactions.record_buy("T", shares=10, price=50, trade_date="2026-01-01")
        transactions.record_buy("T", shares=10, price=60, trade_date="2026-02-01")
        transactions.record_sell("T", shares=10, price=70, trade_date="2026-03-01")
        lots = transactions.compute_open_lots_fifo("T")
        assert len(lots) == 1
        assert lots[0].unit_cost == pytest.approx(60)

    def test_fully_sold_position(self, tmp_db) -> None:
        transactions.record_buy("T", shares=10, price=50)
        transactions.record_sell("T", shares=10, price=100)
        total, cost = transactions.cost_basis("T")
        assert total == 0
        assert cost == 0


class TestRealizedPnL:
    def test_gain_on_single_lot(self, tmp_db) -> None:
        transactions.record_buy("NVDA", shares=10, price=100, fees=5, trade_date="2026-01-01")
        transactions.record_sell("NVDA", shares=10, price=200, fees=5, trade_date="2026-02-01")
        result = transactions.realized_pnl("NVDA")
        # cost per share = 100 + 5/10 = 100.5; proceeds per share = 200 - 5/10 = 199.5
        # realized = 10 * (199.5 - 100.5) = 990
        assert result["sold_shares"] == 10
        assert result["realized"] == pytest.approx(990)

    def test_loss(self, tmp_db) -> None:
        transactions.record_buy("X", shares=10, price=100)
        transactions.record_sell("X", shares=10, price=50)
        assert transactions.realized_pnl("X")["realized"] == pytest.approx(-500)


class TestRebuildSummary:
    def test_rebuild_refreshes_portfolio_row(self, tmp_db) -> None:
        transactions.record_buy("MSFT", shares=10, price=200, fees=0)
        # portfolio row starts at 0 shares
        transactions.rebuild_portfolio_summary("MSFT")
        inst = database.get_instrument("MSFT")
        assert inst is not None
        assert inst["shares"] == pytest.approx(10)
        assert inst["avg_purchase_price"] == pytest.approx(200)
