# Python 版 Rainmeter 接口对接指南

本文档说明 Python Windows 版如何对接 `rainmeter-widget/DeepSeekBalanceMonitor`
皮肤。目标是让 Python 版提供与 Rust Windows 版一致的本地 HTTP 状态接口，
Rainmeter 只读取本地状态，不直接接触 API key。

本文档只描述接口约定，不要求立即修改 Python 代码。

## 接口约定

服务只监听本机回环地址：

```text
127.0.0.1:17654
```

Rainmeter 皮肤当前使用两个端点：

```text
GET /widget-status?lang=zh
GET /widget-status?lang=en
GET /check?lang=zh
GET /check?lang=en
```

- `/widget-status`：返回当前缓存状态。
- `/check`：触发一次后台查询，然后返回当前状态。不要阻塞等待完整 API 查询结束。
- `lang=zh|en`：控制返回文案语言；缺省时可跟随 Python 版当前 UI 语言。

建议响应头：

```text
Content-Type: application/json; charset=utf-8
Cache-Control: no-store
Access-Control-Allow-Origin: *
Connection: close
```

## 返回 JSON

HTTP 状态码成功时返回 `200 OK`，`Content-Type` 使用
`application/json; charset=utf-8`。JSON 必须包含以下字段：

```json
{
  "accent_color": "60,105,102",
  "balance_line": "💰 12.34 CNY",
  "status_line": "总余额: 12.34 CNY",
  "last_check": "5 分钟前",
  "service_status_line": "🟢 服务正常",
  "estimated_line": "📊 预计可用 28 天 4 小时"
}
```

字段说明：

- `accent_color`：RGB 字符串，格式为 `R,G,B`，用于 Rainmeter 点缀色。
- `balance_line`：主余额行，建议保持 `💰 金额 币种`。
- `status_line`：辅助状态行，可显示总余额、查询中或错误摘要。
- `last_check`：上次成功查询时间，建议使用相对时间。
- `service_status_line`：DeepSeek API 服务状态，沿用通知中的 emoji 文案。
- `estimated_line`：预计可用天数，缺少消耗率时返回本地化占位文案。

## OpenCode Go 额度字段（Rust Windows 版新增）

`/widget-status` 响应额外包含 OpenCode Go 额度字段（Rust Windows 版后台每 10 分钟
自动刷新一次缓存，未配置 API Key 时不请求）：

```json
{
  "og_configured": true,
  "og_error": "",
  "og_rolling_percent": 8,
  "og_rolling_line": "8% · 3h 8m",
  "og_weekly_percent": 9,
  "og_weekly_line": "9% · 2d 15h",
  "og_monthly_percent": 32,
  "og_monthly_line": "32% · 17d"
}
```

字段说明：

- `og_configured`：布尔值，是否已配置 OpenCode Go API Key。
- `og_error`：最近一次查询的错误消息，正常为空字符串。
- `og_rolling_percent` / `og_weekly_percent` / `og_monthly_percent`：数值（0–100），
  供进度条仪表使用；无数据时为 `0`。
- `og_rolling_line` / `og_weekly_line` / `og_monthly_line`：预格式化显示文本
  （`已用% · 重置剩余时间`），无数据时为 `--`，窗口缺失时为本地化占位文案。

数据语义：

- 后台每 10 分钟查询一次 OpenCode Go 官方接口，查询失败时保留上次成功数据，
  仅在 `og_error` 中体现。
- 未配置 API Key 时 `og_configured` 为 `false`，额度字段为占位值。
- 现有皮肤的正则只提取已知字段，新增字段不影响旧皮肤兼容。

Rainmeter 当前使用正则按字段名解析，字段名必须保持一致；为降低兼容风险，
建议按上方顺序输出字段。

## Command Code 额度字段（v1.4.0 新增，v1.4.3 修复月度）

Rust v1.4.0 已为 Rust Windows / Rust Linux 新增 Command Code 额度显示（设置窗口
「订阅」页、`dsmon command-code` CLI、Plasma 小组件）。Rust Windows 版
`/widget-status` 接口**已预留 Command Code 额度字段**（后台线程每 10 分钟刷新缓存、
查询失败保留上次成功数据），字段设计与 OpenCode Go 的 `og_*` 一致：

```json
{
  "cc_configured": true,
  "cc_error": "",
  "cc_5h_percent": 30,
  "cc_5h_line": "4.2/14.0 · 3h 8m",
  "cc_weekly_percent": 50,
  "cc_weekly_line": "17.5/35.0 · 2d 15h",
  "cc_monthly_percent": 31,
  "cc_monthly_line": "22.0/70.0 · 17d"
}
```

字段说明：

