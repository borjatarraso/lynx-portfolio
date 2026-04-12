"""
Full-screen TUI mode for Lynx Portfolio, powered by Textual.
Launched via: lynx -tui  /  lynx --textual-ui
"""

from __future__ import annotations

import json
from typing import Optional, List, Dict

from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Vertical, Horizontal, VerticalScroll, Container
from textual.screen import Screen, ModalScreen
from textual.widgets import (
    Header, Footer, DataTable, Static, Input, Button, Label,
    Select, LoadingIndicator,
)

from textual.theme import BUILTIN_THEMES, Theme

from . import database, cache, config, forex
from .display import _split_shares, _shares_str
from .operations import (
    add_instrument as ops_add_instrument,
    refresh_instrument as ops_refresh_instrument,
    refresh_all as ops_refresh_all,
)
from . import fetcher, display


# ---------------------------------------------------------------------------
# Theme / constants
# ---------------------------------------------------------------------------

# Textual CSS for the entire app
APP_CSS = """
Screen {
    background: $surface;
}

#portfolio-table {
    height: 1fr;
}

DataTable {
    height: 1fr;
}

DataTable > .datatable--header {
    background: $accent;
    color: $text;
    text-style: bold;
}

DataTable > .datatable--cursor {
    background: $accent 40%;
    color: $text;
}

.title-bar {
    dock: top;
    height: 1;
    background: $accent;
    color: $text;
    text-style: bold;
    content-align: center middle;
    padding: 0 2;
}

.status-bar {
    dock: bottom;
    height: 1;
    background: $surface-darken-1;
    color: $text-muted;
    padding: 0 2;
}

.form-container {
    padding: 1 2;
    height: auto;
    max-height: 90%;
}

.form-container Label {
    margin: 1 0 0 0;
    color: $accent;
    text-style: bold;
}

.form-container Input {
    margin: 0 0 0 0;
}

.form-container .btn-row {
    margin: 1 0;
    height: 3;
}

.form-container Button {
    margin: 0 1;
}

.detail-container {
    padding: 1 2;
}

.detail-row {
    height: 1;
    padding: 0 1;
}

.detail-label {
    width: 24;
    color: $accent;
    text-style: bold;
}

.detail-value {
    width: 1fr;
}

.pnl-positive {
    color: $success;
}

.pnl-negative {
    color: $error;
}

.msg-info {
    color: $accent;
    padding: 1 2;
}

.msg-warn {
    color: $warning;
    padding: 1 2;
}

.msg-err {
    color: $error;
    padding: 1 2;
}

.msg-ok {
    color: $success;
    padding: 1 2;
}

ModalScreen {
    align: center middle;
}

#confirm-dialog {
    width: 70;
    height: auto;
    max-height: 80%;
    border: thick $accent;
    background: $surface;
    padding: 1 2;
    overflow-y: auto;
}

#confirm-dialog Label {
    width: 100%;
    content-align: center middle;
    margin: 0 0 1 0;
}

#confirm-dialog .btn-row {
    height: 3;
    align: center middle;
}

#confirm-dialog Button {
    margin: 0 1;
}

#import-results {
    height: auto;
    max-height: 70%;
    padding: 1 2;
    overflow-y: auto;
}
"""


# ---------------------------------------------------------------------------
# Helper: format PnL string for display (plain text, no Rich markup)
# ---------------------------------------------------------------------------

def _pnl_text(pnl: float, pct: float) -> str:
    sign = "+" if pnl >= 0 else ""
    return f"{sign}{pnl:,.2f} ({sign}{pct:.2f}%)"


# ---------------------------------------------------------------------------
# Confirmation dialog
# ---------------------------------------------------------------------------

class ConfirmDialog(ModalScreen[bool]):
    """A simple Yes/No confirmation dialog."""

    BINDINGS = [
        Binding("y", "confirm", "Yes"),
        Binding("n", "cancel", "No"),
        Binding("escape", "cancel", "Cancel"),
    ]

    def __init__(self, message: str) -> None:
        super().__init__()
        self._message = message

    def compose(self) -> ComposeResult:
        with Vertical(id="confirm-dialog"):
            yield Label(self._message)
            with Horizontal(classes="btn-row"):
                yield Button("Yes", variant="success", id="btn-yes")
                yield Button("No", variant="error", id="btn-no")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "btn-yes")

    def action_confirm(self) -> None:
        self.dismiss(True)

    def action_cancel(self) -> None:
        self.dismiss(False)


