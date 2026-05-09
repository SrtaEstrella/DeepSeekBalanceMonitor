# DeepSeek Balance Monitor

A Windows system tray application that periodically queries the DeepSeek API for account balance, displays it as a dynamic tray icon, and alerts on low balance.

[中文版](README_zh.md)

![preview](preview.png)

---

## Features

- **Tray icon with balance** — Balance shown as a number on a coloured rounded rectangle. Teal (OK), red (low balance), warm gray (API service degraded), gray (no data yet).
- **Low balance notification** — Three modes: never, always, or once per drop (default). The icon turns red regardless.
- **Balance details** — Left-click the icon to see balance, API service status, and last check time.
- **Settings** — API key, check interval, alert threshold, alert mode, API status alerts, language, and auto-start on boot.
- **Rust Windows build** — Community-contributed native Rust build (`rust-windows/`). Smaller binary, Win7/Win8.1 support, startup-folder auto-start.

### Notification Previews

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

## Getting Started

### Direct Download

Grab the latest executable from [Releases](https://github.com/SrtaEstrella/DeepSeekBalanceMonitor/releases). No Python required — just double-click to run. On first launch you'll be prompted to enter your API key.

### Requirements

- Python build: Windows 10+, Python 3.10+
- Rust build: Windows 7 SP1+, 8.1, 10, or 11

### Run from Source (Python)

Requires Python 3.10+.

```bash
pip install -r requirements.txt
python main.py
```

### Build from Source

**Python (PyInstaller):**

```bash
pip install pyinstaller
scripts\build_exe.bat
```

Builds `dist\DeepSeekBalanceMonitor.exe`. GitHub Actions auto-builds and attaches the EXE to each release.

**Rust (`rust-windows/`):**

```powershell
cd rust-windows
rustup toolchain install 1.77.2-x86_64-pc-windows-msvc
cargo +1.77.2 build --release --target x86_64-pc-windows-msvc --locked
```

### Python vs Rust

| | Python | Rust |
|---|---|---|
| Runtime | Python + pystray + Tkinter | Native Rust |
| Min OS | Windows 10+ | Windows 7 SP1+ |
| First launch (no key) | Opens settings dialog | Opens `config.json` in editor |
| Auto-start | Registry Run key | Startup folder shortcut |

## Project Structure

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

## Configuration

Settings are stored in `%APPDATA%\DeepSeek Balance Monitor\config.json`:

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

Logs are written to `%APPDATA%\DeepSeek Balance Monitor\app.log`.

## Tray Menu

| Action | Trigger |
|---|---|
| View Balance | Left-click the icon, or Right-click → View Balance |
| Check Now | Right-click → Check Now |
| Top Up | Right-click → Top Up |
| Settings | Right-click → Settings |
| Quit | Right-click → Quit |

## Icon Colours

| Colour | Meaning |
|---|---|
| Teal | Balance is above the alert threshold |
| Red | Balance is below threshold, or an API error occurred |
| Warm gray | API service is degraded (balance data may be stale) |
| Gray | First check not yet completed, or no API key configured |

## License

MIT
