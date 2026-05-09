"""
Tray application — balance checking loop, notifications, tray menu, and entry point.
"""
import sys
import threading
import webbrowser
from datetime import datetime

import pystray

from src.config import T, log, CONFIG_DIR, APP_NAME, APP_ID
from src.api_client import fetch_balance, fetch_service_status
from src.icon_renderer import create_icon_image
from src.app_state import AppState
from src.storage import save_balance_record


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
            for code, bal in data["all_balances"].items():
                save_balance_record(code, bal["total_balance"],
                                    bal["topped_up_balance"],
                                    bal["granted_balance"])
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
        lines.append(T("bal_error_msg", lang, error=err))
    elif not balances:
        lines.append(T("bal_empty_msg", lang))
    else:
        pb = app.get_preferred_balance()
        if pb:
            lines.append(T("bal_line", lang,
                           balance=f"{pb['total_balance']:,.2f}",
                           code=pb["currency"],
                           topped=f"{pb['topped_up_balance']:,.2f}",
                           granted=f"{pb['granted_balance']:,.2f}"))
        else:
            first_code = next(iter(balances))
            b = balances[first_code]
            lines.append(T("bal_line", lang,
                           balance=f"{b['total_balance']:,.2f}",
                           code=first_code,
                           topped=f"{b['topped_up_balance']:,.2f}",
                           granted=f"{b['granted_balance']:,.2f}"))
        time_str = last.strftime("%Y-%m-%d %H:%M:%S") if last else "-"
        lines.append(T("last_check", lang) + ": " + time_str)

    lines.append(status_line)
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


def make_menu(app: AppState):
    lang = app.lang
    return pystray.Menu(
        pystray.MenuItem(T("view_balance", lang), on_show_balance, default=True),
        pystray.MenuItem(T("check_now", lang), on_check_now),
        pystray.MenuItem(T("top_up", lang), on_top_up),
        pystray.MenuItem(T("settings", lang), on_settings),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem(T("quit", lang), on_quit),
    )


# --- Entry Point ----------------------------------------------------

def main():
    log("=" * 50)
    log(f"{APP_NAME} starting")

    app = AppState()

    # First run -- force settings if no API key
    if not app.config.get("api_key", "").strip():
        log("No API key -- opening settings")
        try:
            from src.settings_dialog import open_settings
            open_settings(app)
            app = AppState()
        except Exception as e:
            log(f"Settings failed: {e}")

        if not app.config.get("api_key", "").strip():
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