# ---------------------------------------------------------------------------
# Clear-cache confirmation screen (two-step safety)
# ---------------------------------------------------------------------------

class ClearCacheScreen(ModalScreen[bool]):
    """
    Two-step clear-cache confirmation:
    1. Blinking red warning listing all instruments → Enter to continue, Esc to cancel.
    2. Abort / Continue buttons — Abort is focused by default.
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
    ]

    _step: int = 1  # 1 = warning, 2 = confirm

    def compose(self) -> ComposeResult:
        instruments = database.get_all_instruments()
        lines = [f"  • {inst.get('ticker', '?'):14s}  {inst.get('name') or '—'}"
                 for inst in instruments]
        listing = "\n".join(lines) if lines else "  (no instruments)"

        with Vertical(id="confirm-dialog"):
            yield Static(
                "[blink bold red]⚠  WARNING: WIPE ALL CACHED DATA  ⚠[/blink bold red]\n\n"
                "[bold red]The following instruments will lose cached data:[/bold red]\n"
                f"{listing}\n\n"
                "[bold red]Prices and market data will need to be re-fetched.[/bold red]\n\n"
                "[dim]Press Enter to continue — Esc to cancel[/dim]",
                id="cache-warning",
            )
            with Horizontal(classes="btn-row", id="cache-confirm-btns"):
                yield Button("Abort", variant="error", id="btn-abort")
                yield Button("Continue", variant="warning", id="btn-continue")

    def on_mount(self) -> None:
        # Hide confirm buttons until the user presses Enter on step 1.
        self.query_one("#cache-confirm-btns").display = False

    def on_key(self, event) -> None:
        if self._step == 1 and event.key == "enter":
            event.prevent_default()
            self._step = 2
            self.query_one("#cache-warning", Static).update(
                "[bold red]Confirm: wipe all cached instrument data?[/bold red]\n\n"
                "[dim]This cannot be undone. Select Abort or Continue.[/dim]"
            )
            self.query_one("#cache-confirm-btns").display = True
            # Focus the Abort button so a quick Enter press does NOT clear.
            self.query_one("#btn-abort", Button).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "btn-continue")

    def action_cancel(self) -> None:
        self.dismiss(False)


# ---------------------------------------------------------------------------
# Portfolio screen (main screen)
# ---------------------------------------------------------------------------

class PortfolioScreen(Screen):
    """Main portfolio table view."""

    BINDINGS = [
        Binding("a",       "add",         "Add"),
        Binding("d",       "delete",      "Delete"),
        Binding("e",       "edit",        "Edit"),
        Binding("r",       "refresh_one", "Refresh"),
        Binding("R",       "refresh_all", "Refresh All"),
        Binding("i",       "import_json", "Import"),
        Binding("c",       "clear_cache", "Clear Cache"),
        Binding("q",       "quit_app",    "Quit"),
    ]

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield DataTable(id="portfolio-table")
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one(DataTable)
        table.cursor_type = "row"
        table.zebra_stripes = True

        # Determine whether any instrument uses a non-EUR currency so we can
        # show EUR columns.  Use whatever rates are already cached (forex was
        # fetched at startup in cli.py before launching the TUI).
        instruments = database.get_all_instruments()
        self._show_eur = any(
            (inst.get("currency") or "EUR").upper() != "EUR"
            for inst in instruments
        )

        columns = [
            "Ticker", "ISIN", "Name", "Exchange",
            "Shares", "Avg Price", "Curr Price", "CCY",
            "Mkt Value",
        ]
        if self._show_eur:
            columns += ["EUR Val", "EUR P&L"]
        else:
            columns.append("P&L")
        table.add_columns(*columns)
        self._reload_table()

    def _reload_table(self) -> None:
        table = self.query_one(DataTable)
        table.clear()
        instruments = database.get_all_instruments()
        if not instruments:
            return

        for inst in instruments:
            shares    = inst.get("shares") or 0.0
            avg_price = inst.get("avg_purchase_price")   # may be None
            curr      = inst.get("current_price")
            ccy       = (inst.get("currency") or "EUR").upper()
            has_cost  = avg_price is not None
            qt        = inst.get("quote_type")
            shares_s  = _shares_str(shares, qt)

            if curr is not None:
                mkt_val = shares * curr
                curr_s  = f"{curr:,.2f}"
                mkt_s   = f"{mkt_val:,.2f}"
                if has_cost:
                    invested = shares * avg_price
                    pnl = mkt_val - invested
                    pct = (pnl / invested * 100) if invested else 0.0
                    pnl_s = _pnl_text(pnl, pct)
                else:
                    pnl = None
                    pct = None
                    pnl_s = "—"
                if self._show_eur:
                    mkt_eur = forex.to_eur(mkt_val, ccy)
                    eur_mkt_s = f"{mkt_eur:,.2f}" if mkt_eur is not None else "N/A"
                    if pnl is not None:
                        pnl_eur = forex.to_eur(pnl, ccy)
                        eur_pnl_s = _pnl_text(pnl_eur, pct) if pnl_eur is not None else "N/A"
                    else:
                        eur_pnl_s = "—"
            else:
                curr_s = "N/A"
                mkt_s  = "N/A"
                pnl_s  = "N/A"
                if self._show_eur:
                    eur_mkt_s = "N/A"
                    eur_pnl_s = "N/A"

            exch = (
                inst.get("exchange_display")
                or inst.get("exchange_code")
                or "—"
            )

            row = [
                inst.get("ticker") or "",
                inst.get("isin") or "—",
                (inst.get("name") or "—")[:36],
                exch[:24],
                shares_s,
                f"{avg_price:,.2f}" if has_cost else "—",
                curr_s,
                inst.get("currency") or "—",
                mkt_s,
            ]
            if self._show_eur:
                row += [eur_mkt_s, eur_pnl_s]
            else:
                row.append(pnl_s)

            table.add_row(*row, key=inst.get("ticker"))

    def _get_selected_ticker(self) -> Optional[str]:
        table = self.query_one(DataTable)
        if table.row_count == 0:
            return None
        row_key, _ = table.coordinate_to_cell_key(table.cursor_coordinate)
        return str(row_key.value) if row_key else None

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Enter pressed on a row → open detail view."""
        ticker = str(event.row_key.value) if event.row_key else None
        if ticker:
            self.app.push_screen(DetailScreen(ticker))

    def action_add(self) -> None:
        self.app.push_screen(AddScreen(), callback=self._on_form_dismiss)

    def action_edit(self) -> None:
        ticker = self._get_selected_ticker()
        if ticker:
            self.app.push_screen(EditScreen(ticker), callback=self._on_form_dismiss)

    def action_delete(self) -> None:
        ticker = self._get_selected_ticker()
        if not ticker:
            return
        self.app.push_screen(
            ConfirmDialog(f"Delete {ticker} from portfolio?"),
            callback=lambda confirmed: self._do_delete(ticker, confirmed),
        )

    def _do_delete(self, ticker: str, confirmed: bool) -> None:
        if confirmed:
            database.delete_instrument(ticker)
            self.notify(f"Deleted {ticker}", severity="information")
            self._reload_table()

    def action_refresh_one(self) -> None:
        ticker = self._get_selected_ticker()
        if ticker:
            self._do_refresh_one(ticker)

    @work(thread=True)
    def _do_refresh_one(self, ticker: str) -> None:
        inst = database.get_instrument(ticker)
        isin = inst.get("isin") if inst else None
        cache.delete(ticker)
        data = fetcher.fetch_instrument_data(ticker, isin)
        if data:
            cache.put(ticker, data)
            database.apply_cache_to_portfolio(ticker, data)
            self.app.call_from_thread(self.notify, f"Refreshed {ticker}", severity="information")
        else:
            self.app.call_from_thread(self.notify, f"Failed to refresh {ticker}", severity="error")
        self.app.call_from_thread(self._reload_table)

    def action_refresh_all(self) -> None:
        self._do_refresh_all()

    @work(thread=True)
    def _do_refresh_all(self) -> None:
        instruments = database.get_all_instruments()
        for inst in instruments:
            ticker = inst["ticker"]
            isin   = inst.get("isin")
            cache.delete(ticker)
            data = fetcher.fetch_instrument_data(ticker, isin)
            if data:
                cache.put(ticker, data)
                database.apply_cache_to_portfolio(ticker, data)
        self.app.call_from_thread(self.notify, f"Refreshed {len(instruments)} instruments", severity="information")
        self.app.call_from_thread(self._reload_table)

    def action_import_json(self) -> None:
        self.app.push_screen(ImportScreen(), callback=self._on_form_dismiss)

    def action_clear_cache(self) -> None:
        self.app.push_screen(
            ClearCacheScreen(),
            callback=self._on_clear_cache_result,
        )

    def _on_clear_cache_result(self, confirmed: bool) -> None:
        if confirmed:
            n = cache.delete()
            self.notify(f"Cache cleared ({n} entries)", severity="information")
        else:
            self.notify("Cache clear aborted", severity="warning")

    def action_quit_app(self) -> None:
        self.app.exit()

    def _on_form_dismiss(self, result: object = None) -> None:
        self._reload_table()


