# Changelog

All notable changes to **Lynx Portfolio** are documented in this file.  
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).  
Versioning follows Semantic Versioning — minor releases (`v0.x`) iterate features;
`v1.0` marks the first production-stable major release.

---

## [Unreleased]

---

## [3.0] - 2026-04-22

Part of **Lince Investor Suite v3.0** coordinated release.

### Added
- Uniform PageUp / PageDown navigation across every UI mode (GUI, TUI,
  interactive, console). Scrolling never goes above the current output
  in interactive and console mode; Shift+PageUp / Shift+PageDown remain
  reserved for the terminal emulator's own scrollback.

### Changed
- TUI wires `lynx_investor_core.pager.PagingAppMixin` and
  `tui_paging_bindings()` into the main application.
- Graphical mode binds `<Prior>` / `<Next>` / `<Control-Home>` /
  `<Control-End>` via `bind_tk_paging()`.
- Interactive mode pages long output through `console_pager()` /
  `paged_print()`.
- New dependency on `lynx-investor-core>=2.0` for the shared pager module.

---

## [v2.0] — 2026-04-19

Major release — **Lince Investor Suite v2.0** unified release.

### Changed
- **Unified suite**: All Lince Investor projects (portfolio, fundamental,
  compare, investor-basic-materials, investor-energy) now share consistent
  version numbering, logos, keybindings, CLI patterns, export styling,
  installation instructions, and documentation structure.
- **TUI keybinding**: About is now `F1` (previously `?`) to match the
  standard across the suite.
- **Entry point**: `lynx-portfolio` console script now routes through
  `lynx_portfolio.__main__:main` for consistency with other suite projects.
- **Documentation**: Standardized installation section with clone + pip
  install steps and dependency table matching other suite projects.

---

## [v1.0] — 2026-04-15

First production-stable major release.

### Added
- **Logo display** across all interfaces: PNG logos in GUI (splash screen,
  toolbar, About dialog) and green block-character ASCII art in terminal
  modes (interactive, console, TUI About screen).
- **Logo assets**: `img/` directory with 5 PNG variants (large, medium,
  small, half, quarter) of the Lynx Portfolio shield logo.
- `lynx_portfolio/logo.py` module with path helpers and pre-rendered
  ASCII art constant.

### Changed
- First major release: all features, interfaces, encryption, validation,
  and error handling are considered production-stable.

---

## [v0.6] — 2026-04-14

### Added
- **Input validation module** (`validation.py`): centralised validators for
  tickers, ISINs, exchange suffixes, shares, prices, and search queries.
  Applied to all 5 interfaces (interactive, console, TUI, GUI, REST API).
- **50 new unit tests** in `test_validation.py` covering all validators
  with edge cases (empty, spaces, SQL injection, unicode, negative values,
  overlong strings, control characters).

### Fixed
- **Race condition in refresh**: `refresh_instrument_quiet()` now wraps all
  database/cache operations in try/except to prevent silent thread death
  during background refreshes.
- **Cache timestamp crash**: `datetime.fromisoformat()` calls now handle
  malformed timestamps instead of raising ValueError.
- **Config corruption**: `save_config()` now uses atomic writes (temp file +
  fsync + os.replace) to prevent partial config files on crash.
- **TUI refresh crash**: all `@work`-decorated methods in TUI now catch
  exceptions and display errors via Textual notifications instead of dying
  silently.
- **TUI import crash**: individual instrument failures during import no
  longer abort the entire batch.
- **REST API validation**: all `<ticker>` URL path parameters now validated
  via `validate_ticker()`, returning 400 JSON errors for malformed input.
  POST/PUT body values validated with `validate_shares()`/`validate_price()`.

---

## [v0.5] — 2026-04-14

### Added
- **Graphical setup wizard**: first-run wizard now shows native tkinter dialogs
  when using GUI mode (`-x`), with database location picker, default mode
  selection, instrument form, and encryption setup.
- **TUI search auto-fill**: search results in the TUI Add screen now
  auto-populate ticker, ISIN, and exchange suffix when a result is selected.
- **Project README.md**: comprehensive documentation for GitHub with
  installation, quick start, interfaces, encryption, testing, and project
  structure.
- **BSD 3-Clause LICENSE file** at project root with full license text.
- **About dialog** (GUI): custom dialog with author, clickable license URL,
  and scrollable full license text.

### Fixed
- **First-run wizard not launching**: `_setup_default_mode()` now checks
  that the database file actually exists on disk, not just that `db_path`
  is set in config. A stale config with a deleted DB correctly triggers
  the wizard.
- **Wizard crash with encryption + first instrument**: reordered wizard
  steps so encryption runs last (after adding instruments), preventing the
  "database file not found" crash.
- **Devel mode data isolation**: `--default-mode` no longer modifies
  production config when `--devel` is active. All devel-mode operations
  use an isolated temporary database.
