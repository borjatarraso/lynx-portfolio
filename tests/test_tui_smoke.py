"""Headless TUI smoke tests.

Ensure the Textual app can be mounted without raising (the v5.4 → v5.4.1
regression was an `InvalidThemeError` that only fired at mount time).
Every TUI in the Suite should have a companion test like this.

Tests use ``anyio.run`` rather than ``pytest-asyncio`` so the Suite
doesn't grow another test-only dependency — ``anyio`` is already in the
test environment (pulled in transitively by Textual).
"""

from __future__ import annotations

from pathlib import Path

import pytest


pytest.importorskip("textual")
anyio = pytest.importorskip("anyio")


@pytest.fixture()
def tmp_db(tmp_path: Path):
    """Point the portfolio DB at a fresh tempfile so the TUI can read."""
    from lynx_portfolio import database
    db_file = tmp_path / "portfolio.db"
    database.set_db_path(str(db_file))
    database.init_db()
    yield db_file


def test_tui_mounts_without_theme_error(tmp_db) -> None:
    """App.run_test() drives on_mount() — would raise InvalidThemeError
    on v5.4 if the default theme wasn't registered before being set."""
    from lynx_portfolio.tui import LynxApp

    async def _run() -> None:
        app = LynxApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            # The active theme must actually be a registered one.
            assert app.theme in app.available_themes

    anyio.run(_run, backend="asyncio")


def test_tui_cycles_themes_without_error(tmp_db) -> None:
    """Pressing `t` cycles through every registered theme without crash."""
    from lynx_portfolio.tui import LynxApp

    async def _run() -> None:
        app = LynxApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            for _ in range(8):
                await pilot.press("t")
                await pilot.pause()
                assert app.theme in app.available_themes

    anyio.run(_run, backend="asyncio")


def test_tui_default_is_lynx_theme_when_available(tmp_db) -> None:
    """v5.4+ ships lynx-theme; verify it's the active default."""
    from lynx_portfolio.tui import LynxApp

    async def _run() -> None:
        app = LynxApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            assert app.theme == "lynx-theme"

    anyio.run(_run, backend="asyncio")
