# 更新日志

所有值得记录的变更均记录于此。

## Rust v1.4.3 (2026-09-12)

### 修复

- Rust 双端：API 不再返回 `credits.planId` 后，Command Code 月度用量会从 CLI、Plasma 小组件、Windows 设置窗口与 Rainmeter `cc_monthly_*` 字段中消失；现改为由 5h/周滚动窗口上限（cap）自动识别档位与月度额度——Go 10 / GOAT 70 / Pro 80 / Max 10× 150 / Max 20× 300 / Team Pro 40 credits
- Rust 双端：月度用量按 `档位额度 − credits.monthlyCredits` 计算并钳制在额度内，加成额度不再产生负数；窗口 cap 未收录的套餐（纯充值账号无滚动窗口）月度仍显示不可用

### 变更

- Command Code：不再解析 `credits.planId`，移除固定 GOAT 70 credits 常量；月度窗口不再要求账号被识别为 GOAT 套餐

### Python 版（本次发布不升版本号）

- Command Code 月度窗口改用同一套窗口 cap 反推逻辑，标准 `command_code` 条目也能显示月度；`command_code_goat` 条目新增 `window_pools`（14/35/70）参与插值
- 保存设置后自动轮询不再静默停止：余额查询循环在 `finally` 中重挂载，设置保存改用 `restart_polling()` 原子取消并重启
- OCGo 精化剩余改为 round 区间语义（`|精化 − 原始| ≤ 0.5`，与 API 取整整数一致），替代原 floor 区间

## Rust v1.4.2 (2026-09-06)

### 修复

- Rust Linux：`status_rank` 把未识别的服务状态排成最高级，状态页中无法解析的组件会掩盖真实的 `critical` 故障——CLI/小组件显示「状态未知」而非「关键不可用」；未知状态改为最低级，与 rust-windows 一致
- Rust 双端：忙时消耗速率算法在判断空闲切片时硬编码 10 分钟查询间隔，现改用配置的 `interval_minutes`；较大间隔（如 60 分钟）下正常轮询间隔不再被误判为空闲切片（此前会低估速率）
- Rust Windows：余额历史与 Rust Linux 一致按 120 秒窗口去重；此前每次查询都无条件入库，即使余额无变化，1 分钟间隔下每币种每天最多膨胀约 1440 行
- Rust Windows：`config.json` 损坏时不再静默重置全部配置——先备份为 `config.json.corrupt` 并写入日志
- Rust Windows：设置窗口先校验全部字段再保存凭据；此前查询间隔/预警线校验失败时，新 DeepSeek Key 已提前写入加密存储
- Rust Windows：导出路径真正展开 `%USERPROFILE%` 前缀；此前占位符只是提示，实际按字面量使用，会生成名为 `%USERPROFILE%` 的目录
- Rust 双端：OpenCode Go 用量百分比钳制到 0–100（此前 Linux CLI 可能打印超过 100% 的值）
- Rust 双端：多币种并存时余额展示与低余额预警优先取 CNY，而非字典序第一个币种（此前可能拿 USD 数值与人民币预警线比较）

### 变更

- Rust 双端：SQLite 启用 WAL 日志模式与 5 秒 busy timeout，并为 `timestamp` 与（`currency`, `timestamp`）建索引；并发访问（Windows UI 线程与余额查询 / OpenCode Go / Command Code / Rainmeter 线程，Linux 守护进程与 widget-status 命令）不再因锁冲突报 "database is locked"，历史查询走索引
- Rust Windows：托盘字体改为进程内加载一次（线程局部缓存），不再每次刷新托盘都读字体文件；移除未使用的 `ensure_config_file`

### 安全

- Rust Windows：通过命名互斥体阻止重复启动——第二实例记录日志、弹出原生提示框后退出，不再出现两个托盘图标争抢同一图标文件与数据库
- Rust Windows：本地 Rainmeter HTTP 服务不再返回 `Access-Control-Allow-Origin: *`，浏览器中打开的任意网页无法再借 CORS 读取余额/订阅数据或触发查询（Rainmeter 的 WebParser 不依赖 CORS）

## Rust v1.4.1 (2026-09-01)

### 变更

