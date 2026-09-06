"""
Tray application — balance checking loop, notifications, tray menu, and entry point.
"""
import sys
import threading
import webbrowser
from datetime import datetime, timedelta
from functools import partial

import pystray
import tkinter as tk
from tkinter import ttk

from src.core.config import T, log, CONFIG_DIR, APP_NAME, APP_ID
from src.core.config import load_config, get_apis, get_preferred_api, get_api_by_id, set_preferred_api
from src.core.config import format_ago
from src.platforms.registry import get_platform, get_all_platforms as _get_plats
from src.platforms.registry import STATUS_ICON as _STATUS_ICON
from src.core.secure_settings import read_api_key_for_id
from src.platforms.deepseek import fetch_balance, fetch_service_status, install_proxy
from src.platforms.minimax import fetch_minimax_service_status
from src.ui.icon_renderer import create_icon_image
from src.core.app_state import AppState
from src.integrations.rainmeter_server import start_rainmeter_server
from src.core.storage import save_balance_record, prune_old_data, get_consumption_rate, save_package_record, get_package_history_page

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
        return 0.06, 0
    total_drop = records[-1]["total"] - records[0]["total"]
    daily = total_drop / 7 if total_drop > 0 else 0.04
    hourly = daily / 24
    hrs = records[0]["topped"] / hourly if hourly > 0 else 0
    return hourly, hrs


# --- Balance Check --------------------------------------------------

def _fetch_payg(api):
    api_id = api.get("id")
    key = read_api_key_for_id(api_id)
    if not key:
        return api_id, None, "no key"
    plat = api.get("platform", "")
    try:
        if plat.startswith("kimi_"):
            from src.platforms.kimi import fetch_kimi_balance
            data = fetch_kimi_balance(key, platform_key=plat,
                                      http_proxy=app_proxy_url())
            return api_id, data, None
        if plat.startswith("stepfun_"):
            from src.platforms.stepfun import fetch_stepfun_balance
            data = fetch_stepfun_balance(key, platform_key=plat,
                                         http_proxy=app_proxy_url())
            return api_id, data, None
        if plat.startswith("openrouter"):
            from src.platforms.openrouter import fetch_openrouter_balance
            data = fetch_openrouter_balance(key, http_proxy=app_proxy_url())
            return api_id, data, None
        data = fetch_balance(key)
        return api_id, data, None
    except Exception as e:
        return api_id, None, str(e).split("\n")[0]


def app_proxy_url():
    cfg = load_config()
    return cfg.get("http_proxy", "") if cfg.get("proxy_enabled") else ""


def _update_icons(app):
    """Render the status icon once and push it to BOTH the tray and (if the
    main window exists) the window's title-bar/taskbar icon.

    Tk calls must run on the main thread: the window update is dispatched via
    after(0) so it stays safe when invoked from the polling thread."""
    img = create_icon_image(app)
    if app.icon:
        app.icon.icon = img
    mw = getattr(app, "_main_window", None)
    if mw is not None and not isinstance(mw, tk.Toplevel) and hasattr(mw, "set_dynamic_icon"):
        try:
            app._tk_root.after(0, lambda: mw.set_dynamic_icon(img))
        except Exception:
            pass


def _fetch_package(api, proxy_url=""):
    api_id = api.get("id")
    key = read_api_key_for_id(api_id)
    if not key:
        return api_id, None, "no key"
    plat = api.get("platform", "")
    try:
        if plat.startswith("minimax_"):
            from src.platforms.minimax import fetch_minimax_quota
            quota = fetch_minimax_quota(platform_key=plat, api_key=key, http_proxy=proxy_url)
        elif plat.startswith("command_code"):
            from src.platforms.command_code import fetch_command_code_quota
            quota = fetch_command_code_quota(api_key=key, platform_key=plat, http_proxy=proxy_url)
        elif plat.startswith("glm_"):
            from src.platforms.glm import fetch_glm_quota
            quota = fetch_glm_quota(api_key=key, platform_key=plat, http_proxy=proxy_url)
        else:
            from src.platforms.opencode import fetch_opencode_quota
            quota = fetch_opencode_quota(api_key=key, http_proxy=proxy_url)
        return api_id, quota, None
    except Exception as e:
        return api_id, None, str(e).split("\n")[0]


