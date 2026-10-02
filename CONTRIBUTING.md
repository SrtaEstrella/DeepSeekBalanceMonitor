# Contributing

> 本文档描述 v2.0.3 Dev 的 Python-Windows 运行时架构与各端约定，供贡献者快速建立基线。
> 权威细节（配置/密钥存储/多平台矩阵/忙时算法）见 `CLAUDE.md`；agent 高信号事实见 `AGENTS.md`。
> 同一功能存在 Python 与 Rust 双实现，修改 API 客户端 / 忙时速率算法 / 告警逻辑时必须同步检查两端。

## 项目状态

v2.0.3 Dev 包结构；15 平台（DeepSeek/Kimi/StepFun/OpenRouter 按量 + OCGo/MiniMax/Command Code/GLM 套餐）；管理页设为首选按钮；并行/单打双查询模式；Python 与 Rust 双实现。

### 架构总览（v2.0.3 Dev 包结构）

```
src/
├─ tray_app.py            入口编排（托盘主循环），惰性导入 ui.main_window 等
├─ core/                  基础设施（无 UI 依赖）
│   ├─ paths.py             常量+log 叶子
│   ├─ config.py            DEFAULT_CONFIG/CRUD/i18n _T
│   ├─ secure_settings.py   Fernet+SQLite
│   ├─ storage.py           双表读写+消耗速率+get_today_spend
│   └─ app_state.py         AppState 共享状态（含峰谷相位机/单日过快判定）
├─ platforms/             平台注册表与 API 客户端（无 src 依赖）
│   ├─ registry.py          PlatformMeta + PLATFORMS + BILLING_COL_MAP + STATUS_ICON
│   ├─ _http.py             共享层：install_proxy/http_get_json/format_reset_short
│   ├─ deepseek.py          余额 + FlashDuty 状态页
│   ├─ minimax.py           套餐额度（TLS 重试 x3）+ MiniMax 状态页
│   ├─ kimi.py              按量余额 CN(CNY)/Global(USD)
│   ├─ stepfun.py           按量余额 CN(CNY)/Global(USD)，仅 prepaid
│   ├─ command_code.py      Command Code 客户端（窗口 cap 反推档位）
│   └─ opencode.py          OCGo 套餐额度
├─ ui/                    全部 tkinter 界面
│   ├─ main_window.py       懒构建 tabs 主窗
│   ├─ history_dialog.py    HistoryFrame 看板 + LedgerFrame 流水表
│   ├─ manage_frame.py      管理 Tab 组合帧
│   ├─ api_management_frame.py  含设为首选按钮
│   ├─ settings_dialog.py
│   └─ icon_renderer.py     托盘图标渲染（5 态：ok/low/fast/degraded/nodata）
├─ integrations/
│   └─ rainmeter_server.py  Rainmeter HTTP 接口
├─ mac/                   macOS 实现（rumps/pywebview，勿动功能）
└─ webview/               macOS 设置 webview 桥
├─ rust-linux/          Rust CLI+守护+Plasma 小组件（工具链固定 1.77.2）
└─ rust-windows/        Rust Windows 原生 GUI（nwg high-dpi；rustls+webpki-roots 内嵌证书）
```

依赖方向：tray_app → {core, platforms, ui, integrations}；ui → {core, platforms}；core → platforms.registry（叶子）；integrations → {core, ui}。
**循环依赖消解**：`core/paths.py` 打破 config↔secure_settings/storage；`tray_app↔ui.main_window` 双向惰性导入保留。

### 主窗口结构（懒构建）

- Tab 注册表 `_holders/_builders`，内容**首次选中时才构建**；打开后链式预构建其余 tab（每 tick 一个，防卡顿回归）
- Tab 顺序：📊 看板 → 🗂 管理 → ⚙️ 设置 → (🛠 开发者 demo)
- **关键教训：`_ensure()` 必须返回 `win`**——曾因重构丢失 return 导致首次打开全链路失效（窗口不显示、事件不触发、tab 全空白），症状分散难查
- 窗口高度按 DPI 公式计算（两整图表块+第三块 header）
- 图表画布为**固定物理像素高**，不乘 DPI（绘制即物理坐标，字号由 Tk 自动缩放）