- Linux 安装按职责拆分：`dsmon` 二进制与 systemd 用户服务保持系统级安装（`/usr/local/bin/dsmon`、`/etc/systemd/user/dsmon.service`，需 sudo）；Plasma 小组件及其图标安装到用户目录（`~/.local/share/`），后续更新小组件无需 sudo
- Plasma 小组件改用绝对路径 `/usr/local/bin/dsmon` 调用 dsmon，确保 Plasma `executable` 引擎无论会话 PATH 如何都能找到
- 安装完毕后对 sudo 用户自动执行 `systemctl --user enable --now dsmon.service`，守护进程设为登录自启动并立即启动
- 非 systemd 发行版（如 OpenRC）：安装脚本跳过 systemd 服务文件，改为写入桌面自启动项（`~/.config/autostart/deepseek-balance-monitor.desktop`），在桌面登录时启动守护进程
- 安装时检测早期纯用户级安装（1.4.1 预览版：`~/.local/bin/dsmon`、`~/.config/systemd/user/dsmon.service`）遗留的用户级文件，并询问是否清理

## Rust v1.4.0 (2026-09-01)

### 新增

- Command Code 额度显示（Rust Windows 与 Rust Linux）：调用 `api.commandcode.ai/alpha/billing/credits`（经 `alpha/whoami` 获取 `orgId`），报告 5 小时 / 每周 / 每月三档用量；GOAT 套餐按 70 credits 推算月度用量，其他套餐显示为不可用
- Windows：设置窗口新增「订阅」标签页，同时展示 OpenCode Go 与 Command Code 两组额度（各含三档进度条与刷新按钮）；DeepSeek、OpenCode Go、Command Code 三个 API Key 统一在「账户」标签页输入
- Linux：新增 `dsmon command-code`（查询额度）、`dsmon command-code set-key <api_key>`（保存 API Key）与 `dsmon command-code json`（JSON 输出）CLI 命令
- Linux：Plasma 6 小组件新增「订阅」设置页展示 OpenCode Go 与 Command Code 额度，凭据集中在「账户」页；主视图新增 Command Code 区（三档用量进度条）
- Command Code API Key 加密存储于 `secure_settings` 表（独立 key：`command_code_api_key`），绝不写入 config.json
- Rust Windows：本地 Rainmeter `/widget-status` 接口新增 Command Code 额度字段（`cc_configured`、`cc_error`、`cc_5h|weekly|monthly_percent` 与 `_line`），后台线程每 10 分钟刷新缓存、查询失败保留上次成功数据——为后续 Rainmeter 皮肤接入预留接口；约定见 `rainmeter-widget/PYTHON_RAINMETER_INTEGRATION.md`

## Rust v1.3.3 (2026-08-30)

### 变更

- Rust Windows 从 native-tls（Schannel）迁移到 rustls + 内嵌 webpki-roots，与 rust-linux 统一：不再依赖系统证书库，Windows 7/8.1 开箱即用并获得 TLS 1.3；企业代理 / 安全软件做 HTTPS 检查时将无法通过证书校验（仅信任内嵌根证书）
- 移除 `scripts/update_windows_root_certs.bat`：内嵌根证书后不再需要（Python 版本本就仅支持 Windows 10+）；README 的 TLS 章节与目录树已同步更新

### 修复

- 设置窗口分组标题字体渲染错误：加粗标题不再硬编码 Segoe UI（其缺少 CJK 字形，中文 UI 下走字体回退或显示豆腐块），改用统一 UI 字体族并经真实字体枚举回落（Microsoft YaHei UI → Microsoft YaHei / SimSun）；同时去掉误传的 9 像素字号，标题不再小于正文

## Rust v1.3.2 (2026-08-14)

### 变更

- Plasma 6 小组件设置页仿照 rust-windows 重新设计：新增「账户」页集中管理 DeepSeek 与 OpenCode Go 两个 API Key 及 OpenCode 额度进度条；「常规」页按「查询 / 通用 / 代理 / 图标外观」分组；独立的「OpenCode Go」设置页并入「账户」页
- Plasma 小组件主视图重新设计：DeepSeek 区采用四行布局（余额、上次查询、API 服务状态、预计可用），刷新按钮移至右上角并同时刷新 DeepSeek 与 OpenCode；OpenCode 区展示三档用量进度条，字号与进度条高度增大
- 两个区块统一字号层级与间距，视觉层次更清晰
- Rust Windows：本地 Rainmeter `/widget-status` 接口新增 OpenCode Go 额度字段（`og_configured`、`og_error`、`og_rolling|weekly|monthly_percent` 与 `_line`），后台线程每 10 分钟刷新缓存、查询失败保留上次成功数据；接口约定与 Python 版实施建议见 `rainmeter-widget/PYTHON_RAINMETER_INTEGRATION.md`

