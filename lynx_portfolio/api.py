"""
REST API for Lynx Portfolio, powered by Flask.

Start with:  lynx-portfolio --api [--port 5000]
"""

from datetime import datetime, timezone
from typing import Optional

from flask import Flask, request, jsonify

from . import APP_NAME, VERSION
from . import database, cache, fetcher, forex
from . import operations

app = Flask(__name__)


# ---------------------------------------------------------------------------
# Silent notifier — collects messages instead of printing to terminal
# ---------------------------------------------------------------------------

class _APINotifier(operations.Notifier):
    """Collect status messages so they can be returned in JSON responses."""

    def __init__(self):
        self.messages = []

    def info(self, msg: str) -> None:
        self.messages.append({"level": "info", "message": msg})

    def ok(self, msg: str) -> None:
        self.messages.append({"level": "ok", "message": msg})

    def err(self, msg: str) -> None:
        self.messages.append({"level": "error", "message": msg})

    def warn(self, msg: str) -> None:
        self.messages.append({"level": "warning", "message": msg})

    def show_instrument(self, inst: dict) -> None:
        pass  # API returns JSON; no terminal display


def _use_api_notifier() -> _APINotifier:
    """Install a fresh APINotifier and return it."""
    n = _APINotifier()
    operations.set_notifier(n)
    return n


def _restore_notifier() -> None:
    operations.set_notifier(operations.DisplayNotifier())


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _enrich_instrument(inst: dict) -> dict:
    """Add computed fields (market_value, pnl, pnl_pct, eur_*) to an instrument dict."""
    shares = inst.get("shares") or 0.0
    avg    = inst.get("avg_purchase_price")
    curr   = inst.get("current_price")
    ccy    = (inst.get("currency") or "EUR").upper()

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
# Health / version
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
def list_portfolio():
    instruments = database.get_all_instruments()
    return jsonify([_enrich_instrument(i) for i in instruments])


@app.route("/api/portfolio/<ticker>", methods=["GET"])
def get_instrument(ticker: str):
    inst = database.get_instrument(ticker.upper())
    if not inst:
        return jsonify({"error": f"'{ticker.upper()}' not found"}), 404
    return jsonify(_enrich_instrument(inst))


@app.route("/api/portfolio", methods=["POST"])
def add_instrument_endpoint():
    body = request.get_json(silent=True) or {}
    ticker    = body.get("ticker")
    isin      = body.get("isin")
    shares    = body.get("shares")
    avg_price = body.get("avg_price")
    exchange  = body.get("exchange")

    if not ticker and not isin:
        return jsonify({"error": "Provide at least 'ticker' or 'isin'"}), 400
    if shares is None:
        return jsonify({"error": "'shares' is required"}), 400

    try:
        shares = float(shares)
        if avg_price is not None:
            avg_price = float(avg_price)
    except (TypeError, ValueError):
        return jsonify({"error": "Invalid numeric value for shares or avg_price"}), 400

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
        # Extract the actual stored symbol from the notifier's "Added XXX" message.
        added = None
        for m in notifier.messages:
            if m["level"] == "ok" and "Added " in m["message"]:
                sym = m["message"].split("Added ", 1)[1].split(" ", 1)[0]
                added = database.get_instrument(sym)
                break
        # Fallback: get the most recently added instrument.
        if not added:
            instruments = database.get_all_instruments()
            if instruments:
                added = instruments[-1]
        return jsonify({
            "status": "created",
            "instrument": _enrich_instrument(added) if added else None,
            "messages": notifier.messages,
        }), 201
    else:
        return jsonify({
            "status": "failed",
            "messages": notifier.messages,
        }), 409