# ---------------------------------------------------------------------------
# Detail screen
# ---------------------------------------------------------------------------

class DetailScreen(Screen):
    """Show detailed info for a single instrument."""

    BINDINGS = [
        Binding("escape", "go_back", "Back"),
        Binding("q",      "go_back", "Back"),
    ]

    def __init__(self, ticker: str) -> None:
        super().__init__()
        self._ticker = ticker

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with VerticalScroll(classes="detail-container"):
            yield Static(id="detail-content")
        yield Footer()

    def on_mount(self) -> None:
        inst = database.get_instrument(self._ticker)
        if not inst:
            self.query_one("#detail-content", Static).update(
                f"[bold red]'{self._ticker}' not found.[/bold red]"
            )
            return

        shares    = inst.get("shares") or 0.0
        avg_price = inst.get("avg_purchase_price")   # may be None
        curr      = inst.get("current_price")
        has_cost  = avg_price is not None
        qt        = inst.get("quote_type")

        exch = (
            inst.get("exchange_display")
            or inst.get("exchange_code")
            or "—"
        )

        ccy = (inst.get("currency") or "EUR").upper()

        lines = [
            f"[bold cyan]{'─' * 60}[/bold cyan]",
            f"[bold cyan]  {self._ticker}[/bold cyan]",
            f"[bold cyan]{'─' * 60}[/bold cyan]",
            "",
            f"  [bold cyan]Ticker[/bold cyan]              {inst.get('ticker', '')}",
            f"  [bold cyan]ISIN[/bold cyan]                {inst.get('isin') or '—'}",
            f"  [bold cyan]Name[/bold cyan]                {inst.get('name') or '—'}",
            f"  [bold cyan]Exchange[/bold cyan]            {exch}",
            f"  [bold cyan]Currency[/bold cyan]            {inst.get('currency') or '—'}",
            f"  [bold cyan]Sector[/bold cyan]              {inst.get('sector') or '—'}",
            f"  [bold cyan]Industry[/bold cyan]            {inst.get('industry') or '—'}",
            f"  [bold cyan]Shares[/bold cyan]              {_shares_str(shares, qt)}",
            f"  [bold cyan]Avg Purchase Price[/bold cyan]  {avg_price:,.2f}" if has_cost else f"  [bold cyan]Avg Purchase Price[/bold cyan]  [dim]Not tracked[/dim]",
            f"  [bold cyan]Current Price[/bold cyan]       {curr:,.2f}" if curr is not None else f"  [bold cyan]Current Price[/bold cyan]       N/A",
        ]

        if has_cost:
            invested = shares * avg_price
            lines.append(f"  [bold cyan]Total Invested[/bold cyan]      {invested:,.2f}")
            if ccy != "EUR":
                inv_eur = forex.to_eur(invested, ccy)
                if inv_eur is not None:
                    lines.append(f"  [bold cyan]Total Invested (EUR)[/bold cyan] {inv_eur:,.2f}")
        else:
            lines.append(f"  [bold cyan]Total Invested[/bold cyan]      [dim]Not tracked[/dim]")

        if curr is not None:
            mkt_val = shares * curr
            lines.append(f"  [bold cyan]Market Value[/bold cyan]        {mkt_val:,.2f}")
            if ccy != "EUR":
                mkt_eur = forex.to_eur(mkt_val, ccy)
                if mkt_eur is not None:
                    lines.append(f"  [bold cyan]Market Value (EUR)[/bold cyan]  {mkt_eur:,.2f}")
            if has_cost:
                pnl   = mkt_val - invested
                pct   = (pnl / invested * 100) if invested else 0.0
                color = "green" if pnl >= 0 else "red"
                sign  = "+" if pnl >= 0 else ""
                lines.append(f"  [bold cyan]P&L[/bold cyan]                 [{color}]{sign}{pnl:,.2f} ({sign}{pct:.2f}%)[/{color}]")
                if ccy != "EUR":
                    pnl_eur = forex.to_eur(pnl, ccy)
                    if pnl_eur is not None:
                        lines.append(f"  [bold cyan]P&L (EUR)[/bold cyan]           [{color}]{sign}{pnl_eur:,.2f} ({sign}{pct:.2f}%)[/{color}]")
            else:
                lines.append(f"  [bold cyan]P&L[/bold cyan]                 [dim]Not tracked[/dim]")

        if inst.get("description"):
            lines.append(f"  [bold cyan]Description[/bold cyan]         {inst['description']}")

        lines.append(f"  [bold cyan]Added[/bold cyan]               {inst.get('created_at') or '—'}")
        lines.append(f"  [bold cyan]Updated[/bold cyan]             {inst.get('updated_at') or '—'}")
        lines.append("")

        self.query_one("#detail-content", Static).update("\n".join(lines))

    def action_go_back(self) -> None:
        self.app.pop_screen()


