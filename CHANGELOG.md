# Changelog

All notable changes to DeepSeek Balance Monitor are documented here.

## Rust v1.4.3 (2026-09-12)

### Fixed

- Both Rust implementations: Command Code monthly usage disappeared from the CLI, the Plasma widget, the Windows settings window and the Rainmeter `cc_monthly_*` fields once the API stopped returning `credits.planId`; the plan tier (and its monthly credit pool) is now inferred from the rolling window caps (5h/weekly), which identify the plan uniquely — Go 10 / GOAT 70 / Pro 80 / Max 10× 150 / Max 20× 300 / Team Pro 40 credits
- Both Rust implementations: monthly usage is `pool − credits.monthlyCredits`, clamped to the pool, so bonus credits can no longer produce a negative usage; plans whose window caps match no known tier (pay-as-you-go has no rolling windows) keep the monthly window unavailable

### Changed

- Command Code: `credits.planId` parsing and the fixed GOAT 70-credit constant are gone; the monthly window no longer requires the account to be identified as a GOAT plan

### Python implementation (no version bump in this release)

- Command Code monthly window uses the same window-cap inference instead of the removed `planId`, and the standard `command_code` platform entry shows the monthly window too; the `command_code_goat` entry gains `window_pools` (14/35/70) for refining
- Automatic polling no longer stops silently after saving settings: balance-check cycles re-arm themselves in a `finally` block, and settings save calls `restart_polling()` to cancel and re-arm atomically
- OCGo refined remaining uses round-band semantics (`|refined − raw| ≤ 0.5`, matching the API's rounded integer) instead of the previous floor band

## Rust v1.4.2 (2026-09-06)

### Fixed

- Rust Linux: an unrecognized service-status component ranked highest in `status_rank`, masking real `critical` outages — the CLI/widget showed "Status Unknown" instead of "Critical Outage"; unknown now ranks lowest, matching rust-windows
- Both Rust implementations: the busy-hour consumption-rate algorithm hardcoded a 10-minute check interval when deciding whether a gap is idle; it now uses the configured `interval_minutes`, so larger intervals (e.g. 60 min) no longer have their normal polling gaps sliced as idle time, which underestimated the rate
- Rust Windows: balance history rows are deduplicated with the same 120-second window as Rust Linux; previously every check inserted a row even with an unchanged balance, bloating the database (up to ~1440 rows/day per currency at a 1-minute interval)
- Rust Windows: a corrupted `config.json` no longer silently resets all settings — the file is backed up as `config.json.corrupt` and the failure is logged
- Rust Windows: the settings dialog validates all fields before persisting any API key; previously a new DeepSeek key was written to secure storage even when interval/threshold validation failed afterwards
- Rust Windows: export paths starting with `%USERPROFILE%` are expanded; the placeholder suggested it but the raw string was used, creating a literal `%USERPROFILE%` directory
- Both Rust implementations: OpenCode Go usage percent is clamped to 0–100 (the Linux CLI could print values above 100%)
- Both Rust implementations: balance display and the low-balance threshold prefer the CNY balance when multiple currencies exist, instead of the alphabetically-first currency (a USD balance could be compared against the CNY threshold)

### Changed

- Both Rust implementations: the SQLite database now runs in WAL journal mode with a 5-second busy timeout and indexes on `timestamp` and (`currency`, `timestamp`); concurrent access (Windows UI thread vs. balance-check / OpenCode Go / Command Code / Rainmeter threads, Linux daemon vs. widget-status) no longer fails with "database is locked", and history queries use the indexes
- Rust Windows: the tray icon font is loaded once per process (thread-local cache) instead of re-reading the font file on every tray refresh; unused `ensure_config_file` removed

### Security

- Rust Windows: launching a second copy is now blocked by a named mutex — the duplicate logs the failure, shows a native message box, and exits instead of running two tray icons racing on the same icon file and database
- Rust Windows: the local Rainmeter HTTP server no longer sends `Access-Control-Allow-Origin: *`, so web pages open in the user's browser can no longer read balance/subscription data or trigger checks via CORS (Rainmeter's WebParser does not rely on CORS)

