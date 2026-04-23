"""
Graphical interface for Lynx Portfolio, powered by tkinter/ttk.
Launched via: lynx-portfolio -x  /  lynx-portfolio --gui

Dark-themed financial dashboard with splash screen, grouped toolbar,
colour-coded P&L, and polished modal dialogs.
"""

from __future__ import annotations

import json
import os
import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from typing import Optional, Dict

from lynx_investor_core.gui_themes import ThemeCycler, apply_theme

from . import APP_NAME, VERSION, LICENSE, LICENSE_URL, LICENSE_TEXT, ABOUT_LINES, SUITE_LABEL
from . import database, cache, forex
from .display import _shares_str
from .operations import (
    Notifier,
    set_notifier,
    add_instrument as ops_add_instrument,
    refresh_instrument as ops_refresh_instrument,
    refresh_all as ops_refresh_all,
)


# ---------------------------------------------------------------------------
# Colour palette  (dark financial-dashboard theme)
# ---------------------------------------------------------------------------

_C = {
    "bg":           "#0f111a",   # deep navy-black
    "bg_alt":       "#161927",   # slightly lighter (alternating rows)
    "surface":      "#1a1d2e",   # cards / dialogs
    "surface2":     "#222640",   # elevated surface (toolbar)
    "border":       "#2a2e45",   # subtle borders
    "fg":           "#e0e0e8",   # primary text
    "fg_dim":       "#7a7f99",   # secondary / muted text
    "fg_heading":   "#ffffff",   # headings
    "accent":       "#38bdf8",   # sky-blue accent (buttons, links)
    "accent_hover": "#7dd3fc",   # lighter on hover
    "accent_dark":  "#0284c7",   # pressed / active
    "green":        "#4ade80",   # profit / success
    "green_bg":     "#052e16",   # subtle green tint
    "red":          "#f87171",   # loss / error
    "red_bg":       "#450a0a",   # subtle red tint
    "yellow":       "#fbbf24",   # warnings
    "cyan":         "#22d3ee",   # info highlights
    "select":       "#1e3a5f",   # selected row
    "btn_bg":       "#2a2e45",   # button background
    "btn_fg":       "#e0e0e8",   # button text
    "entry_bg":     "#161927",   # entry fields
    "entry_fg":     "#e0e0e8",   # entry text
}


# ---------------------------------------------------------------------------
# GUI Notifier  (thread-safe)
# ---------------------------------------------------------------------------

class _GUINotifier(Notifier):
    def __init__(self, root: tk.Tk, callback):
        self._root = root
        self._cb = callback

    def _schedule(self, msg: str, level: str) -> None:
        self._root.after(0, self._cb, msg, level)

    def info(self, msg: str) -> None:  self._schedule(msg, "info")
    def ok(self, msg: str) -> None:    self._schedule(msg, "ok")
    def err(self, msg: str) -> None:   self._schedule(msg, "error")
    def warn(self, msg: str) -> None:  self._schedule(msg, "warning")
    def show_instrument(self, inst: dict) -> None: pass


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _pnl_text(pnl: float, pct: float) -> str:
    sign = "+" if pnl >= 0 else ""
    return f"{sign}{pnl:,.2f} ({sign}{pct:.2f}%)"


def _price_str(value: Optional[float]) -> str:
    return f"{value:,.2f}" if value is not None else "N/A"


# ---------------------------------------------------------------------------
# Style setup  (call once after Tk() is created)
# ---------------------------------------------------------------------------

def _apply_dark_theme(root: tk.Tk) -> ttk.Style:
    style = ttk.Style(root)
    style.theme_use("clam")

    # --- Global defaults ---
    style.configure(".", background=_C["bg"], foreground=_C["fg"],
                    borderwidth=0, font=("Segoe UI", 10))

    # --- Treeview (portfolio table) ---
    style.configure("Treeview",
                    background=_C["bg"], foreground=_C["fg"],
                    fieldbackground=_C["bg"], rowheight=28,
                    font=("Consolas", 10), borderwidth=0)
    style.configure("Treeview.Heading",
                    background=_C["surface2"], foreground=_C["accent"],
                    font=("Segoe UI", 10, "bold"), borderwidth=0,
                    relief="flat")
    style.map("Treeview",
              background=[("selected", _C["select"])],
              foreground=[("selected", _C["fg_heading"])])
    style.map("Treeview.Heading",
              background=[("active", _C["border"])])

    # --- Buttons ---
    style.configure("TButton",
                    background=_C["btn_bg"], foreground=_C["btn_fg"],
                    padding=(14, 7), font=("Segoe UI", 9),
                    borderwidth=1, relief="flat")
    style.map("TButton",
              background=[("active", _C["border"]), ("pressed", _C["accent_dark"])],
              foreground=[("active", _C["fg_heading"])])

    style.configure("Accent.TButton",
                    background=_C["accent_dark"], foreground="#ffffff",
                    padding=(16, 8), font=("Segoe UI", 10, "bold"))
    style.map("Accent.TButton",
              background=[("active", _C["accent"]), ("pressed", _C["accent_dark"])])

    style.configure("Danger.TButton",
                    background="#7f1d1d", foreground="#fca5a5",
                    padding=(14, 7), font=("Segoe UI", 9))
    style.map("Danger.TButton",
              background=[("active", "#991b1b")])

    # --- Labels ---
    style.configure("TLabel", background=_C["bg"], foreground=_C["fg"])
    style.configure("Title.TLabel", font=("Segoe UI", 16, "bold"),
                    foreground=_C["accent"])
    style.configure("Subtitle.TLabel", font=("Segoe UI", 10),
                    foreground=_C["fg_dim"])
    style.configure("Heading.TLabel", font=("Segoe UI", 12, "bold"),
                    foreground=_C["fg_heading"])
    style.configure("Status.TLabel", font=("Consolas", 9),
                    foreground=_C["fg_dim"])
    style.configure("Summary.TLabel", font=("Segoe UI", 10),
                    foreground=_C["fg"])
    style.configure("DialogTitle.TLabel", font=("Segoe UI", 13, "bold"),
                    foreground=_C["accent"])
    style.configure("FieldLabel.TLabel", font=("Segoe UI", 10),
                    foreground=_C["fg_dim"])
    style.configure("DetailLabel.TLabel", font=("Segoe UI", 10, "bold"),
                    foreground=_C["accent"])
    style.configure("DetailValue.TLabel", font=("Consolas", 10),
                    foreground=_C["fg"])
    style.configure("PnlGreen.TLabel", foreground=_C["green"])
    style.configure("PnlRed.TLabel", foreground=_C["red"])
    style.configure("Error.TLabel", foreground=_C["red"],
                    font=("Segoe UI", 9))
    style.configure("Splash.TLabel", background=_C["surface"])

    # --- Frames ---
    style.configure("TFrame", background=_C["bg"])
    style.configure("Toolbar.TFrame", background=_C["surface2"])
    style.configure("Card.TFrame", background=_C["surface"])
    style.configure("Splash.TFrame", background=_C["surface"])

    # --- Entries ---
    style.configure("TEntry",
                    fieldbackground=_C["entry_bg"], foreground=_C["entry_fg"],
                    insertcolor=_C["fg"], borderwidth=1, relief="solid")
    style.map("TEntry",
              fieldbackground=[("focus", _C["surface"])],
              bordercolor=[("focus", _C["accent"])])

    # --- Scrollbar ---
    style.configure("Vertical.TScrollbar",
                    background=_C["surface2"], troughcolor=_C["bg"],
                    borderwidth=0, arrowsize=14)
    style.configure("Horizontal.TScrollbar",
                    background=_C["surface2"], troughcolor=_C["bg"],
                    borderwidth=0, arrowsize=14)

    # --- Separator ---
    style.configure("TSeparator", background=_C["border"])

    # --- LabelFrame ---
    style.configure("TLabelframe", background=_C["surface"],
                    foreground=_C["accent"], borderwidth=1, relief="solid")
    style.configure("TLabelframe.Label", background=_C["surface"],
                    foreground=_C["accent"], font=("Segoe UI", 10, "bold"))

    return style


# ---------------------------------------------------------------------------
# Splash screen
# ---------------------------------------------------------------------------

