# API Reference

Lynx Portfolio exposes a REST API via Flask. Start the server with:

```bash
lynx-portfolio --api
# Listening on http://localhost:5000
```

All endpoints return JSON. Timestamps follow ISO 8601.

All `<ticker>` path parameters are validated — invalid tickers (spaces,
special characters, overlong strings) return `400 Bad Request`.

---

## Health check

### `GET /api/health`

Returns server health status.

**Response** `200 OK`

```json
{
  "status": "ok",
  "timestamp": "2026-04-15T10:30:00+00:00"
}
```

**curl**

```bash
curl http://localhost:5000/api/health
```

---

## Version

### `GET /api/version`

Returns application name and version.

**Response** `200 OK`

```json
{
  "name": "Lynx Portfolio",
  "version": "v1.0"
}
```

**curl**

```bash
curl http://localhost:5000/api/version
```

---

## List portfolio

### `GET /api/portfolio`

Returns all positions enriched with live market data. Each instrument includes
computed fields: `market_value`, `total_invested`, `pnl`, `pnl_pct`, and their
EUR equivalents (`market_value_eur`, `pnl_eur`).

**Response** `200 OK`

```json
[
  {
    "ticker": "AAPL",
    "shares": 10,
    "avg_purchase_price": 185.50,
    "current_price": 195.20,
    "currency": "USD",
    "name": "Apple Inc.",
    "isin": "US0378331005",
    "exchange_display": "NASDAQ",
    "market_value": 1952.00,
    "market_value_eur": 1790.10,
    "total_invested": 1855.00,
    "pnl": 97.00,
    "pnl_pct": 5.23,
    "pnl_eur": 88.95
  }
]
```

Positions without `avg_purchase_price` return `null` for `total_invested`,
`pnl`, `pnl_pct`, and `pnl_eur`.

**curl**

```bash
curl http://localhost:5000/api/portfolio
```

---

## Show single instrument

### `GET /api/portfolio/<ticker>`

Returns detail for a single position with computed fields.

**Path parameters**

| Parameter | Type   | Description          |
|-----------|--------|----------------------|
| `ticker`  | string | Yahoo Finance ticker (alphanumeric, dots, hyphens) |

**Response** `200 OK` — same shape as a single element from the list endpoint.

**Response** `400 Bad Request` — invalid ticker format.

**Response** `404 Not Found` — ticker not in the portfolio.

**curl**

```bash
curl http://localhost:5000/api/portfolio/AAPL
```

---

## Add position

### `POST /api/portfolio`

Add a new instrument to the portfolio. Lynx resolves the ticker via Yahoo
Finance, fetches market data, and persists the position.

**Request body** (`application/json`)

| Field      | Type   | Required | Description                          |
|------------|--------|----------|--------------------------------------|
| `ticker`   | string | Yes*     | Yahoo Finance ticker symbol          |
| `isin`     | string | Yes*     | ISIN code (alternative to ticker)    |
| `shares`   | number | Yes      | Number of shares (must be positive)  |
| `avg_price`| number | No       | Average purchase price (non-negative)|
| `exchange` | string | No       | Preferred exchange suffix            |

*At least one of `ticker` or `isin` must be provided.

**Response** `201 Created`

```json
{
  "status": "created",
  "instrument": { ... },
  "messages": [
    {"level": "info", "message": "Using AAPL  (NASDAQ)"},
    {"level": "ok", "message": "Added AAPL to portfolio."}
  ]
}
```

**Response** `400 Bad Request` — missing required fields, invalid ticker, negative shares, etc.

**Response** `409 Conflict` — instrument already exists.

**curl**

```bash
# With cost tracking
curl -X POST http://localhost:5000/api/portfolio \
  -H "Content-Type: application/json" \
  -d '{"ticker": "AAPL", "shares": 10, "avg_price": 185.50}'

# Without cost tracking
curl -X POST http://localhost:5000/api/portfolio \
  -H "Content-Type: application/json" \
  -d '{"ticker": "MSFT", "shares": 5}'
```

---

## Update position

### `PUT /api/portfolio/<ticker>`

Update an existing position's share count or average purchase price.

**Path parameters**

| Parameter | Type   | Description          |
|-----------|--------|----------------------|
| `ticker`  | string | Yahoo Finance ticker |

**Request body** (`application/json`)

| Field                | Type   | Required | Description                    |
|----------------------|--------|----------|--------------------------------|
| `shares`             | number | No       | New share count (positive)     |
| `avg_purchase_price` | number | No       | New average price (non-negative, or null to clear) |

At least one field must be provided.

**Response** `200 OK`

```json
{
  "status": "updated",
  "instrument": { ... }
}
```

**Response** `400 Bad Request` — invalid values (negative shares, etc.).

**Response** `404 Not Found` — ticker not in portfolio.

