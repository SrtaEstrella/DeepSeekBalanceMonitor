# DeepSeek Balance Monitor / DeepSeek 余额监控

A Windows system tray application that periodically queries the DeepSeek API for account balance, displays it as a dynamic tray icon, and alerts on low balance.

一个 Windows 系统托盘应用，定时查询 DeepSeek API 账户余额，以动态图标形式显示在任务栏，余额过低时弹窗提醒。

![preview](preview.png)

---

## English

### Features

- **Tray icon with balance** — Balance shown as a number on a coloured rounded rectangle. Teal (OK), red (low balance), warm gray (API service degraded), gray (no data yet).
- **Low balance notification** — Three modes: never, always, or once per drop (default). The icon turns red regardless.
- **Balance details** — Left-click the icon to see balance, API service status, and last check time.
- **Settings** — API key, check interval, alert threshold, alert mode, API status alerts, language, and auto-start on boot.
- **Rust Windows build** — Community-contributed native Rust build (`rust-windows/`). Smaller binary, Win7/Win8.1 support, bundled DeepSeek icon, startup-folder auto-start.

#### Notification Previews

**Normal balance view:**

> DeepSeek Balance:
> 12.34 CNY (Topped 10.00, Granted 2.34)
> Last Check: 2026-05-08 14:30:00
> DeepSeek API Status: 🟢 All Systems Operational

**Low balance alert:**

> ⚠ DeepSeek Low Balance
> 
> Balance is only 0.50, below your alert threshold of 1.00.
> Please top up!

### Direct Download

