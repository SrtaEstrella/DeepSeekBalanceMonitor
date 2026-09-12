# DeepSeek Balance Monitor

A Windows tray app and Linux CLI/Plasma widget that periodically query the DeepSeek API for account balance and alert on low balance.

[中文版](README_zh.md)

![preview](assets/preview.png)

![Rainmeter preview](assets/preview_rainmeter.png)

Rainmeter widget preview

[Linux Plasma widget preview](assets/preview_linux.png) (KDE Plasma 6 only)

[Mac WebView screenshots](assets/webview%20screenshots/) — menu bar, settings UI, history chart, light theme

---

## Current Version Highlights

- Migrated to FlashDuty-backed DeepSeek status page, replacing the deprecated `status.deepseek.com/api/v2` endpoint.
- Custom icon styling with 5 preset colour themes, custom hex colours, and an icon stroke toggle.
- History viewer with paginated balance records, an interactive trend chart, and consumption rate analysis.
- CSV export with a configurable save path.
- Busy-hour consumption rate estimation (filters idle/flat periods) in balance notifications and the history viewer.
- HTTP proxy support.
- Balance detail notifications now use emoji-prefixed lines and relative last-check time.
- Demo mode for testing without a real API key: developer tools panel on Py-Win/Py-Mac, `demo` API key trigger on Rust.
- Encrypted API key storage: Fernet + SQLite on Py-Win, SQLite `secure_settings` on Rust, Keychain on Py-Mac.
- Rainmeter desktop widget: local-only status interface; `.rmskin` release packaging. Supported on both Rust and Python Windows builds.
- Rainmeter `/widget-status` now includes OpenCode Go quota fields (`og_*`), refreshed every 10 minutes in the background; interface contract documented with Python-port guidance.
- OpenCode Go quota display (Rust builds): fetches the official OpenCode Go API (`opencode.ai/zen/go/v1/usage`, Bearer API key) for rolling (5h), weekly, and monthly usage; credentials stored encrypted in SQLite, never in config.json.
- Command Code quota display (Rust builds): fetches `api.commandcode.ai` billing endpoints (Bearer API key) for 5h, weekly, and monthly usage; the monthly window is derived from the plan tier inferred from the rolling window caps (Go 10 / GOAT 70 / Pro 80 / Max 10× 150 / Max 20× 300 / Team Pro 40 credits); the Windows settings dialog and Plasma widget each gain a "Subscriptions" page showing OpenCode Go and Command Code quota side by side, with all API keys entered on the Account page. Linux CLI: `dsmon command-code` / `dsmon command-code set-key` / `dsmon command-code json`.
- Rust builds use rustls with embedded webpki-roots: no OS certificate store is consulted, so the Windows build works out of the box on Windows 7/8.1 and supports TLS 1.3.

Rust Linux-specific:
- Rust Linux: `dsmon set-key` and `dsmon set <field> <value>`; daemon reloads config on each poll cycle; CLI stays English-only.
- `dsmon opencode-go` prints OpenCode Go quota; `dsmon opencode-go set-key <api_key>` stores the API key encrypted; `dsmon opencode-go json` emits machine-readable output.
- `dsmon command-code` prints Command Code quota; `dsmon command-code set-key <api_key>` stores the API key encrypted; `dsmon command-code json` emits machine-readable output.
- The Plasma 6 widget settings are split by purpose: the Account page holds all API keys (DeepSeek, OpenCode Go, Command Code); a new Subscriptions page shows both OpenCode Go and Command Code quota bars; the General page is organised into Query / General / Proxy / Icon Appearance groups.
- Plasma 6 widget main view: the DeepSeek balance is shown as a large number with last check, API status, and estimated availability in a four-line layout; the OpenCode and Command Code sections each show three usage progress bars (5h/Weekly/Monthly), all refreshed together from the top-right button.
- Refreshing the Linux Plasma widget model: balance, relative last check, API service status, and estimated availability now match the Rainmeter widget layout.
- Plasma widget language changes now sync `cfg_language` to `dsmon`'s `ui_language`, persisting the Chinese/English selection across Plasma restarts.
- Linux releases now provide both a complete `.tar.gz` package and a standalone `.plasmoid` widget package for direct download.

