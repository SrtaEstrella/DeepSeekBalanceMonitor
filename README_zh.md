# DeepSeek 余额监控

一个 Windows 系统托盘应用和 Linux 命令行 / Plasma 小组件，定时查询 DeepSeek API 账户余额，并在余额过低时提醒。

[English](README.md)

![preview](assets/preview_zh.png)

![Rainmeter 小组件预览](assets/preview_rainmeter_zh.png)

Rainmeter 小组件预览图

[Linux Plasma 小组件预览](assets/preview_linux.png)（仅 KDE Plasma 6）

[Mac WebView 截图](assets/webview%20screenshots/) — 菜单栏、设置界面、历史图表、浅色主题

---

## 当前版本亮点

- 已改用 FlashDuty 后台的 DeepSeek 状态页，替代失效的 `status.deepseek.com/api/v2` 旧接口。
- 自定义图标样式：5 套预置配色、自定义 hex 颜色和图标描边开关。
- 历史记录页：分页余额记录、交互式趋势图和消耗速率分析。
- CSV 导出支持配置保存路径。
- 余额通知和历史页显示忙时消耗速率（过滤闲时/平直段）与预计可用时间。
- 支持 HTTP 代理。
- 余额详情通知使用 emoji 前缀和相对上次查询时间。
- Demo 模式无需真实 Key 即可测试：Py-Win/Py-Mac 提供开发者面板，Rust 通过保存 `demo` 作为 API Key 触发。
- API Key 加密存储：Py-Win 使用 Fernet + SQLite，Rust 使用 SQLite `secure_settings`，Py-Mac 使用 Keychain。
- Rainmeter 桌面小工具：仅本地可访问的状态接口；`.rmskin` 发布打包。Rust/Python Windows 双版均已支持。
- Rainmeter `/widget-status` 现包含 OpenCode Go 额度字段（`og_*`），后台每 10 分钟刷新；接口约定与 Python 版实施建议见 `rainmeter-widget/PYTHON_RAINMETER_INTEGRATION.md`。
- OpenCode Go 额度显示（Rust 版）：改用官方 OpenCode Go API（`opencode.ai/zen/go/v1/usage`，Bearer API Key 认证），展示 5 小时滚动 / 每周 / 每月三档用量；凭据加密存于 SQLite，绝不写入 config.json。
- Command Code 额度显示（Rust 版）：调用 `api.commandcode.ai` 计费接口（Bearer API Key 认证），展示 5 小时 / 每周 / 每月三档用量；月度窗口按档位推算——由 5h/周滚动窗口上限（cap）对照官方档位表自动识别（Go 10 / GOAT 70 / Pro 80 / Max 10× 150 / Max 20× 300 / Team Pro 40 credits）；Windows 设置窗口与 Plasma 小组件各新增「订阅」页，并排展示 OpenCode Go 与 Command Code 额度，全部 API Key 在「账户」页输入。Linux CLI：`dsmon command-code` / `dsmon command-code set-key` / `dsmon command-code json`。
- Rust 双端统一 TLS 栈（rustls + 内嵌 webpki-roots）：不依赖系统证书库，Windows 版在 Windows 7/8.1 上开箱即用并支持 TLS 1.3。

Rust Linux 版本限定：
- Rust Linux：`dsmon set-key` 和 `dsmon set <field> <value>`；daemon 每轮轮询重新读取配置；CLI 固定英文输出。
- `dsmon opencode-go` 输出 OpenCode Go 额度；`dsmon opencode-go set-key <api_key>` 加密保存 API Key；`dsmon opencode-go json` 输出机器可读 JSON。
- `dsmon command-code` 输出 Command Code 额度；`dsmon command-code set-key <api_key>` 加密保存 API Key；`dsmon command-code json` 输出机器可读 JSON。
- Plasma 6 小组件设置页按用途拆分：「账户」页集中管理全部 API Key（DeepSeek、OpenCode Go、Command Code）；新增「订阅」页并排展示 OpenCode Go 与 Command Code 额度进度条；「常规」页按「查询 / 通用 / 代理 / 图标外观」分组。
- Plasma 6 小组件主视图：DeepSeek 余额以大数字展示，配合上次查询、API 服务状态与预计可用的四行布局；OpenCode 与 Command Code 区各展示三档用量进度条（5h/每周/每月），右上角按钮一键同时刷新。
- 刷新 Linux Plasma 小组件显示模型：余额、相对上次查询、API 服务状态和预计可用时间现在与 Rainmeter 小工具布局一致。
- Plasma 小组件语言修改现在会同步 `cfg_language` 到 `dsmon` 的 `ui_language`，重启 Plasma 后仍能保持中英文选择。
- Linux 发布现在同时提供完整 `.tar.gz` 包和可直接下载的独立 `.plasmoid` 小组件包。