# ---------------------------------------------------------------------------
# Add instrument screen
# ---------------------------------------------------------------------------

class AddScreen(Screen):
    """Form to add a new instrument."""

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
    ]

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with VerticalScroll(classes="form-container"):
            yield Static("[bold cyan]Add New Instrument[/bold cyan]\n", classes="msg-info")
            yield Label("Ticker  [dim](e.g. AAPL, NESN.SW, VWCE.DE)[/dim]")
            yield Input(placeholder="Ticker (Enter to skip if using ISIN)", id="inp-ticker")
            yield Label("ISIN  [dim](optional)[/dim]")
            yield Input(placeholder="e.g. CH0038863350", id="inp-isin")
            yield Label("Exchange suffix  [dim](optional, e.g. SW, DE, AS)[/dim]")
            yield Input(placeholder="Exchange suffix", id="inp-exchange")
            yield Label("Number of shares")
            yield Input(placeholder="e.g. 10", id="inp-shares", type="number")
            yield Label("Average purchase price  [dim](leave empty to skip cost tracking)[/dim]")
            yield Input(placeholder="e.g. 150.00 (optional)", id="inp-avgprice", type="number")
            with Horizontal(classes="btn-row"):
                yield Button("Add", variant="success", id="btn-add")
                yield Button("Cancel", variant="error", id="btn-cancel")
            yield Static("", id="add-status")
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-cancel":
            self.dismiss()
        elif event.button.id == "btn-add":
            self._do_add()

    def _do_add(self) -> None:
        ticker   = self.query_one("#inp-ticker", Input).value.strip()
        isin     = self.query_one("#inp-isin", Input).value.strip()
        exchange = self.query_one("#inp-exchange", Input).value.strip()
        shares_s = self.query_one("#inp-shares", Input).value.strip()
        price_s  = self.query_one("#inp-avgprice", Input).value.strip()

        if not ticker and not isin:
            self.query_one("#add-status", Static).update(
                "[bold red]Provide at least a ticker or ISIN.[/bold red]"
            )
            return

        try:
            shares    = float(shares_s)
            avg_price = float(price_s) if price_s else None
        except ValueError:
            self.query_one("#add-status", Static).update(
                "[bold red]Invalid number for shares or price.[/bold red]"
            )
            return

        self.query_one("#add-status", Static).update(
            "[bold yellow]Adding instrument...[/bold yellow]"
        )
        self._run_add(ticker or None, isin or None, exchange or None, shares, avg_price)

    @work(thread=True)
    def _run_add(
        self,
        ticker: Optional[str],
        isin: Optional[str],
        exchange: Optional[str],
        shares: float,
        avg_price: float,
    ) -> None:
        ok = ops_add_instrument(
            ticker=ticker,
            isin=isin,
            shares=shares,
            avg_purchase_price=avg_price,
            preferred_exchange=exchange,
        )
        if ok:
            self.app.call_from_thread(self.notify, "Instrument added", severity="information")
            self.app.call_from_thread(self.dismiss)
        else:
            self.app.call_from_thread(
                self.query_one("#add-status", Static).update,
                "[bold red]Failed to add instrument. Check ticker/ISIN and try again.[/bold red]",
            )

    def action_cancel(self) -> None:
        self.dismiss()


