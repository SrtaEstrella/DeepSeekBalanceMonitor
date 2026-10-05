import tempfile
import urllib.error
import unittest
import json
import sys
import sqlite3
from pathlib import Path
from unittest.mock import patch, Mock
from src.platforms import deepseek as api_client
from src.core.config import DEFAULT_CONFIG, T
from src.core.app_state import AppState

# Skip macOS-specific tests on non-macOS platforms
if sys.platform == "darwin":
    from src.mac.keystore import decrypt_api_key, encrypt_api_key
else:
    decrypt_api_key = encrypt_api_key = None

class ApiClientTests(unittest.TestCase):
    def test_fetch_balance_parses_currency_amounts(self):
        payload = {
            "is_available": False,
            "balance_infos": [{
                "currency": "CNY",
                "total_balance": "12.50", "granted_balance": "2.00",
                "topped_up_balance": "10.50",
            }],
        }
        with patch("src.platforms.deepseek.http_get_json", return_value=payload):
            result = api_client.fetch_balance("key")
        self.assertFalse(result["is_available"])
        balance = result["all_balances"]["CNY"]
        self.assertEqual((balance["total_balance"], balance["granted_balance"],
                          balance["topped_up_balance"]), (12.5, 2.0, 10.5))

    def test_fetch_balance_clamps_negative_buckets(self):
        # topped -0.10 + granted 6.00 => 6.00 usable, NOT the raw sum 5.90.
        # A negative bucket is not usable balance, so it clamps to 0 and the
        # total is derived from the clamped buckets.
        payload = {
            "is_available": True,
            "balance_infos": [{
                "currency": "CNY",
                "total_balance": "5.90", "granted_balance": "6.00",
                "topped_up_balance": "-0.10",
            }],
        }
        with patch("src.platforms.deepseek.http_get_json", return_value=payload):
            result = api_client.fetch_balance("key")
        balance = result["all_balances"]["CNY"]
        self.assertEqual(balance["topped_up_balance"], 0.0)
        self.assertEqual(balance["granted_balance"], 6.0)
        self.assertEqual(balance["total_balance"], 6.0)

    def test_fetch_balance_handles_empty_and_unauthorized_responses(self):
        with patch("src.platforms.deepseek.http_get_json", return_value={"balance_infos": []}):
            with self.assertRaises(ValueError):
                api_client.fetch_balance("key")
        error = urllib.error.HTTPError("url", 401, "", {}, None)
        with patch("src.platforms.deepseek.http_get_json", side_effect=error):
            with self.assertRaises(PermissionError):
                api_client.fetch_balance("bad-key")
        error.close()

    def test_fetch_service_status_reports_api_component_state(self):
        # A real DeepSeek page identifies itself through its API components; the
        # payload ships as escaped JSON inside an RSC push chunk.
        payload = {"components": [{"name": "DeepSeek V4 Pro API服务(API Service)"}],
                   "active_changes": []}
        inner = json.dumps(payload, ensure_ascii=False)
        html = "<script>self.__next_f.push([1," + json.dumps(inner, ensure_ascii=False) + "])</script>"
        mock_resp = Mock()
        mock_resp.read.return_value = html.encode("utf-8")
        mock_resp.__enter__ = Mock(return_value=mock_resp)
        mock_resp.__exit__ = Mock(return_value=False)
        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = api_client.fetch_service_status()
        self.assertEqual(result, {"indicator": "none", "api_operational": True})
        self.assertIsInstance(result["api_operational"], bool)

        # Network error returns None
        with patch("urllib.request.urlopen", side_effect=RuntimeError("boom")):
            self.assertIsNone(api_client.fetch_service_status())

class AppStateTests(unittest.TestCase):
    def _state(self, alert_mode="once", threshold=10):
        config = {"language": "en", "threshold_yuan": threshold,
                  "alert_mode": alert_mode}
        with patch("src.core.app_state.load_config", return_value=config):
            return AppState()

    def test_low_balance_alert_once_and_api_status_transitions(self):
        state = self._state()
        state.balances = {"CNY": {"total_balance": 5}}
        self.assertTrue(state.is_low_balance())
        self.assertTrue(state.should_alert())
        self.assertFalse(state.should_alert())
        state.balances["CNY"]["total_balance"] = 11
        self.assertFalse(state.should_alert())
        state.balances["CNY"]["total_balance"] = 5
        self.assertTrue(state.should_alert())
        state.service_status = {"api_operational": False}
        self.assertEqual(state.check_api_status_alert(), "degraded")
        self.assertIsNone(state.check_api_status_alert())
        state.service_status = {"api_operational": True}
        self.assertEqual(state.check_api_status_alert(), "recovered")

    def test_restart_polling_rearms_after_cancel(self):
        """Settings-save pattern: cancel_timer() alone must not leave the
        automatic loop dead — restart_polling() has to re-arm a fresh timer."""
        state = self._state()
        state.running = True
        calls = []
        state._poll_cb = lambda: calls.append(1)
        state.schedule_next_check(state._poll_cb, 3600)
        timer1 = state._timer
        self.assertIsNotNone(timer1)
        state.restart_polling()  # what settings save now does
        timer2 = state._timer
        self.assertIsNotNone(timer2)
        self.assertIsNot(timer1, timer2)
        state.cancel_timer()
        self.assertIsNone(state._timer)

    def test_restart_polling_uses_configured_interval(self):
        config = {"language": "en", "interval_minutes": 30}
        with patch("src.core.app_state.load_config", return_value=config):
            state = AppState()
        state.running = True
        state._poll_cb = lambda: None
        state.restart_polling()  # interval_sec omitted -> reads config
        self.assertIsNotNone(state._timer)
        self.assertEqual(state._timer.interval, 30 * 60)
        state.cancel_timer()