- **TUI animation black screen**: renamed internal `_animate` method to
  avoid collision with Textual's `Widget._animate` BoundAnimator slot.
- **TUI keybinding reliability**: added `priority=True` and `on_key()`
  fallback for keybindings that were swallowed by focused widgets.
- **GUI toolbar layout**: reorganised buttons into logical groups with
  icons (Portfolio, Data, Import/Cache, About/Quit).

### Changed
- **License**: upgraded to BSD 3-Clause with full text in `__init__.py`,
  `LICENSE` file, and GUI About dialog.
- Version bumped to v0.5.

---

## [v0.4] — 2026-04-14

### Changed
- **Interactive mode is now the default**: running `lynx` without a mode flag
  launches the interactive REPL. The previous non-interactive (console) mode is
  now available via `-c` / `--console`.
- **Shortened run-mode flags**: `--production-mode` → `--production`,
  `--devel-mode` → `--devel`.
- **Smart run-mode default**: if a database directory is configured, Lynx
  automatically uses production mode. Falls back to devel only when no
  configuration exists.
- **Database encryption (vault)**: password-based AES encryption for the
  portfolio database using Fernet + PBKDF2-HMAC-SHA256 key derivation.
  New flags: `--encrypt`, `--disable-encryption`, `--decrypt` / `-d`.
- **Backup and restore**: automatic `.bak` backups on every session open.
  Restore with `--restore` / `-r`.
- **Setup wizard** (`-w` / `--wizard`): guided first-time setup for database
  location, encryption, default mode, and first instrument.
- **Instrument search by name** (`--name` / `-n`): available in console `add`
  and `show` subcommands, interactive REPL, and TUI.
- **Configurable default interface mode** (`--default-mode` / `-dm`): persist
  your preferred interface (interactive, console, tui, gui) to config.
- **Parallel refresh**: `refresh_all()` uses ThreadPoolExecutor for concurrent
  data fetching (4 parallel workers by default).
- Legacy `-ni` flag mapped to `--console` for backwards compatibility.

---

## [v0.3] — 2026-04-12

### Added
- **REST API** (`--api` / `--port`): Flask-based API with 12 endpoints for portfolio
  CRUD, refresh, cache management, and forex rates. Instruments include computed fields
  (market_value, pnl, pnl_pct, EUR equivalents). Start with `lynx --production --api`.
- **Optional cost tracking**: `avg_purchase_price` is now optional. Instruments without
  it show "Not tracked" / "—" and are excluded from Invested / P&L totals.
- **Notifier abstraction** in `operations.py`: decouples business logic from Rich terminal
  display, enabling headless API operation.
- **Robot Framework BDD tests** (`tests/robot/`): 9 CLI tests + 12 API tests using
  Given/When/Then format with temp database isolation.
- **Project documentation** (`docs/`): README, user guide, API reference, architecture.
- **12 custom TUI themes**: matrix, monochrome, amber-terminal, phosphor-blue, cyberpunk,
  ocean-deep, sunset, arctic, synthwave, forest, blood-moon, high-contrast. Press `t` to cycle.
- **`--import FILE`** top-level flag for bulk JSON import without `-ni` subcommand.
- **Suffix-fallback search**: when a plain ticker (e.g. "NAS") returns no equities,
  common exchange suffixes (.OL, .TO, .V, .DE, etc.) are tried automatically.

### Fixed
- **Interactive prompt corruption**: replaced all Rich Prompt.ask / Confirm.ask calls
  with plain `_ask()` / `_confirm()` wrappers — question text prints via Rich, input
  reads on a separate `> ` line. Backspace and arrows can never corrupt the question.
- **DisplayNotifier infinite recursion**: the Notifier was calling `_notifier.info()`
  instead of `display.info()`, causing a stack overflow on every status message.
- **TUI P&L column inconsistency**: the TUI table showed a native-currency P&L column
  alongside EUR columns; now matches the CLI behaviour (EUR P&L replaces P&L when
  non-EUR currencies are present).
- **`_ensure_dir` crash on bare filename**: `os.makedirs("")` raised `FileNotFoundError`
  when the DB path had no directory component.
- **Clear-cache safety**: all modes now show a blinking red warning listing all portfolio
  instruments, require Enter to continue, then Abort/Continue (Abort default).

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
  from the command line, without needing `-c import --file` or any interactive mode.
  Optional `--exchange SUFFIX` sets the default exchange for all entries in the file.
  Example: `lynx --production --import portfolio.json --exchange V`
  The existing `-c import --file` subcommand is unchanged.

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
  `--production`.
- **Configurable data directory**: the database is no longer hardcoded to
  `~/.lynx/`. The user chooses the location during `--configure`.
- **`import` subcommand**: bulk-add instruments from a JSON file via
  `lynx -c import --file portfolio.json`. Each entry requires `ticker`,
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