# ---------------------------------------------------------------------------
# Edit instrument screen
# ---------------------------------------------------------------------------

class EditScreen(Screen):
    """Form to update shares / avg price for an instrument."""

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
    ]

    def __init__(self, ticker: str) -> None:
        super().__init__()
        self._ticker = ticker

    def compose(self) -> ComposeResult:
        inst = database.get_instrument(self._ticker) or {}
        cur_shares = inst.get("shares", 0.0)
        cur_price  = inst.get("avg_purchase_price")   # may be None
        price_disp = f"{cur_price:,.2f}" if cur_price is not None else "Not tracked"

        yield Header(show_clock=True)
        with VerticalScroll(classes="form-container"):
            yield Static(
                f"[bold cyan]Update {self._ticker}[/bold cyan]\n"
                f"  Current shares: {cur_shares}  |  Current avg price: {price_disp}\n",
                classes="msg-info",
            )
            yield Label("New shares  [dim](leave empty to keep)[/dim]")
            yield Input(placeholder=str(cur_shares), id="inp-shares", type="number")
            yield Label("New average price  [dim](leave empty to keep)[/dim]")
            yield Input(placeholder=price_disp, id="inp-price", type="number")
            with Horizontal(classes="btn-row"):
                yield Button("Update", variant="success", id="btn-update")
                yield Button("Cancel", variant="error", id="btn-cancel")
            yield Static("", id="edit-status")
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-cancel":
            self.dismiss()
        elif event.button.id == "btn-update":
            self._do_update()

    def _do_update(self) -> None:
        shares_s = self.query_one("#inp-shares", Input).value.strip()
        price_s  = self.query_one("#inp-price", Input).value.strip()

        kwargs: dict = {}
        try:
            if shares_s:
                kwargs["shares"] = float(shares_s)
            if price_s:
                kwargs["avg_purchase_price"] = float(price_s)
        except ValueError:
            self.query_one("#edit-status", Static).update(
                "[bold red]Invalid number.[/bold red]"
            )
            return

        if not kwargs:
            self.notify("Nothing changed", severity="warning")
            self.dismiss()
            return

        if database.update_instrument(self._ticker, **kwargs):
            self.notify(f"Updated {self._ticker}", severity="information")
            self.dismiss()
        else:
            self.query_one("#edit-status", Static).update(
                f"[bold red]'{self._ticker}' not found.[/bold red]"
            )

    def action_cancel(self) -> None:
        self.dismiss()


