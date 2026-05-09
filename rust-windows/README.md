# DeepSeek Balance Monitor - Rust Windows Build

This is the Windows Rust port of the existing Python tray app. It targets:

- Windows 7 SP1 / Windows Server 2008 R2 SP1 with all official updates
- Windows 8.1 / Windows Server 2012 R2
- Windows 10 and Windows 11

The toolchain is pinned to Rust `1.77.2` because Rust `1.78+` raised the normal
Windows target baseline to Windows 10.

## Build

Run from this directory in a Visual Studio developer shell:

```powershell
rustup toolchain install 1.77.2-x86_64-pc-windows-msvc
cargo +1.77.2 build --release --target x86_64-pc-windows-msvc
```

The executable is written to:

```text
target\x86_64-pc-windows-msvc\release\deepseek-balance-monitor.exe
```

## Runtime Notes

Configuration is shared with the Python version:

```text
%APPDATA%\DeepSeek Balance Monitor\config.json
%APPDATA%\DeepSeek Balance Monitor\app.log
```

The app stores no API keys in source code. Enter the API key in the settings
window on first launch.
