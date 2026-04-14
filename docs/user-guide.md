# User Guide

This guide covers day-to-day usage of Lynx Portfolio across all four
interfaces.

## Configuration

Run the configuration wizard to set your database directory:

```bash
lynx-portfolio --configure
```

The resulting config is stored at `~/.config/lynx/config.json`. It contains the
path where Lynx will create and look for its SQLite database files.

## First Run and Setup

On the very first run (no database configured), Lynx automatically launches the
**setup wizard**. The wizard walks you through choosing a database directory,
optionally enabling encryption, and adding your first instrument.

After the wizard completes, the database file is created (even if empty) and
Lynx enters the interactive REPL. On subsequent runs, Lynx opens the existing
database directly — no wizard.

If you quit with an empty portfolio, Lynx reminds you that you can re-run the
wizard at any time with `lynx-portfolio -w`.

## Production vs Development mode

By default Lynx runs in **production mode**, using the persistent database. If
no database is configured yet, the setup wizard runs automatically.

Use `--devel` to experiment with a temporary database:

```bash
lynx-portfolio --devel                # temporary DB, nothing persisted
lynx-portfolio --production -c list   # explicitly force production mode
```

## Console mode (`-c`)

Best for scripting, cron jobs, and quick one-liners.

### Subcommands

| Command   | Description                       | Example                                           |
|-----------|-----------------------------------|----------------------------------------------------|
| `add`     | Add a new position                | `lynx-portfolio -c add --ticker AAPL --shares 10 --avg-price 185.50` |
| `add`     | Add by name search                | `lynx-portfolio -c add --name "Apple" --shares 10`           |
| `list`    | Show all portfolio positions      | `lynx-portfolio -c list`                                     |
| `show`    | Show details for one instrument   | `lynx-portfolio -c show --ticker AAPL`                       |
| `show`    | Show by name search               | `lynx-portfolio -c show --name "Apple"`                      |
| `update`  | Update shares or avg price        | `lynx-portfolio -c update AAPL --shares 15`          |
| `delete`  | Remove a position                 | `lynx-portfolio -c delete AAPL`                      |
| `refresh` | Refresh market data for a ticker  | `lynx-portfolio -c refresh AAPL`                     |
| `import`  | Import positions from JSON        | `lynx-portfolio -c import portfolio.json`            |

### Examples

```bash
# Add a position without cost tracking (avg_purchase_price omitted)
lynx-portfolio -c add MSFT 5

# Add with cost tracking
lynx-portfolio -c add MSFT 5 --price 420.00

# Update only the share count
lynx-portfolio -c update MSFT --shares 10

# Refresh all cached data
lynx-portfolio -rc
```

## Interactive REPL (default)

Launch with:

```bash
lynx-portfolio
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
lynx-portfolio -tui
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
lynx-portfolio --api
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

## First-time Setup Wizard (`-w`)

Run the wizard for a guided first-time setup:

```bash
lynx-portfolio -w
```

The wizard walks you through:

1. **Database location** — Choose where to store the portfolio database
   (default: `~/.local/share/lynx`). If a database already exists, you are
   warned and can choose to replace it or pick a different directory.
2. **Encryption** — Optionally encrypt the database with a password vault.
3. **First instrument** — Add your first stock or ETF right away.

## Database Encryption (Vault)

Lynx can encrypt your portfolio database with a password to protect your
investment data.

### Enable encryption

```bash
lynx-portfolio --production --encrypt
# or
lynx-portfolio --production -en
```

You will be asked to set a password three times (enter, confirm, confirm again).
While typing, press `*` to toggle between showing and hiding the password.

The plain database is encrypted into `portfolio.db.enc` + `portfolio.db.salt`
and the unencrypted file is removed.

### Using an encrypted database

On subsequent runs Lynx auto-detects the encrypted vault and prompts for the
password:

```bash
lynx-portfolio --production -i        # prompts for password automatically
lynx-portfolio --production -tui      # same
lynx-portfolio --production -x        # same
```

For non-interactive / scripted use, pass the password inline:

```bash
lynx-portfolio --production -d "mypassword" -c list
lynx-portfolio --production --decrypt "mypassword" -c show --ticker AAPL
```

### Disable encryption

To permanently remove encryption and return to a plain database:

```bash
lynx-portfolio --production --disable-encryption
# or
lynx-portfolio --production -de
```

You will be asked for the current password. The vault files are removed and
the plain database is restored.

### Signal safety

When the vault is open, Lynx installs signal handlers for `SIGINT` (Ctrl+C),
`SIGTERM`, and `SIGHUP`. If the process is interrupted, the vault is
re-encrypted and the temporary working file is securely deleted before exit.

## Backup and Restore

Lynx automatically creates a backup (`.bak`) of the database each time it is
opened. For encrypted databases the backup covers the `.enc` and `.salt` files.

### Restore from backup

```bash
lynx-portfolio --production --restore
# or
lynx-portfolio --production -r
```

Lynx detects whether the backup is for a plain or encrypted database and
restores accordingly.

## Cache management

Lynx caches instrument metadata in the SQLite database to avoid redundant API
calls.

| Action                   | CLI flag / command        |
|--------------------------|---------------------------|
| Delete entire cache      | `lynx-portfolio -dc`                |
| Refresh entire cache     | `lynx-portfolio -rc`                |
| Auto-refresh on interval | `lynx-portfolio -arc=3600` (seconds)|
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

- On first run, the setup wizard launches automatically. After that, just
  run `lynx-portfolio` to start the interactive REPL.
- Use `--devel` while learning the tool — it creates a temporary database.
- The `-v` flag enables verbose output, useful for debugging data-fetch issues.
- Bulk-load your portfolio from JSON:
  ```bash
  lynx --import portfolio.json
  ```
- Positions added without a price can be updated later:
  ```bash
  lynx -c update AAPL --price 185.50
  ```
