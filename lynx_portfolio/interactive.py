"""
Interactive REPL mode for Lynx Portfolio.
"""

import sys
from typing import Optional, List, Dict

from rich.table import Table
from rich import box

from lynx_investor_core.pager import console_pager, paged_print

from . import ABOUT_LINES
from . import database, cache, display
from .operations import add_instrument, refresh_instrument, refresh_all

# ---------------------------------------------------------------------------
# In-session readline history (↑/↓ arrow navigation).
# readline is imported for its side-effect: it hooks into Python's input()
# and enables history navigation automatically.  No history file is written,
# so nothing survives after the process exits.
# ---------------------------------------------------------------------------
try:
    import readline as _rl
    _rl.set_history_length(500)
    _rl.parse_and_bind("set editing-mode emacs")
    _rl.parse_and_bind("set horizontal-scroll-mode off")
    _HAS_READLINE = True
except ImportError:           # Windows without pyreadline
    _HAS_READLINE = False

# \001 / \002 = readline's RL_PROMPT_START_IGNORE / RL_PROMPT_END_IGNORE.
_REPL_PROMPT = "\n\001\033[1;36m\002lynx>\001\033[0m\002 "


def _flush() -> None:
    sys.stdout.flush()


def _read_command() -> str:
    """Read one REPL line with readline history support."""
    _flush()
    return input(_REPL_PROMPT).strip()


def _ask(label: str, default: str = "") -> str:
    """
    Print *label* via Rich (supports markup), then read input on a
    separate line using a plain '> ' prompt.  This keeps the question
    text immune to backspace / arrow-key corruption because only the
    '> ' prompt line is editable — readline never touches the label.
    """
    _flush()
    display.console.print(label)
    _flush()
    suffix = f" [{default}]" if default else ""
    raw = input(f"  \001\033[36m\002>\001\033[0m\002{suffix} ").strip()
    return raw if raw else default


def _ask_float(label: str, required: bool = True) -> Optional[float]:
    """
    Ask for a numeric value.  When *required* is False, an empty answer
    returns None.  On invalid input returns the sentinel string 'INVALID'
    so callers can distinguish "empty = None" from "garbage".
    """
    raw = _ask(label, default="" if required else "")
    if not raw:
        return None
    try:
        return float(raw)
    except ValueError:
        return "INVALID"          # type: ignore[return-value]


def _confirm(label: str, default: bool = False) -> bool:
    """Yes/No confirmation using plain input (no Rich Prompt)."""
    _flush()
    hint = "[Y/n]" if default else "[y/N]"
    display.console.print(label)
    _flush()
    raw = input(f"  \001\033[36m\002>\001\033[0m\002 {hint} ").strip().lower()
    if not raw:
        return default
    return raw in ("y", "yes")


