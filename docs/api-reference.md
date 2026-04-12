# API Reference

Lynx Portfolio exposes a REST API via Flask. Start the server with:

```bash
lynx --api
# Listening on http://localhost:5000
```

All endpoints return JSON. Timestamps follow ISO 8601.

---

## Health check

### `GET /api/health`

Returns server health status.

**Response** `200 OK`

```json
{
  "status": "ok",
  "timestamp": "2026-04-12T10:30:00Z"
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
  "version": "v0.2"
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
computed fields: `market_value`, `pnl`, `pnl_pct`, and their EUR equivalents.

**Response** `200 OK`

```json
[
  {
    "ticker": "AAPL",
    "shares": 10,
    "avg_purchase_price": 185.50,
    "current_price": 195.20,
    "currency": "USD",
    "market_value": 1952.00,
    "market_value_eur": 1790.10,
    "pnl": 97.00,
    "pnl_pct": 5.23,
    "pnl_eur": 88.95,
    "isin": "US0378331005",
    "exchange": "NMS",
    "name": "Apple Inc."
  }
]
```

Positions without `avg_purchase_price` return `null` for `pnl`, `pnl_pct`, and
`pnl_eur`.

**curl**

```bash
curl http://localhost:5000/api/portfolio
```

---

## Show single instrument

### `GET /api/portfolio/<ticker>`

Returns detail for a single position.

**Path parameters**

| Parameter | Type   | Description          |
|-----------|--------|----------------------|
| `ticker`  | string | Yahoo Finance ticker |

**Response** `200 OK` -- same shape as a single element from the list endpoint.

**Response** `404 Not Found` -- if the ticker is not in the portfolio.

**curl**

```bash
curl http://localhost:5000/api/portfolio/AAPL
```

---

## Add position

### `POST /api/portfolio`

Add a new instrument to the portfolio.

**Request body** (`application/json`)

| Field      | Type   | Required | Description                 |
|------------|--------|----------|-----------------------------|
| `ticker`   | string | Yes      | Yahoo Finance ticker symbol |
| `shares`   | number | Yes      | Number of shares            |
| `avg_price`| number | No       | Average purchase price      |
| `isin`     | string | No       | ISIN code                   |
| `exchange` | string | No       | Exchange identifier         |

**Response** `201 Created`

```json
{
  "message": "Position added",
  "ticker": "AAPL",
  "shares": 10
}
```

**Response** `400 Bad Request` -- missing required fields or invalid data.

**curl**

```bash
# With cost tracking
curl -X POST http://localhost:5000/api/portfolio \
  -H "Content-Type: application/json" \
  -d '{"ticker": "AAPL", "shares": 10, "avg_price": 185.50}'

# Without cost tracking (P&L will show "Not tracked")
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

| Field                | Type   | Required | Description           |
|----------------------|--------|----------|-----------------------|
| `shares`             | number | No       | New share count       |
| `avg_purchase_price` | number | No       | New average price     |

At least one field must be provided.

**Response** `200 OK`

```json
{
  "message": "Position updated",
  "ticker": "AAPL"
}
```

**Response** `404 Not Found` -- ticker not in portfolio.

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
  "message": "Position deleted",
  "ticker": "AAPL"
}
```

**Response** `404 Not Found` -- ticker not in portfolio.

**curl**

```bash
curl -X DELETE http://localhost:5000/api/portfolio/AAPL
```

---

## Refresh single instrument

### `POST /api/portfolio/<ticker>/refresh`

Re-fetch market data for a single instrument from Yahoo Finance.

**Path parameters**

| Parameter | Type   | Description          |
|-----------|--------|----------------------|
| `ticker`  | string | Yahoo Finance ticker |

**Response** `200 OK`

```json
{
  "message": "Instrument refreshed",
  "ticker": "AAPL"
}
```

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
  "message": "All instruments refreshed"
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
  "message": "Cache cleared"
}
```

**Response** `400 Bad Request` -- if `force=true` is not provided.

```json
{
  "error": "Pass ?force=true to confirm cache deletion"
}
```

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
  "message": "Cache entry deleted",
  "ticker": "AAPL"
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

## Error responses

All error responses follow a consistent shape:

```json
{
  "error": "Human-readable error message"
}
```

Common status codes:

| Code | Meaning                                    |
|------|--------------------------------------------|
| 200  | Success                                    |
| 201  | Resource created                           |
| 400  | Bad request (missing fields, invalid data) |
| 404  | Resource not found                         |
| 500  | Internal server error                      |