## Features

- **Tray icon with balance** — Balance shown as a number on a coloured rounded rectangle. Teal (OK), red (low balance), warm gray (API service degraded), gray (no data yet). 5 customisable themes + custom hex colours.
- **Low balance notification** — Three modes: never, always, or once per drop (default). The icon turns red regardless.
- **Balance details** — Left-click the icon to see balance (emoji-prefixed), consumption rate, API service status, and relative last-check time.
- **History viewer** — Paginated table of all balance records with interactive trend chart and consumption rate analysis. CSV export.
- **Settings** — API key (Fernet + SQLite encrypted storage), check interval, alert threshold, alert mode, icon theme, proxy, and more.
- **OpenCode Go & Command Code quota** (Rust builds) — A "Subscriptions" settings page (Windows) or `dsmon opencode-go` / `dsmon command-code` (Linux) shows rolling 5h/weekly/monthly usage from the opencode.ai and commandcode.ai dashboards, with encrypted credential storage.
- **Demo mode** — `--demo` flag for testing without an API key, with a developer tools panel.
- **Optional desktop widgets** — KDE Plasma 6 on Linux, and Rainmeter on Windows (Rust and Python builds both supported).
- **Community ports** — Rust-Win (Win7+), Rust-Linux (CLI + Plasma 6 widget), Py-Mac (Keychain-secured, WebView settings UI).

### Notification Previews

**Normal balance view:**

> DeepSeek Balance:  
> 💰 12.34 CNY (Topped 10.00, Granted 2.34)  
> 📊 Busy: 0.06/hr  |  Est. 28d 4h remaining  
> 📡 DeepSeek API Status: 🟢 All Systems Operational  
> 🕐 Last Check: 5 min ago

**Low balance alert:**

> ⚠ DeepSeek Low Balance  
> Balance is only 0.50, below your alert threshold of 1.00.  
> Please top up!

## Getting Started

### Direct Download