- `cc_configured`：布尔值，是否已配置 Command Code API Key。
- `cc_error`：最近一次查询的错误消息，正常为空字符串。
- `cc_5h_percent` / `cc_weekly_percent` / `cc_monthly_percent`：数值（0–100），
  供进度条仪表使用；无数据时为 `0`。
- `cc_5h_line` / `cc_weekly_line` / `cc_monthly_line`：预格式化显示文本
  （`已用/上限 · 重置剩余时间`），无数据时为 `--`，窗口缺失时为本地化占位文案。

数据语义：

- 后台按 OpenCode Go 相同的节奏（每 10 分钟）查询 Command Code 官方接口，
  查询失败时保留上次成功数据，仅在 `cc_error` 中体现。
- 月度窗口为推算值：cap 由 5h/周窗口 cap 对照官方档位表唯一确定（Go 10 /
  GOAT 70 / Pro 80 / Max 10× 150 / Max 20× 300 / Team Pro 40 credits），
  已用 = 档位额度 − `credits.monthlyCredits`。v1.4.3 起月度对全部可识别档位可用；
  v1.4.0–1.4.2 仅 GOAT 套餐可推算，且依赖 API 已移除的 `credits.planId`（实际已失效）。
- 纯充值账号没有滚动窗口，档位无法识别，`cc_monthly_*` 为占位值。
- 未配置 API Key 时 `cc_configured` 为 `false`，额度字段为占位值。
- Rainmeter 皮肤正则按字段名解析，新增字段不影响旧皮肤兼容。

Python 版托盘已展示 Command Code 额度（`src/platforms/command_code.py`，档位识别
逻辑与 Rust 一致）；对接 Rainmeter 时按本约定补齐 `cc_*` 字段即可。

## 状态映射

Python 版可按当前托盘状态生成 Rainmeter JSON：

| Python 状态 | `balance_line` | `status_line` | `last_check` |
| --- | --- | --- | --- |
| 查询成功 | `💰 12.34 CNY` | `总余额: 12.34 CNY` | 相对时间 |
| 查询中 | `💰 -- CNY` | `正在查询...` | 上次成功查询时间或 `尚未查询` |
| 无 API key | `💰 -- CNY` | 本地化错误摘要 | `尚未查询` |
| API 请求失败 | `💰 -- CNY` | 本地化错误摘要 | 上次成功查询时间或 `尚未查询` |
| 进程未启动 | 无响应 | 由 Rainmeter fallback 显示 | 由 Rainmeter fallback 显示 |

`accent_color` 建议沿用项目主题色规则：

| 状态 | 建议含义 |
| --- | --- |
| `ok` | 余额正常且服务正常 |
| `low` | 余额低于预警线 |
| `degraded` | DeepSeek API 服务异常或降级 |
| `nodata` | 尚无余额数据、正在查询或未配置 key |

## 无数据与错误处理

如果 Python 进程未启动，Rainmeter 会显示皮肤内置 fallback：

```text
⚠ 请打开原进程
未识别到本地数据
```

如果 Python 进程已启动但还没有余额数据，接口仍应返回合法 JSON，例如：

```json
{
  "accent_color": "60,105,102",
  "balance_line": "💰 -- CNY",
  "status_line": "正在查询...",
  "last_check": "尚未查询",
  "service_status_line": "⚪ 状态未知",
  "estimated_line": "📊 预计可用 --"
}
```

不要把 Python 异常栈、requests 错误文本或英文库错误直接返回给 Rainmeter。

接口自身发生异常时，建议仍返回合法 JSON，并把错误写入 Python 版日志。

## 安全要求

- 只绑定 `127.0.0.1`，不要监听 `0.0.0.0`。
- 不在 URL、响应 JSON、日志或 Rainmeter 配置中暴露 API key。
- `/check` 只触发主程序已有查询逻辑，不能接受外部传入的 key。
- HTTP 服务线程退出失败时只记录日志，不应影响托盘主循环。
- Rainmeter 端只允许读取展示状态，不能提供修改配置、写入 API key 或导出数据的接口。

## Python 实现建议

- 使用标准库 `http.server.ThreadingHTTPServer` 即可，不需要新增依赖。
- 服务线程设为 daemon thread，随托盘程序退出。
- 复用现有应用状态：余额、上次查询时间、服务状态、消耗率估算。
- `/check` 中只投递一次后台刷新任务；如果已有查询正在运行，直接返回当前状态。
- JSON 序列化使用 `json.dumps(..., ensure_ascii=False)`。

建议拆分为三个小函数，保持实现简单：

```python
def start_rainmeter_server(app_state) -> None:
    """启动本地 HTTP 服务线程。"""


def build_rainmeter_status(app_state, lang: str) -> dict:
    """从当前应用状态生成 Rainmeter JSON。"""


def trigger_rainmeter_check(app_state) -> None:
    """触发一次后台查询；如果正在查询则直接返回。"""
```