class _SplashScreen:
    """Brief branded splash shown while the main window loads."""

    def __init__(self, root: tk.Tk) -> None:
        self._root = root
        self._splash = tk.Toplevel(root)
        self._splash.overrideredirect(True)
        self._images = []  # prevent GC

        w, h = 440, 420
        sw = root.winfo_screenwidth()
        sh = root.winfo_screenheight()
        x = (sw - w) // 2
        y = (sh - h) // 2
        self._splash.geometry(f"{w}x{h}+{x}+{y}")
        self._splash.configure(bg=_C["surface"])

        frame = ttk.Frame(self._splash, style="Splash.TFrame", padding=30)
        frame.pack(fill="both", expand=True)

        # Logo image
        from .logo import logo_medium
        logo_path = logo_medium()
        if logo_path:
            try:
                logo_img = tk.PhotoImage(file=logo_path)
                # Scale down to ~120px height
                scale = max(1, logo_img.height() // 120)
                logo_img = logo_img.subsample(scale, scale)
                self._images.append(logo_img)
                tk.Label(frame, image=logo_img, bg=_C["surface"]).pack(pady=(0, 8))
            except Exception:
                pass

        # Brand text
        ttk.Label(frame, text="LYNX", style="Splash.TLabel",
                  font=("Segoe UI", 36, "bold"),
                  foreground=_C["accent"]).pack(pady=(0, 0))
        ttk.Label(frame, text="PORTFOLIO", style="Splash.TLabel",
                  font=("Segoe UI", 14),
                  foreground=_C["fg_dim"]).pack()

        ttk.Separator(frame, orient="horizontal").pack(fill="x", pady=15)

        ttk.Label(frame, text=f"Investment Portfolio Manager  {VERSION}",
                  style="Splash.TLabel",
                  font=("Segoe UI", 10),
                  foreground=_C["fg_dim"]).pack()

        ttk.Label(frame, text=LICENSE,
                  style="Splash.TLabel",
                  font=("Segoe UI", 8),
                  foreground=_C["fg_dim"]).pack(pady=(4, 0))

        self._status = ttk.Label(frame, text="Loading...", style="Splash.TLabel",
                                 font=("Segoe UI", 9),
                                 foreground=_C["accent"])
        self._status.pack(pady=(12, 0))

        # Progress bar (canvas-based, hidden until needed)
        self._bar_canvas = tk.Canvas(
            frame, width=300, height=6,
            bg=_C["surface"], highlightthickness=0,
        )
        self._bar_canvas.pack(pady=(10, 0))
        # Track background
        self._bar_canvas.create_rectangle(
            0, 0, 300, 6, fill=_C["border"], outline="",
        )
        # Filled portion
        self._bar_fill = self._bar_canvas.create_rectangle(
            0, 0, 0, 6, fill=_C["accent"], outline="",
        )
        self._bar_canvas.pack_forget()  # hidden by default

        # Ticker detail line
        self._detail = ttk.Label(frame, text="", style="Splash.TLabel",
                                 font=("Consolas", 9),
                                 foreground=_C["fg_dim"])
        self._detail.pack(pady=(6, 0))
        self._detail.pack_forget()  # hidden by default

        self._splash.update()

    def set_status(self, text: str) -> None:
        self._status.configure(text=text)
        self._splash.update()

    def show_progress(self) -> None:
        """Make the progress bar and detail label visible."""
        self._bar_canvas.pack(pady=(10, 0))
        self._detail.pack(pady=(6, 0))
        self._splash.update()

    def set_progress(self, fraction: float, ticker: str,
                     state: str = "refreshing") -> None:
        """Update the progress bar and ticker detail during refresh."""
        # Update bar fill
        fill_w = int(300 * min(fraction, 1.0))
        self._bar_canvas.coords(self._bar_fill, 0, 0, fill_w, 6)
        # Update detail text
        if state == "refreshing":
            icon, color = "⟳", _C["accent"]
            label = f"Refreshing  [{ticker}] …"
        elif state == "done":
            icon, color = "✓", _C["green"]
            label = f"Refreshed   [{ticker}]"
        else:
            icon, color = "✗", _C["red"]
            label = f"Failed      [{ticker}]"
        self._detail.configure(text=f" {icon}  {label}", foreground=color)
        self._splash.update()

    def close(self) -> None:
        self._splash.destroy()


# ---------------------------------------------------------------------------
# Toolbar separator (vertical line)
# ---------------------------------------------------------------------------

def _toolbar_sep(parent: ttk.Frame) -> None:
    sep = ttk.Frame(parent, width=2, style="TFrame")
    sep.pack(side="left", fill="y", padx=8, pady=4)
    # Draw a thin vertical line using a canvas for precise control
    c = tk.Canvas(sep, width=1, height=24, bg=_C["border"],
                  highlightthickness=0)
    c.pack()


# ---------------------------------------------------------------------------
# Main application window
# ---------------------------------------------------------------------------

class LynxGUI:
    """Main Lynx Portfolio graphical interface."""

    _COLUMNS = [
        ("ticker",   "Ticker",     100, "w"),
        ("isin",     "ISIN",       130, "w"),
        ("name",     "Name",       220, "w"),
        ("exchange", "Exchange",   160, "w"),
        ("shares",   "Shares",     90,  "e"),
        ("avg",      "Avg Price",  100, "e"),
        ("curr",     "Curr Price", 100, "e"),
        ("ccy",      "CCY",        55,  "center"),
        ("mkt",      "Mkt Value",  120, "e"),
    ]

    _EUR_COLUMNS = [
        ("eur_val", "EUR Val",  120, "e"),
        ("eur_pnl", "EUR P&L",  170, "e"),
    ]

    _PNL_COLUMN = [
        ("pnl", "P&L", 170, "e"),
    ]

    def __init__(self, needs_refresh: bool = False,
                 verbose: bool = False) -> None:
        self._root = tk.Tk()
        self._root.withdraw()  # hide while building
        self._root.title(f"{APP_NAME} {VERSION}")
        self._root.geometry("1340x720")
        self._root.minsize(960, 440)
        self._root.configure(bg=_C["bg"])

        _apply_dark_theme(self._root)

        # Splash
        splash = _SplashScreen(self._root)
        splash_start = time.monotonic()

        # Install notifier
        set_notifier(_GUINotifier(self._root, self._set_status))

        splash.set_status("Reading portfolio...")
        instruments = database.get_all_instruments()

        # Refresh inside splash if needed (first run today)
        if instruments and needs_refresh:
            from .operations import refresh_instrument_quiet
            splash.set_status("Refreshing portfolio data...")
            splash.show_progress()
            total = len(instruments)
            for idx, inst in enumerate(instruments):
                ticker = inst["ticker"]
                splash.set_progress(idx / total, ticker, "refreshing")
                ok = refresh_instrument_quiet(ticker)
                splash.set_progress(
                    (idx + 1) / total, ticker,
                    "done" if ok else "fail",
                )
            splash.set_status("Refresh complete")
            # Re-read instruments after refresh
            instruments = database.get_all_instruments()

        self._show_eur = any(
            (inst.get("currency") or "EUR").upper() != "EUR"
            for inst in instruments
        )

        splash.set_status("Building interface...")
        self._build_ui()
        self._reload_table()

        # Ensure splash is visible for at least 2 seconds
        elapsed = time.monotonic() - splash_start
        remaining = 2.0 - elapsed
        if remaining > 0:
            splash.set_status("Ready")
            time.sleep(remaining)

        # Show main window, close splash
        splash.close()
        self._root.deiconify()

        # Keyboard shortcuts
        self._root.bind("<F5>", lambda _: self._on_refresh_all())
        self._root.bind("<Delete>", lambda _: self._on_delete())
        self._root.bind("<F12>", lambda _: self._xyzzy())

        # Suite-wide theme cycling (Ctrl+T / Ctrl+Shift+T)
        self._theme_cycler = ThemeCycler(self._root)
        self._theme_cycler.apply_current()
        self._root.bind_all("<Control-t>", lambda _: self._theme_cycler.next())
        self._root.bind_all("<Control-T>", lambda _: self._theme_cycler.previous())

    # ----- UI construction ---------------------------------------------------

    def _build_ui(self) -> None:
        root = self._root

        # ── Toolbar ──────────────────────────────────────────────────────
        toolbar = ttk.Frame(root, style="Toolbar.TFrame", padding=(8, 6))
        toolbar.pack(side="top", fill="x")

        # Toolbar logo
        from .logo import logo_quarter
        logo_path = logo_quarter()
        if logo_path:
            try:
                self._toolbar_logo = tk.PhotoImage(file=logo_path)
                tk.Label(toolbar, image=self._toolbar_logo,
                         bg=_C["surface2"]).pack(side="left", padx=(4, 6))
            except Exception:
                pass

        ttk.Label(toolbar, text="LYNX",
                  font=("Segoe UI", 15, "bold"),
                  foreground=_C["accent"],
                  background=_C["surface2"]).pack(side="left", padx=(0, 2))
        ttk.Label(toolbar, text="PORTFOLIO",
                  font=("Segoe UI", 10),
                  foreground=_C["fg_dim"],
                  background=_C["surface2"]).pack(side="left", padx=(0, 16))

        # ── Group 1: Portfolio management ────────────────────────────────
        ttk.Button(toolbar, text="\u2795 Add", command=self._on_add,
                   style="Accent.TButton").pack(side="left", padx=2)
        ttk.Button(toolbar, text="\u270e Edit", command=self._on_edit).pack(
            side="left", padx=2)
        ttk.Button(toolbar, text="\u2716 Delete", command=self._on_delete,
                   style="Danger.TButton").pack(side="left", padx=2)
        ttk.Button(toolbar, text="\U0001f50d Detail", command=self._on_detail).pack(
            side="left", padx=2)

        _toolbar_sep(toolbar)

        # ── Group 2: Data refresh ───────────────────────────────────────
        ttk.Button(toolbar, text="\u21bb Refresh",
                   command=self._on_refresh_one).pack(side="left", padx=2)
        ttk.Button(toolbar, text="\u21bb All",
                   command=self._on_refresh_all).pack(side="left", padx=2)
        self._auto_update_btn = ttk.Button(
            toolbar, text="\u23f0 Auto: OFF",
            command=self._on_toggle_auto_update)
        self._auto_update_btn.pack(side="left", padx=2)
        self._auto_update_id = None
        self._AUTO_UPDATE_INTERVAL = 60_000  # ms

        _toolbar_sep(toolbar)

        # ── Group 3: Import & cache ─────────────────────────────────────
        ttk.Button(toolbar, text="\U0001f4c2 Import",
                   command=self._on_import).pack(side="left", padx=2)
        ttk.Button(toolbar, text="\U0001f5d1 Clear Cache",
                   command=self._on_clear_cache,
                   style="Danger.TButton").pack(side="left", padx=2)

        # ── Right side: About, version, Quit ────────────────────────────
        ttk.Button(toolbar, text="Quit", command=self._root.destroy,
                   style="Danger.TButton").pack(side="right", padx=2)
        ttk.Label(toolbar, text=VERSION,
                  font=("Consolas", 9),
                  foreground=_C["fg_dim"],
                  background=_C["surface2"]).pack(side="right", padx=8)
        ttk.Button(toolbar, text="\u2139 About",
                   command=self._on_about).pack(side="right", padx=2)

        # ── Thin accent line under toolbar ───────────────────────────────
        tk.Frame(root, height=2, bg=_C["accent_dark"]).pack(side="top", fill="x")

        # ── Portfolio table ──────────────────────────────────────────────
        cols = self._COLUMNS + (self._EUR_COLUMNS if self._show_eur else self._PNL_COLUMN)
        col_ids = [c[0] for c in cols]

        table_frame = ttk.Frame(root)
        table_frame.pack(fill="both", expand=True, padx=8, pady=(6, 0))

        self._tree = ttk.Treeview(
            table_frame, columns=col_ids, show="headings", selectmode="browse",
        )
        # Tag-based row colouring
        self._tree.tag_configure("even", background=_C["bg"])
        self._tree.tag_configure("odd",  background=_C["bg_alt"])
        self._tree.tag_configure("profit", foreground=_C["green"])
        self._tree.tag_configure("loss",   foreground=_C["red"])

        for cid, heading, width, anchor in cols:
            self._tree.heading(cid, text=heading)
            self._tree.column(cid, width=width, anchor=anchor, minwidth=50)

        vsb = ttk.Scrollbar(table_frame, orient="vertical", command=self._tree.yview)
        hsb = ttk.Scrollbar(table_frame, orient="horizontal", command=self._tree.xview)
        self._tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        self._tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        table_frame.rowconfigure(0, weight=1)
        table_frame.columnconfigure(0, weight=1)

        self._tree.bind("<Double-1>", self._on_double_click)

        # ── Summary bar ──────────────────────────────────────────────────
        summary_frame = tk.Frame(root, bg=_C["surface2"], height=34)
        summary_frame.pack(side="bottom", fill="x")
        summary_frame.pack_propagate(False)
        self._summary_var = tk.StringVar(value="")
        tk.Label(summary_frame, textvariable=self._summary_var,
                 bg=_C["surface2"], fg=_C["fg"], font=("Segoe UI", 10),
                 anchor="w", padx=12).pack(fill="both", expand=True)

        # ── Status bar ───────────────────────────────────────────────────
        status_frame = tk.Frame(root, bg=_C["bg"], height=26)
        status_frame.pack(side="bottom", fill="x")
        status_frame.pack_propagate(False)
        self._status_label = tk.Label(status_frame, text="Ready",
                                      bg=_C["bg"], fg=_C["fg_dim"],
                                      font=("Consolas", 9), anchor="w", padx=12)
        self._status_label.pack(fill="both", expand=True)

    # ----- Data loading ------------------------------------------------------

    def _reload_table(self) -> None:
        tree = self._tree
        tree.delete(*tree.get_children())

        instruments = database.get_all_instruments()
        if not instruments:
            self._summary_var.set(
                "Portfolio is empty  \u2014  click Add to get started"
            )
            return

        show_eur = any(
            (inst.get("currency") or "EUR").upper() != "EUR"
            for inst in instruments
        )
        if show_eur != self._show_eur:
            self._show_eur = show_eur
            self._rebuild_columns()

        total_invested = 0.0
        total_market = 0.0
        total_invested_eur = 0.0
        total_market_eur = 0.0
        total_today_eur = 0.0
        has_today_data = False
        untracked = 0

        for idx, inst in enumerate(instruments):
            shares    = inst.get("shares") or 0.0
            avg_price = inst.get("avg_purchase_price")
            curr      = inst.get("current_price")
            ccy       = (inst.get("currency") or "EUR").upper()
            has_cost  = avg_price is not None
            qt        = inst.get("quote_type")

            shares_s = _shares_str(shares, qt)
            avg_s    = f"{avg_price:,.2f}" if has_cost else "\u2014"
            curr_s   = f"{curr:,.2f}" if curr is not None else "N/A"

            row_pnl = None  # track for row colouring

            if has_cost:
                invested = shares * avg_price
                total_invested += invested
                inv_eur = forex.to_eur(invested, ccy)
                if inv_eur is not None:
                    total_invested_eur += inv_eur
            else:
                untracked += 1

            rmc = inst.get("regular_market_change")
            if rmc is not None:
                day_change_eur = forex.to_eur(rmc * shares, ccy)
                if day_change_eur is not None:
                    total_today_eur += day_change_eur
                    has_today_data = True

            if curr is not None:
                mkt_val = shares * curr
                mkt_s   = f"{mkt_val:,.2f}"
                total_market += mkt_val

                if has_cost:
                    pnl = mkt_val - invested
                    pct = (pnl / invested * 100) if invested else 0.0
                    pnl_s = _pnl_text(pnl, pct)
                    row_pnl = pnl
                else:
                    pnl = None
                    pct = None
                    pnl_s = "\u2014"

                if self._show_eur:
                    mkt_eur = forex.to_eur(mkt_val, ccy)
                    eur_mkt_s = f"{mkt_eur:,.2f}" if mkt_eur is not None else "N/A"
                    if mkt_eur is not None:
                        total_market_eur += mkt_eur
                    if pnl is not None:
                        pnl_eur = forex.to_eur(pnl, ccy)
                        eur_pnl_s = _pnl_text(pnl_eur, pct) if pnl_eur is not None else "N/A"
                    else:
                        eur_pnl_s = "\u2014"
            else:
                mkt_s = "N/A"
                pnl_s = "N/A"
                if self._show_eur:
                    eur_mkt_s = "N/A"
                    eur_pnl_s = "N/A"

            exch = inst.get("exchange_display") or inst.get("exchange_code") or "\u2014"

            values = [
                inst.get("ticker") or "",
                inst.get("isin") or "\u2014",
                (inst.get("name") or "\u2014")[:42],
                exch[:28],
                shares_s,
                avg_s,
                curr_s,
                inst.get("currency") or "\u2014",
                mkt_s,
            ]
            if self._show_eur:
                values += [eur_mkt_s, eur_pnl_s]
            else:
                values.append(pnl_s)

            tags = ("even",) if idx % 2 == 0 else ("odd",)
            tree.insert("", "end", iid=inst.get("ticker"),
                        values=values, tags=tags)

        # Summary text
        total_pnl = total_market - total_invested
        total_pct = (total_pnl / total_invested * 100) if total_invested else 0.0
        sign      = "+" if total_pnl >= 0 else ""

        today_sign = "+" if total_today_eur >= 0 else ""
        today_str  = (
            f"{today_sign}{total_today_eur:,.2f}"
            if has_today_data else "N/A"
        )

        if self._show_eur:
            ep = total_market_eur - total_invested_eur
            epc = (ep / total_invested_eur * 100) if total_invested_eur else 0.0
            es = "+" if ep >= 0 else ""
            summary = (
                f"EUR Invested: {total_invested_eur:,.2f}     "
                f"EUR Market Value: {total_market_eur:,.2f}     "
                f"EUR P&L: {es}{ep:,.2f} ({es}{epc:.2f}%)     "
                f"EUR Market Today: {today_str}"
            )
        else:
            summary = (
                f"Invested: {total_invested:,.2f}     "
                f"Market Value: {total_market:,.2f}     "
                f"P&L: {sign}{total_pnl:,.2f} ({sign}{total_pct:.2f}%)     "
                f"EUR Market Today: {today_str}"
            )

        if untracked:
            summary += f"     [{untracked} without cost basis]"

        self._summary_var.set(summary)

    def _rebuild_columns(self) -> None:
        cols = self._COLUMNS + (self._EUR_COLUMNS if self._show_eur else self._PNL_COLUMN)
        col_ids = [c[0] for c in cols]
        self._tree.configure(columns=col_ids)
        for cid, heading, width, anchor in cols:
            self._tree.heading(cid, text=heading)
            self._tree.column(cid, width=width, anchor=anchor, minwidth=50)

    # ----- Status bar --------------------------------------------------------

    def _set_status(self, msg: str, level: str = "info") -> None:
        colours = {
            "ok":      _C["green"],
            "error":   _C["red"],
            "warning": _C["yellow"],
            "info":    _C["cyan"],
        }
        prefix = {"ok": "\u2713", "error": "\u2717",
                  "warning": "\u26a0", "info": "\u2139"}.get(level, "")
        self._status_label.configure(
            text=f" {prefix}  {msg}",
            fg=colours.get(level, _C["fg_dim"]),
        )

    # ----- Selection helper --------------------------------------------------

    def _get_selected_ticker(self) -> Optional[str]:
        sel = self._tree.selection()
        if not sel:
            messagebox.showinfo("No Selection",
                                "Select an instrument in the table first.",
                                parent=self._root)
            return None
        return sel[0]

    # ----- Thread helper -----------------------------------------------------

    def _run_in_thread(self, target, *args, on_done=None) -> None:
        def wrapper():
            try:
                target(*args)
            except Exception as exc:
                self._root.after(0, lambda: self._set_status(str(exc), "error"))
            finally:
                if on_done:
                    self._root.after(0, on_done)
        threading.Thread(target=wrapper, daemon=True).start()

    def _on_double_click(self, event) -> None:
        item = self._tree.identify_row(event.y)
        if item:
            DetailDialog(self._root, item)

    # ----- Actions -----------------------------------------------------------

    def _on_add(self) -> None:
        AddDialog(self._root, self._reload_table)

    def _on_edit(self) -> None:
        ticker = self._get_selected_ticker()
        if ticker:
            EditDialog(self._root, ticker, self._reload_table)

    def _on_delete(self) -> None:
        ticker = self._get_selected_ticker()
        if not ticker:
            return
        if messagebox.askyesno("Confirm Delete",
                               f"Remove {ticker} from portfolio?",
                               parent=self._root):
            if database.delete_instrument(ticker):
                self._set_status(f"Deleted {ticker}", "ok")
                self._reload_table()
            else:
                self._set_status(f"'{ticker}' not found.", "error")

    def _on_refresh_one(self) -> None:
        ticker = self._get_selected_ticker()
        if not ticker:
            return
        self._set_status(f"Refreshing {ticker}...", "info")
        self._run_in_thread(ops_refresh_instrument, ticker,
                            on_done=self._reload_table)

    def _on_refresh_all(self) -> None:
        self._set_status("Refreshing all instruments...", "info")
        self._run_in_thread(ops_refresh_all, on_done=self._reload_table)

    def _xyzzy(self) -> None:
        from .egg import run_gui_egg
        run_gui_egg(self._root)

    def _on_import(self) -> None:
        ImportDialog(self._root, self._reload_table)

    def _on_detail(self) -> None:
        ticker = self._get_selected_ticker()
        if ticker:
            DetailDialog(self._root, ticker)

    def _on_clear_cache(self) -> None:
        instruments = database.get_all_instruments()
        if not instruments:
            n = cache.delete()
            self._set_status(f"Cache cleared ({n} entries removed).", "ok")
            return

        listing = "\n".join(
            f"  \u2022  {inst.get('ticker', '?'):14s}  {inst.get('name') or '\u2014'}"
            for inst in instruments
        )
        if messagebox.askyesno(
            "Clear Cache",
            f"This will wipe cached data for:\n\n{listing}\n\n"
            "Prices and market data will need to be re-fetched.\n\nContinue?",
            icon="warning", parent=self._root,
        ):
            n = cache.delete()
            self._set_status(f"Cache cleared ({n} entries removed).", "ok")

    # ----- About -------------------------------------------------------------

    def _on_about(self) -> None:
        _AboutDialog(self._root)

    # ----- Auto-update -------------------------------------------------------

    def _on_toggle_auto_update(self) -> None:
        if self._auto_update_id is not None:
            self._root.after_cancel(self._auto_update_id)
            self._auto_update_id = None
            self._auto_update_btn.configure(text="\u23f0 Auto: OFF")
            self._set_status("Auto-update OFF", "info")
        else:
            self._auto_update_btn.configure(text="\u23f0 Auto: ON")
            self._set_status(
                f"Auto-update ON (every {self._AUTO_UPDATE_INTERVAL // 1000}s)",
                "info",
            )
            self._schedule_auto_update()

    def _schedule_auto_update(self) -> None:
        self._auto_update_id = self._root.after(
            self._AUTO_UPDATE_INTERVAL, self._do_auto_update,
        )

    def _do_auto_update(self) -> None:
        def _refresh():
            ops_refresh_all()
        def _done():
            self._reload_table()
            if self._auto_update_id is not None:
                self._schedule_auto_update()
        self._run_in_thread(_refresh, on_done=_done)

    # ----- Run ---------------------------------------------------------------

    def run(self) -> None:
        self._root.mainloop()


# ---------------------------------------------------------------------------
# Base dialog mixin  (dark styling + Escape to close)
# ---------------------------------------------------------------------------

class _BaseDialog:
    """Common dialog setup: dark background, Escape binding, centring."""

    def _init_dialog(self, parent: tk.Tk, title: str,
                     width: int, height: int, *,
                     resizable: bool = False,
                     grab: bool = True) -> tk.Toplevel:
        dlg = tk.Toplevel(parent)
        dlg.title(title)
        dlg.configure(bg=_C["surface"])
        dlg.resizable(resizable, resizable)
        dlg.transient(parent)
        if grab:
            dlg.grab_set()

        # Centre on parent
        parent.update_idletasks()
        px = parent.winfo_x() + (parent.winfo_width() - width) // 2
        py = parent.winfo_y() + (parent.winfo_height() - height) // 2
        dlg.geometry(f"{width}x{height}+{max(px,0)}+{max(py,0)}")

        # Escape to close
        dlg.bind("<Escape>", lambda _: dlg.destroy())

        return dlg


# ---------------------------------------------------------------------------
# Add instrument dialog
# ---------------------------------------------------------------------------

class AddDialog(_BaseDialog):

    def __init__(self, parent: tk.Tk, on_done) -> None:
        self._on_done = on_done
        self._destroyed = False
        self._search_results: list = []

        self._dlg = self._init_dialog(parent, "Add Instrument", 520, 520)
        self._dlg.protocol("WM_DELETE_WINDOW", self._on_close)

        outer = ttk.Frame(self._dlg, style="Card.TFrame", padding=20)
        outer.pack(fill="both", expand=True)

        ttk.Label(outer, text="Add New Instrument",
                  style="DialogTitle.TLabel").grid(
            row=0, column=0, columnspan=3, sticky="w", pady=(0, 12))

        # Name search row
        ttk.Label(outer, text="Search by name", style="FieldLabel.TLabel").grid(
            row=1, column=0, sticky="w", pady=(6, 0))
        search_frame = ttk.Frame(outer, style="Card.TFrame")
        search_frame.grid(row=1, column=1, columnspan=2, sticky="ew",
                          padx=(10, 0), pady=(6, 0))
        self._search_entry = ttk.Entry(search_frame, width=24)
        self._search_entry.pack(side="left", fill="x", expand=True)
        self._search_btn = ttk.Button(
            search_frame, text="Search", width=8,
            command=self._do_search, style="Accent.TButton",
        )
        self._search_btn.pack(side="left", padx=(6, 0))

        # Search results combo
        self._results_var = tk.StringVar(value="")
        self._results_combo = ttk.Combobox(
            outer, textvariable=self._results_var, state="readonly", width=50,
        )
        self._results_combo.grid(row=2, column=0, columnspan=3, sticky="ew",
                                 pady=(4, 8))
        self._results_combo.bind("<<ComboboxSelected>>", self._on_result_selected)
        self._results_combo.grid_remove()  # hidden until search

        fields = [
            ("Ticker",             "ticker",   "e.g. AAPL, NESN.SW, VWCE.DE"),
            ("ISIN",               "isin",     "e.g. CH0038863350 (optional)"),
            ("Exchange suffix",    "exchange",  "e.g. SW, DE, AS (optional)"),
            ("Shares",             "shares",   "Number of shares"),
            ("Avg purchase price", "avg_price", "Leave empty to skip cost tracking"),
        ]

        self._entries: Dict[str, ttk.Entry] = {}
        for i, (label, key, hint) in enumerate(fields, start=3):
            ttk.Label(outer, text=label, style="FieldLabel.TLabel").grid(
                row=i, column=0, sticky="w", pady=(6, 0))
            entry = ttk.Entry(outer, width=34)
            entry.grid(row=i, column=1, columnspan=2, sticky="ew",
                       padx=(10, 0), pady=(6, 0))
            self._entries[key] = entry

        outer.columnconfigure(1, weight=1)

        row_status = 3 + len(fields)
        self._status_var = tk.StringVar(value="")
        ttk.Label(outer, textvariable=self._status_var,
                  style="Error.TLabel").grid(
            row=row_status, column=0, columnspan=3, sticky="w", pady=(10, 0))

        btn_frame = ttk.Frame(outer, style="Card.TFrame")
        btn_frame.grid(row=row_status + 1, column=0, columnspan=3,
                       sticky="e", pady=(14, 0))
        ttk.Button(btn_frame, text="Cancel", command=self._on_close,
                   width=10).pack(side="right", padx=(6, 0))
        self._add_btn = ttk.Button(btn_frame, text="Add Instrument",
                                   command=self._do_add,
                                   style="Accent.TButton", width=14)
        self._add_btn.pack(side="right")

        self._search_entry.focus_set()
        self._dlg.bind("<Return>", lambda _: self._do_add())

    def _do_search(self) -> None:
        from .validation import sanitise_search_query
        raw = self._search_entry.get().strip()
        if not raw:
            self._status_var.set("Enter a name to search.")
            return
        query, err = sanitise_search_query(raw)
        if err:
            self._status_var.set(err)
            return
        self._status_var.set(f"Searching for '{query}'...")
        self._search_btn.configure(state="disabled")

        def _search():
            from . import fetcher
            try:
                results = fetcher.search_by_name(query)
            except Exception:
                results = []
            if self._destroyed:
                return
            self._dlg.after(0, lambda: self._show_search_results(results))

        threading.Thread(target=_search, daemon=True).start()

    def _show_search_results(self, results: list) -> None:
        self._search_btn.configure(state="normal")
        self._search_results = results
        if not results:
            self._status_var.set("No instruments found.")
            self._results_combo.grid_remove()
            return
        self._status_var.set(f"Found {len(results)} result(s). Select one:")
        values = []
        for r in results:
            name = r.get("longname") or r.get("shortname", "")
            values.append(
                f"{r['symbol']}  —  {name}  ({r['exchange_display']}, {r['quote_type']})"
            )
        self._results_combo["values"] = values
        self._results_combo.current(0)
        self._results_combo.grid()
        self._on_result_selected(None)

    def _on_result_selected(self, _event) -> None:
        idx = self._results_combo.current()
        if 0 <= idx < len(self._search_results):
            chosen = self._search_results[idx]
            self._entries["ticker"].delete(0, "end")
            self._entries["ticker"].insert(0, chosen["symbol"])
            self._status_var.set(f"Selected: {chosen['symbol']}")

    def _on_close(self) -> None:
        self._destroyed = True
        self._dlg.destroy()

    def _do_add(self) -> None:
        from .validation import (
            validate_ticker, validate_isin, validate_shares, validate_price,
            validate_exchange,
        )
        ticker   = self._entries["ticker"].get().strip()
        isin     = self._entries["isin"].get().strip()
        exchange = self._entries["exchange"].get().strip()
        shares_s = self._entries["shares"].get().strip()
        price_s  = self._entries["avg_price"].get().strip()

        if not ticker and not isin:
            self._status_var.set("Provide at least a ticker or ISIN.")
            return

        if ticker:
            ticker, err = validate_ticker(ticker)
            if err:
                self._status_var.set(err)
                return

        if isin:
            isin, err = validate_isin(isin)
            if err:
                self._status_var.set(err)
                return

        if exchange:
            exchange, err = validate_exchange(exchange)
            if err:
                self._status_var.set(err)
                return

        shares, err = validate_shares(shares_s)
        if err:
            self._status_var.set(err)
            return

        avg_price, err = validate_price(price_s)
        if err:
            self._status_var.set(err)
            return

        self._status_var.set("Adding instrument...")
        self._add_btn.configure(state="disabled")

        def _add():
            ok = ops_add_instrument(
                ticker=ticker or None, isin=isin or None,
                shares=shares, avg_purchase_price=avg_price,
                preferred_exchange=exchange or None,
            )
            if not self._destroyed:
                self._dlg.after(0, lambda: self._finish(ok))

        threading.Thread(target=_add, daemon=True).start()

    def _finish(self, ok: bool) -> None:
        if self._destroyed:
            return
        if ok:
            self._destroyed = True
            self._dlg.destroy()
            self._on_done()
        else:
            self._add_btn.configure(state="normal")
            self._status_var.set("Failed to add. Check ticker/ISIN and try again.")


# ---------------------------------------------------------------------------
# Edit instrument dialog
# ---------------------------------------------------------------------------

class EditDialog(_BaseDialog):

    def __init__(self, parent: tk.Tk, ticker: str, on_done) -> None:
        self._ticker = ticker
        self._on_done = on_done

        inst = database.get_instrument(ticker) or {}
        cur_shares = inst.get("shares", 0.0)
        cur_price  = inst.get("avg_purchase_price")

        self._dlg = self._init_dialog(parent, f"Edit {ticker}", 440, 280)

        outer = ttk.Frame(self._dlg, style="Card.TFrame", padding=20)
        outer.pack(fill="both", expand=True)

        ttk.Label(outer, text=f"Update {ticker}",
                  style="DialogTitle.TLabel").grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 4))

        price_disp = f"{cur_price:,.2f}" if cur_price is not None else "Not tracked"
        ttk.Label(outer,
                  text=f"Current: {cur_shares} shares  |  avg price: {price_disp}",
                  style="Subtitle.TLabel").grid(
            row=1, column=0, columnspan=2, sticky="w", pady=(0, 14))

        ttk.Label(outer, text="New shares", style="FieldLabel.TLabel").grid(
            row=2, column=0, sticky="w", pady=(4, 0))
        self._shares_entry = ttk.Entry(outer, width=20)
        self._shares_entry.grid(row=2, column=1, sticky="ew", padx=(10, 0), pady=(4, 0))

        ttk.Label(outer, text="New avg price", style="FieldLabel.TLabel").grid(
            row=3, column=0, sticky="w", pady=(4, 0))
        self._price_entry = ttk.Entry(outer, width=20)
        self._price_entry.grid(row=3, column=1, sticky="ew", padx=(10, 0), pady=(4, 0))

        outer.columnconfigure(1, weight=1)

        self._status_var = tk.StringVar(value="")
        ttk.Label(outer, textvariable=self._status_var,
                  style="Error.TLabel").grid(
            row=4, column=0, columnspan=2, sticky="w", pady=(8, 0))

        btn_frame = ttk.Frame(outer, style="Card.TFrame")
        btn_frame.grid(row=5, column=0, columnspan=2, sticky="e", pady=(14, 0))
        ttk.Button(btn_frame, text="Cancel",
                   command=self._dlg.destroy, width=10).pack(side="right", padx=(6, 0))
        ttk.Button(btn_frame, text="Update",
                   command=self._do_update,
                   style="Accent.TButton", width=10).pack(side="right")

        self._shares_entry.focus_set()
        self._dlg.bind("<Return>", lambda _: self._do_update())

    def _do_update(self) -> None:
        from .validation import validate_shares, validate_price
        shares_s = self._shares_entry.get().strip()
        price_s  = self._price_entry.get().strip()
        kwargs: dict = {}
        if shares_s:
            val, err = validate_shares(shares_s)
            if err:
                self._status_var.set(err)
                return
            kwargs["shares"] = val
        if price_s:
            val, err = validate_price(price_s)
            if err:
                self._status_var.set(err)
                return
            kwargs["avg_purchase_price"] = val

        if not kwargs:
            self._dlg.destroy()
            return

        if database.update_instrument(self._ticker, **kwargs):
            self._dlg.destroy()
            self._on_done()
        else:
            self._status_var.set(f"'{self._ticker}' not found.")


