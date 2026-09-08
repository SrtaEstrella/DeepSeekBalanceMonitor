import tempfile
import urllib.error
import unittest
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
        # Verify the function returns a dict with expected keys on success
        # (parsing details depend on FlashDuty RSC format, tested manually)
        html = '{\\"name\\":\\"API\\"}'
        mock_resp = Mock()
        mock_resp.read.return_value = html.encode("utf-8")
        mock_resp.__enter__ = Mock(return_value=mock_resp)
        mock_resp.__exit__ = Mock(return_value=False)
        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = api_client.fetch_service_status()
        self.assertIn("indicator", result)
        self.assertIn("api_operational", result)
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
