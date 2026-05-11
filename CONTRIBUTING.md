# Contributing - Port Sync Guide

## Config Schema (v1.2)

移植版本必须兼容以下 `config.json` 字段。未知字段应保留不删，忽略即可。
下表是 v1.2 目标 schema；当前 Python 版未实现的新增行为在 `Changed Since v1.2` 中单独列出。

| Key | Type | Default | Notes |
|---|---|---|---|
| `api_key` | string | `""` | deprecated — plaintext is only read for migration; runtime key is stored encrypted in SQLite and config.json holds `""` |
| `interval_minutes` | int | `10` | 1–1440 |
| `threshold_yuan` | float | `1.0` | 0–10000 |
| `language` | string | `"en"` | reserved for command-line/non-GUI text and legacy compatibility; CLI output must stay English and user settings should not expose this field |
| `ui_language` | string | `"zh"` | GUI / tray / widget language; `"zh"` or `"en"` |
| `alert_mode` | string | `"once"` | `"never"` / `"always"` / `"once"` |
| `api_alert_enabled` | bool | `true` | |
| `retention_days` | int | `30` | 1–3650 |
| `theme` | string | `"default"` | `"default"` / `"contrast"` / `"bright"` / `"dark_mode"` / `"mono"` / `"custom"` |
| `icon_colors` | object | `{}` | `{"ok":"3C6966","low":"B9463C","degraded":"78695A","nodata":"69696E"}` - only used when `theme` is `"custom"` |
| `icon_stroke` | bool | `false` | icon outline colour matches text (white/black based on background) |
| `export_path` | string | `""` | directory for CSV exports; empty = user home directory |
| `http_proxy` | string | `""` | HTTP/HTTPS proxy URL, e.g. `http://127.0.0.1:7890` |
| `auto_start` | bool | `false` | |

## Notification Format

点击图标查看余额的通知卡片格式（标题 + 多行正文，每行有 emoji 前缀）。文案跟随 `ui_language`，以下为中文示例：

```
DeepSeek 余额：                              ← 固定标题
💰 12.34 CNY（充值 10.00，赠送 2.34）        ← 有余额时显示
📊 日均消耗 1.50 | 预计可用 28 天 4 小时  ← 有历史数据时显示
📡 API 服务状态：🟢 服务正常          ← 常驻，emoji 为双指示器
🕐 上次查询：5 分钟前                          ← 仅显示相对时间
```

## CLI Operations

当前只有 Rust Linux 版提供用户可直接使用的 CLI，命令名为 `dsmon`。Windows / macOS 如后续增加 CLI，应遵循相同语义，但现阶段仍以 GUI / 托盘为主。

| Command | Requirement |
|---|---|
| `dsmon init-config` | 仅在配置不存在时创建默认配置，不覆盖未知字段 |
| `dsmon set-key` | 从 stdin 或参数读取 API Key，加密写入 SQLite `secure_settings`，并确保 `config.json.api_key` 为空；`demo` 触发演示模式 |
| `dsmon set <field> <value>` | 修改单个配置字段并校验非法输入；不得用于 API Key，API Key 必须走 `set-key` |
| `dsmon check` | 手动查询一次余额，输出固定英文，不发送桌面通知，并写入历史记录 |
| `dsmon daemon` | systemd 用户服务使用的轮询模式；每轮必须重新读取配置 |
| `dsmon history [days]` | 输出英文历史统计摘要，不要求输出原始行 |
| `dsmon history export [days] [currency\|all] [path\|-]` | 导出 CSV；未指定路径时使用 `export_path` 或用户主目录 |
| `dsmon widget-status` | 输出 Plasma 小组件消费的 JSON，字段变化需兼容旧小组件 |

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
- 保存设置时必须校验非法输入并提示用户；保存过程不要求原子写入

### Behaviour

