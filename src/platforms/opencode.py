"""
Opencode Go quota client — official API.
Official: GET https://opencode.ai/zen/go/v1/usage
  Headers: Authorization: Bearer <api_key>, x-api-key: <api_key>
  Returns: {"usage": {"rolling": {"status","percent","resetsAt"}, "weekly": {...}, "monthly": {...}}}
"""
from datetime import datetime, timezone
import urllib.error

from src.platforms._http import install_proxy as _install_proxy
from src.platforms._http import http_get_json, format_reset_short  # re-export

USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Gecko/20100101 Firefox/148.0"
OFFICIAL_URL = "https://opencode.ai/zen/go/v1/usage"

def _parse_window(data: dict, key: str) -> dict | None:
    """Parse a usage window from the response.
    Actual format: {"rolling": {"status": "ok", "percent": 4, "resetsAt": "ISO8601"}}
    """
    w = data.get(key)
    if not isinstance(w, dict):
        return None
    try:
        up = float(w.get("percent", w.get("usagePercent", 0)))
        resets_at = w.get("resetsAt", "")
        if resets_at:
            # parse ISO8601 to reset seconds
            reset_dt = datetime.fromisoformat(resets_at.replace("Z", "+00:00"))
            now = datetime.now(timezone.utc)
            reset_sec = max(0, int((reset_dt - now).total_seconds()))
        else:
            reset_sec = int(w.get("resetInSec", 0))
        up = max(0.0, min(100.0, up))   # shared contract §7.3: clamp to [0, 100]
        return {"usage_percent": up, "percent_remaining": max(0.0, 100.0 - up), "reset_in_sec": reset_sec}
    except Exception:
        return None

def fetch_opencode_quota(api_key: str, http_proxy: str = "") -> dict:
    """Fetch OpenCode Go quota via official API.

    Returns:
        {"rolling": {"usage_percent", "percent_remaining", "reset_in_sec"},
         "weekly": ..., "monthly": ...}
    Raises ValueError on failure.
    """
    if not api_key or not api_key.strip():
        raise ValueError("No API key provided for OpenCode Go")

    _install_proxy(http_proxy or "")
    headers = {
        "Authorization": f"Bearer {api_key.strip()}",
        "x-api-key": api_key.strip(),
        "User-Agent": USER_AGENT,
        "Accept": "application/json",
    }
    try:
        data = http_get_json(OFFICIAL_URL, headers=headers, timeout=10)
        # wrap: actual response is {"usage": {...}}
        usage_data = data.get("usage", data)
        if isinstance(usage_data, dict) and usage_data.get("type") == "error":
            raise ValueError(usage_data.get("error", {}).get("message", "API error"))
        quota = {
            "rolling": _parse_window(usage_data, "rolling"),
            "weekly": _parse_window(usage_data, "weekly"),
            "monthly": _parse_window(usage_data, "monthly"),
        }
        if quota["rolling"] is None and quota["weekly"] is None and quota["monthly"] is None:
            raise ValueError("No usage data returned from OpenCode Go API")
        return quota
    except urllib.error.HTTPError as e:
        if e.code == 401:
            raise ValueError("Invalid API key (401)")
        raise ValueError(f"OpenCode Go API error: HTTP {e.code}")
