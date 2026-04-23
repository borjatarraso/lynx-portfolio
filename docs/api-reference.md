# Lynx Portfolio REST API

Part of **Lince Investor Suite v4.0**.

Lynx Portfolio exposes a REST API via Flask. Start the server with:

```bash
lynx-portfolio --api               # bind to 127.0.0.1:5000 (default)
lynx-portfolio --api --port 8080   # bind to 127.0.0.1:8080
lynx-portfolio --api --unsafe-bind-all   # bind 0.0.0.0 — requires opt-in
```

All endpoints return JSON. Timestamps follow ISO 8601. Money amounts
ending in `_eur` have been converted to EUR via the Suite's forex
cache.

## Authentication

Every non-public endpoint is protected by a bearer token.

* The token is **generated on first start** and saved at
  `<data-dir>/api_token` with file mode `0600`.
* Clients supply it via `Authorization: Bearer <token>` or
  `?token=<token>` (query string).
* The token is printed once to stderr when the server starts; copy it
  from the banner or read it from the file on disk.

```bash
TOKEN=$(cat ~/.lynx-portfolio/api_token 2>/dev/null || \
        cat data/api_token)
curl -H "Authorization: Bearer $TOKEN" http://127.0.0.1:5000/api/portfolio
```

### Public (no token) endpoints

* `GET /api/health`
* `GET /api/version`

Every other route returns `401 unauthorized` without a valid token.

## Transport

* **Default bind:** `127.0.0.1` (loopback only). Other hosts on the
  network cannot connect.
* **`--unsafe-bind-all`** binds `0.0.0.0`. The Suite prints a prominent
  warning in the banner when this flag is set.
* **TLS:** not provided in-process. Put the server behind a local
  reverse-proxy (nginx, Caddy) if you need HTTPS.

## Error responses

Every error response has the same shape:

```json
{ "error": "Human-readable message" }
```

The server **never echoes upstream exception text** — 5xx responses
carry only a generic `"Internal server error"` / `"Failed to fetch
upstream data"` message, and the full traceback is logged server-side.

| Code | Meaning |
|------|---------|
| 200 | Success |
| 201 | Resource created |
| 400 | Bad request (missing fields, invalid data) |
| 401 | Missing or wrong bearer token |
| 404 | Resource not found |
| 409 | Conflict (e.g. instrument already exists) |
| 500 | Internal server error |
| 502 | Upstream fetch failed (Yahoo Finance, forex, etc.) |
| 503 | API not ready (server misconfigured) |

---

# Endpoints

## Health & version (public)

### `GET /api/health`

```json
{ "status": "ok", "timestamp": "2026-04-23T10:30:00+00:00" }
```

### `GET /api/version`

```json
{ "name": "Lynx Portfolio", "version": "4.0" }
```

## Portfolio CRUD

### `GET /api/portfolio`

List every instrument with computed fields (`market_value`, `pnl`,
`pnl_pct`, `market_value_eur`, `pnl_eur`).

### `GET /api/portfolio/<ticker>`

Single instrument detail.

### `POST /api/portfolio`

Add a new instrument.

```json
{
  "ticker": "AAPL",
  "shares": 10,
  "avg_price": 150.0,
  "exchange": "NASDAQ",
  "isin": null
}
```

At least one of `ticker` / `isin` is required. `shares` is required.

### `PUT /api/portfolio/<ticker>`

Update shares and/or cost basis. Pass `"avg_purchase_price": null` to
clear the cost basis.

### `DELETE /api/portfolio/<ticker>`

Remove the position.

## Refresh

### `POST /api/portfolio/<ticker>/refresh`

Wipe the cache for one ticker and re-fetch from Yahoo Finance.

### `POST /api/portfolio/refresh`

Refresh every instrument in the portfolio. Returns counts.

```json
{ "status": "refreshed", "refreshed": 8, "total": 10 }
```

## Cache

### `DELETE /api/cache?force=true`

Wipe the entire instrument cache. The `force=true` query flag is
required — without it you get `400`.

### `DELETE /api/cache/<ticker>`

Clear the cache for one ticker.

## Forex

### `GET /api/forex/rates`

Current session rates with EUR as base.

```json
{ "base_currency": "EUR", "rates": {"USD": 1.0724, "CHF": 0.9411 } }
```

---

# Dashboard (v4.0)

Six analytics views powered by the same `dashboard.py` module that
drives the interactive REPL and TUI. Every endpoint is idempotent,
safe to poll, and returns JSON only — no server-side rendering.

## `GET /api/dashboard`

Full snapshot: every section below in a single response.

```json
{
  "stats":   { ... },
  "sectors": [ ... ],
  "movers":  { "gainers": [...], "losers": [...] },
  "income":  { ... },
  "alerts":  [ ... ]
}
```

## `GET /api/dashboard/stats`

Portfolio summary card.