- **通知卡片重构**：标题使用 `bal_title` 翻译，正文按行排列--余额行（有数据时）、状态行（上次查询 / 查询出错 / 尚未查询）、API 服务状态行（常驻）
- **API 服务状态**：每次轮询额外调用 `status.deepseek.com` API，匹配组件名含 `api` 的项。GUI / tray / widget 状态变化时独立弹通知（`api_degraded_title/msg`、`api_recovered_title/msg`）
- **托盘图标新增暖灰色**：API 服务异常时底色变为暖灰 + 余额数字，优先级高于余额高低判断（红色 > 暖灰 > 青色 > 灰色）
- **余额查询容错**：查询失败时若 API 服务已知异常，不清空已有余额数据、不设错误状态
- **低余额提醒**：从二元开关变为三选一下拉，模式切换时 `_alert_suppressed` 状态位自动复位。`"never"` 模式下切回会重新触发
- **右键充值**：托盘菜单新增一项，跳转 `platform.deepseek.com/top_up`
- **Windows 凭据管理器**：API Key 优先从 Windows Credential Manager 读取（加密存储），`config.json` 保存空 `api_key` 作为兼容占位
- **Demo 模式**：Python 版通过 `--demo` 启动参数进入 Demo 模式，使用内存预设数据并显示开发者工具入口

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
- **新增** `export_path: string`，CSV 导出目录。Python 版空时弹保存对话框；指定目录时自动生成时间戳文件名
- **新增** `http_proxy: string`，HTTP/HTTPS 代理地址。各版本按自身 HTTP client 机制应用代理配置

### Behaviour

- **自定义图标配色**：5 套预置主题 + custom 模式，`_get_colors(config)` 统一读取。托盘文字和描边颜色基于背景亮度自选黑白（阈值 170）。保存后图标即时刷新
- **API Key 加密存储**：API Key 不再写入 config.json；Python Windows 版使用 Credential Manager，macOS 版使用本地加密存储。`load_config()` 仍兼容读取旧 config.json 中的 key 作为迁移 fallback
- **Demo 模式**：Python 版通过 `--demo` 启动，`app.demo_mode = True`，`do_balance_check` 使用预设数据
- **历史记录页**：右键新增「📊 历史记录」，展示历史记录、消耗速率，并支持 CSV 导出全部记录；图表/表格的具体格式和实现方式不作为跨平台要求
- **消耗速率**：`get_consumption_rate()` 基于总余额 `total` 计算非递增区间，按时长加权平均，返回日均消耗和预计剩余天/小时。余额通知和历史页同步显示
- **API 服务状态入数据库**：`balance_history` 表新增 `service_status` 列，`save_balance_record` 同步写入
- **通知卡片视觉优化**：每行增加 emoji 前缀（💰📊🕐📡），上次查询改为仅显示相对时间（N 分钟/小时前）
- **HTTP 代理**：启动时读取 `http_proxy` 配置并全局安装，设置页修改后即时生效
- **Python 版窗口管理**：设置、历史、开发者面板共用 `_tk_root`，避免多 `tk.Tk()` 导致变量/样式冲突。历史和开发者面板支持重复唤起聚焦；该项不是跨平台实现要求

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
| `proxy_label` | HTTP/HTTPS 代理： | HTTP/HTTPS proxy: |
| `proxy_hint` | 例如 http://127.0.0.1:7890，留空则不使用 | e.g. http://127.0.0.1:7890, leave blank to disable |

## Changed Since v1.2

### Config

- **新增** `ui_language: string`，GUI / 托盘 / 小工具界面语言统一读取该字段；`language` 保留给命令行/兼容旧配置并固定默认英文。旧配置仅有 `language` 时，迁移版本应复制到 `ui_language` 后保存
- **调整** `export_path` 默认导出位置：空值时使用用户主目录；默认文件名为 `deepseek-balance-history-YYYYMMDD.csv`

### Behaviour

- **API Key 统一 SQLite 加密存储**：Windows / macOS / Linux 各版本统一使用 SQLite `secure_settings` 表加密保存 API Key。`config.json.api_key` 仅作为旧版本迁移入口；加载到非空值时必须自动写入 SQLite，并立即保存为 `""`
- **Demo 模式统一入口**：所有版本通过 API Key 填入 `demo` 触发，固定读取独立 SQLite `demo_mode_balance` 表中的预设数据，不请求真实 API，不写入真实历史表
- **CLI 输出**：Linux / Windows / macOS 命令行输出统一使用英文，不随 `ui_language` 切换；Linux 命令行版不主动发送桌面通知
- **Linux 配置命令**：`dsmon set <field> <value>` 保存后，daemon 下一轮轮询和手动查询命令必须读取最新配置
