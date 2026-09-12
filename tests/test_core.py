import tempfile
import urllib.error
import unittest
import sys
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
