"""Regression checks for complete and real-Windows-shaped ML inference."""
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app import services


FULL = {
    "os_type": "Windows", "os_days_since_update": 150.0,
    "firewall_enabled": False, "antivirus_enabled": False,
    "days_since_av_update": 45.0, "browser_safe_browsing_enabled": False,
    "browser_autofill_passwords": True, "risky_extension_count": 3,
}

WINDOWS_PARTIAL = {
    "os_type": "Windows", "os_days_since_update": 8.0,
    "firewall_enabled": True, "antivirus_enabled": True,
    "days_since_av_update": 0.0, "browser_safe_browsing_enabled": None,
    "browser_autofill_passwords": True, "risky_extension_count": 0,
}


class MlPipelineTests(unittest.TestCase):
    def test_complete_telemetry_uses_full_rf(self):
        result = services.run_pipeline(FULL)
        self.assertTrue(result["ml_used"])
        self.assertFalse(result["degraded"])
        self.assertEqual(result["ml_strategy"], "full_7_feature")
        self.assertIsNotNone(result["ml_confidence"])

    def test_real_windows_shape_uses_observable_rf_without_fabrication(self):
        result = services.run_pipeline(WINDOWS_PARTIAL)
        self.assertTrue(result["ml_used"])
        self.assertTrue(result["degraded"])
        self.assertEqual(result["ml_strategy"], "observable_6_feature")
        self.assertIsNotNone(result["ml_confidence"])
        self.assertIn("browser_safe_browsing_enabled", result["telemetry_unavailable_features"])
        self.assertNotIn("browser_safe_browsing_enabled", result["telemetry_observed_features"])
        self.assertTrue(result["ml_explanation"])
        self.assertTrue(all(r["feature"] != "browser_safe_browsing_enabled" for r in result["recommendations"]))
        self.assertTrue(any(f["id"] == "R6_AUTOFILL" for f in result["findings"]))

    def test_other_missing_shape_remains_marked_rule_fallback(self):
        incomplete = dict(WINDOWS_PARTIAL, antivirus_enabled=None)
        result = services.run_pipeline(incomplete)
        self.assertFalse(result["ml_used"])
        self.assertTrue(result["degraded"])
        self.assertIsNone(result["ml_confidence"])
        self.assertEqual(result["recommendations"], [])


if __name__ == "__main__":
    unittest.main()
