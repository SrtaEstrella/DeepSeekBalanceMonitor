# Contributing - Port Sync Guide

## Config Schema (v1.1)

移植版本必须兼容以下 `config.json` 字段。未知字段应保留不删，忽略即可。

| Key | Type | Default | Notes |
|---|---|---|---|
| `api_key` | string | `""` | deprecated — stored in system credential manager, config.json holds `""` as fallback |
| `interval_minutes` | int | `10` | 1–1440 |
| `threshold_yuan` | float | `1.0` | 0–10000 |
| `language` | string | `"zh"` | `"zh"` or `"en"` |
| `alert_mode` | string | `"once"` | `"never"` / `"always"` / `"once"` |
| `api_alert_enabled` | bool | `true` | |
| `retention_days` | int | `30` | 1–3650 |
| `theme` | string | `"default"` | `"default"` / `"contrast"` / `"bright"` / `"dark_mode"` / `"mono"` / `"custom"` |
| `icon_colors` | object | `{}` | `{"ok":"3C6966","low":"B9463C","degraded":"78695A","nodata":"69696E"}` - only used when `theme` is `"custom"` |
| `icon_stroke` | bool | `false` | icon outline colour matches text (white/black based on background) |
| `export_path` | string | `""` | directory for CSV exports; empty = ask on export |
| `http_proxy` | string | `""` | HTTP/HTTPS proxy URL, e.g. `http://127.0.0.1:7890` |
| `auto_start` | bool | `false` | |

## Notification Format

点击图标查看余额的通知卡片格式（标题 + 多行正文，每行有 emoji 前缀）：

