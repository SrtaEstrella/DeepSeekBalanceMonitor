"""
API Management Frame — for MainWindow Notebook.
Multi-platform multi-account via platform registry.
"""
import threading
import tkinter as tk
from tkinter import ttk, messagebox

from src.core.config import T, load_config, create_api, update_api, delete_api, get_apis
from src.core.secure_settings import read_api_key_for_id
from src.platforms.registry import get_all_platforms, get_platform


class ApiManagementFrame(ttk.Frame):
    def __init__(self, parent, app, on_change=None, on_select=None):
        super().__init__(parent, padding=10)
        self.app = app
        self.on_change = on_change
        self.on_select = on_select
        self._build()

    def _build(self):
        lang = self.app.lang
        # Header with title and action buttons
        header = ttk.Frame(self)
        header.pack(fill="x", pady=(0, 8))
        ttk.Label(header, text=T("api_management", lang), font=("Segoe UI", 11, "bold")).pack(side="left")
        self._btn_edit = ttk.Button(header, text="✏️ " + T("edit_api", lang), command=self._on_edit)
        self._btn_edit.pack(side="right", padx=(4, 0))
        self._btn_delete = ttk.Button(header, text="🗑 " + T("delete_api", lang), command=self._on_delete)
        self._btn_delete.pack(side="right")
        self._btn_add = ttk.Button(header, text="➕ " + T("add_api", lang), command=self._on_add)
        self._btn_add.pack(side="right", padx=(0, 8))
        # set-as-preferred: applies to the highlighted row; disabled when it IS preferred
        self._btn_pref = ttk.Button(header, text="⭐ " + T("set_preferred_btn", lang), command=self._on_set_preferred)
        self._btn_pref.pack(side="right")
        # initially disable edit/delete (no selection)
        self._btn_edit.configure(state="disabled")
        self._btn_delete.configure(state="disabled")

                # Tree
        tree_frame = ttk.Frame(self)
        tree_frame.pack(fill="both", expand=True)
        # centered placeholder when no APIs exist
        self._empty_label = tk.Label(tree_frame, text=T("no_apis", lang),
                                     font=("Microsoft YaHei UI", 11), fg="#999")
        tree_style = ttk.Style()
        tree_style.configure("Api.Treeview", rowheight=30, font=("Segoe UI", 9))
        self.tree = ttk.Treeview(tree_frame, columns=("name", "platform", "billing", "id"), show="headings", height=8, style="Api.Treeview")
        self.tree.heading("name", text=T("api_name_label", lang).rstrip("：:"))
        self.tree.heading("platform", text=T("platform_label", lang).rstrip("：:"))
        self.tree.heading("billing", text=T("billing_period_label", lang).rstrip("：:"))
        self.tree.heading("id", text=T("api_id_label", lang).rstrip("：:"))
        self.tree.column("name", width=160, anchor="w")
        self.tree.column("platform", width=130, anchor="center")
        self.tree.column("billing", width=100, anchor="center")
        self.tree.column("id", width=90, anchor="center")
        sb = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.tree.bind("<Double-1>", lambda e: self._on_edit())
        self.tree.bind("<<TreeviewSelect>>", self._on_select)

        self.hint = tk.StringVar(value="")
        # empty-text labels still occupy a full line — pack only when there is content
        self._hint_label = ttk.Label(self, textvariable=self.hint, font=("Segoe UI", 9), foreground="#888")

        self.refresh()

    def select_api(self, api_id: str) -> bool:
        """Selects the row for an account id (the overview's cards use this)."""
        for item in self.tree.get_children():
            values = self.tree.item(item, "values")
            if len(values) >= 4 and values[3] == api_id:
                self.tree.selection_set(item)
                self.tree.focus(item)
                self.tree.see(item)
                return True
        return False

    def _selected_id(self):
        sel = self.tree.selection()
        if not sel:
            return None
        vals = self.tree.item(sel[0], "values")
        return vals[3] if len(vals) >= 4 else (vals[2] if len(vals) >= 3 else None)

    def _on_select(self, _event=None):
        selected = self._selected_id()
        state = "normal" if selected else "disabled"
        try:
            self._btn_edit.configure(state=state)
        except Exception:
            pass
        try:
            self._btn_delete.configure(state=state)
        except Exception:
            pass
        # preferred button: enabled only when the selected row is NOT already preferred
        cur_pref = (self.app.config or {}).get("preferred_api_id", "")
        is_pref = bool(selected) and selected == cur_pref
        try:
            self._btn_pref.configure(
                state="disabled" if is_pref else state,
                text=("⭐ " + T("already_preferred", lang)) if is_pref
                     else ("⭐ " + T("set_preferred_btn", lang)),
            )
        except Exception:
            pass
        # notify external listener (e.g. ledger table below in Manage tab)
        if self.on_select:
            try:
                self.on_select(selected)
            except Exception:
                pass

    def _on_set_preferred(self):
        """Persist the highlighted API as preferred, then sync tray/ledger/dashboard."""
        api_id = self._selected_id()
        if not api_id:
            return
        # reuse the tray's full switch chain: config + cache + icon + main-window sync
        from src.tray_app import _apply_preferred_switch
        from src.core.paths import log as _log
        _apply_preferred_switch(self.app, api_id)
        _log(f"Preferred API set to {api_id} via manage tab")
        # re-render row states (button label/disabled) + notify ledger listener
        self.refresh()
        messagebox.showinfo(T("set_preferred_btn", self.app.lang),
                            T("preferred_api_label", self.app.lang) + " " +
                            (self.tree.item(self.tree.selection()[0], "values")[0]
                             if self.tree.selection() else ""),
                            parent=self.winfo_toplevel())

    def refresh(self, follow_preferred=False):
        # reload tree from config
        try:
            self.tree.delete(*self.tree.get_children())
        except Exception:
            pass
        try:
            # read the shared in-memory config (authoritative; test/mock friendly)
            cfg = self.app.config
            apis = cfg.get("apis") or []
            for api in apis:
                plat_key = api.get("platform", "")
                pmeta = get_platform(plat_key)
                plat_disp = pmeta.display_name if pmeta else plat_key
                bp = api.get("billing_period", "")
                # raw literal form ("5h"/"weekly"/"monthly"), em-dash placeholder if unset
                bp_disp = bp if bp else "—"
                self.tree.insert("", "end", values=(api.get("name"), plat_disp, bp_disp, api.get("id")))
            if not apis:
                self.hint.set(T("no_apis", self.app.lang))
                try:
                    self._empty_label.place(relx=0.5, rely=0.5, anchor="center")
                    self._empty_label.lift()
                except Exception:
                    pass
            else:
                self.hint.set("")
                try:
                    self._empty_label.place_forget()
                except Exception:
                    pass
                # default-select the preferred API (or first row) so the ledger follows
                pref_id = cfg.get("preferred_api_id", "")
                target_iid = None
                for iid in self.tree.get_children():
                    vals = self.tree.item(iid, "values")
                    if len(vals) >= 4 and vals[3] == pref_id:
                        target_iid = iid
                        break
                if target_iid is None:
                    kids = self.tree.get_children()
                    target_iid = kids[0] if kids else None
                if target_iid:
                    self.tree.selection_set(target_iid)
            # re-emit current selection so listeners (ledger) follow add/delete
            self._on_select()
            # notify parent if needed
            if self.on_change:
                try:
                    self.on_change()
                except Exception:
                    pass
        except Exception as e:
            self.hint.set(str(e))

    def on_show(self):
        self.refresh()

    def _on_add(self):
        self._open_form(mode="add")

    def _on_edit(self):
        api_id = self._selected_id()
        if not api_id:
            messagebox.showwarning(T("warn_title", self.app.lang), T("no_apis", self.app.lang), parent=self.winfo_toplevel())
            return
        self._open_form(mode="edit", api_id=api_id)

    def _on_delete(self):
        api_id = self._selected_id()
        if not api_id:
            return
        cfg = load_config()
        api = next((a for a in cfg.get("apis", []) if a["id"] == api_id), None)
        name = api.get("name") if api else api_id
        if not messagebox.askyesno(T("warn_title", self.app.lang), T("confirm_delete", self.app.lang, name=name), parent=self.winfo_toplevel()):
            return
        if delete_api(api_id):
            # also need to refresh config in app
            try:
                self.app.config = load_config()
            except Exception:
                pass
            self.refresh()
            # trigger tray refresh
            try:
                if hasattr(self.app, "_rebuild_menu") and self.app.icon:
                    self.app.icon.menu = self.app._rebuild_menu()
                # refresh history second-level tabs if main window exists
                if hasattr(self.app, "_main_window") and self.app._main_window:
                    # find history frame and refresh its api selector
                    try:
                        hist = self.app._main_window._tabs.get("history")
                        if hist and hasattr(hist, "refresh_api_selector"):
                            hist.refresh_api_selector()
                    except Exception:
                        pass
            except Exception:
                pass
            messagebox.showinfo(T("delete_api", self.app.lang), T("delete_success", self.app.lang, name=name), parent=self.winfo_toplevel())
        else:
            messagebox.showerror(T("warn_title", self.app.lang), T("api_exists", self.app.lang), parent=self.winfo_toplevel())

    def _open_form(self, mode="add", api_id=None):
        lang = self.app.lang
        is_edit = mode == "edit"
        cfg = load_config()
        api = None
        if is_edit:
            api = next((a for a in cfg.get("apis", []) if a["id"] == api_id), None)
            if not api:
                return
        # Toplevel form
        top = tk.Toplevel(self.winfo_toplevel())
        top.title(T("edit_api", lang) if is_edit else T("add_api", lang))
        top.geometry("440x660")
        top.transient(self.winfo_toplevel())
        top.grab_set()
        top.resizable(False, False)
        # center
        top.update_idletasks()
        sw, sh = top.winfo_screenwidth(), top.winfo_screenheight()
        w, h = top.winfo_width(), top.winfo_height()
        top.geometry(f"+{(sw-w)//2}+{(sh-h)//2}")

        # Platform — from registry
        ttk.Label(top, text=T("platform_label", lang)).pack(anchor="w", padx=12, pady=(12, 0))
        all_plat = get_all_platforms()
        plat_var = tk.StringVar(value=api.get("platform", all_plat[0].key) if is_edit else all_plat[0].key)
        plat_display = [p.display_name for p in all_plat]
        plat_map = {p.display_name: p.key for p in all_plat}
        cur_disp = next((p.display_name for p in all_plat if p.key == plat_var.get()), plat_display[0])
        plat_combo_var = tk.StringVar(value=cur_disp)
        plat_combo = ttk.Combobox(top, textvariable=plat_combo_var, values=plat_display, state="readonly" if not is_edit else "disabled", width=18)
        plat_combo.pack(anchor="w", padx=12, pady=(0, 8))

        # Name — directly filled with default "平台-序号", editable
        ttk.Label(top, text=T("api_name_label", lang)).pack(anchor="w", padx=12)
        def _default_name_for(plat):
            from src.core.config import _get_next_api_name, load_config as _lc
            try:
                _cfg = _lc()
                return _get_next_api_name(plat, _cfg.get("apis") or [])
            except Exception:
                pmeta = get_platform(plat)
                prefix = pmeta.display_name if pmeta else plat
                return f"{prefix}-1"
        init_plat = plat_map.get(plat_combo_var.get(), "deepseek")
        init_name = api.get("name", "") if is_edit else _default_name_for(init_plat)
        name_var = tk.StringVar(value=init_name)
        name_entry = ttk.Entry(top, textvariable=name_var, width=36)
        name_entry.pack(anchor="w", padx=12, pady=(0, 8))
        _name_touched = {"v": is_edit, "updating": False}
        def _on_name_write(*_a):
            if _name_touched.get("updating"):
                return
            _name_touched["v"] = True
        try:
            name_var.trace_add("write", _on_name_write)
        except Exception:
            pass
        def _on_plat_change(*_a):
            """Auto-update default name when platform switches (add mode only)."""
            if is_edit or _name_touched["v"]:
                return
            plat = plat_map.get(plat_combo_var.get(), all_plat[0].key)
            try:
                _name_touched["updating"] = True
                name_var.set(_default_name_for(plat))
            finally:
                _name_touched["updating"] = False
        plat_combo_var.trace_add("write", _on_plat_change)

        # Credentials area — single API Key field for all platforms
        cred_frame = ttk.Frame(top)
        cred_frame.pack(fill="both", expand=True, padx=12, pady=(0, 8))

        key_hint = T("key_stored_hint", lang)
        cred_var = tk.StringVar(value="")
        cred_entry = ttk.Entry(cred_frame, textvariable=cred_var, show="•", width=36)
        cred_entry_state = {"placeholder_active": is_edit}
        if is_edit:
            cred_var.set(key_hint)
            cred_entry.configure(foreground="gray")
        def _cred_focus_in(_e):
            if cred_entry_state["placeholder_active"]:
                cred_var.set("")
                cred_entry.configure(foreground="black")
                cred_entry_state["placeholder_active"] = False
        def _cred_focus_out(_e):
            if cred_entry_state["placeholder_active"] and not cred_var.get().strip():
                cred_var.set(key_hint)
                cred_entry.configure(foreground="gray")
        cred_entry.bind("<FocusIn>", _cred_focus_in)
        cred_entry.bind("<FocusOut>", _cred_focus_out)
        cred_show = tk.BooleanVar(value=False)
        def _tog_cred(*_a):
            cred_entry.configure(show="" if cred_show.get() else "•")
        cred_show.trace_add("write", _tog_cred)
        cred_check = ttk.Checkbutton(cred_frame, text=T("show_key", lang), variable=cred_show)

        cred_label = ttk.Label(cred_frame, text=T("api_key_label", lang))
        cred_label.pack(anchor="w")
        cred_entry.pack(anchor="w", pady=(0, 2))
        cred_check.pack(anchor="w")

        # Billing period (package mode only) — options from platform's package_windows
        BILLING_LABELS = {"5h": "5小时滚动", "weekly": "每周", "monthly": "每月"}
        BILLING_LABELS_EN = {"5h": "5h rolling", "weekly": "Weekly", "monthly": "Monthly"}
        billing_period_var = tk.StringVar(value="monthly" if not is_edit else (api.get("billing_period", "monthly") if api else "monthly"))
        billing_frame = ttk.Frame(cred_frame)
        self._billing_frame = billing_frame
        billing_label = ttk.Label(billing_frame, text=T("billing_period_label", lang))
        self._billing_label = billing_label
        billing_combo = ttk.Combobox(billing_frame, textvariable=billing_period_var, state="readonly", width=14)
        self._billing_combo = billing_combo
        billing_hint = ttk.Label(billing_frame, text=T("billing_period_hint", lang), foreground="#888", font=("Segoe UI", 8))
        self._billing_hint = billing_hint

        def _refresh_billing(*_a):
            plat = plat_map.get(plat_combo_var.get(), all_plat[0].key)
            pmeta = get_platform(plat)
            if pmeta and pmeta.supports_package and not pmeta.supports_payg:
                billing_frame.pack(fill="x", pady=(8, 0))
                billing_label.pack(anchor="w")
                billing_combo.pack(anchor="w", pady=(0, 2))
                billing_hint.pack(anchor="w", pady=(0, 4))
                # set options from platform's package_windows
                pw = pmeta.package_windows
                opts = {k: BILLING_LABELS.get(k, k) if lang == "zh" else BILLING_LABELS_EN.get(k, k) for k in pw}
                billing_combo["values"] = list(opts.keys())
                # if current value not in options, reset to platform fallback
                if billing_period_var.get() not in opts:
                    billing_period_var.set(default_billing_period_for(pmeta))
            else:
                billing_frame.pack_forget()
                billing_period_var.set("")
        plat_combo_var.trace_add("write", _refresh_billing)
        _refresh_billing()

        # Account-level settings (Rust v2.4): a line of its own, a monthly
        # budget, and whether the account takes part in alerts / the widget.
        acct_frame = ttk.Frame(top)
        acct_frame.pack(fill="x", padx=12, pady=(8, 0))
        ttk.Label(acct_frame, text=T("alert_threshold_label", lang)).grid(row=0, column=0, sticky="w")
        alert_var = tk.StringVar(value=str(api.get("alert_threshold", 0) if is_edit else 0))
        ttk.Entry(acct_frame, textvariable=alert_var, width=10).grid(row=0, column=1, sticky="w", padx=(6, 0))
        ttk.Label(acct_frame, text=T("monthly_budget_label", lang)).grid(row=0, column=2, sticky="w", padx=(14, 0))
        budget_var = tk.StringVar(value=str(api.get("monthly_budget", 0) if is_edit else 0))
        ttk.Entry(acct_frame, textvariable=budget_var, width=10).grid(row=0, column=3, sticky="w", padx=(6, 0))
        alert_enabled_var = tk.BooleanVar(value=bool(api.get("alert_enabled", True)) if is_edit else True)
        ttk.Checkbutton(acct_frame, text=T("alert_enabled_label", lang),
                        variable=alert_enabled_var).grid(row=1, column=0, columnspan=2, sticky="w", pady=(6, 0))
        widget_var = tk.BooleanVar(value=bool(api.get("show_in_widget", True)) if is_edit else True)
        ttk.Checkbutton(acct_frame, text=T("show_in_widget_label", lang),
                        variable=widget_var).grid(row=1, column=2, columnspan=2, sticky="w", pady=(6, 0))
        ttk.Label(acct_frame, text=T("alert_threshold_hint", lang),
                  foreground="#888", font=("Segoe UI", 8)).grid(row=2, column=0, columnspan=4, sticky="w", pady=(2, 0))

        # Buttons
        btn_frame = ttk.Frame(top)
        btn_frame.pack(fill="x", side="bottom", padx=12, pady=12)
        def _clean_key(raw):
            """Return None if raw is the hint text or empty."""
            if not raw or raw.strip() == key_hint:
                return None
            return raw.strip()
        test_status = tk.StringVar(value="")
        test_btn = ttk.Button(btn_frame, text=T("key_test_btn", lang))
        test_btn.pack(side="left")
        ttk.Label(btn_frame, textvariable=test_status, foreground="#666").pack(side="left", padx=(6, 0))

        def _test():
            plat = plat_map.get(plat_combo_var.get(), all_plat[0].key)
            key = _clean_key(cred_var.get())
            if not key and is_edit:
                key = read_api_key_for_id(api_id)
            if not key:
                messagebox.showwarning(T("warn_title", lang), T("warn_no_key", lang), parent=top)
                return
            mode_for_test = api.get("mode", "payg") if is_edit else (
                get_platform(plat).default_mode if get_platform(plat) else "payg")
            proxy = self.app.config.get("http_proxy", "") if self.app.config.get("proxy_enabled") else ""
            test_btn.configure(state="disabled")
            test_status.set(T("key_test_running", lang))
            result = {}

            def _run():
                from src.platforms.key_test import test_key
                result["value"] = test_key(plat, mode_for_test, key, proxy)
            threading.Thread(target=_run, daemon=True).start()

            # Tk must be touched from the thread that owns it: the worker only
            # fills `result`, and this poll runs on the UI thread.
            def _poll():
                if "value" not in result:
                    try:
                        top.after(100, _poll)
                    except Exception:
                        pass
                    return
                ok, detail = result["value"]
                try:
                    test_status.set(T("key_test_ok", lang, detail=detail) if ok
                                    else T("key_test_fail", lang, error=detail))
                    test_btn.configure(state="normal")
                except Exception:
                    pass
            top.after(100, _poll)

        test_btn.configure(command=_test)
        def _save():
            plat = plat_map.get(plat_combo_var.get(), all_plat[0].key)
            name = name_var.get().strip()
            try:
                alert_threshold = max(0.0, float(alert_var.get() or 0))
                monthly_budget = max(0.0, float(budget_var.get() or 0))
            except ValueError:
                messagebox.showwarning(T("warn_title", lang), T("validate_number", lang), parent=top)
                return
            key = _clean_key(cred_var.get())
            # A key belongs to one account: refuse a value already stored under
            # another id instead of silently sharing the same provider account.
            if key:
                for other in get_apis():
                    if other.get("id") == api_id:
                        continue
                    if read_api_key_for_id(other.get("id") or "") == key:
                        messagebox.showwarning(
                            T("warn_title", lang),
                            T("key_duplicate", lang, name=other.get("name") or other.get("id")),
                            parent=top)
                        return
            if mode == "add":
                if not key:
                    messagebox.showwarning(T("warn_title", lang), T("warn_no_key", lang), parent=top)
                    return
                new_id = create_api(platform=plat, name=name, api_key=key, billing_period=billing_period_var.get(),
                                    alert_threshold=alert_threshold, monthly_budget=monthly_budget,
                                    alert_enabled=alert_enabled_var.get(),
                                    show_in_widget=widget_var.get())
                # update app config
                try:
                    self.app.config = load_config()
                    if hasattr(self.app, "_rebuild_menu") and self.app.icon:
                        self.app.icon.menu = self.app._rebuild_menu()
                except Exception:
                    pass
                self.refresh()
                try:
                    if hasattr(self.app, "_main_window") and self.app._main_window:
                        hist = self.app._main_window._tabs.get("history")
                        if hist and hasattr(hist, "refresh_api_selector"):
                            hist.refresh_api_selector()
                except Exception:
                    pass
                top.destroy()
            else:
                # edit — only update key if user typed a new value (not hint text)
                update_api(api_id, name=name, api_key=key, billing_period=billing_period_var.get(),
                           alert_threshold=alert_threshold, monthly_budget=monthly_budget,
                           alert_enabled=alert_enabled_var.get(),
                           show_in_widget=widget_var.get())
                self.app.config = load_config()
                if hasattr(self.app, "_rebuild_menu") and self.app.icon:
                    try:
                        self.app.icon.menu = self.app._rebuild_menu()
                    except Exception:
                        pass
                self.refresh()
                try:
                    if hasattr(self.app, "_main_window") and self.app._main_window:
                        hist = self.app._main_window._tabs.get("history")
                        if hasattr(hist, "refresh_api_selector"):
                            hist.refresh_api_selector()
                except Exception:
                    pass
                top.destroy()

        ttk.Button(btn_frame, text=T("save", lang), command=_save).pack(side="right", padx=(5, 0))
        ttk.Button(btn_frame, text=T("cancel", lang), command=top.destroy).pack(side="right")
        top.bind("<Return>", lambda e: _save())
        top.bind("<Escape>", lambda e: top.destroy())
        if is_edit:
            name_entry.focus_set()
        else:
            plat_combo.focus_set()
