"""REST API for Lynx Portfolio, powered by Flask.

Start with:  ``lynx-portfolio --api [--port 5000]``.

## Security model

* **Loopback by default.** The server binds to ``127.0.0.1`` unless the
  operator passes ``--unsafe-bind-all`` — the Suite refuses to expose
  portfolio data on other interfaces without an explicit opt-in.
* **Bearer-token auth.** On first start, a 48-char token is generated and
  stored at ``data/api_token`` with mode ``0600``. Every API request
  (except ``/api/health`` and ``/api/version``) must supply
  ``Authorization: Bearer <token>`` or ``?token=<token>``. The token is
  printed once on server start.
* **Generic errors.** Exceptions bubble up as ``500 Internal server
  error`` — never with the raw ``str(exc)`` text leaking internals.

## New dashboard endpoints (v4.0)

* ``GET /api/dashboard/stats``       portfolio summary card
* ``GET /api/dashboard/sectors``     sector allocation breakdown
* ``GET /api/dashboard/movers``      top gainers & losers for the day
* ``GET /api/dashboard/income``      annual dividend income projection
* ``GET /api/dashboard/alerts``      drawdown / concentration alerts
* ``GET /api/dashboard/benchmark``   portfolio vs market index
* ``GET /api/dashboard``             single-call snapshot of all sections
"""

from __future__ import annotations

import os
import secrets
import stat
import sys
import threading
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path
from typing import Any, Callable, Dict, Optional

_NOTIFIER_LOCK = threading.Lock()

from flask import Flask, jsonify, request

from . import APP_NAME, VERSION
from . import cache, dashboard, database, fetcher, forex, operations
from .validation import validate_ticker, validate_shares, validate_price


app = Flask(__name__)
app.config["API_TOKEN"] = None  # populated by run_api_server / init_api


# ---------------------------------------------------------------------------
# Authentication — bearer-token on every non-public route
# ---------------------------------------------------------------------------

_PUBLIC_PATHS = {"/api/health", "/api/version"}


def _token_path() -> Path:
    """Return the filesystem path where the API token is persisted."""
    try:
        db_path = database.get_db_path()
        return Path(db_path).parent / "api_token"
    except RuntimeError:
        return Path.home() / ".lynx-portfolio" / "api_token"


def _load_or_generate_token() -> str:
    """Read ``data/api_token`` or create one with mode 0600."""
    path = _token_path()
    try:
        if path.exists():
            token = path.read_text().strip()
            if len(token) >= 32:
                return token
    except OSError:
        pass

    token = secrets.token_urlsafe(36)

    for candidate in (path, Path.home() / ".lynx-portfolio" / "api_token"):
        try:
            candidate.parent.mkdir(parents=True, exist_ok=True)
            candidate.write_text(token + "\n")
            os.chmod(candidate, stat.S_IRUSR | stat.S_IWUSR)
            return token
        except OSError:
            continue
    return token  # returned without persistence — server still works for this run


def _request_token() -> Optional[str]:
    hdr = request.headers.get("Authorization", "")
    if hdr.lower().startswith("bearer "):
        return hdr[7:].strip()
    tok = request.args.get("token")
    if tok:
        return tok.strip()
    return None


def requires_token(fn: Callable) -> Callable:
    """Decorator that enforces bearer-token auth on the wrapped route."""
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if request.path in _PUBLIC_PATHS:
            return fn(*args, **kwargs)
        configured = app.config.get("API_TOKEN")
        if not configured:
            # Server misconfigured — never allow requests through.
            return jsonify({"error": "API not ready"}), 503
        supplied = _request_token()
        if not supplied or not secrets.compare_digest(supplied, configured):
            return jsonify({"error": "unauthorized"}), 401
        return fn(*args, **kwargs)
    return wrapper


# ---------------------------------------------------------------------------
# Silent notifier — collects messages instead of printing
# ---------------------------------------------------------------------------

class _APINotifier(operations.Notifier):
    """Collect status messages so they can be returned in JSON responses."""

    def __init__(self) -> None:
        self.messages: list[Dict[str, str]] = []

    def info(self, msg: str) -> None:
        self.messages.append({"level": "info", "message": msg})

    def ok(self, msg: str) -> None:
        self.messages.append({"level": "ok", "message": msg})

    def err(self, msg: str) -> None:
        self.messages.append({"level": "error", "message": msg})

    def warn(self, msg: str) -> None:
        self.messages.append({"level": "warning", "message": msg})

    def show_instrument(self, inst: Dict[str, Any]) -> None:  # pragma: no cover
        pass  # API returns JSON; no terminal display


