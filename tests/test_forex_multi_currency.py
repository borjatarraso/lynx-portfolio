"""Tests for the v5.3 multi-currency display helpers."""

from __future__ import annotations

import pytest

from lynx_portfolio import forex


@pytest.fixture(autouse=True)
def seeded_rates(monkeypatch: pytest.MonkeyPatch):
    """Install a deterministic session-rate cache for every test."""
    rates = {"EUR": 1.0, "USD": 0.92, "GBP": 1.18, "CHF": 1.04}
    monkeypatch.setattr(forex, "_session_rates", dict(rates))
    forex.set_display_currency("EUR")
    yield
    forex.set_display_currency("EUR")


class TestDisplayCurrency:
    def test_default_is_eur(self) -> None:
        assert forex.get_display_currency() == "EUR"

    def test_set_changes_default(self) -> None:
        forex.set_display_currency("USD")
        assert forex.get_display_currency() == "USD"

    def test_set_none_normalizes_to_eur(self) -> None:
        forex.set_display_currency(None)  # type: ignore[arg-type]
        assert forex.get_display_currency() == "EUR"

    def test_set_lowercase_is_uppercased(self) -> None:
        forex.set_display_currency("usd")
        assert forex.get_display_currency() == "USD"


class TestFromEur:
    def test_to_eur_is_identity(self) -> None:
        assert forex.from_eur(100.0) == 100.0

    def test_to_usd_uses_inverse_rate(self) -> None:
        forex.set_display_currency("USD")
        # 100 EUR / 0.92 EUR-per-USD ≈ 108.70 USD
        assert forex.from_eur(100.0) == pytest.approx(100.0 / 0.92, rel=1e-4)

    def test_unknown_currency_returns_none(self) -> None:
        forex.set_display_currency("XYZ")
        assert forex.from_eur(100.0) is None

    def test_none_amount_passes_through(self) -> None:
        assert forex.from_eur(None) is None


class TestConvert:
    def test_same_currency_is_identity(self) -> None:
        assert forex.convert(100.0, "USD", "USD") == 100.0

    def test_usd_to_gbp(self) -> None:
        # 100 USD -> EUR (×0.92) -> GBP (/1.18)
        expected = 100.0 * 0.92 / 1.18
        assert forex.convert(100.0, "USD", "GBP") == pytest.approx(expected, rel=1e-4)

    def test_missing_source_returns_none(self) -> None:
        assert forex.convert(100.0, "XXX", "USD") is None

    def test_missing_target_returns_none(self) -> None:
        assert forex.convert(100.0, "USD", "XXX") is None


class TestAvailableCurrencies:
    def test_returns_sorted_set(self) -> None:
        out = forex.available_currencies()
        assert out == ["CHF", "EUR", "GBP", "USD"]
