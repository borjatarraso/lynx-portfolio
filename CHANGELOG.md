# Changelog

All notable changes to **Lynx Portfolio** are documented in this file.  
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).  
Versioning follows Semantic Versioning — minor releases (`v0.x`) iterate features;
`v1.0` marks the first production-stable major release.

---

## [Unreleased / v0.2-dev] — 2026-04-12

### Added
- **Multi-market exchange resolution**: instruments are now resolved to a specific
  exchange with the correct ticker suffix (e.g. `NESN.SW`, `VWCE.DE`, `IWDA.AS`).
- **`--exchange` / `-e` flag** on the `add` command: specify the preferred exchange
  suffix (e.g. `--exchange SW` for SIX Swiss, `--exchange DE` for XETRA,
  `--exchange AS` for Euronext Amsterdam).
- **Ticker suffix support**: if you type `NESN.SW` directly, the suffix is respected
  and no market-search is performed.
- **ISIN → all markets expansion**: when an ISIN is provided, Lynx now searches
  Yahoo Finance both by ISIN and by the resolved base ticker, surfacing all available
  exchange listings (not just the primary one).
- **Interactive `markets` command**: shows all available exchanges for a ticker or ISIN.
- **Exchange columns in DB**: `exchange_code` (internal Yahoo code, e.g. `GER`) and
  `exchange_display` (human-readable, e.g. `Deutsche Börse XETRA`) stored per position.
- **Exchange column in portfolio table** and instrument detail view.
- **Automatic DB migration**: new columns are added to existing databases without
  losing data.
- **83-entry `YAHOO_EXCHANGE_INFO` mapping**: covers US, all major European markets
  (SIX, XETRA, Frankfurt, Stuttgart, Munich, Düsseldorf, Berlin, Hamburg, Euronext
  Paris/Amsterdam/Brussels/Lisbon/Dublin, Borsa Italiana, Madrid, LSE, Oslo, Stockholm,
  Copenhagen, Helsinki, Vienna, Warsaw, Athens) plus Americas and Asia-Pacific.
- **ISIN country-code heuristic**: auto-selects the most natural exchange for a given
  ISIN (e.g. `CH` → SIX Swiss, `DE` → XETRA, `FR` → Euronext Paris).

### Fixed
- Description field no longer produces double-period at end of sentence.
- `apply_cache_to_portfolio` now only updates fields that are actually present in
  the cache response.

### Changed
- **Share column alignment**: integer digits now align across all rows in the
  portfolio table. The ones digit of every share count falls at the same column
  position; decimal digits extend to the right only where present:
  ```
  6,789
    145
     23.5
  1,000.25
  ```
- ETFs and funds show decimals only when the stored value is actually fractional;
  whole-number holdings display without a decimal point.
- Equities (stocks) always display as integers; fractional input is rounded with a
  warning at add-time.

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