def do_balance_check(app: AppState):
    if app.demo_mode:
        with app._lock:
            app.balances = _DEMO["balances"]
            app.service_status = _DEMO["service_status"]
            app.error = None
            app.last_check = datetime.now()
        if app.icon:
            app.icon.title = app.balance_tooltip()
            _update_icons(app)
        interval_sec = int(app.config.get("interval_minutes", 10)) * 60
        app.schedule_next_check(lambda: do_balance_check(app), interval_sec)
        return

    if not app.running:
        return
    # fetch service status based on preferred API's platform
    status = None
    try:
        pref = get_preferred_api()
        if pref:
            plat = pref.get("platform", "")
            if plat == "deepseek":
                status = fetch_service_status()
            elif plat.startswith("minimax_"):
                status = fetch_minimax_service_status()
            # opencode_go has no status page — status stays None
    except Exception:
        status = None
    with app._lock:
        app.service_status = status

    if not app.running:
        return
    # --- Fetch APIs: parallel (all) or one-hot (preferred only) ---
    cfg = load_config()
    apis = get_apis(cfg)
    if not apis:
        with app._lock:
            app.error = T("error_no_key", app.lang)
            app.balances = {}
            app.package_data = None
    else:
        if cfg.get("fetch_mode", "parallel") == "onehot":
            pref = get_preferred_api(cfg)
            apis = [pref] if pref else []
        if not apis:
            # one-hot with no preferred API: skip queries this round, keep last
            # data untouched, and keep the poll loop alive (must reschedule here,
            # since the tail of this function is skipped)
            interval_sec = int(app.config.get("interval_minutes", 10)) * 60
            app.schedule_next_check(lambda: do_balance_check(app), interval_sec)
            return
        from concurrent.futures import ThreadPoolExecutor, as_completed
        proxy_url = cfg.get("http_proxy", "") if cfg.get("proxy_enabled") else ""
        payg_apis = [a for a in apis if a.get("mode") == "payg"]
        pkg_apis = [a for a in apis if a.get("mode") == "package"]

        def _fetch_status_for(plat):
            try:
                if plat == "deepseek":
                    return fetch_service_status()
                if plat.startswith("minimax_"):
                    return fetch_minimax_service_status()
            except Exception:
                return None
            return None

        futures = {}
        with ThreadPoolExecutor(max_workers=min(len(apis) + 3, 10)) as pool:
            for api in payg_apis:
                futures[pool.submit(_fetch_payg, api)] = ("payg", api)
            for api in pkg_apis:
                futures[pool.submit(_fetch_package, api, proxy_url)] = ("package", api)
            # fetch status for every platform that has a status page
            status_futures = {}
            for api in apis:
                plat = api.get("platform", "")
                pmeta = get_platform(plat)
                if pmeta and pmeta.has_status_page and plat not in status_futures:
                    status_futures[plat] = pool.submit(_fetch_status_for, plat)

        # collect per-platform service statuses FIRST — each API's DB row is
        # written with its own platform's status, not the preferred one's
        statuses = {}
        for plat, sf in status_futures.items():
            try:
                st = sf.result()
                if st is not None:
                    statuses[plat] = st
            except Exception as e:
                log(f"Status fetch failed for {plat}: {e}")

        for f in as_completed(futures):
            mode, api = futures[f]
            api_id, result, err = f.result()
            if result is None:
                log(f"Check failed for {api.get('name')} ({mode}): {err}")
                continue
            # per-API status: this platform's own fetch result only.
            # Platforms without a status page (or failed fetches) write NULL —
            # never borrow the preferred API's indicator for another platform.
            own_st = statuses.get(api.get("platform", ""))
            s_ind = own_st.get("indicator") if own_st else None
            if mode == "payg":
                data = result
                for code, bal in data["all_balances"].items():
                    save_balance_record(code, bal["total_balance"], bal["topped_up_balance"], bal["granted_balance"], service_status=s_ind, api_id=api_id)
                log(f"Balance OK for {api.get('name')}: {list(data['all_balances'].values())[0]['total_balance']:.2f}")
            else:
                quota = result
                r5 = quota.get("5h") or quota.get("rolling")
                rw = quota.get("weekly")
                rm = quota.get("monthly")
                save_package_record(
                    api_id,
                    h5_percent=r5.get("usage_percent") if r5 else None,
                    h5_reset=r5.get("reset_in_sec") if r5 else None,
                    weekly_percent=rw.get("usage_percent") if rw else None,
                    weekly_reset=rw.get("reset_in_sec") if rw else None,
                    monthly_percent=rm.get("usage_percent") if rm else None,
                    monthly_reset=rm.get("reset_in_sec") if rm else None,
                    service_status=s_ind,
                )
                log(f"Package OK for {api.get('name')}: h5={r5.get('usage_percent') if r5 else 'N/A'}, weekly={rw.get('usage_percent') if rw else 'N/A'}")

        # cache results per API — merge into existing entry so status/error survive
        for f in futures:
            mode, api = futures[f]
            aid = api.get("id")
            try:
                _, result, _err = f.result()
                with app._lock:
                    entry = app._api_cache.setdefault(aid, {})
                    if result is None:
                        entry["error"] = _err
                        continue
                    if mode == "payg":
                        entry["balances"] = result["all_balances"]
                    else:
                        entry["package_data"] = result
                    entry["error"] = None
                    entry["last_check"] = datetime.now()
                    st = statuses.get(api.get("platform", ""))
                    if st is not None:
                        entry["service_status"] = st
            except Exception as e:
                log(f"Cache merge failed for {api.get('name')}: {e}")
        # update app state with preferred API's cached data
        pref = get_preferred_api(cfg)
        if pref:
            pref_id = pref.get("id")
            cached = app._api_cache.get(pref_id, {})
            with app._lock:
                if "balances" in cached:
                    app.balances = cached["balances"]
                    app.package_data = cached.get("package_data")
                    app.error = cached.get("error")
                    app.last_check = cached.get("last_check")
                    app.service_status = cached.get("service_status", status)
                elif "package_data" in cached:
                    app.package_data = cached["package_data"]
                    app.balances = {}
                    app.error = cached.get("error")
                    app.last_check = cached.get("last_check")
                    app.service_status = cached.get("service_status", status)
                else:
                    # no cached data — could be first startup with timeout, NOT missing key
                    app.balances = {}
                    app.package_data = None
                    # only show "no key" if the API truly has no key configured
                    key = read_api_key_for_id(pref_id)
                    if not key:
                        app.error = T("error_no_key", app.lang)
                    else:
                        app.error = None  # fetch failed but key exists — show "..." not error

    if app.icon:
        app.icon.title = app.balance_tooltip()
        _update_icons(app)
        # keep tray menu lang in sync
        try:
            app.icon.menu = app._rebuild_menu()
        except Exception:
            pass

    # refresh main window overview/history if open (follow new preferred API)
    try:
        mw = getattr(app, "_main_window", None)
        if mw and hasattr(mw, "refresh_all"):
            app._tk_root.after(0, lambda: mw.refresh_all(follow_preferred=True))
    except Exception:
        pass

    if app.should_alert():
        notify_user(app)

    # single-day spend too fast → one-shot alert + orange icon state is derived in renderer
    try:
        app.is_daily_spend_fast()  # refresh fast-state for icon
        if app.should_spend_alert():
            lang = app.lang
            msg = T("spend_alert_msg", lang,
                    value=f"{get_today_spend_value(app)}",
                    line=(f"{app.config.get('daily_spend_line_yuan', 20)}"
                          if _pref_mode(app) == "payg" else
                          f"{app.config.get('daily_spend_line_percent', 10)}%"))
            app.icon.notify(msg, title=T("spend_alert_title", lang))
    except Exception as e:
        log(f"Spend alert failed: {e}")

    if app.config.get("api_alert_enabled", True):
        transition = app.check_api_status_alert()
        if transition:
            notify_api_status(app, transition)

    # DeepSeek peak/valley phase-change reminder (only when a deepseek API is preferred)
    try:
        if app.config.get("peak_valley_alert_enabled", False):
            pref = next((a for a in app.config.get("apis") or []
                         if a.get("id") == app.config.get("preferred_api_id")), {})
            if str(pref.get("platform", "")).startswith("deepseek"):
                lang = app.lang
                phase = app.check_peak_valley_transition()
                if phase:
                    key = f"peak_alert_{phase}"
                    app.icon.notify(T(key, lang), title="DeepSeek")
                    log(f"Peak/valley reminder: {phase}")
    except Exception as e:
        log(f"Peak/valley reminder failed: {e}")

    interval_sec = int(app.config.get("interval_minutes", 10)) * 60
    app.schedule_next_check(lambda: do_balance_check(app), interval_sec)