Grab the latest files from [Releases](https://github.com/wenyinos/DeepSeekBalanceMonitor/releases). Python builds use `DeepSeekBalanceMonitor.exe`, Rust Windows builds use `deepseek-balance-monitor-*-windows-*.exe`, full Linux packages use `deepseek-balance-monitor-*-linux-x86_64.tar.gz`, and standalone Plasma widgets use `deepseek-balance-monitor-*-plasmoid.plasmoid`. Release builds do not require Python.

### Optional Plasma Widget (Linux)

The Plasma widget is optional and requires KDE Plasma 6. It reads status from a local `dsmon` instance and does not directly receive your API key.

1. Download `deepseek-balance-monitor-*-linux-x86_64.tar.gz` from [Releases](https://github.com/wenyinos/DeepSeekBalanceMonitor/releases).
2. Extract and run the install script:

   ```bash
   tar -xzf deepseek-balance-monitor-*-linux-x86_64.tar.gz
   cd deepseek-balance-monitor-*-linux-x86_64
   sudo ./install.sh
   ```

   The installer auto-enables and starts the daemon (`systemctl --user enable --now dsmon.service`).

3. Add **DeepSeek Balance Monitor** from the Plasma widget chooser.
4. Open the widget settings, enter your DeepSeek API key (or use `dsmon set-key`), then click **Save**.
5. Click **Check** in the widget to manually refresh the balance.

If you only need the widget, download `deepseek-balance-monitor-*-plasmoid.plasmoid` and install it with the Plasma widget installer. The full Linux tarball also contains the same widget under `plasmoid/`.

### Optional Rainmeter Widget (Windows)

The Rainmeter desktop widget is optional. It reads local status from a running DeepSeek Balance Monitor process (`127.0.0.1:17654`); it does not store or receive your API key. Supported on both Rust and Python Windows builds. The `/widget-status` response includes DeepSeek balance, service status, consumption rate and — on the Rust Windows build — OpenCode Go quota fields (`og_configured`, `og_error`, and `og_rolling|weekly|monthly_percent`/`_line`), refreshed every 10 minutes in the background.

1. Install Rainmeter from [rainmeter.net](https://www.rainmeter.net/).
2. Run any Windows build (Python or Rust) — the local status interface starts automatically.
3. Download `deepseek-balance-monitor-*-rainmeter.rmskin` from [Releases](https://github.com/wenyinos/DeepSeekBalanceMonitor/releases).
4. Double-click the `.rmskin` file and install the skin.
5. In Rainmeter, load `DeepSeekBalanceMonitor\DeepSeekBalanceMonitor.ini` (or `DeepSeekBalanceMonitor.en.ini` for English).

**High-DPI screens:** set `Rainmeter.exe` → Properties → Compatibility → Change high DPI settings → check "Override high DPI scaling behavior" and select "Application". Then load the 2x-scaled `DeepSeekBalanceMonitor.hd.ini` (or `.en.hd.ini`).

### Requirements

Direct downloads (`.exe`, `.tar.gz`, `.dmg`) require no additional runtimes.

- Py-Win: Windows 10+
- Rust-Win: Windows 7 SP1+ (all official updates), 8.1, 10, or 11
- Rust-Linux: RHEL 8 / Ubuntu 20.04 era glibc or newer; KDE Plasma 6.0+ for the widget
- Py-Mac: MacOS 10.14+

Building from source additionally requires Python 3.10+ (Py-Win, Py-Mac) or Rust 1.77.2 (Rust-Win, Rust-Linux).

### TLS Certificates

Both Rust builds use rustls with embedded webpki-roots: the Mozilla root store is compiled into the binary and no operating system certificate store is consulted. The Windows build therefore works on Windows 7/8.1 with stale trust stores out of the box (TLS 1.3 included), and the former `update_windows_root_certs.bat` helper script has been removed as unnecessary — Py-Win requires Windows 10+ anyway.

Note that TLS inspection by a corporate proxy or security software will fail certificate validation, because only the embedded root store is trusted.

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

**Rust Windows (`rust-windows/`):**

```powershell
cd rust-windows
rustup toolchain install 1.77.2-x86_64-pc-windows-msvc
cargo +1.77.2 build --release --target x86_64-pc-windows-msvc --locked
```

**Rust Linux (`rust-linux/`):**

```bash
cd rust-linux
cargo +1.77.2 build --release --locked
```

Linux release tarballs install the `dsmon` binary and systemd user service at system level (`/usr/local/bin/dsmon`, `/etc/systemd/user/dsmon.service`) with sudo, and the Plasma widget plus its icon under your user directory (`~/.local/share/`) so widget updates never need sudo:

```bash
tar -xzf deepseek-balance-monitor-*-linux-x86_64.tar.gz
cd deepseek-balance-monitor-*-linux-x86_64
sudo ./install.sh
```

On systemd systems the installer runs `systemctl --user enable --now dsmon.service` (for the sudo user) so the daemon auto-starts on login and runs immediately; on non-systemd systems it writes a desktop autostart entry instead.

The CLI is currently available only in the Rust Linux build. Windows and MacOS builds use GUI/tray controls.

Useful Linux CLI commands:

| Command | Purpose |
|---|---|
| `dsmon init-config` | Create the default config file if it does not exist |
| `dsmon set-key` | Read an API key from stdin and store it encrypted in SQLite; enter `demo` to enable demo mode |
| `dsmon set <field> <value>` | Update one config field, such as `interval`, `threshold`, `ui-language`, `http-proxy`, `theme`, or `color-ok` |
| `dsmon check` | Run one balance check and print the result in English |
| `dsmon daemon` | Run the polling loop used by the user systemd service |
| `dsmon history [days]` | Print a balance history summary |
| `dsmon history export [days] [currency\|all] [path\|-]` | Export history as CSV; `-` writes CSV to stdout |
| `dsmon widget-status` | Print JSON status consumed by the Plasma widget |
| `dsmon opencode-go` | Print OpenCode Go quota (5h/weekly/monthly usage); store the API key with `dsmon opencode-go set-key <api_key>` (or pipe it via stdin; get a key at https://opencode.ai/auth) |
| `dsmon command-code` | Print Command Code quota (5h/weekly/monthly usage); store the API key with `dsmon command-code set-key <api_key>` (or pipe it via stdin; get a key at https://commandcode.ai) |

**MacOS (`src/mac/`):**

```bash
cd src/mac
pip install -r requirements.txt
bash ../scripts/build_mac.sh
```

### Python vs Rust

| | Python Windows | Rust Windows | Rust Linux | Python MacOS |
|---|---|---|---|---|
| Runtime | Python + pystray + Tkinter | Native Rust + native-windows-gui | Native Rust CLI | Python + rumps + webview |
| Min OS | Windows 10+ | Windows 7 SP1+ | RHEL 8 / Ubuntu 20.04 era glibc | MacOS 10.14+ |
| First launch (no key) | Opens settings dialog | Opens settings dialog | Installer/check prompts for `dsmon set-key` | Opens settings window |
| Auto-start | Registry Run key | Startup folder shortcut | systemd user service | Login items |
| API key storage | Fernet + SQLite | SQLite `secure_settings` encrypted with Windows DPAPI | SQLite `secure_settings` encrypted locally | MacOS Keychain |

## Project Structure

```
DeepSeekBalance/
├── src/                       # Application package
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
├── src/mac/                    # Native MacOS port
│   ├── main.py
│   ├── settings.py
│   └── keystore.py
├── scripts/                    # Build & utility scripts
│   ├── build_exe.bat
│   ├── build_mac.sh
│   ├── setup.bat
│   ├── run_silent.vbs
│   └── demo.vbs
├── assets/                     # Icons, previews, fonts
│   ├── app.ico
│   ├── AppIcon.icns / .png
│   ├── preview.png / preview_zh.png
│   └── font/
├── rainmeter-widget/           # Rainmeter desktop skin source
├── rust-windows/               # Native Rust Windows port
│   ├── src/main.rs
│   ├── app.manifest
│   └── build.rs
├── rust-linux/                # Rust Linux CLI and Plasma 6 widget
│   ├── src/main.rs
│   ├── package/
│   └── plasmoid/
├── main.py
├── requirements.txt
└── README.md
```

## Configuration

Windows builds store settings in `%APPDATA%\DeepSeek Balance Monitor\config.json`:

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

API keys are never written to this file. Python Windows uses Fernet + SQLite encryption, Python MacOS uses Keychain, and Rust Windows/Linux store encrypted keys in SQLite `secure_settings`.

Linux `dsmon` stores settings in `~/.config/deepseek-balance-monitor/config.json` and logs in `~/.local/state/deepseek-balance-monitor/app.log`.

Windows logs are written to `%APPDATA%\DeepSeek Balance Monitor\app.log`.

Rust Windows and Rust Linux store encrypted settings and balance history in `balance_history.db` next to their app data. History uses the same `retention_days` setting as log cleanup. The Windows settings dialog and Plasma widget settings include a History tab with days/currency filters, trend summary, chart, and CSV export. Linux CLI output stays English-only and `dsmon history` prints text statistics instead of raw rows.

## Tray Menu

| Action | Trigger |
|---|---|
| View Balance | Left-click the icon, or Right-click → View Balance |
| Check Now | Right-click → Check Now |
| Top Up | Right-click → Top Up |
| History | Right-click → History |
| Settings | Right-click → Settings |
| Quit | Right-click → Quit |

## Icon Colours

| Colour | Meaning |
|---|---|
| Teal | Balance is above the alert threshold |
| Red | Balance is below threshold, or an API error occurred |
| Warm gray | API service is degraded (balance data may be stale) |
| Gray | First check not yet completed, or no API key configured |

Colours are customisable via 5 presets or custom hex values in the settings dialog.

## Changelog

[CHANGELOG.md](CHANGELOG.md)

## License

MIT