_HELP = """
[bold cyan]Commands[/bold cyan]

  [bold]list[/bold]  /  [bold]ls[/bold]                List all portfolio positions
  [bold]add[/bold]                        Add a new instrument (guided prompt, supports name search)
  [bold]show[/bold]   <ticker>            Show detailed view for an instrument
  [bold]show[/bold]   --name <query>      Search by name and show instrument detail
  [bold]update[/bold] <ticker>            Update shares / average price
  [bold]delete[/bold] <ticker>            Remove an instrument from the portfolio
  [bold]refresh[/bold]                    Refresh live data for all instruments
  [bold]refresh[/bold] <ticker>           Refresh live data for one instrument
  [bold]import[/bold] <file.json>         Bulk-add instruments from a JSON file
  [bold]clear-cache[/bold]               Wipe all cached data
  [bold]markets[/bold] <ticker or ISIN>  List all exchanges where an instrument trades

[bold cyan]Dashboard[/bold cyan]

  [bold]dashboard[/bold]                  Full dashboard snapshot (stats + sectors + movers + alerts)
  [bold]stats[/bold]                      Portfolio summary (value, PnL, day change)
  [bold]sectors[/bold]                    Sector allocation breakdown
  [bold]movers[/bold]                     Top gainers / losers for the day
  [bold]income[/bold]                     Annual dividend income projection
  [bold]alerts[/bold]                     Drawdown / concentration / stale alerts
  [bold]benchmark[/bold] [<ticker>]       Portfolio vs market index (default ^GSPC)
  [bold]chart[/bold] <ticker> [period]    Price history chart (1y / 5y / 6mo / ytd …)

[bold cyan]Transactions & tax lots[/bold cyan]

  [bold]buy[/bold] <ticker> <shares> <price>    Record a BUY transaction
  [bold]sell[/bold] <ticker> <shares> <price>   Record a SELL transaction (FIFO)
  [bold]trades[/bold] [ticker]             Show the trade log
  [bold]lots[/bold] <ticker>                Show open tax lots (FIFO)
  [bold]realized[/bold] <ticker>            Realized PnL on closed shares

[bold cyan]Watchlists[/bold cyan]

  [bold]watch[/bold] <ticker> [list]       Add ticker to a watchlist
  [bold]unwatch[/bold] <ticker> [list]     Remove ticker from a watchlist
  [bold]watchlist[/bold] [list]            Show a watchlist

[bold cyan]Price alerts[/bold cyan]

  [bold]alert[/bold] <ticker> <op> <price>  Create a threshold alert (>= <= > < ==)
  [bold]alerts-list[/bold]                 Show all alert rules
  [bold]alert-del[/bold] <id>               Delete alert by id

[bold cyan]Import[/bold cyan]

  [bold]import-csv[/bold] <path> [broker]   Bulk-import trades from IBKR / Trading212 / Degiro / Fidelity / generic CSV

[bold cyan]Backtesting (v5.1)[/bold cyan]

  [bold]backtest[/bold] <tickers> [period] [weights]  Buy-and-hold / rebalanced backtest
      example: backtest AAPL,MSFT,GOOGL 5y 40,40,20
  [bold]bench-hist[/bold] [index] [period]  Portfolio vs historical benchmark (CAGR, alpha, beta, correlation)

[bold cyan]Utilities[/bold cyan]

  [bold]config[/bold]                     Show or update configuration
  [bold]about[/bold]                      Show application information
  [bold]help[/bold]                       Show this message
  [bold]quit[/bold]  /  [bold]exit[/bold]  /  [bold]q[/bold]    Exit
"""


def _show_empty_portfolio_hint() -> None:
    """Show a hint when quitting with an empty portfolio."""
    instruments = database.get_all_instruments()
    if not instruments:
        display.console.print(
            "\n[yellow]Your portfolio is empty.[/yellow]  "
            "You can re-run the setup wizard at any time with "
            "[bold]lynx-portfolio -w[/bold] or [bold]lynx-portfolio --wizard[/bold].\n"
        )


