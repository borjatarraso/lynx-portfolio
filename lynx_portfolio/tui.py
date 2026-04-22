"""
Full-screen TUI mode for Lynx Portfolio, powered by Textual.
Launched via: lynx-portfolio -tui  /  lynx-portfolio --textual-ui
"""

from __future__ import annotations

import json
import textwrap
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

from lynx_investor_core.pager import PagingAppMixin, tui_paging_bindings

from . import ABOUT_LINES
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

#portfolio-summary {
    height: auto;
    max-height: 5;
    padding: 0 2;
    background: $surface-darken-1;
    border-top: solid $accent;
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
# About screen
# ---------------------------------------------------------------------------

class AboutScreen(ModalScreen):
    """Display application information."""

    BINDINGS = [
        Binding("escape", "dismiss", "Close"),
        Binding("enter", "dismiss", "Close"),
    ]

    def compose(self) -> ComposeResult:
        from .logo import load_logo_ascii_rich
        with Vertical(id="confirm-dialog"):
            yield Static(load_logo_ascii_rich())
            yield Label("\n".join(ABOUT_LINES))
            with Horizontal(classes="btn-row"):
                yield Button("Close", variant="primary", id="btn-close")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss()

    def action_dismiss(self) -> None:
        self.dismiss()


# ---------------------------------------------------------------------------
# Animation screen
# ---------------------------------------------------------------------------

_EGG_CSS = """
EggScreen {
    background: #000000;
}
EggScreen > Vertical {
    background: #000000;
    width: 100%;
    height: 100%;
}
EggScreen #egg-canvas {
    width: 100%;
    height: 1fr;
    content-align: center middle;
    text-align: center;
    background: #000000;
    color: #00ff00;
}
EggScreen #egg-hint {
    width: 100%;
    height: 1;
    text-align: center;
    background: #000000;
    color: #444444;
    dock: bottom;
}
"""

