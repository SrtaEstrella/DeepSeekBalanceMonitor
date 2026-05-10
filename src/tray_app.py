"""
Tray application — balance checking loop, notifications, tray menu, and entry point.
"""
import sys
import threading
import webbrowser
from datetime import datetime

import pystray

from src.config import T, log, CONFIG_DIR, APP_NAME, APP_ID
from src.api_client import fetch_balance, fetch_service_status, install_proxy
from src.icon_renderer import create_icon_image
from src.app_state import AppState
from src.storage import save_balance_record, prune_old_data

_DEMO = {
    "balances": {"CNY": {"total_balance": 42.50, "topped_up_balance": 40.00, "granted_balance": 2.50}},
    "service_status": {"indicator": "none", "api_operational": True},
}


# pystray on Windows uses Shell_NotifyIconA whose NOTIFYICONDATA.szTip / szInfo
# fields are ANSI (code-page dependent).  On Chinese Windows the system code page
# is GBK which handles Chinese natively — but any character outside the current
# code page will raise UnicodeEncodeError at the ctypes boundary.
# We only sanitise the *exception message* (which may contain arbitrary Unicode
# from API error bodies) before it reaches a tooltip or notification.
def _sanitise_error(text):
    """Strip characters that cannot be encoded in the system ANSI code page."""
    if text is None:
        return ""
    try:
        text.encode("mbcs")
        return text
    except (UnicodeEncodeError, LookupError):
        return text.encode("mbcs", errors="replace").decode("mbcs")


# --- Balance Check --------------------------------------------------

def do_balance_check(app: AppState):
    if app.demo_mode:
        with app._lock:
            app.balances = _DEMO["balances"]
            app.service_status = _DEMO["service_status"]
            app.error = None
            app.last_check = datetime.now()
        if app.icon:
            app.icon.title = app.balance_tooltip()
            app.icon.icon = create_icon_image(app)
        interval_sec = int(app.config.get("interval_minutes", 10)) * 60
        app.schedule_next_check(lambda: do_balance_check(app), interval_sec)
        return

    try:
        status = fetch_service_status()
    except Exception:
        status = None
    with app._lock:
        app.service_status = status

    api_key = app.config.get("api_key", "").strip()
    if not api_key:
        with app._lock:
            app.error = T("error_no_key", app.lang)
            app.balances = {}
    else:
        try:
            data = fetch_balance(api_key)
            with app._lock:
                app.balances = data["all_balances"]
                app.error = None
                app.last_check = datetime.now()
            b = app.get_preferred_balance()
            if b:
                log(f"Balance OK: {b['total_balance']:.2f} {b['currency']}")
            ss = app.service_status
            s_indicator = ss.get("indicator") if ss else None
            for code, bal in data["all_balances"].items():
                save_balance_record(code, bal["total_balance"],
                                    bal["topped_up_balance"],
                                    bal["granted_balance"],
                                    service_status=s_indicator)
        except Exception as e:
            raw = str(e).split("\n")[0]
            # If the API is known to be degraded, a failed balance
            # check is expected — keep the previous data in place.
            api_degraded = status and not status.get("api_operational", True)
            if api_degraded:
                log(f"Balance check failed (API degraded, keeping previous data): {e}")
            else:
                with app._lock:
                    app.error = _sanitise_error(raw)
                    app.balances = {}
                log(f"Check failed: {e}")

    if app.icon:
        app.icon.title = app.balance_tooltip()
        app.icon.icon = create_icon_image(app)

    if app.should_alert():
        notify_user(app)

    if app.config.get("api_alert_enabled", True):
        transition = app.check_api_status_alert()
        if transition:
            notify_api_status(app, transition)

    interval_sec = int(app.config.get("interval_minutes", 10)) * 60
    app.schedule_next_check(lambda: do_balance_check(app), interval_sec)


# --- Low-Balance Notification ---------------------------------------