# --- Low-Balance Notification ---------------------------------------

def _pref_mode(app: AppState) -> str:
    pref_id = app.config.get("preferred_api_id", "")
    for a in app.config.get("apis") or []:
        if a.get("id") == pref_id:
            return a.get("mode", "payg")
    return "payg"


def get_today_spend_value(app: AppState) -> float:
    from src.core.storage import get_today_spend
    pref_id = app.config.get("preferred_api_id", "")
    api = next((a for a in app.config.get("apis") or [] if a.get("id") == pref_id), {})
    bp = api.get("billing_period") or None
    return get_today_spend(pref_id, api.get("mode", "payg"), bp)


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
    with app._lock:
        balances = dict(app.balances)
        err = app.error
        last = app.last_check
        raw_status = app.service_status
        pd = app.package_data

    # Get preferred API name for title
    api_name = ""
    pref_id = app.config.get("preferred_api_id", "")
    for api in app.config.get("apis") or []:
        if api.get("id") == pref_id:
            api_name = api.get("name", "")
            break

    # Package mode notification
    if pd:
        try:
            from src.platforms.opencode import format_reset_short
            # determine which windows this platform supports and preferred billing period
            pref_platform = ""
            billing_period = "monthly"
            try:
                pref_api = get_api_by_id(app.config.get("preferred_api_id")) if app.config.get("preferred_api_id") else None
                if pref_api:
                    pref_platform = pref_api.get("platform", "")
                    # user-set billing_period, verbatim — no platform fallback
                    billing_period = pref_api.get("billing_period") or ""
            except Exception:
                pass
            pmeta = get_platform(pref_platform) if pref_platform else None
            windows = pmeta.package_windows if pmeta else ["5h", "weekly", "monthly"]
            # map display labels
            window_labels = {
                "5h": (T("win_5h", lang), "5h rolling"),
                "weekly": (T("win_weekly", lang), "Weekly"),
                "monthly": (T("win_monthly", lang), "Monthly"),
            }
            # map quota keys (MiniMax uses "5h", OCGo uses "rolling")
            window_keys = {
                "5h": ("5h", "rolling"),
                "weekly": ("weekly",),
                "monthly": ("monthly",),
            }
            lines = []
            for wkey in windows:
                label = window_labels.get(wkey, (wkey, wkey))[0 if lang == "zh" else 1]
                wdata = None
                for k in window_keys.get(wkey, (wkey,)):
                    wdata = pd.get(k)
                    if wdata:
                        break
                if wdata:
                    remaining = wdata.get("percent_remaining", 100 - wdata.get("usage_percent", 0))
                    fine = False
                    if wkey in ("weekly", "monthly"):
                        from src.core.storage import get_refined_remaining
                        pref_id = app.config.get("preferred_api_id", "")
                        r = get_refined_remaining(pref_id or "", target=wkey)
                        if r is not None:
                            remaining, fine = r, True
                    reset_s = wdata.get("reset_in_sec", 0)
                    reset_str = format_reset_short(reset_s, lang) if reset_s > 0 else "-"
                    key = "remaining_pct_fine" if fine else "remaining_pct"
                    lines.append(f"{label}：{T(key, lang, pct=remaining)}（{reset_str}）")
            # status line only if platform has a status page
            if pmeta and pmeta.has_status_page:
                ind = raw_status.get("indicator") if raw_status else None
                status_key = f"status_{ind}" if ind else "status_unknown"
                lines.append(f"📡 {T('service_status', lang)} {_STATUS_ICON.get(ind, '⚪')} {T(status_key, lang)}")
            if last:
                sp = " " if lang == "en" else ""
                lines.append(f"🕐 {T('last_check', lang)}{sp}{format_ago(last, lang)}")
            icon.notify("\n".join(lines), title=T("bal_title", lang, name=api_name))
        except Exception as e:
            log(f"Package notify failed: {e}")
        return

    # PayG mode notification
    title = T("bal_title", lang, name=api_name)
    status_key = f"status_{raw_status.get('indicator')}" if raw_status and raw_status.get("indicator") else "status_unknown"
    status_line = T("service_status", lang) + " " + _STATUS_ICON.get(raw_status.get("indicator") if raw_status else None, "⚪") + " " + T(status_key, lang)
    lines = []
    if err:
        lines.append(f"⚠ {T('bal_error_msg', lang, error=err)}")
    elif not balances:
        lines.append(f"⏳ {T('bal_empty_msg', lang)}")
    else:
        pb = app.get_preferred_balance()
        if pb:
            bal = T('bal_line', lang, balance=f"{pb['total_balance']:,.2f}", code=pb['currency'], topped=f"{pb['topped_up_balance']:,.2f}", granted=f"{pb['granted_balance']:,.2f}")
        else:
            first_code = next(iter(balances)); b = balances[first_code]
            bal = T('bal_line', lang, balance=f"{b['total_balance']:,.2f}", code=first_code, topped=f"{b['topped_up_balance']:,.2f}", granted=f"{b['granted_balance']:,.2f}")
        lines.append(f"💰 {bal}")
        if app.demo_mode and hasattr(app, '_demo_rate'):
            hourly_rate = app._demo_rate; busy_hours = app._demo_hrs
        else:
            hourly_rate = busy_hours = None
            pref_id = app.config.get("preferred_api_id")
            pref_api = get_api_by_id(pref_id) if pref_id else None
            if not (pref_api and pref_api.get("mode") == "package"):
                cr = get_consumption_rate(api_id=pref_id) if pref_id else get_consumption_rate()
                if cr: hourly_rate, busy_hours = cr[:2]
        if hourly_rate is not None:
            total_hrs = round(busy_hours, 1)
            lines.append(f"📊 {T('rate_line', lang, rate=hourly_rate, prefix=T('est_prefix', lang), remaining=f'{total_hrs}')}")
    lines.append(f"📡 {status_line}")
    if last:
        sp = " " if lang == "en" else ""
        lines.append(f"🕐 {T('last_check', lang)}{sp}{format_ago(last, lang)}")
    icon.notify("\n".join(lines), title=title)


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
    def _show():
        try:
            from src.ui.main_window import MainWindow
            mw = getattr(app, "_main_window", None)
            if not isinstance(mw, MainWindow):
                mw = MainWindow(app)
                app._main_window = mw
            mw.show("history")
        except Exception as e:
            log(f"MainWindow history error: {e}")
    app._tk_root.after(0, _show)

