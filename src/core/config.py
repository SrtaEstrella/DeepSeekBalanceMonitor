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

from src.core.paths import APP_NAME, APP_ID, CONFIG_DIR, CONFIG_FILE, LOG_FILE, DB_FILE, log
from src.platforms.registry import get_platform
from src.core.secure_settings import (
    read_api_key, store_api_key, delete_api_credentials,
    read_api_key_for_id, store_api_key_for_id,
)

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

DEFAULT_CONFIG = {
    "api_key": "",  # legacy single-key, migrated to apis[0] on first load
    "apis": [],
    "preferred_api_id": "",
    "interval_minutes": 10,
    "fetch_mode": "parallel",     # "parallel" = all APIs each poll; "onehot" = preferred only
    "threshold_yuan": 1.0,
    "threshold_package_percent": 10,  # for package mode (remaining %)
    "daily_spend_line_yuan": 20,      # payg: single-day spend that flips the icon
    "daily_spend_line_percent": 10,   # package: single-day quota usage that flips it
    "daily_spend_alert_enabled": False,
    "language": "zh",
    "alert_mode": "once",    # "never" | "always" | "once"
    "api_alert_enabled": True,
    "peak_valley_alert_enabled": False,
    "retention_days": 180,
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
        "view_balance":     "⚡ 余额速览",
        "check_now":        "🔄 立即查询",
        "top_up":           "🌐 控制台",
        "history":          "📊 看板",
        "dashboard":        "📊 看板",
        "ledger":           "📅 流水",
        "manage":           "🗂 管理",
        "ledger_hint":      "API 流水记录：",
        "select_api_prompt": "请选择要查看的API",
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
        "icon_stroke_label": "图标描边",
        "settings_title":   "设置",
        "api_key_label":    "API Key：",
        "show_key":         "显示 API Key",
        "interval_label":   "查询间隔（分钟）：",
        "interval_hint":    "  （1 ~ 1440 分钟）",
        "fetch_mode_label": "查询模式：",
        "fetch_mode_parallel": "并发（全部 API）",
        "fetch_mode_onehot":  "单打（仅首选）",
        "threshold_label":  "余额预警线：",
        "threshold_mode_label": "按量",
        "threshold_pkg_mode_label": "套餐",
        "threshold_hint":   "  低于此值时托盘图标显示红色预警",
        "spend_line_label": "单日消耗线：",
        "spend_line_hint":  "  单日消耗达到此值时托盘图标显示橙色预警",
        "language_label":   "语言 / Language：",
        "save":             "保存",
        "cancel":           "取消",
        "warn_title":       "警告",
        "warn_no_key":      "API Key 不能为空！",
        "low_bal_title":    "⚠ DeepSeek 余额不足",
        "low_bal_msg":      "当前余额仅剩 {balance}，已低于您设置的提醒阈值 {threshold}。\n请及时充值！",
        "api_degraded_title": "⚠️ DeepSeek API 服务异常",
        "api_degraded_msg":   "检测到 API 服务状态异常，可能影响余额查询和正常调用。",
        "api_recovered_title": "✅ DeepSeek API 服务恢复",
        "api_recovered_msg":   "API 服务已恢复正常。",
        "bal_empty_msg":    "尚未查询到余额，请稍后或点击「立即查询」",
        "bal_title":        "{name} 余额：",
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
        "open_log_label":     "打开运行日志…",
        "api_alert_label":    "API 服务状态变化提醒",
        "spend_alert_label":  "单日消耗过快提醒",
        "spend_alert_title": "⚠ 单日消耗过快",
        "peak_alert_peak":   "🐳▲ 梁文峰时段开始（计价 2x）",
        "peak_alert_valley": "🐳▼ 梁文谷时段开始（半价）",
        "spend_alert_msg":   "今日已消耗 {value}（预警线 {line}），请注意控制节奏。",
        "auto_start_label": "开机自动启动",
        "alert_mode_label": "低余额提醒",
        "alert_check_label": "低额提醒",
        "spend_check_label":  "过快提醒",
        "peak_valley_alert_label": "DeepSeek 峰谷时提醒",
        "alert_mode_never":  "不提醒",
        "alert_mode_always": "持续提醒",
        "alert_mode_once":   "仅提醒一次",
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
        "unsaved_confirm":   "设置已更改，是否保存？",
        "other_settings":    "其他设置",
        "not_enough_data":   "数据不足，无法计算",
        "load_more":         "加载更多 ▼",
        "all_loaded":        "已加载全部",
        "export_csv_btn":    "导出 CSV",
        "export_msg":        "已导出 {n} 条记录",
        "filter_btn":        "筛选",
        "cancel_btn":        "取消",
        "remaining_dh":      "{d} 天 {h} 小时",
        "remaining_h":       "{h} 小时",
        "remaining_lt1h":    "不足 1 小时",
        "est_prefix":        "预计可用",
        "ago_just":          "刚刚",
        "ago_min":           "{n} 分钟前",
        "ago_hr":            "{n} 小时前",
        "hex_invalid":       "自定义颜色需为 6 位 hex 值。",
        "rate_line":         "忙时消耗 {rate:.2f}/小时  |  {prefix}忙时 {remaining} 小时",
        "validate_invalid":  "输入值不合法，请检查各字段。",
        "validate_interval": "查询间隔需在 1 ~ 1440 分钟之间。",
        "validate_threshold": "预警阈值需在 0 ~ 10000 之间。",
        "validate_retention": "保留天数需在 1 ~ 3650 之间。",
        "rms_fallback":      "📊 预计可用 --",
        # v2 multi-API
        "api_management":    "API 管理",
        "platform_label":    "平台：",
        "platform_deepseek": "DeepSeek",
        "platform_opencode_go": "OpenCode Go",
        "api_name_label":    "名称：",
        "api_name_hint":     "默认 平台-序号",
        "api_id_label":      "ID：",
        "add_api":           "添加 API",
        "set_preferred_btn": "设为首选",
        "already_preferred": "已是首选",
        "edit_api":          "编辑",
        "delete_api":        "删除",
        "preferred_api_label": "首选展示项：",
        "no_apis":           "暂无 API，请先添加",
        "confirm_delete":    "确定删除 {name} 吗？",
        "api_exists":        "API 已存在",
        "delete_success":    "已删除 {name}",
        "select_api":        "选择 API：",
        "key_stored_hint": "已加密存储，若需修改请填写新值",
        "billing_period_label": "展示周期：",
        "billing_period_hint": "用于托盘图标与速率统计的窗口维度",
        "api_select":        "🔀 API选择",
        "add_edit_api":      "➕ 添加/编辑…",
        "win_5h":            "5h滚动",
        "win_weekly":        "每周",
        "win_monthly":       "每月",
        "pkg_rate_line":     "忙时 {rate:.2f}%{unit}/h | 剩余 {remaining}h",
        "remaining_pct":     "{pct:.0f}% 剩余",
        "remaining_pct_fine":  "{pct:.2f}% 剩余",
        "col_5h":            "5h 余额%",
        "col_weekly":        "周余额%",
        "col_monthly":       "月余额%",
        "preview_ok":        "正常",
        "preview_low":       "低额",
        "preview_fast":      "过快",
        "preview_degraded":  "异常",
        "preview_nodata":    "等待",
        "block_balance":     "余额变动",
        "block_daily":       "每日消耗",
        "block_dist":        "时段分布",
        "days_7":            "7天",
        "days_30":           "30天",
        "days_180":          "180天",
    },
    "en": {
        "total_balance":    "Total balance",
        "last_check":       "Last check:",
        "not_checked":      "Not checked",
        "error_no_key":     "No API Key configured",
        "view_balance":     "⚡ Balance Glance",
        "check_now":        "🔄 Check Now",
        "top_up":           "🌐 Console",
        "history":          "📊 Dashboard",
        "dashboard":        "📊 Dashboard",
        "ledger":           "📅 Ledger",
        "manage":           "🗂 Manage",
        "ledger_hint":      "API Records:",
        "select_api_prompt": "Select an API to view",
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
        "icon_stroke_label": "Icon stroke",
        "settings_title":   "Settings",
        "api_key_label":    "API Key:",
        "show_key":         "Show API key",
        "interval_label":   "Check interval (min):",
        "interval_hint":    "  (1 ~ 1440 min)",
        "fetch_mode_label": "Fetch mode:",
        "fetch_mode_parallel": "Parallel (all APIs)",
        "fetch_mode_onehot":  "One-hot (preferred only)",
        "threshold_label":  "Low balance threshold:",
        "threshold_mode_label": "PAYG",
        "threshold_pkg_mode_label": "Package",
        "threshold_hint":   "  Icon turns red when balance drops below this value",
        "spend_line_label": "Daily spend line:",
        "spend_line_hint":  "  Icon turns orange when single-day usage reaches this value",
        "language_label":   "Language / 语言：",
        "save":             "Save",
        "cancel":           "Cancel",
        "warn_title":       "Warning",
        "warn_no_key":      "API Key cannot be empty!",
        "low_bal_title":    "⚠ DeepSeek Low Balance",
        "low_bal_msg":      "Balance is only {balance}, below your alert threshold of {threshold}.\nPlease top up!",
        "api_degraded_title": "⚠️ DeepSeek API Degraded",
        "api_degraded_msg":   "API service status has changed — balance queries and normal usage may be affected.",
        "api_recovered_title": "✅ DeepSeek API Recovered",
        "api_recovered_msg":   "API service is back to normal.",
        "bal_empty_msg":    "No balance data yet. Please wait or click 'Check Now'.",
        "bal_title":        "{name} Balance:",
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
        "open_log_label":     "Open runtime log...",
        "api_alert_label":    "API service status alerts",
        "spend_alert_label":  "Daily spend too fast alert",
        "spend_alert_title": "⚠ Daily spend too fast",
        "peak_alert_peak":   "△ DeepSeek peak hours started (2x pricing)",
        "peak_alert_valley": "▽ DeepSeek off-peak hours started (half price)",
        "spend_alert_msg":   "Today: {value} (threshold {line}). Consider slowing down.",
        "auto_start_label": "Auto-start on boot",
        "alert_mode_label": "Low balance alert",
        "alert_check_label": "Low-balance alert",
        "spend_check_label":  "Fast-spend alert",
        "peak_valley_alert_label": "DeepSeek peak/off-peak reminder",
        "alert_mode_never":  "Never",
        "alert_mode_always": "Always",
        "alert_mode_once":   "Once",
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
        "unsaved_confirm":   "Settings changed. Save?",
        "other_settings":    "Other settings",
        "not_enough_data":   "Not enough data",
        "load_more":         "Load more ▼",
        "all_loaded":        "All loaded",
        "export_csv_btn":    "Export CSV",
        "export_msg":        "{n} records exported",
        "filter_btn":        "Filter",
        "cancel_btn":        "Cancel",
        "remaining_dh":      "{d}d {h}h",
        "remaining_h":       "{h}h",
        "remaining_lt1h":    "< 1h",
        "est_prefix":        "Est.",
        "ago_just":          "just now",
        "ago_min":           "{n} min ago",
        "ago_hr":            "{n} hr ago",
        "hex_invalid":       "Custom colors must be 6-digit hex values.",
        "rate_line":         "Busy: {rate:.2f}/hr  |  {prefix} busy {remaining}h",
        "validate_invalid":  "Invalid input. Please check all fields.",
        "validate_interval": "Check interval must be 1–1440 minutes.",
        "validate_threshold": "Threshold must be 0–10000.",
        "validate_retention": "Retention days must be 1–3650.",
        "rms_fallback":      "📊 --",
        "api_management":    "API Management",
        "platform_label":    "Platform:",
        "platform_deepseek": "DeepSeek",
        "platform_opencode_go": "OpenCode Go",
        "api_name_label":    "Name:",
        "api_name_hint":     "Default Platform-Idx",
        "api_id_label":      "ID:",
        "add_api":           "Add API",
        "set_preferred_btn": "Set as Preferred",
        "already_preferred": "Already Preferred",
        "edit_api":          "Edit",
        "delete_api":        "Delete",
        "preferred_api_label": "Preferred Display:",
        "no_apis":           "No APIs, please add one",
        "confirm_delete":    "Delete {name}?",
        "api_exists":        "API already exists",
        "delete_success":    "Deleted {name}",
        "select_api":        "Select API:",
        "package_display_period_label": "Package display period:",
        "key_stored_hint": "Encrypted, fill new value to change",
        "billing_period_label": "Display Period:",
        "billing_period_hint": "Window dimension for tray icon and rate statistics",
        "api_select":        "🔀 API Select",
        "add_edit_api":      "➕ Add/Edit…",
        "win_5h":            "5h rolling",
        "win_weekly":        "Weekly",
        "win_monthly":       "Monthly",
        "pkg_rate_line":     "Busy {rate:.2f}%{unit}/h | {remaining}h left",
        "remaining_pct":     "{pct:.0f}% left",
        "remaining_pct_fine":  "{pct:.2f}% left",
        "col_5h":            "5h Remaining%",
        "col_weekly":        "Weekly Remaining%",
        "col_monthly":       "Monthly Remaining%",
        "preview_ok":        "OK",
        "preview_low":       "Low",
        "preview_fast":     "Fast",
        "preview_degraded":  "Deg",
        "preview_nodata":    "...",
        "block_balance":     "Balance Trend",
        "block_daily":       "Daily Usage",
        "block_dist":        "Hourly Distribution",
        "days_7":            "7d",
        "days_30":           "30d",
        "days_180":          "180d",
    },
}