@app.route("/api/portfolio/<ticker>", methods=["PUT"])
def update_instrument_endpoint(ticker: str):
    body = request.get_json(silent=True) or {}
    kwargs = {}

    if "shares" in body:
        try:
            kwargs["shares"] = float(body["shares"])
        except (TypeError, ValueError):
            return jsonify({"error": "Invalid value for 'shares'"}), 400

    if "avg_purchase_price" in body:
        val = body["avg_purchase_price"]
        if val is None:
            kwargs["avg_purchase_price"] = None
        else:
            try:
                kwargs["avg_purchase_price"] = float(val)
            except (TypeError, ValueError):
                return jsonify({"error": "Invalid value for 'avg_purchase_price'"}), 400

    if not kwargs:
        return jsonify({"error": "Nothing to update. Send 'shares' and/or 'avg_purchase_price'."}), 400

    if database.update_instrument(ticker.upper(), **kwargs):
        inst = database.get_instrument(ticker.upper())
        return jsonify({
            "status": "updated",
            "instrument": _enrich_instrument(inst) if inst else None,
        })
    return jsonify({"error": f"'{ticker.upper()}' not found"}), 404


@app.route("/api/portfolio/<ticker>", methods=["DELETE"])
def delete_instrument_endpoint(ticker: str):
    if database.delete_instrument(ticker.upper()):
        return jsonify({"status": "deleted", "ticker": ticker.upper()})
    return jsonify({"error": f"'{ticker.upper()}' not found"}), 404


# ---------------------------------------------------------------------------
# Refresh
# ---------------------------------------------------------------------------

@app.route("/api/portfolio/<ticker>/refresh", methods=["POST"])
def refresh_instrument_endpoint(ticker: str):
    inst = database.get_instrument(ticker.upper())
    if not inst:
        return jsonify({"error": f"'{ticker.upper()}' not found"}), 404

    isin = inst.get("isin")
    cache.delete(ticker.upper())
    data = fetcher.fetch_instrument_data(ticker.upper(), isin)
    if not data:
        return jsonify({"error": f"Failed to fetch data for {ticker.upper()}"}), 502

    cache.put(ticker.upper(), data)
    database.apply_cache_to_portfolio(ticker.upper(), data)

    updated = database.get_instrument(ticker.upper())
    return jsonify({
        "status": "refreshed",
        "instrument": _enrich_instrument(updated) if updated else None,
    })


@app.route("/api/portfolio/refresh", methods=["POST"])
def refresh_all_endpoint():
    instruments = database.get_all_instruments()
    if not instruments:
        return jsonify({"status": "empty", "refreshed": 0})

    count = 0
    for inst in instruments:
        ticker = inst["ticker"]
        isin   = inst.get("isin")
        cache.delete(ticker)
        data = fetcher.fetch_instrument_data(ticker, isin)
        if data:
            cache.put(ticker, data)
            database.apply_cache_to_portfolio(ticker, data)
            count += 1

    return jsonify({"status": "refreshed", "refreshed": count, "total": len(instruments)})


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------

@app.route("/api/cache", methods=["DELETE"])
def clear_cache():
    force = request.args.get("force", "").lower() == "true"
    if not force:
        return jsonify({
            "error": "Cache clear requires ?force=true to prevent accidental data loss"
        }), 400
    n = cache.delete()
    return jsonify({"status": "cleared", "entries_removed": n})


@app.route("/api/cache/<ticker>", methods=["DELETE"])
def clear_cache_ticker(ticker: str):
    n = cache.delete(ticker.upper())
    return jsonify({"status": "cleared", "ticker": ticker.upper(), "entries_removed": n})


# ---------------------------------------------------------------------------
# Forex
# ---------------------------------------------------------------------------

@app.route("/api/forex/rates", methods=["GET"])
def forex_rates():
    rates = forex.get_session_rates()
    return jsonify({"base_currency": "EUR", "rates": rates})


# ---------------------------------------------------------------------------
# Error handlers
# ---------------------------------------------------------------------------

@app.errorhandler(404)
def not_found(e):
    return jsonify({"error": "Not found"}), 404


@app.errorhandler(500)
def internal_error(e):
    return jsonify({"error": "Internal server error"}), 500


# ---------------------------------------------------------------------------
# Init / run
# ---------------------------------------------------------------------------

def init_api() -> None:
    """Called before starting the Flask app to set up API-specific config."""
    pass  # Database and forex are already initialised by cli.py


def run_api_server(port: int = 5000) -> None:
    """Start the Flask development server."""
    init_api()
    app.run(host="0.0.0.0", port=port, debug=False)