# ---------------------------------------------------------------------------
# Import screen
# ---------------------------------------------------------------------------

class ImportScreen(Screen):
    """Import instruments from a JSON file."""

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
    ]

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with VerticalScroll(classes="form-container"):
            yield Static("[bold cyan]Import from JSON[/bold cyan]\n", classes="msg-info")
            yield Label("Path to JSON file")
            yield Input(placeholder="e.g. portfolio.json", id="inp-file")
            yield Label("Default exchange suffix  [dim](optional)[/dim]")
            yield Input(placeholder="e.g. DE, SW, AS", id="inp-exchange")
            with Horizontal(classes="btn-row"):
                yield Button("Import", variant="success", id="btn-import")
                yield Button("Cancel", variant="error", id="btn-cancel")
            yield Static("", id="import-status")
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-cancel":
            self.dismiss()
        elif event.button.id == "btn-import":
            self._do_import()

    def _do_import(self) -> None:
        filepath = self.query_one("#inp-file", Input).value.strip()
        exchange = self.query_one("#inp-exchange", Input).value.strip() or None

        if not filepath:
            self.query_one("#import-status", Static).update(
                "[bold red]Please enter a file path.[/bold red]"
            )
            return

        try:
            with open(filepath, "r") as f:
                instruments = json.load(f)
        except FileNotFoundError:
            self.query_one("#import-status", Static).update(
                f"[bold red]File not found: {filepath}[/bold red]"
            )
            return
        except json.JSONDecodeError as exc:
            self.query_one("#import-status", Static).update(
                f"[bold red]Invalid JSON: {exc}[/bold red]"
            )
            return

        if not isinstance(instruments, list):
            self.query_one("#import-status", Static).update(
                "[bold red]JSON must be an array of objects.[/bold red]"
            )
            return

        self.query_one("#import-status", Static).update(
            f"[bold yellow]Importing {len(instruments)} instruments...[/bold yellow]"
        )
        self._run_import(instruments, exchange)

    @work(thread=True)
    def _run_import(self, instruments: list, exchange: Optional[str]) -> None:
        total   = len(instruments)
        added   = 0
        skipped = 0

        for entry in instruments:
            if not isinstance(entry, dict):
                skipped += 1
                continue
            ticker    = entry.get("ticker")
            shares    = entry.get("shares")
            avg_price = entry.get("avg_price")
            if not ticker or shares is None or avg_price is None:
                skipped += 1
                continue
            try:
                shares    = float(shares)
                avg_price = float(avg_price)
            except (TypeError, ValueError):
                skipped += 1
                continue

            ok = ops_add_instrument(
                ticker=ticker,
                isin=entry.get("isin"),
                shares=shares,
                avg_purchase_price=avg_price,
                preferred_exchange=entry.get("exchange") or exchange,
            )
            if ok:
                added += 1
            else:
                skipped += 1

        msg = f"Import complete: {added} added, {skipped} skipped (of {total})"
        self.app.call_from_thread(self.notify, msg, severity="information")
        self.app.call_from_thread(self.dismiss)

    def action_cancel(self) -> None:
        self.dismiss()


