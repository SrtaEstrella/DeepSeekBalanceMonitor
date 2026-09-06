"""
Application state - holds balances, config, timer, and helper methods.
"""
import os
import sys
import threading

from src.core.config import load_config, T, log, APP_ID


class AppState:
    def __init__(self):
        self.config = load_config()
        self.icon = None
        self.balances = {}
        self.last_check = None
        self.error = None
        self.service_status = None
        self._timer = None
        self.running = True
        self._lock = threading.Lock()
        self._settings_open = False
        self._settings_window = None
        self._history_open = False
        self._history_window = None
        self._main_window = None
        self._tk_root = None
        self._alert_suppressed = False
        self._api_was_operational = True
        self.demo_mode = False
        self.package_data = None  # latest package quota for preferred API
        self._alert_suppressed_pkg = False
        self._check_generation = 0  # incremented on API switch to discard stale results
        self._api_cache = {}  # {api_id: {"balances": {...}, "package_data": {...}, "service_status": {...}, "error": str}}

    @property
    def lang(self):
        return self.config.get("language", "zh")

    def get_preferred_balance(self):
        for c, b in self.balances.items():
            return {**b, "currency": c}
        return None

    def balance_tooltip(self):
        with self._lock:
            pd = self.package_data
            if pd:
                # package mode: show best available remaining % (refined
                # fractional value for weekly/monthly when possible)
                mp = pd.get("monthly") or pd.get("weekly") or pd.get("5h") or pd.get("rolling")
                if mp:
                    rm = mp.get("percent_remaining", 100 - mp.get("usage_percent", 0))
                    pref_id = self.config.get("preferred_api_id", "")
                    api = next((a for a in (self.config.get("apis") or [])
                                if a.get("id") == pref_id), None)
                    bp = (api or {}).get("billing_period") or "monthly"
                    if bp in ("weekly", "monthly"):
                        try:
                            from src.core.storage import get_refined_remaining
                            r = get_refined_remaining(pref_id, target=bp)
                            if r is not None:
                                rm = r
                        except Exception:
                            pass
                    return f"{T('total_balance', self.lang)} {rm:.2f}%"
            if self.error:
                return T("tooltip_error", self.lang, error=self.error)
            b = self.get_preferred_balance()
            if b:
                return T("tooltip_balance", self.lang,
                         total=f"{b['total_balance']:,.2f}",
                         code=b["currency"])
            return T("tooltip_checking", self.lang)

    def is_low_balance(self):
        with self._lock:
            # package mode: check remaining % using billing_period
            pd = self.package_data
            if pd:
                mp = pd.get("monthly") or pd.get("weekly") or pd.get("5h") or pd.get("rolling")
                if mp:
                    remaining_pct = mp.get("percent_remaining", 100 - mp.get("usage_percent", 0))
                    threshold = float(self.config.get("threshold_package_percent", 10))
                    return remaining_pct < threshold
            # payg mode: check total balance
            b = self.get_preferred_balance()
            if b is None:
                return False
            t = float(self.config.get("threshold_yuan", 1.0))
            return b["total_balance"] < t

    def should_alert(self):
        """Return True if a low-balance notification should fire this cycle."""
        with self._lock:
            mode = self.config.get("alert_mode", "always")
            if mode == "never":
                self._alert_suppressed = False
                return False
            b = self.get_preferred_balance()
            if b is None:
                return False
            t = float(self.config.get("threshold_yuan", 1.0))
            low = b["total_balance"] < t
            if not low:
                self._alert_suppressed = False
                return False
            if mode == "always":
                return True
            if self._alert_suppressed:
                return False
            self._alert_suppressed = True
            return True

    def is_daily_spend_fast(self):
        """True when today's consumption crosses the configured daily-spend line.
        Resets naturally at midnight (aggregation window = today)."""
        from src.core.storage import get_today_spend
        with self._lock:
            pref_id = self.config.get("preferred_api_id", "")
            apis = self.config.get("apis") or []
            api = next((a for a in apis if a.get("id") == pref_id), None)
            mode = (api or {}).get("mode", "payg")
            # billing_period is user-set at API creation — take it verbatim
            bp = (api or {}).get("billing_period")
            try:
                if mode == "package":
                    line = float(self.config.get("daily_spend_line_percent", 10))
                    spent = get_today_spend(pref_id, "package", bp)
                    fast = spent >= line > 0
                else:
                    line = float(self.config.get("daily_spend_line_yuan", 20))
                    spent = get_today_spend(pref_id, "payg")
                    fast = spent >= line > 0
            except Exception as e:
                log(f"daily-spend check failed: {e}")
                return False
            # one-shot alert state (same pattern as low-balance suppression)
            if getattr(self, "_spend_was_fast", False) != fast:
                self._spend_was_fast = fast
                self._spend_alert_fired = False
            return fast

    def should_spend_alert(self):
        """One-shot alert on entering the daily-spend-fast state."""
        if not self.config.get("daily_spend_alert_enabled", False):
            return False
        if not self.is_daily_spend_fast():
            return False
        with self._lock:
            if getattr(self, "_spend_alert_fired", False):
                return False
            self._spend_alert_fired = True
            return True

    def check_api_status_alert(self):
        """Return "degraded", "recovered", or None on first status change.
        Fires once per transition — only when the API operational flag flips."""
        with self._lock:
            st = self.service_status
            if st is None:
                return None
            now_ok = st.get("api_operational", True)
            was_ok = self._api_was_operational
            self._api_was_operational = now_ok
            if was_ok and not now_ok:
                return "degraded"
            if not was_ok and now_ok:
                return "recovered"
            return None

    @staticmethod
    def _deepseek_peak_phase(now=None):
        """Return "peak" or "valley" for DeepSeek peak/off-peak pricing.
        Beijing time (GMT+8) Mon–Fri 09:00–12:00 & 14:00–18:00 = peak;
        weekends and all other hours = valley (half price)."""
        from datetime import datetime, timezone, timedelta as _td
        tz = timezone(_td(hours=8))
        n = now or datetime.now(tz)
        if n.tzinfo is None:
            pass
        weekday = n.weekday()  # Mon=0 .. Sun=6
        if weekday >= 5:
            return "valley"
        hm = n.hour * 60 + n.minute
        if (9 * 60 <= hm < 12 * 60) or (14 * 60 <= hm < 18 * 60):
            return "peak"
        return "valley"

    def check_peak_valley_transition(self):
        """Return "peak", "valley", or None when the DeepSeek pricing phase flips."""
        with self._lock:
            phase = self._deepseek_peak_phase()
            prev = getattr(self, "_pv_phase", None)
            self._pv_phase = phase
            if prev is None or prev == phase:
                return None
            return phase

    def schedule_next_check(self, cb, interval_sec):
        with self._lock:
            if self._timer:
                self._timer.cancel()
            if not self.running:
                return
            self._timer = threading.Timer(interval_sec, cb)
            self._timer.daemon = True
            self._timer.start()

    def cancel_timer(self):
        with self._lock:
            if self._timer:
                self._timer.cancel()
                self._timer = None