## Rust v1.3.1 (2026-08-14)

### 变更

- Windows 设置窗口重新设计：新增「账户」标签页集中管理 DeepSeek 与 OpenCode Go 两个 API Key；「设置」标签页按「查询 / 通用 / 代理 / 图标外观」分组，组标题加粗并带分隔线；所有控件对齐统一网格，标签与输入框列宽一致

## Rust v1.3.0 (2026-08-14)

### 变更

- OpenCode Go 额度改用官方 API（`opencode.ai/zen/go/v1/usage`，Bearer API Key 认证），取代原工作区仪表板爬虫方式（workspace ID + auth cookie）
- 凭据简化为单个 API Key，加密存储于 `secure_settings` 表（`opencode_go_api_key`），绝不写入 config.json
- Windows：设置窗口「OpenCode Go」标签页改为填写 API Key（替代原工作区 ID / Auth Cookie）
- Linux：`dsmon opencode-go set-key <api_key>` 保存 API Key；无参数时从 stdin 读取，与 `dsmon set-key` 行为一致
- Plasma：小组件「OpenCode Go」设置页新增 API Key 输入与保存（与 DeepSeek Key 相同模式）；额度进度条改用 `QtControls.ProgressBar` 保证可靠渲染

## Rust v1.2.10 (2026-08-02)

### 新增

- OpenCode Go 额度显示（Rust Windows 与 Rust Linux）：调用官方 `opencode.ai/zen/go/v1/usage` API（Bearer API Key 认证），报告 5 小时滚动 / 每周 / 每月三档用量的已用与剩余百分比及重置时间
- Windows：设置窗口新增「OpenCode Go」标签页，可填写 API Key 并手动刷新
- Linux：新增 `dsmon opencode-go`（查询额度）、`dsmon opencode-go set-key <api_key>`（保存 API Key）与 `dsmon opencode-go json`（JSON 输出）CLI 命令
- Linux：Plasma 6 小组件新增独立的「OpenCode Go」设置页面展示额度，直接从 `dsmon opencode-go json` 读取
- OpenCode Go API Key 加密存储于 `secure_settings` 表（独立 key：`opencode_go_api_key`），绝不写入 config.json

## Rust v1.2.6 (2026-06-08)

### 变更

- 消耗速率算法升级为忙时切片算法（移植自 Python v1.2.7）：过滤长闲时段与平直段，以忙时小时速率替代日均消耗
- 统一全平台显示格式：
  - 中文：`📊 忙时消耗 0.06/小时 | 预计可用 28 天 4 小时`
  - 英文：`📊 Busy: 0.06/hr | Est. 28d 4h remaining`
- 更新 `ConsumptionRate` 结构体：`daily_rate` → `hourly_rate`，`hours_left` → `busy_hours_left`
- 更新演示模式适配新字段
- Plasma 小组件更新为显示忙时小时消耗速率

### 平台特定

- **Rust Windows**：为 Rainmeter 小组件接口添加 `estimated_line` 字段
- **Rust Linux**：移除 `estimated_line`（Plasma 小组件不需要，直接使用 `consumption_rate` 字段）

## Python v1.2.7 (2026-05-28)

### 修复

- 修复 tkinter+pystray 双事件循环死锁导致打开设置/历史窗口时托盘图标卡死

### 变更

- 消耗速率改用忙时切片算法：过滤长闲时段与平直段，以忙时小时速率替代日均消耗显示

## Python v1.2.6 (2026-05-13)

### 修复

- 修复系统代理（Clash 等）关闭后连接拒绝且无法退出软件的问题：空 `ProxyHandler` 拦截系统代理，`socket.setdefaulttimeout` 全局兜底
- 修复无网络时 DNS 解析超时阻塞：全局 socket 超时 + 退出标志位检查
- 修复退出流程中 `cancel_timer` 潜在阻塞导致 `icon.stop()` 无法执行的问题：`icon.stop()` 提前至清理逻辑之前
- 移除 API Key 输入 `demo` 触发开发模式：Python 版仅用 `--demo` 命令