## 核心实现与约定

### 1. 多平台注册表 `src/platforms/registry.py`

- `PlatformMeta`: `key/display_name/default_mode/package_windows/has_status_page/console_url` + `default_billing_period`（billing_period 未设时全链路默认窗口）+ `window_pools`（窗口池美元限额，供余额插值模型；仅 OCGo 设置 5h=$12/周=$30/月=$60，其余平台 None 不精化）
- 已注册 15 平台：
  - payg：`deepseek`、`kimi_token_cn/global`（Kimi）、`stepfun_token_cn/global`（StepFun）、`openrouter`（OpenRouter，需 Management Key）
  - package：`opencode_go`、`minimax_token_cn/global`、`minimax_coding_cn/global`、`command_code`、`command_code_goat`、`glm_coding_cn/global`（GLM Coding Plan）
- 添加新平台只需在 PLATFORMS 字典加一行
- 同文件还承载共享常量：`BILLING_COL_MAP/billing_col()`、`STATUS_ICON`

### 2. GLM Coding Plan 与 OpenRouter

- `glm_coding_cn/global`（`src/platforms/glm.py`）：半公开监控端点 `GET /api/monitor/usage/quota/limit`（open.bigmodel.cn / api.z.ai），Bearer 认证（401 时回退裸 Key 一次）；`TOKENS_LIMIT` 第 0/1 条 → 5h/weekly，`TIME_LIMIT` → monthly（MCP 次数）；默认周窗口首选
- `openrouter`（`src/platforms/openrouter.py`）：**仅 Management Key** 可用——`GET /api/v1/credits` 得账户 USD 余额（total_credits − total_usage）；普通推理 Key（401/403）直接报"Invalid or non-management API key"，无 /key 降级
- 两者均无状态页、无套餐忙时预留

### 3. Command Code 平台（`src/platforms/command_code.py`）

- 接口：`GET https://api.commandcode.ai/alpha/whoami`（取 orgId，失败容忍）→ `alpha/billing/credits`（Bearer 认证；无 orgId 也可查）
- 档位自动识别（平台 key 只决定默认计费窗口与插值池）：
  - API 不返回套餐标识（`planId` 已移除）；月度 cap 由 5h/周窗口 cap 对照官方档位表唯一确定：Go 10 / GOAT 70 / Pro 80 / Max 10× 150 / Max 20× 300 / Team Pro 40 credits；两个平台条目都能显示 monthly
  - `credits.monthlyCredits` 为月度剩余（USD）：Python `剩余% = remaining/cap`；Rust `used = clamp(cap − remaining, 0, cap)`；cap 未收录（纯充值账号无滚动窗口）→ monthly 不可用
  - `command_code` 默认周窗口首选；`command_code_goat` 默认月窗口首选并带 `window_pools`（14/35/70）参与插值
- 统一统计“剩余”而非已用：各窗口产出 `percent_remaining` 为主，`usage_percent` 仅派生（100−剩余，最低 0）
- 剩余可 >100%（加成/结余）——Python 端 `monthlyCredits/cap*100` 不 clamp；Rust 端以 cap 内钳制呈现已用；5h/week 仍 clamp [0,100]
- 窗口数据 `{name: usage_percent, percent_remaining, reset_in_sec}`；resetAt 秒/毫秒归一；used/cap 兼容数字或数字字符串
- billing_period 平台默认贯通各消费点：icon_renderer、history_dialog（信息栏/折线/日志列/容耗图 `_get_billing_col`）、tray 通知栏均按 `get_platform(...).default_billing_period` 解析；API 表单未选项时落平台默认
- 若 5h/week/monthly 全缺 → ValueError（无窗口可显示）

### 4. 余额插值模型（OCGo 周/月剩余精化，`storage.get_refined_remaining(_series)`）