```json
{
  "positions": 12,
  "total_value_eur": 87412.55,
  "total_invested_eur": 72000.00,
  "total_pnl_eur": 15412.55,
  "total_pnl_pct": 21.40,
  "day_change_eur": -213.40,
  "day_change_pct": -0.24,
  "generated_at": "2026-04-23T09:30:00+00:00"
}
```

Fields are `null` when the underlying data is not available (e.g. no
cost basis recorded, or all prices missing).

## `GET /api/dashboard/sectors`

Sector allocation, sorted by EUR value descending. Positions without a
sector land in `"Unclassified"`.

```json
[
  { "sector": "Technology", "positions": 4, "value_eur": 33100.00, "pct_of_portfolio": 37.87 },
  { "sector": "Healthcare", "positions": 3, "value_eur": 21800.00, "pct_of_portfolio": 24.94 },
  { "sector": "Financials", "positions": 2, "value_eur": 18500.00, "pct_of_portfolio": 21.16 }
]
```

## `GET /api/dashboard/movers?limit=N`

Top `N` gainers and losers of the day. `limit` defaults to 5; allowed
range `1..50`. Positions without `regular_market_change` are excluded.

```json
{
  "gainers": [
    { "ticker": "NVDA", "name": "NVIDIA Corp", "sector": "Technology",
      "day_change_pct": 3.21, "day_change_abs": 18.40,
      "current_price": 591.55, "currency": "USD" }
  ],
  "losers": [
    { "ticker": "META", "name": "Meta Platforms", "sector": "Communication Services",
      "day_change_pct": -1.42, "day_change_abs": -8.10,
      "current_price": 562.30, "currency": "USD" }
  ]
}
```

## `GET /api/dashboard/income`

Annual dividend income projection. Uses `dividend_rate` (annual cash /
share) when present; otherwise derives it from `dividend_yield ×
current_price`.

```json
{
  "annual_income_eur": 2431.88,
  "monthly_income_eur": 202.66,
  "portfolio_yield_pct": 2.78,
  "yield_on_cost_pct": 3.38,
  "contributions": [
    { "ticker": "JNJ", "annual_income_eur": 421.44, "annual_income": 458.00, "currency": "USD" }
  ]
}
```

## `GET /api/dashboard/alerts`

Actionable alerts. Query parameters (all optional):

| Parameter | Default | Meaning |
|---|---|---|
| `drawdown_pct` | `15` | Fire when a position is down ≥ this % vs cost basis. |
| `concentration_pct` | `20` | Fire when a position is ≥ this % of portfolio value. |
| `stale_days` | `7` | Fire when `updated_at` is older than this many days. |

```json
[
  { "severity": "warn", "kind": "drawdown", "ticker": "BABA",
    "message": "BABA is down 22.4% vs cost basis" },
  { "severity": "warn", "kind": "concentration", "ticker": "AAPL",
    "message": "AAPL is 31.2% of portfolio — concentrated" },
  { "severity": "info", "kind": "stale", "ticker": "VWCE.DE",
    "message": "VWCE.DE last refreshed 9d ago" }
]
```

Severities: `critical` (≥ 2× drawdown threshold), `warn`, `info`.
Kinds: `drawdown`, `concentration`, `stale`, `missing_avg_price`.

## `GET /api/dashboard/benchmark?ticker=^GSPC`

Portfolio PnL % vs a benchmark index over the last 52 weeks. The
`ticker` parameter is strictly validated — only alphanumeric, dots,
hyphens, and carets (`^`) are allowed.

```json
{
  "portfolio_return_pct": 21.40,
  "benchmark": { "ticker": "^GSPC", "current_price": 5880.12, "return_pct": 12.15 },
  "alpha_pct": 9.25
}
```

---

# Validation rules

| Input | Rule |
|---|---|
| `ticker` | Alphanumeric, dots, hyphens, carets; max 20 chars |
| `isin` | 2 letters + 10 alphanumerics |
| `shares` | Positive number, max 1×10⁹ |
| `avg_price` | Non-negative, max 1×10⁹ |
| `avg_purchase_price` | Non-negative, or `null` to clear |
| Bearer token | `secrets.compare_digest` — timing-safe equality |

## CLI bounds (v4.0)

| Flag | Range |
|---|---|
| `--port` | 1 – 65535 |
| `--auto-refresh-cache` | ≥ 30 s |
| `--unsafe-bind-all` | boolean (explicit opt-in) |

---

# Suite context

Lynx Portfolio is part of the **Lince Investor Suite v4.0**. The
dashboard module is shared with other Suite programs through
`lynx_investor_core`, and the sector / industry taxonomy used by
`GET /api/dashboard/sectors` aligns with the
[`lynx-investor-*` agents](https://github.com/borjatarraso?tab=repositories).

## Author

Borja Tarraso — <borja.tarraso@member.fsf.org> · BSD 3-Clause.
