"""
Cross-platform encrypted key-value store backed by SQLite + Fernet.
"""
import os
import sqlite3
from pathlib import Path

from cryptography.fernet import Fernet

from src.config import CONFIG_DIR, log

DB_PATH = CONFIG_DIR / "secure_settings.db"
KEY_PATH = CONFIG_DIR / ".keyfile"


def _get_fernet():
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    if KEY_PATH.exists():
        key = KEY_PATH.read_bytes()
    else:
        key = Fernet.generate_key()
        KEY_PATH.write_bytes(key)
    return Fernet(key)


def store_api_key(api_key: str):
    try:
        f = _get_fernet()
        encrypted = f.encrypt(api_key.encode("utf-8"))
        conn = sqlite3.connect(str(DB_PATH))
        conn.execute("CREATE TABLE IF NOT EXISTS secrets (key TEXT PRIMARY KEY, value BLOB)")
        conn.execute("INSERT OR REPLACE INTO secrets (key, value) VALUES (?, ?)",
                     ("api_key", encrypted))
        conn.commit()
        conn.close()
    except Exception as e:
        log(f"Failed to store API key: {e}")


def read_api_key() -> str | None:
    try:
        if not DB_PATH.exists():
            return None
        f = _get_fernet()
        conn = sqlite3.connect(str(DB_PATH))
        cur = conn.execute("SELECT value FROM secrets WHERE key = ?", ("api_key",))
        row = cur.fetchone()
        conn.close()
        if row:
            return f.decrypt(row[0]).decode("utf-8")
        return None
    except Exception as e:
        log(f"Failed to read API key: {e}")
        return None


def delete_api_key():
    try:
        if DB_PATH.exists():
            conn = sqlite3.connect(str(DB_PATH))
            conn.execute("DELETE FROM secrets WHERE key = ?", ("api_key",))
            conn.commit()
            conn.close()
    except Exception:
        pass