def _use_api_notifier() -> _APINotifier:
    n = _APINotifier()
    operations.set_notifier(n)
    return n


def _restore_notifier() -> None:
    operations.set_notifier(operations.DisplayNotifier())


# ---------------------------------------------------------------------------
# Instrument enrichment (shared with dashboard helpers)
# ---------------------------------------------------------------------------

def _enrich_instrument(inst: Dict[str, Any]) -> Dict[str, Any]:
    """Add computed fields (market_value, pnl, pnl_pct, eur_*) to *inst*."""
    shares_raw = inst.get("shares")
    shares = 0.0 if shares_raw is None else float(shares_raw)
    avg = inst.get("avg_purchase_price")
    curr = inst.get("current_price")
    ccy = (inst.get("currency") or "EUR").upper()

    out = dict(inst)

    if curr is not None:
        mkt = shares * curr
        out["market_value"] = round(mkt, 2)
        eur_mkt = forex.to_eur(mkt, ccy)
        if eur_mkt is not None:
            out["market_value_eur"] = round(eur_mkt, 2)
    else:
        out["market_value"] = None

    if avg is not None:
        invested = shares * avg
        out["total_invested"] = round(invested, 2)
        if curr is not None:
            pnl = (shares * curr) - invested
            pct = (pnl / invested * 100) if invested else 0.0
            out["pnl"] = round(pnl, 2)
            out["pnl_pct"] = round(pct, 2)
            eur_pnl = forex.to_eur(pnl, ccy)
            if eur_pnl is not None:
                out["pnl_eur"] = round(eur_pnl, 2)
        else:
            out["pnl"] = None
            out["pnl_pct"] = None
    else:
        out["total_invested"] = None
        out["pnl"] = None
        out["pnl_pct"] = None

    return out


# ---------------------------------------------------------------------------
# Health / version (public — no auth)
# ---------------------------------------------------------------------------

@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({
        "status": "ok",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })


@app.route("/api/version", methods=["GET"])
def version():
    return jsonify({"name": APP_NAME, "version": VERSION})


# ---------------------------------------------------------------------------
# Portfolio CRUD
# ---------------------------------------------------------------------------

@app.route("/api/portfolio", methods=["GET"])
@requires_token
def list_portfolio():
    instruments = database.get_all_instruments()
    return jsonify([_enrich_instrument(i) for i in instruments])


@app.route("/api/portfolio/<ticker>", methods=["GET"])
@requires_token
def get_instrument(ticker: str):
    ticker, err = validate_ticker(ticker)
    if err:
        return jsonify({"error": err}), 400
    inst = database.get_instrument(ticker)
    if not inst:
        return jsonify({"error": f"'{ticker}' not found"}), 404
    return jsonify(_enrich_instrument(inst))


@app.route("/api/portfolio", methods=["POST"])
@requires_token
def add_instrument_endpoint():
    body = request.get_json(silent=True) or {}
    ticker = body.get("ticker")
    isin = body.get("isin")
    shares = body.get("shares")
    avg_price = body.get("avg_price")
    exchange = body.get("exchange")

    if not ticker and not isin:
        return jsonify({"error": "Provide at least 'ticker' or 'isin'"}), 400
    if shares is None:
        return jsonify({"error": "'shares' is required"}), 400

    if ticker:
        ticker, err = validate_ticker(str(ticker))
        if err:
            return jsonify({"error": err}), 400

    shares, err = validate_shares(shares)
    if err:
        return jsonify({"error": err}), 400

    if avg_price is not None:
        avg_price, err = validate_price(avg_price)
        if err:
            return jsonify({"error": err}), 400

    with _NOTIFIER_LOCK:
        notifier = _use_api_notifier()
        try:
            ok = operations.add_instrument(
                ticker=ticker,
                isin=isin,
                shares=shares,
                avg_purchase_price=avg_price,
                preferred_exchange=exchange,
            )
        finally:
            _restore_notifier()

    if ok:
        added = None
        for m in notifier.messages:
            if m["level"] == "ok" and "Added " in m["message"]:
                sym = m["message"].split("Added ", 1)[1].split(" ", 1)[0]
                added = database.get_instrument(sym)
                break
        if not added:
            instruments = database.get_all_instruments()
            if instruments:
                added = instruments[-1]
        return jsonify({
            "status": "created",
            "instrument": _enrich_instrument(added) if added else None,
            "messages": notifier.messages,
        }), 201
    return jsonify({
        "status": "failed",
        "messages": notifier.messages,
    }), 409