class EggScreen(Screen):
    """Nothing to see here."""

    CSS = _EGG_CSS
    BINDINGS = [
        Binding("escape", "go_back", "", show=False, priority=True),
        Binding("space", "go_back", "", show=False, priority=True),
        Binding("q", "go_back", "", show=False, priority=True),
    ]

    _FRAMES = [
        # Phase 0-7: Lynx face blinking
        ("[bold cyan]"
         "    /\\_/\\\n"
         "   ( o.o )\n"
         "    > ^ <\n"
         "   /|   |\\\n"
         "  (_|   |_)[/bold cyan]"),
        ("[bold cyan]"
         "    /\\_/\\\n"
         "   ( -.o )\n"
         "    > ^ <\n"
         "   /|   |\\\n"
         "  (_|   |_)[/bold cyan]"),
        ("[bold cyan]"
         "    /\\_/\\\n"
         "   ( o.- )\n"
         "    > ^ <\n"
         "   /|   |\\\n"
         "  (_|   |_)[/bold cyan]"),
        ("[bold cyan]"
         "    /\\_/\\\n"
         "   ( ^.^ )\n"
         "    > ^ <\n"
         "   /|   |\\\n"
         "  (_|   |_)[/bold cyan]"),
    ]

    _RAINBOW = ["red", "yellow", "green", "cyan", "blue", "magenta"]

    def __init__(self) -> None:
        super().__init__()
        self._tick = 0
        self._phase = 0
        self._sound_started = False

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static(id="egg-canvas")
            yield Static("Press Esc to close", id="egg-hint")

    def on_mount(self) -> None:
        self._timer = self.set_interval(0.22, self._tick_frame)
        # Start sound
        if not self._sound_started:
            self._sound_started = True
            try:
                from .egg import _play_sound_async
                _play_sound_async()
            except Exception:
                pass

    def _tick_frame(self) -> None:
        canvas = self.query_one("#egg-canvas", Static)
        t = self._tick
        p = self._phase

        if p == 0:
            # Blinking lynx
            frame = self._FRAMES[t % len(self._FRAMES)]
            canvas.update(f"\n\n\n{frame}\n\n[dim]🐱 meow[/dim]")
            if t > 7:
                self._phase = 1
                self._tick = 0
                return

        elif p == 1:
            # Rainbow banner
            c = self._RAINBOW[t % len(self._RAINBOW)]
            canvas.update(
                f"\n\n[bold {c}]"
                " ██╗     ██╗   ██╗███╗   ██╗██╗  ██╗\n"
                " ██║     ╚██╗ ██╔╝████╗  ██║╚██╗██╔╝\n"
                " ██║      ╚████╔╝ ██╔██╗ ██║ ╚███╔╝ \n"
                " ██║       ╚██╔╝  ██║╚██╗██║ ██╔██╗ \n"
                " ███████╗   ██║   ██║ ╚████║██╔╝ ██╗\n"
                " ╚══════╝   ╚═╝   ╚═╝  ╚═══╝╚═╝  ╚═╝\n"
                f"[/bold {c}]"
            )
            if t > 11:
                self._phase = 2
                self._tick = 0
                return

        elif p == 2:
            # Bull market
            c = "green" if t % 2 == 0 else "bold green"
            canvas.update(
                f"\n[{c}]"
                "           /|            |\\\n"
                "          / |    ____    | \\\n"
                "         /  |   /    \\   |  \\\n"
                "        /   |  |  $$  |  |   \\\n"
                "            |  |  $$  |  |\n"
                "             \\ |      | /\n"
                "              \\|______|/\n"
                "               |      |\n"
                "              /|      |\\\n"
                "             / |      | \\\n"
                "               |  ||  |\n"
                "              /|      |\\\n"
                "             /_|      |_\\\n"
                f"[/{c}]\n\n"
                "[bold green]📈  BULL MARKET DETECTED!  📈[/bold green]"
            )
            if t > 8:
                self._phase = 3
                self._tick = 0
                return

        elif p == 3:
            # Chart going up
            c = self._RAINBOW[t % len(self._RAINBOW)]
            canvas.update(
                f"\n[bold {c}]"
                "                               ╱\n"
                "   $$$                       ╱\n"
                "   $$$                     ╱\n"
                "   $$$                   ╱\n"
                "   $$$                 ╱   ╲\n"
                "   $$$     ╱╲        ╱       ╲ ╱\n"
                "   $$$   ╱    ╲    ╱\n"
                "   $$$ ╱        ╲╱\n"
                "   ───────────────────────────────\n"
                "    JAN FEB MAR APR MAY JUN JUL\n"
                f"[/bold {c}]"
            )
            if t > 8:
                self._phase = 4
                self._tick = 0
                return

        elif p == 4:
            # Rocket
            flames = "~" * min(t + 1, 10)
            c = "bold yellow" if t % 2 == 0 else "bold red"
            canvas.update(
                "\n[bold white]"
                "        *\n"
                "       /|\\\n"
                "      / | \\\n"
                "     /  |  \\\n"
                "    |   |   |\n"
                "    |  LPM  |\n"
                "    |       |\n"
                "    |_______|\n"
                "[/bold white]"
                f"[{c}]"
                f"      /{flames}\\\n"
                f"     /{flames}{flames}\\\n"
                f"[/{c}]\n"
                "[bold yellow]🚀  TO THE MOON!  🚀[/bold yellow]"
            )
            if t > 10:
                self._phase = 5
                self._tick = 0
                return

        elif p == 5:
            # Fireworks
            sparkles = "✦✧★☆⚡💎🔥💰📈🚀🐂💹🏆🎯🎰"
            c1 = self._RAINBOW[t % len(self._RAINBOW)]
            c2 = self._RAINBOW[(t + 2) % len(self._RAINBOW)]
            c3 = self._RAINBOW[(t + 4) % len(self._RAINBOW)]
            spark_line = " ".join(sparkles[(t + i) % len(sparkles)] for i in range(14))
            fw_chars = [". ", "* ", ". ", "* ", ". "]
            fw = " ".join(fw_chars[i % len(fw_chars)] for i in range(t % 5 + 8))
            canvas.update(
                f"\n[bold {c1}]{fw}[/bold {c1}]\n"
                f"[bold {c2}]   {fw}[/bold {c2}]\n"
                f"[bold {c3}]{fw}   [/bold {c3}]\n\n"
                "🌕🌕🌕🌕🌕🌕🌕🌕\n\n"
                f"{spark_line}\n\n"
                f"[bold {c1}]★  L Y N X   P O R T F O L I O  ★[/bold {c1}]\n\n"
                "[dim]Your portfolio is watching. Always.[/dim]\n"
            )
            if t > 14:
                self._phase = 6
                self._tick = 0
                return

        elif p == 6:
            # Grand finale — big lynx
            c = self._RAINBOW[t % len(self._RAINBOW)]
            sparkles = "✦✧★☆⚡💎🔥💰📈🚀🐂💹🏆🎯🎰"
            spark_line = " ".join(sparkles[(t + i) % len(sparkles)] for i in range(16))
            canvas.update(
                f"\n[bold {c}]"
                "              ╱╲_╱╲\n"
                "             ╱      ╲\n"
                "            │  ●  ●  │\n"
                "            │   ╲╱   │\n"
                "             ╲  ──  ╱\n"
                "       ╱╲    │╲    ╱│    ╱╲\n"
                "      ╱  ╲───╯ ╲──╱ ╰───╱  ╲\n"
                "     │    ╲             ╱    │\n"
                "     │     ╲───────────╱     │\n"
                "      ╲     │         │     ╱\n"
                "       ╲    │         │    ╱\n"
                "        ╰───╯         ╰───╯\n"
                f"[/bold {c}]\n"
                f"[bold cyan]Lynx Portfolio[/bold cyan]\n"
                f"{spark_line}\n"
            )
            if t > 14:
                self._timer.stop()
                self.app.pop_screen()
                return

        self._tick += 1

    def action_go_back(self) -> None:
        self._timer.stop()
        self.app.pop_screen()