- 目标：把 API 整数周/月剩余%（1% 步长）插值为连续小数（如 70 → 70.43）；日消耗分布为次生
- **取整语义实证为 round**（区间交集实验排除 floor 5%；绝对重建排除 ceil 0.4%）——因此区间是 `(obs−0.5, obs+0.5]`，**不是** floor 语义的 `(obs−1, obs]`：一位小数下的整数位由 round 决定，允许落在 `raw±0.5` 内（floor 区间会把估计钉在 raw 之上，实测 864/1258 点偏差 >0.5）
- **池比推进**：5h=$12 / 周=$30 / 月=$60（`window_pools`）；每行推进量 = 该行真实 5h 消耗美元 × 100 ÷ **目标窗口池额**（已知常量）。**切勿改用经验比率**（如「累计消耗/累计涨幅」）：5h 是滚动窗口，重置会吞掉消费，比率偏低约 9%，估计会漂到观测整数之上（曾出现 raw 66 而精化 63.0）
- 模型：维护连续用量估计 `u_cont`，周期重置时锚定为 `obs`；每行 `u_cont += d_usd × 100 ÷ 池额`（仅 `b5 > a5` 时），随后钳到 `(obs−0.5+0.06, obs+0.5−0.06]`——0.06 是显示余量（值先按 2 位存储、再按 1 位格式化，正好 x.5 会跨界）；输出 `剩余 = round(100 − u_cont, 2)`
- **严格因果**（每点只用前驱，新增在线行不改历史值）+ **周期内单调**（余额只降，仅周期重置才跳升）；无 5h 消耗行保持平段（真无消耗）
- 小数位只会落在 **0.2 网格**上（1 个 5h 整数点 = $0.12 = 月池的 0.2%），这是数据分辨率的极限，不是缺陷
- 5h 自身取整（自身窗口整数）不作处理；无 `window_pools` 的平台（minimax/glm、command_code 标准条目）回落原始整数

### 5. 管理 Tab `src/manage_frame.py`（合并 API管理+流水）

- 上半部 = 完整 ApiManagementFrame（增删改查/表单/billing_period）+ ⭐设为首选按钮
- 设为首选复用托盘 `_apply_preferred_switch` 完整链（图标/缓存/主窗同步）；当前首选行按钮禁用并显示"已是首选"
- 下半部 = LedgerFrame(show_selector=False)，由上方表格点选驱动（`on_select` → `ledger.set_api_id`）
- 无 API 时管理表居中提示"请先添加 API"，流水区控件全禁用（防串数据查询）
- 未选中时流水表清空+占位提示（placeholder 需 `lift()` 防 Treeview 覆盖）
- 托盘"添加/编辑"与 show("api_management"/"ledger") 均路由到 manage tab
- **陷阱**：mgmt.refresh() 会触发 on_change → 不得在 _on_api_change 中再回调 mgmt.refresh（递归爆栈）；改为 mgmt.refresh() 末尾重发 `_on_select()` 单向同步
- 首选切换必须走 tray 的 `_apply_preferred_switch` 完整链——仅 set_preferred_api 不刷新图标/缓存

### 6. 看板 HistoryFrame

- 信息栏：Text widget（固定像素×DPI holder + pack_propagate(False)）
  - payg：大字加粗余额（tag_raise("big") 保证优先级）+ 今日消耗/30d日均 + 状态 + 速率 + 上次查询
  - package：各窗口 `标签 [ttk.Progressbar] 剩余%（X重置）`（window_create 内嵌，样式 `ok/warn/crit.Horizontal.TProgressbar` 按余量三档配色）+ 日消耗 + 状态；剩余>100%（加成/结余）文本保留、进度条满格
  - 无数据时显示错误行但仍渲染日消耗/状态
  - 渲染异常兜底：_update_info 外壳 try/except 记日志显示"数据不足"
- 数据源：`app._api_cache[选中api_id]`，缓存空且=首选时回退全局状态
- 三图表块（可滚动 Canvas+Scrollbar，滚轮绑定 Enter/Leave），各块带周期单选：
  1. 余额变动 折线（30/7天）
  2. 每日消耗 热力图(180天)/柱状(30天)
  3. 时段分布 柱状（30/7天）
