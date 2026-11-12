"""Overview page — every account on one page.

Rust v2.4 puts the accounts closest to their line first and lets a card open
the platform page with that account selected. This page keeps that idea in
tkinter: totals per currency at the top, then one row per account, with the
accounts that need attention first.
"""
import tkinter as tk
from tkinter import ttk

from src.core.config import T, load_config
from src.platforms.registry import get_platform


class OverviewFrame(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, padding=12)
        self.app = app
        self._build()

    def _build(self):
        lang = self.app.lang
        ttk.Label(self, text=T("overview", lang),
                  font=("Segoe UI", 12, "bold")).pack(anchor="w")
        self.totals = ttk.Label(self, text="", font=("Segoe UI", 10, "bold"))
        self.totals.pack(anchor="w", pady=(4, 2))
        ttk.Label(self, text=T("overview_hint", lang),
                  foreground="#888", font=("Segoe UI", 8)).pack(anchor="w", pady=(0, 8))

        holder = ttk.Frame(self)
        holder.pack(fill="both", expand=True)
        self.scroll = tk.Canvas(holder, highlightthickness=0)
        vsb = ttk.Scrollbar(holder, orient="vertical", command=self.scroll.yview)
        self.scroll.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        self.scroll.pack(side="left", fill="both", expand=True)
        self.inner = ttk.Frame(self.scroll)
        self._window = self.scroll.create_window((0, 0), window=self.inner, anchor="nw")
        self.inner.bind("<Configure>",
                        lambda e: self.scroll.configure(scrollregion=self.scroll.bbox("all")))
        self.scroll.bind("<Configure>",
                         lambda e: self.scroll.itemconfigure(self._window, width=e.width))
        self.refresh()

    def refresh(self, follow_preferred=False):
        for widget in self.inner.winfo_children():
            widget.destroy()

        lang = self.app.lang
        cfg = load_config()
        apis = list(cfg.get("apis") or [])
        preferred_id = cfg.get("preferred_api_id", "")
        with self.app._lock:
            cache = {aid: dict(entry) for aid, entry in self.app._api_cache.items()}

        totals = {}
        rows = []
        for api in apis:
            aid = api.get("id") or ""
            entry = cache.get(aid) or {}
            name = api.get("name") or api.get("platform") or aid
            platform = api.get("platform", "")
            meta = get_platform(platform)
            display = meta.display_name if meta else platform
            kind = api.get("mode", "payg")
            risk = 0
            reading = ""
            note = ""

            if kind == "package":
                pkg = entry.get("package_data") or {}
                main = pkg.get("monthly") or pkg.get("weekly") or pkg.get("5h") or pkg.get("rolling")
                if main:
                    remaining = main.get("percent_remaining",
                                         100 - main.get("usage_percent", 0))
                    reading = f"{remaining:.1f}%"
                    line = self._line(api, "threshold_package_percent", aid == preferred_id)
                    if remaining < line:
                        risk = 2
                        note = T("overview_low", lang, line=f"{line:g}%")
                elif entry.get("error"):
                    risk = 3
                    note = entry["error"]
                else:
                    note = T("overview_no_data", lang)
            else:
                balances = entry.get("balances") or {}
                code = "CNY" if "CNY" in balances else next(iter(balances), None)
                bal = balances.get(code) if code else None
                if bal:
                    reading = f"{bal['total_balance']:,.2f} {code}"
                    totals[code] = totals.get(code, 0.0) + bal["total_balance"]
                    line = self._line(api, "threshold_yuan", aid == preferred_id)
                    if line > 0 and bal["total_balance"] < line:
                        risk = 2
                        note = T("overview_low", lang, line=f"{line:,.2f} {code}")
                elif entry.get("error"):
                    risk = 3
                    note = entry["error"]
                else:
                    note = T("overview_no_data", lang)
                budget = float(api.get("monthly_budget") or 0.0)
                if budget > 0:
                    from src.core.storage import get_month_spend
                    spent = get_month_spend(aid)
                    if spent and spent[1] >= budget:
                        risk = max(risk, 2)
                        note = T("overview_budget", lang,
                                 spent=f"{spent[1]:,.2f}", budget=f"{budget:,.2f}")

            rows.append((risk, name, display, kind, reading, note, aid))

        if totals:
            self.totals.configure(text="   ".join(
                f"{T('overview_total', lang)} {code}: {value:,.2f}"
                for code, value in sorted(totals.items())))
        else:
            self.totals.configure(text=T("overview_empty_totals", lang))

        if not apis:
            ttk.Label(self.inner, text=T("overview_empty", lang),
                      foreground="#888").pack(anchor="w", pady=12)
            return

        for risk, name, display, kind, reading, note, aid in sorted(rows, key=lambda r: -r[0]):
            self._card(risk, name, display, kind, reading, note, aid)

    @staticmethod
    def _line(api: dict, global_key: str, preferred: bool) -> float:
        """The account's own line; the global one applies only to the preferred
        account, because that is the account the existing alerts judge."""
        try:
            own = float(api.get("alert_threshold") or 0.0)
        except (TypeError, ValueError):
            own = 0.0
        if own > 0:
            return own
        if not preferred:
            return 0.0
        try:
            return float(load_config().get(global_key, 0.0))
        except (TypeError, ValueError):
            return 0.0

    def _card(self, risk, name, display, kind, reading, note, api_id):
        lang = self.app.lang
        if risk >= 3:
            color = "#b3261e"
        elif risk == 2:
            color = "#c77700"
        else:
            color = "#2e7d32"
        card = tk.Frame(self.inner, bd=1, relief="solid", highlightthickness=0)
        card.pack(fill="x", pady=3, padx=2)
        head = tk.Frame(card)
        head.pack(fill="x", padx=8, pady=(6, 0))
        tk.Label(head, text=name, font=("Segoe UI", 10, "bold"),
                 anchor="w").pack(side="left")
        tk.Label(head, text=display, foreground="#888",
                 font=("Segoe UI", 8)).pack(side="left", padx=(8, 0))
        tk.Label(head, text=reading or "—", foreground=color,
                 font=("Segoe UI", 10, "bold")).pack(side="right")
        if note:
            tk.Label(card, text=note, foreground=color, anchor="w",
                     font=("Segoe UI", 8)).pack(fill="x", padx=8, pady=(0, 6))
        else:
            tk.Label(card, text=T("overview_ok", lang), foreground="#888", anchor="w",
                     font=("Segoe UI", 8)).pack(fill="x", padx=8, pady=(0, 6))
        for widget in (card, head, *head.winfo_children(), *card.winfo_children()):
            try:
                widget.bind("<Button-1>", lambda e, aid=api_id: self._open(aid))
            except Exception:
                pass

    def _open(self, api_id: str):
        mw = getattr(self.app, "_main_window", None)
        if mw is None or not hasattr(mw, "show"):
            return
        mw.show("manage")

        def _select():
            manage = getattr(mw, "_tabs", {}).get("manage")
            if manage is not None and hasattr(manage, "select_api"):
                manage.select_api(api_id)
        try:
            mw._win.after(80, _select)
        except Exception:
            pass
