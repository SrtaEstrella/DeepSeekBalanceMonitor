# Rust 与 Python 版共同暴露的接口

本文件列出一个「实现」对外必须一致的东西。现有实现是纯 Rust 的 `dsmon2`（`dsmon-core` + `dsmon-ui`），
将来若有 Python 实现，它**只要按本文件实现第 1 节，桌面小工具就能直接用，不需要改一行**（见
`WIDGET.md`）；第 2–7 节则是两个版本能在同一台机器上共存、并共用同一份用户数据的前提。

读法：

- 🔒 = **契约**。改了就会破坏另一个实现或小工具，必须两边同步改并升级 `version`。
- ⚙️ = 实现细节。各自怎么写都行，但**对外表现**要一致（例如托盘用什么库无所谓，D-Bus 名必须是那个）。
- 取值一律以代码为准，本文件只是索引：路径看 `dsmon-core/src/paths.rs`，配置看 `config.rs`，
  库表看 `storage.rs`，平台清单看 `catalog.rs`。**文档与代码不一致时，改文档。**

---

## 1. 本地数据接口 🔒

小工具与任何第三方客户端**只**通过这里取数。这是两版之间唯一的运行时接口。

### 1.1 传输

| 项 | 值 |
|---|---|
| 监听地址 | `127.0.0.1:18964` —— **只绑回环**，不绑 `0.0.0.0` |
| 端口 | 固定 18964（1.x 的 Rainmeter 接口占 17654，两者并存不冲突）。不做备选段、不写端口文件 |
| 绑定失败 | 记日志、接口不可用，**主程序照常运行**；客户端提示要写「主程序未运行，或端口 18964 被占用」 |
| 启用条件 | 主程序在跑就监听（常开），进程退出即消失；没有单独的开关 |
| 协议 | 最小 HTTP/1.x：只需解析请求行；响应 `Connection: close`，不做 keep-alive |
| 响应头 | `Content-Type: application/json; charset=utf-8`、`Cache-Control: no-store` |

### 1.2 端点

| 方法与路径 | 语义 | 响应 |
|---|---|---|
| `GET /widget-status?days=1\|7\|30` | 返回当前缓存快照。`days` 缺省 7，非法值按 7 处理；**只影响 `series`** | `200` + 载荷 |
| `GET /check` | 触发一次后台轮询，**立即返回当前快照**（不等待查询完成） | `200` + 载荷 |
| 其他路径 | — | `404` |
| 非 GET | — | `405` |

### 1.3 载荷 🔒

```json
{
  "version": 2,
  "provider": { "name": "dsmon2", "version": "2.1.2" },
  "generated_at": "2026-09-15 10:42:00",
  "lang": "zh",
  "checking": false,
  "service_status": "none",
  "last_check_at": "2026-09-15 10:42:00",
  "last_check_sec": 42,
  "today_spend": { "platform": "deepseek", "currency": "CNY", "amount": 12.5 },
  "platforms": [
    {
      "key": "deepseek", "display": "DeepSeek", "kind": "payg",
      "balances": [{ "currency": "CNY", "total_balance": 12.34,
                     "topped_up_balance": 10.0, "granted_balance": 2.34 }],
      "rate": { "hourly_rate": 0.42, "busy_hours_left": 291.5, "currency": "CNY" },
      "windows": [],
      "series": [{ "t": 1757900000, "v": 12.34 }],
      "daily": [{ "date": "2026-09-14", "used": 3.2, "weekday": 0 }]
    }
  ]
}
```

