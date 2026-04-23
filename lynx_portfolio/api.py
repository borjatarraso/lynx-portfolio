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
from . import (
    broker_import, cache, dashboard, database, fetcher, forex, operations,
    price_alerts, transactions, watchlists,
)
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
# Charts (v5.0)
# ---------------------------------------------------------------------------

@app.route("/api/charts/<ticker>", methods=["GET"])
@requires_token
def chart_series(ticker: str):
    """Return JSON { dates: [...], closes: [...], return_pct }."""
    ticker, err = validate_ticker(ticker)
    if err:
        return jsonify({"error": err}), 400
    period = request.args.get("period", "1y")
    try:
        from lynx_investor_core.charts import fetch_price_history, compute_return
    except ImportError:
        return jsonify({"error": "charts module unavailable"}), 503
    dates, closes = fetch_price_history(ticker, period=period)
    return jsonify({
        "ticker": ticker,
        "period": period,
        "dates": dates,
        "closes": closes,
        "return_pct": compute_return(closes),
    })


# ---------------------------------------------------------------------------
# Transactions (v5.0)
# ---------------------------------------------------------------------------

@app.route("/api/transactions", methods=["GET"])
@requires_token
def list_transactions_all():
    ticker = request.args.get("ticker")
    if ticker:
        ticker, err = validate_ticker(ticker)
        if err:
            return jsonify({"error": err}), 400
    txs = transactions.list_transactions(ticker)
    return jsonify([{
        "id": t.id,
        "ticker": t.ticker,
        "trade_type": t.trade_type,
        "shares": t.shares,
        "price": t.price,
        "fees": t.fees,
        "currency": t.currency,
        "trade_date": t.trade_date,
        "note": t.note,
    } for t in txs])


@app.route("/api/transactions", methods=["POST"])
@requires_token
def record_transaction():
    body = request.get_json(silent=True) or {}
    ticker = body.get("ticker")
    trade_type = (body.get("trade_type") or "").upper()
    shares = body.get("shares")
    price = body.get("price")

    if trade_type not in ("BUY", "SELL"):
        return jsonify({"error": "trade_type must be BUY or SELL"}), 400
    if not ticker:
        return jsonify({"error": "ticker is required"}), 400
    ticker, err = validate_ticker(str(ticker))
    if err:
        return jsonify({"error": err}), 400

    shares, err = validate_shares(shares)
    if err:
        return jsonify({"error": err}), 400
    price, err = validate_price(price)
    if err:
        return jsonify({"error": err}), 400

    fn = transactions.record_buy if trade_type == "BUY" else transactions.record_sell
    try:
        tid = fn(
            ticker,
            shares=shares,
            price=price,
            fees=float(body.get("fees") or 0.0),
            currency=body.get("currency"),
            trade_date=body.get("trade_date"),
            note=body.get("note"),
        )
        transactions.rebuild_portfolio_summary(ticker)
    except Exception:
        return jsonify({"error": "failed to record transaction"}), 500
    return jsonify({"status": "recorded", "id": tid}), 201


@app.route("/api/transactions/<int:tx_id>", methods=["DELETE"])
@requires_token
def remove_transaction(tx_id: int):
    if transactions.delete_transaction(tx_id):
        return jsonify({"status": "deleted", "id": tx_id})
    return jsonify({"error": f"transaction #{tx_id} not found"}), 404


@app.route("/api/transactions/<ticker>/lots", methods=["GET"])
@requires_token
def tax_lots(ticker: str):
    ticker, err = validate_ticker(ticker)
    if err:
        return jsonify({"error": err}), 400
    lots = transactions.compute_open_lots_fifo(ticker)
    return jsonify([{
        "trade_id": lot.trade_id,
        "ticker": lot.ticker,
        "shares_remaining": lot.shares_remaining,
        "unit_cost": lot.unit_cost,
        "currency": lot.currency,
        "trade_date": lot.trade_date,
    } for lot in lots])


@app.route("/api/transactions/<ticker>/realized", methods=["GET"])
@requires_token
def realized_pnl_endpoint(ticker: str):
    ticker, err = validate_ticker(ticker)
    if err:
        return jsonify({"error": err}), 400
    return jsonify(transactions.realized_pnl(ticker))


# ---------------------------------------------------------------------------
# Watchlists (v5.0)
# ---------------------------------------------------------------------------

@app.route("/api/watchlists", methods=["GET"])
@requires_token
def list_watchlists():
    name = request.args.get("name")
    items = watchlists.list_all(name)
    return jsonify([{
        "id": i.id, "name": i.name, "ticker": i.ticker, "note": i.note,
        "created_at": i.created_at,
    } for i in items])


