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

:: Build the single-file executable
echo [*] Building executable (this may take a minute)...
echo.

pyinstaller ^
    --onefile ^
    --windowed ^
    --noconsole ^
    --name "DeepSeekBalanceMonitor" ^
    --icon assets/app.ico ^
    --paths src ^
    --add-data "assets/app.ico;." ^
    --version-file version_info.txt ^
    --clean ^
    main.py

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