# ---------------------------------------------------------------------------
# Main Textual App
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Custom themes
# ---------------------------------------------------------------------------

_MATRIX = Theme(
    name="matrix",
    primary="#00FF41",        # classic Matrix phosphor green
    secondary="#008F11",      # darker green for secondary elements
    warning="#39FF14",        # bright neon green for warnings
    error="#FF0000",          # red — the only non-green colour (errors must stand out)
    success="#00FF41",        # same phosphor green
    accent="#20C20E",         # slightly muted green for accents
    foreground="#00FF41",     # green text on black
    background="#000000",     # pure black
    surface="#0A0A0A",        # near-black for raised surfaces
    panel="#0D1F0D",          # very dark green tint for panels/borders
    dark=True,
    luminosity_spread=0.15,
    text_alpha=0.95,
)

_MONOCHROME = Theme(
    name="monochrome",
    primary="#FFFFFF",
    secondary="#AAAAAA",
    warning="#FFFF00",
    error="#FF4444",
    success="#00FF00",
    accent="#CCCCCC",
    foreground="#E0E0E0",
    background="#000000",
    surface="#111111",
    panel="#1A1A1A",
    dark=True,
)

_AMBER_TERMINAL = Theme(
    name="amber-terminal",
    primary="#FFB000",        # warm amber (IBM 3278 / VT220)
    secondary="#CC8800",
    warning="#FFCC00",
    error="#FF3300",
    success="#FFB000",
    accent="#FF9500",
    foreground="#FFB000",
    background="#000000",
    surface="#0A0800",
    panel="#1A1200",
    dark=True,
)

_PHOSPHOR_BLUE = Theme(
    name="phosphor-blue",
    primary="#33BBFF",        # P1 blue phosphor tube
    secondary="#1177AA",
    warning="#66DDFF",
    error="#FF3355",
    success="#33FFCC",
    accent="#2299DD",
    foreground="#33BBFF",
    background="#000000",
    surface="#000A12",
    panel="#001428",
    dark=True,
)

_CYBERPUNK = Theme(
    name="cyberpunk",
    primary="#FF2A6D",        # neon pink
    secondary="#05D9E8",      # electric cyan
    warning="#FFD319",        # neon yellow
    error="#FF0044",
    success="#01F9C6",        # neon teal
    accent="#05D9E8",
    foreground="#D1F7FF",
    background="#0D0221",     # deep midnight blue
    surface="#150535",
    panel="#1A0A3E",
    dark=True,
)

_OCEAN_DEEP = Theme(
    name="ocean-deep",
    primary="#0077B6",
    secondary="#00B4D8",
    warning="#F9C74F",
    error="#E63946",
    success="#2A9D8F",
    accent="#48CAE4",
    foreground="#CAF0F8",
    background="#03071E",
    surface="#0A1128",
    panel="#102040",
    dark=True,
)

_SUNSET = Theme(
    name="sunset",
    primary="#FF6B35",        # warm orange
    secondary="#F7C59F",      # pale gold
    warning="#FFE66D",
    error="#EF476F",
    success="#06D6A0",
    accent="#FF9F1C",
    foreground="#FFF1E6",
    background="#1A0A00",
    surface="#2D1810",
    panel="#3D2015",
    dark=True,
)

