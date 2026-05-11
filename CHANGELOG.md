# Changelog

All notable changes to DeepSeek Balance Monitor are documented here.

Where older release notes were not present in the repository, entries were reconstructed from git tags and commit history.

## Rust v1.2 (2026-05-11)

### Added

- Rust Windows and Rust Linux are now versioned as `1.2.0` across Cargo metadata, Windows manifest, and Plasma widget metadata.
- Encrypted SQLite `secure_settings` API key storage for both Rust Windows and Rust Linux.
- Automatic migration from legacy plaintext `config.json.api_key` into encrypted SQLite storage.
- Rust demo mode enabled by saving `demo` as the API key; demo data is stored in an isolated `demo_mode_balance` table.
- Rust Linux `dsmon set-key` command for encrypted API key updates.
- Rust Linux `dsmon set <field> <value>` command for single-field configuration updates.
- Rust Linux installer prompts for an API key when the first check has no key or detects an invalid key.
- Rust Linux package includes `uninstall.sh` for removing `dsmon` and the systemd user service while leaving active Plasma widget files untouched.
- Plasma 6 desktop widget liquid-glass view with balance, last check, API service status, estimated availability, refresh control, and emoji status text.

### Changed

- Rust Linux daemon reloads configuration on every polling cycle so CLI changes are picked up without restarting the service.
- Rust Linux CLI output is English-only and no longer sends desktop notifications.
- Rust Windows opens the settings dialog on first launch when no API key is available.
- Rust Windows and Rust Linux separate `ui_language` from fixed English CLI `language`.
- Rust CSV exports default to the user's home directory and use date-suffixed filenames.
- Rust Windows and Rust Linux keep demo balance data out of the real `balance_history` table.
- Plasma widget settings use the new `dsmon set` command path instead of the legacy bulk `set-config` flow.

## Python v1.2 (2026-05-11)

### Added

- Custom icon styling with 5 preset colour themes: Default, High Contrast, Bright, Dark Mode, and Monochrome.
- Custom hex colour editor and icon stroke toggle.
- History viewer with paginated balance records, an interactive trend chart, and consumption rate analysis.
- CSV export with a configurable save path.
- Consumption rate estimation with daily average spend and projected days/hours remaining in balance notifications and history views.
- Demo mode with a developer tools panel for testing without a real API key.
- HTTP proxy support for restricted network environments.
- Windows Credential Manager integration so API keys are stored encrypted instead of plaintext in `config.json`.
- macOS WebView-based settings UI.
- Unit test coverage for core API parsing and state transitions.

### Changed

- Balance detail notifications now use emoji-prefixed lines.
- Last-check time is displayed as a relative time.
- API service status is recorded alongside each balance history entry.
- Settings, history, and developer tools share one Tk root window to avoid window-state conflicts.
- Settings validation now shows clearer errors and includes version, contributor, and project-link information.
- macOS build script gained DMG packaging support.

## v1.1 Fix Releases (2026-05-10)

### Fixed

- Repaired Plasma widget configuration pages.
- Added the Windows app icon to Rust Windows builds.
- Refreshed project structure and contributor documentation.

## v1.1 (2026-05-10)

### Added

- API service status polling via `status.deepseek.com`.
- Warm gray tray icon state when the DeepSeek API service is degraded.
- Independent desktop notifications for API service status changes.
- "Top Up" menu item that opens `platform.deepseek.com/top_up`.
- SQLite balance history storage with configurable log and record retention.
- Community ports:
  - Rust Windows native tray app for Windows 7 and newer.
  - Rust Linux CLI and KDE Plasma 6 widget.
  - Python macOS app with local key storage.
- Rust history tooling: chart, days/currency filters, CSV export, and `dsmon history` CLI commands.
- Plasma widget daemon start/stop action with command-error notifications.
- Windows 7/8.1 root certificate update helper script.

### Changed

- Low balance alerts now support three modes: never, always, or once per drop.
- Balance detail notifications were redesigned with a fixed title, inline balance breakdown, and always-visible service status.
- Settings dialog validates numeric inputs on save and warns about out-of-range values.
- Python API requests moved from `requests` to the standard library `urllib.request`.

## Rust v1.0.1 (2026-05-10)

### Fixed

- Adjusted Rust workflow tag triggers to avoid collisions with Python release tags.
- Updated Rust port synchronization documentation.

## v1.0.1 (2026-05-09)

### Changed

- Made direct downloads the recommended installation path in README.
- Moved screenshots closer to the top of README.
- Cleaned up user-facing README wording.
- Removed the old taskbar preview image.
- Performed code audit cleanup and formatting normalization.

### Fixed

- Improved settings dialog behaviour.
- Hardened API key encoding.
- Refined icon colour and alert toggle handling.

## v1.0.0 (2026-05-06)

### Added

- Initial public Python Windows tray app.
- Periodic DeepSeek balance checks.
- Low-balance alerts.
- Settings dialog for API key, interval, threshold, language, and auto-start.
- Tray icon rendering.
- Build scripts for packaged Windows executables.

### Changed

- Repository was reorganized into `src/` and `scripts/`.
- Hardcoded currency symbols were removed from balance display.
- Deprecated currency selection logic was removed.

## Rust Linux v0.2.0 (2026-05-09)

### Added

- Initial Rust Linux `dsmon` release build.
- Linux packaging groundwork for command-line balance checks.

## Rust Windows v0.1.1 (2026-05-09)

### Changed

- Prepared the Rust Windows 0.1.1 release.
- Documented the Rust Windows build flow.
- Merged the Rust Windows port with the upstream Python baseline.

## Rust Windows v0.1.0 (2026-05-09)

### Added

- Initial Rust Windows native build.
- GitHub Actions release artifact workflow for Rust Windows builds.

### Fixed

- Hardened Rust Windows startup build behaviour.