class ConfigContractTests(unittest.TestCase):
    def test_v12_config_fields_and_notification_text_exist(self):
        for key in ("retention_days", "theme", "icon_colors", "icon_stroke",
                    "export_path", "http_proxy"):
            self.assertIn(key, DEFAULT_CONFIG)

        english_line = T("bal_line", "en", balance="12.34", code="CNY",
                         topped="10.00", granted="2.34")
        self.assertEqual(english_line, "12.34 CNY (Topped 10.00, Granted 2.34)")
        self.assertEqual(T("service_status", "en"), "API Status:")

@unittest.skipUnless(sys.platform == "darwin", "macOS only")
class MacKeystoreTests(unittest.TestCase):
    def test_mac_keystore_round_trip_and_wrong_key_returns_empty(self):
        with tempfile.TemporaryDirectory() as data, tempfile.TemporaryDirectory() as other:
            encrypted = encrypt_api_key("test-key-value", Path(data))

            self.assertEqual(decrypt_api_key(encrypted, Path(data)), "test-key-value")
            self.assertEqual(decrypt_api_key(encrypted, Path(other)), "")


class CommandCodeQuotaTests(unittest.TestCase):
    def test_monthly_cap_inferred_from_window_caps(self):
        from src.platforms import command_code
        for (five, weekly), cap in {
            (3, 6): 10.0,      # Go
            (14, 35): 70.0,    # GOAT
            (16, 40): 80.0,    # Pro
            (45, 90): 150.0,   # Max 10x
            (90, 180): 300.0,  # Max 20x
            (12, 24): 40.0,    # Team Pro
        }.items():
            limits = {"fiveHour": {"cap": five}, "weekly": {"cap": weekly}}
            self.assertEqual(command_code._monthly_cap_from_windows(limits), cap)
        # Uncatalogued caps / no windows (pay-as-you-go) -> no monthly window
        self.assertIsNone(command_code._monthly_cap_from_windows(
            {"fiveHour": {"cap": 10}, "weekly": {"cap": 20}}))
        self.assertIsNone(command_code._monthly_cap_from_windows({}))

    def test_fetch_quota_reports_monthly_without_plan_id(self):
        from src.platforms import command_code
        whoami = {"success": True, "org": None}
        credits = {
            "credits": {"monthlyCredits": 55.0},
            "windowLimits": {
                "fiveHour": {"used": 0, "cap": 14, "resetAt": 0},
                "weekly": {"used": 3.5, "cap": 35, "resetAt": 0},
            },
        }
        with patch("src.platforms.command_code.http_get_json",
                   side_effect=[whoami, credits]):
            quota = command_code.fetch_command_code_quota("test-key")
        self.assertAlmostEqual(quota["monthly"]["percent_remaining"], 55.0 / 70.0 * 100.0)
        self.assertAlmostEqual(quota["monthly"]["usage_percent"], 100.0 - 55.0 / 70.0 * 100.0)
        self.assertEqual(quota["monthly"]["reset_in_sec"], 0)
        self.assertAlmostEqual(quota["weekly"]["percent_remaining"], 90.0)

    def test_bonus_credits_are_not_clamped(self):
        from src.platforms import command_code
        whoami = {"success": True, "org": None}
        credits = {
            "credits": {"monthlyCredits": 90.0},
            "windowLimits": {
                "fiveHour": {"used": 0, "cap": 14},
                "weekly": {"used": 1.0, "cap": 35},
            },
        }
        with patch("src.platforms.command_code.http_get_json",
                   side_effect=[whoami, credits]):
            quota = command_code.fetch_command_code_quota("test-key")
        self.assertGreater(quota["monthly"]["percent_remaining"], 100.0)
        self.assertEqual(quota["monthly"]["usage_percent"], 0.0)


