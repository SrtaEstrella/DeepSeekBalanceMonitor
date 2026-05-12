"""
Constants, i18n, logging, config load/save, DPI awareness.
Imported by all other modules.
"""
import ctypes
import json
import os
import sys
from datetime import datetime
from pathlib import Path

# ─── High-DPI Awareness (before any GUI) ──────────────────────────
def _set_dpi_awareness():
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass

_set_dpi_awareness()

# ─── Constants ────────────────────────────────────────────────────
APP_NAME = "DeepSeek Balance Monitor"
APP_ID   = "deepseek-balance-monitor"

if sys.platform == "darwin":
    CONFIG_DIR = Path.home() / "Library" / "Application Support" / APP_NAME
else:
    CONFIG_DIR = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / APP_NAME

CONFIG_FILE = CONFIG_DIR / "config.json"
LOG_FILE    = CONFIG_DIR / "app.log"
DB_FILE     = CONFIG_DIR / "balance_history.db"

DEFAULT_CONFIG = {
    "api_key": "",
    "interval_minutes": 10,
    "threshold_yuan": 1.0,
    "language": "zh",
    "alert_mode": "once",    # "never" | "always" | "once"
    "api_alert_enabled": True,
    "retention_days": 30,
    "theme": "default",
    "icon_colors": {},
    "icon_stroke": False,
    "export_path": "",
    "http_proxy": "",
    "proxy_enabled": False,
    "rainmeter_enabled": True,
    "auto_start": False,
}

