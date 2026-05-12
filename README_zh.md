# DeepSeek 余额监控

一个 Windows 系统托盘应用和 Linux 命令行 / Plasma 小组件，定时查询 DeepSeek API 账户余额，并在余额过低时提醒。

[English](README.md)

![preview](assets/preview_zh.png)

[Linux Plasma 小组件预览](assets/preview_linux.png)（仅 KDE Plasma 6）

[Mac WebView 截图](assets/webview%20screenshots/) — 菜单栏、设置界面、历史图表、浅色主题

---

## 当前版本亮点

- 自定义图标样式：5 套预置配色、自定义 hex 颜色和图标描边开关。
- 历史记录页：分页余额记录、交互式趋势图和消耗速率分析。
- CSV 导出支持配置保存路径。
- 余额通知和历史页显示消耗速率与预计可用时间。
- 支持 HTTP 代理。
- 余额详情通知使用 emoji 前缀和相对上次查询时间。
- Demo 模式无需真实 Key 即可测试：Py-Win/Py-Mac 提供开发者面板，Rust 通过保存 `demo` 作为 API Key 触发。
- API Key 加密存储：Py-Win 使用 Fernet + SQLite，Rust 使用 SQLite `secure_settings`，Py-Mac 使用 Keychain。
- Rainmeter 桌面小工具：仅本地可访问的状态接口；`.rmskin` 发布打包。Rust/Python Windows 双版均已支持。

Rust Linux 版本限定：
- Rust Linux：`dsmon set-key` 和 `dsmon set <field> <value>`；daemon 每轮轮询重新读取配置；CLI 固定英文输出。
- Plasma 6 小组件：透明液态玻璃桌面样式，余额、上次查询、服务状态、预计可用时间、刷新按钮和 emoji 状态。


## 功能

- **托盘图标显示余额** — 余额以数字形式显示在任务栏圆角图标上。青色（正常）、红色（低余额）、暖灰色（API 服务异常）、灰色（无数据）。5 套可切换配色 + 自定义 hex 颜色
- **低余额通知** — 三种模式：不提醒、持续提醒、仅提醒一次（默认）。图标仍会变红
- **余额详情** — 左键单击图标查看余额（emoji 前缀）、消耗速率、API 服务状态和相对时间
- **历史记录页** — 分页表格展示所有余额记录，附带折线图和消耗分析，支持 CSV 导出
- **设置** — API Key（Fernet + SQLite加密存储）、查询间隔、预警阈值、提醒模式、图标主题、代理等
- **Demo 模式** — `--demo` 免 Key 体验，开发者面板可调参数
- **可选桌面小工具** — Linux 支持 KDE Plasma 6，Windows 支持 Rainmeter（Rust/Python 双版均已适配）
- **社区移植** — Rust-Win（Win7+）、Rust-Linux（CLI + Plasma 6 小组件）、Py-Mac（Keychain 加密，WebView 设置界面）

### 通知预览

**查看余额：**

> DeepSeek 余额：  
> 💰 12.34 CNY（充值 10.00，赠送 2.34）  
> 📊 日均消耗 1.50  |  预计可用 28 天 4 小时  
> 📡 DeepSeek API 服务状态：🟢 服务正常  
> 🕐 上次查询：5 分钟前

**低余额告警：**

> ⚠ DeepSeek 余额不足  
> 当前余额仅剩 0.50，已低于您设置的提醒阈值 1.00。  
> 请及时充值！

## 开始使用

### 直接下载

从 [Releases](https://github.com/wenyinos/DeepSeekBalanceMonitor/releases) 下载最新文件。Python 打包版使用 `DeepSeekBalanceMonitor.exe`，Rust Windows 版使用 `deepseek-balance-monitor.exe`，Linux 版使用 `deepseek-balance-monitor-*-linux-x86_64.tar.gz`。发布版无需 Python 环境。

### 可选 Rainmeter 小工具（Windows）

Rainmeter 桌面小工具是可选功能。它通过本地地址 `127.0.0.1:17654` 从运行中的主进程获取状态，不保存也不接收 API Key。Rust 和 Python Windows 版均已支持。

1. 从 [rainmeter.net](https://www.rainmeter.net/) 下载并安装 Rainmeter。
2. 运行任意 Windows 版本（Python 或 Rust）——本地状态接口会自动启动。
3. 从 [Releases](https://github.com/SrtaEstrella/DeepSeekBalanceMonitor/releases) 下载 `deepseek-balance-monitor-*-rainmeter.rmskin`。
4. 双击 `.rmskin` 安装皮肤。
5. 在 Rainmeter 中加载 `DeepSeekBalanceMonitor\DeepSeekBalanceMonitor.ini`（英文版用 `DeepSeekBalanceMonitor.en.ini`）。

**高分屏：** 先对 `Rainmeter.exe` 右键 → 属性 → 兼容性 → 更改高 DPI 设置 → 勾选"替代高 DPI 缩放行为"并选"应用程序"。然后加载 `DeepSeekBalanceMonitor.hd.ini`（或 `.en.hd.ini`），这是 2x 缩放版。

### 运行要求

直接下载（`.exe`、`.tar.gz`、`.dmg`）无需额外运行环境。

- Py-Win：Windows 10+
- Rust-Win：安装所有官方更新的 Windows 7 SP1+、8.1、10 或 11
- Rust-Linux：RHEL 8 / Ubuntu 20.04 同时代或更新 glibc；可选小组件需 KDE Plasma 6.0+
- Py-Mac：MacOS 10.14+

从源码构建需额外安装 Python 3.10+（Py-Win、Py-Mac）或 Rust 1.77.2（Rust-Win、Rust-Linux）。

### Windows 7/8.1 根证书说明

如果 Windows 7/8.1 无法查询 `status.deepseek.com`，可以右键 `scripts\update_windows_root_certs.bat` 并选择“以管理员身份运行”，通过 Windows Update 更新系统根证书库。该脚本不内置证书，也不会修改程序 TLS 后端。

旧版 Windows 即使更新根证书后，仍可能无法获取 API 服务状态，因为 DeepSeek 状态页和余额接口使用不同的 TLS 端点。常见原因包括缺少 TLS 1.2 或 Windows Update 相关补丁、Schannel 密码套件支持过旧、系统信任设置陈旧、系统时间不正确，或代理 / 安全软件进行 HTTPS 检查。余额查询可能仍然正常。项目将 Windows 7/8.1 上的 API 服务状态查询视为尽力而为，不准备在程序侧增加绕过方案。

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

Linux 发布包会安装 `/usr/local/bin/dsmon`、`/etc/systemd/user/dsmon.service`，并在 Plasma 6 环境中安装可选小组件：

```bash
tar -xzf deepseek-balance-monitor-*-linux-x86_64.tar.gz
cd deepseek-balance-monitor-*-linux-x86_64
sudo ./install.sh
```

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
│   ├── update_windows_root_certs.bat
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