## Python v1.2.5 (2026-05-13)

### 新增

- 开发者 Demo 模式更新：启动时在线生成模拟历史数据；开发者面板新增自定义消耗速率数值显示
- 图标自定义颜色支持实时预览与色值保存时校验
- 历史记录支持按天查询，以 `YYYYMMDD` 格式筛选

### 变更

- 历史记录页解耦为独立模块 `src/history_dialog.py`
- 托盘通知和历史页的速率/时间/前缀等双语字段全面抽取为 i18n key

### 修复

- 修复设置页"启用代理"关闭时 `install_proxy("")` 误用空 `ProxyHandler` 覆盖系统代理的问题

## Rust v1.2.5 (2026-05-12)

### 新增

- 独立 Plasma 小组件发布资产：`deepseek-balance-monitor-*-plasmoid.plasmoid`
- Linux 发布 tar 包现在也在 `plasmoid/` 目录内包含同一套 Plasma 小组件
- Linux 发布资产新增 `checksums.txt`，用于校验 tar 包完整性

### 变更

- Plasma 小组件显示同步 Rainmeter 布局：余额行、相对上次查询时间、API 服务状态和预计剩余时间
- Plasma 小组件语言设置现在会把 `cfg_language` 同步回 `ui_language`，中英文选择在重启 Plasma 后仍保持
- 低余额显示颜色优先于 API 服务异常颜色，与 Rainmeter 点缀色规则保持一致
- Rust Linux 和 Rust Windows 的服务状态查询改用 FlashDuty 后台的 DeepSeek 状态页
- 消耗估算改用 7 天 topped 余额历史，数据不足时 fallback 到保留期窗口
- 代理设置新增显式启用开关，关闭代理时保留代理地址不清除

### 修复

- 修复 Linux Plasma 修改语言后重启 `plasmashell` 又恢复中文的问题
- 修复 Rust 移植版仍调用已移除 DeepSeek 状态 REST API 的问题
- 修复 Windows 设置页标题和底部状态行，使其符合 v1.2 设置页设计


## Python v1.2.2 (2026-05-12)

### 修复

- API 服务状态监测紧急迁移至 FlashDuty 端点，因 DeepSeek 官方已更换状态页底层

## Python v1.2.1 (2026-05-12)

### 新增

- Rainmeter 本地 HTTP 状态接口，启动时自动监听 `127.0.0.1:17654`，可独立开关
- Rainmeter `.rmskin` 皮肤打包脚本，CI 随 Release 自动构建
- Rainmeter 高分屏 2x 缩放版皮肤（中英双版）

### 变更

- API Key 加密存储统一为 Fernet + SQLite，保留原方案兼容性回退；save_config() 自动清空明文字段
- 代理改为开关 + 地址输入框，关闭时保留地址不清除
- 设置页标题简化为 `⚙️ 设置`，移除 footer 中的上次查询和余额行，底部显示版本号与贡献者信息
- 消耗速率恢复为 topped 余额 + 7 天窗口 + 加权平均，支持保留天数 fallback

## Rust v1.2 (2026-05-11)

### 新增

- Rust Windows 与 Rust Linux 版本号统一为 `1.2.0`
- SQLite `secure_settings` 加密存储 API Key（Rust Windows / Linux）
- 旧 `config.json.api_key` 明文自动迁移至加密存储
- Rust demo 模式：API Key 填入 `demo` 触发，数据写入独立 `demo_mode_balance` 表
- Rust Linux `dsmon set-key` 命令，加密更新 API Key
- Rust Linux `dsmon set <field> <value>` 命令，单字段配置更新
- Rust Linux 安装器首次检测到无 Key 或 Key 无效时提示输入
- Rust Linux `uninstall.sh` 卸载脚本（保留 Plasma 小组件）
- Plasma 6 小组件液态玻璃风格视图，支持余额、上次查询、服务状态、可用天数、刷新控制、emoji 状态文字
- Rainmeter 桌面小组件，通过本地 `127.0.0.1:17654` 接口获取数据；Rust Windows 现已提供该接口
- GitHub Actions 通过 `rmskin-builder` 自动打包 `.rmskin`

### 变更