```
DeepSeek 余额：                              ← 固定标题
💰 12.34 CNY（充值 10.00，赠送 2.34）        ← 有余额时显示
📊 日均消耗 1.50 | 预计可用 28 天 4 小时  ← 有历史数据时显示
📡 API 服务状态：🟢 服务正常          ← 常驻，emoji 为双指示器
🕐 上次查询：5 分钟前                          ← 仅显示相对时间
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

- **通知卡片重构**：标题固定为 `DeepSeek 余额：`，正文按行排列--余额行（有数据时）、状态行（上次查询 / 查询出错 / 尚未查询）、API 服务状态行（常驻）
- **API 服务状态**：每次轮询额外调用 `status.deepseek.com` API，匹配组件名含 `api` 的项。状态变化时独立弹通知（`api_degraded_title/msg`、`api_recovered_title/msg`）
- **托盘图标新增暖灰色**：API 服务异常时底色变为暖灰 + 余额数字，优先级高于余额高低判断（红色 > 暖灰 > 青色 > 灰色）
- **余额查询容错**：查询失败时若 API 服务已知异常，不清空已有余额数据、不设错误状态
- **低余额提醒**：从二元开关变为三选一下拉，模式切换时 `_alert_suppressed` 状态位自动复位。`"never"` 模式下切回会重新触发
- **右键充值**：托盘菜单新增一项，跳转 `platform.deepseek.com/top_up`
- **Windows 凭据管理器**：API Key 优先从 Windows Credential Manager 读取（加密存储），`config.json` 作为 fallback。移植版需兼容：`load_config()` 在加载文件后尝试 `read_credential()`，有值时覆盖 `api_key` 字段
- **Demo 模式**：`--demo` 启动参数跳过真实 API 调用，使用预设数据。Demo 模式下 `app.demo_mode = True`，托盘菜单额外显示「开发者」选项，打开后可自由调节余额、错误状态、API 状态等参数

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

以下 Key 已从 Python 版移除，移植版本无需实现：
`topped_up`, `granted`, `currency`, `checking`, `error_fetch`, `bal_msg`, `bal_error_title`, `bal_empty_title`, `bal_currency_line`, `status_line`, `status_line_no`, `preferred_currency`, `currency_label`, `currency_hint`, `enable_alerts`, `enable_alerts_label`

## Changed Since v1.1

### Config

- **新增** `theme: string`，默认 `"default"`。可选 `"contrast"` / `"bright"` / `"dark_mode"` / `"mono"` / `"custom"`
- **新增** `icon_colors: object`，仅在 `theme: "custom"` 时生效，含 `ok`/`low`/`degraded`/`nodata` 四个 6 位 hex 值
- **新增** `icon_stroke: bool`，默认 `false`。描边颜色随文字自适应
- **新增** `export_path: string`，CSV 导出目录。空时弹保存对话框
- **新增** `http_proxy: string`，HTTP/HTTPS 代理地址。启动时通过 `urllib.request.ProxyHandler` 全局安装

### Behaviour

- **自定义图标配色**：5 套预置主题 + custom 模式，`_get_colors(config)` 统一读取。托盘文字和描边颜色基于背景亮度自选黑白（阈值 170）。保存后图标即时刷新
- **Windows 凭据管理器**：API Key 不再写入 config.json，专存系统凭据管理器。`load_config()` 仍兼容读取旧 config.json 中的 key 作为迁移兜底
- **Demo 模式**：`--demo` 启动，`app.demo_mode = True`，`do_balance_check` 使用预设数据。右键菜单新增「🛠 开发者」面板调节各种参数
- **历史记录页**：右键新增「📊 历史记录」，Treeview 分页表格（100 条/页）+ Canvas 折线图（与表格数据同步，上限 1000 点）+ 消耗速率标签。支持 CSV 导出全部记录
- **消耗速率**：`get_consumption_rate()` 基于 topped 余额计算非递增区间，按时长加权平均，返回日均消耗和预计剩余天/小时。余额通知和历史页同步显示
- **API 服务状态入数据库**：`balance_history` 表新增 `service_status` 列，`save_balance_record` 同步写入
- **通知卡片视觉优化**：每行增加 emoji 前缀（💰📊🕐📡），上次查询改为仅显示相对时间（N 分钟/小时前）
- **HTTP 代理**：启动时读取 `http_proxy` 配置并全局安装，设置页修改后即时生效
- **共享 tk 根窗口**：设置、历史、开发者面板共用 `_tk_root`，避免多 `tk.Tk()` 导致变量/样式冲突。历史和开发者面板支持重复唤起聚焦

以下 Key 为新增，各移植版本需同时支持中英文：

| Key | 中文 | English |
|---|---|---|
| `dev_tools` | 🛠 开发者 | 🛠 Dev Tools |
| `history` | 📊 历史记录 | 📊 History |
| `icon_stroke_label` | 图标描边 | Icon stroke |
| `theme_label` | 图标主题： | Icon Theme: |
| `theme_default` | 默认 | Default |
| `theme_contrast` | 高对比 | High Contrast |
| `theme_bright` | 明亮 | Bright |
| `theme_dark_mode` | 暗色模式 | Dark Mode |
| `theme_mono` | 纯灰度 | Monochrome |
| `theme_custom` | 自定义 | Custom |
| `export_label` | 数据导出路径： | Export path: |
| `export_browse` | 浏览 | Browse |
| `proxy_label` | HTTP 代理： | HTTP proxy: |
| `proxy_hint` | 例如 http://127.0.0.1:7890，留空则不使用 | e.g. http://127.0.0.1:7890, leave blank to disable |

## Changed Since v1.2 (待实现)

- **API Key 跨平台统一存储**：将 API Key 存储从 Windows Credential Manager 改为 Windows/Linux 统一的 SQLite `secure_settings` 加密存储，解决 Linux 版无系统凭据管理器的问题
- **config.json.api_key 只作迁移入口**：`load_config()` 中读取旧 `config.json` 的 `api_key` 仅用于首次迁移，迁移后必须清空文件中的明文字段
- **代理文案调整**：`HTTP 代理` → `HTTP/HTTPS proxy`，与底层实现一致（ProxyHandler 同时覆盖 http 和 https）