- 绘图方法签名统一 `(canvas=None, chart_h=None)` 参数化，_draw_block 分发
- **悬浮提示**：canvas._hover_pts 记录命中区域；折线=点命中，柱状=整列矩形命中（零高度柱可命中），热力图=格子矩形；tooltip 贴边翻转防出界
- API 选择器：手动选择保留，`follow_preferred=True` 时跟随 config 首选（托盘切换/设置保存/on_show 传入）；下拉显示仅 API 名称（同名自动 ` #2` 序号），不带平台括注

### 7. 热力图 `_draw_heatmap`

- GitHub 风格：周列（周一首行）、5级绿色渐变按相对量
- 纵向撑满固定画布（cell 由高度反推）、水平居中
- 星期标签贴网格左缘；月份标签位于网格上方留间距；图例已移除
- payg 用落差、package 用涨幅（正增量累加口径同日消耗）

### 8. 双模式与多平台余额

- `apis[].mode`: `payg`/`package`；`apis[].billing_period`: per-API（管理表显示原始字面值）
- 套餐忙时速率已移除（量化百分比下切片算法失真）；日消耗保留
- payg 客户端 schema 映射约定（各平台独立解析文件，映射到应用三字段模型）：
  - total_balance = 可用余额；topped_up_balance = 充值/现金；granted_balance = 赠送/代金券
  - Kimi: available/voucher/cash；StepFun: balance/total_cash_balance/total_voucher_balance
  - 货币随平台区域标注（CNY/USD），写入 balance_history.currency 列
  - **一个账号固定只有一种币种**（CNY 或 USD，由平台区域决定）：`all_balances` 实际只含一条——Kimi/StepFun 的 CN 与 Global 本就是两个独立平台条目，OpenRouter 恒为 USD，DeepSeek 同一账号的 `balance_infos` 也只有一条。所以不存在"同一账号内多币种取舍"的问题，**勿新增"优先某种币种"的逻辑**：前提不成立时它恒等于取首条（Rust 侧曾有过这类想当然的改动）。USD 账号的 `threshold_yuan` 按美元数值填写即可
- **负值语义**：负的分量不是可用余额——DeepSeek 各分量各自钳 0，且 `total_balance` 由**钳后分量重算**（`充值 -0.10 + 赠送 6.00` → 可用 **6.00**，而非 API 原始相加的 5.90）。历史中已存的负分量行在 `storage._connect()` 内幂等修正（仅 `WHERE topped<0 OR granted<0`）
- **陷阱**：`total = 充值 + 赠送` 并非所有平台成立——OpenRouter 的 `topped_up_balance` 是**累计充值**而非剩余现金（`total = total_credits − total_usage`），因此不得对全部历史行按分量重算；上述修正的 WHERE 条件正是为此收窄

### 9. 统计口径（消耗速率与预计可用）

- 速率与「预计可用」基数都读 `balance_history.total`，**不是 `topped`**：消耗可能走赠送余额，只读充值列会得到恒定序列（实测充值恒为 -0.23 → 速率恒 0、预计可用算出负值，界面显示"预计可用忙时 -0.1 小时"）
- 预计可用基数 `max(0.0, 最新 total)` 钳 0（非正余额按耗尽处理）
- 最短速率样本 = `max(60 秒, 半个轮询周期)`，替代原先 0.01 小时（36 秒）的经验值：一个 46 秒区间携带 0.08 落差时会独占权重、外推出 6.26/小时
- 7 天口径无有效样本时回退保留窗口；客户端不重算（`docs/INTERFACES.md` §1.4）

### 10. 托盘与通知

