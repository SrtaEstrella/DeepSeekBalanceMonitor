"""
Balance history storage — SQLite-backed, for spend-rate / trend analysis.
"""
import csv
import sqlite3
from datetime import datetime

from src.core.paths import DB_FILE, CONFIG_DIR, LOG_FILE, log
from src.core.config import load_config
from src.platforms.registry import billing_col as BILLING_COL_MAP_REF


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
            service_status  TEXT,
            api_id          TEXT
        )
    """)
    # Migrate: add columns if missing from older DB
    for col in ("service_status TEXT", "api_id TEXT"):
        try:
            conn.execute(f"ALTER TABLE balance_history ADD COLUMN {col}")
        except sqlite3.OperationalError:
            pass
    # migrate legacy rows with NULL api_id to preferred_api_id if available
    try:
        cur = conn.execute("SELECT COUNT(*) FROM balance_history WHERE api_id IS NULL OR api_id=''")
        cnt = cur.fetchone()[0]
        if cnt > 0:
            cfg = load_config()
            pref = cfg.get("preferred_api_id") or (cfg.get("apis") or [{}])[0].get("id") if cfg.get("apis") else None
            if pref:
                conn.execute("UPDATE balance_history SET api_id=? WHERE api_id IS NULL OR api_id=''", (pref,))
                conn.commit()
    except Exception:
        pass
    conn.commit()
    return conn


def save_balance_record(currency: str, total: float, topped: float, granted: float,
                        service_status: str | None = None, api_id: str | None = None):
    """Insert one balance record. Called after each successful balance check."""
    try:
        conn = _connect()
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        # resolve api_id if not given
        if not api_id:
            cfg = load_config()
            api_id = cfg.get("preferred_api_id", "")
        conn.execute(
            "INSERT INTO balance_history (timestamp, currency, total, topped, granted, service_status, api_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (ts, currency, total, topped, granted, service_status, api_id or ""),
        )
        conn.commit()
        conn.close()
    except Exception as e:
        log(f"Failed to save balance record: {e}")


def get_refined_remaining_series(api_id: str, target: str = "monthly",
                                 days: int = 30) -> tuple:
    """Refined REMAINING% (100 - usage) at every observation in a window —
    the interpolation extends to historical data, not just the latest point.

    Model works on the usage series (positive deltas = consumption) and
    returns REMAINING for display consistency: real_remaining =
    100 - (usage_int + 0.5 - frac). Internally it warms up over a longer
    window (90 days) so the front of the requested range already carries
    established rate/prefix (no artificial .5 plateaus); only points within
    the requested `days` are returned.

    Returns (timestamps, remaining_vals).
    """
    from datetime import datetime, timedelta
    try:
        from src.core.config import load_config
        api = next((a for a in (load_config().get("apis") or [])
                    if a.get("id") == api_id), None)
        from src.platforms.registry import get_platform
        pmeta = get_platform((api or {}).get("platform", "")) if api else None
        pools = (pmeta.window_pools if pmeta else None) or {}
        fpool = pools.get("5h")
        if not fpool or not pools.get(target):
            return [], []
        col_map = {"5h": "h5_percent", "weekly": "weekly_percent", "monthly": "monthly_percent"}
        tcol = col_map.get(target, "monthly_percent")
        model_days = max(90, days)   # warm-up window for rate/prefix
        conn = _connect_package()
        cutoff = (datetime.now() - timedelta(days=model_days)).strftime("%Y-%m-%d %H:%M:%S")
        out_cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
        cur = conn.execute(
            f"SELECT timestamp, h5_percent, {tcol} FROM package_history "
            f"WHERE api_id=? AND timestamp>=? ORDER BY timestamp ASC",
            (api_id or "", cutoff))
        rows = cur.fetchall()
        conn.close()
        if len(rows) < 4:
            return [], []

        tidx = 2

        def _dt(a, b):
            try:
                from datetime import datetime as dt
                return (dt.strptime(b, "%Y-%m-%d %H:%M:%S") -
                        dt.strptime(a, "%Y-%m-%d %H:%M:%S")).total_seconds() / 3600.0
            except Exception:
                return 0.0

        ts_out, v_out = [], []
        # CAUSAL refinement: every point uses only data up to its own
        # timestamp (prefix accumulated per target period; rate from the most
        # recent segments BEFORE the point). New online rows never change
        # historical values.
        from collections import deque
        spend_cum = 0.0      # 5h spend $ since period start (prefix, causal)
        rise_cum = 0.0       # coarse rise % since period start (prefix)
        prev_ts = None
        rate_q = deque(maxlen=4)
        u_cont = None        # continuous usage estimate (never quantized)
        drift_check = 0
        for i, r in enumerate(rows):
            ts, h5, obs = r[0], r[1], r[2]
            if obs is None:
                prev_ts = ts
                continue
            if i > 0:
                p_obs = rows[i-1][tidx]
                if p_obs is not None and obs < p_obs:
                    # period reset: re-anchor and reset prefix
                    spend_cum = 0.0
                    rise_cum = 0.0
                    rate_q.clear()
                    u_cont = obs + 0.5
                    prev_ts = ts
                    drift_check = 0
                    continue
                a5, b5 = rows[i-1][1], h5
                d_usd = 0.0
                if a5 is not None and b5 is not None and b5 > a5:
                    d_usd = (b5 - a5) / 100.0 * fpool
                    spend_cum += d_usd
                if p_obs is not None and obs > p_obs:
                    rise_cum += obs - p_obs
                avg_per_coarse = (spend_cum / rise_cum) if (rise_cum > 0 and spend_cum > 0) else None
                if u_cont is None:
                    u_cont = obs + 0.5
                # only REAL 5h spend in this interval advances the estimate
                # (consumption is intermittent — never smear a rate over
                # every row, which overshoots the observed total)
                if avg_per_coarse and d_usd > 0:
                    u_cont += d_usd / avg_per_coarse
                # band clamp: only the LOWER band is enforced (never let the
                # estimate run below obs-0.5). No upper clamp — the line keeps
                # falling with real consumption; a plateau can only mean
                # genuinely zero spend.
                if u_cont < obs - 0.5:
                    u_cont = obs - 0.5
            else:
                u_cont = obs + 0.5
            prev_ts = ts
            if ts < out_cutoff:
                continue      # only the requested range is surfaced
            ts_out.append(ts)
            # REMAINING = 100 - continuous usage (smooth line)
            v_out.append(round(max(0.0, min(100.0, 100 - u_cont)), 2))
        return ts_out, v_out
    except Exception as e:
        log(f"Refined remaining series failed: {e}")
        return [], []


def get_refined_remaining(api_id: str, target: str = "monthly") -> float | None:
    """Latest refined remaining% — thin wrapper over the causal series
    (last point). See get_refined_remaining_series for the model."""
    try:
        ts, vs = get_refined_remaining_series(api_id, target=target, days=90)
        return vs[-1] if vs else None
    except Exception as e:
        log(f"Refined remaining failed: {e}")
        return None


def get_refined_daily_consumption(api_id: str, days: int = 30,
                                  target: str = "monthly") -> tuple:
    """Model coarse-window daily consumption with finer-window shape.

    OCGo windows quantize usage to whole percent steps; a 5h rolling window
    samples ~10min and therefore carries far finer consumption structure than
    weekly (1% steps) or monthly (same). This refines the TARGET window's
    daily totals by distributing its observed rise with the SHAPE of a finer
    window's positive deltas (relative weights).

    Correctness rules:
      1) reset edges (target-window usage DROPS) split the series into
         periods; each period is anchored independently, so a quota reset
         never lets pre-reset consumption contaminate the post-reset shape,
         and vice versa.
      2) per-period anchoring: the modeled sum inside a period equals that
         period's observed target rise → rounding the modeled daily values
         back to integers reproduces the coarse observation (self-consistent).
      Fallback: L1 5h shape (>=2 segments) -> L2 weekly shape -> L3 raw steps.

    Returns (dates[days], vals[days], source) source='5h'|'weekly'|'raw'.
    """
    from collections import defaultdict
    from datetime import datetime, timedelta
    try:
        col_map = {"5h": "h5_percent", "weekly": "weekly_percent", "monthly": "monthly_percent"}
        tcol = col_map.get(target, "monthly_percent")
        conn = _connect_package()
        cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
        cur = conn.execute(
            "SELECT timestamp, h5_percent, weekly_percent, monthly_percent "
            "FROM package_history WHERE api_id=? AND timestamp>=? ORDER BY timestamp ASC",
            (api_id or "", cutoff))
        rows = cur.fetchall()
        conn.close()
    except Exception as e:
        log(f"Refined consumption query failed: {e}")
        rows = []

    tidx = {"h5": 1, "weekly": 2, "monthly": 3}[target]

    def _periods(rows, tidx):
        """Split rows into target-window periods cut at usage DROP edges
        (quota resets). Returns list of row-slices."""
        per = []
        start = 0
        for i in range(1, len(rows)):
            a, b = rows[i-1][tidx], rows[i][tidx]
            if a is not None and b is not None and b < a:
                per.append(rows[start:i])
                start = i
        per.append(rows[start:])
        return per

    def _weight_and_count(col_idx, rows):
        w = defaultdict(float)
        n = 0
        for i in range(1, len(rows)):
            a, b = rows[i-1][col_idx], rows[i][col_idx]
            if a is None or b is None:
                continue
            d = b - a
            if d <= 0:
                continue
            n += 1
            w[rows[i][0][:10]] += d
        return w, n

    def _rise(col_idx, rows):
        t = 0.0
        for i in range(1, len(rows)):
            a, b = rows[i-1][col_idx], rows[i][col_idx]
            if a is not None and b is not None and b > a:
                t += b - a
        return t

    # pick the shape source once for the whole series
    w5, n5 = _weight_and_count(1, rows)
    ww, nw = _weight_and_count(2, rows)
    if n5 >= 2:
        source, s_idx = "5h", 1
    elif nw >= 2:
        source, s_idx = "weekly", 2
    else:
        source, s_idx = "raw", None

    daily = defaultdict(float)
    if source == "raw":
        for i in range(1, len(rows)):
            a, b = rows[i-1][3], rows[i][3]
            if a is not None and b is not None and b > a:
                daily[rows[i][0][:10]] += b - a
    else:
        # per-period anchoring: each reset-bounded period anchors independently
        for period in _periods(rows, tidx):
            w, n = _weight_and_count(s_idx, period)
            rise = _rise(tidx, period)
            tot = sum(w.values())
            if rise > 0 and tot > 0:
                for k, v in w.items():
                    daily[k] += v / tot * rise

    dates = []
    vals = []
    d0 = datetime.now() - timedelta(days=days - 1)
    for i in range(days):
        day = (d0 + timedelta(days=i)).strftime("%Y-%m-%d")
        dates.append(day[5:10])
        vals.append(round(daily.get(day, 0.0), 2))
    return dates, vals, source


def get_refined_hourly_distribution(api_id: str, days: int = 7) -> tuple:
    """Hourly consumption distribution refined by the finest window's shape.

    Bins positive deltas (consumption segments) of the 5h window by hour of
    day; falls back to weekly deltas when 5h is sparse. No anchoring needed —
    this is a shape distribution, expressed in the source window's percent
    units. Returns (labels[24], vals[24], source)."""
    from collections import defaultdict
    from datetime import datetime, timedelta
    try:
        conn = _connect_package()
        cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
        cur = conn.execute(
            "SELECT timestamp, h5_percent, weekly_percent "
            "FROM package_history WHERE api_id=? AND timestamp>=? ORDER BY timestamp ASC",
            (api_id or "", cutoff))
        rows = cur.fetchall()
        conn.close()
    except Exception as e:
        log(f"Refined hourly query failed: {e}")
        rows = []

    def _hour_weights(rows, col_idx, pool_usd):
        """Hour-of-day consumption (percent of the source pool), time-prorated
        across hour boundaries: a segment (t0->t1, d%) is split by the minutes
        it occupies in each hour, so the distribution is continuous
        (fractional), never integer buckets."""
        h = defaultdict(float)
        n = 0
        for i in range(1, len(rows)):
            a, b = rows[i-1][col_idx], rows[i][col_idx]
            if a is None or b is None:
                continue
            d = b - a
            if d <= 0:
                continue
            n += 1
            d_usd = d / 100.0 * pool_usd
            try:
                t0 = datetime.strptime(rows[i-1][0], "%Y-%m-%d %H:%M:%S")
                t1 = datetime.strptime(rows[i][0], "%Y-%m-%d %H:%M:%S")
            except Exception:
                h[int(rows[i][0][11:13])] += d_usd
                continue
            span = (t1 - t0).total_seconds()
            if span <= 0:
                h[int(t1.hour)] += d_usd
                continue
            cur = t0
            while cur < t1:
                nxt = min(t1, (cur.replace(minute=0, second=0, microsecond=0)
                               + timedelta(hours=1)))
                frac = (nxt - cur).total_seconds() / span
                h[cur.hour] += d_usd * frac
                cur = nxt
        return h, n

    h5, n5 = _hour_weights(rows, 1, 12.0)
    hw, nw = _hour_weights(rows, 2, 30.0)
    if n5 >= 2:
        h, source = h5, "5h"
    elif nw >= 2:
        h, source = hw, "weekly"
    else:
        h, source = {}, "raw"
    labels = [f"{x:02d}:00" for x in range(24)]
    vals = [round(h.get(x, 0.0), 2) for x in range(24)]
    return labels, vals, source


def get_today_spend(api_id: str, mode: str = "payg", billing_period: str | None = None) -> float:
    """Single-day consumption for today, in CNY (payg) or percent-points (package).
    Busy-period deltas only (same aggregation as the daily-usage charts)."""
    try:
        from datetime import datetime
        cutoff = datetime.now().strftime("%Y-%m-%d 00:00:00")
        if mode == "package":
            col_map = {"5h": "h5_percent", "weekly": "weekly_percent", "monthly": "monthly_percent"}
            col = col_map.get(billing_period or "", "monthly_percent")
            conn = _connect_package()
            cur = conn.execute(
                f"SELECT timestamp, {col} FROM package_history "
                f"WHERE api_id=? AND timestamp >= ? AND {col} IS NOT NULL ORDER BY timestamp ASC",
                (api_id or "", cutoff))
            rows = cur.fetchall()
            conn.close()
            spend = 0.0
            for i in range(1, len(rows)):
                rise = (rows[i][1] or 0) - (rows[i-1][1] or 0)
                if rise > 0:
                    spend += rise
        else:
            conn = _connect()
            cur = conn.execute(
                "SELECT timestamp, topped FROM balance_history "
                "WHERE api_id=? AND timestamp >= ? ORDER BY timestamp ASC",
                (api_id or "", cutoff))
            rows = cur.fetchall()
            conn.close()
            spend = 0.0
            for i in range(1, len(rows)):
                drop = rows[i-1][1] - rows[i][1]
                if drop > 0:
                    spend += drop
        return round(spend, 2)
    except Exception as e:
        log(f"Failed to compute today spend: {e}")
        return 0.0


def get_history_page(limit: int = 100, offset: int = 0, api_id: str | None = None):
    """Return one page of balance records, newest first. Filter by api_id if given."""
    try:
        conn = _connect()
        if api_id:
            cur = conn.execute(
                "SELECT timestamp, currency, total, topped, granted, service_status, api_id "
                "FROM balance_history WHERE api_id=? "
                "ORDER BY timestamp DESC LIMIT ? OFFSET ?",
                (api_id, limit, offset),
            )
        else:
            cur = conn.execute(
                "SELECT timestamp, currency, total, topped, granted, service_status, api_id "
                "FROM balance_history "
                "ORDER BY timestamp DESC LIMIT ? OFFSET ?",
                (limit, offset),
            )
        rows = [
            {"timestamp": r[0], "currency": r[1], "total": r[2],
             "topped": r[3], "granted": r[4], "service_status": r[5], "api_id": r[6] if len(r) > 6 else ""}
            for r in cur.fetchall()
        ]
        conn.close()
        return rows
    except Exception as e:
        log(f"Failed to read history page: {e}")
        return []


def get_history_by_date(date_str: str, api_id: str | None = None):
    """Return all balance records for a specific date (YYYY-MM-DD). Filter by api_id if given."""
    try:
        conn = _connect()
        if api_id:
            cur = conn.execute(
                "SELECT timestamp, currency, total, topped, granted, service_status, api_id "
                "FROM balance_history WHERE timestamp LIKE ? AND api_id=? ORDER BY timestamp ASC",
                (f"{date_str}%", api_id),
            )
        else:
            cur = conn.execute(
                "SELECT timestamp, currency, total, topped, granted, service_status, api_id "
                "FROM balance_history WHERE timestamp LIKE ? ORDER BY timestamp ASC",
                (f"{date_str}%",),
            )
        rows = [
            {"timestamp": r[0], "currency": r[1], "total": r[2],
             "topped": r[3], "granted": r[4], "service_status": r[5], "api_id": r[6] if len(r) > 6 else ""}
            for r in cur.fetchall()
        ]
        conn.close()
        return rows
    except Exception as e:
        log(f"Failed to read history by date: {e}")
        return []


def export_all_csv(path: str, api_id: str | None = None) -> int:
    """Export balance records to CSV. Filter by api_id if given."""
    try:
        conn = _connect()
        if api_id:
            cur = conn.execute(
                "SELECT timestamp, currency, total, topped, granted, service_status, api_id FROM balance_history WHERE api_id=? ORDER BY timestamp ASC", (api_id,))
        else:
            cur = conn.execute(
                "SELECT timestamp, currency, total, topped, granted, service_status, api_id FROM balance_history ORDER BY timestamp ASC"
            )
        count = 0
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["timestamp", "currency", "total", "topped", "granted", "service_status", "api_id"])
            for r in cur:
                w.writerow(r)
                count += 1
        conn.close()
        return count
    except Exception as e:
        log(f"Failed to export CSV: {e}")
        return 0


def export_package_csv(path: str, api_id: str | None = None) -> int:
    """Export package quota records to CSV. Filter by api_id if given."""
    try:
        conn = _connect_package()
        if api_id:
            cur = conn.execute(
                "SELECT timestamp, h5_percent, h5_reset, weekly_percent, weekly_reset, monthly_percent, monthly_reset, service_status FROM package_history WHERE api_id=? ORDER BY timestamp ASC", (api_id,))
        else:
            cur = conn.execute(
                "SELECT timestamp, h5_percent, h5_reset, weekly_percent, weekly_reset, monthly_percent, monthly_reset, service_status FROM package_history ORDER BY timestamp ASC"
            )
        count = 0
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["timestamp", "h5_used%", "h5_reset_sec", "weekly_used%", "weekly_reset_sec",
                        "monthly_used%", "monthly_reset_sec", "service_status"])
            for r in cur:
                w.writerow(r)
                count += 1
        conn.close()
        return count
    except Exception as e:
        log(f"Failed to export package CSV: {e}")
        return 0


def get_consumption_rate(days=7, api_id: str | None = None, billing_period: str | None = None):
    """Busy-hour weighted hourly consumption rate. Filter by api_id if given.
    Pass billing_period ("5h"/"weekly"/"monthly") for package-mode quota rate."""
    result = _get_consumption_rate_for_days(days, _interval_min=None, api_id=api_id, billing_period=billing_period)
    if result or days != 7:
        return result
    retention_days = load_config().get("retention_days", 180)
    fallback_days = max(days, retention_days)
    if fallback_days <= days:
        return result
    return _get_consumption_rate_for_days(fallback_days, _interval_min=None, api_id=api_id, billing_period=billing_period)


def _get_consumption_rate_for_days(days=7, _interval_min=None, api_id: str | None = None, billing_period: str | None = None):
    """Busy-hour slicing: split on top-ups, long idle gaps, and long flat periods.
    Only "busy" intervals contribute to the weighted hourly rate. Filter by api_id if given.
    If billing_period is set, read package_history usage%% instead (negated so that
    usage rises count as consumption and quota resets act as top-ups)."""
    try:
        if billing_period:
            col = BILLING_COL_MAP_REF(billing_period)
            conn = _connect_package()
            cur = conn.execute(
                f"SELECT timestamp, '{col}', {col} FROM package_history WHERE timestamp >= datetime('now', ?) AND api_id=? AND {col} IS NOT NULL ORDER BY timestamp ASC",
                (f"-{days} days", api_id or ""),
            )
            raw_rows = cur.fetchall()
            conn.close()
            if len(raw_rows) < 2:
                return None
            # convert usage%% to remaining%% (consumption = remaining dropping)
            # NOTE: percent values are integer-quantized (1%% steps), so busy-interval
            # slicing amplifies quantization noise into huge %/h rates. Use a robust
            # reset-safe estimate instead: sum of positive drops / total calendar hours.
            parsed = [(datetime.strptime(r[0], "%Y-%m-%d %H:%M:%S"), r[1], 100.0 - (r[2] or 0)) for r in raw_rows]
            currency = "%"

            total_drop = 0.0
            for i in range(1, len(parsed)):
                d = parsed[i - 1][2] - parsed[i][2]
                if d > 0:
                    total_drop += d
            hours_total = (parsed[-1][0] - parsed[0][0]).total_seconds() / 3600
            if hours_total <= 0 or total_drop <= 0:
                return None
            avg_hourly = total_drop / hours_total
            latest_remaining = parsed[-1][2]
            busy_hours = max(0.0, latest_remaining) / avg_hourly
            return avg_hourly, busy_hours, currency

        conn = _connect()
        if api_id:
            cur = conn.execute(
                "SELECT timestamp, currency, topped FROM balance_history WHERE timestamp >= datetime('now', ?) AND api_id=? ORDER BY timestamp ASC",
                (f"-{days} days", api_id),
            )
        else:
            cur = conn.execute(
                "SELECT timestamp, currency, topped FROM balance_history WHERE timestamp >= datetime('now', ?) ORDER BY timestamp ASC",
                (f"-{days} days",),
            )
        rows = cur.fetchall()
        conn.close()
        if len(rows) < 2:
            return None

        parsed = [(datetime.strptime(r[0], "%Y-%m-%d %H:%M:%S"), r[1], r[2]) for r in rows]
        currency = parsed[0][1]
        if _interval_min is None:
            _interval_min = int(load_config().get("interval_minutes", 10))
        m_sec = max(30, 2 * _interval_min) * 60

        intervals = _slice_busy_intervals(parsed, m_sec)

        total_weight = 0.0
        weighted_sum = 0.0
        for sv, st, ev, et in intervals:
            if ev >= sv:
                continue
            delta_h = (et - st).total_seconds() / 3600
            if delta_h < 0.01:
                continue
            hourly_rate = (sv - ev) / delta_h
            weighted_sum += hourly_rate * delta_h
            total_weight += delta_h

        if total_weight == 0:
            return None
        avg_hourly = weighted_sum / total_weight
        if avg_hourly <= 0:
            return None
        busy_hours = parsed[-1][2] / avg_hourly
        return avg_hourly, busy_hours, currency
    except Exception as e:
        log(f"Failed to compute consumption rate: {e}")
        return None


def _slice_busy_intervals(parsed, m_sec):
    """Pure function: split parsed [(ts,curr,val)] into busy intervals."""
    intervals = []
    seg_start_val = parsed[0][2]
    seg_start_ts = parsed[0][0]
    prev_val = seg_start_val
    prev_ts = seg_start_ts
    eq_start_idx = None

    def _flush_eq_as_interval(end_idx):
        """If the equal run ending at end_idx is long, flush segment before it."""
        nonlocal seg_start_val, seg_start_ts
        eq_dur = (parsed[end_idx][0] - parsed[eq_start_idx][0]).total_seconds()
        if eq_dur > m_sec and parsed[eq_start_idx][0] > seg_start_ts:
            intervals.append((seg_start_val, seg_start_ts,
                              parsed[eq_start_idx][2], parsed[eq_start_idx][0]))
            return True
        return False

    for i in range(1, len(parsed)):
        curr_ts, _, curr_val = parsed[i]
        gap_sec = (curr_ts - prev_ts).total_seconds()

        if curr_val > prev_val:  # Rule 1: top-up
            if eq_start_idx is not None:
                if _flush_eq_as_interval(i - 1):
                    seg_start_val = curr_val
                    seg_start_ts = curr_ts
                    prev_val = curr_val
                    prev_ts = curr_ts
                    eq_start_idx = None
                    continue
                eq_start_idx = None
            if prev_ts > seg_start_ts:
                intervals.append((seg_start_val, seg_start_ts, prev_val, prev_ts))
            seg_start_val = curr_val
            seg_start_ts = curr_ts

        elif curr_val < prev_val:  # consumption drop
            if gap_sec > m_sec:  # Rule 2: long idle gap
                if eq_start_idx is not None:
                    if _flush_eq_as_interval(i - 1):
                        seg_start_val = prev_val
                        seg_start_ts = prev_ts
                    eq_start_idx = None
                if prev_ts > seg_start_ts:
                    intervals.append((seg_start_val, seg_start_ts, prev_val, prev_ts))
                seg_start_val = curr_val
                seg_start_ts = curr_ts
            else:  # normal consumption, may follow short equal run
                if eq_start_idx is not None:
                    eq_dur = (prev_ts - parsed[eq_start_idx][0]).total_seconds()
                    if eq_dur > m_sec:  # Rule 3: long flat discard
                        if parsed[eq_start_idx][0] > seg_start_ts:
                            intervals.append((seg_start_val, seg_start_ts,
                                              parsed[eq_start_idx][2], parsed[eq_start_idx][0]))
                        seg_start_val = curr_val
                        seg_start_ts = curr_ts
                        prev_val = curr_val
                        prev_ts = curr_ts
                        eq_start_idx = None
                        continue
                    eq_start_idx = None
        else:  # curr_val == prev_val — Rule 3: track equal run
            if eq_start_idx is None:
                eq_start_idx = i - 1

        prev_val = curr_val
        prev_ts = curr_ts

    if eq_start_idx is not None:
        eq_dur = (parsed[-1][0] - parsed[eq_start_idx][0]).total_seconds()
        if eq_dur > m_sec:
            if parsed[eq_start_idx][0] > seg_start_ts:
                intervals.append((seg_start_val, seg_start_ts,
                                  parsed[eq_start_idx][2], parsed[eq_start_idx][0]))
            seg_start_ts = parsed[-1][0]

    if parsed[-1][0] > seg_start_ts:
        intervals.append((seg_start_val, seg_start_ts, prev_val, parsed[-1][0]))
    return intervals


def _connect_package():
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_FILE))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS package_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            api_id TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            h5_percent REAL,
            h5_reset INTEGER,
            weekly_percent REAL,
            weekly_reset INTEGER,
            monthly_percent REAL,
            monthly_reset INTEGER,
            service_status TEXT
        )
    """)
    # migrate: add service_status column if missing from older DB
    try:
        conn.execute("ALTER TABLE package_history ADD COLUMN service_status TEXT")
    except sqlite3.OperationalError:
        pass
    conn.commit()
    return conn