def on_settings(icon, item):
    app = getattr(icon, "_app", None)
    if app is None:
        return
    def _show():
        try:
            from src.ui.main_window import MainWindow
            mw = getattr(app, "_main_window", None)
            if not isinstance(mw, MainWindow):
                mw = MainWindow(app)
                app._main_window = mw
            mw.show("settings")
        except Exception as e:
            log(f"MainWindow settings error: {e}")
    app._tk_root.after(0, _show)


def on_top_up(icon, item):
    app = getattr(icon, "_app", None)
    if app is None:
        return
    try:
        pref_id = app.config.get("preferred_api_id")
        pref_api = get_api_by_id(pref_id) if pref_id else None
        url = ""
        if pref_api:
            pmeta = get_platform(pref_api.get("platform", ""))
            if pmeta:
                url = pmeta.console_url
        if not url:
            url = "https://platform.deepseek.com"
        webbrowser.open(url)
        log("Console opened")
    except Exception:
        webbrowser.open("https://platform.deepseek.com")


def on_quit(icon, item):
    app = getattr(icon, "_app", None)
    if app is None:
        icon.stop()
        return
    app.running = False
    try:
        app.cancel_timer()
    except Exception:
        pass
    # Schedule tk root destruction on the tkinter main thread.
    # Using after() ensures we don't call destroy() from the pystray thread.
    try:
        app._tk_root.after(0, app._tk_root.destroy)
    except Exception:
        pass
    icon.stop()
    log("Shutting down")


