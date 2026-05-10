"""
Balance history storage — SQLite-backed, for spend-rate / trend analysis.
"""
import sqlite3
from datetime import datetime

from src.config import DB_FILE, CONFIG_DIR, log


def _connect():
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_FILE))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS balance_history (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp       TEXT    NOT NULL,
            currency        TEXT    NOT NULL,
            total           REAL    NOT NULL,
            topped          REAL    NOT NULL,
            granted         REAL    NOT NULL,
            service_status  TEXT
        )
    """)
    # Migrate: add column if missing from older DB
    try:
        conn.execute("ALTER TABLE balance_history ADD COLUMN service_status TEXT")
    except sqlite3.OperationalError:
        pass
    conn.commit()
    return conn


def save_balance_record(currency: str, total: float, topped: float, granted: float,
                        service_status: str | None = None):
    """Insert one balance record. Called after each successful balance check."""
    try:
        conn = _connect()
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn.execute(
            "INSERT INTO balance_history (timestamp, currency, total, topped, granted, service_status) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (ts, currency, total, topped, granted, service_status),
        )
        conn.commit()
        conn.close()
    except Exception as e:
        log(f"Failed to save balance record: {e}")


def get_balance_history(days: int = 30):
    """Return the last N days of balance records as a list of dicts."""
    try:
        conn = _connect()
        cur = conn.execute(
            "SELECT timestamp, currency, total, topped, granted "
            "FROM balance_history "
            "WHERE timestamp >= datetime('now', ?) "
            "ORDER BY timestamp ASC",
            (f"-{days} days",),
        )
        rows = [
            {"timestamp": r[0], "currency": r[1], "total": r[2],
             "topped": r[3], "granted": r[4]}
            for r in cur.fetchall()
        ]
        conn.close()
        return rows
    except Exception as e:
        log(f"Failed to read balance history: {e}")
        return []


def get_history_page(limit: int = 100, offset: int = 0):
    """Return one page of balance records, newest first."""
    try:
        conn = _connect()
        cur = conn.execute(
            "SELECT timestamp, currency, total, topped, granted, service_status "
            "FROM balance_history "
            "ORDER BY timestamp DESC "
            "LIMIT ? OFFSET ?",
            (limit, offset),
        )
        rows = [
            {"timestamp": r[0], "currency": r[1], "total": r[2],
             "topped": r[3], "granted": r[4], "service_status": r[5]}
            for r in cur.fetchall()
        ]
        conn.close()
        return rows
    except Exception as e:
        log(f"Failed to read history page: {e}")
        return []


def get_consumption_rate(days=7):
    """Calculate average daily consumption from topped-up balance.
    Finds all non-increasing sub-intervals, computes per-interval rate,
    averages them, and returns (daily_rate, hours_remaining) or None.
    Assumes one currency — first seen currency wins."""
    try:
        conn = _connect()
        cur = conn.execute(
            "SELECT timestamp, currency, topped "
            "FROM balance_history "
            "WHERE timestamp >= datetime('now', ?) "
            "ORDER BY timestamp ASC",
            (f"-{days} days",),
        )
        rows = cur.fetchall()
        conn.close()
        if len(rows) < 2:
            return None

        intervals = []
        start_val = rows[0][2]
        start_ts = rows[0][0]
        currency = rows[0][1]
        prev_val = start_val

        for i in range(1, len(rows)):
            val = rows[i][2]
            if val > prev_val:
                # Top-up — close current interval
                intervals.append((start_val, start_ts, prev_val, rows[i-1][0]))
                start_val = val
                start_ts = rows[i][0]
            prev_val = val
        # Last interval
        intervals.append((start_val, start_ts, prev_val, rows[-1][0]))

        rates = []
        for sv, st, ev, et in intervals:
            if ev >= sv:
                continue
            try:
                t1 = datetime.strptime(st, "%Y-%m-%d %H:%M:%S")
                t2 = datetime.strptime(et, "%Y-%m-%d %H:%M:%S")
                delta_h = (t2 - t1).total_seconds() / 3600
                if delta_h < 0.1:
                    continue
                rate_24h = (sv - ev) / delta_h * 24
                rates.append(rate_24h)
            except ValueError:
                continue

        if not rates:
            return None

        daily_rate = sum(rates) / len(rates)
        if daily_rate <= 0:
            return None

        remaining = rows[-1][2]  # current topped balance
        hours_left = remaining / daily_rate * 24
        return daily_rate, hours_left, currency
    except Exception as e:
        log(f"Failed to compute consumption rate: {e}")
        return None


def prune_old_data(retention_days: int):
    """Delete balance records and log entries older than retention_days.
    Called once on startup."""
    try:
        conn = _connect()
        conn.execute(
            "DELETE FROM balance_history "
            "WHERE timestamp < datetime('now', ?)",
            (f"-{retention_days} days",),
        )
        conn.commit()
        conn.execute("VACUUM")
        conn.close()
        log(f"Pruned balance history older than {retention_days} days")
    except Exception as e:
        log(f"Failed to prune balance history: {e}")

    try:
        from src.config import LOG_FILE
        if not LOG_FILE.exists():
            return
        cutoff = datetime.now().timestamp() - retention_days * 86400
        lines = LOG_FILE.read_text(encoding="utf-8").splitlines()
        kept = []
        for line in lines:
            try:
                ts_str = line[1:20]  # "[YYYY-MM-DD HH:MM:SS]"
                ts = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S").timestamp()
                if ts >= cutoff:
                    kept.append(line)
            except (ValueError, IndexError):
                kept.append(line)
        LOG_FILE.write_text("\n".join(kept) + "\n", encoding="utf-8")
        log(f"Pruned log entries older than {retention_days} days")
    except Exception as e:
        log(f"Failed to prune log file: {e}")