## 与 Rust Windows 版保持一致

Python 版实现后，应与 Rust Windows 版保持以下行为一致：

- 端口固定为 `127.0.0.1:17654`。
- `/widget-status` 和 `/check` 字段完全一致。
- `/check` 不阻塞等待网络请求完成。
- `lang=zh|en` 控制返回文案语言。
- Rainmeter 无法接触 API key。
- 无数据时返回合法 JSON；进程未启动时由 Rainmeter fallback 显示。

## 验证方式

启动 Python 版后，可用以下命令验证：

```powershell
curl.exe http://127.0.0.1:17654/widget-status?lang=zh
curl.exe http://127.0.0.1:17654/check?lang=zh
```

返回内容应为合法 JSON，且至少包含：

```text
accent_color
balance_line
status_line
last_check
service_status_line
estimated_line
```

关闭 Python 版后，Rainmeter 小工具应显示：

```text
⚠ 请打开原进程
未识别到本地数据
```

## Python 版实施建议（OpenCode Go 额度字段）

为使 Python 版与 Rust Windows 版提供一致的 `og_*` 字段、共用同一套 Rainmeter
皮肤，建议按以下步骤实施：

### 1. 凭据存储（`src/secure_settings.py`）

现有 `store_api_key` / `read_api_key` 只支持 `api_key` 一个键。建议增加通用
读写函数（保持 Fernet 加密与 `secrets` 表不变）：

```python
def store_secure_value(key: str, value: str):
    f = _get_fernet()
    encrypted = f.encrypt(value.encode("utf-8"))
    with sqlite3.connect(_db_path()) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO secrets (key, value) VALUES (?, ?)",
            (key, encrypted),
        )

def read_secure_value(key: str) -> str | None:
    f = _get_fernet()
    with sqlite3.connect(_db_path()) as conn:
        row = conn.execute(
            "SELECT value FROM secrets WHERE key = ?", (key,)
        ).fetchone()
    if not row:
        return None
    return f.decrypt(row[0]).decode("utf-8")
```

OpenCode Go API Key 使用独立键 `opencode_go_api_key`，**不写入 config.json**。

### 2. 额度查询（建议新增 `src/opencode_go.py` 或并入 `api_client.py`）

调用官方接口，凭据走 Bearer 认证：

```python
OPENCODE_GO_URL = "https://opencode.ai/zen/go/v1/usage"

def fetch_opencode_go_quota(api_key: str) -> dict:
    # GET OPENCODE_GO_URL, Header: Authorization: Bearer <api_key>
    # 解析响应 usage.rolling/weekly/monthly 的 percent 与 resetsAt(ISO 8601)
    # 返回 {"configured": True, "rolling": {"usage_percent": .., "reset_in_sec": ..}, ...}
```

`resetsAt`（ISO 8601 UTC）需转换为相对当前时间的剩余秒数
（`reset_in_sec = max(0, int(dt.timestamp() - time.time()))`）。

### 3. 后台缓存（与 Rust 版一致）

- 应用启动时立即查询一次，之后**每 10 分钟**刷新一次（独立线程，
  用 `threading.Timer` 或循环 + `time.sleep(600)`）。
- 每次查询前重新读取 `opencode_go_api_key`（用户中途修改 Key 即时生效）。
- 查询失败**保留上次成功数据**，仅记录错误。
- 未配置 Key 时不发起请求，`configured = False`。
- 缓存存入托盘应用状态（如 `app.opencode_quota` / `app.opencode_error`），
  `/widget-status` 处理时在 `app._lock` 下读取。

### 4. JSON 输出（`src/rainmeter_server.py`）

在 `/widget-status` 响应中追加与 Rust 版完全一致的字段：

```python
# 示例（百分比数值 + 预格式化文本）
body["og_configured"] = configured
body["og_error"] = error or ""
body["og_rolling_percent"] = rolling_percent   # int, 0-100
body["og_rolling_line"] = f"{percent:.0f}% · {reset_text}"
body["og_weekly_percent"] = weekly_percent
body["og_weekly_line"] = ...
body["og_monthly_percent"] = monthly_percent
body["og_monthly_line"] = ...
```

- `percent`：无数据时 `0`；`line`：无数据时 `--`，窗口缺失时用本地化占位文案
  （如 `不可用` / `unavailable`）。
- `line` 文本格式 `已用% · 重置剩余时间`（如 `8% · 3h 8m`），与 Rust 版一致。
- 字段名、顺序、语义与 Rust Windows 版保持完全一致，Rainmeter 皮肤无需区分
  后端实现。

### 5. 兼容性

- 未实现上述字段前，Python 版响应中缺失 `og_*` 键不会影响现有皮肤
  （正则只提取已知字段）。
- 建议实现后保持字段齐全，便于两端无缝切换同一皮肤。
