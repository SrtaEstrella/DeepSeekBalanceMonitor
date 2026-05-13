"""
Settings dialog — tkinter window for configuring API key, interval, threshold,
language, auto-start, and alert toggle.
"""
import threading


def open_settings(app):
    """Open the settings dialog.  If already open, bring it to the foreground."""
    if app._settings_open and app._settings_window is not None:
        try:
            app._settings_window.deiconify()
            app._settings_window.lift()
            app._settings_window.after(50, app._settings_window.focus_force)
        except Exception:
            pass
        return
    app._settings_open = True

    def _dialog():
        import os
        import sys
        import tkinter as tk
        from tkinter import ttk, messagebox, filedialog

        from src.config import T, save_config, log

        lang = app.lang

        if app._tk_root is None:
            app._tk_root = tk.Tk()
            app._tk_root.withdraw()
        top = app._tk_root
        root = tk.Toplevel(top)
        app._settings_window = root

        def _cleanup():
            app._settings_open = False
            app._settings_window = None
            root.destroy()

        root.protocol("WM_DELETE_WINDOW", _cleanup)

        try:
            if getattr(sys, "frozen", False):
                icon_path = os.path.join(sys._MEIPASS, "app.ico")
            else:
                icon_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                         "assets", "app.ico")
            if os.path.isfile(icon_path):
                root.iconbitmap(icon_path)
        except Exception:
            pass

        root.title(T("settings", lang).rstrip("…"))
        root.geometry("580x520")
        root.resizable(True, True)
        root.minsize(480, 400)
        root.update_idletasks()
        sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
        w, h = root.winfo_width(), root.winfo_height()
        root.geometry(f"+{(sw - w) // 2}+{(sh - h) // 2}")

        # Remove the maximise button — a settings dialog never needs it.
        if sys.platform == "win32":
            try:
                import ctypes
                hwnd = ctypes.windll.user32.GetParent(root.winfo_id())
                GWL_STYLE = -16
                WS_MAXIMIZEBOX = 0x00010000
                style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_STYLE)
                ctypes.windll.user32.SetWindowLongW(hwnd, GWL_STYLE,
                                                    style & ~WS_MAXIMIZEBOX)
            except Exception:
                pass

        # Settings window can launch without foreground activation from a
        # tray-icon callback — force focus so minimise / close respond.
        root.after(50, root.focus_force)

        # Fixed footer MUST pack before the expanding canvas area
        footer = ttk.Frame(root, padding=(20, 10, 20, 10))
        footer.pack(fill="x", side="bottom")

        # Scrollable canvas area takes remaining space
        outer = ttk.Frame(root)
        outer.pack(fill="both", expand=True)

        canvas = tk.Canvas(outer, borderwidth=0, highlightthickness=0)
        scrollbar = tk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        scroll_frame = ttk.Frame(canvas)

        # canvas.bbox("all") does NOT include create_window items on most
        # tk builds — use the frame's actual requested size instead.
        def _update_scrollregion(*_args):
            canvas.configure(
                scrollregion=(0, 0,
                              scroll_frame.winfo_reqwidth(),
                              scroll_frame.winfo_reqheight()))

        scroll_frame.bind("<Configure>", _update_scrollregion)

        canvas_window = canvas.create_window((0, 0), window=scroll_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        def _on_canvas_resize(event):
            canvas.itemconfig(canvas_window, width=event.width)
        canvas.bind("<Configure>", _on_canvas_resize)

        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        canvas.bind("<Enter>", lambda e: canvas.bind_all("<MouseWheel>", _on_mousewheel))
        canvas.bind("<Leave>", lambda e: canvas.unbind_all("<MouseWheel>"))

        scrollbar.pack(side="right", fill="y", pady=(20, 0), padx=(0, 4))
        canvas.pack(side="left", fill="both", expand=True, padx=(20, 0), pady=(20, 0))

        # === Settings widgets inside scroll_frame ===

        ttk.Label(scroll_frame, text=T("api_key_label", lang)).pack(anchor="w")
        api_var = tk.StringVar(value=app.config.get("api_key", ""))
        api_entry = ttk.Entry(scroll_frame, textvariable=api_var, show="•", width=36)
        api_entry.pack(anchor="w", pady=(0, 2))
        show_var = tk.BooleanVar(value=False)

        def _toggle_key_visibility(*_args):
            if show_var.get():
                # ttk.Entry may ignore show='' via .config(); go through Tcl.
                api_entry.tk.call(api_entry._w, "configure", "-show", "")
            else:
                api_entry.configure(show="•")

        show_var.trace_add("write", _toggle_key_visibility)

        ttk.Checkbutton(scroll_frame, text=T("show_key", lang), variable=show_var).pack(
            anchor="w", pady=(0, 8))

        ttk.Separator(scroll_frame, orient="horizontal").pack(fill="x", pady=5)

        ttk.Label(scroll_frame, text=T("interval_label", lang)).pack(anchor="w")
        interval_var = tk.IntVar(value=app.config.get("interval_minutes", 10))
        ifr = ttk.Frame(scroll_frame)
        ifr.pack(fill="x", pady=(0, 8))
        interval_sb = ttk.Spinbox(ifr, from_=1, to=1440, textvariable=interval_var, width=8)
        interval_sb.pack(side="left")
        ttk.Label(ifr, text=T("interval_hint", lang)).pack(side="left")

        ttk.Label(scroll_frame, text=T("threshold_label", lang)).pack(anchor="w")
        threshold_var = tk.DoubleVar(value=app.config.get("threshold_yuan", 1.0))
        tfr = ttk.Frame(scroll_frame)
        tfr.pack(fill="x", pady=(0, 8))
        threshold_sb = ttk.Spinbox(tfr, from_=0.0, to=10000.0, increment=0.5,
                                   textvariable=threshold_var, width=8)
        threshold_sb.pack(side="left")
        ttk.Label(tfr, text=T("threshold_hint", lang)).pack(side="left")

        # alert_mode_map = {T("alert_never", lang): "never", T("alert_always", lang): "always", T("alert_once", lang): "once"}
        alert_mode_map = {
            T("alert_never", lang): "never", T("alert_always", lang): "always", T("alert_once", lang): "once",
        }
        alert_mode_display = list(alert_mode_map.keys())
        cur_alert_display = {v: k for k, v in alert_mode_map.items()}.get(
            app.config.get("alert_mode", "always"), T("alert_always", lang))
        ttk.Label(scroll_frame, text=T("alert_mode_label", lang)).pack(anchor="w")
        alert_mode_var = tk.StringVar(value=cur_alert_display)
        alert_mode_combo = ttk.Combobox(scroll_frame, textvariable=alert_mode_var,
                                        values=alert_mode_display, state="readonly", width=14)
        alert_mode_combo.pack(anchor="w", pady=(0, 8))

        api_alert_var = tk.BooleanVar(
            value=app.config.get("api_alert_enabled", True))
        ttk.Checkbutton(scroll_frame, text=T("api_alert_label", lang),
                        variable=api_alert_var).pack(anchor="w", pady=(0, 8))

        rainmeter_var = tk.BooleanVar(value=app.config.get("rainmeter_enabled", True))
        ttk.Checkbutton(scroll_frame, text=T("rainmeter_label", lang),
                        variable=rainmeter_var).pack(anchor="w", pady=(0, 8))

        ttk.Separator(scroll_frame, orient="horizontal").pack(fill="x", pady=5)
        ttk.Label(scroll_frame, text=T("theme_label", lang)).pack(anchor="w")

        from src.icon_renderer import THEMES, _hex_to_rgba, _text_color, create_icon_image

        THEME_KEYS = ["default", "contrast", "bright", "dark_mode", "mono", "custom"]
        THEME_OPTS = ["theme_default", "theme_contrast", "theme_bright",
                      "theme_dark_mode", "theme_mono", "theme_custom"]
        theme_display = [T(k, lang) for k in THEME_OPTS]

        if lang == "zh":
            PREVIEW_LABELS = {"ok": "正常", "low": "低额", "degraded": "异常", "nodata": "等待"}
            CUSTOM_LABELS = {"ok": "正常", "low": "低额", "degraded": "异常", "nodata": "等待"}
        else:
            PREVIEW_LABELS = {"ok": "OK", "low": "Low", "degraded": "Deg", "nodata": "..."}
            CUSTOM_LABELS = {"ok": "OK", "low": "Low", "degraded": "Degraded", "nodata": "No Data"}

        cur_theme = app.config.get("theme", "default")
        cur_theme_idx = THEME_KEYS.index(cur_theme) if cur_theme in THEME_KEYS else 0

        # Color preview row - goes ABOVE the dropdown
        preview_frame = ttk.Frame(scroll_frame)
        preview_frame.pack(fill="x", pady=(4, 6))
        color_labels = {}

        def _refresh_preview(*_args):
            idx = theme_display.index(theme_var.get()) if theme_var.get() in theme_display else 0
            tk_theme = THEME_KEYS[idx]
            colors = THEMES.get(tk_theme, THEMES["default"])
            for k, lbl in color_labels.items():
                c = colors[k]
                hex_color = f"#{c[0]:02x}{c[1]:02x}{c[2]:02x}"
                tc = _text_color(c)
                lbl.configure(background=hex_color, foreground=_tk_color(tc))

        def _tk_color(rgba):
            return f"#{rgba[0]:02x}{rgba[1]:02x}{rgba[2]:02x}"

        for i, k in enumerate(("ok", "low", "degraded", "nodata")):
            c = THEMES["default"][k]
            hex_color = f"#{c[0]:02x}{c[1]:02x}{c[2]:02x}"
            tc = _text_color(c)
            lbl = tk.Label(preview_frame, text=PREVIEW_LABELS[k], bg=hex_color,
                           fg=_tk_color(tc), font=("Segoe UI", 8, "bold"),
                           width=6, height=1, relief="ridge")
            lbl.pack(side="left", padx=(0 if i == 0 else 3, 0))
            color_labels[k] = lbl

        theme_var = tk.StringVar(value=theme_display[cur_theme_idx])
        theme_var.trace_add("write", _refresh_preview)
        _refresh_preview()

        theme_combo = ttk.Combobox(scroll_frame, textvariable=theme_var,
                                   values=theme_display, state="readonly", width=14)
        theme_combo.pack(anchor="w", pady=(0, 4))

        stroke_var = tk.BooleanVar(value=app.config.get("icon_stroke", True))
        ttk.Checkbutton(scroll_frame, text=T("icon_stroke_label", lang),
                        variable=stroke_var).pack(anchor="w", pady=(0, 6))

        # Custom color inputs (hidden unless "custom" selected)
        custom_frame = ttk.Frame(scroll_frame)
        custom_vars = {}
        for k in ("ok", "low", "degraded", "nodata"):
            row = ttk.Frame(custom_frame)
            row.pack(fill="x", pady=(0, 3))
            ttk.Label(row, text=CUSTOM_LABELS[k], width=7).pack(side="left")
            v = tk.StringVar()
            custom_vars[k] = v
            ttk.Label(row, text="#", foreground="gray").pack(side="left")
            e = ttk.Entry(row, textvariable=v, width=8)
            e.pack(side="left")

        def _on_theme_change(*_args):
            idx = theme_display.index(theme_var.get()) if theme_var.get() in theme_display else 0
            tk_theme = THEME_KEYS[idx]
            if tk_theme == "custom":
                colors = THEMES["default"]
                for k, v in custom_vars.items():
                    c = colors[k]
                    v.set(f"{c[0]:02x}{c[1]:02x}{c[2]:02x}")
                custom_frame.pack(fill="x", pady=(0, 6), after=theme_combo)
            else:
                custom_frame.pack_forget()

        def _on_custom_change(*_args):
            for k, v in custom_vars.items():
                val = v.get().strip()
                if len(val) == 6:
                    try:
                        c = _hex_to_rgba(val)
                        lbl = color_labels.get(k)
                        if lbl:
                            hex_color = f"#{val}"
                            tc = _text_color(c)
                            lbl.configure(background=hex_color, foreground=_tk_color(tc))
                    except ValueError:
                        pass

        for v in custom_vars.values():
            v.trace_add("write", _on_custom_change)

        theme_var.trace_add("write", _on_theme_change)

        # Show custom inputs on open if already in custom mode
        if cur_theme == "custom":
            colors = THEMES["default"]
            saved = app.config.get("icon_colors", {})
            for k, v in custom_vars.items():
                v.set(saved.get(k, f"{colors[k][0]:02x}{colors[k][1]:02x}{colors[k][2]:02x}"))
            custom_frame.pack(fill="x", pady=(0, 6), after=theme_combo)

        ttk.Label(scroll_frame, text=T("language_label", lang)).pack(anchor="w", pady=(2, 0))
        LANG_OPTIONS = {"中文": "zh", "English": "en"}
        LANG_DISPLAY = list(LANG_OPTIONS.keys())
        cur_lang_display = {v: k for k, v in LANG_OPTIONS.items()}.get(
            app.config.get("language", "zh"), "中文")
        lang_var = tk.StringVar(value=cur_lang_display)
        lang_combo = ttk.Combobox(scroll_frame, textvariable=lang_var, values=LANG_DISPLAY,
                                  state="readonly", width=14)
        lang_combo.pack(anchor="w", pady=(0, 12))

        from src.app_state import get_auto_start_state, set_auto_start
        auto_start_var = tk.BooleanVar(
            value=app.config.get("auto_start", False) or get_auto_start_state())
        ttk.Checkbutton(scroll_frame, text=T("auto_start_label", lang),
                        variable=auto_start_var).pack(anchor="w", pady=(0, 2))

        ttk.Label(scroll_frame, text=T("retention_label", lang)).pack(anchor="w")
        retention_var = tk.IntVar(value=app.config.get("retention_days", 30))
        rfr = ttk.Frame(scroll_frame)
        rfr.pack(fill="x", pady=(0, 8))
        retention_sb = ttk.Spinbox(rfr, from_=1, to=3650, textvariable=retention_var, width=8)
        retention_sb.pack(side="left")

        ttk.Label(scroll_frame, text=T("export_label", lang)).pack(anchor="w")
        export_frame = ttk.Frame(scroll_frame)
        export_frame.pack(fill="x", pady=(0, 8))
        export_var = tk.StringVar(value=app.config.get("export_path", ""))
        export_entry = ttk.Entry(export_frame, textvariable=export_var)
        export_entry.pack(side="left", fill="x", expand=True)
        ttk.Button(export_frame, text=T("export_browse", lang),
                   command=lambda: export_var.set(
                       filedialog.askdirectory() or export_var.get())
                   ).pack(side="left", padx=(4, 0))

        proxy_enabled_var = tk.BooleanVar(value=app.config.get("proxy_enabled", False))
        ttk.Checkbutton(scroll_frame, text=T("proxy_enable", lang),
                        variable=proxy_enabled_var).pack(anchor="w")

        proxy_var = tk.StringVar(value=app.config.get("http_proxy", ""))
        proxy_entry = ttk.Entry(scroll_frame, textvariable=proxy_var)
        proxy_entry.pack(fill="x", pady=(0, 8))
        placeholder = T("proxy_placeholder", lang)

        def _on_focus_in(e):
            if proxy_var.get() == "":
                proxy_entry.configure(foreground="black")
        def _on_focus_out(e):
            if proxy_var.get() == "":
                proxy_var.set(placeholder)
                proxy_entry.configure(foreground="gray")
            else:
                proxy_entry.configure(foreground="black")

        def _toggle_proxy(*_args):
            if proxy_enabled_var.get():
                proxy_entry.configure(state="normal")
                if proxy_var.get() in ("", placeholder):
                    proxy_var.set("")
            else:
                proxy_entry.configure(state="disabled")
                if proxy_var.get() == "":
                    proxy_var.set(placeholder)
                    proxy_entry.configure(foreground="gray")
        proxy_enabled_var.trace_add("write", _toggle_proxy)

        if proxy_var.get() == "":
            proxy_var.set(placeholder)
            proxy_entry.configure(foreground="gray")
        if not proxy_enabled_var.get():
            proxy_entry.configure(state="disabled")
        proxy_entry.bind("<FocusIn>", _on_focus_in)
        proxy_entry.bind("<FocusOut>", _on_focus_out)

        _no_scroll = lambda e: "break"
        for w in (interval_sb, threshold_sb, alert_mode_combo, theme_combo, lang_combo, retention_sb):
            w.bind("<MouseWheel>", _no_scroll)

        def _open_url(url):
            import webbrowser
            webbrowser.open(url)

        def _make_link(parent, text, url):
            lbl = tk.Label(parent, text=text, foreground="#3C6966", cursor="hand2",
                           font=("Segoe UI", 8, "underline"))
            lbl.bind("<Button-1>", lambda e, u=url: _open_url(u))
            return lbl

        ttk.Separator(scroll_frame, orient="horizontal").pack(fill="x", pady=(12, 8))
        ttk.Label(scroll_frame, text="v1.2.5_260513",
                  foreground="gray").pack(anchor="w")

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
        tk.Label(contrib_frame, text=" ", foreground="gray").pack(side="left")
        _make_link(contrib_frame, "@CHW0n9",
                   "https://github.com/CHW0n9").pack(side="left")

        _make_link(scroll_frame, "github.com/SrtaEstrella/DeepSeekBalanceMonitor",
                   "https://github.com/SrtaEstrella/DeepSeekBalanceMonitor").pack(anchor="w", pady=(2, 0))

        # Force initial scrollregion now that all children are packed.
        # Must happen before the footer's own pack to avoid a zero-height frame.
        scroll_frame.update_idletasks()
        _update_scrollregion()

        # === Fixed footer widgets ===

        btn_frame = ttk.Frame(footer)
        btn_frame.pack(fill="x")

        def on_save():
            key = api_var.get().strip()
            if not key:
                messagebox.showwarning(T("warn_title", lang), T("warn_no_key", lang),
                                       parent=root)
                return

            try:
                interval = int(interval_var.get())
                threshold = float(threshold_var.get())
                retention = int(retention_var.get())
            except (ValueError, tk.TclError):
                messagebox.showwarning(T("warn_title", lang),
                                       T("validate_invalid", lang), parent=root)
                return

            if not (1 <= interval <= 1440):
                messagebox.showwarning(T("warn_title", lang),
                                       T("validate_interval", lang), parent=root)
                return
            if not (0 <= threshold <= 10000):
                messagebox.showwarning(T("warn_title", lang),
                                       T("validate_threshold", lang), parent=root)
                return
            if not (1 <= retention <= 3650):
                messagebox.showwarning(T("warn_title", lang),
                                       T("validate_retention", lang), parent=root)
                return

            app.config["api_key"] = key
            try:
                from src.secure_settings import store_api_key
                store_api_key(key)
            except ImportError:
                pass

            app.config["interval_minutes"] = interval
            app.config["threshold_yuan"] = threshold
            app.config["language"] = LANG_OPTIONS.get(lang_var.get(), "zh")
            app.config["auto_start"] = auto_start_var.get()
            app.config["alert_mode"] = alert_mode_map.get(alert_mode_var.get(), "always")
            app.config["api_alert_enabled"] = api_alert_var.get()
            app.config["rainmeter_enabled"] = rainmeter_var.get()
            app.config["retention_days"] = retention
            app.config["export_path"] = export_var.get()
            app.config["proxy_enabled"] = proxy_enabled_var.get()
            proxy_val = proxy_var.get().strip()
            new_lang = LANG_OPTIONS.get(lang_var.get(), "zh")
            if proxy_val == T("proxy_placeholder", new_lang):
                proxy_val = ""
            app.config["http_proxy"] = proxy_val
            from src.api_client import install_proxy
            if app.config["proxy_enabled"] and app.config["http_proxy"]:
                install_proxy(app.config["http_proxy"])
            else:
                install_proxy("")

            t_idx = theme_display.index(theme_var.get()) if theme_var.get() in theme_display else 0
            if THEME_KEYS[t_idx] == "custom":
                for k, v in custom_vars.items():
                    val = v.get().strip()
                    if len(val) != 6:
                        messagebox.showwarning(T("warn_title", lang),
                                               T("hex_invalid", lang), parent=root)
                        return
                    try:
                        int(val, 16)
                    except ValueError:
                        messagebox.showwarning(T("warn_title", lang),
                                               T("hex_invalid", lang), parent=root)
                        return
            t_key = THEME_KEYS[t_idx]
            app.config["theme"] = t_key
            if t_key == "custom":
                app.config["icon_colors"] = {k: v.get().strip() for k, v in custom_vars.items()}
            else:
                app.config["icon_colors"] = {}
            app.config["icon_stroke"] = stroke_var.get()

            set_auto_start(app.config["auto_start"])
            save_config(app.config)
            app.cancel_timer()
            if app.icon:
                app.icon.icon = create_icon_image(app)
                app.icon.menu = app._rebuild_menu()
            app._trigger_check()
            log("Settings saved")
            _cleanup()

        ttk.Button(btn_frame, text=T("save", lang), command=on_save).pack(
            side="right", padx=(5, 0))
        ttk.Button(btn_frame, text=T("cancel", lang), command=_cleanup).pack(
            side="right")
        root.bind("<Return>", lambda e: on_save())
        root.bind("<Escape>", lambda e: _cleanup())
        api_entry.focus_set()
        top.mainloop()

    _dialog()