class RefinedRemainingTests(unittest.TestCase):
    """Regression for the OCGo interpolation bug.

    The API's integer used% is ROUNDED (true usage within obs±0.5), so the
    refined remaining must stay inside raw 100-obs ± 0.5 at every point and
    must be monotone inside a billing period.

    Historical failures:
    - empirical spend/rise ratio biased low by 5h window resets inflated
      every advance ~10% -> continuous usage drifted ~3 points ABOVE the
      observed rounded integer (refined 63.0 vs raw 66)
    - later floor-semantics band (obs-1, obs] forced refined remaining to
      always be >= raw 100-obs (|refined-raw| up to +0.94), which is wrong
      for a ROUNDED observation (true usage may sit anywhere in obs±0.5)
    """

    def _series(self, rows):
        """rows: list of (timestamp, h5_percent, monthly_percent) sorted ASC."""
        fd, db = tempfile.mkstemp(suffix=".db")
        import os
        os.close(fd)
        conn = sqlite3.connect(db)
        conn.execute("""CREATE TABLE package_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT, api_id TEXT NOT NULL,
            timestamp TEXT NOT NULL, h5_percent REAL, h5_reset INTEGER,
            weekly_percent REAL, weekly_reset INTEGER,
            monthly_percent REAL, monthly_reset INTEGER, service_status TEXT)""")
        for ts, h5, mo in rows:
            conn.execute(
                "INSERT INTO package_history (api_id, timestamp, h5_percent, "
                "weekly_percent, monthly_percent) VALUES (?,?,?,?,?)",
                ("tid", ts, h5, None, mo))
        conn.commit()
        conn.close()
        real_conn = sqlite3.connect(db)
        self.addCleanup(real_conn.close)
        self.addCleanup(lambda: Path(db).unlink(missing_ok=True))
        patch_db = patch("src.core.storage._connect_package", return_value=real_conn)
        patch_db.start()
        self.addCleanup(patch_db.stop)

        cfg = {"apis": [{"id": "tid", "platform": "opencode_go"}]}
        patch_cfg = patch("src.core.config.load_config", return_value=cfg)
        patch_cfg.start()
        self.addCleanup(patch_cfg.stop)

        from src.core.storage import get_refined_remaining_series
        ts_v, rem_v = get_refined_remaining_series("tid", target="monthly", days=30)
        return ts_v, rem_v

    def _ts(self, days_ago, hour=12):
        from datetime import datetime, timedelta
        d = datetime.now() - timedelta(days=days_ago)
        return d.replace(hour=hour, minute=0, second=0).strftime("%Y-%m-%d %H:%M:%S")

    def test_refined_stays_within_round_band_of_raw(self):
        # Mirrors the reported case: monthly usage 34,35,36 with 5h spend in
        # between and a 5h reset boundary (h5 drop). obs is ROUNDED, so each
        # refined remaining must satisfy |refined - (100-obs)| <= 0.5.
        base = 10  # enough days inside the 30-day surfaced window
        rows = [
            (self._ts(base + 2, 8), 30.0, 33.0),
            (self._ts(base + 2, 9), 32.0, 33.0),
            (self._ts(base + 2, 10), 35.0, 34.0),   # raw remaining 66
            (self._ts(base + 2, 11), 41.0, 34.0),
            (self._ts(base + 2, 12), 43.0, 34.0),
            (self._ts(base + 1, 8), 5.0,  35.0),    # 5h reset, raw 65
            (self._ts(base, 9), 10.0, 36.0),        # raw 64
        ]
        ts_v, rem_v = self._series(rows)
        self.assertEqual(len(ts_v), len(rows))
        obs = [r[2] for r in rows]
        for ts, rem, o in zip(ts_v, rem_v, obs):
            raw = 100 - o
            self.assertLessEqual(abs(rem - raw), 0.5 + 1e-9,
                                 f"{ts}: refined {rem:.2f} vs raw {raw}: "
                                 f"drift {rem - raw:+.3f} > 0.5 (rounded obs)")

    def test_monotone_within_period_and_causal(self):
        rows = [
            (self._ts(6, 8), 10.0, 20.0),
            (self._ts(6, 9), 15.0, 20.0),
            (self._ts(6, 10), 20.0, 21.0),
            (self._ts(6, 11), 25.0, 21.0),
            (self._ts(6, 12), 30.0, 22.0),
            (self._ts(6, 13), 33.0, 22.0),
        ]
        ts_v, rem_v = self._series(rows)
        prev = None
        for rem in rem_v:
            if prev is not None:
                self.assertLessEqual(rem, prev + 1e-9)   # never rises within period
            prev = rem