@app.route("/api/portfolio/<ticker>", methods=["PUT"])
@requires_token
def update_instrument_endpoint(ticker: str):
    ticker, err = validate_ticker(ticker)
    if err:
        return jsonify({"error": err}), 400

    body = request.get_json(silent=True) or {}
    kwargs: Dict[str, Any] = {}

    if "shares" in body:
        val, err = validate_shares(body["shares"])
        if err:
            return jsonify({"error": err}), 400
        kwargs["shares"] = val

    if "avg_purchase_price" in body:
        raw = body["avg_purchase_price"]
        if raw is None:
            kwargs["avg_purchase_price"] = None
        else:
            val, err = validate_price(raw)
            if err:
                return jsonify({"error": err}), 400
            kwargs["avg_purchase_price"] = val

    if not kwargs:
        return jsonify({
            "error": "Nothing to update. Send 'shares' and/or 'avg_purchase_price'.",
        }), 400

    if database.update_instrument(ticker, **kwargs):
        inst = database.get_instrument(ticker)
        return jsonify({
            "status": "updated",
            "instrument": _enrich_instrument(inst) if inst else None,
        })
    return jsonify({"error": f"'{ticker}' not found"}), 404


@app.route("/api/portfolio/<ticker>", methods=["DELETE"])
@requires_token
def delete_instrument_endpoint(ticker: str):
    ticker, err = validate_ticker(ticker)
    if err:
        return jsonify({"error": err}), 400
    if database.delete_instrument(ticker):
        return jsonify({"status": "deleted", "ticker": ticker})
    return jsonify({"error": f"'{ticker}' not found"}), 404


# ---------------------------------------------------------------------------
# Refresh
# ---------------------------------------------------------------------------

@app.route("/api/portfolio/<ticker>/refresh", methods=["POST"])
@requires_token
def refresh_instrument_endpoint(ticker: str):
    ticker, err = validate_ticker(ticker)
    if err:
        return jsonify({"error": err}), 400
    inst = database.get_instrument(ticker)
    if not inst:
        return jsonify({"error": f"'{ticker}' not found"}), 404

    isin = inst.get("isin")
    cache.delete(ticker)
    try:
        data = fetcher.fetch_instrument_data(ticker, isin)
    except Exception:
        return jsonify({"error": "Failed to fetch upstream data"}), 502
    if not data:
        return jsonify({"error": f"Failed to fetch data for {ticker}"}), 502

    cache.put(ticker, data)
    database.apply_cache_to_portfolio(ticker, data)

    updated = database.get_instrument(ticker)
    return jsonify({
        "status": "refreshed",
        "instrument": _enrich_instrument(updated) if updated else None,
    })


@app.route("/api/portfolio/refresh", methods=["POST"])
@requires_token
def refresh_all_endpoint():
    instruments = database.get_all_instruments()
    if not instruments:
        return jsonify({"status": "empty", "refreshed": 0})

    count = 0
    for inst in instruments:
        ticker = inst["ticker"]
        isin = inst.get("isin")
        cache.delete(ticker)
        try:
            data = fetcher.fetch_instrument_data(ticker, isin)
        except Exception:
            continue  # skip this ticker, keep going
        if data:
            cache.put(ticker, data)
            database.apply_cache_to_portfolio(ticker, data)
            count += 1

    return jsonify({
        "status": "refreshed",
        "refreshed": count,
        "total": len(instruments),
    })


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------

@app.route("/api/cache", methods=["DELETE"])
@requires_token
def clear_cache():
    force = request.args.get("force", "").lower() == "true"
    if not force:
        return jsonify({
            "error": "Cache clear requires ?force=true to prevent accidental data loss",
        }), 400
    n = cache.delete()
    return jsonify({"status": "cleared", "entries_removed": n})


@app.route("/api/cache/<ticker>", methods=["DELETE"])
@requires_token
def clear_cache_ticker(ticker: str):
    ticker, err = validate_ticker(ticker)
    if err:
        return jsonify({"error": err}), 400
    n = cache.delete(ticker)
    return jsonify({"status": "cleared", "ticker": ticker, "entries_removed": n})