# ─── i18n ─────────────────────────────────────────────────────────
_T = {
    "zh": {
        "total_balance":    "总余额",
        "last_check":       "上次查询：",
        "not_checked":      "尚未查询",
        "error_no_key":     "未配置 API Key",
        "view_balance":     "📋 查看余额",
        "check_now":        "🔄 立即查询",
        "top_up":           "💰 充值",
        "history":          "📊 历史记录",
        "settings":         "⚙️ 设置…",
        "quit":             "❌ 退出",
        "dev_tools":        "🛠 开发者",
        "theme_label":      "图标主题：",
        "theme_default":    "默认",
        "theme_contrast":   "高对比",
        "theme_bright":     "明亮",
        "theme_dark_mode":  "暗色模式",
        "theme_mono":       "纯灰度",
        "theme_custom":     "自定义",
        "icon_stroke_label": "图标描边：",
        "settings_title":   "设置",
        "api_key_label":    "DeepSeek API Key:",
        "show_key":         "显示 API Key",
        "interval_label":   "查询间隔（分钟）：",
        "interval_hint":    "  （1 ~ 1440 分钟）",
        "threshold_label":  "余额预警线：",
        "threshold_hint":   "  低于此值时托盘图标显示红色预警",
        "language_label":   "语言 / Language：",
        "save":             "保存",
        "cancel":           "取消",
        "warn_title":       "警告",
        "warn_no_key":      "API Key 不能为空！",
        "exit_no_key":      "请在下次启动时配置 API Key。程序退出。",
        "low_bal_title":    "⚠ DeepSeek 余额不足",
        "low_bal_msg":      "当前余额仅剩 {balance}，已低于您设置的提醒阈值 {threshold}。\n请及时充值！",
        "api_degraded_title": "⚠️ DeepSeek API 服务异常",
        "api_degraded_msg":   "检测到 API 服务状态异常，可能影响余额查询和正常调用。",
        "api_recovered_title": "✅ DeepSeek API 服务恢复",
        "api_recovered_msg":   "API 服务已恢复正常。",
        "bal_empty_msg":    "尚未查询到余额，请稍后或点击「立即查询」",
        "bal_title":        "DeepSeek 余额：",
        "bal_line":         "{balance} {code}（充值 {topped}，赠送 {granted}）",
        "tooltip_balance":  "总余额: {total} {code}",
        "tooltip_error":    "错误：{error}",
        "tooltip_checking": "查询中…",
        "bal_error_msg":    "查询出错：{error}",

        "status_none":        "服务正常",
        "status_minor":       "轻微异常",
        "status_major":       "严重异常",
        "status_critical":    "关键不可用",
        "status_maintenance": "维护中",
        "status_unknown":     "服务状态未知",
        "service_status":     "API 服务状态：",
        "retention_label":    "日志和记录保留天数：",
        "api_alert_label":    "API 服务状态变化提醒",
        "auto_start_label": "开机自动启动：",
        "alert_mode_label": "低余额提醒：",
        "alert_mode_never":  "不提醒",
        "alert_mode_always": "持续提醒",
        "alert_mode_once":   "仅提醒一次",
        "currency":          "偏好货币",
        "tab_chart":         "图表",
        "tab_settings":      "设置",
        "balance_history":   "余额历史",
        "history_table":     "历史记录",
        "th_time":           "时间",
        "th_currency":       "币种",
        "th_total":          "总额",
        "th_topped":         "充值",
        "th_granted":        "赠送",
        "th_status":         "状态",
        "export_label":      "导出路径：",
        "export_browse":     "浏览",
        "proxy_enable":      "启用 HTTP/HTTPS 代理",
        "proxy_label":       "HTTP/HTTPS 代理：",
        "proxy_placeholder":  "代理地址",
        "proxy_hint":        "留空则不使用",
        "rainmeter_label":   "启用 Rainmeter 接口",
        "retention_hint":    "（1 ~ 3650 天）",
        "unsaved_changes":   "有未保存的更改。确定要放弃吗？",
        "other_settings":    "其他设置",
        "not_enough_data":   "数据不足，无法计算",
    },
    "en": {
        "total_balance":    "Total balance",
        "last_check":       "Last check:",
        "not_checked":      "Not checked",
        "error_no_key":     "No API Key configured",
        "view_balance":     "📋 View Balance",
        "check_now":        "🔄 Check Now",
        "top_up":           "💰 Top Up",
        "history":          "📊 History",
        "settings":         "⚙️ Settings…",
        "quit":             "❌ Quit",
        "dev_tools":        "🛠 Dev Tools",
        "theme_label":      "Icon theme:",
        "theme_default":    "Default",
        "theme_contrast":   "High Contrast",
        "theme_bright":     "Bright",
        "theme_dark_mode":  "Dark Mode",
        "theme_mono":       "Monochrome",
        "theme_custom":     "Custom",
        "icon_stroke_label": "Icon stroke: ",
        "settings_title":   "Settings",
        "api_key_label":    "DeepSeek API key:",
        "show_key":         "Show API key",
        "interval_label":   "Check interval (min):",
        "interval_hint":    "  (1 ~ 1440 min)",
        "threshold_label":  "Low balance threshold:",
        "threshold_hint":   "  Icon turns red when balance drops below this value",
        "language_label":   "Language / 语言：",
        "save":             "Save",
        "cancel":           "Cancel",
        "warn_title":       "Warning",
        "warn_no_key":      "API Key cannot be empty!",
        "exit_no_key":      "Please configure an API Key on next launch. Exiting.",
        "low_bal_title":    "⚠ DeepSeek Low Balance",
        "low_bal_msg":      "Balance is only {balance}, below your alert threshold of {threshold}.\nPlease top up!",
        "api_degraded_title": "⚠️ DeepSeek API Degraded",
        "api_degraded_msg":   "API service status has changed — balance queries and normal usage may be affected.",
        "api_recovered_title": "✅ DeepSeek API Recovered",
        "api_recovered_msg":   "API service is back to normal.",
        "bal_empty_msg":    "No balance data yet. Please wait or click 'Check Now'.",
        "bal_title":        "DeepSeek Balance:",
        "bal_line":         "{balance} {code} (Topped {topped}, Granted {granted})",
        "tooltip_balance":  "Balance: {total} {code}",
        "tooltip_error":    "Error: {error}",
        "tooltip_checking": "Checking…",
        "bal_error_msg":    "Fetch error: {error}",

        "status_none":        "All Systems Operational",
        "status_minor":       "Minor Outage",
        "status_major":       "Major Outage",
        "status_critical":    "Critical Outage",
        "status_maintenance": "Under Maintenance",
        "status_unknown":     "Status Unknown",
        "service_status":     "API Status:",
        "retention_label":    "Log & record retention (days): ",
        "api_alert_label":    "API service status alerts",
        "auto_start_label": "Auto-start on boot: ",
        "alert_mode_label": "Low balance alert:",
        "alert_mode_never":  "Never",
        "alert_mode_always": "Always",
        "alert_mode_once":   "Once",
        "currency":          "Primary currency",
        "tab_chart":         "Chart",
        "tab_settings":      "Settings",
        "balance_history":   "Balance history",
        "history_table":     "History records",
        "th_time":           "Time",
        "th_currency":       "Curr",
        "th_total":          "Total",
        "th_topped":         "Topped",
        "th_granted":        "Granted",
        "th_status":         "Status",
        "export_label":      "Export path:",
        "export_browse":     "Browse",
        "proxy_enable":      "Enable proxy",
        "proxy_label":       "HTTP/HTTPS proxy:",
        "proxy_placeholder":  "Proxy address",
        "proxy_hint":        "Leave blank to disable",
        "rainmeter_label":   "Enable Rainmeter interface",
        "retention_hint":    "(1 ~ 3650 days)",
        "unsaved_changes":   "Unsaved changes will be lost. Continue?",
        "other_settings":    "Other settings",
        "not_enough_data":   "Not enough data",
    },
}