class ConsumptionRateBalanceBaseTests(unittest.TestCase):
    """The consumption rate / "预计可用" estimate must be built on `total`
    (total_balance = topped_up + granted), not on `topped` alone.

    Reported symptom: the DeepSeek statistics ignored the granted (赠送)
    balance. Real data — topped sat at -0.23 all week while granted held 6.00
    and total was 5.76 — so the estimate base became -0.23 and the UI
    rendered "预计可用忙时 -0.1 小时" (a negative estimate); once consumption
    is drawn from the granted bucket, a topped-only series is flat forever
    and the rate reads 0.
    """

    def _rate(self, rows):
        """rows: list of (timestamp, total, topped, granted). Patches the DB and config."""
        fd, db = tempfile.mkstemp(suffix=".db")
        import os
        os.close(fd)
        conn = sqlite3.connect(db)
        conn.execute("""CREATE TABLE balance_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT NOT NULL,
            currency TEXT NOT NULL, total REAL NOT NULL, topped REAL NOT NULL,
            granted REAL NOT NULL, service_status TEXT, api_id TEXT)""")
        for ts, total, topped, granted in rows:
            conn.execute(
                "INSERT INTO balance_history (timestamp, currency, total, topped, granted, api_id) "
                "VALUES (?,?,?,?,?,?)", (ts, "CNY", total, topped, granted, "tid"))
        conn.commit()
        conn.close()

        patch_db = patch("src.core.storage.DB_FILE", Path(db))
        patch_db.start()
        self.addCleanup(patch_db.stop)
        patch_cfg = patch("src.core.storage.load_config",
                          return_value={"interval_minutes": 10, "retention_days": 180})
        patch_cfg.start()
        self.addCleanup(patch_cfg.stop)
        self.addCleanup(lambda: Path(db).unlink(missing_ok=True))

        from src.core.storage import get_consumption_rate
        return get_consumption_rate(days=7, api_id="tid")

    def _ts(self, minutes_ago):
        from datetime import datetime, timedelta
        return (datetime.now() - timedelta(minutes=minutes_ago)).strftime("%Y-%m-%d %H:%M:%S")

    def test_estimated_hours_use_total_not_topped(self):
        # Consumption of 0.50 CNY every 10 minutes drawn from the GRANTED
        # bucket, exactly as the parser now stores it once negatives are
        # clamped away (topped 0.00, granted = total). Reading `topped` alone
        # would see a flat 0.00 series and yield no rate at all.
        totals = [6.76, 6.26, 5.76, 5.26, 4.76, 4.26]
        rows = [(self._ts((len(totals) - 1 - i) * 10), t, 0.0, t)
                for i, t in enumerate(totals)]
        result = self._rate(rows)
        self.assertIsNotNone(result, "granted-bucket consumption must produce a rate")
        hourly_rate, busy_hours, currency = result
        # 2.50 CNY over 50 minutes of busy time
        self.assertAlmostEqual(hourly_rate, 3.0, places=6)
        self.assertEqual(currency, "CNY")
        # base must be the LAST TOTAL (4.26), not the constant topped (-0.23)
        self.assertAlmostEqual(busy_hours, 4.26 / 3.0, places=6)
        self.assertGreater(busy_hours, 0.0, "estimate must never go negative here")

    def test_topped_only_flat_series_still_uses_total(self):
        # Even with no consumption at all, the base is the usable total.
        rows = [(self._ts((2 - i) * 10), 15.0, 9.0, 6.0) for i in range(3)]
        self.assertIsNone(self._rate(rows))

    def test_negative_balance_clamps_estimate_to_zero(self):
        # A platform may legitimately report a negative remaining total while
        # its buckets stay non-negative (OpenRouter: total = gross credits −
        # usage), so this clamp stays reachable after the row migration above.
        # Real case: the DeepSeek total sat at -0.23 for a whole week.
        totals = [-0.23, -0.73, -1.23, -1.73, -2.23, -2.73]
        rows = [(self._ts((len(totals) - 1 - i) * 10), t, 9.0, 0.0)
                for i, t in enumerate(totals)]
        result = self._rate(rows)
        self.assertIsNotNone(result)
        hourly_rate, busy_hours, _currency = result
        self.assertAlmostEqual(hourly_rate, 3.0, places=6)
        self.assertEqual(busy_hours, 0.0, "negative balance must clamp to 0 hours")

    def test_short_interval_does_not_dominate_rate(self):
        # Reported case: two extra/manual checks 46 s apart carrying a 0.08
        # drop were the only interval with a non-zero drop, so they owned the
        # whole weighted average and extrapolated to 6.26/h. Such an interval
        # is not a measurement span and must not qualify as a rate sample.
        rows = [
            (self._ts(90), 6.00, 0.0, 6.00),
            (self._ts(80), 6.00, 0.0, 6.00),
            (self._ts(2), 5.92, 0.0, 5.92),            # drop closes the flat run
            (self._ts(2 - 46 / 60), 5.84, 0.0, 5.84),  # 46 s later -> 0.08 drop
        ]
        self.assertIsNone(self._rate(rows),
                          "a 46-second interval must not produce a rate")

    def test_poll_interval_samples_still_produce_rate(self):
        # Positive control: samples one poll interval apart (10 min) remain
        # valid rate measurements.
        rows = [
            (self._ts(30), 6.00, 0.0, 6.00),
            (self._ts(20), 5.90, 0.0, 5.90),
            (self._ts(10), 5.80, 0.0, 5.80),
        ]
        result = self._rate(rows)
        self.assertIsNotNone(result)
        hourly_rate, busy_hours, _currency = result
        self.assertAlmostEqual(hourly_rate, 0.20 / (20 / 60), places=6)
        self.assertAlmostEqual(busy_hours, 5.80 / hourly_rate, places=6)

    def test_legacy_negative_rows_are_normalized_to_usable_total(self):
        # Rows already stored with a negative bucket (pre-rule history, or rows
        # written by the Rust builds, which persist raw API values) must be
        # repaired on connect so statistics see the usable total.
        fd, db = tempfile.mkstemp(suffix=".db")
        import os
        os.close(fd)
        patch_db = patch("src.core.storage.DB_FILE", Path(db))
        patch_db.start()
        self.addCleanup(patch_db.stop)
        patch_cfg = patch("src.core.storage.load_config",
                          return_value={"interval_minutes": 10, "retention_days": 180})
        patch_cfg.start()
        self.addCleanup(patch_cfg.stop)
        self.addCleanup(lambda: Path(db).unlink(missing_ok=True))

        from src.core.storage import _connect
        _connect().close()                       # create the schema

        raw = sqlite3.connect(db)
        for ts, total, topped, granted in ((self._ts(20), -0.23, -0.23, 0.0),
                                           (self._ts(10), 5.76, -0.23, 6.0)):
            raw.execute(
                "INSERT INTO balance_history (timestamp, currency, total, topped, granted, api_id) "
                "VALUES (?,?,?,?,?,?)", (ts, "CNY", total, topped, granted, "tid"))
        raw.commit()
        raw.close()

        _connect().close()                       # migration runs here
        raw = sqlite3.connect(db)
        rows = raw.execute("SELECT total, topped, granted FROM balance_history "
                           "ORDER BY timestamp ASC").fetchall()
        raw.close()
        self.assertEqual(rows[0], (0.0, 0.0, 0.0))
        self.assertEqual(rows[1], (6.0, 0.0, 6.0),
                         "topped -0.23 + granted 6.00 must become 6.00 usable, not 5.76")