- **双查询模式**（`config.fetch_mode`: `"parallel"` / `"onehot"`，设置页可选，默认 parallel）：parallel = 每轮查全 API；onehot = 仅查首选 API（服务状态也只抓首选平台）；onehot 无首选时本轮跳过查询、保留旧数据但**必须重排 schedule_next_check**（早返回前补调度，否则轮询停止）。缓存语义两模统一：被查询 API 走同一 merge（失败保留旧数据+只更新 error），未被查询的缓存完全不动
- 并行查询所有 API + 按平台并行抓服务状态（statuses dict 按 api.platform 分发入缓存，合并而非覆盖）
- DB 状态写入只写本平台 own_st：无状态页平台（command_code/opencode/kimi/stepfun/glm/openrouter）或抓取失败一律写 NULL，禁止借用首选平台状态
- MiniMax TLS UNEXPECTED_EOF → fetch_minimax_quota 内 3 次重试（间隔1s）+ Connection: close
- 切换首选 → refresh_all(follow_preferred=True)
- 托盘菜单顺序：⚡余额速览（default）→ 📊看板 → API选择 → 立即查询 → 控制台 → 设置；API 选择子菜单仅显示名称
- 峰谷时提醒（默认关，勾选框与API状态变化提醒同行）：GMT+8 周一至五 9–12/14–18 为 △peak，周末与其余为 ▽valley；相位翻转一次性通知；仅首选为 deepseek 时生效
- 单日消耗过快提醒（默认关）：当日忙时正增量达到线值（payg CNY / package %，package 按平台默认窗口）触发一次通知；图标同步变橙

### 11. 服务状态

- DeepSeek → **双源**：`status.deepseek.com`（规范域名，即页面 `custom_domain`）优先，失败回退 FlashDuty 后端主机 `cn.statuspage.flashduty.com/deepseek`；MiniMax → status.minimax.io (LLM 组件)；OCGo/Kimi/StepFun/Command Code → 无
- **历史陷阱**：早期使用的 `status.flashcat.cloud/deepseek` 是 **FlashDuty 自家**状态页（302 到根页面，整页 0 处 deepseek），解析器却照旧返回 operational——该功能因此只可能输出「服务正常」或「状态未知」，异常状态结构上无法出现
- 解析实现（`platforms/deepseek.py` 的 `fetch_service_status()` / `parse_status_page()`）：
  - **页面身份校验**：必须找到 API 类组件（`API\s*服务|API\s*Service`，真实名为 `DeepSeek V4 Pro API服务(API Service)` 等），否则返回 None（界面显示"服务状态未知"）——**认不出就报未知，绝不假报"服务正常"**
  - **RSC 解码**：逐个 `self.__next_f.push([1,"…"])` 块 `json.loads` 解出字符串字面量，再用**带字符串状态的括号配对**取 `active_changes`；禁止用 `\[[^\]]*\]` 这类正则在原文上抓取——告警激活时 `affected_components` 嵌套会让正则截断，`json.loads` 抛错后被兜底 except 吞掉，正好把真实故障变成"未知"
  - 只看 API 类组件；`resolved/completed/scheduled` 的变化不计入；未识别状态按 degraded 计入（**不回落 `none`**）
  - 指示值遵循 `docs/INTERFACES.md` §7.4 的归一表（含 `degraded_performance` → minor、`major_outage` → critical 两个别名）

### 12. 设置页排版（SettingsFrame._build 单行化）

- 单行行式：查询间隔 / 语言 / 保留天数 / 导出路径 / 启用代理+地址同行；开机自启、Rainmeter 各自独立行
- 预警线与单日线各自两行式：前导词完整表述一行 + 缩进组件行（按量/套餐双 spinbox + 低额/过快勾选框缀于对应行尾）
- 主题行含图标描边 checkbox；预览色块 5 态（含 fast）；自定义色输入 grid 3+2 位于色块下方
- API状态变化提醒与 DeepSeek 峰谷时提醒同行
- 作者信息块（_make_link 本地定义：by / RedNote / Contributors / GitHub 链接紧随版本号右侧不指定字体）
- 语言切换：保存检测 lang_changed → mw.close_for_rebuild() 销毁主窗全部懒构建状态，下次打开按新语言重建
- 放弃修改：reload_from_config() 销毁重建 SettingsFrame 回滚控件值
- 未保存弹框仅在**关闭窗口**时出现（hide()/show(key≠settings)/X 协议走 _leave_settings_check）；切 tab 不询问
- 首选展示项已从设置页移除——由管理页 ⭐按钮取代；refresh_preferred_selector/preferred_combo/_pref_map 已删