def T(key: str, lang: str = "zh", **kwargs) -> str:
    table = _T.get(lang, _T["zh"])
    text = table.get(key)
    if text is None:
        text = _T["zh"].get(key, key)
    return text.format(**kwargs) if kwargs else text

# ─── Logging ─────────────────────────────────────────────────────
def log(msg: str):
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"[{ts}] {msg}\n")
    except Exception:
        pass

# ─── Config I/O ──────────────────────────────────────────────────
def _resolve_api_key(cfg: dict):
    """Resolve API key: secure_settings → credential_store → config.json (migration)."""
    try:
        from src.secure_settings import read_api_key
        key = read_api_key()
        if key:
            cfg["api_key"] = key
            return
    except ImportError:
        pass
    try:
        from src.credential_store import read_credential
        key = read_credential()
        if key:
            cfg["api_key"] = key
            # Migrate from credential_store to secure_settings
            try:
                from src.secure_settings import store_api_key
                store_api_key(key)
            except ImportError:
                pass
    except ImportError:
        pass


def load_config() -> dict:
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                cfg = {**DEFAULT_CONFIG, **json.load(f)}
            if "enable_alerts" in cfg:
                if "alert_mode" not in cfg or cfg["alert_mode"] == DEFAULT_CONFIG["alert_mode"]:
                    cfg["alert_mode"] = "always" if cfg["enable_alerts"] else "never"
                del cfg["enable_alerts"]
            _resolve_api_key(cfg)
            return cfg
        except Exception as e:
            log(f"Failed to load config: {e}")

    cfg = DEFAULT_CONFIG.copy()
    _resolve_api_key(cfg)
    return cfg

def _has_secure_storage():
    try:
        from src.secure_settings import store_api_key
        return True
    except ImportError:
        pass
    try:
        from src.credential_store import store_credential
        return True
    except ImportError:
        pass
    return False


def save_config(config: dict) -> None:
    try:
        safe = {**config}
        safe.pop("enable_alerts", None)
        if _has_secure_storage():
            safe["api_key"] = ""
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(safe, f, indent=2, ensure_ascii=False)
        log("Config saved")
    except Exception as e:
        log(f"Failed to save config: {e}")
