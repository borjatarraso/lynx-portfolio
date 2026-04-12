# Architecture

This document describes Lynx Portfolio's internal structure, data flow, storage
schema, and key design decisions.

## Module responsibilities

| Module            | Responsibility                                          |
|-------------------|---------------------------------------------------------|
| `__init__.py`     | Package marker, version constant                        |
| `cli.py`          | Argument parsing, top-level flag handling, `-ni` router  |
| `interactive.py`  | Interactive REPL (`-i`), command loop, input parsing     |
| `tui.py`          | Textual full-screen TUI (`-tui`), keybindings, widgets   |
| `api.py`          | Flask REST API (`--api`), route definitions              |
| `operations.py`   | Business logic: add, update, delete, refresh, import     |
| `database.py`     | SQLite connection (WAL mode), CRUD for positions         |
| `cache.py`        | Instrument metadata cache (read/write/invalidate)        |
| `fetcher.py`      | Yahoo Finance calls via yfinance, OpenFIGI ISIN lookup   |
| `forex.py`        | EUR conversion rates, session-level caching              |
| `display.py`      | Rich tables, formatting, terminal output helpers         |
| `config.py`       | Read/write `~/.config/lynx/config.json`                  |

## Data flow

### Adding a position

```
User input (any interface)
       |
       v
  operations.add()
       |
       +---> database.insert_position(ticker, shares, avg_price?)
       |
       +---> fetcher.fetch_instrument(ticker)
       |         |
       |         +---> yfinance: price, name, currency, exchange
       |         +---> OpenFIGI (if ISIN provided): resolve ISIN
       |
       +---> cache.store(ticker, instrument_data)
       |
       +---> forex.convert(value, currency) --> EUR
       |
       v
  Notifier --> display / API response / TUI refresh
```

### Listing the portfolio

```
User requests list
       |
       v
  operations.list()
       |
       +---> database.get_all_positions()
       |
       +---> cache.get_all() --> instrument metadata
       |         |
       |         +---> (cache miss) --> fetcher.fetch_instrument()
       |
       +---> forex.get_rates() --> EUR conversion
       |
       +---> enrich each position:
       |       market_value = shares * current_price
       |       pnl = market_value - (shares * avg_purchase_price)  [if tracked]
       |       *_eur variants via forex rates
       |
       v
  Formatted output (table / JSON / TUI widget)
```

## SQLite schema

The database uses WAL (Write-Ahead Logging) mode for safe concurrent reads.

### positions table

| Column             | Type    | Nullable | Description                 |
|--------------------|---------|----------|-----------------------------|
| ticker             | TEXT    | No       | Primary key, Yahoo symbol   |
| shares             | REAL    | No       | Number of shares held       |
| avg_purchase_price | REAL    | Yes      | Average cost basis per share|
| isin               | TEXT    | Yes      | ISIN code                   |
| exchange           | TEXT    | Yes      | Exchange identifier         |
| created_at         | TEXT    | No       | ISO 8601 timestamp          |
| updated_at         | TEXT    | No       | ISO 8601 timestamp          |

### instrument_cache table

| Column       | Type    | Nullable | Description                      |
|--------------|---------|----------|----------------------------------|
| ticker       | TEXT    | No       | Primary key, Yahoo symbol        |
| name         | TEXT    | Yes      | Instrument display name          |
| currency     | TEXT    | Yes      | Native currency (USD, EUR, etc.) |
| current_price| REAL    | Yes      | Last fetched price               |
| exchange     | TEXT    | Yes      | Exchange identifier              |
| fetched_at   | TEXT    | No       | ISO 8601 timestamp of last fetch |

## Design decisions

### Notifier pattern

Interface modules (CLI, interactive, TUI, API) do not call business logic
directly. Instead, `operations.py` acts as the single source of truth and
notifies the caller of results. This keeps the four interfaces thin and
prevents logic duplication. Each interface only needs to translate user input
into an `operations` call and render the result.

### Forex session cache

Exchange rates are fetched exactly once per session from yfinance and held in
memory. This avoids redundant network calls when listing a portfolio with many
positions in different currencies. The rates are not persisted to disk -- a
fresh set is fetched each time Lynx starts.

### Suffix-inference for exchange detection

Yahoo Finance tickers carry exchange information in their suffix (e.g., `.L`
for London, `.DE` for XETRA). The fetcher module infers the exchange from the
ticker suffix when no explicit exchange is provided. This lets users add
positions with just a ticker symbol while still getting correct exchange
metadata.

### Optional cost tracking

The `avg_purchase_price` column is nullable. When omitted, Lynx still tracks
the position and shows its current market value, but all P&L fields display
"Not tracked". This is intentional: many users want to monitor holdings they
acquired at unknown or irrelevant cost bases (gifts, transfers, long-held
positions). Forcing a price would produce misleading P&L numbers.

### Development mode as default

The `--devel-mode` flag (which uses a temporary database) is the default. This
protects users from accidentally modifying their real portfolio while
experimenting. Production mode must be explicitly opted into with
`--production-mode`.

### WAL mode for SQLite

WAL (Write-Ahead Logging) is enabled on every database connection. It allows
concurrent readers without blocking writes, which matters when the API server
handles multiple requests or when the TUI refreshes data in the background.
