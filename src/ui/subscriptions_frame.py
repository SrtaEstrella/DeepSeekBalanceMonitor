"""Subscriptions page — one card per package account.

The dashboard shows the account selected in its own picker; this page is the
other half of the multi-account view: every plan account at once, each with its
windows, remaining share and reset countdown (Rust v2.4's subscription page).
"""
import tkinter as tk
from tkinter import ttk

from src.core.config import T, load_config
from src.core.storage import get_refined_remaining, get_today_spend
from src.platforms.opencode import format_reset_short
from src.platforms.registry import get_platform

_WINDOW_KEYS = {"5h": ("5h", "rolling"), "weekly": ("weekly",), "monthly": ("monthly",)}
_WINDOW_LABELS = {"5h": "win_5h", "weekly": "win_weekly", "monthly": "win_monthly"}


class SubscriptionsFrame(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, padding=12)
        self.app = app
        self._build()

    def _build(self):
        lang = self.app.lang
        ttk.Label(self, text=T("subscriptions", lang),
                  font=("Segoe UI", 12, "bold")).pack(anchor="w")
        ttk.Label(self, text=T("subscriptions_hint", lang),
                  foreground="#888", font=("Segoe UI", 8)).pack(anchor="w", pady=(2, 8))

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
        apis = [a for a in (load_config().get("apis") or [])
                if a.get("mode") == "package"]
        with self.app._lock:
            cache = {aid: dict(entry) for aid, entry in self.app._api_cache.items()}

        if not apis:
            ttk.Label(self.inner, text=T("subscriptions_empty", lang),
                      foreground="#888").pack(anchor="w", pady=12)
            return

        for api in apis:
            self._card(api, cache.get(api.get("id") or "") or {}, lang)

    def _card(self, api: dict, entry: dict, lang: str):
        aid = api.get("id") or ""
        platform = api.get("platform", "")
        meta = get_platform(platform)
        display = meta.display_name if meta else platform
        name = api.get("name") or display
        windows = meta.package_windows if meta else ["5h", "weekly", "monthly"]
        billing = api.get("billing_period") or ""

        card = tk.Frame(self.inner, bd=1, relief="solid")
        card.pack(fill="x", pady=4, padx=2)
        head = tk.Frame(card)
        head.pack(fill="x", padx=8, pady=(6, 2))
        tk.Label(head, text=name, font=("Segoe UI", 10, "bold"),
                 anchor="w").pack(side="left")
        tk.Label(head, text=display, foreground="#888",
                 font=("Segoe UI", 8)).pack(side="left", padx=(8, 0))
        if billing:
            tk.Label(head, text=T("billing_period_label", lang).rstrip("：:"),
                     foreground="#888", font=("Segoe UI", 8)).pack(side="right")

        pkg = entry.get("package_data") or {}
        if entry.get("error"):
            tk.Label(card, text=entry["error"], foreground="#b3261e", anchor="w",
                     font=("Segoe UI", 8)).pack(fill="x", padx=8, pady=(2, 6))
            return
        if not pkg:
            tk.Label(card, text=T("overview_no_data", lang), foreground="#888",
                     anchor="w", font=("Segoe UI", 8)).pack(fill="x", padx=8, pady=(2, 6))
            return

        for wkey in windows:
            data = None
            for key in _WINDOW_KEYS.get(wkey, (wkey,)):
                data = pkg.get(key)
                if data:
                    break
            if not data:
                continue
            remaining = data.get("percent_remaining", 100 - data.get("usage_percent", 0))
            fine = False
            if wkey in ("weekly", "monthly"):
                refined = get_refined_remaining(aid, target=wkey)
                if refined is not None:
                    remaining, fine = refined, True
            reset = data.get("reset_in_sec", 0)
            row = tk.Frame(card)
            row.pack(fill="x", padx=8, pady=2)
            tk.Label(row, text=T(_WINDOW_LABELS.get(wkey, wkey), lang),
                     width=7, anchor="w").pack(side="left")
            ttk.Progressbar(row, value=max(0.0, min(100.0, remaining)),
                            maximum=100, length=180).pack(side="left", padx=(4, 8))
            value = f"{remaining:.1f}%" if fine else f"{remaining:.0f}%"
            tk.Label(row, text=f"{value}  {format_reset_short(reset, lang) if reset > 0 else '-'}",
                     anchor="w").pack(side="left")

        try:
            spent = get_today_spend(aid, "package", billing or None)
        except Exception:
            spent = 0.0
        if spent:
            tk.Label(card, text=T("subscriptions_today", lang, value=f"{spent:.2f}%"),
                     foreground="#666", anchor="w",
                     font=("Segoe UI", 8)).pack(fill="x", padx=8, pady=(2, 6))
