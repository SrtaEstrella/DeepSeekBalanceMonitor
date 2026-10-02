"""
Shared constants and logging — imported by config, secure_settings, storage.
No dependencies on other src modules (leaf node).
"""
import sys
from pathlib import Path

APP_NAME = "DeepSeek Balance Monitor"
APP_ID   = "deepseek-balance-monitor"

if sys.platform == "darwin":
    CONFIG_DIR = Path.home() / "Library" / "Application Support" / APP_NAME
else:
    import os
    CONFIG_DIR = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / APP_NAME

CONFIG_FILE = CONFIG_DIR / "config.json"
LOG_FILE    = CONFIG_DIR / "app.log"
DB_FILE     = CONFIG_DIR / "balance_history.db"


def log(msg: str):
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        from datetime import datetime
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"[{ts}] {msg}\n")
    except Exception:
        pass


# ─── Single instance ──────────────────────────────────────────────
_INSTANCE_HANDLE = None


def acquire_single_instance(name: str = APP_ID) -> bool:
    """Claim the single-instance lock for this app.

    Returns True when this process owns it, False when another instance is
    already running (parity with the Rust Windows build's named mutex: a second
    tray fights the first over the SQLite file and the tray icon image).

    Windows uses a session-local named mutex; other platforms take an advisory
    file lock, which the OS drops when the process dies, so a crash cannot leave
    a stale lock behind. Any failure to create the lock counts as acquired —
    a platform quirk must never block startup. The handle is kept for the
    process lifetime (a released handle would release the lock with it).
    """
    global _INSTANCE_HANDLE
    if _INSTANCE_HANDLE is not None:
        return True

    if sys.platform == "win32":
        try:
            import ctypes
            ERROR_ALREADY_EXISTS = 183
            kernel32 = ctypes.windll.kernel32
            kernel32.CreateMutexW.restype = ctypes.c_void_p
            kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_wchar_p]
            kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
            handle = kernel32.CreateMutexW(None, 0, f"Local\\{name}")
            if not handle:
                return True
            if kernel32.GetLastError() == ERROR_ALREADY_EXISTS:
                kernel32.CloseHandle(handle)
                return False
            _INSTANCE_HANDLE = handle
            return True
        except Exception:
            return True

    try:
        import fcntl
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        fh = open(CONFIG_DIR / f"{name}.lock", "w")
        try:
            fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            fh.close()
            return False
        _INSTANCE_HANDLE = fh
        return True
    except Exception:
        return True