class RustParityTests(unittest.TestCase):
    """Fixes the Rust builds shipped from 1.3.3 on that the Python build lacked.

    SQLite WAL + indexes, the corrupt-config backup, the single-instance lock
    and the clamped quota percentages (all 1.4.2), plus the CNY-preferring
    balance pick that keeps `threshold_yuan` from being compared with USD.
    """

    def _temp_db(self):
        fd, db = tempfile.mkstemp(suffix=".db")
        import os
        os.close(fd)
        patch_db = patch("src.core.storage.DB_FILE", Path(db))
        patch_db.start()
        self.addCleanup(patch_db.stop)
        self.addCleanup(lambda: Path(db).unlink(missing_ok=True))
        return db

    # ── SQLite: WAL + indexes ────────────────────────────────────────────────
    def test_sqlite_enables_wal_and_indexes(self):
        self._temp_db()
        from src.core.storage import _connect, _connect_package
        for connect, index in ((_connect, "idx_balance_api_ts"),
                               (_connect_package, "idx_package_api_ts")):
            conn = connect()
            try:
                mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
                self.assertEqual(mode.lower(), "wal", "WAL keeps readers off the writer's lock")
                # No busy-timeout statement is issued: Python's sqlite3 already
                # connects with 5 s, which is the behaviour we rely on. The
                # assertion documents that assumption.
                self.assertEqual(conn.execute("PRAGMA busy_timeout").fetchone()[0], 5000)
                names = {r[0] for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='index'")}
                self.assertIn(index, names)
            finally:
                conn.close()

    # ── Corrupt config is preserved before defaults take over ────────────────
    def test_unreadable_config_is_backed_up(self):
        tmp = tempfile.mkdtemp()
        cfg_file = Path(tmp) / "config.json"
        cfg_file.write_text("{ this is not json", encoding="utf-8")
        with patch("src.core.config.CONFIG_FILE", cfg_file), \
             patch("src.core.config.log"):
            from src.core.config import load_config
            cfg = load_config()
        self.assertEqual(cfg.get("interval_minutes"), DEFAULT_CONFIG["interval_minutes"])
        self.assertTrue((Path(tmp) / "config.json.corrupt").exists(),
                        "the unreadable config must be copied before falling back")

    # ── Single-instance lock ─────────────────────────────────────────────────
    @unittest.skipUnless(sys.platform == "win32", "named mutex is Windows-only")
    def test_second_instance_is_refused(self):
        import ctypes
        from src.core import paths as paths_mod
        paths_mod._INSTANCE_HANDLE = None
        self.addCleanup(lambda: setattr(paths_mod, "_INSTANCE_HANDLE", None))
        k32 = ctypes.windll.kernel32
        k32.CreateMutexW.restype = ctypes.c_void_p
        k32.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_wchar_p]
        k32.CloseHandle.argtypes = [ctypes.c_void_p]
        held = k32.CreateMutexW(None, 0, f"Local\\{paths_mod.APP_ID}")
        self.assertTrue(held, "could not create the test mutex")
        self.addCleanup(lambda: k32.CloseHandle(ctypes.c_void_p(held)))
        self.assertFalse(paths_mod.acquire_single_instance(),
                         "a held mutex must turn the second instance away")

    # ── Export path expansion (~ plus the platform's variable syntax) ────────
    def test_export_path_expands_variables_and_home(self):
        import os as _os
        from src.core.storage import _resolve_export_path
        # `~` expands wherever a home directory is resolvable
        if _os.path.expanduser("~") != "~":
            self.assertNotIn("~", _resolve_export_path("~/balance.csv"))
        self.assertTrue(_resolve_export_path("~/balance.csv").endswith("balance.csv"))
        if _os.name == "nt":
            # ntpath.expandvars handles the %VAR% form a Windows user may paste
            expanded = _resolve_export_path("%USERPROFILE%/balance.csv")
            self.assertNotIn("%USERPROFILE%", expanded)
            self.assertTrue(expanded.endswith("balance.csv"))
        else:
            # posixpath.expandvars handles $VAR (it deliberately leaves %VAR% alone)
            _os.environ["DSH_EXPORT_TEST"] = "expanded"
            self.addCleanup(lambda: _os.environ.pop("DSH_EXPORT_TEST", None))
            self.assertIn("expanded", _resolve_export_path("$DSH_EXPORT_TEST/balance.csv"))

    # ── Quota percentages clamped to 0–100 (shared contract §7.3) ───────────
    def test_opencode_percentage_is_clamped(self):
        payload = {"usage": {"rolling": {"status": "ok", "percent": 150}}}
        with patch("src.platforms.opencode.http_get_json", return_value=payload), \
             patch("src.platforms.opencode._install_proxy"):
            from src.platforms.opencode import fetch_opencode_quota
            quota = fetch_opencode_quota("key")
        self.assertEqual(quota["rolling"]["usage_percent"], 100.0)
        self.assertEqual(quota["rolling"]["percent_remaining"], 0.0)

    def test_glm_percentage_is_clamped(self):
        payload = {"code": 0, "success": True, "data": {"limits": [
            {"type": "TOKENS_LIMIT", "percentage": 150},
            {"type": "TOKENS_LIMIT", "percentage": -20}]}}
        with patch("src.platforms.glm.http_get_json", return_value=payload), \
             patch("src.platforms.glm._install_proxy"):
            from src.platforms.glm import fetch_glm_quota
            quota = fetch_glm_quota("key", platform_key="glm_coding_cn")
        self.assertEqual(quota["5h"]["usage_percent"], 100.0)
        self.assertEqual(quota["5h"]["percent_remaining"], 0.0)
        self.assertEqual(quota["weekly"]["usage_percent"], 0.0)
        self.assertEqual(quota["weekly"]["percent_remaining"], 100.0)

    def test_minimax_percentages_are_clamped(self):
        payload = {"base_resp": {"status_code": 0}, "data": {"model_remains": [
            {"model_name": "general",
             "current_interval_remaining_percent": 150,
             "current_weekly_remaining_percent": -5,
             "end_time": 0, "weekly_end_time": 0}]}}
        with patch("src.platforms.minimax.http_get_json", return_value=payload), \
             patch("src.platforms.minimax._install_proxy"):
            from src.platforms.minimax import fetch_minimax_quota
            quota = fetch_minimax_quota("minimax_token_cn", "key")
        self.assertEqual(quota["5h"]["percent_remaining"], 100.0)
        self.assertEqual(quota["5h"]["usage_percent"], 0.0)
        self.assertEqual(quota["weekly"]["percent_remaining"], 0.0)
        self.assertEqual(quota["weekly"]["usage_percent"], 100.0)