def _on_dev_tools(icon, item):
    app = getattr(icon, "_app", None)
    if app is None:
        return
    def _show():
        try:
            from src.ui.main_window import MainWindow
            mw = getattr(app, "_main_window", None)
            if not isinstance(mw, MainWindow):
                mw = MainWindow(app)
                app._main_window = mw
            mw.show("dev")
        except Exception as e:
            log(f"Dev tools open failed: {e}")
    app._tk_root.after(0, _show)


class DevFrame(ttk.Frame):
    """Embeddable dev tools for MainWindow."""
    def __init__(self, parent, app):
        super().__init__(parent, padding=10)
        self.app = app
        self._build()
    def _build(self):
        import tkinter as tk
        from tkinter import ttk
        from datetime import datetime
        from src.ui.icon_renderer import create_icon_image
        ttk.Label(self, text="Balance (total / topped / granted)").pack(anchor="w")
        bf = ttk.Frame(self); bf.pack(fill="x", pady=(0, 8))
        self.total_var = tk.DoubleVar(value=42.50)
        self.topped_var = tk.DoubleVar(value=40.00)
        self.granted_var = tk.DoubleVar(value=2.50)
        ttk.Spinbox(bf, from_=0, to=9999, textvariable=self.total_var, width=6).pack(side="left")
        ttk.Spinbox(bf, from_=0, to=9999, textvariable=self.topped_var, width=6).pack(side="left", padx=4)
        ttk.Spinbox(bf, from_=0, to=9999, textvariable=self.granted_var, width=6).pack(side="left")
        ttk.Label(self, text="Error (empty = none)").pack(anchor="w")
        self.err_var = tk.StringVar()
        ttk.Entry(self, textvariable=self.err_var).pack(fill="x", pady=(0, 8))
        ttk.Label(self, text="API Status").pack(anchor="w")
        status_opts = ["none", "minor", "major", "critical", "maintenance"]
        self.status_var = tk.StringVar(value="none")
        ttk.Combobox(self, textvariable=self.status_var, values=status_opts, state="readonly", width=14).pack(anchor="w", pady=(0, 8))
        ttk.Label(self, text="Consumption rate / Est. hours (display only)").pack(anchor="w")
        rf = ttk.Frame(self); rf.pack(fill="x", pady=(0, 8))
        self.rate_var = tk.DoubleVar(value=0.06)
        self.hours_var = tk.DoubleVar(value=28 * 24)
        ttk.Spinbox(rf, from_=0, to=9999, increment=0.01, textvariable=self.rate_var, width=6).pack(side="left")
        ttk.Label(rf, text=" /hr").pack(side="left")
        ttk.Spinbox(rf, from_=0, to=99999, textvariable=self.hours_var, width=6).pack(side="left", padx=4)
        ttk.Label(rf, text=" h").pack(side="left")
        def _apply():
            with self.app._lock:
                self.app.balances = {"CNY": {"total_balance": self.total_var.get(), "topped_up_balance": self.topped_var.get(), "granted_balance": self.granted_var.get()}}
                self.app.service_status = {"indicator": self.status_var.get(), "api_operational": self.status_var.get() == "none"}
                err = self.err_var.get().strip()
                self.app.error = err if err else None
                self.app.last_check = datetime.now()
                self.app._demo_rate = self.rate_var.get()
                self.app._demo_hrs = self.hours_var.get()
            if self.app.icon:
                self.app.icon.title = self.app.balance_tooltip()
                _update_icons(self.app)
            # refresh overview if present
            try:
                if hasattr(self.app, "_main_window") and self.app._main_window:
                    # find overview refresh
                    pass
            except: pass
        ttk.Button(self, text="Apply", command=_apply).pack(pady=(4, 0))
    def on_show(self): pass
    def refresh(self, follow_preferred=False): pass


