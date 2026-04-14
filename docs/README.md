# Lynx Portfolio

**Version:** v0.4 | **Python:** >= 3.9 | **License:** BSD

Lynx Portfolio is a command-line investment portfolio manager that tracks your
holdings, fetches live market data from Yahoo Finance, and converts everything
to EUR so you can see your real exposure at a glance.

## Features

- **Four interfaces** -- pick the one that fits your workflow:
  - Interactive REPL (default) with command history
  - Console mode (`-c`) for scripting and one-shot commands
  - Full-screen TUI (`-tui`) built on Textual
  - REST API (`--api`) powered by Flask
- **Live market data** from Yahoo Finance via `yfinance`
- **ISIN resolution** through OpenFIGI
- **Automatic EUR conversion** -- forex rates fetched once per session
- **SQLite storage** with WAL mode for safe concurrent reads
- **Smart mode selection** -- uses persistent DB if configured, devel otherwise
- **Optional cost tracking** -- positions without `avg_purchase_price` display
  "Not tracked" instead of misleading zeros

## Installation

```bash
# Clone the repository
git clone <repo-url>
cd lynx-portfolio

# Install in editable mode (creates the `lynx` command)
pip install -e .
```

### Dependencies

| Package    | Purpose                        |
|------------|--------------------------------|
| yfinance   | Market data from Yahoo Finance |
| requests   | HTTP calls (OpenFIGI, etc.)    |
| rich       | Terminal tables and formatting |
| textual    | Full-screen TUI framework      |
| flask      | REST API server                |

## Quick start

```bash
# 1. Configure the database directory (stored at ~/.config/lynx/config.json)
lynx --configure

# 2. Add a position
lynx -c add AAPL 10 --price 185.50

# 3. List your portfolio
lynx -c list
```

Lynx automatically uses the persistent database if configured. For testing,
use `--devel` to get a temporary database.

## Running modes

| Flag               | Database                                     | Use case               |
|--------------------|----------------------------------------------|------------------------|
| *(default)*        | Persistent if configured, temporary otherwise | Normal usage           |
| `--devel`          | Temporary                                    | Testing and exploration|
| `--production`     | Persistent                                   | Explicit production    |

## Interfaces at a glance

| Flag    | Description                  | Example                          |
|---------|------------------------------|----------------------------------|
| *(none)*| Interactive REPL (default)   | `lynx`                           |
| `-c`    | Console (non-interactive)    | `lynx -c list`                   |
| `-tui`  | Textual full-screen TUI      | `lynx -tui`                      |
| `--api` | REST API (Flask, port 5000)  | `lynx --api`                     |

## Top-level flags

| Flag              | Description                           |
|-------------------|---------------------------------------|
| `--configure`     | Set up database directory             |
| `--import FILE`   | Import positions from a JSON file     |
| `-dc`             | Delete the instrument cache           |
| `-rc`             | Refresh the instrument cache          |
| `-arc=SECONDS`    | Auto-refresh cache interval           |
| `-v`              | Verbose output                        |

## Documentation

- [User Guide](user-guide.md) -- configuration, interfaces, import format,
  cache management
- [API Reference](api-reference.md) -- every REST endpoint with curl examples
- [Architecture](architecture.md) -- modules, data flow, schema, design
  decisions

## Entry points

```bash
# Via pip-installed command
lynx -c list

# Directly
python lynx.py -c list
```
