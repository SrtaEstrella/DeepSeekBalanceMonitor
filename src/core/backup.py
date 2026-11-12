"""Backup and restore for this build's own data directory.

A backup is a folder holding the four files that make the application what it
is: the configuration, the encrypted key store, the key file that opens it and
the history database. SQLite files are copied through SQLite's own backup API,
so a live WAL does not leave a half-written database behind.

A restore is deliberately not applied while the application runs: the request
writes `.restore-pending`, and the next start swaps the files in before the
database or the configuration is opened. The files being replaced are kept
beside them as `.before-restore-<stamp>`.
"""
import json
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

from src.core.paths import CONFIG_DIR, CONFIG_FILE, DB_FILE, log

PENDING = CONFIG_DIR / ".restore-pending"
BACKUP_DIR = CONFIG_DIR / "backups"


def _copy_sqlite(source: Path, target: Path) -> None:
    src = sqlite3.connect(str(source))
    dst = sqlite3.connect(str(target))
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()


def _copy_file(source: Path, target: Path) -> None:
    if source.name.endswith(".db"):
        _copy_sqlite(source, target)
    else:
        shutil.copy2(source, target)


def _files() -> list:
    from src.core.secure_settings import DB_PATH, KEY_PATH
    return [CONFIG_FILE, DB_PATH, KEY_PATH, DB_FILE]


def backup_now() -> Path:
    """Writes one timestamped backup folder and returns it."""
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    target = BACKUP_DIR / stamp
    index = 1
    while target.exists():
        target = BACKUP_DIR / f"{stamp}-{index}"
        index += 1
    target.mkdir(parents=True)
    for source in _files():
        if source.exists():
            _copy_file(source, target / source.name)
    log(f"Backup written to {target}")
    return target


def request_restore(source) -> None:
    """Marks a backup folder to be applied on the next start."""
    src = Path(source)
    if not (src / CONFIG_FILE.name).exists() or not (src / DB_FILE.name).exists():
        raise ValueError("not a backup folder: config.json and balance_history.db are required")
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    PENDING.write_text(json.dumps({"source": str(src.resolve())}), encoding="utf-8")


def apply_pending_restore() -> bool:
    """Applies a pending restore; called before the database is opened."""
    if not PENDING.exists():
        return False
    try:
        payload = json.loads(PENDING.read_text(encoding="utf-8"))
        source = Path(payload.get("source", ""))
        if not source.is_dir():
            raise ValueError("the backup folder is gone")

        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        keep = CONFIG_DIR / f".before-restore-{stamp}"
        keep.mkdir(parents=True, exist_ok=True)
        for target in _files():
            if target.exists():
                _copy_file(target, keep / target.name)
            source_file = source / target.name
            if not source_file.exists():
                continue
            # A WAL left by the file being replaced would be replayed over the
            # restored database; the backup is a clean single file.
            for suffix in ("-wal", "-shm"):
                side = Path(str(target) + suffix)
                if side.exists():
                    side.unlink()
            _copy_file(source_file, target)

        PENDING.unlink()
        log(f"Restored from {source}; previous files kept in {keep}")
        return True
    except Exception as e:
        log(f"Restore failed: {e}")
        try:
            PENDING.unlink()
        except Exception:
            pass
        return False