- Rust Linux daemon 每次轮询重新读取配置，CLI 修改即时生效
- Rust Linux CLI 固定英文输出，不弹桌面通知
- Rust Windows 首次无 Key 时弹出设置对话框
- Rust Windows/Linux 分离 `ui_language`（GUI）与 `language`（CLI 固定英文）
- Rust CSV 导出默认保存到用户主目录，文件名带日期后缀
- Rust demo 余额不污染真实 `balance_history` 表
- Plasma 小组件设置改用 `dsmon set` 命令

## Python v1.2 (2026-05-11)

### 新增

- 自定义图标配色：5 套预置主题（默认/高对比/明亮/暗色模式/纯灰度）+ 自定义 hex 颜色 + 图标描边开关
- 历史记录页：分页表格 + 折线图 + 消耗速率分析，支持 CSV 导出
- 消耗速率估算：基于 topped 余额的非递增区间加权平均，在余额通知和历史页同步显示
- Demo 模式：`--demo` 启动，右键开发者面板调节各种参数
- HTTP 代理支持
- API Key 加密存储于 Windows 凭据管理器，config.json 降级为迁移入口
- MacOS WebView 设置界面
- 核心 API 解析和状态迁移的单元测试覆盖

### 变更

- 余额通知卡片：emoji 前缀 + 仅显示相对时间 + 服务状态调整到时间之前
- API 服务状态同步写入本地数据库
- 设置、历史、开发者面板共享 Tk 根窗口，避免窗口冲突；历史和开发者面板支持重复唤起聚焦
- 设置页底部显示版本号/贡献者/项目链接
- MacOS 构建脚本增加 DMG 打包

## Rust v1.1 (2026-05-10)

### 新增

- Rust Windows 原生托盘程序，支持 Win7+
- Rust Linux CLI + KDE Plasma 6 小组件
- Rust 历史功能：图表、天数/币种筛选、CSV 导出、`dsmon history` CLI
- Plasma 小组件守护进程启停 + 命令错误通知
- Windows 7/8.1 根证书更新辅助脚本

### 修复

- 修复 Plasma 小组件配置页
- Rust Windows 构建补充应用图标

## Python v1.1 (2026-05-10)

### 新增

- API 服务状态轮询（`status.deepseek.com`），托盘图标 API 异常时显示暖灰色，状态变化独立通知
- 托盘菜单「充值」直达 `platform.deepseek.com/top_up`
- SQLite 余额历史存储，日志与记录自动清理，可配置保留天数（默认 30 天）
- 社区移植 Python MacOS 应用程序，Keychain 加密
- 新增 CONTRIBUTING.md 供社区移植者参考
- GitHub Actions 自动构建，打包 Python EXE 并挂到 Release

### 变更

- 低余额提醒三选一：不提醒 / 持续提醒 / 仅提醒一次，默认仅一次
- 余额通知卡片重构：固定标题 + 内嵌明细 + 服务状态常驻
- 设置保存时校验字段数值范围或非法输入，并弹出警告
- 移除 `requests`，改用 stdlib `urllib.request`

## Rust v1.0.1 (2026-05-09)

内部开发版本号为 Windows v0.1.0/v0.1.1 及 Linux v0.2.0

### 新增

- 初始 Rust Windows 原生构建
- GitHub Actions Rust Windows 构建产物发布流程
- 编写 Rust Windows 构建文档
- 将 Rust Windows 移植合并入上游 Python 主分支
- 初始 Rust Linux `dsmon` 发布构建
- Linux 打包基础，支持命令行余额查询

### 修复

- Rust Windows 启动构建流程加固
- Rust workflow tag 触发器调整为 `rust-v*`，避免与 Python 版冲突
- 更新 Rust 移植同步文档

## Python v1.0.1 (2026-05-09)

### 变更

- 仓库结构重组为 `src/` 和 `scripts/`
- 废弃货币选择逻辑，因每个账号对应固定单一币种
- 设置对话框行为改进
- API Key 字符编码加固
- 图标配色和提醒开关优化
- README 文档更新：推荐直接下载为首选安装方式，优化预览图
- 代码审计、格式清理

## Python v1.0.0 (2026-05-06)

### 新增

- 首次公开发布 Python Windows 托盘应用
- 定时 DeepSeek 余额查询
- 低余额提醒
- 设置对话框（API Key、查询间隔、阈值、语言、开机自启）
- 托盘图标渲染
- Windows 可执行文件打包脚本