def run() -> None:
    display.console.print(
        "\n[bold cyan]Lynx Portfolio Manager[/bold cyan]  —  Interactive Mode\n"
        "Type [bold]help[/bold] for available commands or [bold]quit[/bold] to exit.\n"
    )

    while True:
        try:
            raw = _read_command()
        except (KeyboardInterrupt, EOFError):
            display.console.print("\n[cyan]Goodbye![/cyan]")
            _show_empty_portfolio_hint()
            break

        if not raw:
            continue

        parts = raw.split(None, 1)
        cmd   = parts[0].lower()
        arg   = parts[1].strip() if len(parts) > 1 else ""

        if cmd in ("quit", "exit", "q"):
            display.console.print("[cyan]Goodbye![/cyan]")
            _show_empty_portfolio_hint()
            break

        elif cmd == "help":
            display.console.print(_HELP)

        elif cmd in ("list", "ls"):
            with console_pager(display.console):
                display.display_portfolio(database.get_all_instruments())

        elif cmd == "add":
            _cmd_add()

        elif cmd == "show":
            if not arg:
                display.err("Usage: show <ticker>  or  show --name <query>")
            elif arg.lower().startswith(("--name", "-n ")):
                # Name search mode — strip the flag prefix to get the query
                from .validation import sanitise_search_query
                parts = arg.split(None, 1)
                query = parts[1].strip() if len(parts) > 1 else ""
                if query:
                    query, qerr = sanitise_search_query(query)
                    if qerr:
                        display.err(qerr)
                    else:
                        from . import fetcher
                        display.info(f"Searching for '{query}'…")
                        try:
                            results = fetcher.search_by_name(query)
                        except Exception as exc:
                            display.err(f"Search failed: {exc}")
                            results = None
                        if not results:
                            display.err(f"No instruments found matching '{query}'.")
                        else:
                            ticker_found = _pick_from_search_results(results)
                            if ticker_found:
                                _cmd_show(ticker_found)
                else:
                    display.err("Usage: show --name <query>")
            else:
                _cmd_show(arg.upper())

        elif cmd == "delete":
            if not arg:
                display.err("Usage: delete <ticker>")
            else:
                _cmd_delete(arg.upper())

        elif cmd == "update":
            if not arg:
                display.err("Usage: update <ticker>")
            else:
                _cmd_update(arg.upper())

        elif cmd == "refresh":
            if arg:
                refresh_instrument(arg.upper())
            else:
                refresh_all()

        elif cmd == "import":
            if not arg:
                display.err("Usage: import <file.json>")
            else:
                _cmd_import(arg)

        elif cmd == "clear-cache":
            instruments = database.get_all_instruments()
            if display.confirm_clear_cache(instruments):
                n = cache.delete()
                display.ok(f"Cache cleared ({n} entries removed).")

        elif cmd == "markets":
            if not arg:
                display.err("Usage: markets <ticker or ISIN>")
            else:
                _cmd_markets(arg)

        elif cmd == "config":
            from . import config as cfg
            cfg.run_configure(display.console)

        elif cmd == "about":
            from .logo import LOGO_ASCII
            sys.stdout.write(LOGO_ASCII)
            sys.stdout.flush()
            for line in ABOUT_LINES:
                display.console.print(line)

        elif cmd == "lynx":
            from .egg import run_interactive_egg
            run_interactive_egg()

        elif cmd == "dashboard":
            from . import dashboard as _dash
            from .display import render_dashboard
            render_dashboard(display.console, _dash.compute_full_dashboard())

        elif cmd == "stats":
            from . import dashboard as _dash
            from .display import render_stats
            render_stats(display.console, _dash.compute_stats())

        elif cmd == "sectors":
            from . import dashboard as _dash
            from .display import render_sector_allocation
            render_sector_allocation(display.console, _dash.compute_sector_allocation())

        elif cmd == "movers":
            from . import dashboard as _dash
            from .display import render_movers
            try:
                limit = int(arg) if arg else 5
            except ValueError:
                display.err("Usage: movers [<limit>]")
                continue
            render_movers(display.console, _dash.compute_movers(limit=limit))

        elif cmd == "income":
            from . import dashboard as _dash
            from .display import render_income
            render_income(display.console, _dash.compute_income())

        elif cmd == "alerts":
            from . import dashboard as _dash
            from .display import render_alerts
            render_alerts(display.console, _dash.compute_alerts())

        elif cmd == "benchmark":
            from . import dashboard as _dash
            from .display import render_benchmark
            bench = arg.strip() if arg else "^GSPC"
            render_benchmark(display.console, _dash.compute_benchmark(bench))

        elif cmd == "chart":
            parts = arg.split() if arg else []
            if not parts:
                display.err("Usage: chart <ticker> [period]")
                continue
            ticker = parts[0].upper()
            period = parts[1] if len(parts) > 1 else "1y"
            try:
                from lynx_investor_core.charts import (
                    fetch_price_history, render_price_chart,
                )
            except ImportError:
                display.err("Charting requires lynx-investor-core>=4.0 and plotext.")
                continue
            display.info(f"Fetching price history for {ticker} ({period})…")
            dates, closes = fetch_price_history(ticker, period=period)
            if not closes:
                display.err(f"No price data for {ticker}.")
                continue
            chart = render_price_chart(
                dates, closes,
                title=f"{ticker} — {period}",
                width=min(100, display.console.width - 4),
                height=20,
            )
            display.console.print(chart)

        elif cmd == "buy":
            parts = arg.split() if arg else []
            if len(parts) < 3:
                display.err("Usage: buy <ticker> <shares> <price> [fees] [trade_date]")
                continue
            try:
                from . import transactions as _tx
                from .validation import validate_ticker, validate_shares, validate_price
                ticker, terr = validate_ticker(parts[0])
                if terr:
                    display.err(terr); continue
                sh, serr = validate_shares(parts[1])
                if serr: display.err(serr); continue
                pr, perr = validate_price(parts[2])
                if perr: display.err(perr); continue
                fees = float(parts[3]) if len(parts) > 3 else 0.0
                date_s = parts[4] if len(parts) > 4 else None
                tid = _tx.record_buy(ticker, shares=sh, price=pr, fees=fees, trade_date=date_s)
                _tx.rebuild_portfolio_summary(ticker)
                display.ok(f"Recorded BUY #{tid}: {sh} {ticker} @ {pr}.")
            except (ValueError, TypeError) as exc:
                display.err(f"Bad input: {exc}")

        elif cmd == "sell":
            parts = arg.split() if arg else []
            if len(parts) < 3:
                display.err("Usage: sell <ticker> <shares> <price> [fees] [trade_date]")
                continue
            try:
                from . import transactions as _tx
                from .validation import validate_ticker, validate_shares, validate_price
                ticker, terr = validate_ticker(parts[0])
                if terr:
                    display.err(terr); continue
                sh, serr = validate_shares(parts[1])
                if serr: display.err(serr); continue
                pr, perr = validate_price(parts[2])
                if perr: display.err(perr); continue
                fees = float(parts[3]) if len(parts) > 3 else 0.0
                date_s = parts[4] if len(parts) > 4 else None
                tid = _tx.record_sell(ticker, shares=sh, price=pr, fees=fees, trade_date=date_s)
                _tx.rebuild_portfolio_summary(ticker)
                display.ok(f"Recorded SELL #{tid}: {sh} {ticker} @ {pr}.")
            except (ValueError, TypeError) as exc:
                display.err(f"Bad input: {exc}")

        elif cmd == "trades":
            from . import transactions as _tx
            from rich.table import Table as _T
            ticker = (arg.strip() or None)
            if ticker:
                ticker = ticker.upper()
            txs = _tx.list_transactions(ticker)
            if not txs:
                display.info("No transactions recorded."); continue
            t = _T(title=f"Trades{' — ' + ticker if ticker else ''}", box=box.ROUNDED, header_style="bold cyan")
            for col in ("ID", "Date", "Type", "Ticker", "Shares", "Price", "Fees", "Note"):
                t.add_column(col, justify="right" if col in ("Shares", "Price", "Fees") else "left")
            for tx in txs:
                color = "green" if tx.trade_type == "BUY" else "red"
                t.add_row(
                    str(tx.id), tx.trade_date, f"[{color}]{tx.trade_type}[/{color}]",
                    tx.ticker, f"{tx.shares:g}", f"{tx.price:,.2f}",
                    f"{tx.fees:.2f}", (tx.note or "")[:40],
                )
            display.console.print(t)

        elif cmd == "lots":
            if not arg:
                display.err("Usage: lots <ticker>"); continue
            from . import transactions as _tx
            from rich.table import Table as _T
            lots = _tx.compute_open_lots_fifo(arg.strip().upper())
            if not lots:
                display.info(f"No open lots for {arg.strip().upper()}."); continue
            t = _T(title=f"Open lots — {arg.strip().upper()} (FIFO)",
                   box=box.ROUNDED, header_style="bold cyan")
            t.add_column("Trade ID"); t.add_column("Date")
            t.add_column("Shares", justify="right")
            t.add_column("Unit cost", justify="right")
            for lot in lots:
                t.add_row(str(lot.trade_id), lot.trade_date,
                          f"{lot.shares_remaining:g}", f"{lot.unit_cost:,.4f}")
            display.console.print(t)

        elif cmd == "realized":
            if not arg:
                display.err("Usage: realized <ticker>"); continue
            from . import transactions as _tx
            from rich.panel import Panel as _P
            result = _tx.realized_pnl(arg.strip().upper())
            color = "green" if result["realized"] >= 0 else "red"
            display.console.print(_P(
                f"[bold]Sold shares[/bold]   {result['sold_shares']}\n"
                f"[bold]Proceeds[/bold]      {result['proceeds']:,.2f}\n"
                f"[bold]Cost basis[/bold]    {result['basis']:,.2f}\n"
                f"[bold]Realized[/bold]      [{color}]{result['realized']:,.2f}[/{color}]",
                title=f"[bold cyan]Realized PnL — {arg.strip().upper()}[/bold cyan]",
                border_style="cyan", box=box.ROUNDED,
            ))

        elif cmd == "watch":
            parts = arg.split(maxsplit=1) if arg else []
            if not parts:
                display.err("Usage: watch <ticker> [list_name]"); continue
            from . import watchlists as _wl
            ticker = parts[0].upper()
            name = parts[1] if len(parts) > 1 else "default"
            wid = _wl.add(ticker, name=name)
            if wid is None:
                display.warn(f"{ticker} already on watchlist '{name}'.")
            else:
                display.ok(f"Added {ticker} to watchlist '{name}'.")

        elif cmd == "unwatch":
            parts = arg.split(maxsplit=1) if arg else []
            if not parts:
                display.err("Usage: unwatch <ticker> [list_name]"); continue
            from . import watchlists as _wl
            ticker = parts[0].upper()
            name = parts[1] if len(parts) > 1 else "default"
            if _wl.remove(ticker, name=name):
                display.ok(f"Removed {ticker} from '{name}'.")
            else:
                display.warn(f"{ticker} not on watchlist '{name}'.")

        elif cmd == "watchlist":
            from . import watchlists as _wl
            from rich.table import Table as _T
            name = (arg.strip() or None)
            items = _wl.list_all(name)
            if not items:
                display.info(f"Watchlist '{name or 'default'}' is empty."); continue
            t = _T(title=f"Watchlist{' — ' + name if name else ''}",
                   box=box.ROUNDED, header_style="bold cyan")
            t.add_column("List"); t.add_column("Ticker"); t.add_column("Note")
            for item in items:
                t.add_row(item.name, item.ticker, item.note or "")
            display.console.print(t)

        elif cmd == "alert":
            parts = arg.split() if arg else []
            if len(parts) < 3:
                display.err("Usage: alert <ticker> <op> <price> (op: >= <= > < ==)")
                continue
            from . import price_alerts as _pa
            try:
                aid = _pa.create(
                    parts[0].upper(),
                    condition=parts[1],
                    threshold=float(parts[2]),
                    note=" ".join(parts[3:]) if len(parts) > 3 else None,
                )
                display.ok(f"Created alert #{aid}: {parts[0].upper()} {parts[1]} {parts[2]}")
            except ValueError as exc:
                display.err(str(exc))

        elif cmd in ("alerts-list", "alert-list"):
            from . import price_alerts as _pa
            from rich.table import Table as _T
            alerts = _pa.list_all()
            if not alerts:
                display.info("No price alerts defined."); continue
            t = _T(title="Price alerts", box=box.ROUNDED, header_style="bold cyan")
            for c in ("ID", "Ticker", "Rule", "Triggered", "Enabled", "Note"):
                t.add_column(c)
            for a in alerts:
                t.add_row(
                    str(a.id), a.ticker,
                    f"{a.condition} {a.threshold:,.2f}",
                    (a.triggered_at or "—")[:19],
                    "✓" if a.enabled else "—",
                    (a.note or "")[:40],
                )
            display.console.print(t)

        elif cmd == "alert-del":
            if not arg:
                display.err("Usage: alert-del <id>"); continue
            from . import price_alerts as _pa
            try:
                aid = int(arg.strip())
            except ValueError:
                display.err("id must be an integer"); continue
            if _pa.delete(aid):
                display.ok(f"Deleted alert #{aid}.")
            else:
                display.warn(f"No alert with id {aid}.")

        elif cmd == "backtest":
            parts = arg.split() if arg else []
            if not parts:
                display.err("Usage: backtest <tickers> [period] [weights]")
                continue
            try:
                from lynx_investor_core import backtest as _bt
            except ImportError:
                display.err("backtest requires lynx-investor-core>=5.0")
                continue
            tickers = [t.strip().upper() for t in parts[0].split(",") if t.strip()]
            period = parts[1] if len(parts) > 1 else "5y"
            weights = None
            if len(parts) > 2:
                try:
                    weights = [float(w) for w in parts[2].split(",")]
                except ValueError:
                    display.err("weights must be a comma-separated list of numbers")
                    continue
            display.info(f"Backtesting {tickers} over {period}…")
            try:
                result = _bt.run_backtest(tickers, weights=weights, period=period)
            except Exception as exc:
                display.err(f"backtest failed: {exc}")
                continue
            from rich.panel import Panel as _P
            color = "green" if result.total_return_pct > 0 else "red"
            body = (
                f"[bold]Tickers[/bold]          {', '.join(result.tickers)}\n"
                f"[bold]Weights[/bold]          {[round(w, 3) for w in result.weights]}\n"
                f"[bold]Initial[/bold]          {result.initial_capital:,.2f}\n"
                f"[bold]Final value[/bold]      {result.final_value:,.2f}\n"
                f"[bold]Total return[/bold]     [{color}]{result.total_return_pct:+.2f}%[/{color}]\n"
                f"[bold]CAGR[/bold]             {result.cagr_pct:+.2f}%\n"
                f"[bold]Volatility[/bold]       {result.volatility_pct:.2f}%\n"
                f"[bold]Max drawdown[/bold]     [red]{result.max_drawdown_pct:.2f}%[/red]\n"
                f"[bold]Sharpe ratio[/bold]     {result.sharpe_ratio:.2f}"
            )
            if result.skipped_tickers:
                body += f"\n[yellow]Skipped (no data):[/yellow] {', '.join(result.skipped_tickers)}"
            display.console.print(_P(body, title="[bold cyan]Backtest[/bold cyan]",
                                     border_style="cyan", box=box.ROUNDED))

        elif cmd == "bench-hist":
            parts = arg.split() if arg else []
            bench = parts[0] if parts else "^GSPC"
            period = parts[1] if len(parts) > 1 else "5y"
            try:
                from lynx_investor_core import backtest as _bt
            except ImportError:
                display.err("bench-hist requires lynx-investor-core>=5.0")
                continue
            # Build positions from the current portfolio with current market value.
            positions = []
            for inst in database.get_all_instruments():
                curr = inst.get("current_price")
                shares = inst.get("shares") or 0
                if curr and shares > 0:
                    positions.append((inst["ticker"], shares * curr))
            if not positions:
                display.warn("Portfolio is empty — nothing to benchmark.")
                continue
            display.info(f"Computing historical comparison vs {bench} over {period}…")
            result = _bt.historical_benchmark(positions, bench, period=period)
            from rich.panel import Panel as _P
            alpha_color = "green" if result.alpha_pct >= 0 else "red"
            beta_str = f"{result.beta:.2f}" if result.beta is not None else "—"
            corr_str = f"{result.correlation:.2f}" if result.correlation is not None else "—"
            display.console.print(_P(
                f"[bold]Period[/bold]             {result.period}\n"
                f"[bold]Portfolio return[/bold]   {result.portfolio_return_pct:+.2f}%\n"
                f"[bold]Portfolio CAGR[/bold]     {result.portfolio_cagr_pct:+.2f}%\n"
                f"[bold]{bench} return[/bold]    {result.benchmark_return_pct:+.2f}%\n"
                f"[bold]{bench} CAGR[/bold]      {result.benchmark_cagr_pct:+.2f}%\n"
                f"[bold]Alpha[/bold]              [{alpha_color}]{result.alpha_pct:+.2f}%[/{alpha_color}]\n"
                f"[bold]Beta[/bold]               {beta_str}\n"
                f"[bold]Correlation[/bold]        {corr_str}\n"
                f"[bold]Max drawdown[/bold]       [red]{result.max_drawdown_pct:.2f}%[/red]",
                title=f"[bold cyan]Portfolio vs {bench}[/bold cyan]",
                border_style="cyan", box=box.ROUNDED,
            ))

        elif cmd == "import-csv":
            parts = arg.split(maxsplit=1) if arg else []
            if not parts:
                display.err("Usage: import-csv <path> [broker]"); continue
            from . import broker_import as _bi
            from pathlib import Path as _Path
            path = _Path(parts[0]).expanduser()
            broker = parts[1] if len(parts) > 1 else None
            result = _bi.import_csv(path, broker=broker)
            display.ok(
                f"Imported {result.imported}/{result.rows_read} trades "
                f"(broker={result.broker}, new tickers={len(result.new_tickers)})."
            )
            if result.errors:
                for err in result.errors[:5]:
                    display.warn(err)
                if len(result.errors) > 5:
                    display.warn(f"... and {len(result.errors) - 5} more errors.")

        else:
            display.warn(f"Unknown command '{cmd}'. Type 'help' for available commands.")


