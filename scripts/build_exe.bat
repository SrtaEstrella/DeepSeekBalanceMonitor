@echo off
chcp 65001 >nul
title Building DeepSeek Balance Monitor .exe

:: Always run from project root (one level above scripts/)
cd /d "%~dp0.."

echo ==============================================
echo   Building DeepSeek Balance Monitor .exe
echo ==============================================
echo.

:: Check Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python not found.
    pause
    exit /b 1
)

:: Check / Install PyInstaller
pip show pyinstaller >nul 2>&1
if %errorlevel% neq 0 (
    echo [*] Installing PyInstaller...
    pip install pyinstaller --quiet
    if %errorlevel% neq 0 (
        echo [ERROR] Failed to install PyInstaller.
        pause
        exit /b 1
    )
)
echo [OK] PyInstaller ready
echo.

:: Kill any running instance, then WAIT for it to go away: the app holds a
:: single-instance lock, so starting the new build while the old one is still
:: alive would make the new one report "already running" and exit — leaving the
:: previous build in the tray while the build itself reported success.
:: The delay is `ping`, not `timeout`: timeout needs a console stdin and fails
:: outright when this script is run with redirected input (CI, agent tooling).
echo [*] Stopping running instance (if any)...
setlocal enabledelayedexpansion
set _waited=0
:wait_kill
taskkill /f /im DeepSeekBalanceMonitor.exe >nul 2>&1
tasklist /fi "imagename eq DeepSeekBalanceMonitor.exe" 2>nul | find /i "DeepSeekBalanceMonitor.exe" >nul
if errorlevel 1 goto kill_done
set /a _waited+=1
if !_waited! gtr 10 goto kill_timeout
ping -n 2 127.0.0.1 >nul
goto wait_kill
:kill_timeout
echo [WARN] The running instance did not exit within ~10s.
echo        Close it from the tray and run this script again, otherwise the
echo        freshly built exe will refuse to start (single-instance lock).
endlocal
echo.
:kill_done
endlocal
echo.

:: Build via the .spec (single source of truth: icon, datas, version,
:: DPI manifest, onefile). Do NOT use ad-hoc CLI flags — they bypass the
:: manifest embedded by the spec.
:build
pyinstaller DeepSeekBalanceMonitor.spec --noconfirm --clean

if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Build failed.
    pause
    exit /b 1
)

echo.
echo ==============================================
echo   Build successful!  Launching...
echo ==============================================
start "" "dist\DeepSeekBalanceMonitor.exe"
exit /b 0