| 字段 | 类型 | 说明 |
|---|---|---|
| `version` | 整数 | 载荷格式的主版本，当前 **2**。客户端遇到不认识的主版本要提示「主程序版本过新，请升级」，不要装作连不上 |
| `provider` | 对象 | 谁在供数（`name` + 版本），便于诊断 |
| `generated_at` | 字符串 | 生成时刻，`%Y-%m-%d %H:%M:%S`（与数据库同格式） |
| `lang` | 字符串 | 主程序当前语言，`zh` / `en`；**给小工具之外的消费者参考**，小工具自己从配置读 |
| `checking` | 布尔 | 是否有轮询在飞行中 |
| `service_status` | 字符串 | 服务状态指示，取值见 §7.4 |
| `last_check_at` | 字符串｜null | 上次成功查询的时刻，**已格式化**（`%Y-%m-%d %H:%M:%S`）；客户端直接显示，不需要日期库 |
| `last_check_sec` | 整数｜null | 距上次成功查询的秒数，供客户端判断数据新鲜度 |
| `today_spend` | 对象｜null | 某个余额平台**今天已经花掉的金额**：`platform`（哪个平台）、`currency`、`amount`。算法是「当日第一条读数 − 最后一条」（与历史页的 `1d` 同一个滚动窗口），余额上升（充值）或当天只有一条读数时为 `null`——**没有可比的东西就不报数**，不拿 0 冒充。客户端应把它显示在**对应平台**的卡片上 |
| `platforms[].key` | 字符串 | 平台标识，与 §2 的密钥名、§3 的 `platform` 列**同一个值** |
| `platforms[].display` | 字符串 | 展示名（专有名词，不翻译） |
| `platforms[].kind` | 字符串 | `payg`（余额）或 `package`（额度窗口），同 `catalog::Mode` |
| `platforms[].balances[]` | 数组 | 各币种余额，字段同 `model::Balance`（`total_balance` / `topped_up_balance` /
`granted_balance`）；`package` 平台通常为空 |
| `platforms[].rate` | 对象｜null | `hourly_rate`（每小时消耗，**固定 7 天口径**）+ `busy_hours_left`（预计可用小时数）+ `currency` |
| `platforms[].windows[]` | 数组 | 额度窗口：`name_key`（i18n 键）、`usage_percent`、`reset_in_sec` |
| `platforms[].series[]` | 数组 | **余额曲线**，按 `days` 截取，**降采样到 ≤240 点**；`t` 秒级时间戳、`v` 总余额 |
| `platforms[].daily[]` | 数组 | 每日用量（热力图）：`date`（`YYYY-MM-DD`）、`used`、`weekday`（0=周一，客户端据此排版，仍不需要日期库） |

### 1.4 不变式 🔒

1. **只含已配置平台**（该平台有密钥），顺序按 `catalog::PLATFORMS`；一个都没有就是空数组。
2. **窗口名给键、不给成品文案**：`name_key` ∈ {`window_5h`, `window_weekly`, `window_monthly`}，
   由客户端翻译（客户端与主程序共用同一张 i18n 表）。
3. **不传凭据**：响应里没有任何 API Key、密文或密钥材料；客户端不需要提供任何凭据，**接口不做鉴权、
   没有令牌**（本机单用户工具，只绑回环）。任何想给这个接口加认证的方案都不必做。
4. **除 `/check` 外无写操作**；`/check` 也只是触发一次轮询，不改配置、不改数据。
5. `rate` 是**7 天口径**（无数据回退到保留窗口），与主程序状态页显示的是同一个数——客户端不要重算。
6. `series` 与 `daily` 只给数字，不含文案。
7. 单个响应体量控制在几十 KB 以内（`series` 降采样就是为此）。

---

## 2. 配置文件 `config.json` 🔒

| 平台 | 路径 |
|---|---|
| Linux | `$XDG_CONFIG_HOME/dsmon2/config.json`（缺省 `~/.config/dsmon2/`） |
| Windows | `%APPDATA%\dsmon2\config.json` |

**本文件不含任何密钥**：API Key 只在 `secure_settings`（§3），所以小工具这类只读客户端可以放心读它来取主题、
语言与窗口设置（这是它唯一会打开的配置来源）。

