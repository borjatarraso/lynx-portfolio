# Changelog

All notable changes to **Lynx Portfolio** are documented in this file.  
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).  
Versioning follows Semantic Versioning — minor releases (`v0.x`) iterate features;
`v1.0` marks the first production-stable major release.

---

## [v0.1] — 2026-04-12

### Added
- Initial release of **Lynx Portfolio Manager**.
- Add investment instruments by **ticker** and/or **ISIN** (`add` command).
- ISIN → ticker resolution via [OpenFIGI](https://www.openfigi.com/) (free, no API key).
- Live instrument data fetched from **Yahoo Finance** (`yfinance`):
  - Full name, current price, currency, sector, industry, one-sentence description.
- Local **SQLite** database (`~/.lynx/portfolio.db`) for portfolio positions.
- **Local cache** (same DB) with configurable TTL (default 1 hour).
- **Interactive mode** (`-i` / `--interactive`): REPL with guided prompts.
- **Non-interactive mode** (`-ni` / `--non-interactive`) with subcommands:
  - `add`, `list`, `show`, `update`, `delete`, `refresh`
- Cache management flags:
  - `-dc` / `--delete-cache` — wipe entire cache.
  - `-rc` / `--refresh-cache` — re-fetch live data for all positions.
  - `-arc=SECONDS` / `--auto-refresh-cache=SECONDS` — background auto-refresh.
- **Portfolio table** with P&L per position (colour-coded) and totals summary.
- **Detailed instrument view** (`show`) with all stored fields.
- `-v` / `--version` flag.
- `-h` / `--help` flag (built-in argparse).
- Git version control initialised on `main`; branch `release/v0.1` created.
