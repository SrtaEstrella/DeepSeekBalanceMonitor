"""
Local widget interface — the dsmon2-widget contract on 127.0.0.1:18964.

The Rust 2.x desktop widget reads everything it shows from here: the JSON
payload `docs/INTERFACES.md` §1 defines, on the port that contract fixes. A
Python build implementing only that section drives the widget without the
widget changing a line.

The Rainmeter interface (port 17654, a different text shape) stays as it is
for the older widget — both run side by side; this one has no switch of its
own and listens whenever the application runs.
"""
import json
import threading
from datetime import date, datetime
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

from src.core.config import log
from src.core.secure_settings import read_api_key_for_id
from src.core.storage import (
    get_balance_series,
    get_consumption_rate,
    get_package_daily_usage,
    get_refined_remaining,
    get_today_total_spend,
)
from src.platforms.registry import get_platform

PORT = 18964

# The payload format version the widget speaks; it refuses unknown majors.
PAYLOAD_VERSION = 2
# Whose data this is, for the widget's diagnostics.
PROVIDER = {"name": "deepseek-balance-monitor", "version": "2.0.3 Dev"}

# `days` only affects the balance curve; anything else is a seven-day one.
DAYS = (1, 7, 30)
DEFAULT_DAYS = 7
# The heat map reads a month of daily figures, and the curve is thinned to
# this many points — the widget draws a sparkline, not the history page.
HEATMAP_DAYS = 30
MAX_SERIES_POINTS = 240

# MiniMax plans report their five-hour window as "5h", OpenCode Go as
# "rolling"; the payload always speaks the catalog's names.
_WINDOW_KEYS = {"5h": ("5h", "rolling"), "weekly": ("weekly",), "monthly": ("monthly",)}
_WINDOW_LABEL_KEYS = {"5h": "window_5h", "weekly": "window_weekly", "monthly": "window_monthly"}


def _parse_days(query: str) -> int:
    """The `days` parameter: one of 1/7/30, anything else reads as 7."""
    values = parse_qs(query).get("days")
    if not values:
        return DEFAULT_DAYS
    try:
        days = int(values[0])
    except (TypeError, ValueError):
        return DEFAULT_DAYS
    return days if days in DAYS else DEFAULT_DAYS


def _display_name(platform: str) -> str:
    meta = get_platform(platform)
    return meta.display_name if meta else platform


def _balance_entries(balances: dict) -> list:
    entries = []
    for currency, balance in balances.items():
        entries.append({
            "currency": currency,
            "total_balance": balance.get("total_balance", 0.0),
            "topped_up_balance": balance.get("topped_up_balance", 0.0),
            "granted_balance": balance.get("granted_balance", 0.0),
        })
    return entries


def _rate_entry(api_id: str) -> dict | None:
    """The burn rate, seven-day reading — the same one the status page shows."""
    try:
        result = get_consumption_rate(days=7, api_id=api_id)
    except Exception as e:
        log(f"Widget rate lookup failed: {e}")
        return None
    if not result:
        return None
    hourly_rate, busy_hours, currency = result
    return {
        "hourly_rate": hourly_rate,
        "busy_hours_left": busy_hours,
        "currency": currency,
    }


def _series(api_id: str, days: int) -> list:
    """The balance curve, thinned to what a sparkline needs (≤ 240 points)."""
    rows = get_balance_series(api_id, days)
    points = []
    for timestamp, total in rows:
        try:
            moment = datetime.strptime(timestamp, "%Y-%m-%d %H:%M:%S")
        except (TypeError, ValueError):
            continue
        points.append({"t": int(moment.timestamp()), "v": total})
    return _thinned(points)