**必须原子写**（写同目录临时文件再 `fs::rename`）。两个进程会同时读写这一份文件：小工具每 2 秒重读一次
（拿主题、语言、窗口设置），主程序保存设置时会写。非原子写会让读者读到半截 JSON，而现有实现遇到解析
失败会把文件改名为 `config.json.corrupt` 并回落到默认值——两进程共用时就等于**静默清空用户设置**。

字段（默认值 / 取值范围）：

| 字段 | 类型 | 默认 | 范围或取值 | 用途 |
|---|---|---|---|---|
| `interval_minutes` | 整数 | 10 | 1–1440 | 轮询间隔 |
| `threshold_yuan` | 浮点 | 1.0 | ≤10000 | 低余额告警阈值 |
| `ui_language` | 字符串 | `zh` | `zh` / `en` | 界面与通知语言；**小工具也读它** |
| `auto_start` | 布尔 | false | — | 开机自启 |
| `alert_mode` | 字符串 | `once` | `once` / `always` / `never` | 低余额告警频率 |
| `api_alert_enabled` | 布尔 | true | — | 服务状态异常是否告警 |
| `retention_days` | 整数 | 30 | 1–3650 | 历史保留天数（裁剪与日志共用） |
| `export_path` | 字符串 | 空 | 目录路径 | CSV 导出目录，空=家目录 |
| `http_proxy` | 字符串 | 空 | `host:port` | 代理地址 |
| `proxy_enabled` | 布尔 | false | — | 是否走代理 |
| `ui_theme` | 字符串 | `system` | `system` / `light` / `dark` | 明暗；**小工具也读它** |
| `theme` | 字符串 | `default` | `default`/`contrast`/`bright`/`dark_mode`/`mono`/`custom` | 颜色风格 |
| `icon_colors` | 对象 | 空 | 键 `ok`/`degraded`/`low`/`error` → `#rrggbb` | 自定义配色（`theme=custom` 时） |
| `icon_stroke` | 布尔 | false | — | 图标描边 |
| `widget_enabled` | 布尔 | false | — | **主程序启动时是否拉起小工具**（不控制端口）；托盘的「显示/隐藏桌面小工具」就是改它。小工具**读到 true→false 会自己退出**，所以取消显示不必去杀进程 |
| `widget_size` | 字符串 | `standard` | `compact` / `standard` | 小工具尺寸预设 |
| `widget_opacity` | 浮点 | 0.9 | **四档 0.25 / 0.50 / 0.75 / 0.90**，夹取到 `[0.25, 0.90]` 后吸附到最近档位 | 小工具面板底色 alpha（卡片与文字不随之变淡）；拿不到合成器时按不透明绘制，但不改配置值 |
| `widget_always_on_top` | 布尔 | true | — | 小工具置顶 |
| `widget_show_trend` | 布尔 | true | — | 小工具是否画折线 |
| `widget_pos` | 数组｜null | null | `[x, y]` 逻辑点 | 小工具位置 |
| `billing_day_command_code` | 整数 | 1 | 1–31 | Command Code 的续费日（其 API 不报周期结束） |
| `window_size` | 数组｜null | null | `[w, h]` | **遗留字段**：上一版的窗口几何，2.0 无人读，只保证往返不丢 |
| `window_pos` | 数组｜null | null | `[x, y]` | 主窗口位置（2.0 尚未使用） |
| `widget_window_size` | 数组｜null | null | `[w, h]`，夹取到 280×240 … 2000×2000 | **小工具自己的尺寸**：用户拖拽后写回。与 `window_size` 分开是因为后者是上一版的遗留、2.0 无人读，不该拿来当小工具的状态 |
| `tray_hint_shown` | 布尔 | false | — | 「仍在托盘运行」提示是否已展示过 |

两条纪律：

- **越界值一律夹取**，不报错（间隔、阈值、保留天数、不透明度、尺寸枚举、计费日都要按上表夹取）。
- **字段集必须一致**：现有实现的 `serde` 会丢弃不认识的字段，所以若一方写入了对方不认识的字段，对方
  一保存就会把你那个字段抹掉。加字段时两边同步加；不要只在一侧加实验字段。