_ARCTIC = Theme(
    name="arctic",
    primary="#B0E0E6",        # powder blue
    secondary="#87CEEB",
    warning="#F0E68C",
    error="#CD5C5C",
    success="#90EE90",
    accent="#ADD8E6",
    foreground="#F0F8FF",     # alice blue
    background="#0B1929",
    surface="#0F2233",
    panel="#162D44",
    dark=True,
)

_SYNTHWAVE = Theme(
    name="synthwave",
    primary="#E040FB",        # bright magenta
    secondary="#7C4DFF",      # deep violet
    warning="#FFD740",
    error="#FF1744",
    success="#00E5FF",
    accent="#EA80FC",
    foreground="#F3E5F5",
    background="#0D0015",
    surface="#1A0029",
    panel="#2D004D",
    dark=True,
)

_FOREST = Theme(
    name="forest",
    primary="#4CAF50",        # material green
    secondary="#81C784",
    warning="#FFB74D",
    error="#E57373",
    success="#66BB6A",
    accent="#A5D6A7",
    foreground="#E8F5E9",
    background="#0A1A0A",
    surface="#102010",
    panel="#1A2E1A",
    dark=True,
)

_BLOOD_MOON = Theme(
    name="blood-moon",
    primary="#C62828",        # deep red
    secondary="#EF5350",
    warning="#FF8F00",
    error="#FF1744",
    success="#43A047",
    accent="#FF5252",
    foreground="#FFCDD2",
    background="#0A0000",
    surface="#1A0505",
    panel="#2D0A0A",
    dark=True,
)

_HIGH_CONTRAST = Theme(
    name="high-contrast",
    primary="#FFFFFF",
    secondary="#00FFFF",
    warning="#FFFF00",
    error="#FF0000",
    success="#00FF00",
    accent="#FF00FF",
    foreground="#FFFFFF",
    background="#000000",
    surface="#000000",
    panel="#1A1A1A",
    dark=True,
    text_alpha=1.0,
)

_CUSTOM_THEMES = [
    _MATRIX, _MONOCHROME, _AMBER_TERMINAL, _PHOSPHOR_BLUE, _CYBERPUNK,
    _OCEAN_DEEP, _SUNSET, _ARCTIC, _SYNTHWAVE, _FOREST, _BLOOD_MOON,
    _HIGH_CONTRAST,
]

# Curated list of popular themes shipped with Textual, ordered for cycling.
_THEME_NAMES = [
    "matrix",
    "monochrome",
    "amber-terminal",
    "phosphor-blue",
    "cyberpunk",
    "ocean-deep",
    "sunset",
    "arctic",
    "synthwave",
    "forest",
    "blood-moon",
    "high-contrast",
    "tokyo-night",
    "dracula",
    "monokai",
    "catppuccin-mocha",
    "nord",
    "gruvbox",
    "rose-pine",
    "solarized-dark",
    "textual-dark",
    "catppuccin-frappe",
    "catppuccin-macchiato",
    "rose-pine-moon",
    "atom-one-dark",
    "flexoki",
    "textual-light",
    "solarized-light",
    "catppuccin-latte",
    "atom-one-light",
    "rose-pine-dawn",
    "textual-ansi",
]


class LynxApp(App):
    """Lynx Portfolio Manager — Full-screen TUI."""

    TITLE = "Lynx Portfolio"
    SUB_TITLE = "Investment Portfolio Manager"
    CSS = APP_CSS

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("t", "cycle_theme", "Theme"),
    ]

    def on_mount(self) -> None:
        # Register custom themes first, then all built-in ones.
        for t in _CUSTOM_THEMES:
            self.register_theme(t)
        for name, theme_obj in BUILTIN_THEMES.items():
            self.register_theme(theme_obj)
        # Default to the Matrix theme — green-on-black hacker terminal style.
        self.theme = "matrix"
        self.push_screen(PortfolioScreen())

    def action_cycle_theme(self) -> None:
        """Cycle to the next theme in the curated list."""
        try:
            idx = _THEME_NAMES.index(self.theme)
        except ValueError:
            idx = -1
        next_idx = (idx + 1) % len(_THEME_NAMES)
        self.theme = _THEME_NAMES[next_idx]
        self.notify(f"Theme: {self.theme}", severity="information")
