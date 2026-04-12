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
    width: 60;
    height: auto;
    max-height: 12;
    border: thick $accent;
    background: $surface;
    padding: 1 2;
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
            "Mkt Value", "P&L",
        ]
        if self._show_eur:
            columns += ["EUR Val", "EUR P&L"]
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
            avg_price = inst.get("avg_purchase_price") or 0.0
            curr      = inst.get("current_price")
            ccy       = (inst.get("currency") or "EUR").upper()
            invested  = shares * avg_price
            qt        = inst.get("quote_type")
            shares_s  = _shares_str(shares, qt)

            if curr is not None:
                mkt_val = shares * curr
                pnl     = mkt_val - invested
                pct     = (pnl / invested * 100) if invested else 0.0
                curr_s  = f"{curr:,.2f}"
                mkt_s   = f"{mkt_val:,.2f}"
                pnl_s   = _pnl_text(pnl, pct)
                if self._show_eur:
                    mkt_eur = forex.to_eur(mkt_val, ccy)
                    pnl_eur = forex.to_eur(pnl, ccy)
                    eur_mkt_s = f"{mkt_eur:,.2f}" if mkt_eur is not None else "N/A"
                    eur_pnl_s = _pnl_text(pnl_eur, pct) if pnl_eur is not None else "N/A"
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
                (inst.get("name") or "—")[:30],
                exch[:20],
                shares_s,
                f"{avg_price:,.2f}",
                curr_s,
                inst.get("currency") or "—",
                mkt_s,
                pnl_s,
            ]
            if self._show_eur:
                row += [eur_mkt_s, eur_pnl_s]

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
        n = cache.delete()
        self.notify(f"Cache cleared ({n} entries)", severity="information")

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
        avg_price = inst.get("avg_purchase_price") or 0.0
        curr      = inst.get("current_price")
        invested  = shares * avg_price
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
            f"  [bold cyan]Avg Purchase Price[/bold cyan]  {avg_price:,.2f}",
            f"  [bold cyan]Current Price[/bold cyan]       {curr:,.2f}" if curr is not None else f"  [bold cyan]Current Price[/bold cyan]       N/A",
            f"  [bold cyan]Total Invested[/bold cyan]      {invested:,.2f}",
        ]

        if ccy != "EUR":
            inv_eur = forex.to_eur(invested, ccy)
            if inv_eur is not None:
                lines.append(f"  [bold cyan]Total Invested (EUR)[/bold cyan] {inv_eur:,.2f}")

        if curr is not None:
            mkt_val = shares * curr
            pnl     = mkt_val - invested
            pct     = (pnl / invested * 100) if invested else 0.0
            color   = "green" if pnl >= 0 else "red"
            sign    = "+" if pnl >= 0 else ""
            lines.append(f"  [bold cyan]Market Value[/bold cyan]        {mkt_val:,.2f}")
            if ccy != "EUR":
                mkt_eur = forex.to_eur(mkt_val, ccy)
                if mkt_eur is not None:
                    lines.append(f"  [bold cyan]Market Value (EUR)[/bold cyan]  {mkt_eur:,.2f}")
            lines.append(f"  [bold cyan]P&L[/bold cyan]                 [{color}]{sign}{pnl:,.2f} ({sign}{pct:.2f}%)[/{color}]")
            if ccy != "EUR":
                pnl_eur = forex.to_eur(pnl, ccy)
                if pnl_eur is not None:
                    lines.append(f"  [bold cyan]P&L (EUR)[/bold cyan]           [{color}]{sign}{pnl_eur:,.2f} ({sign}{pct:.2f}%)[/{color}]")

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
            yield Label("Average purchase price")
            yield Input(placeholder="e.g. 150.00", id="inp-avgprice", type="number")
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
            avg_price = float(price_s)
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
        cur_price  = inst.get("avg_purchase_price", 0.0)

        yield Header(show_clock=True)
        with VerticalScroll(classes="form-container"):
            yield Static(
                f"[bold cyan]Update {self._ticker}[/bold cyan]\n"
                f"  Current shares: {cur_shares}  |  Current avg price: {cur_price:,.2f}\n",
                classes="msg-info",
            )
            yield Label("New shares  [dim](leave empty to keep)[/dim]")
            yield Input(placeholder=str(cur_shares), id="inp-shares", type="number")
            yield Label("New average price  [dim](leave empty to keep)[/dim]")
            yield Input(placeholder=f"{cur_price:,.2f}", id="inp-price", type="number")
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

class LynxApp(App):
    """Lynx Portfolio Manager — Full-screen TUI."""

    TITLE = "Lynx Portfolio"
    SUB_TITLE = "Investment Portfolio Manager"
    CSS = APP_CSS

    BINDINGS = [
        Binding("q", "quit", "Quit"),
    ]

    def on_mount(self) -> None:
        self.push_screen(PortfolioScreen())
