"""
DeepSeek API client — fetches account balance from the DeepSeek API.
"""
import json
import urllib.request
import urllib.error


def _get_json(url, headers=None, timeout=15):
    """GET a JSON endpoint. Returns parsed dict, or raises HTTPError on
    4xx/5xx, URLError on network failure."""
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read().decode("utf-8")
        if resp.status >= 400:
            raise urllib.error.HTTPError(url, resp.status, "", resp.headers, None)
        return json.loads(body)


def fetch_balance(api_key: str) -> dict:
    """Query balance. Returns dict with 'is_available' and 'all_balances'.

    Raises PermissionError on 401, URLError/HTTPError on other failures,
    ValueError if the response contains no balance_infos.
    """
    # HTTP headers must be Latin-1 (RFC 7230 §3.2).  Any character
    # outside Latin-1 in the API key will crash http.client.putheader()
    # with UnicodeEncodeError before the request ever leaves the machine.
    api_key = api_key.encode("latin-1", errors="ignore").decode("latin-1")

    url = "https://api.deepseek.com/user/balance"
    headers = {"Accept": "application/json", "Authorization": f"Bearer {api_key}"}

    try:
        data = _get_json(url, headers)
    except urllib.error.HTTPError as e:
        if e.code == 401:
            raise PermissionError("Invalid API Key (401 Unauthorized)")
        raise

    infos = data.get("balance_infos", [])
    if not infos:
        raise ValueError("No balance information in response")
    all_balances = {}
    for info in infos:
        code = info.get("currency", "CNY")
        all_balances[code] = {
            "total_balance": float(info.get("total_balance", 0)),
            "granted_balance": float(info.get("granted_balance", 0)),
            "topped_up_balance": float(info.get("topped_up_balance", 0)),
        }
    return {
        "is_available": data.get("is_available", True),
        "all_balances": all_balances,
    }


def fetch_service_status():
    """Fetch DeepSeek service status from status.deepseek.com.
    Returns dict {"indicator": str, "api_operational": bool},
    or None on failure.  The API component is checked specifically
    — the overall indicator may report minor/major even when the
    API itself is fine (e.g. website outage)."""
    try:
        headers = {"User-Agent": "DeepSeekBalanceMonitor/1.0"}
        data = _get_json(
            "https://status.deepseek.com/api/v2/status.json",
            headers=headers, timeout=10)
        indicator = data.get("status", {}).get("indicator", "none")
        components = _get_json(
            "https://status.deepseek.com/api/v2/components.json",
            headers=headers, timeout=10)
        api_operational = True
        for comp in components.get("components", []):
            if "api" in comp.get("name", "").lower():
                api_operational = comp.get("status") == "operational"
                break
        return {"indicator": indicator, "api_operational": api_operational}
    except Exception:
        return None