---

## 3. 状态目录、数据库与密钥 🔒

| 文件 | Linux | Windows |
|---|---|---|
| 数据库 | `$XDG_STATE_HOME/dsmon2/dsmon.db`（缺省 `~/.local/state/dsmon2/`） | `%APPDATA%\dsmon2\dsmon.db` |
| 密钥 | 同目录 `.secure_settings.key`（权限 **0600**，32 字节） | 同左 |
| 初始化标记 | 同目录 `.dsmon.db.initialized` | 同左 |
| 日志 | 同目录 `app.log` | 同左 |

数据库（SQLite，WAL + `busy_timeout` 5 秒，即使两个进程同时写也不会 `database is locked`）：

```sql
balance_history(id, platform, timestamp, currency, total, topped, granted, service_status)
subscription_history(id, timestamp, provider, used, cap, window)
secure_settings(key PRIMARY KEY, value BLOB, updated_at)
-- 索引：balance_history(timestamp)、balance_history(currency, timestamp)、
--       subscription_history(provider, timestamp)、
--       subscription_history(provider, window, timestamp)
```

- `timestamp` 一律 `%Y-%m-%d %H:%M:%S`（本地时间，与 1.x 一致）。
- 同一平台 **120 秒**内的重复读数跳过（去重窗口），时间戳相同的写入视为重复。
- `platform` / `provider` 列的值就是 §7.1 的 `key`。
- `window` 是 `5h` / `weekly` / `monthly`：一个套餐有多个窗口，历史要分得开。**没有 `window` 列的老库
  自动补一列**（`ALTER TABLE … ADD COLUMN window TEXT NOT NULL DEFAULT 'monthly'`），已存在的行按定义
  都是月度——那时只记月度。
- **窗口的"池"金额是跨实现的事实**：OpenCode Go 的 5h/weekly/monthly 分别是 **$12 / $30 / $60**。
  端点的周/月只有整数百分比，5h 却是金额；用「本步内花掉的金额 ÷ (池 ÷ 100)」就能把粗百分比细化到
  小数（`history::refined_percent`）。另一个实现要显示同样的数字，就得用同样的池。
- **`DELETE` 不会缩小文件**：只有 `PRAGMA wal_checkpoint(TRUNCATE); VACUUM;`（设置页的手动清理）才回收空间。

密钥与密文格式：

- 密钥文件：32 字节随机数，权限 0600，**只创建一次**；并发首次创建时后到者要等赢家写完再读
  （否则会撞上「文件已存在但内容还没写」）。
- 密文格式：`DSBM1`（5 字节前缀）‖ 12 字节 nonce ‖ 密文 ‖ 16 字节 GCM tag，AES-256-GCM。
- AAD 是固定串 `deepseek-balance-monitor secure_settings api_key v1`——**跨实现必须逐字节一致**，
  否则对方写的密文解不开。
- `secure_settings.key` 的取值 = 平台 `key`（如 `deepseek`、`opencode_go`、`glm_coding_cn`）。
  **API Key 永不写入 `config.json`。**

只读边界：

