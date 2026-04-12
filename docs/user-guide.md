# User Guide

This guide covers day-to-day usage of Lynx Portfolio across all four
interfaces.

## Configuration

Run the configuration wizard to set your database directory:

```bash
lynx --configure
```

The resulting config is stored at `~/.config/lynx/config.json`. It contains the
path where Lynx will create and look for its SQLite database files.

## Development vs Production mode

Lynx defaults to **development mode** (`--devel-mode`), which uses a temporary
database that is discarded when the session ends. This is useful for testing
imports, trying commands, or exploring the tool without risk.

Switch to **production mode** to persist data across sessions:

```bash
lynx --production-mode -ni list
```

You can combine the mode flag with any interface flag.

## Non-interactive CLI (`-ni`)

Best for scripting, cron jobs, and quick one-liners.

### Subcommands

| Command   | Description                       | Example                                    |
|-----------|-----------------------------------|--------------------------------------------|
| `add`     | Add a new position                | `lynx -ni add AAPL 10 --price 185.50`     |
| `list`    | Show all portfolio positions      | `lynx -ni list`                            |
| `show`    | Show details for one instrument   | `lynx -ni show AAPL`                       |
| `update`  | Update shares or avg price        | `lynx -ni update AAPL --shares 15`         |
| `delete`  | Remove a position                 | `lynx -ni delete AAPL`                     |
| `refresh` | Refresh market data for a ticker  | `lynx -ni refresh AAPL`                    |
| `import`  | Import positions from JSON        | `lynx -ni import portfolio.json`           |

### Examples

```bash
# Add a position without cost tracking (avg_purchase_price omitted)
lynx -ni add MSFT 5

# Add with cost tracking
lynx -ni add MSFT 5 --price 420.00

# Update only the share count
lynx -ni update MSFT --shares 10

# Refresh all cached data
lynx -rc
```

## Interactive REPL (`-i`)

Launch with:

```bash
lynx -i
```

You get a prompt where you can type commands interactively.

### Available commands

| Command        | Alias | Description                          |
|----------------|-------|--------------------------------------|
| `list`         | `ls`  | List all positions                   |
| `add`          |       | Add a position (prompts for details) |
| `show`         |       | Show instrument detail               |
| `update`       |       | Update a position                    |
| `delete`       |       | Remove a position                    |
| `refresh`      |       | Refresh market data                  |
| `import`       |       | Import from JSON file                |
| `clear-cache`  |       | Clear the instrument cache           |
| `markets`      |       | Show market/exchange info            |
| `config`       |       | Show current configuration           |
| `help`         |       | Print available commands             |
| `quit`         |       | Exit the REPL                        |

## Full-screen TUI (`-tui`)

Launch with:

```bash
lynx -tui
```

The TUI displays your portfolio in a table with live data. Navigate with the
keyboard.

### Keybindings

| Key     | Action                        |
|---------|-------------------------------|
| `a`     | Add a new position            |
| `d`     | Delete selected position      |
| `e`     | Edit selected position        |
| `r`     | Refresh selected instrument   |
| `R`     | Refresh all instruments       |
| `i`     | Import from JSON file         |
| `c`     | Clear instrument cache        |
| `t`     | Cycle through themes          |
| `q`     | Quit                          |
| `Enter` | Show detail view              |
| `Esc`   | Go back / close dialog        |

### Theme cycling

Press `t` in the TUI to cycle through available color themes. The current theme
is applied immediately.

## REST API (`--api`)

Start the API server (Flask, default port 5000):

```bash
lynx --api
```

The server exposes a full CRUD interface for portfolio management. See the
[API Reference](api-reference.md) for every endpoint.

Quick smoke test:

```bash
curl http://localhost:5000/api/health
# {"status": "ok", "timestamp": "2026-04-12T10:00:00Z"}
```

## JSON import format

The `import` command (available in all interfaces) expects a JSON file with an
array of position objects:

```json
[
  {
    "ticker": "AAPL",
    "shares": 10,
    "avg_price": 185.50,
    "isin": "US0378331005",
    "exchange": "NMS"
  },
  {
    "ticker": "MSFT",
    "shares": 5
  }
]
```

Only `ticker` and `shares` are required. The remaining fields are optional:

| Field      | Required | Description                            |
|------------|----------|----------------------------------------|
| `ticker`   | Yes      | Yahoo Finance ticker symbol            |
| `shares`   | Yes      | Number of shares held                  |
| `avg_price`| No       | Average purchase price (cost tracking) |
| `isin`     | No       | ISIN code for the instrument           |
| `exchange` | No       | Exchange identifier                    |

Positions without `avg_price` will display "Not tracked" for P&L fields.

## Cache management

Lynx caches instrument metadata in the SQLite database to avoid redundant API
calls.

| Action                   | CLI flag / command        |
|--------------------------|---------------------------|
| Delete entire cache      | `lynx -dc`                |
| Refresh entire cache     | `lynx -rc`                |
| Auto-refresh on interval | `lynx -arc=3600` (seconds)|
| Clear cache (REPL)       | `clear-cache`             |
| Clear cache (TUI)        | Press `c`                 |
| Clear cache (API)        | `DELETE /api/cache?force=true` |
| Clear single ticker      | `DELETE /api/cache/<ticker>`   |

The `-arc` flag sets an automatic refresh interval in seconds. For example,
`-arc=3600` refreshes the cache every hour.

## Forex conversion

Lynx fetches EUR exchange rates once per session via yfinance. All monetary
values (market value, P&L) are shown in both the instrument's native currency
and EUR. The rates are cached in memory for the duration of the session -- no
repeated network calls.

You can inspect the current rates through the API:

```bash
curl http://localhost:5000/api/forex/rates
```

## Tips

- Use `--devel-mode` (the default) while learning the tool. Switch to
  `--production-mode` when you are confident in your workflow.
- The `-v` flag enables verbose output, useful for debugging data-fetch issues.
- Combine `--import` with `--production-mode` to bulk-load your real portfolio:
  ```bash
  lynx --production-mode --import portfolio.json
  ```
- Positions added without a price can be updated later:
  ```bash
  lynx -ni update AAPL --price 185.50
  ```
