"""
OpenRouter balance client — USD payg, requires a Management Key.

  GET /api/v1/credits
Auth: Authorization: Bearer <management_api_key>
Response: {"data": {"total_credits": float, "total_usage": float}}

balance = total_credits - total_usage (account-level, not per-key).
"""
import urllib.error

from src.platforms._http import install_proxy as _install_proxy
from src.platforms._http import http_get_json

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"

API_BASE = "https://openrouter.ai/api/v1"


def fetch_openrouter_balance(api_key: str, platform_key: str = "openrouter",
                             http_proxy: str = "") -> dict:
    """Fetch OpenRouter account balance via /credits (Management Key).

    Returns the app's payg shape:
        {"is_available": bool,
         "all_balances": {"USD": {"total_balance", "topped_up_balance",
                                  "granted_balance"}}}

    Raises ValueError on failure (401 → Invalid API key / not a Management Key;
    a plain inference key lacks /credits permission).
    """
    if not api_key or not api_key.strip():
        raise ValueError("No API key provided for OpenRouter")
    _install_proxy(http_proxy or "")
    headers = {
        "Authorization": f"Bearer {api_key.strip()}",
        "Content-Type": "application/json",
        "User-Agent": USER_AGENT,
        "Accept": "application/json",
    }
    try:
        data = http_get_json(API_BASE + "/credits", headers=headers, timeout=10)
    except urllib.error.HTTPError as e:
        if e.code == 401 or e.code == 403:
            raise ValueError("Invalid or non-management API key "
                             f"(HTTP {e.code})")
        raise ValueError(f"OpenRouter API error: HTTP {e.code}")
    if not isinstance(data, dict):
        raise ValueError("OpenRouter API returned an unexpected payload")
    d = data.get("data") or {}
    total = float(d.get("total_credits") or 0)
    used = float(d.get("total_usage") or 0)
    balance = total - used
    return {
        "is_available": balance > 0,
        "all_balances": {"USD": {
            "total_balance": balance,
            "topped_up_balance": total,
            "granted_balance": 0.0,
        }},
    }