- **1.x 的目录只读**：Linux `~/.local/state/deepseek-balance-monitor/balance_history.db`、
  Windows `%APPDATA%\DeepSeek Balance Monitor\`。只在用户显式执行「从 1.x 导入」时读一次，**绝不写入**，
  两个版本可同时运行。
- **日志裁剪只有主程序做**：`app.log` 与历史表的裁剪都是「读全文/全表 → 覆盖写」，多个进程同时做会互相
  覆盖。小工具只 append 日志（`O_APPEND` 单行写入）。
- 首启会从「过去共用的那个目录」搬移本版自己的文件（`dsmon.db`、`.secure_settings.key`、
  `.dsmon.db.initialized`，以及靠独有字段认出的 `config.json`）；**目标已存在就跳过**。

---

## 4. 单实例与唤出 ⚙️（名字是契约）

第二次启动要把已有窗口唤出，然后自己退出：

| 对象 | Linux | Windows |
|---|---|---|
| 主程序 `dsmon2` | D-Bus 名 `com.github.wenyinos.deepseek-balance-monitor`，路径 `/app`，接口 `com.github.wenyinos.DeepseekBalanceMonitor`，方法 `Show` | 互斥体 `Local\DeepSeekBalanceMonitor` + 命名事件 `Local\DeepSeekBalanceMonitorShow` |
| 小工具 `dsmon2-widget` | D-Bus 名 `com.github.wenyinos.deepseek-balance-monitor-widget`，路径 `/app`，接口与主程序**同名**，方法 `Show` | 互斥体 `Local\DeepSeekBalanceMonitorWidget` + 命名事件 `Local\DeepSeekBalanceMonitorWidgetShow` |

- **两套名字必须不同**：小工具若占用主程序的名字，会被判为「后来者」直接退出；反过来，主程序也会在
  小工具开着时启动不了。
- Linux 侧用 `RequestName` 的旗标判定「谁先到」，拿不到名字的一方调 `Show` 后退出。
- **接口名两边共用**是刻意的：`#[zbus::interface(name = …)]` 只收编译期常量，而调用方指定的是**服务名**，
  接口名只在单个进程的对象服务器里解析，两边各有一份实现并不冲突。
- 唤醒的语义由收方决定：主程序翻成「显示主窗口」，小工具翻成 `Visible(true)` + `Focus`。
  请求只有一种（`instance::Request::Show`）。

---

## 5. 开机自启 🔒

**两个程序各有一条自启项**，互不干扰：主程序与小工具都可以单独开机启动（小工具在没有主程序时会
显示断开提示并重试）。

| 程序 | Linux | Windows |
|---|---|---|
| 主程序 `dsmon2` | `$XDG_CONFIG_HOME/autostart/deepseek-balance-monitor.desktop`，`Exec=<绝对路径> --minimized` | `Run` 键下值名 `DeepSeek Balance Monitor`，数据是 `"<绝对路径>" --minimized` |
| 小工具 `dsmon2-widget` | `$XDG_CONFIG_HOME/autostart/deepseek-balance-monitor-widget.desktop`，`Exec=<绝对路径>`（**无参数**） | `Run` 键下值名 `DeepSeek Balance Monitor Widget`，数据是 `"<绝对路径>"` |

- Linux 的桌面项文件要 **0755**（有些会话只启动可执行的自启项）。
- 对应的配置字段：主程序 `auto_start`、小工具 `widget_auto_start`（默认都为 true）。
- 该设置**每次启动都对账**（按配置写入或移除），不是只在设置页点一下时写——这样换了可执行文件位置、
  或从别的版本继承了设置，都能自愈。小工具被关闭（它自己的 ✕）时**连自启项一起去掉**：关闭就是
  「不再需要」，留下条目会在下次登录又把它带回来。
- `--minimized` 的语义见 §6：启动后**不进窗口**，但要等托盘图标真的注册成功再隐藏；托盘不在就不藏
  （否则会出现「程序在跑、屏幕上一个东西都没有」）。小工具没有窗口要收起来，所以不带参数，按上次
  的位置与大小出现。

---

## 6. 命令行与可执行文件 🔒

| 项 | 值 |
|---|---|
| 主程序 | `dsmon2`（Windows `dsmon2.exe`） |
| 小工具 | `dsmon2-widget`（Windows `dsmon2-widget.exe`） |
| 参数 | `--minimized`：启动后进入托盘、不显示窗口（自启用） |
| 参数 | **没有别的参数**。想换数据来源就换掉监听方（Python 版也监听 `127.0.0.1:18964`），不靠命令行指路 |