def _thinned(points: list) -> list:
    """Evenly thins a series, always keeping the last point."""
    if len(points) <= MAX_SERIES_POINTS:
        return points
    step = -(-len(points) // MAX_SERIES_POINTS)  # ceil
    last = len(points) - 1
    return [point for index, point in enumerate(points) if index % step == 0 or index == last]


def _windows(api_id: str, platform: str, package_data: dict) -> list:
    """The plan's windows, refined the way the dashboard shows them.

    The weekly and monthly windows are refined from the five-hour spend where
    the platform's pools are known (OpenCode Go, GOAT); the crude integer is
    what the endpoint reports when they are not.
    """
    meta = get_platform(platform)
    names = meta.package_windows if meta else ["5h", "weekly", "monthly"]
    windows = []
    for name in names:
        data = None
        for key in _WINDOW_KEYS.get(name, (name,)):
            data = package_data.get(key)
            if data:
                break
        if not data:
            continue
        remaining = data.get("percent_remaining", 100 - data.get("usage_percent", 0))
        if name in ("weekly", "monthly"):
            refined = get_refined_remaining(api_id, target=name)
            if refined is not None:
                remaining = refined
        usage = max(0.0, min(100.0, 100.0 - remaining))
        windows.append({
            "name_key": _WINDOW_LABEL_KEYS.get(name, name),
            "usage_percent": round(usage, 2),
            "reset_in_sec": int(data.get("reset_in_sec") or 0),
        })
    return windows


def _daily(api_id: str) -> list:
    """Per-day consumption for the heat map: date, used points, weekday."""
    usage = []
    for day, used in get_package_daily_usage(api_id, HEATMAP_DAYS):
        try:
            weekday = date.fromisoformat(day).weekday()  # 0 = Monday
        except ValueError:
            weekday = 0
        usage.append({"date": day, "used": used, "weekday": weekday})
    return usage


def _platform_status(platform: str, status: dict | None) -> str | None:
    """The platform's own status-page indicator, for the ones that have one."""
    if platform != "deepseek" and not platform.startswith("minimax_"):
        return None
    if not status:
        return None
    return status.get("indicator")


def _platform_entry(app, api: dict, cache: dict, days: int) -> dict:
    platform = api.get("platform", "")
    entry = {
        "key": platform,
        "display": _display_name(platform),
        "kind": api.get("mode", "payg"),
        "balances": [],
        "rate": None,
        "windows": [],
        "series": [],
        "daily": [],
    }
    data = cache.get(api.get("id") or "", {})

    if entry["kind"] == "package":
        entry["windows"] = _windows(api.get("id") or "", platform,
                                    data.get("package_data") or {})
        entry["daily"] = _daily(api.get("id") or "")
    else:
        entry["balances"] = _balance_entries(data.get("balances") or {})
        entry["rate"] = _rate_entry(api.get("id") or "")
        entry["series"] = _series(api.get("id") or "", days)

    status = _platform_status(platform, data.get("service_status"))
    if status:
        entry["service_status"] = status
    return entry


def build_payload(app, days: int = DEFAULT_DAYS) -> dict:
    """The whole payload, built from the state the tray already keeps.

    Only configured platforms appear (the widget shows exactly what the
    application would); the per-platform readings come from the poll cache,
    and the curve and day figures from the history store.
    """
    if days not in DAYS:
        days = DEFAULT_DAYS

    with app._lock:
        last_check = app.last_check
        checking = getattr(app, "checking", False)
        cache = dict(app._api_cache)

    apis = [
        api for api in (app.config.get("apis") or [])
        if read_api_key_for_id(api.get("id") or "")
    ]
    platforms = [_platform_entry(app, api, cache, days) for api in apis]

    # The top-level indicator is the preferred platform's, the way the tray
    # icon follows it.
    preferred_id = app.config.get("preferred_api_id") or ""
    preferred = next((api for api in apis if api.get("id") == preferred_id), None)
    status = None
    if preferred:
        status = _platform_status(preferred.get("platform", ""),
                                  (cache.get(preferred_id) or {}).get("service_status"))

    # What today has cost the preferred balance account.
    today_spend = None
    if preferred and preferred.get("mode", "payg") == "payg":
        spent = get_today_total_spend(preferred_id)
        if spent:
            today_spend = {
                "platform": preferred.get("platform", ""),
                "currency": spent[0],
                "amount": spent[1],
            }

    now = datetime.now()
    return {
        "version": PAYLOAD_VERSION,
        "provider": PROVIDER,
        "generated_at": now.strftime("%Y-%m-%d %H:%M:%S"),
        "lang": app.lang,
        "checking": checking,
        "service_status": status or "unknown",
        "last_check_at": last_check.strftime("%Y-%m-%d %H:%M:%S") if last_check else None,
        "last_check_sec": int((now - last_check).total_seconds()) if last_check else None,
        "today_spend": today_spend,
        "platforms": platforms,
    }


def _make_server(app, port: int = PORT) -> ThreadingHTTPServer:
    class _Handler(BaseHTTPRequestHandler):
        def _respond(self, body: dict):
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(data)

        def _respond_status(self, code: int):
            self.send_response(code)
            self.send_header("Content-Length", "0")
            self.send_header("Connection", "close")
            self.end_headers()

        def do_GET(self):
            parsed = urlparse(self.path)
            if parsed.path not in ("/widget-status", "/check"):
                self._respond_status(404)
                return
            if parsed.path == "/check":
                # Fire a poll and answer with the current snapshot, without
                # waiting for the poll to finish (the contract's semantics).
                trigger = getattr(app, "_trigger_check", None)
                if trigger:
                    trigger()
            self._respond(build_payload(app, _parse_days(parsed.query)))

        def _method_not_allowed(self):
            self._respond_status(405)

        do_POST = do_PUT = do_DELETE = do_PATCH = do_HEAD = do_OPTIONS = _method_not_allowed

        def log_message(self, *args):
            pass

    return ThreadingHTTPServer(("127.0.0.1", port), _Handler)


def start_widget_server(app) -> None:
    """Starts the widget interface; the application runs on if the port is taken.

    A taken port (another copy, or another build) leaves the interface
    unavailable — logged, and nothing else changes.
    """
    def _serve():
        try:
            server = _make_server(app)
        except OSError as e:
            log(f"Widget interface unavailable on 127.0.0.1:{PORT}: {e}")
            return
        log(f"Widget interface listening on 127.0.0.1:{PORT}")
        server.serve_forever()

    threading.Thread(target=_serve, daemon=True).start()
