"""
Balance history storage — SQLite-backed, for spend-rate / trend analysis.
"""
import csv
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


def export_all_csv(path: str) -> int:
    """Export all balance records to a CSV file. Returns row count."""
    try:
        conn = _connect()
        cur = conn.execute(
            "SELECT timestamp, currency, total, topped, granted, service_status "
            "FROM balance_history ORDER BY timestamp ASC"
        )
        count = 0
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["timestamp", "currency", "total", "topped", "granted", "service_status"])
            for r in cur:
                w.writerow(r)
                count += 1
        conn.close()
        return count
    except Exception as e:
        log(f"Failed to export CSV: {e}")
        return 0


def get_consumption_rate(hours=24):
    """Calculate average daily consumption from total balance.
    Finds all non-increasing sub-intervals, computes per-interval rate,
    averages them, and returns (daily_rate, hours_remaining) or None.
    Assumes one currency — first seen currency wins."""
    try:
        conn = _connect()
        # Pick currency: prefer one with most recent non-zero balance
        cur = conn.execute("""
            SELECT currency FROM balance_history 
            GROUP BY currency 
            ORDER BY MAX(timestamp) DESC, MAX(total) DESC 
            LIMIT 1
        """)
        row = cur.fetchone()
        if not row:
            conn.close()
            return None
        target_currency = row[0]

        # Use Python's datetime to handle local timezone correctly
        from datetime import timedelta
        cutoff = (datetime.now() - timedelta(hours=hours)).strftime("%Y-%m-%d %H:%M:%S")

        cur = conn.execute(
            "SELECT timestamp, currency, total "
            "FROM balance_history "
            "WHERE timestamp >= ? AND currency = ? "
            "ORDER BY timestamp ASC",
            (cutoff, target_currency),
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
                intervals.append((start_val, start_ts, prev_val, rows[i-1][0]))
                start_val = val
                start_ts = rows[i][0]
            prev_val = val
        intervals.append((start_val, start_ts, prev_val, rows[-1][0]))

        total_consumed = 0.0
        total_hours = 0.0
        for sv, st, ev, et in intervals:
            if ev >= sv:
                continue
            try:
                t1 = datetime.strptime(st, "%Y-%m-%d %H:%M:%S")
                t2 = datetime.strptime(et, "%Y-%m-%d %H:%M:%S")
                delta_h = (t2 - t1).total_seconds() / 3600
                if delta_h < 0.1:
                    continue
                total_consumed += (sv - ev)
                total_hours += delta_h
            except ValueError:
                continue

        if total_hours < 0.1 or total_consumed <= 0:
            return None

        daily_rate = (total_consumed / total_hours) * 24
        remaining = rows[-1][2]  # current total balance
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