**curl**

```bash
curl -X PUT http://localhost:5000/api/portfolio/AAPL \
  -H "Content-Type: application/json" \
  -d '{"shares": 15, "avg_purchase_price": 190.00}'
```

---

## Delete position

### `DELETE /api/portfolio/<ticker>`

Remove a position from the portfolio.

**Path parameters**

| Parameter | Type   | Description          |
|-----------|--------|----------------------|
| `ticker`  | string | Yahoo Finance ticker |

**Response** `200 OK`

```json
{
  "status": "deleted",
  "ticker": "AAPL"
}
```

**Response** `400 Bad Request` — invalid ticker format.

**Response** `404 Not Found` — ticker not in portfolio.

**curl**

```bash
curl -X DELETE http://localhost:5000/api/portfolio/AAPL
```

---

## Refresh single instrument

### `POST /api/portfolio/<ticker>/refresh`

Re-fetch market data for a single instrument from Yahoo Finance. Updates both
the cache and the portfolio record.

**Path parameters**

| Parameter | Type   | Description          |
|-----------|--------|----------------------|
| `ticker`  | string | Yahoo Finance ticker |

**Response** `200 OK`

```json
{
  "status": "refreshed",
  "instrument": { ... }
}
```

**Response** `404 Not Found` — ticker not in portfolio.

**Response** `502 Bad Gateway` — Yahoo Finance fetch failed.

**curl**

```bash
curl -X POST http://localhost:5000/api/portfolio/AAPL/refresh
```

---

## Refresh all instruments

### `POST /api/portfolio/refresh`

Re-fetch market data for every instrument in the portfolio.

**Response** `200 OK`

```json
{
  "status": "refreshed",
  "refreshed": 5,
  "total": 5
}
```

**curl**

```bash
curl -X POST http://localhost:5000/api/portfolio/refresh
```

---

## Delete entire cache

### `DELETE /api/cache`

Clear the entire instrument cache. Requires the `force=true` query parameter as
a safety measure.

**Query parameters**

| Parameter | Type   | Required | Description                    |
|-----------|--------|----------|--------------------------------|
| `force`   | string | Yes      | Must be `true` to confirm      |

**Response** `200 OK`

```json
{
  "status": "cleared",
  "entries_removed": 5
}
```

**Response** `400 Bad Request` — if `force=true` is not provided.

**curl**

```bash
# This will fail (safety check)
curl -X DELETE http://localhost:5000/api/cache

# This works
curl -X DELETE "http://localhost:5000/api/cache?force=true"
```

---

## Delete single cache entry

### `DELETE /api/cache/<ticker>`

Remove a single ticker from the instrument cache.

**Path parameters**

| Parameter | Type   | Description          |
|-----------|--------|----------------------|
| `ticker`  | string | Yahoo Finance ticker |

**Response** `200 OK`

```json
{
  "status": "cleared",
  "ticker": "AAPL",
  "entries_removed": 1
}
```

**curl**

```bash
curl -X DELETE http://localhost:5000/api/cache/AAPL
```

---

## Forex rates

### `GET /api/forex/rates`

Returns the EUR exchange rates used for the current session. Rates are fetched
once from yfinance when the server starts and reused for all subsequent
requests.

**Response** `200 OK`

```json
{
  "base_currency": "EUR",
  "rates": {
    "USD": 1.0892,
    "GBP": 0.8571,
    "CHF": 0.9743,
    "JPY": 163.45
  }
}
```

**curl**

```bash
curl http://localhost:5000/api/forex/rates
```

---

## Input validation

All endpoints validate input and return `400 Bad Request` with a descriptive
error message for invalid data:

| Input                | Validation rule                          |
|----------------------|------------------------------------------|
| `ticker`             | Alphanumeric + dots/hyphens, max 20 chars|
| `isin`               | Exactly 12 chars: 2 letters + 10 alnum   |
| `shares`             | Positive number, max 1 billion           |
| `avg_price`          | Non-negative number, max 1 billion       |
| `avg_purchase_price` | Non-negative number, or `null` to clear  |

**Example error response**

```json
{
  "error": "Invalid ticker format. Use letters, digits, dots, and hyphens (e.g. AAPL, NESN.SW, BRK-B). Got: 'A; DROP TABLE'"
}
```

---

## Error responses

All error responses follow a consistent shape:

```json
{
  "error": "Human-readable error message"
}
```

Common status codes:

| Code | Meaning                                         |
|------|-------------------------------------------------|
| 200  | Success                                         |
| 201  | Resource created                                |
| 400  | Bad request (missing fields, invalid data)      |
| 404  | Resource not found                              |
| 409  | Conflict (e.g. instrument already exists)       |
| 502  | Bad gateway (Yahoo Finance fetch failed)        |
| 500  | Internal server error                           |