@app.route("/api/watchlists", methods=["POST"])
@requires_token
def add_to_watchlist():
    body = request.get_json(silent=True) or {}
    ticker = body.get("ticker")
    name = body.get("name") or "default"
    if not ticker:
        return jsonify({"error": "ticker is required"}), 400
    ticker, err = validate_ticker(str(ticker))
    if err:
        return jsonify({"error": err}), 400
    wid = watchlists.add(ticker, name=str(name), note=body.get("note"))
    if wid is None:
        return jsonify({"status": "already on list", "ticker": ticker, "name": name}), 200
    return jsonify({"status": "added", "id": wid, "ticker": ticker, "name": name}), 201


@app.route("/api/watchlists/<ticker>", methods=["DELETE"])
@requires_token
def remove_from_watchlist(ticker: str):
    ticker, err = validate_ticker(ticker)
    if err:
        return jsonify({"error": err}), 400
    name = request.args.get("name") or "default"
    if watchlists.remove(ticker, name=str(name)):
        return jsonify({"status": "removed", "ticker": ticker, "name": name})
    return jsonify({"error": "not on watchlist"}), 404


# ---------------------------------------------------------------------------
# Price alerts (v5.0)
# ---------------------------------------------------------------------------

@app.route("/api/price-alerts", methods=["GET"])
@requires_token
def list_price_alerts():
    ticker = request.args.get("ticker")
    if ticker:
        ticker, err = validate_ticker(ticker)
        if err:
            return jsonify({"error": err}), 400
    alerts = price_alerts.list_all(ticker=ticker)
    return jsonify([{
        "id": a.id, "ticker": a.ticker, "condition": a.condition,
        "threshold": a.threshold, "note": a.note,
        "triggered_at": a.triggered_at, "enabled": bool(a.enabled),
        "created_at": a.created_at,
    } for a in alerts])


@app.route("/api/price-alerts", methods=["POST"])
@requires_token
def create_price_alert():
    body = request.get_json(silent=True) or {}
    ticker = body.get("ticker")
    condition = body.get("condition")
    threshold = body.get("threshold")
    if not ticker:
        return jsonify({"error": "ticker is required"}), 400
    ticker, err = validate_ticker(str(ticker))
    if err:
        return jsonify({"error": err}), 400
    try:
        aid = price_alerts.create(
            ticker, condition=condition, threshold=float(threshold),
            note=body.get("note"),
        )
    except (ValueError, TypeError) as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify({"status": "created", "id": aid}), 201


@app.route("/api/price-alerts/<int:alert_id>", methods=["DELETE"])
@requires_token
def delete_price_alert(alert_id: int):
    if price_alerts.delete(alert_id):
        return jsonify({"status": "deleted", "id": alert_id})
    return jsonify({"error": f"alert #{alert_id} not found"}), 404


@app.route("/api/price-alerts/<int:alert_id>/reset", methods=["POST"])
@requires_token
def reset_price_alert(alert_id: int):
    if price_alerts.reset(alert_id):
        return jsonify({"status": "reset", "id": alert_id})
    return jsonify({"error": f"alert #{alert_id} not found"}), 404


# ---------------------------------------------------------------------------
# Broker-CSV import (v5.0)
# ---------------------------------------------------------------------------

@app.route("/api/import/preview", methods=["POST"])
@requires_token
def import_preview():
    """Dry-run a CSV upload; returns how many rows would be imported."""
    body = request.get_json(silent=True) or {}
    path = body.get("path")
    broker = body.get("broker")
    if not path:
        return jsonify({"error": "'path' is required"}), 400
    from pathlib import Path as _P
    result = broker_import.import_csv(_P(path), broker=broker, dry_run=True)
    return jsonify({
        "broker": result.broker,
        "rows_read": result.rows_read,
        "imported": result.imported,
        "skipped": result.skipped,
        "errors": result.errors,
        "new_tickers": result.new_tickers,
    })


@app.route("/api/import", methods=["POST"])
@requires_token
def do_import():
    body = request.get_json(silent=True) or {}
    path = body.get("path")
    broker = body.get("broker")
    if not path:
        return jsonify({"error": "'path' is required"}), 400
    from pathlib import Path as _P
    result = broker_import.import_csv(_P(path), broker=broker, dry_run=False)
    status_code = 200 if not result.errors else 207  # Multi-status
    return jsonify({
        "broker": result.broker,
        "rows_read": result.rows_read,
        "imported": result.imported,
        "skipped": result.skipped,
        "errors": result.errors,
        "new_tickers": result.new_tickers,
    }), status_code


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
