"""Tests for the mobile web-UI integration in the Flask API."""

from __future__ import annotations

from pathlib import Path

import pytest

from lynx_portfolio import api, database


@pytest.fixture()
def api_client(tmp_path: Path):
    database.set_db_path(str(tmp_path / "portfolio.db"))
    database.init_db()
    token = api._load_or_generate_token()
    api.app.config["API_TOKEN"] = token
    api.app.config["TESTING"] = True
    with api.app.test_client() as c:
        yield c, token


class TestWebUI:
    def test_root_redirects_to_web(self, api_client) -> None:
        client, _ = api_client
        rv = client.get("/")
        assert rv.status_code == 302
        assert "/web/index.html" in rv.headers.get("Location", "")

    def test_index_html_served(self, api_client) -> None:
        client, _ = api_client
        rv = client.get("/web/index.html")
        assert rv.status_code == 200
        assert b"Lynx Portfolio" in rv.data
        assert b"<title>" in rv.data

    def test_css_served(self, api_client) -> None:
        client, _ = api_client
        rv = client.get("/web/app.css")
        assert rv.status_code == 200
        # Rough sanity: at least one CSS rule
        assert b"body" in rv.data or b":root" in rv.data

    def test_js_served(self, api_client) -> None:
        client, _ = api_client
        rv = client.get("/web/app.js")
        assert rv.status_code == 200
        assert b"fetch" in rv.data
        assert b"api" in rv.data.lower()

    def test_web_assets_do_not_require_auth(self, api_client) -> None:
        """Static assets are served without a bearer token — the page
        itself prompts for the token once loaded."""
        client, _ = api_client
        # no Authorization header
        for path in ("/web/index.html", "/web/app.css", "/web/app.js"):
            rv = client.get(path)
            assert rv.status_code == 200, path


class TestWebFilesOnDisk:
    def test_all_three_files_present(self) -> None:
        from lynx_portfolio import api as _api
        web = _api._WEB_DIR
        assert (web / "index.html").is_file()
        assert (web / "app.css").is_file()
        assert (web / "app.js").is_file()

    def test_html_references_js_and_css(self) -> None:
        from lynx_portfolio import api as _api
        html = (_api._WEB_DIR / "index.html").read_text()
        assert "app.js" in html
        assert "app.css" in html