**刻意不与 1.x 重名**：1.x 装的是 `dsmon` 与 `deepseek-balance-monitor.exe`，本版必须能与它们并存。

---

## 7. 平台目录与客户端

### 7.1 平台条目 🔒

`catalog::PLATFORMS` 里每条：`key`（稳定标识）、`display_name`（专有名词，不翻译）、`mode`
（`payg` / `package`）、`windows`（package 才有：`["5h","weekly","monthly"]` 等）、`console_url`、
`implemented`（客户端是否已实现）。

`key` 有三重身份，三处必须是同一个字符串：配置里的平台标识、`secure_settings` 的键、历史表的
`platform` / `provider` 列。

**加一个平台的成本**：一条 `PlatformMeta` + 一个客户端函数 + `monitor::fetch_package` 一行。

### 7.2 窗口键与 i18n 键 🔒

窗口名到 i18n 键的映射由 `catalog::window_label_key` 给出：`5h` → `window_5h`、`weekly` →
`window_weekly`、`monthly` → `window_monthly`。数据接口只传键，文案由客户端查表。

### 7.3 客户端形态与币种 ⚙️（返回结构是契约）

| 形态 | 签名 |
|---|---|
| 余额型 | `fetch_balance(platform, api_key, proxy) -> Result<Balances, String>`，`Balances` = 币种 → `{total_balance, granted_balance, topped_up_balance}` |
| 额度过 | `fetch_quota(api_key, proxy) -> Result<PackageQuota, String>`，`PackageQuota` = 窗口名 → `{usage_percent, percent_remaining, reset_in_sec, used?, cap?}` |
| 服务状态 | `fetch(proxy) -> String`（指示值见 §7.4） |

- 错误一律是**给人看的字符串**（`sanitize_message` 会去掉可能混进来的密钥等敏感片段）。
- 额度百分比统一以 **`usage_percent` 为主**、`percent_remaining` 派生，两者都夹取到 `[0, 100]`；
  以金额计量的窗口（Command Code 月度）另存 `used` / `cap`。
- 默认币种（`catalog::default_currency`）：`kimi_token_cn`、`stepfun_token_cn` → `CNY`；
  `kimi_token_global`、`stepfun_token_global`、`openrouter` → `USD`；其余 → `CNY`。
  实际余额以 API 返回的币种为准，这个只用于缺省展示与导出。

### 7.4 服务状态指示值 🔒

`none` / `minor` / `major` / `critical` / `maintenance`，外加未知时的 `unknown`（**不得借用其他平台的
状态**）。各家状态页的原始字符串按下面的规则归一到这五个值：

| 原始 | 归一 |
|---|---|
| `degraded`、`degraded_performance` | `minor` |
| `partial_outage` | `major` |
| `full_outage`、`major_outage` | `critical` |
| `under_maintenance` | `maintenance` |

---

## 8. 告警与通知（行为契约）

| 项 | 规则 |
|---|---|
| 低余额告警 | 首选币种余额 `< threshold_yuan` 时触发；`alert_mode`：`once` 每次跌破只报一次、`always` 每次轮询都报、`never` 不报 |
| 服务异常告警 | `api_alert_enabled` 为真且服务状态非 `none` 时触发 |
| Linux 通道 | `org.freedesktop.Notifications`（zbus 直连；没有通知守护就静默） |
| Windows 通道 | 托盘气泡（`Shell_NotifyIconW` + `NIF_INFO`） |
| 谁发通知 | **只有主程序发**。小工具与任何只读客户端都不发，否则同一件事会响两次 |

托盘、通知库、窗口实现本身都属 ⚙️：换个库不影响另一方。

---

## 9. 本清单之外（各自实现自由）

界面布局与配色、图表库、托盘库、字体、打包格式（deb/rpm/MSI）、窗口行为细节（置顶/隐藏的实现方式）、
服务端的并发与线程模型。这些改了不影响另一个实现，也不影响小工具。