## Rust v1.4.1 (2026-09-01)

### Changed

- Linux install split by scope: the `dsmon` binary and systemd user service stay system-level (`/usr/local/bin/dsmon`, `/etc/systemd/user/dsmon.service`, installed with sudo), while the Plasma widget and its icon install under the user directory (`~/.local/share/`) so widget updates never need sudo
- The Plasma widget calls `dsmon` by its absolute path `/usr/local/bin/dsmon` so it works from the Plasma `executable` engine regardless of the session PATH
- The installer runs `systemctl --user enable --now dsmon.service` after installation (for the sudo user), so the daemon is set to auto-start on login and starts immediately
- On non-systemd distributions (e.g. OpenRC), the installer skips the systemd service file and instead writes a desktop autostart entry (`~/.config/autostart/deepseek-balance-monitor.desktop`) that starts the daemon at desktop login
- The installer detects leftover user-level files from the earlier user-only install (1.4.1-rc: `~/.local/bin/dsmon`, `~/.config/systemd/user/dsmon.service`) and offers to remove them

## Rust v1.4.0 (2026-09-01)

### Added

- Command Code quota display (Rust Windows and Rust Linux): queries `api.commandcode.ai/alpha/billing/credits` (with `orgId` from `alpha/whoami`) and reports 5h / weekly / monthly usage. Monthly is derived for GOAT plans (70 credits) and left unavailable for other plans
- Windows: the settings dialog gains a "Subscriptions" tab holding both OpenCode Go and Command Code quota groups (each with three usage progress bars and a refresh button); all API keys (DeepSeek, OpenCode Go, Command Code) are entered on the Account tab
- Linux: new `dsmon command-code` (query quota), `dsmon command-code set-key <api_key>` (store the API key), and `dsmon command-code json` (JSON output) CLI commands
- Linux: the Plasma 6 widget gains a "Subscriptions" settings page showing OpenCode Go and Command Code quota, with credentials kept on the Account page; the widget main view adds a Command Code section with three usage progress bars
- Command Code API key is stored encrypted in the `secure_settings` table under the `command_code_api_key` key, never written to config.json
- Rust Windows: the local Rainmeter `/widget-status` interface now also exposes Command Code quota fields (`cc_configured`, `cc_error`, `cc_5h/weekly/monthly_percent` and `_line`), refreshed every 10 minutes by a background thread with last-good retention on failure — an interface reserve for the upcoming Rainmeter skin integration; the contract is documented in `rainmeter-widget/PYTHON_RAINMETER_INTEGRATION.md`

## Rust v1.3.3 (2026-08-30)

### Changed

- Rust Windows migrated from native-tls (Schannel) to rustls with embedded webpki-roots, matching rust-linux: no OS certificate store is consulted, Windows 7/8.1 installs validate out of the box, and TLS 1.3 is now available on old systems; TLS-inspecting proxies or security software will fail certificate validation since only the embedded root store is trusted
- Removed `scripts/update_windows_root_certs.bat`, unnecessary after the embedded-root migration (Py-Win requires Windows 10+ anyway); README TLS sections and directory trees updated accordingly

### Fixed

- Settings window font rendering: bold group titles no longer hardcode Segoe UI, whose missing CJK glyphs caused font fallback or tofu on the Chinese UI — the heading font now follows the unified UI family with real font enumeration (Microsoft YaHei UI, falling back to Microsoft YaHei / SimSun), and a stray 9-pixel size that rendered titles smaller than body text was dropped

## Rust v1.3.2 (2026-08-14)

### Changed