### 13. 历史表

| 模式 | 表 | 列 |
|---|---|---|
| payg | balance_history | api_id, timestamp, currency, total, topped, granted, service_status |
| package | package_history | api_id, timestamp, h5/weekly/monthly percent+reset, service_status |

Ledger 树列由 `package_windows` + `has_status_page` 动态决定（package 分支勿漏 status 列追加）。

### 14. Rust 双实现

- rust-linux：CLI+守护+Plasma 小组件（`dsmon`），工具链固定 1.77.2（rust-toolchain.toml）；用户级安装免 sudo
- rust-windows：nwg 原生 GUI，声明系统 DPI 感知（app.manifest + high-dpi feature，字体必须 size_absolute）；Command Code 额度显示 + Subscriptions 页
- Command Code monthly 双端口径对照：Rust 展示 used/cap（`档位额度 − monthlyCredits` 钳制），Python 统一剩余口径且剩余可 >100%（加成结余）
- 双端统一 rustls+webpki-roots 内嵌证书（根证书数据靠升级 webpki-roots 依赖维护）
- Rust 端验证由 CI（rockylinux:8 容器 + cargo +1.77.2）承担

## 关键文件清单

| 文件 | 用途 |
|---|---|
| `src/core/paths.py` | 叶子常量+log，无 src 依赖 |
| `src/platforms/registry.py` | 平台注册表（12 平台）+ BILLING_COL_MAP + STATUS_ICON + default_billing_period |
| `src/platforms/_http.py` | 共享 install_proxy/http_get_json/format_reset_short |
| `src/platforms/command_code.py` | Command Code 客户端（5h/weekly + 按窗口 cap 反推档位月度额度） |
| `src/core/config.py` | DEFAULT_CONFIG(retention 180/daily_spend_*)、多API CRUD、i18n _T 字典 |
| `src/core/secure_settings.py` | Fernet+SQLite 加密存储 |
| `src/core/storage.py` | 双表 + get_consumption_rate(billing_period) + get_today_spend |
| `src/ui/manage_frame.py` | 管理 Tab 组合帧 |
| `src/ui/api_management_frame.py` | API 管理表格+表单（on_select 钩子 + ⭐设为首选） |
| `src/ui/main_window.py` | 统一主窗 DSMonitor（懒构建 tabs） |
| `src/ui/history_dialog.py` | HistoryFrame 看板（三图表块/信息栏/悬浮）+ LedgerFrame 流水表 |
| `src/ui/settings_dialog.py` | 设置 Tab（单行排版、dirty tracking、语言重建） |
| `src/tray_app.py` | 托盘主循环、并行轮询、API选择菜单、_apply_preferred_switch |

## 开发注意事项

