# DeepSeek 余额监控

一个 Windows 系统托盘应用和 Linux 命令行 / Plasma 小组件，定时查询 DeepSeek API 账户余额，并在余额过低时提醒。

[English](README.md)

![preview](preview_zh.png)

**Linux Plasma 小组件预览**
桌面小组件仅适用于 KDE Plasma 6 桌面环境。

![Linux 预览](preview_linux.png)

---

## 功能

- **托盘图标显示余额** — 余额以数字形式显示在任务栏圆角图标上。青色（正常）、红色（低余额）、暖灰色（API 服务异常）、灰色（无数据）。
- **低余额通知** — 三种模式：不提醒、持续提醒、仅提醒一次（默认）。图标仍会变红。
- **余额详情** — 左键单击图标查看余额明细、API 服务状态和上次查询时间。
- **设置** — API Key、查询间隔、预警阈值、提醒模式、API 状态提醒、语言、开机自启。
- **Rust Windows 版** — 原生 Rust 构建（`rust-windows/`），支持 Win7/Win8.1，使用启动文件夹快捷方式实现开机自启。
- **Rust Linux 版** — `dsmon` 命令行守护进程（`rust-linux/`），支持 systemd 用户服务、日志保留和可选 KDE Plasma 6 小组件。
- **macOS 版** — 社区贡献的 macOS 移植（`src/mac/`）。原生外观，Keychain 加密存储 API Key。

### 通知预览

**查看余额：**

> DeepSeek 余额：  
> 12.34 CNY（充值 10.00，赠送 2.34）  
> 上次查询: 2026-05-08 14:30:00  
> DeepSeek API 服务状态：🟢 服务正常

**低余额告警：**

> ⚠ DeepSeek 余额不足  
> 当前余额仅剩 0.50，已低于您设置的提醒阈值 1.00。  
> 请及时充值！

## 开始使用

### 直接下载

从 [Releases](https://github.com/wenyinos/DeepSeekBalanceMonitor/releases) 下载最新文件。Python 打包版使用 `DeepSeekBalanceMonitor.exe`，Rust Windows 版使用 `deepseek-balance-monitor.exe`，Linux 版使用 `deepseek-balance-monitor-*-linux-x86_64.tar.gz`。发布版无需 Python 环境。

### 运行要求

- Python 版：Windows 10+，Python 3.10+
- Rust Windows 版：安装所有官方更新的 Windows 7 SP1 / Server 2008 R2 SP1、Windows 8.1 / Server 2012 R2、Windows 10 或 Windows 11
- Rust Linux 版：RHEL 8 / Ubuntu 20.04 同时代或更新 glibc；可选小组件需要 KDE Plasma 6.0+
- macOS 版：macOS 10.14+，Python 3.10+

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
tar -xzf deepseek-balance-monitor-1.1-linux-x86_64.tar.gz
cd deepseek-balance-monitor-1.1-linux-x86_64
sudo ./install.sh
```

**macOS（`src/mac/`）：**

```bash
cd src/mac
pip install -r requirements.txt
bash ../scripts/build_mac.sh
```

### Python 版与 Rust 版对比

| | Python Windows 版 | Rust Windows 版 | Rust Linux 版 | Python macOS 版 |
|---|---|---|---|---|
| 运行时 | Python + pystray + Tkinter | 原生 Rust + native-windows-gui | 原生 Rust 命令行 | Python + rumps + tkinter |
| 最低系统 | Windows 10+ | Windows 7 SP1+ | RHEL 8 / Ubuntu 20.04 同时代 glibc | macOS 10.14+ |
| 首次无 Key | 弹出设置窗口 | 打开 `config.json` 编辑 | 输出配置路径并创建配置 | 弹出设置窗口 |
| 开机自启 | 注册表 Run 键 | 启动文件夹快捷方式 | systemd 用户服务 | 登录项 |
| API Key 存储 | config.json | config.json | config.json | macOS Keychain |

## 项目结构

```
DeepSeekBalance/
├── src/                       # 应用主包
│   ├── config.py
│   ├── api_client.py
│   ├── icon_renderer.py
│   ├── app_state.py
│   ├── settings_dialog.py
│   └── tray_app.py
├── src/mac/                    # 原生 MacOS 移植
│   ├── main.py
│   ├── settings.py
│   └── keystore.py
├── scripts/                    # 构建与工具脚本
│   ├── build_exe.bat
│   ├── build_mac.sh
│   ├── setup.bat
│   └── run_silent.vbs
├── rust-windows/              # 原生 Rust Windows 版
│   ├── src/main.rs
│   ├── app.ico
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
  "api_key": "sk-xxxxxxxx",
  "interval_minutes": 10,
  "threshold_yuan": 1.0,
  "language": "zh",
  "auto_start": false,
  "alert_mode": "once",
  "api_alert_enabled": true,
  "retention_days": 30
}
```

Linux `dsmon` 配置路径：`~/.config/deepseek-balance-monitor/config.json`，日志路径：`~/.local/state/deepseek-balance-monitor/app.log`。

Windows 日志路径：`%APPDATA%\DeepSeek Balance Monitor\app.log`

## 托盘菜单

| 操作 | 方式 |
|---|---|
| 查看余额 | 左键单击图标，或右键 → 查看余额 |
| 立即查询 | 右键 → 立即查询 |
| 充值 | 右键 → 充值 |
| 设置 | 右键 → 设置 |
| 退出 | 右键 → 退出 |

## 图标颜色

| 颜色 | 含义 |
|---|---|
| 青色 | 余额高于预警阈值 |
| 红色 | 余额低于阈值，或 API 查询出错 |
| 暖灰 | API 服务异常（余额数据可能已过时） |
| 灰色 | 尚未完成首次查询，或未配置 Key |

## 更新日志

### v1.1

- API 服务状态轮询，独立图标配色与变化提醒
- 低余额提醒三选一：不提醒 / 持续提醒 / 仅提醒一次（默认）
- 充值直达
- 日志与记录可配置自动清理
- GitHub Actions 自动构建
- 社区移植：Rust-Win（Win7+）、Py-Mac
- 通知卡片重构
- 设置输入校验
- 移除第三方 HTTP 依赖

## 协议

MIT