- Plasma 6 widget settings redesigned to match rust-windows: a new "Account" page holds both API keys (DeepSeek and OpenCode Go) plus the OpenCode quota bars; the General page is organised into Query / General / Proxy / Icon Appearance groups; the separate "OpenCode Go" settings page is merged into Account
- Plasma widget main view redesigned: the DeepSeek section follows a four-line layout (balance, last check, API status, estimated availability) with the refresh button moved to the top-right corner refreshing DeepSeek and OpenCode together; the OpenCode section shows three usage progress bars with larger type and bars
- Font hierarchy and spacing adjusted across both sections for a clearer visual order
- Rust Windows: the local Rainmeter `/widget-status` interface now includes OpenCode Go quota fields (`og_configured`, `og_error`, `og_rolling/weekly/monthly_percent` and `_line`), refreshed every 10 minutes by a background thread with last-good retention on failure; the interface contract and Python-port guidance are documented in `rainmeter-widget/PYTHON_RAINMETER_INTEGRATION.md`

## Rust v1.3.1 (2026-08-14)

### Changed

- Windows settings window redesigned: a new "Account" tab groups the DeepSeek and OpenCode Go API keys; the Settings tab is organised into Query / General / Proxy / Icon Appearance groups with bold titles and separator lines; all controls are aligned to a consistent grid with unified label and input columns

## Rust v1.3.0 (2026-08-14)

### Changed

- OpenCode Go quota now uses the official API (`opencode.ai/zen/go/v1/usage`) with a Bearer API key, replacing the workspace-dashboard scraper (workspace ID + auth cookie)
- Credentials simplified to a single API key, stored encrypted in the `secure_settings` table under `opencode_go_api_key`, never written to config.json
- Windows: the "OpenCode Go" settings tab now takes an API key instead of workspace ID / auth cookie
- Linux: `dsmon opencode-go set-key <api_key>` stores the API key; without an argument it reads from stdin, matching `dsmon set-key`
- Plasma: the "OpenCode Go" settings page gains API key input with save (same pattern as the DeepSeek key), and the quota progress bars use `QtControls.ProgressBar` for reliable rendering

## Rust v1.2.10 (2026-08-02)

### Added

- OpenCode Go quota display (Rust Windows and Rust Linux): queries the official `opencode.ai/zen/go/v1/usage` API with a Bearer API key and reports rolling (~5h), weekly, and monthly usage as used/remaining percentages with reset time
- Windows: the settings dialog gains an "OpenCode Go" tab with an API key input and a manual refresh button
- Linux: new `dsmon opencode-go` (query quota), `dsmon opencode-go set-key <api_key>` (store the API key), and `dsmon opencode-go json` (JSON output) CLI commands
- Linux: the Plasma 6 widget adds a dedicated "OpenCode Go" settings page showing quota, read directly from `dsmon opencode-go json`
- OpenCode Go API key is stored encrypted in the `secure_settings` table under the `opencode_go_api_key` key, never written to config.json

## Rust v1.2.6 (2026-06-08)

### Changed

- Consumption rate algorithm upgraded to busy-hour slicing (ported from Python v1.2.7): filters long idle gaps and flat periods; returns hourly rate instead of daily average
- Unified display format across all platforms:
  - Chinese: `📊 忙时消耗 0.06/小时 | 预计可用 28 天 4 小时`
  - English: `📊 Busy: 0.06/hr | Est. 28d 4h remaining`
- Updated `ConsumptionRate` struct: `daily_rate` → `hourly_rate`, `hours_left` → `busy_hours_left`
- Updated demo mode to use new rate fields
- Plasma widget updated to display hourly consumption rate

### Platform-Specific

- **Rust Windows**: Added `estimated_line` field to Rainmeter widget-status interface
- **Rust Linux**: Removed `estimated_line` (not needed for Plasma widget; uses `consumption_rate` field directly)

## Python v1.2.7 (2026-05-28)

### Fixed

- Fixed tkinter+pystray dual event-loop deadlock freezing the tray icon when settings/history dialogs were open

### Changed

- Consumption rate switched to busy-hour slicing algorithm: long idle gaps and flat periods are filtered out; displayed as hourly rate instead of daily average

