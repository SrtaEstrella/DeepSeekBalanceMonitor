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
            app._settings_window.focus_force()
        except Exception:
            pass
        return
    app._settings_open = True

    def _dialog():
        import os
        import sys
        import tkinter as tk
        from tkinter import ttk, messagebox

        from src.config import T, save_config, log

        lang = app.lang

        root = tk.Tk()
        app._settings_window = root

        def _cleanup():
            app._settings_open = False
            app._settings_window = None
            root.destroy()

        root.protocol("WM_DELETE_WINDOW", _cleanup)

        try:
            if getattr(sys, "frozen", False):
                icon_path = os.path.join(sys._MEIPASS, "app_icon.ico")
            else:
                icon_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                         "app_icon.ico")
            if os.path.isfile(icon_path):
                root.iconbitmap(icon_path)
        except Exception:
            pass

        root.title(T("settings_title", lang))
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

        ALERT_MODES = {"不提醒": "never", "持续提醒": "always", "仅提醒一次": "once"}
        ALERT_MODES_EN = {"Never": "never", "Always": "always", "Once": "once"}
        alert_mode_map = ALERT_MODES if lang == "zh" else ALERT_MODES_EN
        alert_mode_display = list(alert_mode_map.keys())
        cur_alert_display = {v: k for k, v in alert_mode_map.items()}.get(
            app.config.get("alert_mode", "always"), "Always")
        ttk.Label(scroll_frame, text=T("alert_mode_label", lang)).pack(anchor="w")
        alert_mode_var = tk.StringVar(value=cur_alert_display)
        alert_mode_combo = ttk.Combobox(scroll_frame, textvariable=alert_mode_var,
                                        values=alert_mode_display, state="readonly", width=14)
        alert_mode_combo.pack(anchor="w", pady=(0, 8))

        api_alert_var = tk.BooleanVar(
            value=app.config.get("api_alert_enabled", True))
        ttk.Checkbutton(scroll_frame, text=T("api_alert_label", lang),
                        variable=api_alert_var).pack(anchor="w", pady=(0, 8))

        ttk.Label(scroll_frame, text=T("language_label", lang)).pack(anchor="w", pady=(2, 0))
        LANG_OPTIONS = {"中文": "zh", "English": "en"}
        LANG_DISPLAY = list(LANG_OPTIONS.keys())
        cur_lang_display = {v: k for k, v in LANG_OPTIONS.items()}.get(
            app.config.get("language", "zh"), "中文")
        lang_var = tk.StringVar(value=cur_lang_display)
        lang_combo = ttk.Combobox(scroll_frame, textvariable=lang_var, values=LANG_DISPLAY,
                                  state="readonly", width=14)
        lang_combo.pack(anchor="w", pady=(0, 12))

        # Prevent accidental value changes via mousewheel on spinboxes and
        # comboboxes — these are too easy to bump while scrolling the dialog.
        _no_scroll = lambda e: "break"
        for w in (interval_sb, threshold_sb, alert_mode_combo, lang_combo):
            w.bind("<MouseWheel>", _no_scroll)

        from src.app_state import get_auto_start_state, set_auto_start
        auto_start_var = tk.BooleanVar(
            value=app.config.get("auto_start", False) or get_auto_start_state())
        ttk.Checkbutton(scroll_frame, text=T("auto_start_label", lang),
                        variable=auto_start_var).pack(anchor="w", pady=(0, 2))

        ttk.Separator(scroll_frame, orient="horizontal").pack(fill="x", pady=(12, 8))
        ttk.Label(scroll_frame, text="V1.0.1_260508",
                  foreground="gray").pack(anchor="w")
        ttk.Label(scroll_frame, text="GitHub @SrtaEstrella  |  RedNote @Estella_han",
                  foreground="gray").pack(anchor="w", pady=(2, 0))

        # Force initial scrollregion now that all children are packed.
        # Must happen before the footer's own pack to avoid a zero-height frame.
        scroll_frame.update_idletasks()
        _update_scrollregion()

        # === Fixed footer widgets ===

        ttk.Separator(footer, orient="horizontal").pack(fill="x", pady=(0, 8))

        with app._lock:
            last = app.last_check

        if last:
            last_str = last.strftime("%Y-%m-%d %H:%M:%S")
        else:
            last_str = T("not_checked", lang)
        ttk.Label(footer, text=T("last_check", lang) + ": " + last_str,
                  foreground="gray").pack(anchor="w")

        b = app.get_preferred_balance()
        if b:
            code = b["currency"]
            bal_text = T("total_balance", lang) + ": " + f"{b['total_balance']:,.2f} {code}"
        else:
            bal_text = T("not_checked", lang)
        ttk.Label(footer, text=bal_text, foreground="gray").pack(anchor="w", pady=(0, 8))

        btn_frame = ttk.Frame(footer)
        btn_frame.pack(fill="x")

        def on_save():
            from src.tray_app import do_balance_check, make_menu

            key = api_var.get().strip()
            if not key:
                messagebox.showwarning(T("warn_title", lang), T("warn_no_key", lang),
                                       parent=root)
                return
            app.config["api_key"] = key
            app.config["interval_minutes"] = interval_var.get()
            app.config["threshold_yuan"] = threshold_var.get()
            app.config["language"] = LANG_OPTIONS.get(lang_var.get(), "zh")
            app.config["auto_start"] = auto_start_var.get()
            app.config["alert_mode"] = alert_mode_map.get(alert_mode_var.get(), "always")
            app.config["api_alert_enabled"] = api_alert_var.get()
            set_auto_start(app.config["auto_start"])
            save_config(app.config)
            app.cancel_timer()
            # Language may have changed — rebuild the tray menu so it
            # reflects the new locale immediately.
            if app.icon:
                app.icon.menu = make_menu(app)
            threading.Thread(target=do_balance_check, args=(app,), daemon=True).start()
            log("Settings saved")
            _cleanup()

        ttk.Button(btn_frame, text=T("save", lang), command=on_save).pack(
            side="right", padx=(5, 0))
        ttk.Button(btn_frame, text=T("cancel", lang), command=_cleanup).pack(
            side="right")
        root.bind("<Return>", lambda e: on_save())
        root.bind("<Escape>", lambda e: _cleanup())
        api_entry.focus_set()
        root.mainloop()

    _dialog()