class ServiceStatusParsingTests(unittest.TestCase):
    """The DeepSeek status parse was structurally unable to report an incident.

    Reported symptom: healthy showed 服务正常, a real outage showed
    "服务状态未知", and an incident state was never reported. Three causes:

    1. the source URL pointed at status.flashcat.cloud/deepseek, which is
       FlashDuty's OWN status page (no DeepSeek data), yet the parser still
       answered "operational";
    2. component matching looked for names starting with API|Web|网页|APP|对话,
       which never matches the real API components
       ("DeepSeek V4 Pro API服务(API Service)");
    3. the incident extraction regex `\\[[^\\]]*\\]` cannot match a nested
       affected_components array — it truncated the JSON, json.loads raised, and
       the blanket except returned None (= 服务状态未知) exactly when a change
       was active. Only "fine" and "unknown" were reachable.
    """

    API = "DeepSeek V4 Pro API服务(API Service)"
    FLASH = "DeepSeek V4.1 Flash API服务(API Service)"
    CHAT = "对话服务(Chatservice)"
    UPLOAD = "上传文件服务(File Upload Service)"

    @staticmethod
    def _page(payload):
        """Build a page in the real shape: escaped JSON inside an RSC push chunk."""
        import json as _json
        inner = _json.dumps(payload, ensure_ascii=False)
        return ("<script>self.__next_f.push([1,"
                + _json.dumps(inner, ensure_ascii=False) + "])</script>")

    def _parse(self, payload):
        from src.platforms.deepseek import parse_status_page
        return parse_status_page(self._page(payload))

    def test_healthy_page_reports_operational(self):
        result = self._parse({"components": [{"name": self.API}, {"name": self.CHAT}],
                              "active_changes": []})
        self.assertEqual(result, {"indicator": "none", "api_operational": True})

    def test_active_incident_with_nested_components_is_reported(self):
        # The exact shape that used to raise inside json.loads.
        result = self._parse({
            "components": [{"name": self.API}, {"name": self.FLASH}, {"name": self.CHAT}],
            "active_changes": [{
                "change_id": 1, "type": "incident", "status": "investigating",
                "title": "DeepSeek 网页/API 性能下降",
                "affected_components": [
                    {"name": self.API, "status": "degraded"},
                    {"name": self.FLASH, "status": "operational"},
                    {"name": self.CHAT, "status": "degraded"},
                ],
            }],
        })
        self.assertEqual(result, {"indicator": "minor", "api_operational": False})

    def test_worst_affected_api_component_wins(self):
        result = self._parse({
            "components": [{"name": self.API}, {"name": self.FLASH}],
            "active_changes": [{
                "change_id": 2, "type": "incident", "status": "monitoring",
                "affected_components": [{"name": self.API, "status": "degraded"},
                                        {"name": self.FLASH, "status": "full_outage"}],
            }],
        })
        self.assertEqual(result, {"indicator": "critical", "api_operational": False})

    def test_non_api_component_does_not_flag_the_api(self):
        # Chosen semantics: only API-type components drive the API status.
        result = self._parse({
            "components": [{"name": self.API}, {"name": self.UPLOAD}],
            "active_changes": [{
                "change_id": 3, "type": "incident", "status": "investigating",
                "affected_components": [{"name": self.UPLOAD, "status": "partial_outage"}],
            }],
        })
        self.assertEqual(result, {"indicator": "none", "api_operational": True})

    def test_resolved_incident_does_not_raise_the_indicator(self):
        result = self._parse({
            "components": [{"name": self.API}],
            "active_changes": [{
                "change_id": 4, "type": "incident", "status": "resolved",
                "affected_components": [{"name": self.API, "status": "operational"}],
            }],
        })
        self.assertEqual(result, {"indicator": "none", "api_operational": True})

    def test_contract_mapping_covers_every_documented_status(self):
        # docs/INTERFACES.md §7.4 (locked) normalizes each vendor status string
        # onto the shared indicator vocabulary. degraded_performance and
        # major_outage were missing from the table: the former only worked by
        # falling through to the unknown-severity path, the latter would have
        # reported a full outage as "minor".
        for raw, indicator in (("degraded", "minor"),
                               ("degraded_performance", "minor"),
                               ("partial_outage", "major"),
                               ("full_outage", "critical"),
                               ("major_outage", "critical"),
                               ("under_maintenance", "maintenance")):
            result = self._parse({
                "components": [{"name": self.API}],
                "active_changes": [{
                    "change_id": 9, "type": "incident", "status": "investigating",
                    "affected_components": [{"name": self.API, "status": raw}],
                }],
            })
            self.assertIsNotNone(result, raw)
            self.assertEqual(result["indicator"], indicator, raw)
            self.assertEqual(result["api_operational"], indicator == "none", raw)

    def test_foreign_page_is_unknown_not_operational(self):
        # FlashDuty serves its own status page for unknown paths; answering
        # "operational" for it is what hid every DeepSeek incident.
        foreign = ("<script>self.__next_f.push([1,"
                   + json.dumps(json.dumps({"components": [
                       {"name": "Web Console"}, {"name": "Webhooks"}, {"name": "Web Chat"}],
                       "active_changes": []}), ensure_ascii=False)
                   + "])</script>")
        from src.platforms.deepseek import parse_status_page
        self.assertIsNone(parse_status_page(foreign))

    def test_fetch_falls_back_to_the_backend_host(self):
        from src.platforms import deepseek as status_mod
        page = self._page({"components": [{"name": self.API}], "active_changes": []})

        def fake_urlopen(req, timeout=None):
            self.assertTrue(req.full_url.startswith("https://status.deepseek.com"))
            raise urllib.error.URLError("tls handshake reset")

        def fake_urlopen_ok(req, timeout=None):
            self.assertIn("flashduty.com", req.full_url)
            resp = Mock()
            resp.read.return_value = page.encode("utf-8")
            resp.__enter__ = Mock(return_value=resp)
            resp.__exit__ = Mock(return_value=False)
            return resp

        calls = []

        def dispatch(req, timeout=None):
            calls.append(req.full_url)
            return fake_urlopen(req, timeout) if len(calls) == 1 else fake_urlopen_ok(req, timeout)

        with patch("urllib.request.urlopen", side_effect=dispatch):
            result = status_mod.fetch_service_status()
        self.assertEqual(result, {"indicator": "none", "api_operational": True})
        self.assertEqual(len(calls), 2, "must fall back to the second source")

    def test_fetch_returns_none_when_every_source_fails(self):
        from src.platforms import deepseek as status_mod
        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("down")):
            self.assertIsNone(status_mod.fetch_service_status())



