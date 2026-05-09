# Contributing — Port Sync Guide

## Config Schema (v1.1)

移植版本必须兼容以下 `config.json` 字段。未知字段应保留不删，忽略即可。

| Key | Type | Default | Notes |
|---|---|---|---|
| `api_key` | string | `""` | |
| `interval_minutes` | int | `10` | 1–1440 |
| `threshold_yuan` | float | `1.0` | 0–10000 |
| `language` | string | `"zh"` | `"zh"` or `"en"` |
| `alert_mode` | string | `"once"` | `"never"` / `"always"` / `"once"` |
| `api_alert_enabled` | bool | `true` | |
| `retention_days` | int | `30` | 1–3650 |
| `auto_start` | bool | `false` | |

## Notification Format

点击图标查看余额的通知卡片格式（标题 + 多行正文）：

```
DeepSeek 余额：                    ← 固定标题
12.34 CNY（充值 10.00，赠送 2.34） ← 有余额时显示此行
上次查询: 2026-05-08 14:30:00      ← 正常 / 查询出错: xxx / 尚未查询
DeepSeek API 服务状态：🟢 服务正常   ← 常驻
```

## API Endpoints

| Endpoint | Purpose |
|---|---|
| `api.deepseek.com/user/balance` | 余额查询 |
| `status.deepseek.com/api/v2/status.json` | 服务整体状态 |
| `status.deepseek.com/api/v2/components.json` | 组件级状态（匹配 name 含 "api" 的项） |

## Changed Since v1.0.1

### Config

- `enable_alerts: bool` **已移除**，替换为 `alert_mode: "never" | "always" | "once"`，默认 `"once"`
- **新增** `api_alert_enabled: bool`，默认 `true`。为 `false` 时 API 状态翻转不弹通知，但内存状态位继续追踪
- **新增** `retention_days: int`，默认 `30`。日志和 SQLite 余额历史在每次启动时清理超过此天数的记录
- `preferred_currency` **已移除**。DeepSeek 每个账号只有一种币种，API 返回什么就显示什么
- 所有余额数值不再拼接 `¥`，改为标注实际币种代码（如 `12.34 CNY`）
- 设置页新增校验：保存时检查各数值字段范围，非法输入弹警告提示

### Behaviour

- **通知卡片重构**：标题固定为 `DeepSeek 余额：`，正文按行排列——余额行（有数据时）、状态行（上次查询 / 查询出错 / 尚未查询）、API 服务状态行（常驻）
- **API 服务状态**：每次轮询额外调用 `status.deepseek.com` API，匹配组件名含 `api` 的项。状态变化时独立弹通知（`api_degraded_title/msg`、`api_recovered_title/msg`）
- **托盘图标新增暖灰色**：API 服务异常时底色变为暖灰 + 余额数字，优先级高于余额高低判断（红色 > 暖灰 > 青色 > 灰色）
- **余额查询容错**：查询失败时若 API 服务已知异常，不清空已有余额数据、不设错误状态
- **低余额提醒**：从二元开关变为三选一下拉，模式切换时 `_alert_suppressed` 状态位自动复位。`"never"` 模式下切回会重新触发
- **右键充值**：托盘菜单新增一项，跳转 `platform.deepseek.com/top_up`

### i18n

以下 Key 为新增，各移植版本需同时支持中英文：

| Key | 中文 | English |
|---|---|---|
| `alert_mode_label` | 低余额提醒： | Low Balance Alert: |
| `alert_mode_never` | 不提醒 | Never |
| `alert_mode_always` | 持续提醒 | Always |
| `alert_mode_once` | 仅提醒一次 | Once |
| `api_alert_label` | API 服务状态变化提醒 | API service status alerts |
| `api_degraded_title` | ⚠️ DeepSeek API 服务异常 | ⚠️ DeepSeek API Degraded |
| `api_degraded_msg` | 检测到 API 服务状态异常… | API service status has changed… |
| `api_recovered_title` | ✅ DeepSeek API 服务恢复 | ✅ DeepSeek API Recovered |
| `api_recovered_msg` | API 服务已恢复正常。 | API service is back to normal. |
| `service_status` | DeepSeek API 服务状态： | DeepSeek API Status: |
| `status_none` | 服务正常 | All Systems Operational |
| `status_minor` | 轻微异常 | Minor Outage |
| `status_major` | 严重异常 | Major Outage |
| `status_critical` | 关键不可用 | Critical Outage |
| `status_maintenance` | 维护中 | Under Maintenance |
| `status_unknown` | 服务状态未知 | Status Unknown |
| `bal_title` | DeepSeek 余额： | DeepSeek Balance: |
| `bal_line` | {balance} {code}（充值 {topped}，赠送 {granted}） | {balance} {code} (Topped {topped}, Granted {granted}) |
| `retention_label` | 日志和记录保留天数： | Log & record retention (days): |

### Removed i18n Keys

以下 Key 已从 Python 版移除，移植版本无需实现：
`topped_up`, `granted`, `currency`, `checking`, `error_fetch`, `bal_msg`, `bal_error_title`, `bal_empty_title`, `bal_currency_line`, `status_line`, `status_line_no`, `preferred_currency`, `currency_label`, `currency_hint`, `enable_alerts`, `enable_alerts_label`
