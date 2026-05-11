import tempfile
import urllib.error
import unittest
import sys
from pathlib import Path
from unittest.mock import patch
from src import api_client
from src.config import DEFAULT_CONFIG, T
from src.app_state import AppState

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
        with patch("src.api_client._get_json", return_value=payload):
            result = api_client.fetch_balance("key")
        self.assertFalse(result["is_available"])
        balance = result["all_balances"]["CNY"]
        self.assertEqual((balance["total_balance"], balance["granted_balance"],
                          balance["topped_up_balance"]), (12.5, 2.0, 10.5))

    def test_fetch_balance_handles_empty_and_unauthorized_responses(self):
        with patch("src.api_client._get_json", return_value={"balance_infos": []}):
            with self.assertRaises(ValueError):
                api_client.fetch_balance("key")
        error = urllib.error.HTTPError("url", 401, "", {}, None)
        with patch("src.api_client._get_json", side_effect=error):
            with self.assertRaises(PermissionError):
                api_client.fetch_balance("bad-key")
        error.close()

    def test_fetch_service_status_reports_api_component_state(self):
        status = {"status": {"indicator": "minor"}}
        components = {"components": [{"name": "API", "status": "major_outage"}]}
        with patch("src.api_client._get_json", side_effect=[status, components]):
            result = api_client.fetch_service_status()
        self.assertEqual(result, {"indicator": "minor", "api_operational": False})
        with patch("src.api_client._get_json", side_effect=RuntimeError("boom")):
            self.assertIsNone(api_client.fetch_service_status())

class AppStateTests(unittest.TestCase):
    def _state(self, alert_mode="once", threshold=10):
        config = {"language": "en", "threshold_yuan": threshold,
                  "alert_mode": alert_mode}
        with patch("src.app_state.load_config", return_value=config):
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
        self.assertEqual(T("service_status", "en"), "DeepSeek API Status: ")

@unittest.skipUnless(sys.platform == "darwin", "macOS only")
class MacKeystoreTests(unittest.TestCase):
    def test_mac_keystore_round_trip_and_wrong_key_returns_empty(self):
        with tempfile.TemporaryDirectory() as data, tempfile.TemporaryDirectory() as other:
            encrypted = encrypt_api_key("test-key-value", Path(data))

            self.assertEqual(decrypt_api_key(encrypted, Path(data)), "test-key-value")
            self.assertEqual(decrypt_api_key(encrypted, Path(other)), "")
