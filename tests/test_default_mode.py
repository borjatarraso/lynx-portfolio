"""
Tests for default mode behavior:
- Production mode is the default when configured
- First run (no config) auto-launches the wizard
- Empty portfolio shows a hint on quit
- --devel flag still works
"""

import os
import shutil
import tempfile

import pytest

from lynx_portfolio import database, config


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tmpdir():
    d = tempfile.mkdtemp(prefix="lynx_test_defmode_")
    yield d
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def db_path(tmpdir):
    return os.path.join(tmpdir, "portfolio.db")


@pytest.fixture
def populated_db(db_path):
    """Create a real SQLite portfolio DB with one instrument."""
    database.set_db_path(db_path)
    database.init_db()
    database.add_instrument("AAPL", 10, avg_purchase_price=150.0)
    return db_path


# ---------------------------------------------------------------------------
# _setup_default_mode logic
# ---------------------------------------------------------------------------

class TestSetupDefaultMode:
    def test_returns_first_run_when_not_configured(self, tmpdir, monkeypatch):
        """When no config exists, _setup_default_mode returns 'first_run'."""
        # Point config to a non-existent file so get_db_path() returns None
        fake_config = os.path.join(tmpdir, "config.json")
        monkeypatch.setattr(config, "CONFIG_FILE", fake_config)

        from lynx_portfolio.cli import _setup_default_mode
        result = _setup_default_mode()
        assert result == "first_run"

    def test_returns_production_when_configured(self, db_path, tmpdir, monkeypatch):
        """When config has a db_path, _setup_default_mode returns 'production'."""
        # Create a config file with db_path set
        fake_config = os.path.join(tmpdir, "config.json")
        monkeypatch.setattr(config, "CONFIG_FILE", fake_config)
        monkeypatch.setattr(config, "CONFIG_DIR", tmpdir)

        cfg = {"db_path": db_path}
        config.save_config(cfg)

        from lynx_portfolio.cli import _setup_default_mode
        result = _setup_default_mode()
        assert result == "production"
        assert database.get_db_path() == db_path


# ---------------------------------------------------------------------------
# Database creation on first run
# ---------------------------------------------------------------------------

class TestDatabaseCreation:
    def test_init_db_creates_file(self, db_path):
        """init_db() should create the database file even if empty."""
        assert not os.path.isfile(db_path)
        database.set_db_path(db_path)
        database.init_db()
        assert os.path.isfile(db_path)

    def test_empty_db_has_no_instruments(self, db_path):
        """A freshly created DB should have zero instruments."""
        database.set_db_path(db_path)
        database.init_db()
        instruments = database.get_all_instruments()
        assert instruments == []

    def test_init_db_idempotent(self, db_path):
        """Calling init_db() multiple times should not fail."""
        database.set_db_path(db_path)
        database.init_db()
        database.init_db()  # second call is safe
        assert os.path.isfile(db_path)


# ---------------------------------------------------------------------------
# Empty portfolio hint
# ---------------------------------------------------------------------------

class TestEmptyPortfolioHint:
    def test_empty_portfolio_detected(self, db_path):
        """get_all_instruments() returns [] for an empty database."""
        database.set_db_path(db_path)
        database.init_db()
        assert database.get_all_instruments() == []

    def test_non_empty_portfolio_detected(self, populated_db):
        """get_all_instruments() returns instruments for a populated DB."""
        instruments = database.get_all_instruments()
        assert len(instruments) == 1
        assert instruments[0]["ticker"] == "AAPL"


# ---------------------------------------------------------------------------
# Config state
# ---------------------------------------------------------------------------

class TestConfigState:
    def test_not_configured_initially(self, tmpdir, monkeypatch):
        """A fresh install has no config."""
        fake_config = os.path.join(tmpdir, "nonexistent", "config.json")
        monkeypatch.setattr(config, "CONFIG_FILE", fake_config)
        assert config.get_db_path() is None
        assert not config.is_configured()

    def test_configured_after_save(self, tmpdir, monkeypatch):
        """After saving config, is_configured() returns True."""
        monkeypatch.setattr(config, "CONFIG_FILE", os.path.join(tmpdir, "config.json"))
        monkeypatch.setattr(config, "CONFIG_DIR", tmpdir)
        cfg = {"db_path": "/some/path/portfolio.db"}
        config.save_config(cfg)
        assert config.is_configured()
        assert config.get_db_path() == "/some/path/portfolio.db"
