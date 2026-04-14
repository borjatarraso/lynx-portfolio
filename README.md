# Lynx Portfolio

**Investment portfolio tracker with live market data**

[![Python](https://img.shields.io/badge/python-%3E%3D3.9-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-BSD%203--Clause-green.svg)](LICENSE)

Lynx Portfolio is part of the **Lince Investor** suite. It tracks your
investment holdings, fetches live market data from Yahoo Finance, converts
everything to EUR, and shows your real exposure at a glance.

## Features

- **Four interfaces** -- choose what fits your workflow:
  - **Interactive REPL** (default) with command history and guided prompts
  - **Console mode** (`-c`) for scripting and one-shot commands
  - **Full-screen TUI** (`-tui`) built on [Textual](https://textual.textualize.io/)
  - **Graphical interface** (`-x`) with dark-themed tkinter dashboard
  - **REST API** (`--api`) powered by Flask
- **Live market data** from Yahoo Finance via `yfinance`
- **ISIN resolution** through OpenFIGI (no API key required)
- **Multi-exchange support** -- 80+ global exchanges with automatic suffix detection
- **Automatic EUR conversion** -- forex rates fetched once per session
- **Database encryption** -- password vault with Fernet + PBKDF2-HMAC-SHA256
- **Automatic backups** -- `.bak` created on every session open
- **Optional cost tracking** -- positions without `avg_purchase_price` show
  "Not tracked" instead of misleading zeros
- **SQLite storage** with WAL mode for safe concurrent reads
- **First-run setup wizard** -- graphical or terminal, launches automatically

## Installation

```bash
# Clone the repository
git clone https://github.com/borjatarraso/lynx-portfolio.git
cd lynx-portfolio

# Install in editable mode (creates the `lynx-portfolio` command)
pip install -e .
```

### Dependencies

| Package        | Purpose                            |
|----------------|------------------------------------|
| yfinance       | Market data from Yahoo Finance     |
| requests       | HTTP calls (OpenFIGI, etc.)        |
| rich           | Terminal tables and formatting     |
| textual        | Full-screen TUI framework          |
| flask          | REST API server                    |
| cryptography   | Database encryption (Fernet vault) |

All dependencies are installed automatically via `pip install -e .`.

## Quick Start

On the first run, the setup wizard launches automatically:

```bash
lynx-portfolio          # launches wizard, then interactive REPL
```

The wizard guides you through:
1. **Database location** -- where to store your portfolio
2. **Default interface** -- which mode to launch by default
3. **First instrument** -- optionally add a stock or ETF right away
4. **Encryption** -- optionally protect the database with a password

After setup, just run `lynx-portfolio` to start.

### Adding instruments

```bash
# Interactive REPL (default)
lynx-portfolio
# Then type: add

# Console mode (one-shot)
lynx-portfolio -c add --ticker AAPL --shares 10 --avg-price 185.50
lynx-portfolio -c add --isin CH0038863350 --shares 50 --exchange SW

# Bulk import from JSON
lynx-portfolio --import portfolio.json
```

### Viewing your portfolio

```bash
# Interactive REPL
lynx-portfolio
# Then type: list

# Console
lynx-portfolio -c list

# Full-screen TUI
lynx-portfolio -tui

# Graphical interface
lynx-portfolio -x

# REST API
lynx-portfolio --api
curl http://localhost:5000/api/portfolio
```

## Running Modes

| Flag           | Database                               | Use case                  |
|----------------|----------------------------------------|---------------------------|
| *(default)*    | Persistent (wizard on first run)       | Normal usage              |
| `--devel`      | Temporary, isolated (nothing persisted)| Testing and exploration   |
| `--production` | Persistent (explicit)                  | Scripting, CI             |

The `--devel` mode uses a completely isolated temporary database that is
automatically deleted when the session ends. No production data is ever
touched.

## Interfaces

### Interactive REPL (default)

```
lynx-portfolio
```

Commands: `list`, `add`, `show`, `update`, `delete`, `refresh`, `import`,
`clear-cache`, `markets`, `config`, `about`, `help`, `quit`.

### Console Mode (`-c`)

```bash
lynx-portfolio -c list
lynx-portfolio -c add --ticker MSFT --shares 5 --avg-price 420
lynx-portfolio -c show --ticker AAPL
lynx-portfolio -c delete --ticker AAPL --force
lynx-portfolio -c refresh
```

### Full-screen TUI (`-tui`)

```
lynx-portfolio -tui
```

Keybindings: `a` Add, `d` Delete, `e` Edit, `r` Refresh, `R` Refresh All,
`i` Import, `c` Clear Cache, `t` Theme, `?` About, `q` Quit.

### Graphical Interface (`-x`)

```
lynx-portfolio -x
```

Dark-themed dashboard with toolbar, portfolio table, detail views, and
modal dialogs for all operations.

### REST API (`--api`)

```bash
lynx-portfolio --api --port 5000
```

See [docs/api-reference.md](docs/api-reference.md) for all endpoints.

## Database Encryption

```bash
# Enable encryption
lynx-portfolio --encrypt

# Encrypted DB is auto-detected on subsequent runs
lynx-portfolio              # prompts for password

# Inline password (for scripting)
lynx-portfolio -d "password" -c list

# Remove encryption
lynx-portfolio --disable-encryption
```

## Backup and Restore

Backups are created automatically. To restore:

```bash
lynx-portfolio --restore
```

## JSON Import Format

```json
[
  {"ticker": "AAPL",    "shares": 10,   "avg_price": 150.00},
  {"ticker": "NESN.SW", "shares": 50,   "avg_price": 110.00, "isin": "CH0038863350"},
  {"ticker": "VWCE.DE", "shares": 23.5, "avg_price": 70.00,  "exchange": "DE"}
]
```

Required fields: `ticker`, `shares`. Optional: `avg_price`, `isin`, `exchange`.

## Configuration

Configuration is stored at `~/.config/lynx/config.json` (XDG standard).
The database is stored wherever you choose during setup (default:
`~/.local/share/lynx/portfolio.db`).

```bash
# Re-run configuration
lynx-portfolio --configure

# Re-run full setup wizard
lynx-portfolio -w
```

## Running Tests

```bash
# Unit tests (pytest)
pip install pytest
python -m pytest tests/ -v

# Robot Framework BDD tests
pip install robotframework
python -m robot tests/robot/
```

## Project Structure

```
lynx-portfolio/
  lynx_portfolio/           Python package
    __init__.py              Version, constants
    cli.py                   Argument parsing, entry point
    interactive.py           Interactive REPL
    tui.py                   Textual TUI
    gui.py                   Tkinter GUI
    api.py                   Flask REST API
    operations.py            Business logic
    database.py              SQLite layer
    cache.py                 Instrument cache
    fetcher.py               Yahoo Finance + OpenFIGI
    forex.py                 EUR conversion rates
    display.py               Rich terminal output
    config.py                XDG configuration
    vault.py                 Database encryption
    backup.py                Backup/restore
    wizard.py                Setup wizard (terminal)
  tests/
    test_vault.py            Vault unit tests
    test_default_mode.py     Default mode unit tests
    robot/                   Robot Framework BDD tests
  docs/
    user-guide.md            User guide
    api-reference.md         REST API reference
    architecture.md          Architecture and design
  examples/
    portfolio.json           Sample import file
  lynx-portfolio.py          Entry point script
  lynx-portfolio             Symlink launcher
  LICENSE                    BSD 3-Clause License
  pyproject.toml             Build configuration
```

## Documentation

- [User Guide](docs/user-guide.md) -- configuration, all interfaces, import, cache, encryption
- [API Reference](docs/api-reference.md) -- REST endpoints with curl examples
- [Architecture](docs/architecture.md) -- modules, data flow, schema, design decisions

## Author

**Borja Tarraso** -- <borja.tarraso@member.fsf.org>

## License

[BSD 3-Clause License](LICENSE)
