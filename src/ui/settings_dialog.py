"""
Settings dialog — tkinter window for configuring API key, interval, threshold,
language, auto-start, and alert toggle.
"""
import threading
import tkinter as tk
from tkinter import ttk

from src.platforms.registry import get_all_platforms
from src.core.config import T, load_config, get_apis

_PLAT_META = get_all_platforms()


class SettingsFrame(ttk.Frame):
    """Embeddable settings for MainWindow. on_save callback is called after successful save."""
    def __init__(self, parent, app, on_save=None):
        super().__init__(parent)
        self.app = app
        self.on_save = on_save
        self._dirty = False
        self._build()

    def _build(self):
        import os, sys, tkinter as tk
        from tkinter import ttk, messagebox, filedialog
        from src.core.config import T, save_config, log
        from src.ui.icon_renderer import THEMES, _hex_to_rgba, _text_color, create_icon_image
        from src.core.app_state import get_auto_start_state, set_auto_start

        lang = self.app.lang
        # scrollable canvas
        outer = ttk.Frame(self)
        outer.pack(fill="both", expand=True)
        canvas = tk.Canvas(outer, borderwidth=0, highlightthickness=0)
        scrollbar = tk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        scroll_frame = ttk.Frame(canvas)
        def _upd(*_a):
            canvas.configure(scrollregion=(0, 0, scroll_frame.winfo_reqwidth(), scroll_frame.winfo_reqheight()))
        scroll_frame.bind("<Configure>", _upd)
        win = canvas.create_window((0, 0), window=scroll_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(win, width=e.width))
        def _wheel(e): canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")
        canvas.bind("<Enter>", lambda e: canvas.bind_all("<MouseWheel>", _wheel))
        canvas.bind("<Leave>", lambda e: canvas.unbind_all("<MouseWheel>"))
        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True, padx=(10, 0), pady=(10, 0))


        # interval — one line: 查询间隔（分钟）：[spin] hint
        int_row = ttk.Frame(scroll_frame); int_row.pack(fill="x", pady=(0, 8))
        ttk.Label(int_row, text=T("interval_label", lang)).pack(side="left")
        interval_var = tk.IntVar(value=self.app.config.get("interval_minutes", 10))
        interval_sb = ttk.Spinbox(int_row, from_=1, to=1440, textvariable=interval_var, width=8)
        interval_sb.pack(side="left", padx=(6, 0))
        ttk.Label(int_row, text=T("interval_hint", lang)).pack(side="left")

        # fetch mode — one line: 查询模式：[并发(全部) | 单打(仅首选)]
        mode_row = ttk.Frame(scroll_frame); mode_row.pack(fill="x", pady=(0, 8))
        ttk.Label(mode_row, text=T("fetch_mode_label", lang)).pack(side="left")
        FETCH_OPTS = [T("fetch_mode_parallel", lang), T("fetch_mode_onehot", lang)]
        FETCH_MAP = {T("fetch_mode_parallel", lang): "parallel", T("fetch_mode_onehot", lang): "onehot"}
        cur_mode = FETCH_MAP.get(self.app.config.get("fetch_mode", "parallel"), "parallel")
        fetch_mode_var = tk.StringVar(value=next((d for d, k in FETCH_MAP.items() if k == cur_mode), FETCH_OPTS[0]))
        fetch_mode_combo = ttk.Combobox(mode_row, textvariable=fetch_mode_var, values=FETCH_OPTS, state="readonly", width=22)
        fetch_mode_combo.pack(side="left", padx=(6, 0))

        # threshold — leading word line, then indented widget line (fits any language)
        ttk.Label(scroll_frame, text=T("threshold_label", lang)).pack(anchor="w", pady=(0, 2))
        thr_row = ttk.Frame(scroll_frame); thr_row.pack(fill="x", padx=(16, 0), pady=(0, 8))
        threshold_var = tk.DoubleVar(value=self.app.config.get("threshold_yuan", 1.0))
        ttk.Label(thr_row, text=T("threshold_mode_label", lang)).pack(side="left")
        threshold_sb = ttk.Spinbox(thr_row, from_=0.0, to=10000.0, increment=0.5, textvariable=threshold_var, width=6)
        threshold_sb.pack(side="left", padx=(4, 0))
        threshold_pkg_var = tk.IntVar(value=self.app.config.get("threshold_package_percent", 10))
        ttk.Label(thr_row, text=T("threshold_pkg_mode_label", lang)).pack(side="left", padx=(10, 0))
        ttk.Spinbox(thr_row, from_=0, to=100, textvariable=threshold_pkg_var, width=6).pack(side="left", padx=(4, 0))
        alert_enabled_var = tk.BooleanVar(value=self.app.config.get("alert_mode", "once") != "never")
        ttk.Checkbutton(thr_row, text=T("alert_check_label", lang),
                        variable=alert_enabled_var).pack(side="left", padx=(12, 0))

        # daily-spend — same two-line pattern
        ttk.Label(scroll_frame, text=T("spend_line_label", lang)).pack(anchor="w", pady=(0, 2))
        spend_row = ttk.Frame(scroll_frame); spend_row.pack(fill="x", padx=(16, 0), pady=(0, 8))
        daily_spend_yuan_var = tk.DoubleVar(value=self.app.config.get("daily_spend_line_yuan", 20))
        ttk.Label(spend_row, text=T("threshold_mode_label", lang)).pack(side="left")
        ttk.Spinbox(spend_row, from_=0.0, to=10000.0, increment=1.0, textvariable=daily_spend_yuan_var, width=6).pack(side="left", padx=(4, 0))
        daily_spend_pct_var = tk.IntVar(value=self.app.config.get("daily_spend_line_percent", 10))
        ttk.Label(spend_row, text=T("threshold_pkg_mode_label", lang)).pack(side="left", padx=(10, 0))
        ttk.Spinbox(spend_row, from_=0, to=100, textvariable=daily_spend_pct_var, width=6).pack(side="left", padx=(4, 0))
        spend_alert_var = tk.BooleanVar(value=self.app.config.get("daily_spend_alert_enabled", False))
        ttk.Checkbutton(spend_row, text=T("spend_check_label", lang),
                        variable=spend_alert_var).pack(side="left", padx=(12, 0))

        api_alert_var = tk.BooleanVar(value=self.app.config.get("api_alert_enabled", True))
        peak_valley_var = tk.BooleanVar(value=self.app.config.get("peak_valley_alert_enabled", False))
        # API status-change + DeepSeek peak/valley reminder on the same row
        alert2_row = ttk.Frame(scroll_frame); alert2_row.pack(fill="x", pady=(0, 8))
        ttk.Checkbutton(alert2_row, text=T("api_alert_label", lang),
                        variable=api_alert_var).pack(side="left")
        ttk.Checkbutton(alert2_row, text=T("peak_valley_alert_label", lang),
                        variable=peak_valley_var).pack(side="left", padx=(16, 0))
        ttk.Separator(scroll_frame, orient="horizontal").pack(fill="x", pady=5)

        # theme — one line: 托盘图标主题：[combo] [ ]图标描边 ; preview + custom below
        THEME_KEYS = ["default","contrast","bright","dark_mode","mono","custom"]
        THEME_OPTS = ["theme_default","theme_contrast","theme_bright","theme_dark_mode","theme_mono","theme_custom"]
        theme_disp = [T(k, lang) for k in THEME_OPTS]
        STATE_KEYS = ("ok", "low", "fast", "degraded", "nodata")
        if lang=="zh":
            PREVIEW_LABELS={"ok":T("preview_ok",lang),"low":T("preview_low",lang),"fast":T("preview_fast",lang),"degraded":T("preview_degraded",lang),"nodata":T("preview_nodata",lang)}
            CUSTOM_LABELS=PREVIEW_LABELS
        else:
            PREVIEW_LABELS={"ok":"OK","low":"Low","fast":"Fast","degraded":"Deg","nodata":"..."}
            CUSTOM_LABELS={"ok":"OK","low":"Low","fast":"Fast","degraded":"Degraded","nodata":"No Data"}
        cur_theme=self.app.config.get("theme","default")
        cur_idx=THEME_KEYS.index(cur_theme) if cur_theme in THEME_KEYS else 0
        theme_row=ttk.Frame(scroll_frame); theme_row.pack(fill="x", pady=(0, 4))
        ttk.Label(theme_row, text=T("theme_label", lang)).pack(side="left")
        theme_var=tk.StringVar(value=theme_disp[cur_idx])
        theme_combo=ttk.Combobox(theme_row, textvariable=theme_var, values=theme_disp, state="readonly", width=14)
        theme_combo.pack(side="left", padx=(6, 0))
        stroke_var=tk.BooleanVar(value=self.app.config.get("icon_stroke",True))
        ttk.Checkbutton(theme_row, text=T("icon_stroke_label", lang), variable=stroke_var).pack(side="left", padx=(16, 0))
        # color preview swatches (5 states), directly under the combo row
        preview_frame=ttk.Frame(scroll_frame); preview_frame.pack(fill="x", pady=(4,2))
        color_labels={}
        def _tk_color(rgba): return "#{:02x}{:02x}{:02x}".format(rgba[0], rgba[1], rgba[2])
        for i,k in enumerate(STATE_KEYS):
            c=THEMES["default"][k]; hx="#{:02x}{:02x}{:02x}".format(*c[:3])
            lbl=tk.Label(preview_frame, text=PREVIEW_LABELS[k], bg=hx, fg=_tk_color(_text_color(c)), font=("Segoe UI",8,"bold"), width=6, height=1, relief="ridge")
            lbl.pack(side="left", padx=(0 if i==0 else 3,0)); color_labels[k]=lbl
        def _refresh_preview(*_a):
            idx=theme_disp.index(theme_var.get()) if theme_var.get() in theme_disp else 0
            tk_theme=THEME_KEYS[idx]; colors=THEMES.get(tk_theme, THEMES["default"])
            for k,lbl in color_labels.items():
                c=colors[k]; hx="#{:02x}{:02x}{:02x}".format(*c[:3])
                lbl.configure(background=hx, foreground=_tk_color(_text_color(c)))
        theme_var.trace_add("write", _refresh_preview); _refresh_preview()
        # custom hex inputs: placed right under the swatches, 3 per row (5 states → 3+2)
        custom_frame=ttk.Frame(scroll_frame); custom_vars={}
        _grid = [(r, c) for r in range(2) for c in range(3)]
        for i, k in enumerate(STATE_KEYS):
            r, cidx = _grid[i]
            row=ttk.Frame(custom_frame); row.grid(row=r, column=cidx, sticky="w", padx=(0, 10), pady=(0,3))
            ttk.Label(row, text=CUSTOM_LABELS[k], width=6).pack(side="left")
            v=tk.StringVar(); custom_vars[k]=v
            ttk.Label(row, text="#", foreground="gray").pack(side="left")
            ttk.Entry(row, textvariable=v, width=7).pack(side="left")
        def _on_theme(*_a):
            idx=theme_disp.index(theme_var.get()) if theme_var.get() in theme_disp else 0
            tk_theme=THEME_KEYS[idx]
            if tk_theme=="custom":
                cols=THEMES["default"]
                for k,v in custom_vars.items(): v.set(f"{cols[k][0]:02x}{cols[k][1]:02x}{cols[k][2]:02x}")
                custom_frame.pack(fill="x", pady=(4,6), after=preview_frame)
            else: custom_frame.pack_forget()
        def _on_custom(*_a):
            for k,v in custom_vars.items():
                val=v.get().strip()
                if len(val)==6:
                    try:
                        lbl=color_labels.get(k)
                        if lbl: lbl.configure(background=f"#{val}", foreground=_tk_color(_hex_to_rgba(val)))
                    except: pass
        for v in custom_vars.values(): v.trace_add("write", _on_custom)
        theme_var.trace_add("write", _on_theme)
        if cur_theme=="custom":
            saved=self.app.config.get("icon_colors",{})
            cols=THEMES["default"]
            for k,v in custom_vars.items(): v.set(saved.get(k, f"{cols[k][0]:02x}{cols[k][1]:02x}{cols[k][2]:02x}"))
            custom_frame.pack(fill="x", pady=(4,6), after=preview_frame)
        ttk.Separator(scroll_frame, orient="horizontal").pack(fill="x", pady=5)

        # language — one line
        lang_row=ttk.Frame(scroll_frame); lang_row.pack(fill="x", pady=(0, 8))
        ttk.Label(lang_row, text=T("language_label", lang)).pack(side="left")
        LANG_OPTIONS={"中文":"zh","English":"en"}; LANG_DISPLAY=list(LANG_OPTIONS.keys())
        cur_lang_disp={v:k for k,v in LANG_OPTIONS.items()}.get(self.app.config.get("language","zh"),"中文")
        lang_var=tk.StringVar(value=cur_lang_disp)
        lang_combo=ttk.Combobox(lang_row, textvariable=lang_var, values=LANG_DISPLAY, state="readonly", width=14)
        lang_combo.pack(side="left", padx=(6, 0))
        from src.core.app_state import get_auto_start_state, set_auto_start
        auto_var=tk.BooleanVar(value=self.app.config.get("auto_start",False) or get_auto_start_state())
        rain_var=tk.BooleanVar(value=self.app.config.get("rainmeter_enabled", True))
        # auto-start / rainmeter each on their own row
        ttk.Checkbutton(scroll_frame, text=T("auto_start_label", lang),
                        variable=auto_var).pack(anchor="w", pady=(0, 8))
        ttk.Checkbutton(scroll_frame, text=T("rainmeter_label", lang),
                        variable=rain_var).pack(anchor="w", pady=(0, 8))

        # retention — one line
        ret_row=ttk.Frame(scroll_frame); ret_row.pack(fill="x", pady=(0, 8))
        ttk.Label(ret_row, text=T("retention_label", lang)).pack(side="left")
        retention_var=tk.IntVar(value=self.app.config.get("retention_days",180))
        retention_sb=ttk.Spinbox(ret_row, from_=1, to=3650, textvariable=retention_var, width=8)
        retention_sb.pack(side="left", padx=(6, 0))
        # open the runtime log file directly: notepad.exe launched detached (no shell
        # association lookup, no "choose app" dialog; Popen returns instantly so
        # the UI thread is never blocked)
        def _open_log():
            import os, subprocess
            from src.core.config import log as _log
            from src.core.paths import LOG_FILE, CONFIG_DIR
            path = str(LOG_FILE)
            try:
                CONFIG_DIR.mkdir(parents=True, exist_ok=True)
                if not LOG_FILE.exists():
                    LOG_FILE.write_text("", encoding="utf-8")
                subprocess.Popen(["notepad.exe", path])
            except Exception as e:
                _log(f"Open log failed: {e}")
                try:
                    os.startfile(path)
                except Exception as e2:
                    _log(f"Open log fallback failed: {e2}")
        tk.Label(ret_row, text=T("open_log_label", lang), foreground="#1a5fb4",
                 cursor="hand2").pack(side="left", padx=(12, 0), pady=(0, 2))
        ret_row.winfo_children()[-1].bind("<Button-1>", lambda e: _open_log())

        # export path — one line
        exp_row=ttk.Frame(scroll_frame); exp_row.pack(fill="x", pady=(0, 8))
        ttk.Label(exp_row, text=T("export_label", lang)).pack(side="left")
        export_var=tk.StringVar(value=self.app.config.get("export_path",""))
        export_entry=ttk.Entry(exp_row, textvariable=export_var); export_entry.pack(side="left", fill="x", expand=True, padx=(6, 0))
        ttk.Button(exp_row, text=T("export_browse", lang), command=lambda: export_var.set(filedialog.askdirectory() or export_var.get())).pack(side="left", padx=(4,0))
        proxy_row = ttk.Frame(scroll_frame); proxy_row.pack(fill="x", pady=(0, 8))
        proxy_enabled_var=tk.BooleanVar(value=self.app.config.get("proxy_enabled",False))
        ttk.Checkbutton(proxy_row, text=T("proxy_enable", lang), variable=proxy_enabled_var).pack(side="left")
        proxy_var=tk.StringVar(value=self.app.config.get("http_proxy",""))
        proxy_entry=ttk.Entry(proxy_row, textvariable=proxy_var); proxy_entry.pack(side="left", fill="x", expand=True, padx=(6, 0))
        placeholder=T("proxy_placeholder", lang)
        def _on_focus_in(e):
            if proxy_var.get()=="": proxy_entry.configure(foreground="black")
        def _on_focus_out(e):
            if proxy_var.get()=="": proxy_var.set(placeholder); proxy_entry.configure(foreground="gray")
            else: proxy_entry.configure(foreground="black")
        def _toggle_proxy(*_a):
            if proxy_enabled_var.get():
                proxy_entry.configure(state="normal")
                if proxy_var.get() in ("", placeholder): proxy_var.set("")
            else:
                proxy_entry.configure(state="disabled")
                if proxy_var.get()=="": proxy_var.set(placeholder); proxy_entry.configure(foreground="gray")
        proxy_enabled_var.trace_add("write", _toggle_proxy)
        if proxy_var.get()=="": proxy_var.set(placeholder); proxy_entry.configure(foreground="gray")
        if not proxy_enabled_var.get(): proxy_entry.configure(state="disabled")
        proxy_entry.bind("<FocusIn>", _on_focus_in); proxy_entry.bind("<FocusOut>", _on_focus_out)
        _no_scroll=lambda e:"break"
        for w in (interval_sb, threshold_sb, theme_combo, lang_combo, retention_sb): w.bind("<MouseWheel>", _no_scroll)
        ttk.Separator(scroll_frame, orient="horizontal").pack(fill="x", pady=(12,8))
        def _make_link(parent, text, url):
            import webbrowser
            lbl = tk.Label(parent, text=text, foreground="#1a5fb4", cursor="hand2")
            lbl.bind("<Button-1>", lambda e: webbrowser.open(url))
            return lbl
        ver_row = ttk.Frame(scroll_frame); ver_row.pack(fill="x")
        ttk.Label(ver_row, text="v1.2.7_260528",
                  foreground="gray").pack(side="left")
        _make_link(ver_row, "GitHub",
                   "https://github.com/SrtaEstrella/DeepSeekBalanceMonitor").pack(side="left", padx=(10, 0))

        by_frame = tk.Frame(scroll_frame)
        by_frame.pack(anchor="w", pady=(2, 0))
        tk.Label(by_frame, text="by ", foreground="gray").pack(side="left")
        _make_link(by_frame, "@SrtaEstrella",
                   "https://github.com/SrtaEstrella").pack(side="left")
        tk.Label(by_frame, text=" (RedNote ", foreground="gray").pack(side="left")
        _make_link(by_frame, "@Estella_han",
                   "https://www.xiaohongshu.com/user/profile/62bc32b1000000001b026f6d").pack(side="left")
        tk.Label(by_frame, text=")", foreground="gray").pack(side="left")

        contrib_frame = tk.Frame(scroll_frame)
        contrib_frame.pack(anchor="w", pady=(2, 0))
        tk.Label(contrib_frame, text="Contributors: ", foreground="gray").pack(side="left")
        _make_link(contrib_frame, "@wenyinos",
                   "https://github.com/wenyinos").pack(side="left")
        tk.Label(contrib_frame, text=" ", foreground="gray", font=("Segoe UI", 8)).pack(side="left")
        _make_link(contrib_frame, "@CHW0n9",
                   "https://github.com/CHW0n9").pack(side="left")

        # --- Dirty tracking ---
        def _mark_dirty(*_a):
            self._dirty = True
        for v in [interval_var, fetch_mode_var, threshold_var, alert_enabled_var, threshold_pkg_var,
                  daily_spend_yuan_var, daily_spend_pct_var, spend_alert_var,
                  api_alert_var, peak_valley_var, rain_var, theme_var,
                  lang_var, auto_var, retention_var, proxy_enabled_var, proxy_var]:
            try:
                v.trace_add("write", _mark_dirty)
            except Exception:
                pass
        for v in custom_vars.values():
            try:
                v.trace_add("write", _mark_dirty)
            except Exception:
                pass
        def _on_input_change(_e=None):
            self._dirty = True
        for w in scroll_frame.winfo_children():
            try:
                if isinstance(w, tk.Entry):
                    w.bind("<KeyRelease>", _on_input_change)
            except Exception:
                pass
        # reset dirty after all initialization traces have fired
        self._dirty = False

                # buttons
        btn_frame=ttk.Frame(self); btn_frame.pack(fill="x", padx=10, pady=10)

        def _do_save():
            """Save settings without closing window. Returns True on success.
            Preferred API is managed on the Manage tab — not touched here."""
            try:
                interval=int(interval_var.get())
                threshold=float(threshold_var.get())
                retention=int(retention_var.get())
            except Exception:
                return False
            if not (1<=interval<=1440): return False
            if not (0<=threshold<=10000): return False
            if not (1<=retention<=3650): return False
            if self.app.config.get("preferred_api_id"):
                try:
                    from src.core.secure_settings import read_api_key_for_id, store_api_key
                    k = read_api_key_for_id(self.app.config["preferred_api_id"])
                    if k:
                        store_api_key(k)
                        self.app.config["api_key"] = k
                    else:
                        self.app.config["api_key"] = ""
                except Exception as e:
                    log(f"Settings save: credential sync failed: {e}")
            self.app.config["interval_minutes"]=interval
            self.app.config["fetch_mode"]=FETCH_MAP.get(fetch_mode_var.get(), "parallel")
            self.app.config["threshold_yuan"]=threshold
            self.app.config["threshold_package_percent"]=threshold_pkg_var.get()
            self.app.config["daily_spend_line_yuan"]=daily_spend_yuan_var.get()
            self.app.config["daily_spend_line_percent"]=daily_spend_pct_var.get()
            self.app.config["daily_spend_alert_enabled"]=spend_alert_var.get()
            new_lang = LANG_OPTIONS.get(lang_var.get(), "zh")
            lang_changed = (new_lang != self.app.lang)
            self.app.config["language"] = new_lang
            self.app.config["auto_start"]=auto_var.get()
            self.app.config["alert_enabled"] = alert_enabled_var.get()
            # binary → legacy tri-state for mac/webview compat: on=once, off=never
            self.app.config["alert_mode"] = "once" if alert_enabled_var.get() else "never"
            self.app.config["api_alert_enabled"]=api_alert_var.get()
            self.app.config["peak_valley_alert_enabled"]=peak_valley_var.get()
            self.app.config["rainmeter_enabled"]=rain_var.get()
            self.app.config["retention_days"]=retention
            self.app.config["export_path"]=export_var.get()
            self.app.config["proxy_enabled"]=proxy_enabled_var.get()
            proxy_val=proxy_var.get().strip()
            new_lang=LANG_OPTIONS.get(lang_var.get(),"zh")
            if proxy_val==T("proxy_placeholder", new_lang): proxy_val=""
            self.app.config["http_proxy"]=proxy_val
            from src.platforms.deepseek import install_proxy
            if self.app.config["proxy_enabled"] and self.app.config["http_proxy"]: install_proxy(self.app.config["http_proxy"])
            else: install_proxy("")
            t_idx=theme_disp.index(theme_var.get()) if theme_var.get() in theme_disp else 0
            t_key=THEME_KEYS[t_idx]
            self.app.config["theme"]=t_key
            if t_key=="custom": self.app.config["icon_colors"]={k:v.get().strip() for k,v in custom_vars.items()}
            else: self.app.config["icon_colors"]={}
            self.app.config["icon_stroke"]=stroke_var.get()
            set_auto_start(self.app.config["auto_start"])
            save_config(self.app.config)
            # widgets can't re-i18n live — tear down the main window on language
            # change so the next open() rebuilds every tab in the new language
            if lang_changed:
                try:
                    mw = getattr(self.app, "_main_window", None)
                    if mw is not None and hasattr(mw, "close_for_rebuild"):
                        mw.close_for_rebuild()
                        self.app._main_window = None
                except Exception:
                    pass
            # Settings changed (interval_minutes etc.) — restart the automatic
            # poll loop so the new value applies and polling does NOT silently
            # stop. A bare cancel_timer() cancels the only pending poll event
            # and nothing re-arms the self-chaining loop until a manual check;
            # restart_polling keeps cancellation and re-arming together.
            self.app.restart_polling()
            # load new preferred API's cached data into app state
            pref_api_id = self.app.config.get("preferred_api_id", "")
            cached = getattr(self.app, "_api_cache", {}).get(pref_api_id, {})
            with self.app._lock:
                if "balances" in cached:
                    self.app.balances = cached["balances"]
                    self.app.package_data = cached.get("package_data")
                    self.app.error = cached.get("error")
                    self.app.last_check = cached.get("last_check")
                elif "package_data" in cached:
                    self.app.package_data = cached["package_data"]
                    self.app.balances = {}
                    self.app.error = cached.get("error")
                    self.app.last_check = cached.get("last_check")
                else:
                    self.app.balances = {}
                    self.app.package_data = None
                    self.app.error = None
            if self.app.icon:
                from src.ui.icon_renderer import create_icon_image
                self.app.icon.title = self.app.balance_tooltip()
                self.app.icon.icon=create_icon_image(self.app)
                self.app.icon.menu=self.app._rebuild_menu()
            log("Settings saved (embedded)")
            self._dirty = False
            if self.on_save: self.on_save()
            return True

        def on_save():
            if _do_save():
                try:
                    mw = getattr(self.app, "_main_window", None)
                    if mw and hasattr(mw, "hide"):
                        mw.hide()
                except Exception:
                    pass

        ttk.Button(btn_frame, text=T("save", lang), command=on_save).pack(side="right", padx=(5,0))
                # expose nested save routine for class methods (check_unsaved)
        self._do_save_impl = _do_save
        # keep refs
        self._lang_var=lang_var

    def refresh(self, follow_preferred=False):
        pass  # preferred is managed on the Manage tab; nothing to refresh here

    def reload_from_config(self):
        """Discard edits: rebuild all widgets from last-saved config."""
        try:
            self.app.config = load_config()
        except Exception:
            pass
        for w in self.winfo_children():
            w.destroy()
        self._build()
        self._dirty = False

    def on_show(self):
        pass  # nothing dynamic to refresh; preferred lives on the Manage tab

    def check_unsaved(self):
        """Check for unsaved changes. Returns True if safe to proceed (after save or discard)."""
        if not self._dirty:
            return True
        lang = self.app.lang
        from tkinter import messagebox
        save = messagebox.askyesno(T("warn_title", lang), T("unsaved_confirm", lang), parent=self.winfo_toplevel())
        if save:
            try:
                self._do_save_impl()
            except Exception as e:
                from src.core.config import log
                log(f"check_unsaved save failed: {e}")
        else:
            self.reload_from_config()
        return True