# ---------------------------------------------------------------------------
# Market selection prompt (used as market_selector callback in add_instrument)
# ---------------------------------------------------------------------------

def _prompt_market_selection(markets: List[Dict]) -> Optional[Dict]:
    """Show a table of available markets and ask the user to pick one."""
    t = Table(
        title="Available Markets",
        box=box.ROUNDED,
        header_style="bold cyan",
        show_lines=False,
    )
    t.add_column("#",        width=4,  justify="right")
    t.add_column("Symbol",   width=16)
    t.add_column("Exchange", width=32)
    t.add_column("Suffix",   width=8)
    t.add_column("Type",     width=12)

    for i, m in enumerate(markets, 1):
        t.add_row(
            str(i),
            m["symbol"],
            m["exchange_display"] or m["exchange_code"],
            m["suffix"] or "(US)",
            m["quote_type"],
        )

    display.console.print(t)

    valid = set(str(i) for i in range(len(markets) + 1))
    while True:
        answer = _ask(
            f"Select market number [dim](1–{len(markets)}, 0 to cancel)[/dim]"
        )
        if answer in valid:
            break
        display.warn(f"Enter a number between 0 and {len(markets)}.")
    if answer == "0":
        return None
    return markets[int(answer) - 1]


# ---------------------------------------------------------------------------
# Sub-command helpers
# ---------------------------------------------------------------------------