def T(key: str, lang: str = "zh", **kwargs) -> str:
    table = _T.get(lang, _T["zh"])
    text = table.get(key)
    if text is None:
        text = _T["zh"].get(key, key)
    return text.format(**kwargs) if kwargs else text


def format_ago(last_check, lang: str, now=None) -> str:
    """Humanized 'X ago' from a datetime. Shared by tray/history/rainmeter."""
    mins = int(((now or datetime.now()) - last_check).total_seconds() / 60)
    if mins < 1:
        return T("ago_just", lang)
    if mins < 60:
        return T("ago_min", lang, n=mins)
    return T("ago_hr", lang, n=mins // 60)

# ─── Config I/O ──────────────────────────────────────────────────
def _resolve_api_key(cfg: dict):
    """Resolve API key from encrypted storage only."""
    key = read_api_key()
    if key:
        cfg["api_key"] = key


def load_config() -> dict:
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                raw = json.load(f)
                cfg = {**DEFAULT_CONFIG, **raw}
            # normalize apis
            if not isinstance(cfg.get("apis"), list):
                cfg["apis"] = []
            # migrate legacy single key if needed
            migrated = _migrate_legacy_api(cfg)
            # ensure each api has mode
            mode_changed = _ensure_api_modes(cfg)
            # ensure preferred_api_id is valid
            apis = cfg.get("apis") or []
            pref = cfg.get("preferred_api_id", "")
            if apis and not any(a.get("id") == pref for a in apis):
                cfg["preferred_api_id"] = apis[0]["id"]
            if not apis:
                cfg["preferred_api_id"] = ""
            # ensure package settings defaults
            if "threshold_package_percent" not in cfg:
                cfg["threshold_package_percent"] = DEFAULT_CONFIG["threshold_package_percent"]
            _resolve_api_key(cfg)
            # also resolve preferred api's key into cfg["api_key"] for backward compat
            if apis and cfg.get("preferred_api_id"):
                pref_api = next((a for a in apis if a["id"] == cfg["preferred_api_id"]), None)
                if pref_api and pref_api.get("platform") == "deepseek":
                    k = read_api_key_for_id(pref_api["id"])
                    if k:
                        cfg["api_key"] = k
            if migrated or mode_changed:
                # persist migrated apis (will clear api_key plaintext)
                try:
                    save_config(cfg)
                except Exception:
                    pass
            return cfg
        except Exception as e:
            log(f"Failed to load config: {e}")

    cfg = DEFAULT_CONFIG.copy()
    # ensure apis list
    if not isinstance(cfg.get("apis"), list):
        cfg["apis"] = []
    _migrate_legacy_api(cfg)
    mode_changed2 = _ensure_api_modes(cfg)
    if mode_changed2:
        try:
            save_config(cfg)
        except Exception:
            pass
    _resolve_api_key(cfg)
    return cfg


def save_config(config: dict) -> None:
    try:
        safe = {**config}
        # API key is never written to config.json — encrypted storage only
        safe["api_key"] = ""
        # Drop legacy keys that are no longer used
        safe.pop("api_key_enc", None)
        safe.pop("currency", None)
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(safe, f, indent=2, ensure_ascii=False)
        log("Config saved")
    except Exception as e:
        log(f"Failed to save config: {e}")


# ─── Multi-API helpers (v2) ────────────────────────────────────────
def _generate_api_id() -> str:
    import uuid
    return uuid.uuid4().hex[:8]

def _get_next_api_name(platform: str, apis: list) -> str:
    pmeta = get_platform(platform)
    prefix = pmeta.display_name if pmeta else platform
    # count existing with same platform
    n = sum(1 for a in apis if a.get("platform") == platform) + 1
    # ensure uniqueness
    existing_names = {a.get("name") for a in apis}
    name = f"{prefix}-{n}"
    while name in existing_names:
        n += 1
        name = f"{prefix}-{n}"
    return name

def _migrate_legacy_api(cfg: dict) -> bool:
    """If apis is empty but legacy api_key exists (from secure_settings or config), create first DeepSeek api."""
    if cfg.get("apis"):
        return False
    legacy_key = cfg.get("api_key", "").strip()
    if not legacy_key:
        legacy_key = (read_api_key() or "").strip()
    if not legacy_key:
        return False
    # also check for legacy opencode_go global (if any) — not migrated as api, keep separate
    api_id = _generate_api_id()
    name = _get_next_api_name("deepseek", [])
    cfg["apis"] = [{"id": api_id, "platform": "deepseek", "name": name, "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}]
    cfg["preferred_api_id"] = api_id
    # store the legacy key under new per-id key as well
    store_api_key_for_id(api_id, legacy_key)
    store_api_key(legacy_key)
    # clear legacy plaintext
    cfg["api_key"] = legacy_key  # will be cleared on save, but keep for current load's api_key
    log(f"Migrated legacy api_key to {name} ({api_id})")
    return True

def _ensure_api_modes(cfg: dict) -> bool:
    changed = False
    for api in cfg.get("apis") or []:
        if "mode" not in api or api.get("mode") not in ("payg", "package"):
            plat = api.get("platform", "")
            if plat == "opencode_go":
                api["mode"] = "package"
            else:
                api["mode"] = "payg"
            changed = True
    return changed

def get_apis(cfg: dict | None = None) -> list:
    if cfg is None:
        cfg = load_config()
    return list(cfg.get("apis") or [])

def get_api_by_id(api_id: str, cfg: dict | None = None):
    if cfg is None:
        cfg = load_config()
    for a in cfg.get("apis") or []:
        if a.get("id") == api_id:
            return a
    return None

def get_preferred_api(cfg: dict | None = None):
    if cfg is None:
        cfg = load_config()
    pref = cfg.get("preferred_api_id")
    if pref:
        api = get_api_by_id(pref, cfg)
        if api:
            return api
    apis = get_apis(cfg)
    return apis[0] if apis else None

def create_api(platform: str, name: str | None = None, api_key: str | None = None, mode: str | None = None, billing_period: str | None = None) -> str:
    cfg = load_config()
    apis = list(cfg.get("apis") or [])
    if not name or not name.strip():
        name = _get_next_api_name(platform, apis)
    name = name.strip()
    # ensure unique name
    existing = {a.get("name") for a in apis}
    base = name
    suffix = 1
    while name in existing:
        name = f"{base} ({suffix})"
        suffix += 1
    api_id = _generate_api_id()
    # determine mode from platform registry
    if not mode:
        from src.platforms.registry import get_platform as _gp
        pmeta = _gp(platform)
        mode = pmeta.default_mode if pmeta else "payg"
    entry = {"id": api_id, "platform": platform, "name": name, "mode": mode, "billing_period": billing_period or "", "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
    apis.append(entry)
    cfg["apis"] = apis
    if not cfg.get("preferred_api_id"):
        cfg["preferred_api_id"] = api_id
    # store credentials — unified: all platforms use api_key under api:{id}:key
    if api_key:
        store_api_key_for_id(api_id, api_key.strip())
        if cfg.get("preferred_api_id") == api_id:
            store_api_key(api_key.strip())
            cfg["api_key"] = api_key.strip()
    save_config(cfg)
    log(f"Created API {name} ({platform}:{api_id})")
    return api_id

def update_api(api_id: str, name: str | None = None, api_key: str | None = None, platform: str | None = None, mode: str | None = None, billing_period: str | None = None) -> bool:
    cfg = load_config()
    apis = list(cfg.get("apis") or [])
    idx = next((i for i, a in enumerate(apis) if a.get("id") == api_id), None)
    if idx is None:
        return False
    entry = apis[idx]
    if name is not None and name.strip():
        entry["name"] = name.strip()
    if platform:
        entry["platform"] = platform
    if mode:
        entry["mode"] = mode
    if billing_period is not None:
        entry["billing_period"] = billing_period
    # ensure mode default if still missing
    if "mode" not in entry or entry["mode"] not in ("payg", "package"):
        from src.platforms.registry import get_platform as _gp
        _pmeta = _gp(entry.get("platform", ""))
        entry["mode"] = _pmeta.default_mode if _pmeta else "payg"
    apis[idx] = entry
    cfg["apis"] = apis
    # all platforms store their key under api:{id}:key (unified credential scheme)
    if api_key is not None:
        store_api_key_for_id(api_id, api_key.strip())
        if cfg.get("preferred_api_id") == api_id:
            store_api_key(api_key.strip())
            cfg["api_key"] = api_key.strip()
    save_config(cfg)
    log(f"Updated API {api_id}")
    return True

def delete_api(api_id: str) -> bool:
    cfg = load_config()
    apis = [a for a in (cfg.get("apis") or []) if a.get("id") != api_id]
    if len(apis) == len(cfg.get("apis") or []):
        return False
    cfg["apis"] = apis
    # adjust preferred
    if cfg.get("preferred_api_id") == api_id:
        cfg["preferred_api_id"] = apis[0]["id"] if apis else ""
        if cfg["preferred_api_id"]:
            pref = next((a for a in apis if a["id"] == cfg["preferred_api_id"]), None)
            if pref and pref.get("platform") == "deepseek":
                k = read_api_key_for_id(pref["id"])
                if k:
                    store_api_key(k)
                    cfg["api_key"] = k
                else:
                    cfg["api_key"] = ""
            else:
                cfg["api_key"] = ""
        else:
            cfg["api_key"] = ""
    delete_api_credentials(api_id)
    save_config(cfg)
    # also delete history for this api_id
    try:
        import sqlite3
        from src.core.config import DB_FILE
        if DB_FILE.exists():
            conn = sqlite3.connect(str(DB_FILE))
            conn.execute("DELETE FROM balance_history WHERE api_id=?", (api_id,))
            conn.execute("DELETE FROM package_history WHERE api_id=?", (api_id,))
            conn.commit()
            conn.close()
    except Exception:
        pass
    log(f"Deleted API {api_id}")
    return True

def set_preferred_api(api_id: str) -> bool:
    cfg = load_config()
    if not any(a.get("id") == api_id for a in cfg.get("apis") or []):
        return False
    cfg["preferred_api_id"] = api_id
    # sync global api_key for backward compat
    api = next(a for a in cfg["apis"] if a["id"] == api_id)
    if api.get("platform") == "deepseek":
        k = read_api_key_for_id(api_id)
        if k:
            store_api_key(k)
            cfg["api_key"] = k
        else:
            cfg["api_key"] = ""
    else:
        cfg["api_key"] = ""
    save_config(cfg)
    log(f"Preferred API set to {api_id}")
    return True