def save_package_record(api_id: str, h5_percent: float | None, h5_reset: int | None, weekly_percent: float | None, weekly_reset: int | None, monthly_percent: float | None, monthly_reset: int | None, service_status: str | None = None):
    try:
        conn = _connect_package()
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn.execute(
            "INSERT INTO package_history (api_id, timestamp, h5_percent, h5_reset, weekly_percent, weekly_reset, monthly_percent, monthly_reset, service_status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (api_id, ts, h5_percent, h5_reset, weekly_percent, weekly_reset, monthly_percent, monthly_reset, service_status),
        )
        conn.commit()
        conn.close()
    except Exception as e:
        log(f"Failed to save package record: {e}")

def get_package_history_page(limit: int = 100, offset: int = 0, api_id: str | None = None):
    try:
        conn = _connect_package()
        if api_id:
            cur = conn.execute("SELECT timestamp, h5_percent, h5_reset, weekly_percent, weekly_reset, monthly_percent, monthly_reset, service_status FROM package_history WHERE api_id=? ORDER BY timestamp DESC LIMIT ? OFFSET ?", (api_id, limit, offset))
        else:
            cur = conn.execute("SELECT timestamp, h5_percent, h5_reset, weekly_percent, weekly_reset, monthly_percent, monthly_reset, service_status FROM package_history ORDER BY timestamp DESC LIMIT ? OFFSET ?", (limit, offset))
        rows = [{"timestamp": r[0], "h5_percent": r[1], "h5_reset": r[2], "weekly_percent": r[3], "weekly_reset": r[4], "monthly_percent": r[5], "monthly_reset": r[6], "service_status": r[7] if len(r) > 7 else None} for r in cur.fetchall()]
        conn.close()
        return rows
    except Exception as e:
        log(f"Failed to read package history: {e}")
        return []

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
        conn.close()
        log(f"Pruned balance history older than {retention_days} days")
    except Exception as e:
        log(f"Failed to prune balance history: {e}")

    try:
        conn = _connect_package()
        conn.execute("DELETE FROM package_history WHERE timestamp < datetime('now', ?)", (f"-{retention_days} days",))
        conn.commit()
        conn.close()
        log(f"Pruned package history older than {retention_days} days")
    except Exception as e:
        log(f"Failed to prune package history: {e}")

    if not LOG_FILE.exists():
        return
    cutoff = datetime.now().timestamp() - retention_days * 86400
    lines = LOG_FILE.read_text(encoding="utf-8").splitlines()
    kept = []
    for line in lines:
        try:
            ts_str = line[1:20]
            ts = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S").timestamp()
            if ts >= cutoff:
                kept.append(line)
        except (ValueError, IndexError):
            kept.append(line)
    LOG_FILE.write_text("\n".join(kept) + "\n", encoding="utf-8")
    log(f"Pruned log entries older than {retention_days} days")