def _pick_from_search_results(results: List[Dict]) -> Optional[str]:
    """Display search results and let the user pick one. Returns ticker or None."""
    display.console.print(f"\n[bold]Search results:[/bold]\n")
    for i, r in enumerate(results, 1):
        display.console.print(
            f"  [bold cyan]{i:>2}[/bold cyan]  "
            f"[bold]{r['symbol']:<14}[/bold]  "
            f"{(r['longname'] or r['shortname']):<35}  "
            f"[dim]{r['exchange_display']:<20}  "
            f"{r['quote_type']}[/dim]"
        )
    display.console.print(f"\n   [dim]0  Cancel[/dim]\n")

    while True:
        answer = _ask(f"Select [dim](1–{len(results)}, 0 to cancel)[/dim]")
        if not answer:
            continue
        try:
            idx = int(answer)
        except ValueError:
            display.warn(f"Enter a number between 0 and {len(results)}.")
            continue
        if idx == 0:
            return None
        if 1 <= idx <= len(results):
            return results[idx - 1]["symbol"]
        display.warn(f"Enter a number between 0 and {len(results)}.")


def _search_instrument_by_name() -> Optional[str]:
    """Search for instruments by name and let the user select one."""
    from . import fetcher
    from .validation import sanitise_search_query
    name = _ask("Search by name [dim](e.g. 'Apple', 'Vanguard FTSE')[/dim]")
    if not name:
        return None
    name, err = sanitise_search_query(name)
    if err:
        display.err(err)
        return None
    display.info(f"Searching for '{name}'…")
    try:
        results = fetcher.search_by_name(name)
    except Exception as exc:
        display.err(f"Search failed: {exc}")
        return None
    if not results:
        display.err(f"No instruments found matching '{name}'.")
        return None
    return _pick_from_search_results(results)


