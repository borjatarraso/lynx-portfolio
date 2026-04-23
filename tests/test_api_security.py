"""Unit tests for v4.0 API security & dashboard endpoints."""

from __future__ import annotations

import json
import os
import stat
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from lynx_portfolio import api, database


@pytest.fixture()
def tmp_db(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """Point the portfolio DB at a fresh tempfile so tests are isolated."""
    db_file = tmp_path / "portfolio.db"
    database.set_db_path(str(db_file))
    database.init_db()
    yield db_file


@pytest.fixture()
def api_client(tmp_db: Path, monkeypatch: pytest.MonkeyPatch):
    """Flask test client with a fresh token."""
    # Force a new token for this test run
    token = api._load_or_generate_token()
    api.app.config["API_TOKEN"] = token
    api.app.config["TESTING"] = True
    with api.app.test_client() as client:
        yield client, token


class TestAuth:
    def test_unauthenticated_list_is_blocked(self, api_client) -> None:
        client, _ = api_client
        rv = client.get("/api/portfolio")
        assert rv.status_code == 401
        assert b"unauthorized" in rv.data

    def test_token_in_header_accepted(self, api_client) -> None:
        client, token = api_client
        rv = client.get(
            "/api/portfolio",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert rv.status_code == 200

    def test_token_in_query_accepted(self, api_client) -> None:
        client, token = api_client
        rv = client.get(f"/api/portfolio?token={token}")
        assert rv.status_code == 200

    def test_wrong_token_rejected(self, api_client) -> None:
        client, _ = api_client
        rv = client.get(
            "/api/portfolio",
            headers={"Authorization": "Bearer wrong-token-0" * 4},
        )
        assert rv.status_code == 401

    def test_public_endpoints_no_auth(self, api_client) -> None:
        client, _ = api_client
        assert client.get("/api/health").status_code == 200
        assert client.get("/api/version").status_code == 200


class TestTokenFile:
    def test_token_file_has_mode_0600(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
    ) -> None:
        monkeypatch.setattr(api, "_token_path", lambda: tmp_path / "api_token")
        # Ensure no existing token file
        (tmp_path / "api_token").unlink(missing_ok=True)
        token = api._load_or_generate_token()
        assert len(token) >= 32
        path = tmp_path / "api_token"
        assert path.exists()
        mode = stat.S_IMODE(os.stat(path).st_mode)
        # Owner read+write only
        assert mode & (stat.S_IRWXG | stat.S_IRWXO) == 0

    def test_token_is_reused(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
    ) -> None:
        monkeypatch.setattr(api, "_token_path", lambda: tmp_path / "api_token")
        (tmp_path / "api_token").unlink(missing_ok=True)
        first = api._load_or_generate_token()
        second = api._load_or_generate_token()
        assert first == second


class TestErrorHiding:
    def test_500_is_generic(self, api_client) -> None:
        client, token = api_client
        # Force an internal error by mocking get_all_instruments to raise.
        with patch.object(
            database, "get_all_instruments",
            side_effect=RuntimeError("SECRET internal detail"),
        ):
            rv = client.get(
                "/api/portfolio",
                headers={"Authorization": f"Bearer {token}"},
            )
        assert rv.status_code == 500
        body = rv.get_json()
        assert body["error"] == "Internal server error"
        assert "SECRET" not in rv.data.decode()

    def test_upstream_fetcher_failure_is_generic(self, api_client) -> None:
        client, token = api_client
        from lynx_portfolio import fetcher
        # Seed a portfolio entry so the refresh endpoint finds one
        database.update_instrument = lambda *a, **kw: True
        with patch.object(
            database, "get_instrument",
            return_value={"ticker": "AAPL", "isin": None},
        ), patch.object(
            fetcher, "fetch_instrument_data",
            side_effect=Exception("SECRET stack from yfinance"),
        ):
            rv = client.post(
                "/api/portfolio/AAPL/refresh",
                headers={"Authorization": f"Bearer {token}"},
            )
        assert rv.status_code == 502
        body = rv.get_json()
        assert "SECRET" not in json.dumps(body)
        assert body["error"] == "Failed to fetch upstream data"


class TestDashboardEndpoints:
    def test_stats_endpoint(self, api_client, monkeypatch) -> None:
        client, token = api_client
        monkeypatch.setattr(
            database, "get_all_instruments", lambda: [],
        )
        from lynx_portfolio import forex
        monkeypatch.setattr(forex, "to_eur", lambda amount, ccy: amount)
        rv = client.get(
            "/api/dashboard/stats",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert rv.status_code == 200
        body = rv.get_json()
        assert body["positions"] == 0

    def test_movers_limit_validation(self, api_client) -> None:
        client, token = api_client
        rv = client.get(
            "/api/dashboard/movers?limit=999",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert rv.status_code == 400

    def test_alerts_accepts_custom_thresholds(self, api_client, monkeypatch) -> None:
        client, token = api_client
        monkeypatch.setattr(database, "get_all_instruments", lambda: [])
        rv = client.get(
            "/api/dashboard/alerts?drawdown_pct=25&concentration_pct=40&stale_days=30",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert rv.status_code == 200
        assert rv.get_json() == []

    def test_benchmark_ticker_validated(self, api_client) -> None:
        client, token = api_client
        rv = client.get(
            "/api/dashboard/benchmark?ticker=BAD TICKER",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert rv.status_code == 400

    def test_full_dashboard(self, api_client, monkeypatch) -> None:
        client, token = api_client
        monkeypatch.setattr(database, "get_all_instruments", lambda: [])
        from lynx_portfolio import forex
        monkeypatch.setattr(forex, "to_eur", lambda amount, ccy: amount)
        rv = client.get(
            "/api/dashboard",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert rv.status_code == 200
        body = rv.get_json()
        assert set(body.keys()) == {"stats", "sectors", "movers", "income", "alerts"}
