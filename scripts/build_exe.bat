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

:: Kill any running instance
echo [*] Stopping running instance (if any)...
taskkill /f /im DeepSeekBalanceMonitor.exe >nul 2>&1
echo.

:: Build via the .spec (single source of truth: icon, datas, version,
:: DPI manifest, onefile). Do NOT use ad-hoc CLI flags — they bypass the
:: manifest embedded by the spec.
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
