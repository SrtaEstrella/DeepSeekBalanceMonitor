"""
Platform registry — defines supported platforms, their default mode,
credential fields, and fetch logic.

To add a new platform:
  1. Add an entry to PLATFORMS dict below
  2. If payg: implement fetch in tray_app's _fetch_payg API
  3. If package: implement fetch in tray_app's _fetch_package API
  4. Add i18n keys to config.py _T
"""
from dataclasses import dataclass, field

@dataclass
class PlatformMeta:
    key: str                   # internal id, e.g. "deepseek"
    display_name: str          # shown in UI, e.g. "DeepSeek"
    default_mode: str          # "payg" or "package"
    supports_payg: bool = True
    supports_package: bool = True
    cred_fields: list = field(default_factory=list)
    console_url: str = ""
    # Package-specific: which windows to display
    # "5h"=rolling, "weekly", "monthly"
    package_windows: list = field(default_factory=lambda: ["5h", "weekly", "monthly"])
    # Preferred billing window used when api.billing_period is unset
    default_billing_period: str = "monthly"
    # Does this platform have a status page? (affects history table status column)
    has_status_page: bool = False


PLATFORMS = {
    "deepseek": PlatformMeta(
        key="deepseek",
        display_name="DeepSeek",
        default_mode="payg",
        supports_payg=True,
        supports_package=False,
        console_url="https://platform.deepseek.com",
        has_status_page=True,
    ),
    "opencode_go": PlatformMeta(
        key="opencode_go",
        display_name="OpenCode Go",
        default_mode="package",
        supports_payg=False,
        supports_package=True,
        console_url="https://opencode.ai/auth",
        package_windows=["5h", "weekly", "monthly"],
        has_status_page=False,
    ),
    "minimax_token_cn": PlatformMeta(
        key="minimax_token_cn",
        display_name="MiniMax Token Plan (CN)",
        default_mode="package",
        supports_payg=False,
        supports_package=True,
        console_url="https://platform.minimaxi.com",
        package_windows=["5h", "weekly"],
        has_status_page=True,
    ),
    "minimax_token_global": PlatformMeta(
        key="minimax_token_global",
        display_name="MiniMax Token Plan (Global)",
        default_mode="package",
        supports_payg=False,
        supports_package=True,
        console_url="https://platform.minimax.io",
        package_windows=["5h", "weekly"],
        has_status_page=True,
    ),
    "minimax_coding_cn": PlatformMeta(
        key="minimax_coding_cn",
        display_name="MiniMax Coding Plan (CN)",
        default_mode="package",
        supports_payg=False,
        supports_package=True,
        console_url="https://platform.minimaxi.com",
        package_windows=["5h", "weekly"],
        has_status_page=True,
    ),
    "minimax_coding_global": PlatformMeta(
        key="minimax_coding_global",
        display_name="MiniMax Coding Plan (Global)",
        default_mode="package",
        supports_payg=False,
        supports_package=True,
        console_url="https://platform.minimax.io",
        package_windows=["5h", "weekly"],
        has_status_page=True,
    ),
    # Kimi (Moonshot) — payg, balance via /v1/users/me/balance
    "kimi_token_cn": PlatformMeta(
        key="kimi_token_cn",
        display_name="Kimi (CN)",
        default_mode="payg",
        supports_payg=True,
        supports_package=False,
        package_windows=[],
        has_status_page=False,
        console_url="https://platform.kimi.com",
    ),
        "kimi_token_global": PlatformMeta(
        key="kimi_token_global",
        display_name="Kimi (Global)",
        default_mode="payg",
        supports_payg=True,
        supports_package=False,
        package_windows=[],
        has_status_page=False,
        console_url="https://platform.kimi.ai",
    ),
    # StepFun (阶跃星辰) — payg only; balance via /v1/accounts
    "stepfun_token_cn": PlatformMeta(
        key="stepfun_token_cn",
        display_name="StepFun (CN)",
        default_mode="payg",
        supports_payg=True,
        supports_package=False,
        package_windows=[],
        has_status_page=False,
        console_url="https://platform.stepfun.com",
    ),
    "stepfun_token_global": PlatformMeta(
        key="stepfun_token_global",
        display_name="StepFun (Global)",
        default_mode="payg",
        supports_payg=True,
        supports_package=False,
        package_windows=[],
        has_status_page=False,
        console_url="https://platform.stepfun.ai",
    ),
    # Command Code — package windows; GOAT has a monthly credit pool, standard doesn't
    "command_code": PlatformMeta(
        key="command_code",
        display_name="Command Code",
        default_mode="package",
        supports_payg=False,
        supports_package=True,
        console_url="https://commandcode.ai",
        package_windows=["5h", "weekly"],
        default_billing_period="weekly",
        has_status_page=False,
    ),
    "command_code_goat": PlatformMeta(
        key="command_code_goat",
        display_name="Command Code GOAT",
        default_mode="package",
        supports_payg=False,
        supports_package=True,
        console_url="https://commandcode.ai",
        package_windows=["5h", "weekly", "monthly"],
        default_billing_period="monthly",
        has_status_page=False,
    ),
    # GLM Coding Plan — 5h + weekly token windows, monthly MCP call count
    "glm_coding_cn": PlatformMeta(
        key="glm_coding_cn",
        display_name="GLM Coding Plan (CN)",
        default_mode="package",
        supports_payg=False,
        supports_package=True,
        console_url="https://open.bigmodel.cn",
        package_windows=["5h", "weekly", "monthly"],
        default_billing_period="weekly",
        has_status_page=False,
    ),
    "glm_coding_global": PlatformMeta(
        key="glm_coding_global",
        display_name="GLM Coding Plan (Global)",
        default_mode="package",
        supports_payg=False,
        supports_package=True,
        console_url="https://z.ai",
        package_windows=["5h", "weekly", "monthly"],
        default_billing_period="weekly",
        has_status_page=False,
    ),
    # OpenRouter — USD payg; account credits via /credits, key cap via /key
    "openrouter": PlatformMeta(
        key="openrouter",
        display_name="OpenRouter",
        default_mode="payg",
        supports_payg=True,
        supports_package=False,
        package_windows=[],
        has_status_page=False,
        console_url="https://openrouter.ai",
    ),
}

def get_platform(key: str) -> PlatformMeta | None:
    return PLATFORMS.get(key)

def get_all_platforms() -> list[PlatformMeta]:
    return list(PLATFORMS.values())

# billing_period → package_history column
BILLING_COL_MAP = {
    "5h": "h5_percent",
    "weekly": "weekly_percent",
    "monthly": "monthly_percent",
}

def billing_col(billing_period: str | None, default: str = "monthly_percent") -> str:
    return BILLING_COL_MAP.get(billing_period or "", default)

# status indicator → display emoji (shared by tray/history/rainmeter)
STATUS_ICON = {
    "none": "🟢", "minor": "🟡", "major": "🟠",
    "critical": "🔴", "maintenance": "🔵",
}