def _show_main(icon, item, tab="history"):
    app = getattr(icon, "_app", None)
    if app is None:
        return
    def _show():
        try:
            from src.ui.main_window import MainWindow
            mw = getattr(app, "_main_window", None)
            if not isinstance(mw, MainWindow):
                mw = MainWindow(app)
                app._main_window = mw
            mw.show(tab)
        except Exception as e:
            log(f"MainWindow show failed: {e}")
    try:
        app._tk_root.after(0, _show)
    except Exception:
        pass

def _apply_preferred_switch(app: AppState, aid: str, *_args):
    """Switch preferred API and refresh all UI. Accepts extra pystray args."""
    if not set_preferred_api(aid):
        return
    app.config = load_config()
    cached = app._api_cache.get(aid, {})
    with app._lock:
        if "balances" in cached:
            app.balances = cached["balances"]
            app.package_data = cached.get("package_data")
            app.error = cached.get("error")
            app.last_check = cached.get("last_check")
        elif "package_data" in cached:
            app.package_data = cached["package_data"]
            app.balances = {}
            app.error = cached.get("error")
            app.last_check = cached.get("last_check")
        else:
            app.balances = {}
            app.package_data = None
            app.error = None
    if app.icon:
        app.icon.title = app.balance_tooltip()
        _update_icons(app)
        # NOTE: do NOT rebuild the Win32 menu here — the menu structure is
        # static and rebuilding it from the polling thread races the Windows
        # menu redraw (hover text garbles on Win11 25H2). Menu refreshes only
        # happen on startup / preferred-API switch / language change.
    mw = getattr(app, "_main_window", None)
    if mw and hasattr(mw, "refresh_all"):
        app._tk_root.after(0, lambda: mw.refresh_all(follow_preferred=True))


