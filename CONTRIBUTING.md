# Contributing - Port Sync Guide

> **⚠️ 2026-05-12：API 服务状态后台已变更**
>
> DeepSeek 官方状态页底层已从 `status.deepseek.com/api/v2` 迁移至 FlashDuty（`status.flashcat.cloud/deepseek`）。原 REST API 不再可用。Python 版 `src/api_client.py` 的 `fetch_service_status()` 已适配新后台（RSC 抓取 + 组件级状态解析），对应单元测试 `tests/test_core.py` 已同步更新。
>
> 各移植版本需同步跟进此变更。

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
| `proxy_enabled` | bool | `false` | Enable HTTP/HTTPS proxy; when disabled, proxy address is preserved |
| `auto_start` | bool | `false` | |

**补充说明**：
- `proxy_enabled`：控制 HTTP/HTTPS 代理是否启用。禁用时保留代理地址不清除。`proxy_enabled` 为 `false` 时，`http_proxy` 配置不生效。

## Notification Format

点击图标查看余额的通知卡片格式（标题 + 多行正文，每行有 emoji 前缀）。文案跟随 `ui_language`，以下为中英文示例：

**中文示例 (`ui_language: "zh"`)**：
```
DeepSeek 余额：                              ← 固定标题
💰 12.34 CNY（充值 10.00，赠送 2.34）        ← 有余额时显示
📊 日均消耗 1.50 | 预计可用 28 天 4 小时  ← 有历史数据时显示
📡 API 服务状态：🟢 服务正常          ← 常驻，emoji 为双指示器
🕐 上次查询：5 分钟前                          ← 仅显示相对时间
```

