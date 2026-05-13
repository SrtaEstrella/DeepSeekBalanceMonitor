"""
Tray application — balance checking loop, notifications, tray menu, and entry point.
"""
import sys
import threading
import webbrowser
from datetime import datetime, timedelta

import pystray

from src.config import T, log, CONFIG_DIR, APP_NAME, APP_ID
from src.api_client import fetch_balance, fetch_service_status, install_proxy
from src.icon_renderer import create_icon_image
from src.app_state import AppState
from src.rainmeter_server import start_rainmeter_server
from src.storage import save_balance_record, prune_old_data, get_consumption_rate

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


def _generate_demo_history():
    import random as _random
    _random.seed(2026)
    records = []
    now = datetime.now()
    steps = 200
    span_min = 7 * 24 * 60
    topped = 500.0
    granted = 10.0
    bumps = {55: 300, 130: 200, 175: 100}
    for i in range(steps):
        mins_ago = span_min * (steps - 1 - i) / (steps - 1)
        ts = (now - timedelta(minutes=mins_ago)).strftime("%Y-%m-%d %H:%M:%S")
        if i in bumps:
            topped += bumps[i]
        consume = 3.0 + _random.uniform(-2, 2)
        topped = max(topped - consume, 0)
        s = "minor" if i % 55 == 0 else "none"
        records.append({
            "timestamp": ts, "currency": "CNY",
            "total": round(topped + granted, 2),
            "topped": round(topped, 2),
            "granted": round(granted, 2),
            "service_status": s,
        })
    records.reverse()
    return records


def _demo_rate_from(records):
    if len(records) < 2:
        return 1.0, 0
    total_drop = records[-1]["total"] - records[0]["total"]
    daily = total_drop / 7 if total_drop > 0 else 1.0
    hrs = records[0]["topped"] / daily * 24 if daily > 0 else 0
    return daily, hrs


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
            bal = T('bal_line', lang,
                    balance=f"{pb['total_balance']:,.2f}",
                    code=pb['currency'],
                    topped=f"{pb['topped_up_balance']:,.2f}",
                    granted=f"{pb['granted_balance']:,.2f}")
        else:
            first_code = next(iter(balances))
            b = balances[first_code]
            bal = T('bal_line', lang,
                    balance=f"{b['total_balance']:,.2f}",
                    code=first_code,
                    topped=f"{b['topped_up_balance']:,.2f}",
                    granted=f"{b['granted_balance']:,.2f}")
        lines.append(f"💰 {bal}")

        if app.demo_mode and hasattr(app, '_demo_rate'):
            daily_rate = app._demo_rate
            hours_left = app._demo_hours
        else:
            cr = get_consumption_rate()
            daily_rate = hours_left = None
            if cr:
                daily_rate, hours_left = cr[:2]
        if daily_rate is not None:
            days = int(hours_left // 24)
            hrs = int(hours_left % 24)
            if days > 0:
                remaining = T("remaining_dh", lang, d=days, h=hrs)
            elif hrs >= 1:
                remaining = T("remaining_h", lang, h=hrs)
            else:
                remaining = T("remaining_lt1h", lang)
            prefix = T("est_prefix", lang)
            lines.append(f"📊 {T('rate_line', lang, rate=daily_rate, prefix=prefix, remaining=remaining)}")

    lines.append(f"📡 {status_line}")
    if last:
        diff = datetime.now() - last
        mins = int(diff.total_seconds() / 60)
        if mins < 1:
            ago = T("ago_just", lang)
        elif mins < 60:
            ago = T("ago_min", lang, n=mins)
        else:
            hrs = mins // 60
            ago = T("ago_hr", lang, n=hrs)
        sp = " " if lang == "en" else ""
        lines.append(f"🕐 {T('last_check', lang)}{sp}{ago}")
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

    from src.history_dialog import open_history
    open_history(app)

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
    win.geometry("300x480")
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

    ttk.Label(f, text="Consumption rate / Est. hours (display only)").pack(anchor="w")
    rf = ttk.Frame(f)
    rf.pack(fill="x", pady=(0, 8))
    rate_var = tk.DoubleVar(value=1.5)
    hours_var = tk.DoubleVar(value=28 * 24)
    ttk.Spinbox(rf, from_=0, to=9999, increment=0.1, textvariable=rate_var, width=6).pack(side="left")
    ttk.Label(rf, text=" /day").pack(side="left")
    ttk.Spinbox(rf, from_=0, to=99999, textvariable=hours_var, width=6).pack(side="left", padx=4)
    ttk.Label(rf, text=" h").pack(side="left")

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
            app._demo_rate = rate_var.get()
            app._demo_hours = hours_var.get()
        if app.icon:
            app.icon.title = app.balance_tooltip()
            app.icon.icon = create_icon_image(app)

    ttk.Button(f, text="Apply", command=_apply).pack(pady=(4, 0))

    def _dev_cleanup():
        win.destroy()
        app._tk_root.quit()
    win.protocol("WM_DELETE_WINDOW", _dev_cleanup)
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
    app._trigger_check = lambda a=app: threading.Thread(target=do_balance_check, args=(a,), daemon=True).start()
    app._rebuild_menu = lambda a=app: make_menu(a)

    proxy = app.config.get("http_proxy", "").strip()
    if proxy and app.config.get("proxy_enabled", False):
        install_proxy(proxy)
        log(f"Proxy set: {proxy}")

    if "--demo" in sys.argv:
        app.demo_mode = True
        log("Demo mode enabled")
        app._demo_history = _generate_demo_history()
        last = app._demo_history[0]
        _DEMO["balances"]["CNY"] = {
            "total_balance": last["total"],
            "topped_up_balance": last["topped"],
            "granted_balance": last["granted"],
        }
        d_rate, d_hrs = _demo_rate_from(app._demo_history)
        app._demo_daily = d_rate
        app._demo_hrs = d_hrs
    else:
        retention = int(app.config.get("retention_days", 30))
        prune_old_data(retention)

    if app.config.get("rainmeter_enabled", True):
        start_rainmeter_server(app)

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

    icon_img = create_icon_image(app)
    app.icon = pystray.Icon(
        APP_ID,
        icon_img,
        title=app.balance_tooltip(),
        menu=make_menu(app),
    )
    app.icon._app = app

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