def _cmd_add() -> None:
    display.console.print("\n[bold]Add New Instrument[/bold]")

    ticker = _ask(
        "Ticker [dim](e.g. AAPL, NESN.SW, VWCE.DE — include exchange suffix "
        "if known, Enter to skip if using ISIN or name search)[/dim]"
    )
    isin = None
    if not ticker:
        # Offer name search or ISIN
        display.console.print(
            "  [dim]No ticker given. You can search by name or provide an ISIN.[/dim]"
        )
        choice = _ask("Search by [bold]name[/bold] or enter [bold]ISIN[/bold]? [dim](name/isin)[/dim]")
        if choice and choice.lower().startswith("n"):
            ticker = _search_instrument_by_name()
            if not ticker:
                display.info("Cancelled.")
                return
        else:
            isin = _ask("ISIN [dim](Enter to cancel)[/dim]")

    if not ticker and not isin:
        display.err("You must provide at least a ticker, name search, or an ISIN.")
        return

    shares = _ask_float("Number of shares")
    if shares is None or shares == "INVALID":
        display.err("Invalid number. Operation cancelled.")
        return

    avg_price = _ask_float(
        "Average purchase price [dim](Enter to skip — position won't track cost/P&L)[/dim]",
        required=False,
    )
    if avg_price == "INVALID":
        display.err("Invalid number. Operation cancelled.")
        return

    add_instrument(
        ticker or None,
        isin   or None,
        shares,
        avg_price,
        market_selector=_prompt_market_selection,
    )