**英文示例 (`ui_language: "en"`)**：
```
DeepSeek Balance:                              ← Fixed title
💰 12.34 CNY (Topped 10.00, Granted 2.34)      ← Shown when balance available
📊 Avg: 1.50/day | Est. 28d 4h remaining       ← Shown with history data
📡 DeepSeek API Status: 🟢 All Systems Operational ← Always visible, dual indicator emoji
🕐 Last Check: 5 min ago                        ← Relative time only
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

**CLI 输出语言**：所有 CLI 输出必须固定为英文，不随 `ui_language` 切换。

## API Endpoints

| Endpoint | Purpose |
|---|---|
| `api.deepseek.com/user/balance` | 余额查询 |
| `status.flashcat.cloud/deepseek` | FlashDuty 服务状态（RSC 解析，匹配 API 组件） |

## 当前版本变更 (v1.2)

### Config

- **新增** `proxy_placeholder` i18n key，代理地址输入框空时灰色提示文字
- **调整** 代理标签 `HTTP 代理` → `HTTP/HTTPS proxy`

### Behaviour

- **自定义图标配色**：5 套预置主题 + custom 模式，`_get_colors(config)` 统一读取。托盘文字和描边颜色基于背景亮度自选黑白（阈值 170）。保存后图标即时刷新
- **API Key 加密存储**：`src/secure_settings.py`（Fernet + SQLite），`load_config()` → `_resolve_api_key()` 按 secure_settings → credential_store → config.json 三级回退，`save_config()` 自动清空明文字段。这是为了兼容旧版本，新版本应统一使用 SQLite 加密存储。
- **Demo 模式**：API Key 填入 `demo` 触发，读取独立 `demo_mode_balance` 表，不请求真实 API。所有版本统一使用此方式。
- **历史记录页**：右键新增「📊 历史记录」，展示历史记录、消耗速率，并支持 CSV 导出全部记录；图表/表格的具体格式和实现方式不作为跨平台要求
- **消耗速率**：`get_consumption_rate(days=7)` 基于 topped 余额 + 加权平均；7 天数据不足时自动扩大到 `retention_days` 窗口
- **API 服务状态入数据库**：`balance_history` 表新增 `service_status` 列，`save_balance_record` 同步写入
- **通知卡片视觉优化**：每行增加 emoji 前缀（💰📊🕐📡），上次查询改为仅显示相对时间（N 分钟/小时前）
- **HTTP 代理**：启动时读取 `http_proxy` 配置并全局安装，设置页修改后即时生效
- **代理开关**：`proxy_enabled` 复选框 + 地址输入框，关闭时保留地址不清除；地址空时灰色 placeholder
- **设置页优化**：标题简化为 `⚙️ 设置` / `⚙️ Settings`；移除 footer 中的上次查询和余额行
- **Python 版窗口管理**：设置、历史、开发者面板共用 `_tk_root`，避免多 `tk.Tk()` 导致变量/样式冲突。历史和开发者面板支持重复唤起聚焦；该项不是跨平台实现要求

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
| `service_status` | API 服务状态： | API Status: |
| `status_none` | 服务正常 | All Systems Operational |
| `status_minor` | 轻微异常 | Minor Outage |
| `status_major` | 严重异常 | Major Outage |
| `status_critical` | 关键不可用 | Critical Outage |
| `status_maintenance` | 维护中 | Under Maintenance |
| `status_unknown` | 服务状态未知 | Status Unknown |
| `bal_title` | DeepSeek 余额： | DeepSeek Balance: |
| `bal_line` | {balance} {code}（充值 {topped}，赠送 {granted}） | {balance} {code} (Topped {topped}, Granted {granted}) |
| `retention_label` | 日志和记录保留天数： | Log & record retention (days): |
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
| `proxy_enable` | 启用 HTTP/HTTPS 代理 | Enable HTTP/HTTPS proxy |
| `proxy_placeholder` | 代理地址 | Proxy address |

**已移除的 Key**：以下 Key 已从 Python 版移除，移植版本无需实现：
`topped_up`, `granted`, `currency`, `checking`, `error_fetch`, `bal_msg`, `bal_error_title`, `bal_empty_title`, `bal_currency_line`, `status_line`, `status_line_no`, `preferred_currency`, `currency_label`, `currency_hint`, `enable_alerts`, `enable_alerts_label`

### Windows / Port-Specific

- **Rainmeter 小工具**：`rainmeter-widget/`，本地 HTTP 接口 `127.0.0.1:17654`，中英文双 skin，`.rmskin` CI 打包
- **Windows 凭据管理器**：Python Windows 版使用 Windows Credential Manager 加密存储 API Key（v1.2 特性），后续版本将统一使用 SQLite 加密存储
- **Windows 发布签名（可选）**：SignPath.io（免费版，开源项目），fork 开发者自行配置，详见 [CODE_SIGNING.md](CODE_SIGNING.md)

### macOS / Port-Specific

- **macOS Keychain 集成**：Python macOS 版使用 Keychain 加密存储 API Key（v1.2 特性），后续版本将统一使用 SQLite 加密存储
- **macOS WebView 设置界面**：macOS 版使用 WebView 实现设置界面

### Rust / Port-Specific

- **Plasma 6 小工具**（仅支持 Linux Rust）：透明玻璃风格，emoji 状态展示，配置页改用 `dsmon set` 命令
- **Linux SHA256 校验和**：Release 中提供 `checksums.txt` 用于验证 tarball 完整性，详见 [CODE_SIGNING.md](CODE_SIGNING.md)

## 历史变更记录

### v1.1 变更

**Config**：
- `enable_alerts: bool` **已移除**，替换为 `alert_mode: "never" | "always" | "once"`，默认 `"once"`
- **新增** `api_alert_enabled: bool`，默认 `true`。为 `false` 时 API 状态翻转不弹通知，但内存状态位继续追踪
- **新增** `retention_days: int`，默认 `30`。日志和 SQLite 余额历史在每次启动时清理超过此天数的记录
- `preferred_currency` **已移除**。DeepSeek 每个账号只有一种币种，API 返回什么就显示什么
- 所有余额数值不再拼接 `¥`，改为标注实际币种代码（如 `12.34 CNY`）
- 保存设置时必须校验非法输入并提示用户；保存过程不要求原子写入

**Behaviour**：
- **通知卡片重构**：标题使用 `bal_title` 翻译，正文按行排列--余额行（有数据时）、状态行（上次查询 / 查询出错 / 尚未查询）、API 服务状态行（常驻）
- **API 服务状态**：每次轮询额外调用 `status.deepseek.com` API，匹配组件名含 `api` 的项。GUI / tray / widget 状态变化时独立弹通知（`api_degraded_title/msg`、`api_recovered_title/msg`）
- **托盘图标新增暖灰色**：API 服务异常时底色变为暖灰 + 余额数字，优先级高于余额高低判断（红色 > 暖灰 > 青色 > 灰色）
- **余额查询容错**：查询失败时若 API 服务已知异常，不清空已有余额数据、不设错误状态
- **低余额提醒**：从二元开关变为三选一下拉，模式切换时 `_alert_suppressed` 状态位自动复位。`"never"` 模式下切回会重新触发
- **右键充值**：托盘菜单新增一项，跳转 `platform.deepseek.com/top_up`

### v1.0.1 变更

- 初始版本发布
- 基本余额查询和低余额提醒功能
- 设置对话框和托盘图标
- Windows 可执行文件构建脚本