def notify_user(app: AppState):
    b = app.get_preferred_balance()
    if b is None:
        return
    lang = app.lang
    t = app.config.get("threshold_yuan", 1.0)
    code = b["currency"]
    bal_str = f"{b['total_balance']:,.2f} {code}"
    thr_str = f"{t:,.2f} {code}"
    title = T("low_bal_title", lang)
    msg = T("low_bal_msg", lang, balance=bal_str, threshold=thr_str)
    try:
        app.icon.notify(msg, title=title)
        log(f"Notification sent: {b['total_balance']:.2f}")
    except Exception as e:
        log(f"Notification failed: {e}")
        alert_file = CONFIG_DIR / "LOW_BALANCE_ALERT.txt"
        try:
            with open(alert_file, "w", encoding="utf-8") as f:
                f.write(f"{title}\n\n{msg}\n")
        except Exception:
            pass


def notify_api_status(app: AppState, transition: str):
    """Notify once when the API service status changes."""
    lang = app.lang
    if transition == "degraded":
        title = T("api_degraded_title", lang)
        msg = T("api_degraded_msg", lang)
    else:
        title = T("api_recovered_title", lang)
        msg = T("api_recovered_msg", lang)
    try:
        app.icon.notify(msg, title=title)
        log(f"API status notification: {transition}")
    except Exception as e:
        log(f"API status notify failed: {e}")


# --- Tray Menu Actions ----------------------------------------------

