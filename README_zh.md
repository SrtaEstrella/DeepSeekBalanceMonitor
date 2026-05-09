# DeepSeek 余额监控

一个 Windows 系统托盘应用，定时查询 DeepSeek API 账户余额，以动态图标形式显示在任务栏，余额过低时弹窗提醒。

[English](README.md)

![preview](preview_zh.png)

---

## 功能

- **托盘图标显示余额** — 余额以数字形式显示在任务栏圆角图标上。青色（正常）、红色（低余额）、暖灰色（API 服务异常）、灰色（无数据）。
- **低余额通知** — 三种模式：不提醒、持续提醒、仅提醒一次（默认）。图标仍会变红。
- **余额详情** — 左键单击图标查看余额明细、API 服务状态和上次查询时间。
- **设置** — API Key、查询间隔、预警阈值、提醒模式、API 状态提醒、语言、开机自启。
- **Rust Windows 版** — 社区贡献的原生 Rust 构建（`rust-windows/`）。体积更小，支持 Win7/Win8.1，自带 DeepSeek 图标。

### 通知预览

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

## 开始使用

### 直接下载

从 [Releases](https://github.com/SrtaEstrella/DeepSeekBalanceMonitor/releases) 下载最新可执行文件。无需 Python 环境，双击即用。首次启动会提示输入 API Key。

### 运行要求

- Python 版：Windows 10+，Python 3.10+
- Rust 版：Windows 7 SP1+、8.1、10 或 11

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

**Rust（`rust-windows/`）：**

```powershell
cd rust-windows
rustup toolchain install 1.77.2-x86_64-pc-windows-msvc
cargo +1.77.2 build --release --target x86_64-pc-windows-msvc --locked
```

### Python 版与 Rust 版对比

| | Python 版 | Rust 版 |
|---|---|---|
| 运行时 | Python + pystray + Tkinter | 原生 Rust |
| 最低系统 | Windows 10+ | Windows 7 SP1+ |
| 首次无 Key | 弹出设置窗口 | 打开 config.json 编辑 |
| 开机自启 | 注册表 Run 键 | 启动文件夹快捷方式 |

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
├── scripts/                   # 构建与工具脚本
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

## 配置

配置文件路径：`%APPDATA%\DeepSeek Balance Monitor\config.json`

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

日志路径：`%APPDATA%\DeepSeek Balance Monitor\app.log`

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

## 协议

MIT
