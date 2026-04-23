"""Unit tests for :mod:`lynx_portfolio.dashboard`."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from lynx_portfolio import dashboard


def _fake_eur(amount, currency):
    """Identity: 1 unit of any currency = 1 EUR (simplifies arithmetic)."""
    return amount if amount is not None else None


@pytest.fixture()
def fake_portfolio(monkeypatch: pytest.MonkeyPatch):
    """Install a deterministic fake portfolio via monkeypatch."""
    instruments = [
        {
            "ticker": "AAA",
            "name": "Alpha Corp",
            "sector": "Technology",
            "shares": 100.0,
            "avg_purchase_price": 50.0,
            "current_price": 60.0,
            "regular_market_change": 1.5,
            "currency": "EUR",
            "dividend_rate": 2.0,
            "updated_at": "2026-04-23T10:00:00",
        },
        {
            "ticker": "BBB",
            "name": "Beta Corp",
            "sector": "Healthcare",
            "shares": 50.0,
            "avg_purchase_price": 20.0,
            "current_price": 15.0,
            "regular_market_change": -0.5,
            "currency": "EUR",
            "dividend_yield": 0.03,
            "updated_at": "2026-04-23T10:00:00",
        },
        {
            "ticker": "CCC",
            "name": "Gamma Corp",
            "sector": "Technology",
            "shares": 10.0,
            "avg_purchase_price": 100.0,
            "current_price": 150.0,
            "regular_market_change": 5.0,
            "currency": "EUR",
            "updated_at": "2026-04-23T10:00:00",
        },
    ]
    monkeypatch.setattr(
        dashboard.database, "get_all_instruments", lambda: list(instruments),
    )
    monkeypatch.setattr(dashboard.forex, "to_eur", _fake_eur)
    return instruments


class TestComputeStats:
    def test_empty_portfolio(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(dashboard.database, "get_all_instruments", lambda: [])
        stats = dashboard.compute_stats()
        assert stats["positions"] == 0
        assert stats["total_value_eur"] == 0
        assert stats["total_invested_eur"] == 0

    def test_full_portfolio_totals(self, fake_portfolio) -> None:
        stats = dashboard.compute_stats()
        # AAA: 100 * 60 = 6000; BBB: 50 * 15 = 750; CCC: 10 * 150 = 1500 -> 8250
        assert stats["positions"] == 3
        assert stats["total_value_eur"] == pytest.approx(8250, rel=1e-3)
        # invested: 100*50 + 50*20 + 10*100 = 5000 + 1000 + 1000 = 7000
        assert stats["total_invested_eur"] == pytest.approx(7000, rel=1e-3)
        # pnl = 8250 - 7000 = 1250
        assert stats["total_pnl_eur"] == pytest.approx(1250, rel=1e-3)

    def test_day_change(self, fake_portfolio) -> None:
        stats = dashboard.compute_stats()
        # AAA: 1.5 * 100 = 150; BBB: -0.5 * 50 = -25; CCC: 5 * 10 = 50 → 175
        assert stats["day_change_eur"] == pytest.approx(175, rel=1e-3)


class TestSectorAllocation:
    def test_sorted_desc(self, fake_portfolio) -> None:
        rows = dashboard.compute_sector_allocation()
        assert rows[0]["sector"] == "Technology"  # largest
        # Technology: 6000 + 1500 = 7500; Healthcare: 750
        assert rows[0]["value_eur"] == pytest.approx(7500, rel=1e-3)
        assert rows[0]["pct_of_portfolio"] > 80

    def test_unclassified_bucket(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            dashboard.database, "get_all_instruments",
            lambda: [{
                "ticker": "X", "shares": 1.0, "current_price": 100.0,
                "avg_purchase_price": 50.0, "currency": "EUR", "sector": None,
            }],
        )
        monkeypatch.setattr(dashboard.forex, "to_eur", _fake_eur)
        rows = dashboard.compute_sector_allocation()
        assert rows[0]["sector"] == "Unclassified"


class TestMovers:
    def test_gainers_and_losers(self, fake_portfolio) -> None:
        movers = dashboard.compute_movers(limit=5)
        gainers = [r["ticker"] for r in movers["gainers"]]
        losers = [r["ticker"] for r in movers["losers"]]
        # AAA and CCC gained; BBB lost
        assert "AAA" in gainers
        assert "CCC" in gainers
        assert "BBB" in losers

    def test_limit_respected(self, fake_portfolio) -> None:
        movers = dashboard.compute_movers(limit=1)
        assert len(movers["gainers"]) <= 1
        assert len(movers["losers"]) <= 1

    def test_skips_instruments_missing_change(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(
            dashboard.database, "get_all_instruments",
            lambda: [{
                "ticker": "X", "shares": 1.0, "current_price": 100.0,
                "avg_purchase_price": 50.0, "currency": "EUR",
                "regular_market_change": None,
            }],
        )
        monkeypatch.setattr(dashboard.forex, "to_eur", _fake_eur)
        movers = dashboard.compute_movers()
        assert movers["gainers"] == []
        assert movers["losers"] == []


class TestIncome:
    def test_dividend_rate_positions(self, fake_portfolio) -> None:
        income = dashboard.compute_income()
        # AAA rate=2.0 * 100 shares = 200 annual
        # BBB yield=0.03 * 15 * 50 = 22.50
        # CCC no dividend data
        tickers = {c["ticker"] for c in income["contributions"]}
        assert "AAA" in tickers
        assert "BBB" in tickers
        assert income["annual_income_eur"] == pytest.approx(222.50, rel=1e-3)
        assert income["monthly_income_eur"] == pytest.approx(222.50 / 12, rel=1e-3)


class TestAlerts:
    def test_drawdown_alert(self, fake_portfolio) -> None:
        alerts = dashboard.compute_alerts(drawdown_pct=10.0)
        # BBB invested 20, current 15 → -25% drawdown → triggers
        tickers = [a["ticker"] for a in alerts if a["kind"] == "drawdown"]
        assert "BBB" in tickers

    def test_concentration_alert(self, fake_portfolio) -> None:
        alerts = dashboard.compute_alerts(concentration_pct=10.0)
        # AAA: 6000/8250 = 72%; CCC: 1500/8250 = 18% — both cross 10%
        tickers = [a["ticker"] for a in alerts if a["kind"] == "concentration"]
        assert "AAA" in tickers

    def test_no_alerts_on_healthy_portfolio(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from datetime import datetime
        today = datetime.now().isoformat(timespec="seconds")
        monkeypatch.setattr(
            dashboard.database, "get_all_instruments",
            lambda: [{
                "ticker": "X", "shares": 1.0, "current_price": 100.0,
                "avg_purchase_price": 95.0, "currency": "EUR",
                "regular_market_change": 0.0, "updated_at": today,
            }],
        )
        monkeypatch.setattr(dashboard.forex, "to_eur", _fake_eur)
        alerts = dashboard.compute_alerts()
        # small drawdown, single-position = 100% of portfolio → concentration fires
        # but no drawdown alert
        assert not any(a["kind"] == "drawdown" for a in alerts)


class TestFullDashboard:
    def test_returns_all_sections(self, fake_portfolio) -> None:
        data = dashboard.compute_full_dashboard()
        assert set(data.keys()) == {"stats", "sectors", "movers", "income", "alerts"}
