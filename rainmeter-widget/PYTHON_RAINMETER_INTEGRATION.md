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

Rainmeter 当前使用正则按字段名解析，字段名必须保持一致；为降低兼容风险，
建议按上方顺序输出字段。

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