def on_show_balance(icon, item):
    app = getattr(icon, "_app", None)
    if app is None:
        return
    lang = app.lang
    _STATUS_ICON = {
        "none": "🟢", "minor": "🟡", "major": "🟠",
        "critical": "🔴", "maintenance": "🔵",
    }
    with app._lock:
        balances = dict(app.balances)
        err = app.error
        last = app.last_check
        raw_status = app.service_status
        status_indicator = raw_status.get("indicator") if raw_status else None

    status_key = f"status_{status_indicator}" if status_indicator else "status_unknown"
    status_line = T("service_status", lang) + " " + _STATUS_ICON.get(status_indicator, "⚪") + " " + T(status_key, lang)

    title = T("bal_title", lang)
    lines = []

    if err:
        lines.append(f"⚠ {T('bal_error_msg', lang, error=err)}")
    elif not balances:
        lines.append(f"⏳ {T('bal_empty_msg', lang)}")
    else:
        pb = app.get_preferred_balance()
        if pb:
            lines.append(f"💰 {T('bal_line', lang,
                           balance=f"{pb['total_balance']:,.2f}",
                           code=pb['currency'],
                           topped=f"{pb['topped_up_balance']:,.2f}",
                           granted=f"{pb['granted_balance']:,.2f}")}")
        else:
            first_code = next(iter(balances))
            b = balances[first_code]
            lines.append(f"💰 {T('bal_line', lang,
                           balance=f"{b['total_balance']:,.2f}",
                           code=first_code,
                           topped=f"{b['topped_up_balance']:,.2f}",
                           granted=f"{b['granted_balance']:,.2f}")}")
        if last:
            diff = datetime.now() - last
            mins = int(diff.total_seconds() / 60)
            if mins < 1:
                ago = "just now" if lang == "en" else "刚刚"
            elif mins < 60:
                ago = f"{mins} min ago" if lang == "en" else f"{mins} 分钟前"
            else:
                hrs = mins // 60
                ago = f"{hrs} hr ago" if lang == "en" else f"{hrs} 小时前"
            sep = ": " if lang == "en" else "："
            lines.append(f"🕐 {T('last_check', lang)}{sep}{ago}")

        from src.storage import get_consumption_rate
        cr = get_consumption_rate()
        if cr:
            daily_rate, hours_left, _curr = cr
            days = int(hours_left // 24)
            hrs = int(hours_left % 24)
            if lang == "en":
                lines.append(
                    f"📊 Avg: {daily_rate:.2f}/day  |  Est. {days}d {hrs}h remaining"
                )
            else:
                lines.append(
                    f"📊 日均消耗 {daily_rate:.2f}  |  预计可用 {days} 天 {hrs} 小时"
                )

    lines.append(f"📡 {status_line}")
    msg = "\n".join(lines)

    try:
        icon.notify(msg, title=title)
    except Exception as e:
        log(f"Show-balance notify failed: {e}")


def on_check_now(icon, item):
    app = getattr(icon, "_app", None)
    if app is None:
        return
    app.cancel_timer()
    threading.Thread(target=do_balance_check, args=(app,), daemon=True).start()
    log("Manual check triggered")


def _on_history(icon, item):
    app = getattr(icon, "_app", None)
    if app is None:
        return

    if app._history_open:
        try:
            app._history_window.deiconify()
            app._history_window.lift()
            app._history_window.after(50, app._history_window.focus_force)
        except Exception:
            pass
        return

    import tkinter as tk
    from tkinter import ttk
    from src.storage import get_history_page

    lang = app.lang

    if app._tk_root is None:
        app._tk_root = tk.Tk()
        app._tk_root.withdraw()
    root = app._tk_root
    win = tk.Toplevel(root)
    app._history_open = True
    app._history_window = win

    def _cleanup():
        app._history_open = False
        app._history_window = None
        win.destroy()

    win.protocol("WM_DELETE_WINDOW", _cleanup)
    win.title(T("history", lang))
    win.geometry("850x640")
    win.minsize(500, 400)
    win.after(50, win.focus_force)
    win.update_idletasks()
    sw, sh = win.winfo_screenwidth(), win.winfo_screenheight()
    w, h = win.winfo_width(), win.winfo_height()
    win.geometry(f"+{(sw - w) // 2}+{(sh - h) // 2}")

    try:
        import os, sys as _sys
        if getattr(_sys, "frozen", False):
            icon_path = os.path.join(_sys._MEIPASS, "app.ico")
        else:
            icon_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                     "assets", "app.ico")
        if os.path.isfile(icon_path):
            win.iconbitmap(icon_path)
    except Exception:
        pass

    tree_frame = tk.Frame(win)
    tree_frame.pack(fill="both", expand=True, padx=10, pady=(10, 0))

    style = ttk.Style()
    style.configure("History.Treeview", rowheight=34, font=("Segoe UI", 9))

    tree = ttk.Treeview(tree_frame, columns=("time", "curr", "total", "topped", "granted", "status"),
                        show="headings", style="History.Treeview")
    tree.heading("time", text="Timestamp" if lang == "en" else "时间")
    tree.heading("curr", text="Currency" if lang == "en" else "币种")
    tree.heading("total", text="Total" if lang == "en" else "总余额")
    tree.heading("topped", text="Topped" if lang == "en" else "充值")
    tree.heading("granted", text="Granted" if lang == "en" else "赠送")
    tree.heading("status", text="Status" if lang == "en" else "状态")
    tree.column("time", width=220, minwidth=180)
    tree.column("curr", width=60, anchor="center", minwidth=50)
    tree.column("total", width=100, anchor="e", minwidth=80)
    tree.column("topped", width=100, anchor="e", minwidth=80)
    tree.column("granted", width=100, anchor="e", minwidth=80)
    tree.column("status", width=90, anchor="center", minwidth=75)

    scrollbar = tk.Scrollbar(tree_frame, orient="vertical", command=tree.yview)
    tree.configure(yscrollcommand=scrollbar.set)
    tree.pack(side="left", fill="both", expand=True)
    scrollbar.pack(side="right", fill="y")

    # Bind mousewheel scroll
    def _on_tree_wheel(event):
        tree.yview_scroll(int(-1 * (event.delta / 60)), "units")
    tree.bind("<MouseWheel>", _on_tree_wheel)
    tree.bind("<Enter>", lambda e: tree.bind_all("<MouseWheel>", _on_tree_wheel))
    tree.bind("<Leave>", lambda e: tree.unbind_all("<MouseWheel>"))

    # Chart canvas
    chart_h = 150
    chart = tk.Canvas(win, height=chart_h, bg="#f5f5f5", highlightthickness=0)
    chart.pack(fill="x", padx=10, pady=(6, 0))

    # Rate label below chart
    rate_var = tk.StringVar()
    rate_label = tk.Label(win, textvariable=rate_var, font=("Segoe UI", 9),
                          fg="#555", anchor="w")
    rate_label.pack(fill="x", padx=14, pady=(2, 0))

    def _update_rate_label():
        from src.storage import get_consumption_rate
        cr = get_consumption_rate()
        if cr:
            daily_rate, hours_left, curr = cr
            days = int(hours_left // 24)
            hrs = int(hours_left % 24)
            if lang == "en":
                rate_var.set(
                    f"Avg: {daily_rate:.2f} {curr}/day  |  "
                    f"Est. {days}d {hrs}h remaining"
                )
            else:
                rate_var.set(
                    f"日均消耗 {daily_rate:.2f} {curr}  |  "
                    f"预计可用 {days} 天 {hrs} 小时"
                )
        else:
            rate_var.set(
                "Not enough data" if lang == "en" else "数据不足，无法计算消耗速率"
            )

    offset_var = [0]
    all_rows = []
    btn_frame = ttk.Frame(win)
    btn_frame.pack(fill="x", side="bottom", padx=10, pady=10)
    load_btn = ttk.Button(btn_frame, text="Load more ▼" if lang == "en" else "加载更多 ▼")

    STATUS_SHORT = {
        "none": "OK", "minor": "Min", "major": "Maj",
        "critical": "Crit", "maintenance": "Mnt",
    }

    def _redraw_chart():
        # Reverse so oldest is on the left
        totals = [(r["total"], r["currency"]) for r in reversed(all_rows) if r["currency"]]
        totals = totals[-100:]
        if len(totals) < 2:
            chart.delete("all")
            return
        chart.delete("all")
        cw = chart.winfo_width()
        # Axes margins: left 50px for Y labels, right 10px, top 16px, bottom 24px for X labels
        ml, mr, mt, mb = 50, 12, 16, 28
        w = cw - ml - mr
        h = chart_h - mt - mb
        vals = [t[0] for t in totals]
        lo, hi = min(vals), max(vals)
        if hi == lo:
            hi = lo + 1

        # Axes
        chart.create_line(ml, mt, ml, mt + h, fill="#999", width=1)  # Y axis
        chart.create_line(ml, mt + h, ml + w, mt + h, fill="#999", width=1)  # X axis

        # Y labels (3 ticks)
        for pct in (0, 0.5, 1):
            v = lo + (hi - lo) * pct
            y = mt + h * (1 - pct)
            chart.create_text(ml - 6, y, text=f"{v:.1f}", anchor="e",
                              fill="#666", font=("Segoe UI", 7))

        if len(all_rows) >= 100:
            first_ts = all_rows[99]["timestamp"]
            last_ts = all_rows[0]["timestamp"]
        elif all_rows:
            first_ts = all_rows[-1]["timestamp"]
            last_ts = all_rows[0]["timestamp"]
        else:
            first_ts = last_ts = ""
        chart.create_text(ml, mt + h + 6, text=first_ts[:10] if len(first_ts) > 10 else first_ts,
                          anchor="nw", fill="#666", font=("Segoe UI", 7))
        chart.create_text(ml + w, mt + h + 6, text=last_ts[:10] if len(last_ts) > 10 else last_ts,
                          anchor="ne", fill="#666", font=("Segoe UI", 7))

        # Data line
        pts = []
        for i, v in enumerate(vals):
            x = ml + w * i / (len(vals) - 1)
            y = mt + h * (1 - (v - lo) / (hi - lo))
            pts.extend((x, y))
        if len(pts) >= 4:
            chart.create_line(pts, fill="#3C6966", width=2, smooth=True)
            for x, y in zip(pts[::2], pts[1::2]):
                chart.create_oval(x - 2, y - 2, x + 2, y + 2,
                                  fill="#3C6966", outline="")
        chart.configure(scrollregion=(0, 0, cw, chart_h))

    chart.bind("<Configure>", lambda e: _redraw_chart())

    def _load_page():
        rows = get_history_page(limit=100, offset=offset_var[0])
        for r in rows:
            s = r["service_status"]
            s_label = STATUS_SHORT.get(s, s) if s else "-"
            tree.insert("", "end", values=(
                r["timestamp"], r["currency"], f"{r['total']:.2f}",
                f"{r['topped']:.2f}", f"{r['granted']:.2f}", s_label,
            ))
        all_rows.extend(rows)
        offset_var[0] += len(rows)
        if len(rows) < 100:
            load_btn.configure(state="disabled",
                               text="All loaded" if lang == "en" else "已加载全部")
        _redraw_chart()
        _update_rate_label()

    def _export_csv():
        from tkinter import filedialog, messagebox
        from src.storage import export_all_csv
        import os, datetime as _dt
        path = app.config.get("export_path", "").strip()
        if path:
            ts = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
            f = os.path.join(path, f"deepseek_balance_{ts}.csv")
        else:
            f = filedialog.asksaveasfilename(
                parent=win, defaultextension=".csv",
                filetypes=[("CSV files", "*.csv")],
                initialfile="deepseek_balance_history.csv",
            )
        if f:
            n = export_all_csv(f)
            msg = f"{n} records exported" if lang == "en" else f"已导出 {n} 条记录"
            messagebox.showinfo("Export", msg, parent=win)

    export_btn = ttk.Button(btn_frame, text="Export CSV" if lang == "en" else "导出 CSV",
                            command=_export_csv)

    load_btn.configure(command=_load_page)
    if lang == "en":
        load_btn.pack(side="left")
        export_btn.pack(side="left", padx=(6, 0))
        ttk.Button(btn_frame, text="Close", command=win.destroy).pack(side="right")
    else:
        load_btn.pack(side="left")
        export_btn.pack(side="left", padx=(6, 0))
        ttk.Button(btn_frame, text="关闭", command=win.destroy).pack(side="right")

    _load_page()
    win.protocol("WM_DELETE_WINDOW", lambda: (win.destroy(), setattr(app, '_history_open', False)))
    win.focus_force()
    root.mainloop()


def on_settings(icon, item):
    app = getattr(icon, "_app", None)
    if app is None:
        return
    try:
        from src.settings_dialog import open_settings
        open_settings(app)
    except Exception as e:
        log(f"Settings error: {e}")


def on_top_up(icon, item):
    webbrowser.open("https://platform.deepseek.com/top_up")
    log("Top-up page opened")


def on_quit(icon, item):
    app = getattr(icon, "_app", None)
    if app is None:
        icon.stop()
        return
    app.running = False
    app.cancel_timer()
    log("Shutting down")
    icon.stop()


def _on_dev_tools(icon, item):
    app = getattr(icon, "_app", None)
    if app is None:
        return

    import tkinter as tk
    from tkinter import ttk

    lang = app.lang
    if app._tk_root is None:
        app._tk_root = tk.Tk()
        app._tk_root.withdraw()
    win = tk.Toplevel(app._tk_root)
    win.title("Dev Tools")
    win.geometry("300x380")
    win.resizable(False, False)

    f = ttk.Frame(win, padding=10)
    f.pack(fill="both", expand=True)

    ttk.Label(f, text="Balance (total / topped / granted)").pack(anchor="w")
    bf = ttk.Frame(f)
    bf.pack(fill="x", pady=(0, 8))
    total_var = tk.DoubleVar(value=42.50)
    topped_var = tk.DoubleVar(value=40.00)
    granted_var = tk.DoubleVar(value=2.50)
    ttk.Spinbox(bf, from_=0, to=9999, textvariable=total_var, width=6).pack(side="left")
    ttk.Spinbox(bf, from_=0, to=9999, textvariable=topped_var, width=6).pack(side="left", padx=4)
    ttk.Spinbox(bf, from_=0, to=9999, textvariable=granted_var, width=6).pack(side="left")

    ttk.Label(f, text="Error (empty = none)").pack(anchor="w")
    err_var = tk.StringVar()
    ttk.Entry(f, textvariable=err_var).pack(fill="x", pady=(0, 8))

    ttk.Label(f, text="API Status").pack(anchor="w")
    status_opts = ["none", "minor", "major", "critical", "maintenance"]
    status_var = tk.StringVar(value="none")
    ttk.Combobox(f, textvariable=status_var, values=status_opts,
                 state="readonly", width=14).pack(anchor="w", pady=(0, 8))

    def _apply():
        with app._lock:
            app.balances = {"CNY": {
                "total_balance": total_var.get(),
                "topped_up_balance": topped_var.get(),
                "granted_balance": granted_var.get(),
            }}
            app.service_status = {
                "indicator": status_var.get(),
                "api_operational": status_var.get() == "none",
            }
            err = err_var.get().strip()
            app.error = err if err else None
            app.last_check = datetime.now()
        if app.icon:
            app.icon.title = app.balance_tooltip()
            app.icon.icon = create_icon_image(app)

    ttk.Button(f, text="Apply", command=_apply).pack(pady=(4, 0))

    win.protocol("WM_DELETE_WINDOW", win.destroy)
    win.focus_force()
    app._tk_root.mainloop()


def make_menu(app: AppState):
    lang = app.lang
    items = [
        pystray.MenuItem(T("view_balance", lang), on_show_balance, default=True),
        pystray.MenuItem(T("check_now", lang), on_check_now),
        pystray.MenuItem(T("top_up", lang), on_top_up),
        pystray.MenuItem(T("history", lang), _on_history),
        pystray.MenuItem(T("settings", lang), on_settings),
    ]
    if app.demo_mode:
        items.append(pystray.MenuItem(T("dev_tools", lang), _on_dev_tools))
    items.append(pystray.Menu.SEPARATOR)
    items.append(pystray.MenuItem(T("quit", lang), on_quit))
    return pystray.Menu(*items)


# --- Entry Point ----------------------------------------------------

def main():
    log("=" * 50)
    log(f"{APP_NAME} starting")

    app = AppState()
    proxy = app.config.get("http_proxy", "").strip()
    if proxy:
        install_proxy(proxy)
        log(f"Proxy set: {proxy}")

    if "--demo" in sys.argv:
        app.demo_mode = True
        log("Demo mode enabled")
    else:
        retention = int(app.config.get("retention_days", 30))
        prune_old_data(retention)

    if not app.demo_mode and not app.config.get("api_key", "").strip():
        log("No API key -- opening settings")
        try:
            from src.settings_dialog import open_settings
            open_settings(app)
            app = AppState()
        except Exception as e:
            log(f"Settings failed: {e}")

        if not app.demo_mode and not app.config.get("api_key", "").strip():
            log("No API key provided -- exiting")
            print(T("exit_no_key", app.config.get("language", "zh")))
            sys.exit(0)

    # Create tray icon
    icon_img = create_icon_image(app)
    app.icon = pystray.Icon(
        APP_ID,
        icon_img,
        title=app.balance_tooltip(),
        menu=make_menu(app),
    )
    app.icon._app = app

    # Start first balance check
    threading.Thread(target=do_balance_check, args=(app,), daemon=True).start()
    log("First balance check scheduled")

    try:
        app.icon.run()
    except KeyboardInterrupt:
        pass
    finally:
        app.running = False
        app.cancel_timer()
        log("Exited cleanly")