## Python v1.2.6 (2026-05-13)

### Fixed

- Fixed connection refused and exit failure when system proxy (Clash etc.) goes down: empty `ProxyHandler` blocks system proxy, `socket.setdefaulttimeout` global fallback
- Fixed DNS resolution timeout blocking on network loss: global socket timeout + exit flag checks
- Fixed potential `cancel_timer` deadlock preventing `icon.stop()`: `icon.stop()` now runs before cleanup
- Removed API key `demo` trigger for dev mode: Python uses `--demo` CLI flag only

## Python v1.2.5 (2026-05-13)

### Added

- Developer Demo mode update: mock history data generated on startup; developer panel gains custom consumption rate & estimated hours display
- Custom icon colour live preview with hex validation on save
- History date filter with `YYYYMMDD` format query

### Changed

- History viewer extracted to `src/history_dialog.py`
- Tray notification and history page rate/time/prefix bilingual strings fully extracted to i18n keys

### Fixed

- Fixed settings "Enable proxy" off calling `install_proxy("")` with empty `ProxyHandler` overriding system proxy

## Rust v1.2.5 (2026-05-12)

### Added

- Standalone Plasma widget release asset: `deepseek-balance-monitor-*-plasmoid.plasmoid`
- Linux release tarballs now include the same Plasma widget package under `plasmoid/`
- Linux release assets include `checksums.txt` for tarball verification

### Changed

- Plasma widget display now follows the Rainmeter layout: balance line, relative last-check time, API service status, and estimated remaining time
- Plasma widget language settings now sync `cfg_language` back to `ui_language`, so English/Chinese selection survives Plasma restarts
- Low-balance display colour now takes priority over API-degraded colour, matching Rainmeter accent rules
- Rust Linux and Rust Windows service-status checks now use the FlashDuty-backed DeepSeek status page
- Consumption estimates use topped-balance history over a 7-day window, with retention-period fallback when needed
- Proxy settings now include an explicit enable toggle while preserving the proxy address when disabled

### Fixed

- Fixed Linux Plasma language changes appearing to reset after restarting `plasmashell`
- Fixed removed DeepSeek status REST API usage in Rust ports
- Fixed Windows settings title/footer behaviour to match the v1.2 settings design

## Python v1.2.2 (2026-05-12)

### Fixed

- Emergency migration of API service status monitoring to FlashDuty endpoint after DeepSeek replaced the underlying status page

## Python v1.2.1 (2026-05-12)

### Added

- Rainmeter local HTTP status interface on `127.0.0.1:17654`, auto-starts with the app, toggleable in settings
- Rainmeter `.rmskin` packaging script; CI auto-builds alongside EXE
- Rainmeter 2x high-DPI skin variants (ZH/EN)

### Changed

- API key storage unified to Fernet + SQLite, with legacy fallback; save_config() clears plaintext automatically
- Proxy now a checkbox toggle + address input; address is preserved when disabled
- Settings title simplified to `⚙️ Settings`, footer balance/last-check rows removed, version & contributor info shown
- Consumption rate restored to topped-balance with 7-day window and weighted average, plus retention fallback

## Rust v1.2 (2026-05-11)

### Added

- Rust Windows and Rust Linux versioned as `1.2.0`
- SQLite `secure_settings` encrypted API key storage (Rust Windows / Linux)
- Auto-migration from legacy plaintext `config.json.api_key` to encrypted storage
- Rust demo mode: save `demo` as the API key, data stored in isolated `demo_mode_balance` table
- Rust Linux `dsmon set-key` command for encrypted API key updates
- Rust Linux `dsmon set <field> <value>` command for single-field config updates
- Rust Linux installer prompts for API key on first launch when none is configured
- Rust Linux `uninstall.sh` script (preserves Plasma widget)
- Plasma 6 widget liquid-glass view with balance, last check, service status, estimated availability, refresh control, and emoji status text
- Rainmeter desktop widget via local `127.0.0.1:17654` interface; Rust Windows currently provides the interface
- GitHub Actions `.rmskin` packaging via `rmskin-builder`

