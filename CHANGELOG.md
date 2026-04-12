# Changelog

All notable changes to **Lynx Portfolio** are documented in this file.  
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).  
Versioning follows Semantic Versioning — minor releases (`v0.x`) iterate features;
`v1.0` marks the first production-stable major release.

---

## [Unreleased]

### Fixed
- **TSXV / TSX Venture Exchange stocks not recognised** (e.g. FUU.V — F3 Uranium Corp):
  Yahoo Finance's Search API returns exchange code `"VAN"` for TSXV (not the previously
  assumed `"CVE"`) and `"TOR"` for TSX (not `"TSX"`). Both codes were absent from
  `PRIMARY_EXCHANGE_CODES`, so TSXV/TSX results were silently filtered out and a wrong
  instrument was picked instead.
  - Added `"TOR"` and `"VAN"` as the canonical codes; kept `"TSX"` and `"CVE"` as
    legacy aliases so existing portfolios are unaffected.
  - Updated `ISIN_COUNTRY_TO_EXCHANGE_CODE["CA"]` to `"TOR"`; `pick_best_market` now
    tries all Canadian exchange codes in order (TOR → TSX → VAN → CVE → NEO → CNQ)
    so TSXV listings are found when no TSX listing exists.
  - Added suffix-inference fallback in `search_markets`: when Yahoo returns an
    unrecognised or mismatched exchange code, the symbol's suffix (e.g. `.V`, `.TO`)
    is used as ground truth to infer the correct exchange — making market detection
    resilient to future Yahoo code changes.
- **OTC Quoted Board stocks not recognised**: Yahoo returns exchange code `"OQB"` for
  OTC Quoted Board (not the old `"OBB"` alias). Added `"OQB"` alongside the legacy
  `"OBB"` entry. Also added `"OTC"` (generic OTC) and `"GREY"` (grey market).

### Added
- **Expanded global exchange coverage** in `YAHOO_EXCHANGE_INFO`:
  - Canada: `TOR` (TSX), `VAN` (TSXV/CDNX), `CNQ` (Canadian Securities Exchange)
  - Americas: `SGO` (Bolsa de Santiago), `BUE` (Buenos Aires)
  - Asia-Pacific: `NZX` (New Zealand), `BSE`/`NSE` (India), `SHH`/`SHZ` (China),
    `SET` (Thailand), `KLS` (Malaysia), `JKT` (Indonesia)
  - Africa: `JSE` (Johannesburg)
- **`ISIN_COUNTRY_TO_EXCHANGE_CODE`**: added `NZ`, `IN`, `ZA` country mappings.

### Added
- **`--import FILE`** top-level flag: bulk-add instruments from a JSON file directly
  from the command line, without needing `-ni import --file` or any interactive mode.
  Optional `--exchange SUFFIX` sets the default exchange for all entries in the file.
  Example: `lynx --production-mode --import portfolio.json --exchange V`
  The existing `-ni import --file` subcommand is unchanged.

- **EUR currency conversion** using Yahoo Finance forex rates (`yfinance`):
  - Rates are fetched once per session at startup for all non-EUR currencies in the portfolio.
  - Symbol format: `{CCY}EUR=X` (e.g. `USDEUR=X`) — 1 unit of CCY expressed in EUR.
  - Portfolio table gains **EUR Val** and **EUR P&L** columns when any non-EUR instrument is present.
  - Summary panel shows EUR totals (Invested, Market Value, P&L) and the exchange rates applied (e.g. `USD/EUR=0.9234, CHF/EUR=1.0821`).
  - Instrument detail view (`show`) gains **Total Invested (EUR)**, **Market Value (EUR)**, and **P&L (EUR)** rows for non-EUR instruments.
  - TUI mode (`-tui`) also shows EUR Val / EUR P&L columns and EUR rows in the detail screen.
  - New `forex.py` module: `fetch_session_rates()`, `get_session_rates()`, `to_eur()`.
- **readline cursor fix** (interactive mode): ANSI colour codes in the `lynx>` prompt are now wrapped with `\001`/`\002` (readline's `RL_PROMPT_START_IGNORE`/`RL_PROMPT_END_IGNORE` markers), so left/right arrow-key navigation no longer jumps before the prompt text.

- **Full-screen TUI mode** (`-tui` / `--textual-ui`): keyboard-driven interface built
  with [Textual](https://textual.textualize.io/), the modern Python TUI framework
  from the Rich team.
  - Portfolio table with arrow-key navigation, zebra-striped rows, and row selection.
  - Press **Enter** on a row to see the detailed instrument view.
  - **Keybindings**: `a` Add, `d` Delete, `e` Edit, `r` Refresh, `R` Refresh All,
    `i` Import JSON, `c` Clear Cache, `q` Quit, `Esc` Back.
  - Add / Edit / Import screens with form inputs and async background API calls.
  - Confirmation dialog for delete (Yes/No or `y`/`n`).
  - Header with clock, footer showing all available keybindings.
  - Color scheme: cyan accents, green/red P&L, yellow warnings, magenta highlights.

---

## [v0.2] — 2026-04-12

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

- **`--configure` option**: interactive wizard to set up the database directory.
  Configuration is stored at `$XDG_CONFIG_HOME/lynx/config.json`
  (default `~/.config/lynx/config.json`). Required before first use in
  `--production-mode`.
- **Configurable data directory**: the database is no longer hardcoded to
  `~/.lynx/`. The user chooses the location during `--configure`.
- **`import` subcommand**: bulk-add instruments from a JSON file via
  `lynx -ni import --file portfolio.json`. Each entry requires `ticker`,
  `shares`, `avg_price`; optional `isin`, `exchange`. Example file included
  at `examples/portfolio.json`.
- **Interactive `import` and `config` commands**: `import <file.json>` and
  `config` available inside the REPL.

### Fixed
- Description field no longer produces double-period at end of sentence.
- `apply_cache_to_portfolio` now only updates fields that are actually present in
  the cache response.
- **cache.py double DB hit**: `cache.get()` now calls `cache_get()` once and
  computes age from the returned `cached_at` field instead of issuing two queries.
- **SQLite connection robustness**: added WAL journal mode and 10-second write
  timeout to prevent `database is locked` errors from the auto-refresh thread.
- **Suffixed ticker hardcodes `quote_type: "EQUITY"`**: tickers with a suffix
  (e.g. `VWCE.DE`) no longer get a synthetic `EQUITY` type; the actual type is
  resolved from `fetch_instrument_data`, preventing incorrect fractional-share
  warnings on ETFs.
- **OpenFIGI preference order**: `_isin_to_ticker_openfigi` now builds a dynamic
  preference list from the ISIN country code instead of always preferring Swiss
  then German exchanges.
- **`fetch_instrument_data` empty-dict guard**: checks `not info` before checking
  individual keys, correctly handling delisted tickers that return `{}`.
- **`_first_sentence` unbounded length**: output is now capped at 300 characters.
- **Interactive `update` ignores return value**: `_cmd_update` now checks the
  `update_instrument()` return value and reports errors when the ticker is not
  found.
- **Portfolio totals inflated when price is missing**: `display_portfolio` no
  longer adds cost basis to market value for positions without a price; a footnote
  shows how many positions were excluded.
- **`_price_str` decimal inconsistency**: instrument detail view now uses 2
  decimal places (matching the portfolio table).
- **Redundant OpenFIGI call in `operations.py`**: removed the fallback call to
  `_isin_to_ticker_openfigi` which duplicated work already done by
  `resolve_markets_for_input`.

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
- Local **SQLite** database for portfolio positions.
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