# ---------------------------------------------------------------------------
# Forex
# ---------------------------------------------------------------------------

@app.route("/api/forex/rates", methods=["GET"])
@requires_token
def forex_rates():
    rates = forex.get_session_rates()
    return jsonify({"base_currency": "EUR", "rates": rates})


# ---------------------------------------------------------------------------
# Dashboard (v4.0)
# ---------------------------------------------------------------------------

@app.route("/api/dashboard", methods=["GET"])
@requires_token
def dashboard_full():
    return jsonify(dashboard.compute_full_dashboard())


@app.route("/api/dashboard/stats", methods=["GET"])
@requires_token
def dashboard_stats():
    return jsonify(dashboard.compute_stats())


@app.route("/api/dashboard/sectors", methods=["GET"])
@requires_token
def dashboard_sectors():
    return jsonify(dashboard.compute_sector_allocation())


@app.route("/api/dashboard/movers", methods=["GET"])
@requires_token
def dashboard_movers():
    try:
        limit = int(request.args.get("limit", "5"))
    except (TypeError, ValueError):
        return jsonify({"error": "limit must be an integer"}), 400
    if limit < 1 or limit > 50:
        return jsonify({"error": "limit must be between 1 and 50"}), 400
    return jsonify(dashboard.compute_movers(limit=limit))


@app.route("/api/dashboard/income", methods=["GET"])
@requires_token
def dashboard_income():
    return jsonify(dashboard.compute_income())


@app.route("/api/dashboard/alerts", methods=["GET"])
@requires_token
def dashboard_alerts():
    try:
        dd = float(request.args.get("drawdown_pct", "15"))
        conc = float(request.args.get("concentration_pct", "20"))
        stale = int(request.args.get("stale_days", "7"))
    except (TypeError, ValueError):
        return jsonify({"error": "threshold parameters must be numeric"}), 400
    return jsonify(dashboard.compute_alerts(
        drawdown_pct=dd,
        concentration_pct=conc,
        stale_days=stale,
    ))


@app.route("/api/dashboard/benchmark", methods=["GET"])
@requires_token
def dashboard_benchmark():
    ticker = request.args.get("ticker", "^GSPC")
    # Allow-list benchmarks to avoid SSRF-via-ticker
    normalized, err = validate_ticker(ticker)
    if err or not normalized:
        return jsonify({"error": err or "invalid benchmark"}), 400
    return jsonify(dashboard.compute_benchmark(normalized))


# ---------------------------------------------------------------------------
# Error handlers — never leak exception text
# ---------------------------------------------------------------------------

@app.errorhandler(404)
def not_found(_e):
    return jsonify({"error": "Not found"}), 404


@app.errorhandler(500)
def internal_error(_e):
    return jsonify({"error": "Internal server error"}), 500


@app.errorhandler(Exception)
def unexpected(_e):  # pragma: no cover
    return jsonify({"error": "Internal server error"}), 500


# ---------------------------------------------------------------------------
# Init / run
# ---------------------------------------------------------------------------

def init_api() -> str:
    """Initialise API-specific config. Returns the bearer token."""
    token = _load_or_generate_token()
    app.config["API_TOKEN"] = token
    return token


def run_api_server(
    port: int = 5000,
    *,
    bind_all: bool = False,
    host: Optional[str] = None,
) -> None:
    """Start the Flask server.

    Defaults to binding ``127.0.0.1``. Pass ``bind_all=True`` to bind
    ``0.0.0.0`` — the caller is expected to enable this only when the
    operator has asked for it explicitly (``--unsafe-bind-all`` on the CLI).
    """
    token = init_api()

    if host is None:
        host = "0.0.0.0" if bind_all else "127.0.0.1"

    banner = [
        "",
        f"  {APP_NAME} v{VERSION} — API server",
        f"  Listening on http://{host}:{port}",
        "  Authentication: Bearer token",
        f"  Token:          {token}",
        f"  Token file:     {_token_path()} (chmod 600)",
        "",
    ]
    if bind_all:
        banner.insert(1, "  !!! WARNING: bound to 0.0.0.0 — accessible from the network !!!")
    print("\n".join(banner), file=sys.stderr)

    app.run(host=host, port=port, debug=False)
