"""Immediate credential test for the settings form.

The form can test a key before it is saved (Rust v2.4's "test" button), so this
module takes the platform and the key as arguments instead of reading storage.
It returns a short human-readable answer; the raw exception text is only used
when the provider gave no summary of its own.
"""
from src.platforms._http import install_proxy
from src.platforms.registry import get_platform


def _payg(platform: str, key: str, proxy: str) -> str:
    # Install it up front, as every platform client does internally: the
    # DeepSeek client has no proxy argument and uses whatever opener is
    # installed, so without this the proxy this function is given would be
    # ignored for exactly that platform.
    install_proxy(proxy or "")
    if platform.startswith("kimi_"):
        from src.platforms.kimi import fetch_kimi_balance
        data = fetch_kimi_balance(key, platform_key=platform, http_proxy=proxy)
    elif platform.startswith("stepfun_"):
        from src.platforms.stepfun import fetch_stepfun_balance
        data = fetch_stepfun_balance(key, platform_key=platform, http_proxy=proxy)
    elif platform.startswith("openrouter"):
        from src.platforms.openrouter import fetch_openrouter_balance
        data = fetch_openrouter_balance(key, http_proxy=proxy)
    else:
        from src.platforms.deepseek import fetch_balance
        data = fetch_balance(key)
    balances = data.get("all_balances") or {}
    if balances:
        code, first = next(iter(balances.items()))
        return f"{first.get('total_balance', 0):,.2f} {code}"
    return "OK"


def _package(platform: str, key: str, proxy: str) -> str:
    if platform.startswith("minimax_"):
        from src.platforms.minimax import fetch_minimax_quota
        quota = fetch_minimax_quota(platform_key=platform, api_key=key, http_proxy=proxy)
    elif platform.startswith("command_code"):
        from src.platforms.command_code import fetch_command_code_quota
        quota = fetch_command_code_quota(api_key=key, http_proxy=proxy)
    elif platform.startswith("glm_"):
        from src.platforms.glm import fetch_glm_quota
        quota = fetch_glm_quota(api_key=key, platform_key=platform, http_proxy=proxy)
    else:
        from src.platforms.opencode import fetch_opencode_quota
        quota = fetch_opencode_quota(api_key=key, http_proxy=proxy)
    main = quota.get("monthly") or quota.get("weekly") or quota.get("5h") or quota.get("rolling")
    if main:
        remaining = main.get("percent_remaining", 100 - main.get("usage_percent", 0))
        return f"{remaining:.0f}%"
    return "OK"


def test_key(platform: str, mode: str, key: str, proxy: str = "") -> tuple:
    """Returns (ok, message). Never raises."""
    key = (key or "").strip()
    if not key:
        return False, "no key"
    meta = get_platform(platform)
    kind = mode or (meta.default_mode if meta else "payg")
    try:
        summary = _package(platform, key, proxy) if kind == "package" else _payg(platform, key, proxy)
        return True, summary
    except Exception as e:
        return False, str(e).split("\n")[0]