## 功能

- **托盘图标显示余额** — 余额以数字形式显示在任务栏圆角图标上。青色（正常）、红色（低余额）、暖灰色（API 服务异常）、灰色（无数据）。5 套可切换配色 + 自定义 hex 颜色
- **低余额通知** — 三种模式：不提醒、持续提醒、仅提醒一次（默认）。图标仍会变红
- **余额详情** — 左键单击图标查看余额（emoji 前缀）、消耗速率、API 服务状态和相对时间
- **历史记录页** — 分页表格展示所有余额记录，附带折线图和消耗分析，支持 CSV 导出
- **设置** — API Key（Fernet + SQLite加密存储）、查询间隔、预警阈值、提醒模式、图标主题、代理等
- **OpenCode Go 与 Command Code 额度**（Rust 版）— Windows 设置「订阅」页或 Linux `dsmon opencode-go` / `dsmon command-code` 展示 opencode.ai 与 commandcode.ai 仪表板的 5h/每周/每月用量，凭据加密存储
- **Demo 模式** — `--demo` 免 Key 体验，开发者面板可调参数
- **可选桌面小工具** — Linux 支持 KDE Plasma 6，Windows 支持 Rainmeter（Rust/Python 双版均已适配）
- **社区移植** — Rust-Win（Win7+）、Rust-Linux（CLI + Plasma 6 小组件）、Py-Mac（Keychain 加密，WebView 设置界面）

### 通知预览

**查看余额：**

> DeepSeek 余额：  
> 💰 12.34 CNY（充值 10.00，赠送 2.34）  
> 📊 忙时消耗 0.06/小时  |  预计可用 28 天 4 小时  
> 📡 DeepSeek API 服务状态：🟢 服务正常  
> 🕐 上次查询：5 分钟前

**低余额告警：**

> ⚠ DeepSeek 余额不足  
> 当前余额仅剩 0.50，已低于您设置的提醒阈值 1.00。  
> 请及时充值！

## 开始使用

### 直接下载