def _cmd_show(ticker: str) -> None:
    from .validation import validate_ticker
    ticker, err = validate_ticker(ticker)
    if err:
        display.err(err)
        return
    inst = database.get_instrument(ticker)
    if inst:
        display.display_instrument(inst)
    else:
        display.err(f"'{ticker}' not found in portfolio.")


def _cmd_delete(ticker: str) -> None:
    from .validation import validate_ticker
    ticker, err = validate_ticker(ticker)
    if err:
        display.err(err)
        return
    inst = database.get_instrument(ticker)
    if not inst:
        display.err(f"'{ticker}' not found in portfolio.")
        return
    if _confirm(f"Delete [bold]{ticker}[/bold] from portfolio?"):
        if database.delete_instrument(ticker):
            display.ok(f"Deleted {ticker}.")
        else:
            display.err("Deletion failed.")


def _cmd_update(ticker: str) -> None:
    from .validation import validate_ticker, validate_shares, validate_price
    ticker, err = validate_ticker(ticker)
    if err:
        display.err(err)
        return
    inst = database.get_instrument(ticker)
    if not inst:
        display.err(f"'{ticker}' not found in portfolio.")
        return

    cur_price = inst.get("avg_purchase_price")
    price_disp = f"{cur_price:,.2f}" if cur_price is not None else "not tracked"
    display.console.print(
        f"\n[bold]Update {ticker}[/bold]  "
        f"(shares: {inst['shares']}, avg price: {price_disp})"
    )

    raw_shares = _ask("New shares [dim](Enter to keep)[/dim]")
    raw_price  = _ask("New avg price [dim](Enter to keep)[/dim]")

    kwargs: dict = {}
    if raw_shares:
        val, verr = validate_shares(raw_shares)
        if verr:
            display.err(verr)
            return
        kwargs["shares"] = val
    if raw_price:
        val, verr = validate_price(raw_price)
        if verr:
            display.err(verr)
            return
        kwargs["avg_purchase_price"] = val

    if kwargs:
        if database.update_instrument(ticker, **kwargs):
            display.ok(f"Updated {ticker}.")
        else:
            display.err(f"'{ticker}' not found.")
    else:
        display.info("Nothing changed.")


def _cmd_import(filepath: str) -> None:
    """Bulk-add instruments from a JSON file."""
    from .cli import _import_from_json
    _import_from_json(filepath)


def _cmd_markets(query: str) -> None:
    """Show all exchanges where a ticker/ISIN is listed."""
    from . import fetcher as f
    from .validation import validate_ticker, validate_isin
    query = query.strip()
    if not query:
        display.err("Usage: markets <ticker or ISIN>")
        return
    isin = None
    ticker = None
    if len(query) == 12 and query[:2].isalpha():
        isin, err = validate_isin(query)
        if err:
            # Fall back to treating it as a ticker
            ticker, err2 = validate_ticker(query)
            if err2:
                display.err(err)
                return
    else:
        ticker, err = validate_ticker(query)
        if err:
            display.err(err)
            return
    try:
        markets, _ = f.resolve_markets_for_input(ticker, isin)
    except Exception as exc:
        display.err(f"Market lookup failed: {exc}")
        return
    if not markets:
        display.warn(f"No markets found for '{query}'.")
        return
    _prompt_market_selection(markets)