Grab the latest executable from [Releases](https://github.com/wenyinos/DeepSeekBalanceMonitor/releases). Use `DeepSeekBalanceMonitor.exe` for the Python-packaged build or `deepseek-balance-monitor.exe` for the Rust Windows build. No Python is required for release executables.

### Requirements

- Python build: Windows 10 or later, Python 3.10+
- Rust build: Windows 7 SP1 / Server 2008 R2 SP1 with all official updates, Windows 8.1 / Server 2012 R2, Windows 10, or Windows 11

### Run from Source

Requires Python 3.10+.

```bash
pip install -r requirements.txt
python main.py
```

On first launch the settings window opens automatically — enter your DeepSeek API key. The app lives in the system tray; left-click the icon to view balance, right-click for the menu.

### Building the EXE

Requires Python 3.10+ and PyInstaller.

```bash
pip install pyinstaller
scripts\build_exe.bat
```

Builds `dist\DeepSeekBalanceMonitor.exe` as a single-file executable.

### Rust Windows Build

The Rust port lives in `rust-windows/` and shares the same config and log files as the Python version. It is built with Rust `1.77.2` to keep the Windows 7/8.1 target viable.

```powershell
cd rust-windows
rustup toolchain install 1.77.2-x86_64-pc-windows-msvc
cargo +1.77.2 build --release --target x86_64-pc-windows-msvc --locked
```

GitHub Actions publishes the release executable as `deepseek-balance-monitor.exe` on `v0.1.1`.

### Python vs Rust Build

| Area | Python build | Rust Windows build |
|---|---|---|
| Runtime | Python + pystray + Tkinter | Native Rust + native-windows-gui |
| Packaging | PyInstaller single exe | Cargo release exe via GitHub Actions |
| Minimum target | Windows 10+ documented | Win7 SP1 / Win8.1+ target, real Windows test passed |
| First launch without key | Opens settings dialog | Creates/opens `config.json` and shows a local-storage notice |
| Auto-start | Registry Run key | Current-user Startup folder `.lnk`, no admin rights |
| Icon | Generated `app_icon.ico`; dynamic tray balance icon | Bundled DeepSeek exe icon; dynamic tray balance icon |
| Config path | `%APPDATA%\DeepSeek Balance Monitor\config.json` | Same path, compatible schema |

### Project Structure

```
DeepSeekBalance/
├── src/                       # Application package
│   ├── config.py
│   ├── api_client.py
│   ├── icon_renderer.py
│   ├── app_state.py
│   ├── settings_dialog.py
│   └── tray_app.py
├── scripts/                   # Build & utility scripts
│   ├── generate_icon.py
│   ├── build_exe.bat
│   ├── setup.bat
│   └── run_silent.vbs
├── rust-windows/              # Native Rust Windows port
│   ├── src/main.rs
│   ├── app.ico
│   ├── app.manifest
│   └── build.rs
├── main.py
├── requirements.txt
└── README.md
```

### Configuration

Settings are stored in `%APPDATA%\DeepSeek Balance Monitor\config.json`:

```json
{
  "api_key": "sk-xxxxxxxx",
  "interval_minutes": 10,
  "threshold_yuan": 1.0,
  "language": "zh",
  "auto_start": false,
  "alert_mode": "always"
}
```

Logs are written to `%APPDATA%\DeepSeek Balance Monitor\app.log`. The Rust build defaults `auto_start` to `true`; the original Python default is `false`. In the Rust build, auto-start creates or removes a shortcut at `%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\DeepSeek Balance Monitor.lnk`.

### Tray Menu

| Action | Trigger |
|---|---|
| View Balance | Left-click the icon, or Right-click → View Balance |
| Check Now | Right-click → Check Now |
| Top Up | Right-click → Top Up |
| Settings | Right-click → Settings |
| Quit | Right-click → Quit |

### Icon Colours

| Colour | Meaning |
|---|---|
| Teal | Balance is above the alert threshold |
| Red | Balance is below threshold, or an API error occurred |
| Warm gray | API service is degraded (balance data may be stale) |
| Gray | First check not yet completed, or no API key configured |

### License

MIT

---

## 中文

### 功能

- **托盘图标显示余额** — 余额以数字形式显示在任务栏圆角图标上。青色（正常）、红色（低余额）、暖灰色（API 服务异常）、灰色（无数据）。
- **低余额通知** — 三种模式：不提醒、持续提醒、仅提醒一次（默认）。图标仍会变红。
- **余额详情** — 左键单击图标查看余额明细、API 服务状态和上次查询时间。
- **设置** — API Key、查询间隔、预警阈值、提醒模式、API 状态提醒、语言、开机自启。
- **Rust Windows 版** — 社区贡献的原生 Rust 构建（`rust-windows/`）。体积更小，支持 Win7/Win8.1，自带 DeepSeek 图标。

#### 通知预览

**查看余额：**

> DeepSeek 余额：
> 12.34 CNY（充值 10.00，赠送 2.34）
> 上次查询: 2026-05-08 14:30:00
> DeepSeek API 服务状态：🟢 服务正常

**低余额告警：**

> ⚠ DeepSeek 余额不足
> 
> 当前余额仅剩 0.50，已低于您设置的提醒阈值 1.00。
> 请及时充值！

### 直接下载

从 [Releases](https://github.com/wenyinos/DeepSeekBalanceMonitor/releases) 下载最新可执行文件。Python 打包版使用 `DeepSeekBalanceMonitor.exe`，Rust Windows 版使用 `deepseek-balance-monitor.exe`；发布版无需 Python 环境。

### 运行要求

- Python 版：Windows 10 及以上，Python 3.10+
- Rust 版：安装所有官方更新的 Windows 7 SP1 / Server 2008 R2 SP1、Windows 8.1 / Server 2012 R2、Windows 10 或 Windows 11

### 源码运行

需要 Python 3.10+。

```bash
pip install -r requirements.txt
python main.py
```

首次运行会自动弹出设置窗口，输入 DeepSeek API Key。应用常驻系统托盘，左键单击图标查看余额，右键打开菜单。

### 构建 EXE

需要 Python 3.10+ 和 PyInstaller。

```bash
pip install pyinstaller
scripts\build_exe.bat
```

构建为单文件 `dist\DeepSeekBalanceMonitor.exe`。

### Rust Windows 构建

Rust 版本位于 `rust-windows/`，与 Python 版共用配置和日志文件。工具链锁定 Rust `1.77.2`，用于保留 Windows 7/8.1 目标兼容性。

```powershell
cd rust-windows
rustup toolchain install 1.77.2-x86_64-pc-windows-msvc
cargo +1.77.2 build --release --target x86_64-pc-windows-msvc --locked
```

GitHub Actions 会在 `v0.1.1` 发布页上传 `deepseek-balance-monitor.exe`。

### Python 版与 Rust 版对比

| 项目 | Python 版 | Rust Windows 版 |
|---|---|---|
| 运行时 | Python + pystray + Tkinter | 原生 Rust + native-windows-gui |
| 打包 | PyInstaller 单文件 exe | Cargo release exe，由 GitHub Actions 构建 |
| 最低目标 | 文档标注 Windows 10+ | 目标支持 Win7 SP1 / Win8.1+，Windows 实机测试通过 |
| 首次无 Key | 弹出设置窗口 | 创建/打开 `config.json`，并提示信息仅保存在本机 |
| 开机自启 | 注册表 Run 键 | 当前用户启动文件夹 `.lnk`，无需管理员权限 |
| 图标 | 生成 `app_icon.ico`；托盘图标动态显示余额 | 内置 DeepSeek exe 图标；托盘图标动态显示余额 |
| 配置路径 | `%APPDATA%\DeepSeek Balance Monitor\config.json` | 相同路径，配置格式兼容 |

### 项目结构

```
DeepSeekBalance/
├── src/                       # 应用主包
│   ├── config.py
│   ├── api_client.py
│   ├── icon_renderer.py
│   ├── app_state.py
│   ├── settings_dialog.py
│   └── tray_app.py
├── scripts/                   # 构建与工具脚本
│   ├── generate_icon.py
│   ├── build_exe.bat
│   ├── setup.bat
│   └── run_silent.vbs
├── rust-windows/              # 原生 Rust Windows 版
│   ├── src/main.rs
│   ├── app.ico
│   ├── app.manifest
│   └── build.rs
├── main.py
├── requirements.txt
└── README.md
```

### 配置

配置文件路径：`%APPDATA%\DeepSeek Balance Monitor\config.json`

```json
{
  "api_key": "sk-xxxxxxxx",
  "interval_minutes": 10,
  "threshold_yuan": 1.0,
  "language": "zh",
  "auto_start": false,
  "alert_mode": "always"
}
```

日志路径：`%APPDATA%\DeepSeek Balance Monitor\app.log`。Rust 版 `auto_start` 默认值为 `true`；原 Python 版默认值为 `false`。Rust 版自启动会创建或删除 `%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\DeepSeek Balance Monitor.lnk`。

### 托盘菜单

| 操作 | 方式 |
|---|---|
| 查看余额 | 左键单击图标，或右键 → 查看余额 |
| 立即查询 | 右键 → 立即查询 |
| 充值 | 右键 → 充值 |
| 设置 | 右键 → 设置 |
| 退出 | 右键 → 退出 |

### 图标颜色

| 颜色 | 含义 |
|---|---|
| 青色 | 余额高于预警阈值 |
| 红色 | 余额低于阈值，或 API 查询出错 |
| 暖灰 | API 服务异常（余额数据可能已过时） |
| 灰色 | 尚未完成首次查询，或未配置 Key |

### 协议

MIT
