"""
DeepSeek API client — balance + FlashDuty status page.
"""
import json
import re
import urllib.request
import urllib.error

from src.platforms._http import install_proxy, http_get_json


def fetch_balance(api_key: str) -> dict:
    """Query balance. Returns dict with 'is_available' and 'all_balances'.

    Raises PermissionError on 401, ValueError on empty payload,
    URLError/HTTPError on other failures.
    """
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    try:
        data = http_get_json("https://api.deepseek.com/user/balance", headers=headers)
    except urllib.error.HTTPError as e:
        if e.code == 401:
            raise PermissionError("Invalid API key (401)")
        raise
    if not data.get("balance_infos"):
        raise ValueError("No balance information returned")

    all_balances = {}
    for info in data.get("balance_infos", []):
        code = info.get("currency", "CNY")
        # A negative bucket is NOT usable balance: clamp each at 0 and derive
        # the total from the CLAMPED buckets. topped -0.10 + granted 6.00 is
        # 6.00 usable, not the API's raw sum of 5.90 — the display, the history
        # rows and the consumption-rate statistics must all agree on that.
        granted = max(0.0, float(info.get("granted_balance", 0) or 0))
        topped = max(0.0, float(info.get("topped_up_balance", 0) or 0))
        all_balances[code] = {
            "total_balance": granted + topped,
            "granted_balance": granted,
            "topped_up_balance": topped,
        }
    return {
        "is_available": data.get("is_available", True),
        "all_balances": all_balances,
    }


# ─── Status page (FlashDuty-hosted; page custom_domain = status.deepseek.com) ───
# The canonical domain is tried first; FlashDuty's backend host serves the same
# page and is the only one reachable from some networks (the vanity domain's TLS
# handshake is reset there). The URL used before — status.flashcat.cloud/deepseek
# — is FlashDuty's OWN status page: it carries no DeepSeek data at all, yet the
# parser still answered "operational", so 异常状态 was never reported.
STATUS_URLS = (
    "https://status.deepseek.com/",
    "https://cn.statuspage.flashduty.com/deepseek",
)
_STATUS_TIMEOUT = 10
_STATUS_UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

# component status -> app indicator (matches the i18n status_* keys).
# The normalization table is the shared contract in docs/INTERFACES.md §7.4:
# degraded / degraded_performance -> minor, partial_outage -> major,
# full_outage / major_outage -> critical, under_maintenance -> maintenance.
_FLASHDUTY_MAP = {
    "operational":          "none",
    "degraded":             "minor",
    "degraded_performance": "minor",
    "partial_outage":       "major",
    "full_outage":          "critical",
    "major_outage":         "critical",
    "under_maintenance":    "maintenance",
}
# severity ranking used to pick the worst affected API component; an
# unrecognized status must never read as "fine"
_SEVERITY = {"operational": 0, "under_maintenance": 1,
             "degraded": 2, "degraded_performance": 2,
             "partial_outage": 3,
             "full_outage": 4, "major_outage": 4}
_UNKNOWN_SEVERITY = 2

# a change that is already over must not raise the indicator
_INACTIVE_CHANGES = {"resolved", "completed", "scheduled"}

# Only API-type components drive the API status. The page names them
# "DeepSeek V4 Pro API服务(API Service)" / "DeepSeek V4.1 Flash API服务(API Service)";
# chat, upload and search services are deliberately ignored.
_API_COMPONENT_RE = re.compile(r"API\s*服务|API\s*Service", re.I)


def _decode_rsc_payload(html: str) -> str:
    """Join the Next.js RSC chunks into one payload with real (unescaped) quotes.

    The page ships its data as `self.__next_f.push([1,"<escaped JSON>"])` script
    chunks. Inside them every quote is escaped, so the JSON structure is
    invisible until the string literals are decoded — and a blunt
    `replace("\\\\", "")` corrupts the payload. Decoding chunk by chunk keeps
    nesting intact.
    """
    marker = "self.__next_f.push(["
    parts = []
    idx = 0
    while True:
        i = html.find(marker, idx)
        if i < 0:
            break
        j = html.find('"', i + len(marker))
        if j < 0:
            break
        k = j + 1
        while k < len(html):
            if html[k] == "\\":
                k += 2
                continue
            if html[k] == '"':
                break
            k += 1
        try:
            parts.append(json.loads(html[j:k + 1]))
        except Exception:
            pass
        idx = k + 1
    return "".join(parts) if parts else html


def _extract_json_value(text: str, key: str):
    """Return the raw JSON array/object following "key": via bracket matching.

    String-aware and nesting-aware, so it survives exactly what the previous
    `\\[[^\\]]*\\]` regex could not: an active incident, whose
    affected_components array is nested inside the change array. That regex
    truncated the JSON, json.loads raised, and the blanket except turned a real
    outage into "服务状态未知".
    """
    m = re.search(r'"' + re.escape(key) + r'"\s*:\s*([\[{])', text)
    if not m:
        return None
    start = m.start(1)
    open_c = text[start]
    close_c = "]" if open_c == "[" else "}"
    depth = 0
    in_str = False
    esc = False
    for k in range(start, len(text)):
        c = text[k]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
        elif c == '"':
            in_str = True
        elif c == open_c:
            depth += 1
        elif c == close_c:
            depth -= 1
            if depth == 0:
                return text[start:k + 1]
    return None


def parse_status_page(html: str):
    """Parse a DeepSeek status page into {"indicator", "api_operational"}.

    Returns None when the page cannot be identified as DeepSeek's. A wrong or
    restructured page must surface as "unknown", never as a silent 服务正常.
    """
    text = _decode_rsc_payload(html)

    # Identify the page by its API service components: FlashDuty answers unknown
    # paths with its own status page, which has no such components.
    api_names = {n for n in re.findall(r'"name"\s*:\s*"([^"]*)"', text)
                 if _API_COMPONENT_RE.search(n)}
    if not api_names:
        return None

    raw = _extract_json_value(text, "active_changes")
    if raw is None:
        return None
    try:
        changes = json.loads(raw)
    except Exception:
        return None

    worst = "operational"
    for change in changes:
        if str(change.get("status", "")).lower() in _INACTIVE_CHANGES:
            continue
        for comp in change.get("affected_components") or []:
            if not _API_COMPONENT_RE.search(str(comp.get("name", ""))):
                continue
            status = str(comp.get("status", "")).lower()
            if _SEVERITY.get(status, _UNKNOWN_SEVERITY) > _SEVERITY[worst]:
                worst = status if status in _SEVERITY else "degraded"

    indicator = _FLASHDUTY_MAP.get(worst, "minor")
    return {"indicator": indicator, "api_operational": indicator == "none"}


def fetch_service_status():
    """Fetch DeepSeek API service status from the FlashDuty status page.

    Tries the canonical domain, then FlashDuty's backend host.
    Returns dict {"indicator": str, "api_operational": bool},
    or None when the status cannot be determined (never a silent "operational").
    """
    for url in STATUS_URLS:
        try:
            req = urllib.request.Request(url, headers=_STATUS_UA)
            with urllib.request.urlopen(req, timeout=_STATUS_TIMEOUT) as resp:
                html = resp.read().decode("utf-8", "replace")
        except Exception:
            continue
        parsed = parse_status_page(html)
        if parsed is not None:
            return parsed
    return None
