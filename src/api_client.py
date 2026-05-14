"""
DeepSeek API client - fetches account balance from the DeepSeek API.
"""
import json
import socket
import urllib.request
import urllib.error

socket.setdefaulttimeout(15)

_proxy_installed = False


def install_proxy(proxy_url: str):
    """Install a global HTTP/HTTPS proxy. If proxy_url is non-empty, use it.
    Otherwise install an opener that bypasses system proxy (direct connection)."""
    global _proxy_installed
    if proxy_url:
        handler = urllib.request.ProxyHandler({"http": proxy_url, "https": proxy_url})
        urllib.request.install_opener(urllib.request.build_opener(handler))
    else:
        urllib.request.install_opener(urllib.request.build_opener(urllib.request.ProxyHandler({})))
    _proxy_installed = True


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


# FlashDuty status → legacy indicator mapping
_FLASHDUTY_MAP = {
    "operational":        "none",
    "degraded":           "minor",
    "partial_outage":     "major",
    "full_outage":        "critical",
    "under_maintenance":  "maintenance",
}


def fetch_service_status():
    """Fetch DeepSeek API service status from FlashDuty status page.
    Returns dict {"indicator": str, "api_operational": bool},
    or None on failure."""
    try:
        import re
        url = "https://status.flashcat.cloud/deepseek"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=5) as resp:
            html = resp.read().decode("utf-8")
        full = " ".join(html.split("\n"))

        # Find component names from RSC payload
        names = re.findall(r'\\"name\\"\s*:\s*\\"((?:API|Web|网页|APP|对话)[^\\]+)\\"', full)
        seen = set()
        api_name = None
        for n in names:
            if n not in seen:
                seen.add(n)
                if n.startswith("API") or "API" in n:
                    api_name = n
                    break

        if not api_name:
            return {"indicator": "none", "api_operational": True}

        # Check active incidents for API component
        active_match = re.search(r'\\"active_changes\\"\s*:\s*(\[[^\]]*\])', full)
        if active_match:
            raw = active_match.group(1).replace("\\", "")
            changes = json.loads(raw)
            for inc in changes:
                for ac in inc.get("affected_components", []):
                    if ac.get("name") == api_name:
                        status = ac.get("status", "degraded")
                        indicator = _FLASHDUTY_MAP.get(status, "none")
                        return {"indicator": indicator,
                                "api_operational": status == "operational"}

        return {"indicator": "none", "api_operational": True}
    except Exception:
        return None