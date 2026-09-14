"""
End-to-end integration test: agent pipeline -> real running backend.

Uses a FAKE provider standing in for WindowsProvider, since this sandbox
cannot execute real Windows telemetry collection. This tests everything
EXCEPT the Windows-specific OS calls: config loading, device_id
persistence, pydantic validation, serialization, HTTP POST, error
handling, and response display — i.e. the entire "thin client" contract
this milestone was about. The Windows-specific parsing logic is separately
unit-tested in test_parsers.py. A live smoke test of WindowsProvider
itself still needs to happen on a real Windows machine — this test does
not substitute for that.

Requires the backend to be running at settings.backend_url first.
"""
import sys
import tempfile
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from telemetry.base import TelemetryProvider, RawTelemetry
from logging_setup import setup_logging
import client
from config import settings

setup_logging("INFO", "text")


class FakeProvider(TelemetryProvider):
    """Stands in for WindowsProvider — returns fixed, realistic values
    instead of calling real OS APIs. NOT a substitute for testing
    WindowsProvider itself; see module docstring."""

    @property
    def os_type(self) -> str:
        return "Windows"

    def get_os_days_since_update(self):
        return 45.0

    def get_firewall_enabled(self):
        return True

    def get_antivirus_status(self):
        return True, 5.0

    def get_browser_safe_browsing_enabled(self):
        return False

    def get_browser_autofill_passwords(self):
        return True

    def get_risky_extension_count(self):
        return 1


class FailingFieldProvider(TelemetryProvider):
    """Simulates a real-world partial failure: antivirus check throws
    (e.g. permission denied), everything else succeeds. Tests that
    base.collect()'s per-field isolation actually works, and that the
    resulting payload triggers the backend's degraded-mode path."""

    @property
    def os_type(self) -> str:
        return "Windows"

    def get_os_days_since_update(self):
        return 10.0

    def get_firewall_enabled(self):
        return True

    def get_antivirus_status(self):
        raise PermissionError("Simulated: access denied to SecurityCenter2")

    def get_browser_safe_browsing_enabled(self):
        return True

    def get_browser_autofill_passwords(self):
        return False

    def get_risky_extension_count(self):
        return 0


class RealWindowsShapeProvider(TelemetryProvider):
    """The evidence-backed production Windows shape: safe browsing unknown,
    all six observable signals present. This must execute RF inference."""
    @property
    def os_type(self): return "Windows"
    def get_os_days_since_update(self): return 8.0
    def get_firewall_enabled(self): return True
    def get_antivirus_status(self): return True, 0.0
    def get_browser_safe_browsing_enabled(self): return None
    def get_browser_autofill_passwords(self): return True
    def get_risky_extension_count(self): return 0


def run_test(name, provider, use_temp_device_file=True):
    print(f"\n--- {name} ---")
    if use_temp_device_file:
        with tempfile.TemporaryDirectory() as tmpdir:
            settings.device_id_file = str(Path(tmpdir) / "device_id")
            return _run(provider)
    else:
        return _run(provider)


def _run(provider):
    raw = provider.collect()
    print(f"Collected telemetry (errors={raw.collection_errors}): "
          f"os_update_days={raw.os_days_since_update}, firewall={raw.firewall_enabled}, "
          f"av={raw.antivirus_enabled}, safe_browsing={raw.browser_safe_browsing_enabled}")

    device_id = client.get_or_create_device_id()
    print(f"device_id: {device_id}")

    payload = client.validate_telemetry(raw, device_id)
    print(f"Validated payload OK: {payload.model_dump_json()[:120]}...")

    result = client.send_scan(payload)
    print(f"Backend response: score={result['risk_score']}, tier={result['risk_tier']}, "
          f"degraded={result['degraded']}, findings={len(result['findings'])}, "
          f"recommendations={len(result['recommendations'])}")

    client.display_result(result)
    return result


if __name__ == "__main__":
    print(f"Target backend: {settings.backend_url}")
    r1 = run_test("Full telemetry (FakeProvider)", FakeProvider())
    r2 = run_test("Partial failure (FailingFieldProvider -> should be degraded)", FailingFieldProvider())
    r3 = run_test("Real Windows telemetry shape (partial + ML)", RealWindowsShapeProvider())

    assert r1["degraded"] is False, "Full telemetry scan should NOT be degraded"
    assert r2["degraded"] is True, "Partial-failure scan SHOULD be degraded"
    assert r3["degraded"] is True, "Unknown safe-browsing remains honestly partial"
    assert r3["ml_used"] is True and r3["ml_confidence"] is not None, "Real Windows shape must execute ML"
    assert r3["ml_strategy"] == "observable_6_feature", "Must select observable feature model"
    assert "browser_safe_browsing_enabled" in r3["telemetry_unavailable_features"]
    assert all(r["feature"] != "browser_safe_browsing_enabled" for r in r3["recommendations"])
    print("\n\nALL INTEGRATION ASSERTIONS PASSED")
