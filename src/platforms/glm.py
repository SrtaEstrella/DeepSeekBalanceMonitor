"""
GLM Coding Plan (智谱) quota client — CN (open.bigmodel.cn) / Global (api.z.ai).

Semi-public monitoring endpoint (used by the official `glm-plan-usage` plugin):
  GET /api/monitor/usage/quota/limit
Auth: Authorization: Bearer <api_key> (some builds send the key header raw —
      on 401 we retry once without the Bearer prefix).

Response data.limits entries:
  TOKENS_LIMIT — first = 5h rolling window, second = weekly (community order)
  TIME_LIMIT   — monthly MCP tool-call count

App convention: package windows report REMAINING % as the primary measure.
"""
import urllib.error

from src.platforms._http import install_proxy as _install_proxy
from src.platforms._http import http_get_json

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"

_GLM_ENDPOINTS = {
    "glm_coding_cn":     ("https://open.bigmodel.cn", "CNY"),
    "glm_coding_global": ("https://api.z.ai",         "USD"),
}


def _reset_in_sec(ms_epoch):
    if ms_epoch is None:
        return 0
    from datetime import datetime, timezone
    try:
        sec = float(ms_epoch) / 1000.0
        return max(0, int(sec - datetime.now(timezone.utc).timestamp()))
    except Exception:
        return 0


def fetch_glm_quota(api_key: str, platform_key: str = "glm_coding_cn",
                    http_proxy: str = "") -> dict:
    """Fetch GLM Coding Plan quota.

    Returns dict shaped like other package clients:
        {"5h": {"usage_percent","percent_remaining","reset_in_sec"},
         "weekly": {...}, "monthly": {...}}
    Any missing window is None. percent_remaining = 100 − API percentage.

    Raises ValueError on failure (401 → Invalid API key).
    """
    if not api_key or not api_key.strip():
        raise ValueError("No API key provided for GLM Coding Plan")
    endpoint = _GLM_ENDPOINTS.get(platform_key)
    if not endpoint:
        raise ValueError(f"Unknown GLM platform: {platform_key}")
    base_url, _currency = endpoint
    url = base_url + "/api/monitor/usage/quota/limit"

    _install_proxy(http_proxy or "")
    headers = {
        "Authorization": f"Bearer {api_key.strip()}",
        "Content-Type": "application/json",
        "User-Agent": USER_AGENT,
        "Accept": "application/json",
    }

    def _fetch():
        return http_get_json(url, headers=headers, timeout=10)

    try:
        data = _fetch()
    except urllib.error.HTTPError as e:
        if e.code != 401:
            raise ValueError(f"GLM API error: HTTP {e.code}")
        # some deployments expect the raw key without the Bearer prefix
        raw_headers = dict(headers)
        raw_headers["Authorization"] = api_key.strip()
        try:
            data = http_get_json(url, headers=raw_headers, timeout=10)
        except urllib.error.HTTPError as e2:
            if e2.code == 401:
                raise ValueError("Invalid API key (401)")
            raise ValueError(f"GLM API error: HTTP {e2.code}")
    if not isinstance(data, dict):
        raise ValueError("GLM API returned an unexpected payload")
    try:
        code_ok = int(data.get("code")) in (0, 200)
    except (TypeError, ValueError):
        code_ok = False
    if not code_ok or not data.get("success", True):
        raise ValueError(data.get("msg") or "GLM API error")

    d = data.get("data") or {}
    limits = d.get("limits") or []
    if not isinstance(limits, list) or not limits:
        raise ValueError("GLM API returned no quota limits")

    tokens = [x for x in limits if isinstance(x, dict) and x.get("type") == "TOKENS_LIMIT"]
    time_m = [x for x in limits if isinstance(x, dict) and x.get("type") == "TIME_LIMIT"]

    def _window(x):
        if not x:
            return None
        try:
            pct = float(x.get("percentage") or 0)
        except (TypeError, ValueError):
            pct = 0.0
        remaining = max(0.0, min(100.0, 100.0 - pct))
        return {
            "usage_percent": pct,
            "percent_remaining": remaining,
            "reset_in_sec": _reset_in_sec(x.get("nextResetTime")),
        }

    result = {
        "5h": _window(tokens[0] if len(tokens) >= 1 else None),
        "weekly": _window(tokens[1] if len(tokens) >= 2 else None),
        "monthly": _window(time_m[0] if time_m else None),
    }
    if result["5h"] is None and result["weekly"] is None and result["monthly"] is None:
        raise ValueError("GLM API returned no usable quota windows")
    return result