从 [Releases](https://github.com/wenyinos/DeepSeekBalanceMonitor/releases) 下载最新文件。Python 打包版使用 `DeepSeekBalanceMonitor.exe`，Rust Windows 版使用 `deepseek-balance-monitor-*-windows-*.exe`，Linux 完整包使用 `deepseek-balance-monitor-*-linux-x86_64.tar.gz`，独立 Plasma 小组件使用 `deepseek-balance-monitor-*-plasmoid.plasmoid`。发布版无需 Python 环境。

### 可选 Plasma 小组件（Linux）

Plasma 小组件是可选功能，需要 KDE Plasma 6。它从本机 `dsmon` 读取状态，不会直接接收 API Key。

1. 从 [Releases](https://github.com/wenyinos/DeepSeekBalanceMonitor/releases) 下载 `deepseek-balance-monitor-*-linux-x86_64.tar.gz`。
2. 解压并运行安装脚本：

   ```bash
   tar -xzf deepseek-balance-monitor-*-linux-x86_64.tar.gz
   cd deepseek-balance-monitor-*-linux-x86_64
   sudo ./install.sh
   ```

   安装脚本会自动启用并启动守护进程（`systemctl --user enable --now dsmon.service`）。

3. 在 Plasma 小组件选择器中添加 **DeepSeek Balance Monitor**。
4. 打开小组件设置，输入 DeepSeek API Key，或使用 `dsmon set-key` 设置，然后点击 **保存**。
5. 在小组件中点击 **查询** 可手动刷新余额。

如果只需要小组件，可下载 `deepseek-balance-monitor-*-plasmoid.plasmoid` 并用 Plasma 小组件安装器安装。完整 Linux tar 包中也包含同一个小组件，路径为 `plasmoid/`。

### 可选 Rainmeter 小工具（Windows）

Rainmeter 桌面小工具是可选功能。它通过本地地址 `127.0.0.1:17654` 从运行中的主进程获取状态，不保存也不接收 API Key。Rust 和 Python Windows 版均已支持。`/widget-status` 响应包含 DeepSeek 余额、服务状态、消耗速率，以及（Rust Windows 版）OpenCode Go 额度字段（`og_configured`、`og_error`、`og_rolling|weekly|monthly_percent`/`_line`），后台每 10 分钟自动刷新。

1. 从 [rainmeter.net](https://www.rainmeter.net/) 下载并安装 Rainmeter。
2. 运行任意 Windows 版本（Python 或 Rust）——本地状态接口会自动启动。
3. 从 [Releases](https://github.com/wenyinos/DeepSeekBalanceMonitor/releases) 下载 `deepseek-balance-monitor-*-rainmeter.rmskin`。
4. 双击 `.rmskin` 安装皮肤。
5. 在 Rainmeter 中加载 `DeepSeekBalanceMonitor\DeepSeekBalanceMonitor.ini`（英文版用 `DeepSeekBalanceMonitor.en.ini`）。

**高分屏：** 先对 `Rainmeter.exe` 右键 → 属性 → 兼容性 → 更改高 DPI 设置 → 勾选"替代高 DPI 缩放行为"并选"应用程序"。然后加载 2x 缩放版 `DeepSeekBalanceMonitor.hd.ini`（或 `.en.hd.ini`）。

### 运行要求

直接下载（`.exe`、`.tar.gz`、`.dmg`）无需额外运行环境。

- Py-Win：Windows 10+
- Rust-Win：安装所有官方更新的 Windows 7 SP1+、8.1、10 或 11
- Rust-Linux：RHEL 8 / Ubuntu 20.04 同时代或更新 glibc；可选小组件需 KDE Plasma 6.0+
- Py-Mac：MacOS 10.14+

从源码构建需额外安装 Python 3.10+（Py-Win、Py-Mac）或 Rust 1.77.2（Rust-Win、Rust-Linux）。

### TLS 证书说明

两个 Rust 版本均使用 rustls + webpki-roots：Mozilla 根证书库内嵌于二进制，不依赖操作系统证书库。Windows 版在根证书陈旧的 Windows 7/8.1 上可开箱即用（并支持 TLS 1.3），原 `scripts\update_windows_root_certs.bat` 辅助脚本已随之移除——Python 版仅支持 Windows 10+，本就无需该脚本。

请注意：由于程序只信任内嵌根证书，企业代理或安全软件进行 HTTPS 检查时将无法通过证书校验。

### 源码运行（Python）

需要 Python 3.10+。

```bash
pip install -r requirements.txt
python main.py
```

### 从源码构建

**Python（PyInstaller）：**

```bash
pip install pyinstaller
scripts\build_exe.bat
```

构建为 `dist\DeepSeekBalanceMonitor.exe`。GitHub Actions 会在每次 Release 时自动构建并上传 EXE。

**Rust Windows（`rust-windows/`）：**

```powershell
cd rust-windows
rustup toolchain install 1.77.2-x86_64-pc-windows-msvc
cargo +1.77.2 build --release --target x86_64-pc-windows-msvc --locked
```

**Rust Linux（`rust-linux/`）：**

```bash
cd rust-linux
cargo +1.77.2 build --release --locked
```

Linux 发布包会用 sudo 将 `dsmon` 二进制与 systemd 用户服务安装到系统级（`/usr/local/bin/dsmon`、`/etc/systemd/user/dsmon.service`），并把 Plasma 小组件及其图标安装到用户目录（`~/.local/share/`），后续更新小组件无需 sudo：

```bash
tar -xzf deepseek-balance-monitor-*-linux-x86_64.tar.gz
cd deepseek-balance-monitor-*-linux-x86_64
sudo ./install.sh
```

systemd 发行版下安装脚本会对 sudo 用户自动执行 `systemctl --user enable --now dsmon.service`，守护进程登录自启动并立即运行；非 systemd 发行版则改为写入桌面自启动项。

CLI 目前仅 Rust Linux 版提供。Windows 和 MacOS 版使用图形界面 / 托盘操作。

常用 Linux CLI 操作：

| 命令 | 作用 |
|---|---|
| `dsmon init-config` | 在配置文件不存在时创建默认配置 |
| `dsmon set-key` | 从标准输入读取 API Key，并加密保存到 SQLite；输入 `demo` 可进入演示模式 |
| `dsmon set <field> <value>` | 修改单个配置项，例如 `interval`、`threshold`、`ui-language`、`http-proxy`、`theme`、`color-ok` |
| `dsmon check` | 立即查询一次余额，并以英文输出结果 |
| `dsmon daemon` | 运行 systemd 用户服务使用的轮询循环 |
| `dsmon history [days]` | 输出余额历史统计摘要 |
| `dsmon history export [days] [currency\|all] [path\|-]` | 导出历史 CSV；`-` 表示输出到 stdout |
| `dsmon widget-status` | 输出 Plasma 小组件读取的 JSON 状态 |
| `dsmon opencode-go` | 输出 OpenCode Go 额度（5h/每周/每月用量）；API Key 用 `dsmon opencode-go set-key <api_key>` 保存（或经 stdin 管道输入；Key 在 https://opencode.ai/auth 获取） |
| `dsmon command-code` | 输出 Command Code 额度（5h/每周/每月用量）；API Key 用 `dsmon command-code set-key <api_key>` 保存（或经 stdin 管道输入；Key 在 https://commandcode.ai 获取） |

**MacOS（`src/mac/`）：**

```bash
cd src/mac
pip install -r requirements.txt
bash ../scripts/build_mac.sh
```

### Python 版与 Rust 版对比

| | Python Windows 版 | Rust Windows 版 | Rust Linux 版 | Python MacOS 版 |
|---|---|---|---|---|
| 运行时 | Python + pystray + Tkinter | 原生 Rust + native-windows-gui | 原生 Rust 命令行 | Python + rumps + webview |
| 最低系统 | Windows 10+ | Windows 7 SP1+ | RHEL 8 / Ubuntu 20.04 同时代 glibc | MacOS 10.14+ |
| 首次无 Key | 弹出设置窗口 | 弹出设置窗口 | 安装 / 检查时提示运行 `dsmon set-key` | 弹出设置窗口 |
| 开机自启 | 注册表 Run 键 | 启动文件夹快捷方式 | systemd 用户服务 | 登录项 |
| API Key 存储 | Fernet + SQLite | SQLite `secure_settings`，使用 Windows DPAPI 加密 | SQLite `secure_settings`，本地加密 | MacOS Keychain |

## 项目结构

```
DeepSeekBalance/
├── src/                       # 应用主包
│   ├── config.py
│   ├── api_client.py
│   ├── icon_renderer.py
│   ├── app_state.py
│   ├── settings_dialog.py
│   ├── tray_app.py
│   ├── credential_store.py
│   ├── secure_settings.py
│   ├── storage.py
│   └── rainmeter_server.py
├── src/mac/                    # 原生 MacOS 移植
│   ├── main.py
│   ├── settings.py
│   └── keystore.py
├── scripts/                    # 构建与工具脚本
│   ├── build_exe.bat
│   ├── build_mac.sh
│   ├── setup.bat
│   ├── run_silent.vbs
│   └── demo.vbs
├── assets/                     # 图标、预览图、字体
│   ├── app.ico
│   ├── AppIcon.icns / .png
│   ├── preview.png / preview_zh.png
│   └── font/
├── rainmeter-widget/           # Rainmeter 桌面皮肤源文件
├── rust-windows/              # 原生 Rust Windows 版
│   ├── src/main.rs
│   ├── app.manifest
│   └── build.rs
├── rust-linux/                # Rust Linux 命令行与 Plasma 6 小组件
│   ├── src/main.rs
│   ├── package/
│   └── plasmoid/
├── main.py
├── requirements.txt
└── README.md
```

## 配置

Windows 配置文件路径：`%APPDATA%\DeepSeek Balance Monitor\config.json`

```json
{
  "interval_minutes": 10,
  "threshold_yuan": 1.0,
  "language": "zh",
  "alert_mode": "once",
  "api_alert_enabled": true,
  "retention_days": 30,
  "theme": "default",
  "icon_stroke": false,
  "http_proxy": "",
  "auto_start": false
}
```

API Key 不写入此文件。Python Windows 使用 Fernet + SQLite 加密，Python MacOS 使用 Keychain，Rust Windows / Linux 将 Key 加密存入 SQLite `secure_settings`。

Linux `dsmon` 配置路径：`~/.config/deepseek-balance-monitor/config.json`，日志路径：`~/.local/state/deepseek-balance-monitor/app.log`。

Windows 日志路径：`%APPDATA%\DeepSeek Balance Monitor\app.log`

Rust Windows 和 Rust Linux 会在各自应用数据目录保存加密设置和 `balance_history.db`。历史记录使用与日志清理相同的 `retention_days` 保留天数。Windows 设置窗口和 Plasma 小组件设置页提供“历史”选项卡，支持天数 / 币种筛选、趋势统计、图表和 CSV 导出。Linux CLI 固定英文输出，`dsmon history` 显示文字统计，不直接展示原始行。

## 托盘菜单

| 操作 | 方式 |
|---|---|
| 查看余额 | 左键单击图标，或右键 → 查看余额 |
| 立即查询 | 右键 → 立即查询 |
| 充值 | 右键 → 充值 |
| 历史记录 | 右键 → 历史记录 |
| 设置 | 右键 → 设置 |
| 退出 | 右键 → 退出 |

## 图标颜色

| 颜色 | 含义 |
|---|---|
| 青色 | 余额高于预警阈值 |
| 红色 | 余额低于阈值，或 API 查询出错 |
| 暖灰 | API 服务异常（余额数据可能已过时） |
| 灰色 | 尚未完成首次查询，或未配置 Key |

配色支持 5 套预设或自定义 hex 值，在设置中切换。

## 更新日志

[CHANGELOG_zh.md](CHANGELOG_zh.md)

## 协议

MIT
