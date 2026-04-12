# Lynx Portfolio

**Version:** v0.2 | **Python:** >= 3.9 | **License:** MIT

Lynx Portfolio is a command-line investment portfolio manager that tracks your
holdings, fetches live market data from Yahoo Finance, and converts everything
to EUR so you can see your real exposure at a glance.

## Features

- **Four interfaces** -- pick the one that fits your workflow:
  - Non-interactive CLI (`-ni`) for scripting and one-shot commands
  - Interactive REPL (`-i`) with tab completion
  - Full-screen TUI (`-tui`) built on Textual
  - REST API (`--api`) powered by Flask
- **Live market data** from Yahoo Finance via `yfinance`
- **ISIN resolution** through OpenFIGI
- **Automatic EUR conversion** -- forex rates fetched once per session
- **SQLite storage** with WAL mode for safe concurrent reads
- **Development mode** by default -- experiment without touching your real data
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
lynx -ni add AAPL 10 --price 185.50

# 3. List your portfolio
lynx -ni list
```

By default Lynx runs in **development mode** (temporary database). When you are
ready to use real data, switch to production:

```bash
lynx --production-mode -ni list
```

## Running modes

| Flag               | Database            | Use case               |
|--------------------|---------------------|------------------------|
| `--devel-mode`     | Temporary (default) | Testing and exploration|
| `--production-mode`| Persistent          | Real portfolio data    |

## Interfaces at a glance

| Flag    | Description                  | Example                          |
|---------|------------------------------|----------------------------------|
| `-ni`   | Non-interactive CLI          | `lynx -ni list`                  |
| `-i`    | Interactive REPL             | `lynx -i`                        |
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
lynx -ni list

# Directly
python lynx.py -ni list
```