### Changed

- Rust Linux daemon reloads config on each poll cycle; CLI changes take effect immediately
- Rust Linux CLI output is English-only, no desktop notifications
- Rust Windows opens settings dialog on first launch when no API key is configured
- Rust Windows/Linux separate `ui_language` (GUI) from `language` (CLI, fixed English)
- Rust CSV exports default to user home directory with date-suffixed filenames
- Rust demo data stays out of the real `balance_history` table
- Plasma widget settings use `dsmon set` command

## Python v1.2 (2026-05-11)

### Added

- Custom icon themes: 5 presets (Default / High Contrast / Bright / Dark Mode / Monochrome) + custom hex colours + icon stroke toggle
- History viewer: paginated table + trend chart + consumption rate analysis, with CSV export
- Consumption rate estimation: topped-balance weighted average, shown in balance notification and history viewer
- Demo mode: `--demo` flag with developer tools panel
- HTTP proxy support
- API key stored in Windows Credential Manager, config.json relegated to migration fallback
- MacOS WebView settings UI
- Unit test coverage for core API parsing and state transitions

### Changed

- Balance notification: emoji-prefixed lines, relative last-check time, service status repositioned
- API service status recorded alongside each balance history entry
- Settings, history, and dev tools share one Tk root window; history and dev tools support singleton raise-to-front
- Settings footer shows version, contributor credits, and project link
- MacOS build script adds DMG packaging

## Rust v1.1 (2026-05-10)

### Added

- Rust Windows native tray app, Win7+ support
- Rust Linux CLI + KDE Plasma 6 widget
- Rust history features: chart, days/currency filters, CSV export, `dsmon history` CLI
- Plasma widget daemon start/stop with command-error notifications
- Windows 7/8.1 root certificate update helper script

### Fixed

- Repaired Plasma widget configuration pages
- Added app icon to Rust Windows builds

## Python v1.1 (2026-05-10)

### Added

- API service status polling (`status.deepseek.com`); warm gray tray icon when degraded, independent status-change notifications
- "Top Up" tray menu item linking to `platform.deepseek.com/top_up`
- SQLite balance history storage with configurable log/record retention (default 30 days)
- Community port: Python MacOS app with Keychain encryption
- CONTRIBUTING.md for community porters
- GitHub Actions auto-build and attach EXE to releases

### Changed

- Low balance alerts: three modes (never / always / once per drop), default once
- Balance notification redesign: fixed title, inline breakdown, always-visible service status
- Settings validates numeric input ranges on save and warns on invalid values
- Replaced `requests` with stdlib `urllib.request`

## Rust v1.0.1 (2026-05-09)

Internal dev versions: Windows v0.1.0/v0.1.1, Linux v0.2.0

### Added

- Initial Rust Windows native build
- GitHub Actions Rust Windows release artifact workflow
- Rust Windows build documentation
- Merged Rust Windows port with upstream Python main
- Initial Rust Linux `dsmon` release build
- Linux packaging groundwork for command-line balance checks

### Fixed

- Hardened Rust Windows startup build behaviour
- Rust workflow tag trigger changed to `rust-v*` to avoid collision with Python tags
- Updated Rust port sync documentation

## Python v1.0.1 (2026-05-09)

### Changed

- Reorganized repository into `src/` and `scripts/`
- Deprecated currency selection (each account maps to a single fixed currency)
- Settings dialog behaviour improvements
- API key character encoding hardening
- Icon colour and alert toggle refinements
- README updates: direct download as recommended path, optimized preview images
- Code audit and formatting cleanup

## Python v1.0.0 (2026-05-06)

### Added

- Initial public Python Windows tray app release
- Periodic DeepSeek balance checks
- Low-balance alerts
- Settings dialog (API key, interval, threshold, language, auto-start)
- Tray icon rendering
- Windows executable build scripts