class WidgetContractTests(unittest.TestCase):
    """The dsmon2-widget contract (docs/INTERFACES.md §1) as the Python build
    serves it: payload shape, `days` handling, and the HTTP surface."""

    def _app(self, apis=None, preferred="", language="zh"):
        app = AppState()
        app.config = {**DEFAULT_CONFIG, "apis": apis or [],
                      "preferred_api_id": preferred, "language": language}
        return app

    def _patched_app(self, apis, preferred="", series=None, today=None):
        """The widget server with its data sources stubbed: keys exist for
        every API, the curve comes from `series`, the day figure from
        `today`. Returns (exit-stack, app, mocks)."""
        import contextlib
        from src.integrations import widget_server

        app = self._app(apis=apis, preferred=preferred)
        stack = contextlib.ExitStack()
        mocks = {}
        for name, stub in [
            ("read_api_key_for_id", Mock(return_value="key")),
            ("get_balance_series", Mock(return_value=series or [])),
            ("get_consumption_rate", Mock(return_value=None)),
            ("get_today_total_spend", Mock(return_value=today)),
            ("get_package_daily_usage", Mock(return_value=[])),
        ]:
            mocks[name] = stack.enter_context(patch.object(widget_server, name, stub))
        return stack, app, mocks

    def test_payload_basics_with_no_apis(self):
        from src.integrations import widget_server
        app = self._app()
        payload = widget_server.build_payload(app)
        self.assertEqual(payload["version"], 2)
        self.assertEqual(payload["provider"]["name"], "deepseek-balance-monitor")
        self.assertEqual(payload["lang"], "zh")
        self.assertEqual(payload["platforms"], [])
        self.assertIsNone(payload["today_spend"])
        self.assertIn("generated_at", payload)

    def test_days_is_validated(self):
        from src.integrations import widget_server
        self.assertEqual(widget_server._parse_days("days=30"), 30)
        self.assertEqual(widget_server._parse_days("days=1"), 1)
        self.assertEqual(widget_server._parse_days("days=5"), 7)
        self.assertEqual(widget_server._parse_days(""), 7)

    def test_only_configured_platforms_appear(self):
        from src.integrations import widget_server
        stack, app, mocks = self._patched_app(
            apis=[
                {"id": "a1", "platform": "deepseek", "mode": "payg"},
                {"id": "a2", "platform": "opencode_go", "mode": "package"},
            ],
            preferred="a1",
        )
        mocks["read_api_key_for_id"].side_effect = (
            lambda api_id: "key" if api_id == "a1" else None)
        with stack:
            payload = widget_server.build_payload(app)

        self.assertEqual([p["key"] for p in payload["platforms"]], ["deepseek"])
        entry = payload["platforms"][0]
        self.assertEqual(entry["display"], "DeepSeek")
        self.assertEqual(entry["kind"], "payg")
        self.assertEqual(entry["balances"], [])

    def test_series_is_thinned_to_240_points_keeping_the_last(self):
        from src.integrations import widget_server
        points = [(f"2026-01-01 10:{i % 60:02d}:{i % 60:02d}", float(i))
                  for i in range(1000)]
        stack, app, _ = self._patched_app(
            apis=[{"id": "a1", "platform": "deepseek", "mode": "payg"}],
            preferred="a1", series=points,
        )
        with stack:
            payload = widget_server.build_payload(app, days=1)
        series = payload["platforms"][0]["series"]
        self.assertLessEqual(len(series), 240)
        self.assertEqual(series[-1]["v"], 999.0)

    def test_spend_is_reported_for_the_preferred_balance_account(self):
        from src.integrations import widget_server
        stack, app, _ = self._patched_app(
            apis=[{"id": "a1", "platform": "deepseek", "mode": "payg"}],
            preferred="a1", today=("CNY", 12.5),
        )
        with stack:
            payload = widget_server.build_payload(app)
        self.assertEqual(payload["today_spend"],
                         {"platform": "deepseek", "currency": "CNY", "amount": 12.5})

    def test_http_surface(self):
        import http.client
        import threading
        from src.integrations import widget_server

        app = self._app()
        server = widget_server._make_server(app, 0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            port = server.server_address[1]
            conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)

            conn.request("GET", "/widget-status")
            response = conn.getresponse()
            body = json.loads(response.read().decode("utf-8"))
            self.assertEqual(response.status, 200)
            self.assertEqual(response.getheader("Cache-Control"), "no-store")
            self.assertEqual(response.getheader("Connection"), "close")
            self.assertTrue(response.getheader("Content-Type").startswith("application/json"))
            self.assertEqual(body["version"], 2)

            # /check answers with the current snapshot too (no poll is
            # registered here, so it only reads).
            conn.request("GET", "/check")
            self.assertEqual(conn.getresponse().status, 200)

            conn.request("GET", "/nope")
            self.assertEqual(conn.getresponse().status, 404)

            conn.request("POST", "/widget-status")
            self.assertEqual(conn.getresponse().status, 405)
            conn.close()
        finally:
            server.shutdown()
            server.server_close()
