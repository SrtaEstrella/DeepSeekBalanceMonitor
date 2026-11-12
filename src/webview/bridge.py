"""JsApi — Python-JavaScript bridge for WebView settings page."""

import os
import sys

from src.core.config import load_config, save_config, T, log, CONFIG_DIR

SENTINEL_FILE = CONFIG_DIR / ".settings_changed"
PID_FILE = CONFIG_DIR / "settings.pid"


# i18n keys needed by the settings frontend
I18N_KEYS = [
    "settings_title",
    "api_key_label", "show_key",
    "interval_label", "interval_hint",
    "threshold_label", "threshold_hint",
    "alert_mode_label", "alert_mode_never", "alert_mode_always", "alert_mode_once",
    "api_alert_label",
    "theme_label", "theme_default", "theme_contrast", "theme_bright",
    "theme_dark_mode", "theme_mono", "theme_custom",
    "icon_stroke_label",
    "language_label",
    "retention_label", "retention_hint",
    "auto_start_label",
    "export_label", "export_browse",
    "proxy_label", "proxy_hint",
    "save", "cancel", "warn_title", "warn_no_key",
    "tab_chart", "tab_settings", "balance_history", "history_table",
    "th_time", "th_currency", "th_total", "th_topped", "th_granted", "th_status",
    "unsaved_changes", "other_settings", "top_up",
    "service_status", "status_none", "status_minor", "status_major", "status_critical", "status_maintenance", "status_unknown"
]


class JsApi:
    """Exposed to JavaScript via pywebview's js_api mechanism."""

    def __init__(self):
        self._window = None

    def set_window(self, window):
        self._window = window

    def open_url(self, url: str):
        import webbrowser
        webbrowser.open(url)

    # ---- Settings ----

    def get_settings(self):
        try:
            cfg = load_config()
            return {"success": True, "data": cfg, "platform": sys.platform}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def save_settings(self, settings):
        try:
            # The WebView page predates accounts, quiet hours and the other
            # v2.4 fields; merge what it sends over the current file so a save
            # from this window cannot drop them.
            settings = {**load_config(), **settings}
            api_key = settings.get("api_key", "").strip()
            if not api_key:
                return {"success": False, "error": T("warn_no_key", settings.get("language", "zh"))}

            interval = int(settings.get("interval_minutes", 10))
            if not (1 <= interval <= 1440):
                return {"success": False, "error": "Interval must be 1-1440"}

            # Unified encrypted storage — same as Windows tray
            try:
                from src.core.secure_settings import store_api_key
                store_api_key(api_key)
            except Exception:
                pass
            # Never persist plaintext in config.json
            settings["api_key"] = api_key
            save_config(settings)

            from src.core.app_state import set_auto_start
            set_auto_start(bool(settings.get("auto_start", False)))

            try:
                SENTINEL_FILE.parent.mkdir(parents=True, exist_ok=True)
                SENTINEL_FILE.touch()
            except Exception:
                pass

            log("WebView settings saved")
            return {"success": True}
        except Exception as e:
            log(f"WebView save error: {e}")
            return {"success": False, "error": str(e)}

    def get_i18n(self, lang):
        try:
            return {key: T(key, lang) for key in I18N_KEYS}
        except Exception:
            return {}

    def select_directory(self):
        """Open native directory picker."""
        if not self._window:
            return ""
        import webview
        result = self._window.create_file_dialog(webview.FOLDER_DIALOG)
        if result and isinstance(result, (list, tuple)) and len(result) > 0:
            return result[0]
        return ""

    def export_csv(self):
        """Export all balance records to CSV. Opens save dialog."""
        from src.core.storage import export_all_csv
        cfg = load_config()
        default_dir = cfg.get("export_path", "")
        if not self._window:
            return {"success": False, "error": "No window"}

        import webview
        result = self._window.create_file_dialog(
            webview.SAVE_DIALOG, directory=default_dir,
            save_filename="deepseek_balance.csv",
            file_types=("CSV Files (*.csv)",),
        )
        if not result:
            return {"success": False, "error": "Cancelled"}

        path = result if isinstance(result, str) else (result[0] if isinstance(result, (list, tuple)) and len(result) > 0 else None)
        if not path:
            return {"success": False, "error": "Cancelled"}

        count = export_all_csv(path)
        if count > 0:
            log(f"Exported {count} records to {path}")
            return {"success": True, "data": {"count": count, "path": path}}
        return {"success": False, "error": "No data exported"}

    # ---- History API ----

    def get_history_page(self, limit=100, offset=0):
        from src.core.storage import get_history_page as _get_history_page
        try:
            data = _get_history_page(limit, offset)
            return {"success": True, "data": data}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_consumption_rate(self):
        from src.core.storage import get_consumption_rate as _get_consumption_rate
        try:
            result = _get_consumption_rate()
            if result:
                hourly_rate, busy_hours, currency = result
                return {"success": True, "data": {
                    "hourly_rate": round(hourly_rate, 4),
                    "busy_hours": round(busy_hours, 1),
                    "currency": currency,
                }}
            return {"success": True, "data": None}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_api_status(self):
        from src.platforms.deepseek import fetch_service_status
        try:
            status = fetch_service_status()
            if status:
                indicator = str(status.get("indicator", "none")).lower()
                trans_key = f"status_{indicator}"
                return {"success": True, "data": status, "trans_key": trans_key}
            return {"success": False, "error": "Could not fetch status"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def save_pid(self):
        try:
            CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            with open(PID_FILE, "w") as f:
                f.write(str(os.getpid()))
        except Exception:
            pass

    def cleanup_pid(self):
        try:
            if PID_FILE.exists():
                PID_FILE.unlink()
        except Exception:
            pass