_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def get_auto_start_state():
    if sys.platform == "darwin":
        plist_path = os.path.expanduser(f"~/Library/LaunchAgents/{APP_ID}.plist")
        return os.path.exists(plist_path)
    if sys.platform != "win32":
        return False
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY,
                           0, winreg.KEY_READ) as key:
            value, _ = winreg.QueryValueEx(key, APP_ID)
            exe_path = sys.executable
            return value == exe_path
    except (FileNotFoundError, OSError):
        return False


def set_auto_start(enable):
    if sys.platform == "darwin":
        plist_dir = os.path.expanduser("~/Library/LaunchAgents")
        plist_path = os.path.join(plist_dir, f"{APP_ID}.plist")
        if enable:
            if not os.path.exists(plist_dir):
                os.makedirs(plist_dir, exist_ok=True)
            # Use the .app bundle path if frozen, otherwise use python path
            if getattr(sys, 'frozen', False):
                # sys.executable is inside Contents/MacOS/
                app_path = os.path.abspath(os.path.join(os.path.dirname(sys.executable), "../../.."))
                args_str = f"        <string>/usr/bin/open</string>\n        <string>-W</string>\n        <string>-n</string>\n        <string>{app_path}</string>"
            else:
                args_str = f"        <string>{sys.executable}</string>\n        <string>{os.path.abspath(sys.argv[0])}</string>"

            plist_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{APP_ID}</string>
    <key>ProgramArguments</key>
    <array>
{args_str}
    </array>
    <key>RunAtLoad</key>
    <true/>
</dict>
</plist>"""
            try:
                with open(plist_path, "w") as f:
                    f.write(plist_content)
                log(f"Auto-start enabled (macOS): {plist_path}")
            except Exception as e:
                log(f"Failed to enable auto-start: {e}")
        else:
            if os.path.exists(plist_path):
                try:
                    os.remove(plist_path)
                    log("Auto-start disabled (macOS)")
                except Exception as e:
                    log(f"Failed to disable auto-start: {e}")
        return

    if sys.platform != "win32":
        return
    exe_path = sys.executable
    try:
        import winreg
        if enable:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY,
                               0, winreg.KEY_SET_VALUE) as key:
                winreg.SetValueEx(key, APP_ID, 0, winreg.REG_SZ, exe_path)
            log(f"Auto-start enabled: {exe_path}")
        else:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY,
                               0, winreg.KEY_SET_VALUE) as key:
                winreg.DeleteValue(key, APP_ID)
            log("Auto-start disabled")
    except FileNotFoundError:
        if enable:
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as key:
                winreg.SetValueEx(key, APP_ID, 0, winreg.REG_SZ, exe_path)
            log(f"Auto-start enabled (key created): {exe_path}")
    except OSError:
        pass
