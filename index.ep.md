---
ep_version: 1
project: lynx-portfolio
title: Lynx Portfolio
status: DORMANT
last_touched: 2026-04-28
last_touched_text: 28 April 2026
section: sub
category: investments
generated: 2026-08-15
ep_locked: false   # set true and this file is never regenerated
---

# Lynx Portfolio

> Show the investments portfolio

🔴 **DORMANT** · last touched **28 April 2026** (last commit)

---

## What this is

**Investment portfolio tracker with live market data**

Lynx Portfolio is part of the **Lince Investor** suite. It tracks your investment holdings, fetches live market data from Yahoo Finance, converts everything to EUR, and shows your real exposure at a glance.

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

All dependencies are installed automatically via `pip install -e .`.

On the first run, the setup wizard launches automatically:

The wizard guides you through:
1. **Database location** -- where to store your portfolio
2. **Default interface** -- which mode to launch by default
3. **First instrument** -- optionally add a stock or ETF right away
4. **Encryption** -- optionally protect the database with a password

After setup, just run `lynx-portfolio` to start.

The `--devel` mode uses a completely isolated temporary database that is automatically deleted when the session ends. No production data is ever touched.

Commands: `list`, `add`, `show`, `update`, `delete`, `refresh`, `import`, `clear-cache`, `markets`, `config`, `about`, `help`, `quit`.

Keybindings: `a` Add, `d` Delete, `e` Edit, `r` Refresh, `R` Refresh All, `i` Import, `c` Clear Cache, `t` Theme, `F1` About, `q` Quit.

Dark-themed dashboard with toolbar, portfolio table, detail views, and modal dialogs for all operations.

See [docs/api-reference.md](docs/api-reference.md) for all endpoints.

Backups are created automatically. To restore:

Required fields: `ticker`, `shares`. Optional: `avg_price`, `isin`, `exchange`.

Configuration is stored at `~/.config/lynx/config.json` (XDG standard). The database is stored wherever you choose during setup (default: `~/.local/share/lynx/portfolio.db`).

- [User Guide](docs/user-guide.md) -- configuration, all interfaces, import, cache, encryption
- [API Reference](docs/api-reference.md) -- REST endpoints with curl examples
- [Architecture](docs/architecture.md) -- modules, data flow, schema, design decisions
- [Testing](docs/testing.md) -- running pytest and Robot Framework, writing new tests

**Borja Tarraso** -- <borja.tarraso@member.fsf.org>

[BSD 3-Clause License](LICENSE)

This project is part of the **Lince Investor Suite**, authored and signed by

**Borja Tarraso** &lt;[borja.tarraso@member.fsf.org](mailto:borja.tarraso@member.fsf.org)&gt; Licensed under BSD-3-Clause.

## Start here

- [`README.md`](README.md) — what the project is, in its own words
- [`CLAUDE.md`](CLAUDE.md) — working agreement for a session in this repo
- [`docs/README.md`](docs/README.md) — documentation index

## Run it

```bash
cd ~/claude/lince-investor/lynx-portfolio
lynx-portfolio                        # console entry point
python3 -m lynx_portfolio             # runnable package
```

## The rest of it

**Directories**

- `data/` — 2 entries
- `docs/` — 12 entries
- `examples/` — 1 entry
- `img/` — 6 entries
- `lynx_portfolio/` — 29 entries
- `lynx_portfolio.egg-info/` — 6 entries
- `mobile/` — 10 entries
- `tests/` — 13 entries

**Other documentation**

- [`CHANGELOG.md`](CHANGELOG.md)

**`docs/`** holds 12 files.

**Build / config**: `pyproject.toml`

---

## Ownership

<img src="https://www.cortex-university.com/static/brand/lince-logo.png" alt="Lince" width="96" height="96" align="left" style="margin-right:16px" />

**Lynx Portfolio is proudly part of Lince.**

| Company ID | Headquarters |
|---|---|
| 3015071-2 | Helsinki, Finland |

Part of the LINCE company · © All rights reserved


<sub>Standard entry-point card (`index.ep.md`, format v1) — generated 2026-08-15 by Lynx Factory. Regenerating overwrites this file unless `ep_locked: true`.</sub>