# ---------------------------------------------------------------------------
# Portfolio screen (main screen)
# ---------------------------------------------------------------------------

class PortfolioScreen(Screen):
    """Main portfolio table view."""

    BINDINGS = [
        Binding("a",       "add",           "Add"),
        Binding("d",       "delete",        "Delete"),
        Binding("e",       "edit",          "Edit"),
        Binding("r",       "refresh_one",   "Refresh"),
        Binding("R",       "refresh_all",   "Refresh All"),
        Binding("A",       "auto_update",   "Auto-Update"),
        Binding("i",       "import_json",   "Import"),
        Binding("c",       "clear_cache",   "Clear Cache"),
        Binding("f1",      "about",         "About"),
        Binding("q",       "quit_app",      "Quit"),
        Binding("f9",      "xyzzy",         "", show=False, priority=True),
    ]

    _auto_update_timer = None
    _AUTO_UPDATE_INTERVAL = 60  # seconds

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield DataTable(id="portfolio-table")
        yield Static(id="portfolio-summary")
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
            self.query_one("#portfolio-summary", Static).update("")
            return

        total_invested     = 0.0
        total_market       = 0.0
        total_invested_eur = 0.0
        total_market_eur   = 0.0
        total_today_eur    = 0.0
        has_today_data     = False
        has_eur_gap        = False

        for inst in instruments:
            shares    = inst.get("shares") or 0.0
            avg_price = inst.get("avg_purchase_price")   # may be None
            curr      = inst.get("current_price")
            ccy       = (inst.get("currency") or "EUR").upper()
            has_cost  = avg_price is not None
            qt        = inst.get("quote_type")
            shares_s  = _shares_str(shares, qt)

            if has_cost:
                invested = shares * avg_price
                total_invested += invested
                invested_eur = forex.to_eur(invested, ccy)
                if invested_eur is not None:
                    total_invested_eur += invested_eur
                else:
                    has_eur_gap = True

            rmc = inst.get("regular_market_change")
            if rmc is not None:
                day_change_eur = forex.to_eur(rmc * shares, ccy)
                if day_change_eur is not None:
                    total_today_eur += day_change_eur
                    has_today_data = True

            if curr is not None:
                mkt_val = shares * curr
                total_market += mkt_val
                curr_s  = f"{curr:,.2f}"
                mkt_s   = f"{mkt_val:,.2f}"
                if has_cost:
                    pnl = mkt_val - invested
                    pct = (pnl / invested * 100) if invested else 0.0
                    pnl_s = _pnl_text(pnl, pct)
                else:
                    pnl = None
                    pct = None
                    pnl_s = "—"
                if self._show_eur:
                    mkt_eur = forex.to_eur(mkt_val, ccy)
                    if mkt_eur is not None:
                        total_market_eur += mkt_eur
                        eur_mkt_s = f"{mkt_eur:,.2f}"
                    else:
                        has_eur_gap = True
                        eur_mkt_s = "N/A"
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

        # Update summary bar
        self._update_summary(
            total_invested, total_market,
            total_invested_eur, total_market_eur,
            total_today_eur, has_today_data, has_eur_gap,
        )

    def _update_summary(
        self,
        total_invested: float,
        total_market: float,
        total_invested_eur: float,
        total_market_eur: float,
        total_today_eur: float,
        has_today_data: bool,
        has_eur_gap: bool,
    ) -> None:
        today_sign  = "+" if total_today_eur >= 0 else ""
        today_color = "green" if total_today_eur >= 0 else "red"
        today_str   = (
            f"[{today_color}]{today_sign}{total_today_eur:,.2f}[/{today_color}]"
            if has_today_data else "[dim]N/A[/dim]"
        )

        if self._show_eur:
            total_pnl_eur = total_market_eur - total_invested_eur
            total_pct_eur = (total_pnl_eur / total_invested_eur * 100) if total_invested_eur else 0.0
            eur_color = "green" if total_pnl_eur >= 0 else "red"
            eur_sign  = "+" if total_pnl_eur >= 0 else ""
            partial   = " [dim](partial)[/dim]" if has_eur_gap else ""
            text = (
                f"[bold cyan]EUR Invested:[/bold cyan] {total_invested_eur:,.2f}  "
                f"[bold cyan]EUR Market Value:[/bold cyan] {total_market_eur:,.2f}  "
                f"[bold cyan]EUR P&L:[/bold cyan] [{eur_color}]{eur_sign}{total_pnl_eur:,.2f} "
                f"({eur_sign}{total_pct_eur:.2f}%)[/{eur_color}]{partial}  "
                f"[bold cyan]EUR Market Today:[/bold cyan] {today_str}"
            )
        else:
            total_pnl = total_market - total_invested
            total_pct = (total_pnl / total_invested * 100) if total_invested else 0.0
            color = "green" if total_pnl >= 0 else "red"
            sign  = "+" if total_pnl >= 0 else ""
            text = (
                f"[bold cyan]Invested:[/bold cyan] {total_invested:,.2f}  "
                f"[bold cyan]Market Value:[/bold cyan] {total_market:,.2f}  "
                f"[bold cyan]P&L:[/bold cyan] [{color}]{sign}{total_pnl:,.2f} "
                f"({sign}{total_pct:.2f}%)[/{color}]  "
                f"[bold cyan]EUR Market Today:[/bold cyan] {today_str}"
            )

        self.query_one("#portfolio-summary", Static).update(text)

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
        try:
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
        except Exception as exc:
            self.app.call_from_thread(self.notify, f"Refresh error: {exc}", severity="error")
        self.app.call_from_thread(self._reload_table)

    def action_refresh_all(self) -> None:
        self._do_refresh_all()

    @work(thread=True)
    def _do_refresh_all(self) -> None:
        try:
            instruments = database.get_all_instruments()
            count = 0
            for inst in instruments:
                ticker = inst["ticker"]
                isin   = inst.get("isin")
                try:
                    cache.delete(ticker)
                    data = fetcher.fetch_instrument_data(ticker, isin)
                    if data:
                        cache.put(ticker, data)
                        database.apply_cache_to_portfolio(ticker, data)
                        count += 1
                except Exception:
                    pass  # continue with remaining instruments
            self.app.call_from_thread(
                self.notify, f"Refreshed {count}/{len(instruments)} instruments",
                severity="information",
            )
        except Exception as exc:
            self.app.call_from_thread(self.notify, f"Refresh error: {exc}", severity="error")
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

    def action_auto_update(self) -> None:
        if self._auto_update_timer is not None:
            self._auto_update_timer.stop()
            self._auto_update_timer = None
            self.notify("Auto-update OFF", severity="information")
        else:
            self._auto_update_timer = self.set_interval(
                self._AUTO_UPDATE_INTERVAL, self._auto_refresh_tick,
            )
            self.notify(
                f"Auto-update ON (every {self._AUTO_UPDATE_INTERVAL}s)",
                severity="information",
            )

    @work(thread=True)
    def _auto_refresh_tick(self) -> None:
        from .operations import refresh_all as ops_refresh_all
        ops_refresh_all()
        self.app.call_from_thread(self._reload_table)

    def action_about(self) -> None:
        self.app.push_screen(AboutScreen())

    def action_quit_app(self) -> None:
        self.app.exit()

    def action_xyzzy(self) -> None:
        self.app.push_screen(EggScreen())

    def on_key(self, event) -> None:
        if event.key == "f9":
            event.prevent_default()
            event.stop()
            self.action_xyzzy()

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

        # Label column is 22 chars so even the longest label
        # ("Total Invested (EUR)" = 20 chars) gets 2 spaces of padding.
        lines = [
            f"[bold cyan]{'─' * 60}[/bold cyan]",
            f"[bold cyan]  {self._ticker}[/bold cyan]",
            f"[bold cyan]{'─' * 60}[/bold cyan]",
            "",
            f"  [bold cyan]Ticker[/bold cyan]                {inst.get('ticker', '')}",
            f"  [bold cyan]ISIN[/bold cyan]                  {inst.get('isin') or '—'}",
            f"  [bold cyan]Name[/bold cyan]                  {inst.get('name') or '—'}",
            f"  [bold cyan]Exchange[/bold cyan]              {exch}",
            f"  [bold cyan]Currency[/bold cyan]              {inst.get('currency') or '—'}",
            f"  [bold cyan]Sector[/bold cyan]                {inst.get('sector') or '—'}",
            f"  [bold cyan]Industry[/bold cyan]              {inst.get('industry') or '—'}",
            f"  [bold cyan]Shares[/bold cyan]                {_shares_str(shares, qt)}",
            f"  [bold cyan]Avg Purchase Price[/bold cyan]    {avg_price:,.2f}" if has_cost else f"  [bold cyan]Avg Purchase Price[/bold cyan]    [dim]Not tracked[/dim]",
            f"  [bold cyan]Current Price[/bold cyan]         {curr:,.2f}" if curr is not None else f"  [bold cyan]Current Price[/bold cyan]         N/A",
        ]

        if has_cost:
            invested = shares * avg_price
            lines.append(f"  [bold cyan]Total Invested[/bold cyan]        {invested:,.2f}")
            if ccy != "EUR":
                inv_eur = forex.to_eur(invested, ccy)
                if inv_eur is not None:
                    lines.append(f"  [bold cyan]Total Invested (EUR)[/bold cyan]  {inv_eur:,.2f}")
        else:
            lines.append(f"  [bold cyan]Total Invested[/bold cyan]        [dim]Not tracked[/dim]")

        if curr is not None:
            mkt_val = shares * curr
            lines.append(f"  [bold cyan]Market Value[/bold cyan]          {mkt_val:,.2f}")
            if ccy != "EUR":
                mkt_eur = forex.to_eur(mkt_val, ccy)
                if mkt_eur is not None:
                    lines.append(f"  [bold cyan]Market Value (EUR)[/bold cyan]    {mkt_eur:,.2f}")
            if has_cost:
                pnl   = mkt_val - invested
                pct   = (pnl / invested * 100) if invested else 0.0
                color = "green" if pnl >= 0 else "red"
                sign  = "+" if pnl >= 0 else ""
                lines.append(f"  [bold cyan]P&L[/bold cyan]                   [{color}]{sign}{pnl:,.2f} ({sign}{pct:.2f}%)[/{color}]")
                if ccy != "EUR":
                    pnl_eur = forex.to_eur(pnl, ccy)
                    if pnl_eur is not None:
                        lines.append(f"  [bold cyan]P&L (EUR)[/bold cyan]             [{color}]{sign}{pnl_eur:,.2f} ({sign}{pct:.2f}%)[/{color}]")
            else:
                lines.append(f"  [bold cyan]P&L[/bold cyan]                   [dim]Not tracked[/dim]")

        if inst.get("description"):
            # Wrap long descriptions so continuation lines align with the value column.
            # The value column starts at visible position 24 (2-space indent + 22-char label area).
            indent = " " * 24
            max_width = 60  # matches the separator line width
            wrapped = textwrap.fill(
                inst["description"],
                width=max_width,
                initial_indent="",
                subsequent_indent=indent,
            )
            lines.append(f"  [bold cyan]Description[/bold cyan]           {wrapped}")

        lines.append(f"  [bold cyan]Added[/bold cyan]                 {inst.get('created_at') or '—'}")
        lines.append(f"  [bold cyan]Updated[/bold cyan]               {inst.get('updated_at') or '—'}")
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
            yield Label("Search by name  [dim](e.g. 'Apple', 'Vanguard FTSE')[/dim]")
            with Horizontal(classes="btn-row"):
                yield Input(placeholder="Company or fund name", id="inp-search-name")
                yield Button("Search", variant="primary", id="btn-search")
            yield Static("", id="search-results")
            sel_input = Input(placeholder="Type result number (1-10) to select",
                              id="inp-select", type="integer")
            sel_input.display = False
            yield sel_input
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

    _search_results: list = []

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-cancel":
            self.dismiss()
        elif event.button.id == "btn-search":
            self._do_search()
        elif event.button.id == "btn-add":
            self._do_add()
        elif event.button.id and event.button.id.startswith("btn-pick-"):
            idx = int(event.button.id.split("-")[-1])
            if 0 <= idx < len(self._search_results):
                self._fill_from_result(self._search_results[idx])

    @work(thread=True)
    def _do_search(self) -> None:
        from .validation import sanitise_search_query
        raw = self.query_one("#inp-search-name", Input).value.strip()
        if not raw:
            self.app.call_from_thread(
                self.query_one("#search-results", Static).update,
                "[yellow]Enter a name to search.[/yellow]",
            )
            return
        query, qerr = sanitise_search_query(raw)
        if qerr:
            self.app.call_from_thread(
                self.query_one("#search-results", Static).update,
                f"[red]{qerr}[/red]",
            )
            return
        self.app.call_from_thread(
            self.query_one("#search-results", Static).update,
            f"[dim]Searching for '{query}'…[/dim]",
        )
        from . import fetcher
        try:
            results = fetcher.search_by_name(query)
        except Exception:
            results = []
        # Update results list on main thread for thread safety
        def _set_results():
            self._search_results = results
        self.app.call_from_thread(_set_results)
        if not results:
            self.app.call_from_thread(
                self.query_one("#search-results", Static).update,
                f"[red]No results for '{query}'.[/red]",
            )
            return
        lines = [f"[bold]Results for '{query}':[/bold]\n"]
        for i, r in enumerate(results[:10]):
            name = r.get("longname") or r.get("shortname", "")
            lines.append(
                f"  [cyan]{i + 1:>2}[/cyan]  "
                f"[bold]{r['symbol']:<14}[/bold]  "
                f"{name:<30}  "
                f"[dim]{r['exchange_display']}  {r['quote_type']}[/dim]"
            )
        lines.append("\n[dim]Type a number (1-"
                     + str(min(len(results), 10))
                     + ") in the 'Select' field to pick a result.[/dim]")

        def _show():
            self.query_one("#search-results", Static).update("\n".join(lines))
            # Show the selection input
            try:
                sel = self.query_one("#inp-select")
                sel.display = True
                sel.value = ""
                sel.focus()
            except Exception:
                pass
        self.app.call_from_thread(_show)

        # Auto-fill top result
        if results:
            top = results[0]
            def _autofill():
                self._fill_from_result(top)
            self.app.call_from_thread(_autofill)

    def _fill_from_result(self, chosen: dict) -> None:
        """Auto-fill ticker, ISIN, and exchange from a search result."""
        self.query_one("#inp-ticker", Input).value = chosen["symbol"]
        isin = chosen.get("isin") or ""
        if isin:
            self.query_one("#inp-isin", Input).value = isin
        sym = chosen["symbol"]
        if "." in sym:
            self.query_one("#inp-exchange", Input).value = sym.rsplit(".", 1)[1]
        name = chosen.get("longname") or chosen.get("shortname", "")
        self.query_one("#search-results", Static).update(
            f"[green]Selected: {chosen['symbol']} — {name}[/green]"
        )
        # Hide the selection input
        try:
            self.query_one("#inp-select").display = False
        except Exception:
            pass

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "inp-select":
            val = event.value.strip()
            try:
                idx = int(val) - 1
            except (ValueError, TypeError):
                return
            if 0 <= idx < len(self._search_results):
                self._fill_from_result(self._search_results[idx])

    def _do_add(self) -> None:
        from .validation import (
            validate_ticker, validate_isin, validate_shares, validate_price,
            validate_exchange,
        )

        ticker   = self.query_one("#inp-ticker", Input).value.strip()
        isin     = self.query_one("#inp-isin", Input).value.strip()
        exchange = self.query_one("#inp-exchange", Input).value.strip()
        shares_s = self.query_one("#inp-shares", Input).value.strip()
        price_s  = self.query_one("#inp-avgprice", Input).value.strip()

        status = self.query_one("#add-status", Static)

        if not ticker and not isin:
            status.update("[bold red]Provide at least a ticker or ISIN.[/bold red]")
            return

        if ticker:
            ticker, err = validate_ticker(ticker)
            if err:
                status.update(f"[bold red]{err}[/bold red]")
                return

        if isin:
            isin, err = validate_isin(isin)
            if err:
                status.update(f"[bold red]{err}[/bold red]")
                return

        if exchange:
            exchange, err = validate_exchange(exchange)
            if err:
                status.update(f"[bold red]{err}[/bold red]")
                return

        shares, err = validate_shares(shares_s)
        if err:
            status.update(f"[bold red]{err}[/bold red]")
            return

        avg_price, err = validate_price(price_s)
        if err:
            status.update(f"[bold red]{err}[/bold red]")
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
        try:
            ok = ops_add_instrument(
                ticker=ticker,
                isin=isin,
                shares=shares,
                avg_purchase_price=avg_price,
                preferred_exchange=exchange,
            )
        except Exception as exc:
            self.app.call_from_thread(
                self.query_one("#add-status", Static).update,
                f"[bold red]Error: {exc}[/bold red]",
            )
            return
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

        from .validation import validate_shares, validate_price
        status = self.query_one("#edit-status", Static)
        kwargs: dict = {}
        if shares_s:
            val, err = validate_shares(shares_s)
            if err:
                status.update(f"[bold red]{err}[/bold red]")
                return
            kwargs["shares"] = val
        if price_s:
            val, err = validate_price(price_s)
            if err:
                status.update(f"[bold red]{err}[/bold red]")
                return
            kwargs["avg_purchase_price"] = val

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
            if not ticker or shares is None:
                skipped += 1
                continue
            try:
                shares    = float(shares)
                if avg_price is not None:
                    avg_price = float(avg_price)
            except (TypeError, ValueError):
                skipped += 1
                continue

            try:
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
            except Exception:
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


class LynxApp(PagingAppMixin, App):
    """Lynx Portfolio Manager — Full-screen TUI."""

    TITLE = "Lynx Portfolio"
    SUB_TITLE = "Investment Portfolio Manager"
    CSS = APP_CSS

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("t", "cycle_theme", "Theme"),
        *tui_paging_bindings(),
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
