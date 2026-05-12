# Changelog

All notable changes to DeepSeek Balance Monitor are documented here.

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