- API Key 存 secure_settings.db，config.json 永远写空
- ttkbootstrap 尝试后回滚，保持原生 Tk；Canvas 无抗锯齿
- PyInstaller 需 cryptography 在 requirements.txt
- API 切换显示缓存；fetch 失败合并缓存保留旧数据仅更新 error
- 设置保存不触发重查
- 所有 UI 文本必须在 _T 字典中；空值占位符 "-" 不用 em-dash
- PowerShell `Set-Content -Encoding UTF8` 会写 BOM——批量改 py 文件后需剥离 BOM（ast.parse 报 U+FEFF 即此因），或改用 [IO.File]::WriteAllText + UTF8Encoding($false)
- git 全局 http.proxy 指向 127.0.0.1:7890 但本地代理常未运行——用 `git -c http.proxy= fetch` 绕过直连
- 本机 Clash 的 **fake-IP** 模式会把所有域名解析到 `198.18.0.0/16`，而 agent 的 `web_fetch` 会拒绝非公网 IP（SSRF 守卫）→ 外部网页一律取不到。需在 Clash 侧豁免：`%APPDATA%\Clash Plus\Clash Plus\shared_preferences.json` 的 `flutter.config` → `patchClashConfig`，置 `overrideDns: true` 并在 `dns.fake-ip-filter` 加入所需域名（如 `+.github.com`）；**改该文件必须先完全退出 Clash Plus**，否则退出时回写覆盖。另注意 `overrideDns: false` 时该 DNS 设置整块被 App 内置模板忽略
- **Tk 陷阱集**：
  - Text tag 优先级=创建顺序逆序，后建覆盖先建（big 需 tag_raise）
  - Text height 单位按基础字体行高，混合字号需 holder 固定像素+pack_propagate(False)
  - 程序化 notebook.select() 不触发 <<NotebookTabChanged>>（真实点击才触发），关键转换需显式调用
  - window_create 的嵌入 widget 在 delete("1.0","end") 后不会自动销毁，需自行维护引用列表
  - emoji 为非 BMP 字符时勿用 "+Nc" 索引运算加 tag，直接分段 insert 带 tags
  - **首个文案带 emoji 的 `ttk.Button` 在 Windows 上要 0.6–0.9 s**（vista 主题在该次调用里初始化 emoji 字体回退，每进程一次；`ttk.Label` 与 `font.measure` 都不触发）。`tray_app.main()` 启动时用 `T("check_now", lang)` 预热一次
  - **进程内第一个 Toplevel 的首帧绘制另需 0.2–0.3 s**（之后的窗口约 65 ms）。`tray_app.main()` 启动时还映射一个 `-alpha 0` 的不可见窗口（内含几个 ttk 控件）再销毁，把这笔一次性成本一起移出首开路径（实测首帧 327 → 65 ms）
  - **ttk 控件在绘制阶段约 5–7 ms/个**（30 个 label 实测 264 ms）：首屏控件数量直接决定打开卡顿，别往首屏堆控件
  - **画布 `<Configure>` 会在取得真实尺寸之前先触发一次（1×1）**：`_draw_block` 必须先判 `winfo_width() <= 1` 直接返回，否则会白造一整套随即被丢弃的图元（看板首开 9 次绘制里 6 次是这种）
  - **画布图元数量就是绘制成本**：余额折线曾"每个数据点一个圆点"（30 天序列 = 729 个图元，占该区块 98%），而悬停命中判定读的是 `chart._hover_pts` 内存列表、并不需要这些图元 → 等比抽样到 ≤48 个即可保留观感
- 函数内 `from X import log` 会把 log 变成局部名，导致同函数更早的 log() 调用 UnboundLocalError——闭包上层已有则勿再导入。**同类事故**：单实例提示块里多加的 `from src.core.config import load_config, T` 让 `T` 在 `main()` 全程成为局部名，于是正常路径上更早执行的 Tk 预热抛 `UnboundLocalError`（被 except 吞掉，只在日志留一行）——模块级已有 `T`/`load_config`，函数内不要再导入
- **单实例**：`paths.acquire_single_instance()`（Windows 命名互斥体 `Local\<APP_ID>`，其它平台 `flock`）由 `tray_app.main()` 在最前面检查，已被占用时弹一个 5 秒自动关闭的提示再退出。注意用 `tk.Label`+`after` 而非 `messagebox`：后者是模态框，无人点击时会让进程（及其 ~60 MB）一直挂着
- **构建脚本**：`scripts/build_exe.bat` 会先 kill 旧实例并**等它真正退出**再启动新构建——单实例锁生效后，若旧进程还在，新 exe 会直接退出，出现"以为在跑新版、其实是旧版"。脚本内延时用 `ping -n 2 127.0.0.1` 而非 `timeout`：`timeout` 需要控制台 stdin，在 CI / agent 这种 stdin 被重定向的场景会立即报 `Input redirection is not supported` 并变成空转
- **SQLite**：`_connect()` / `_connect_package()` 每次连接设 WAL（文件级持久属性）并确保 `(api_id, timestamp)`、`timestamp` 索引存在。busy timeout 无需自行设置：Python 的 `sqlite3.connect()` 默认已是 5 s
- **本地状态接口**：Rainmeter 的 HTTP 响应**不带** `Access-Control-Allow-Origin`——它携带余额与订阅数据，通配符会让浏览器里任意网页读到并可调 `/check`；Rainmeter 的 WebParser 不依赖 CORS，勿"顺手加回来"