# ---------------------------------------------------------------------------
# Detail dialog  (scrollable, with prominent Close button)
# ---------------------------------------------------------------------------

class DetailDialog(_BaseDialog):

    def __init__(self, parent: tk.Tk, ticker: str) -> None:
        inst = database.get_instrument(ticker)
        if not inst:
            messagebox.showerror("Not Found",
                                 f"'{ticker}' not found in portfolio.",
                                 parent=parent)
            return

        self._dlg = self._init_dialog(parent, f"{ticker}  \u2014  Detail",
                                      580, 560, resizable=True, grab=False)

        # ── Header ───────────────────────────────────────────────────────
        header = tk.Frame(self._dlg, bg=_C["surface2"], height=52)
        header.pack(fill="x")
        header.pack_propagate(False)

        tk.Label(header, text=inst.get("ticker", ""),
                 bg=_C["surface2"], fg=_C["accent"],
                 font=("Segoe UI", 16, "bold"),
                 anchor="w").pack(side="left", padx=16, pady=8)

        name = inst.get("name") or ""
        if name:
            tk.Label(header, text=name,
                     bg=_C["surface2"], fg=_C["fg_dim"],
                     font=("Segoe UI", 11),
                     anchor="w").pack(side="left", padx=(0, 16), pady=8)

        # Close button in header
        close_btn = tk.Button(header, text="\u2715  Close", command=self._dlg.destroy,
                              bg=_C["btn_bg"], fg=_C["btn_fg"],
                              activebackground=_C["border"],
                              activeforeground=_C["fg_heading"],
                              font=("Segoe UI", 10), bd=0,
                              padx=14, pady=4, cursor="hand2")
        close_btn.pack(side="right", padx=16, pady=10)

        tk.Frame(self._dlg, height=2, bg=_C["accent_dark"]).pack(fill="x")

        # ── Scrollable body ──────────────────────────────────────────────
        canvas = tk.Canvas(self._dlg, bg=_C["surface"], highlightthickness=0)
        scrollbar = ttk.Scrollbar(self._dlg, orient="vertical",
                                  command=canvas.yview)
        body = ttk.Frame(canvas, style="Card.TFrame", padding=(20, 12))

        body.bind("<Configure>",
                  lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=body, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # Mouse wheel scrolling
        def _on_mousewheel(event):
            canvas.yview_scroll(-1 * (event.delta // 120 or
                                      (-1 if event.num == 4 else 1)), "units")
        canvas.bind_all("<MouseWheel>", _on_mousewheel)
        canvas.bind_all("<Button-4>", _on_mousewheel)
        canvas.bind_all("<Button-5>", _on_mousewheel)
        # PageUp / PageDown (Ctrl+Home/End) — shared across every suite app.
        from lynx_investor_core.pager import bind_tk_paging
        bind_tk_paging(self._dlg, canvas)

        # Unbind on destroy to avoid affecting other windows
        def _on_destroy(event):
            if event.widget == self._dlg:
                canvas.unbind_all("<MouseWheel>")
                canvas.unbind_all("<Button-4>")
                canvas.unbind_all("<Button-5>")
        self._dlg.bind("<Destroy>", _on_destroy)

        # ── Build detail rows ────────────────────────────────────────────
        shares    = inst.get("shares") or 0.0
        avg_price = inst.get("avg_purchase_price")
        curr      = inst.get("current_price")
        ccy       = (inst.get("currency") or "EUR").upper()
        has_cost  = avg_price is not None
        qt        = inst.get("quote_type")
        exch      = inst.get("exchange_display") or inst.get("exchange_code") or "\u2014"

        rows = [
            ("Ticker",             inst.get("ticker", "")),
            ("ISIN",               inst.get("isin") or "\u2014"),
            ("Name",               inst.get("name") or "\u2014"),
            ("Exchange",           exch),
            ("Currency",           inst.get("currency") or "\u2014"),
            ("Sector",             inst.get("sector") or "\u2014"),
            ("Industry",           inst.get("industry") or "\u2014"),
            None,  # separator
            ("Shares",             _shares_str(shares, qt)),
            ("Avg Purchase Price", f"{avg_price:,.2f}" if has_cost else "Not tracked"),
            ("Current Price",      _price_str(curr)),
        ]

        if has_cost:
            invested = shares * avg_price
            rows.append(("Total Invested", f"{invested:,.2f}"))
            if ccy != "EUR":
                inv_eur = forex.to_eur(invested, ccy)
                if inv_eur is not None:
                    rows.append(("Total Invested (EUR)", f"{inv_eur:,.2f}"))
        else:
            rows.append(("Total Invested", "Not tracked"))

        if curr is not None:
            mkt_val = shares * curr
            rows.append(("Market Value", f"{mkt_val:,.2f}"))
            if ccy != "EUR":
                mkt_eur = forex.to_eur(mkt_val, ccy)
                if mkt_eur is not None:
                    rows.append(("Market Value (EUR)", f"{mkt_eur:,.2f}"))

            rows.append(None)  # separator before P&L

            if has_cost:
                pnl = mkt_val - invested
                pct = (pnl / invested * 100) if invested else 0.0
                rows.append(("P&L", (_pnl_text(pnl, pct), pnl)))
                if ccy != "EUR":
                    pnl_eur = forex.to_eur(pnl, ccy)
                    if pnl_eur is not None:
                        rows.append(("P&L (EUR)", (_pnl_text(pnl_eur, pct), pnl_eur)))
            else:
                rows.append(("P&L", "Not tracked"))

        if inst.get("description"):
            rows.append(None)
            rows.append(("Description", inst["description"]))

        rows.append(None)
        rows.append(("Added",   inst.get("created_at") or "\u2014"))
        rows.append(("Updated", inst.get("updated_at") or "\u2014"))

        grid_row = 0
        for item in rows:
            if item is None:
                # Separator line
                ttk.Separator(body, orient="horizontal").grid(
                    row=grid_row, column=0, columnspan=2,
                    sticky="ew", pady=8)
                grid_row += 1
                continue

            label, value = item

            ttk.Label(body, text=label, style="DetailLabel.TLabel",
                      width=22, anchor="w").grid(
                row=grid_row, column=0, sticky="nw", pady=3)

            # P&L values get colour coding
            if isinstance(value, tuple):
                text, pnl_val = value
                color = _C["green"] if pnl_val >= 0 else _C["red"]
                lbl = tk.Label(body, text=text, bg=_C["surface"],
                               fg=color, font=("Consolas", 11, "bold"),
                               anchor="w")
                lbl.grid(row=grid_row, column=1, sticky="w",
                         padx=(10, 0), pady=3)
            elif label == "Description":
                bg = _C["surface"]
                txt = tk.Text(body, wrap="word", height=4, width=38,
                              font=("Segoe UI", 10), relief="flat",
                              bg=bg, fg=_C["fg"], insertbackground=_C["fg"])
                txt.insert("1.0", value)
                txt.configure(state="disabled")
                txt.grid(row=grid_row, column=1, sticky="ew",
                         padx=(10, 0), pady=3)
            else:
                ttk.Label(body, text=value, style="DetailValue.TLabel",
                          wraplength=320).grid(
                    row=grid_row, column=1, sticky="w", padx=(10, 0), pady=3)

            grid_row += 1

        body.columnconfigure(1, weight=1)

        # ── Bottom close button ──────────────────────────────────────────
        bottom = tk.Frame(self._dlg, bg=_C["surface"], height=50)
        bottom.pack(fill="x", side="bottom")
        bottom.pack_propagate(False)
        tk.Frame(bottom, height=1, bg=_C["border"]).pack(fill="x")
        close_btn2 = ttk.Button(bottom, text="Close", command=self._dlg.destroy,
                                width=12)
        close_btn2.pack(pady=10)


# ---------------------------------------------------------------------------
# Import dialog
# ---------------------------------------------------------------------------

class ImportDialog(_BaseDialog):

    def __init__(self, parent: tk.Tk, on_done) -> None:
        self._on_done = on_done
        self._destroyed = False

        self._dlg = self._init_dialog(parent, "Import from JSON", 500, 250)
        self._dlg.protocol("WM_DELETE_WINDOW", self._on_close)

        outer = ttk.Frame(self._dlg, style="Card.TFrame", padding=20)
        outer.pack(fill="both", expand=True)

        ttk.Label(outer, text="Import from JSON",
                  style="DialogTitle.TLabel").grid(
            row=0, column=0, columnspan=3, sticky="w", pady=(0, 12))

        ttk.Label(outer, text="JSON file", style="FieldLabel.TLabel").grid(
            row=1, column=0, sticky="w", pady=4)
        self._file_entry = ttk.Entry(outer, width=30)
        self._file_entry.grid(row=1, column=1, sticky="ew", padx=(10, 6), pady=4)
        ttk.Button(outer, text="Browse...", command=self._browse,
                   width=9).grid(row=1, column=2, pady=4)

        ttk.Label(outer, text="Default exchange", style="FieldLabel.TLabel").grid(
            row=2, column=0, sticky="w", pady=4)
        self._exchange_entry = ttk.Entry(outer, width=10)
        self._exchange_entry.grid(row=2, column=1, sticky="w", padx=(10, 0), pady=4)

        outer.columnconfigure(1, weight=1)

        self._status_var = tk.StringVar(value="")
        ttk.Label(outer, textvariable=self._status_var,
                  style="Error.TLabel").grid(
            row=3, column=0, columnspan=3, sticky="w", pady=(8, 0))

        btn_frame = ttk.Frame(outer, style="Card.TFrame")
        btn_frame.grid(row=4, column=0, columnspan=3, sticky="e", pady=(14, 0))
        ttk.Button(btn_frame, text="Cancel", command=self._on_close,
                   width=10).pack(side="right", padx=(6, 0))
        self._import_btn = ttk.Button(btn_frame, text="Import",
                                      command=self._do_import,
                                      style="Accent.TButton", width=10)
        self._import_btn.pack(side="right")

        self._file_entry.focus_set()
        self._dlg.bind("<Return>", lambda _: self._do_import())

    def _on_close(self) -> None:
        self._destroyed = True
        self._dlg.destroy()

    def _browse(self) -> None:
        path = filedialog.askopenfilename(
            parent=self._dlg, title="Select JSON file",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")])
        if path:
            self._file_entry.delete(0, "end")
            self._file_entry.insert(0, path)

    def _do_import(self) -> None:
        filepath = self._file_entry.get().strip()
        exchange = self._exchange_entry.get().strip() or None

        if not filepath:
            self._status_var.set("Please select a file.")
            return

        try:
            with open(filepath, "r") as f:
                instruments = json.load(f)
        except FileNotFoundError:
            self._status_var.set(f"File not found: {filepath}")
            return
        except json.JSONDecodeError as exc:
            self._status_var.set(f"Invalid JSON: {exc}")
            return

        if not isinstance(instruments, list):
            self._status_var.set("JSON must be an array of objects.")
            return

        self._status_var.set(f"Importing {len(instruments)} instruments...")
        self._import_btn.configure(state="disabled")

        def _run():
            total = len(instruments)
            added = skipped = 0
            for entry in instruments:
                if not isinstance(entry, dict):
                    skipped += 1; continue
                ticker    = entry.get("ticker")
                shares    = entry.get("shares")
                avg_price = entry.get("avg_price")
                if not ticker or shares is None:
                    skipped += 1; continue
                try:
                    shares = float(shares)
                    if avg_price is not None:
                        avg_price = float(avg_price)
                except (TypeError, ValueError):
                    skipped += 1; continue
                ok = ops_add_instrument(
                    ticker=ticker, isin=entry.get("isin"),
                    shares=shares, avg_purchase_price=avg_price,
                    preferred_exchange=entry.get("exchange") or exchange)
                if ok: added += 1
                else:  skipped += 1

            msg = f"Import complete: {added} added, {skipped} skipped (of {total})"
            if not self._destroyed:
                self._dlg.after(0, lambda: self._finish(msg))

        threading.Thread(target=_run, daemon=True).start()

    def _finish(self, msg: str) -> None:
        if self._destroyed:
            return
        messagebox.showinfo("Import Result", msg, parent=self._dlg)
        self._destroyed = True
        self._dlg.destroy()
        self._on_done()


# ---------------------------------------------------------------------------
# About dialog  (proper custom dialog with license)
# ---------------------------------------------------------------------------

class _AboutDialog(_BaseDialog):
    """Application About dialog with license text."""

    def __init__(self, parent: tk.Tk) -> None:
        self._images = []  # prevent GC
        self._dlg = self._init_dialog(parent, f"About {APP_NAME}", 560, 580,
                                      resizable=True, grab=True)

        outer = ttk.Frame(self._dlg, style="Card.TFrame", padding=24)
        outer.pack(fill="both", expand=True)

        # ── Logo + Title header ──────────────────────────────────────────
        header = ttk.Frame(outer, style="Card.TFrame")
        header.pack(fill="x", pady=(0, 8))

        from .logo import logo_small
        logo_path = logo_small()
        if logo_path:
            try:
                logo_img = tk.PhotoImage(file=logo_path)
                # Scale to ~64px height
                scale = max(1, logo_img.height() // 64)
                logo_img = logo_img.subsample(scale, scale)
                self._images.append(logo_img)
                tk.Label(header, image=logo_img,
                         bg=_C["surface"]).pack(side="left", padx=(0, 16))
            except Exception:
                pass

        title_frame = ttk.Frame(header, style="Card.TFrame")
        title_frame.pack(side="left", fill="y")

        ttk.Label(title_frame, text=APP_NAME,
                  font=("Segoe UI", 18, "bold"),
                  foreground=_C["accent"],
                  background=_C["surface"]).pack(anchor="w")

        ttk.Label(title_frame, text=VERSION,
                  font=("Consolas", 11),
                  foreground=_C["fg_dim"],
                  background=_C["surface"]).pack(anchor="w", pady=(0, 4))

        ttk.Label(title_frame, text=f"Part of {SUITE_LABEL}",
                  font=("Segoe UI", 10),
                  foreground=_C["fg"],
                  background=_C["surface"]).pack(anchor="w")

        # ── Author ───────────────────────────────────────────────────────
        ttk.Separator(outer, orient="horizontal").pack(fill="x", pady=10)

        ttk.Label(outer,
                  text="Author:  Borja Tarraso <borja.tarraso@member.fsf.org>",
                  font=("Segoe UI", 10),
                  foreground=_C["fg"],
                  background=_C["surface"]).pack(anchor="w")

        # ── License ──────────────────────────────────────────────────────
        ttk.Separator(outer, orient="horizontal").pack(fill="x", pady=10)

        license_hdr = ttk.Frame(outer, style="Card.TFrame")
        license_hdr.pack(fill="x")
        ttk.Label(license_hdr, text=f"License:  {LICENSE}",
                  font=("Segoe UI", 10, "bold"),
                  foreground=_C["accent"],
                  background=_C["surface"]).pack(side="left")

        link_label = tk.Label(license_hdr, text=LICENSE_URL,
                              fg=_C["accent"], bg=_C["surface"],
                              font=("Segoe UI", 9, "underline"),
                              cursor="hand2")
        link_label.pack(side="left", padx=(12, 0))
        link_label.bind("<Button-1>", lambda _: self._open_url(LICENSE_URL))

        # License text box
        license_frame = ttk.Frame(outer, style="Card.TFrame")
        license_frame.pack(fill="both", expand=True, pady=(8, 0))

        license_text = tk.Text(license_frame, wrap="word", height=12,
                               font=("Consolas", 9), relief="flat",
                               bg=_C["entry_bg"], fg=_C["fg"],
                               insertbackground=_C["fg"],
                               padx=10, pady=8)
        license_sb = ttk.Scrollbar(license_frame, orient="vertical",
                                   command=license_text.yview)
        license_text.configure(yscrollcommand=license_sb.set)

        license_text.pack(side="left", fill="both", expand=True)
        license_sb.pack(side="right", fill="y")

        license_text.insert("1.0", LICENSE_TEXT)
        license_text.configure(state="disabled")

        # ── Close button ─────────────────────────────────────────────────
        btn_frame = ttk.Frame(outer, style="Card.TFrame")
        btn_frame.pack(fill="x", pady=(12, 0))
        ttk.Button(btn_frame, text="Close", command=self._dlg.destroy,
                   style="Accent.TButton", width=12).pack(side="right")

    @staticmethod
    def _open_url(url: str) -> None:
        try:
            import webbrowser
            webbrowser.open(url)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Graphical setup wizard
# ---------------------------------------------------------------------------

_DEFAULT_DB_DIR = os.path.expanduser("~/.local/share/lynx")


def run_wizard_gui() -> dict:
    """Run the first-time setup wizard using tkinter dialogs.

    Returns the final config dict (already saved), or {} if cancelled.
    """
    import os
    from . import config, database
    from .config import VALID_MODES

    cfg = config.load_config()

    root = tk.Tk()
    root.withdraw()
    _apply_dark_theme(root)

    result = {"cancelled": False}

    # ── Step 1: Database location ────────────────────────────────────────
    def _step1():
        dlg = tk.Toplevel(root)
        dlg.title(f"{APP_NAME} — Setup Wizard (1/4)")
        dlg.configure(bg=_C["surface"])
        dlg.resizable(False, False)
        w, h = 520, 300
        sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
        dlg.geometry(f"{w}x{h}+{(sw-w)//2}+{(sh-h)//2}")
        dlg.protocol("WM_DELETE_WINDOW", lambda: _cancel(dlg))

        outer = ttk.Frame(dlg, style="Card.TFrame", padding=24)
        outer.pack(fill="both", expand=True)

        ttk.Label(outer, text="Step 1 · Database Location",
                  style="DialogTitle.TLabel").pack(anchor="w")
        ttk.Label(outer, text="Choose a directory for the portfolio database.",
                  style="FieldLabel.TLabel").pack(anchor="w", pady=(8, 2))

        current = cfg.get("db_path")
        default_dir = os.path.dirname(current) if current else _DEFAULT_DB_DIR

        ttk.Label(outer, text=f"Default: {default_dir}",
                  style="Subtitle.TLabel").pack(anchor="w", pady=(0, 8))

        dir_frame = ttk.Frame(outer, style="Card.TFrame")
        dir_frame.pack(fill="x", pady=4)
        dir_var = tk.StringVar(value=default_dir)
        dir_entry = ttk.Entry(dir_frame, textvariable=dir_var, width=42)
        dir_entry.pack(side="left", fill="x", expand=True)
        ttk.Button(dir_frame, text="Browse...", width=10,
                   command=lambda: _browse_dir(dir_var)).pack(side="left", padx=(8, 0))

        status_var = tk.StringVar(value="")
        ttk.Label(outer, textvariable=status_var,
                  style="Error.TLabel").pack(anchor="w", pady=(8, 0))

        btn_frame = ttk.Frame(outer, style="Card.TFrame")
        btn_frame.pack(fill="x", pady=(16, 0))
        ttk.Button(btn_frame, text="Cancel", command=lambda: _cancel(dlg),
                   width=10).pack(side="right", padx=(8, 0))
        ttk.Button(btn_frame, text="Next \u2192", style="Accent.TButton",
                   width=10,
                   command=lambda: _finish_step1(dlg, dir_var, status_var)).pack(
            side="right")

        dir_entry.focus_set()
        dlg.grab_set()
        root.wait_window(dlg)

    def _browse_dir(var):
        d = filedialog.askdirectory(title="Select database directory")
        if d:
            var.set(d)

    def _finish_step1(dlg, dir_var, status_var):
        db_dir = os.path.expanduser(os.path.expandvars(dir_var.get().strip()))
        if not db_dir:
            status_var.set("Please enter a directory.")
            return
        db_path = os.path.join(db_dir, "portfolio.db")
        try:
            os.makedirs(db_dir, exist_ok=True)
        except OSError as exc:
            status_var.set(f"Cannot create directory: {exc}")
            return
        cfg["db_path"] = db_path
        config.save_config(cfg)
        database.set_db_path(db_path)
        database.init_db()
        dlg.destroy()

    def _cancel(dlg):
        result["cancelled"] = True
        dlg.destroy()

    # ── Step 2: Default mode ─────────────────────────────────────────────
    def _step2():
        dlg = tk.Toplevel(root)
        dlg.title(f"{APP_NAME} — Setup Wizard (2/4)")
        dlg.configure(bg=_C["surface"])
        dlg.resizable(False, False)
        w, h = 440, 300
        sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
        dlg.geometry(f"{w}x{h}+{(sw-w)//2}+{(sh-h)//2}")
        dlg.protocol("WM_DELETE_WINDOW", lambda: _cancel(dlg))

        outer = ttk.Frame(dlg, style="Card.TFrame", padding=24)
        outer.pack(fill="both", expand=True)

        ttk.Label(outer, text="Step 2 · Default Interface",
                  style="DialogTitle.TLabel").pack(anchor="w")
        ttk.Label(outer, text="Choose which interface launches by default.",
                  style="FieldLabel.TLabel").pack(anchor="w", pady=(8, 12))

        mode_var = tk.StringVar(value="interactive")
        modes = [
            ("Console (non-interactive)", "console"),
            ("Interactive REPL", "interactive"),
            ("Textual UI (full-screen TUI)", "tui"),
            ("Graphical Interface", "gui"),
        ]
        for label, val in modes:
            rb = tk.Radiobutton(outer, text=label, variable=mode_var, value=val,
                                bg=_C["surface"], fg=_C["fg"],
                                selectcolor=_C["bg"],
                                activebackground=_C["surface"],
                                activeforeground=_C["accent"],
                                font=("Segoe UI", 10), anchor="w",
                                indicatoron=True)
            rb.pack(anchor="w", pady=2, padx=8)

        btn_frame = ttk.Frame(outer, style="Card.TFrame")
        btn_frame.pack(fill="x", pady=(16, 0))
        ttk.Button(btn_frame, text="Cancel", command=lambda: _cancel(dlg),
                   width=10).pack(side="right", padx=(8, 0))
        ttk.Button(btn_frame, text="Next \u2192", style="Accent.TButton",
                   width=10,
                   command=lambda: _finish_step2(dlg, mode_var)).pack(side="right")

        dlg.grab_set()
        root.wait_window(dlg)

    def _finish_step2(dlg, mode_var):
        mode = mode_var.get()
        cfg["default_mode"] = mode
        config.save_config(cfg)
        dlg.destroy()

    # ── Step 3: First instrument ─────────────────────────────────────────
    def _step3():
        dlg = tk.Toplevel(root)
        dlg.title(f"{APP_NAME} — Setup Wizard (3/4)")
        dlg.configure(bg=_C["surface"])
        dlg.resizable(False, False)
        w, h = 500, 380
        sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
        dlg.geometry(f"{w}x{h}+{(sw-w)//2}+{(sh-h)//2}")
        dlg.protocol("WM_DELETE_WINDOW", lambda: _cancel(dlg))

        outer = ttk.Frame(dlg, style="Card.TFrame", padding=24)
        outer.pack(fill="both", expand=True)

        ttk.Label(outer, text="Step 3 · Add Your First Instrument",
                  style="DialogTitle.TLabel").pack(anchor="w")
        ttk.Label(outer, text="Optionally add a stock or ETF now. You can skip this.",
                  style="FieldLabel.TLabel").pack(anchor="w", pady=(8, 12))

        fields_frame = ttk.Frame(outer, style="Card.TFrame")
        fields_frame.pack(fill="x")

        entries = {}
        for i, (label, key, hint) in enumerate([
            ("Ticker", "ticker", "e.g. AAPL, NESN.SW, VWCE.DE"),
            ("ISIN (optional)", "isin", "e.g. CH0038863350"),
            ("Shares", "shares", "Number of shares"),
            ("Avg price (optional)", "avg_price", "Leave empty to skip"),
        ]):
            ttk.Label(fields_frame, text=label, style="FieldLabel.TLabel").grid(
                row=i, column=0, sticky="w", pady=4)
            e = ttk.Entry(fields_frame, width=30)
            e.grid(row=i, column=1, sticky="ew", padx=(10, 0), pady=4)
            entries[key] = e
        fields_frame.columnconfigure(1, weight=1)

        status_var = tk.StringVar(value="")
        ttk.Label(outer, textvariable=status_var,
                  style="Error.TLabel").pack(anchor="w", pady=(8, 0))

        btn_frame = ttk.Frame(outer, style="Card.TFrame")
        btn_frame.pack(fill="x", pady=(12, 0))
        ttk.Button(btn_frame, text="Cancel", command=lambda: _cancel(dlg),
                   width=10).pack(side="right", padx=(8, 0))
        ttk.Button(btn_frame, text="Skip \u2192", width=10,
                   command=dlg.destroy).pack(side="right", padx=(8, 0))
        ttk.Button(btn_frame, text="Add & Next \u2192", style="Accent.TButton",
                   width=14,
                   command=lambda: _finish_step3(dlg, entries, status_var)).pack(
            side="right")

        entries["ticker"].focus_set()
        dlg.grab_set()
        root.wait_window(dlg)

    def _finish_step3(dlg, entries, status_var):
        from .validation import (
            validate_ticker, validate_isin, validate_shares, validate_price,
        )
        ticker = entries["ticker"].get().strip()
        isin_raw = entries["isin"].get().strip()
        shares_s = entries["shares"].get().strip()
        price_s = entries["avg_price"].get().strip()

        if not ticker and not isin_raw:
            status_var.set("Enter at least a ticker or ISIN.")
            return

        if ticker:
            ticker, err = validate_ticker(ticker)
            if err:
                status_var.set(err)
                return

        isin = None
        if isin_raw:
            isin, err = validate_isin(isin_raw)
            if err:
                status_var.set(err)
                return

        shares, err = validate_shares(shares_s)
        if err:
            status_var.set(err)
            return

        avg_price, err = validate_price(price_s)
        if err:
            status_var.set(err)
            return

        status_var.set("Adding instrument...")
        dlg.update()

        from .operations import add_instrument
        ok = add_instrument(
            ticker=ticker or None, isin=isin,
            shares=shares, avg_purchase_price=avg_price,
        )
        if ok:
            dlg.destroy()
        else:
            status_var.set("Failed to add. Check ticker/ISIN.")

    # ── Step 4: Encryption ───────────────────────────────────────────────
    def _step4():
        dlg = tk.Toplevel(root)
        dlg.title(f"{APP_NAME} — Setup Wizard (4/4)")
        dlg.configure(bg=_C["surface"])
        dlg.resizable(False, False)
        w, h = 440, 280
        sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
        dlg.geometry(f"{w}x{h}+{(sw-w)//2}+{(sh-h)//2}")
        dlg.protocol("WM_DELETE_WINDOW", lambda: _cancel(dlg))

        outer = ttk.Frame(dlg, style="Card.TFrame", padding=24)
        outer.pack(fill="both", expand=True)

        ttk.Label(outer, text="Step 4 · Encryption",
                  style="DialogTitle.TLabel").pack(anchor="w")
        ttk.Label(outer, text="Encrypt your portfolio database with a password?",
                  style="FieldLabel.TLabel").pack(anchor="w", pady=(8, 4))
        ttk.Label(outer, text="Protects your data if the device is lost or shared.",
                  style="Subtitle.TLabel").pack(anchor="w", pady=(0, 12))

        pw_frame = ttk.Frame(outer, style="Card.TFrame")
        pw_frame.pack(fill="x")
        ttk.Label(pw_frame, text="Password", style="FieldLabel.TLabel").grid(
            row=0, column=0, sticky="w", pady=4)
        pw_entry = ttk.Entry(pw_frame, show="*", width=28)
        pw_entry.grid(row=0, column=1, sticky="ew", padx=(10, 0), pady=4)
        ttk.Label(pw_frame, text="Confirm", style="FieldLabel.TLabel").grid(
            row=1, column=0, sticky="w", pady=4)
        pw_confirm = ttk.Entry(pw_frame, show="*", width=28)
        pw_confirm.grid(row=1, column=1, sticky="ew", padx=(10, 0), pady=4)
        pw_frame.columnconfigure(1, weight=1)

        status_var = tk.StringVar(value="")
        ttk.Label(outer, textvariable=status_var,
                  style="Error.TLabel").pack(anchor="w", pady=(8, 0))

        btn_frame = ttk.Frame(outer, style="Card.TFrame")
        btn_frame.pack(fill="x", pady=(12, 0))
        ttk.Button(btn_frame, text="Cancel", command=lambda: _cancel(dlg),
                   width=10).pack(side="right", padx=(8, 0))
        ttk.Button(btn_frame, text="Skip", width=10,
                   command=dlg.destroy).pack(side="right", padx=(8, 0))
        ttk.Button(btn_frame, text="Encrypt", style="Accent.TButton",
                   width=10,
                   command=lambda: _finish_step4(dlg, pw_entry, pw_confirm, status_var)
                   ).pack(side="right")

        pw_entry.focus_set()
        dlg.grab_set()
        root.wait_window(dlg)

    def _finish_step4(dlg, pw_entry, pw_confirm, status_var):
        pw1 = pw_entry.get()
        pw2 = pw_confirm.get()
        if not pw1:
            status_var.set("Password cannot be empty.")
            return
        if pw1 != pw2:
            status_var.set("Passwords do not match.")
            return

        status_var.set("Encrypting...")
        dlg.update()

        db_path = cfg["db_path"]
        from .vault import VaultSession
        from .backup import create_backup
        create_backup(db_path)
        VaultSession.setup_encryption(db_path, pw1)
        cfg["encrypted"] = True
        config.save_config(cfg)
        dlg.destroy()

    # ── Run steps ────────────────────────────────────────────────────────
    _step1()
    if result["cancelled"] or "db_path" not in cfg:
        root.destroy()
        return {}

    _step2()
    if result["cancelled"]:
        root.destroy()
        return cfg

    _step3()
    if result["cancelled"]:
        root.destroy()
        return cfg

    _step4()

    # ── Done dialog ──────────────────────────────────────────────────────
    if not result["cancelled"]:
        db_path = cfg.get("db_path", "")
        encrypted = cfg.get("encrypted", False)
        messagebox.showinfo(
            "Setup Complete",
            f"Database: {db_path}\n"
            f"Encrypted: {'Yes' if encrypted else 'No'}\n\n"
            f"Setup is complete. The application will now start.",
            parent=root,
        )

    root.destroy()
    return cfg


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run_gui(needs_refresh: bool = False, verbose: bool = False) -> None:
    """Launch the Lynx Portfolio graphical interface."""
    app = LynxGUI(needs_refresh=needs_refresh, verbose=verbose)
    app.run()