def _build_api_selection_submenu(app):
    lang = app.lang
    cfg = load_config()
    apis = get_apis(cfg)
    pref_id = cfg.get("preferred_api_id", "")

    items = []
    for api in apis:
        aid = api["id"]
        disp = api.get("name", aid)

        items.append(pystray.MenuItem(
            disp,
            partial(_apply_preferred_switch, app, aid),
            checked=lambda item, _aid=aid: load_config().get("preferred_api_id", "") == _aid,
            radio=True,
        ))

    if items:
        items.append(pystray.Menu.SEPARATOR)
    items.append(pystray.MenuItem(
        T("add_edit_api", lang),
        lambda icon, item: _show_main(icon, item, "manage"),
    ))
    return pystray.Menu(*items)

def make_menu(app: AppState):
    lang = app.lang
    items = [
        pystray.MenuItem(T("view_balance", lang), on_show_balance, default=True),
        pystray.MenuItem(T("history", lang), _on_history),
        pystray.MenuItem(T("api_select", lang), _build_api_selection_submenu(app)),
        pystray.MenuItem(T("check_now", lang), on_check_now),
        pystray.MenuItem(T("top_up", lang), on_top_up),
        pystray.MenuItem(T("settings", lang), on_settings),
    ]
    if app.demo_mode:
        items.append(pystray.MenuItem(T("dev_tools", lang), _on_dev_tools))
    items.append(pystray.Menu.SEPARATOR)
    items.append(pystray.MenuItem(T("quit", lang), on_quit))
    return pystray.Menu(*items)


# --- Entry Point ----------------------------------------------------

def main():
    import tkinter as tk
    log("=" * 50)
    log(f"{APP_NAME} starting")

    _tk_root = tk.Tk()
    _tk_root.withdraw()

    app = AppState()
    app._tk_root = _tk_root
    app._main_window = None
    app._trigger_check = lambda a=app: threading.Thread(target=do_balance_check, args=(a,), daemon=True).start()
    app._rebuild_menu = lambda a=app: make_menu(a)

    proxy = app.config.get("http_proxy", "").strip()
    if proxy and app.config.get("proxy_enabled", False):
        install_proxy(proxy)
        log(f"Proxy set: {proxy}")
    else:
        install_proxy("")

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
        hourly, hrs = _demo_rate_from(app._demo_history)
        app._demo_rate = hourly
        app._demo_hrs = hrs
    else:
        retention = int(app.config.get("retention_days", 180))
        prune_old_data(retention)

    if app.config.get("rainmeter_enabled", True):
        start_rainmeter_server(app)

    # First-time setup: no APIs → open manage tab — don't block, tray stays with gray icon
    apis = app.config.get("apis") or []
    if not app.demo_mode and not apis:
        log("No APIs -- opening API management")
        try:
            from src.ui.main_window import MainWindow
            mw = MainWindow(app)
            app._main_window = mw
            _tk_root.after(300, lambda: mw.show("manage"))
        except Exception as e:
            log(f"API management open failed: {e}")

    icon_img = create_icon_image(app)
    # push the very first status icon to the window too, in case the main
    # window opens before the first poll completes (app.icon not ready yet —
    # _update_icons handles that gracefully)
    _update_icons(app)
    app.icon = pystray.Icon(
        APP_ID,
        icon_img,
        title=app.balance_tooltip(),
        menu=make_menu(app),
    )
    app.icon._app = app

    threading.Thread(target=do_balance_check, args=(app,), daemon=True).start()
    log("First balance check scheduled")

    # Run pystray in a daemon thread — it must NOT be on the main
    # thread because the main thread belongs to tkinter.
    def _run_pystray():
        try:
            app.icon.run()
        except Exception as e:
            log(f"Pystray error: {e}")
    pystray_thread = threading.Thread(target=_run_pystray, daemon=True)
    pystray_thread.start()
    log("System tray started")

    # Run tkinter mainloop on the main thread.  This blocks until
    # _tk_root.destroy() is called (by the quit handler).
    try:
        _tk_root.mainloop()
    except KeyboardInterrupt:
        pass
    finally:
        app.running = False
        try:
            app.cancel_timer()
        except Exception:
            pass
        log("Exited cleanly")
