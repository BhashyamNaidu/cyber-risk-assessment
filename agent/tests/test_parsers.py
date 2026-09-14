"""
Unit tests for telemetry/parsers.py — the part of the Windows provider
that IS testable without a real Windows host, using realistic fixture
data modeled on documented PowerShell/WMI output formats.
"""
import json
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from telemetry.parsers import (
    parse_hotfix_date_to_days_since, parse_firewall_profiles_json,
    parse_av_product_state, parse_chrome_preferences,
)


def test_hotfix_date_iso_format():
    now = datetime(2026, 8, 6, tzinfo=timezone.utc)
    ten_days_ago = (now - timedelta(days=10)).isoformat()
    result = parse_hotfix_date_to_days_since(ten_days_ago, now=now)
    assert abs(result - 10.0) < 0.01, f"expected ~10 days, got {result}"


def test_hotfix_date_dotnet_format():
    now = datetime(2026, 8, 6, tzinfo=timezone.utc)
    five_days_ago_millis = int((now - timedelta(days=5)).timestamp() * 1000)
    dotnet_str = f"/Date({five_days_ago_millis})/"
    result = parse_hotfix_date_to_days_since(dotnet_str, now=now)
    assert abs(result - 5.0) < 0.01, f"expected ~5 days, got {result}"


def test_hotfix_date_none_input():
    assert parse_hotfix_date_to_days_since(None) is None
    assert parse_hotfix_date_to_days_since("") is None


def test_hotfix_date_garbage_input():
    assert parse_hotfix_date_to_days_since("not a date") is None


def test_hotfix_date_windows_provider_plain_format():
    """Regression test for the FIXED windows_provider.py PowerShell command
    output format: Get-HotFix ... | ForEach-Object { $_.ToString('yyyy-MM-ddTHH:mm:ss') }
    This is the exact plain-string format the agent now requests, verified
    against real Windows 10 (10.0.26200) evidence during Phase 1."""
    now = datetime(2026, 8, 17, tzinfo=timezone.utc)
    ps_output = "2026-08-12T00:00:00"  # 5 days before `now`, matches real captured KB InstalledOn date
    result = parse_hotfix_date_to_days_since(ps_output, now=now)
    assert abs(result - 5.0) < 0.01, f"expected ~5 days, got {result}"


def test_hotfix_date_real_windows_json_object_format():
    """Regression test for a REAL raw PowerShell output captured during
    Phase 1 diagnostics on Windows 10 (10.0.26200): ConvertTo-Json on a raw
    [datetime] serialized as a JSON OBJECT, not a bare string:
        {"value": "/Date(1786473000000)/", "DateTime": "12 August 2026 00:00:00"}
    This is why windows_provider.py no longer uses ConvertTo-Json for this
    field, but the parser must still handle this shape defensively in case
    a future PowerShell/culture configuration reverts to it."""
    real_captured_output = '{\n    "value": "\\/Date(1786473000000)\\/",\n    "DateTime": "12 August 2026 00:00:00"\n}'
    now = datetime(2026, 8, 17, tzinfo=timezone.utc)
    result = parse_hotfix_date_to_days_since(real_captured_output, now=now)
    assert result is not None, "must not return None for this real captured format"
    # Independently compute expected days from the same millis, to verify
    # the JSON-unwrap-then-/Date()/-parse path is arithmetically correct,
    # not just "doesn't crash".
    expected_dt = datetime.fromtimestamp(1786473000000 / 1000.0, tz=timezone.utc)
    expected_days = (now - expected_dt).total_seconds() / 86400.0
    assert abs(result - expected_days) < 0.01, f"expected ~{expected_days:.2f} days, got {result}"


def test_firewall_all_enabled():
    raw = json.dumps([{"Enabled": 1}, {"Enabled": 1}, {"Enabled": 1}])
    assert parse_firewall_profiles_json(raw) is True


def test_firewall_one_disabled():
    raw = json.dumps([{"Enabled": 1}, {"Enabled": 0}, {"Enabled": 1}])
    assert parse_firewall_profiles_json(raw) is False


def test_firewall_single_profile_dict_not_list():
    raw = json.dumps({"Enabled": 1})
    assert parse_firewall_profiles_json(raw) is True


def test_firewall_none_input():
    assert parse_firewall_profiles_json(None) is None
    assert parse_firewall_profiles_json("") is None


def test_firewall_malformed_json():
    assert parse_firewall_profiles_json("{not json") is None


def test_av_product_state_enabled_up_to_date():
    # 0x10 in the enabled position, 0x00 in the up-to-date position
    state = 0x00_10_00
    enabled, up_to_date = parse_av_product_state(state)
    assert enabled is True
    assert up_to_date is True


def test_av_product_state_enabled_out_of_date():
    state = 0x00_10_01
    enabled, up_to_date = parse_av_product_state(state)
    assert enabled is True
    assert up_to_date is False


def test_av_product_state_disabled():
    state = 0x00_00_00
    enabled, up_to_date = parse_av_product_state(state)
    assert enabled is False


def test_av_product_state_none():
    enabled, up_to_date = parse_av_product_state(None)
    assert enabled is None
    assert up_to_date is None


def test_chrome_preferences_full():
    """Note: safebrowsing.enabled is a hypothetical key from before the
    Phase 1 real-Windows investigation closed — real diagnostics confirmed
    no such key exists in practice, so this input is intentionally
    unrealistic for that field (kept only to exercise autofill/extensions
    together). safe_browsing correctly returns None regardless of this
    key's presence — see test_chrome_preferences_safe_browsing_always_none_not_inferred
    for the field's actual frozen behavior."""
    raw = json.dumps({
        "safebrowsing": {"enabled": True},
        "credentials_enable_service": False,
        "extensions": {
            "settings": {
                "ext1": {"state": 1, "manifest": {"permissions": ["<all_urls>"]}},
                "ext2": {"state": 1, "manifest": {"permissions": ["storage"]}},
                "ext3": {"state": 0, "manifest": {"permissions": ["<all_urls>"]}},  # disabled, should not count
            }
        },
    })
    result = parse_chrome_preferences(raw)
    assert result["safe_browsing"] is None  # frozen: always None, see dedicated test below
    assert result["autofill_passwords"] is False
    assert result["risky_extension_count"] == 1  # only ext1: enabled + broad permission


def test_chrome_preferences_safe_browsing_always_none_not_inferred():
    """Regression test for the closed Phase 1 investigation: real Windows
    diagnostics confirmed no legitimate Chrome Preferences boolean
    represents Safe Browsing protection state. safe_browsing must stay
    None even when the safebrowsing dict is present with plausible-looking
    but semantically wrong keys (e.g. scout_reporting_enabled_when_deprecated,
    a metrics-reporting toggle explicitly rejected as a substitute) —
    verifies the parser does NOT infer/fabricate a value from them."""
    raw = json.dumps({
        "safebrowsing": {
            "advanced_protection_last_refresh": "2026-08-01T00:00:00Z",
            "event_timestamps": {},
            "scout_reporting_enabled_when_deprecated": False,
            "unhandled_sync_password_reuses": {},
        }
    })
    result = parse_chrome_preferences(raw)
    assert result["safe_browsing"] is None, (
        "safe_browsing must remain None — scout_reporting_enabled_when_deprecated "
        "or any other unrelated boolean must never be substituted in"
    )


def test_chrome_preferences_missing_keys():
    raw = json.dumps({"some_other_key": True})
    result = parse_chrome_preferences(raw)
    assert result["safe_browsing"] is None
    assert result["autofill_passwords"] is None
    assert result["risky_extension_count"] is None


def test_chrome_preferences_autofill_nested_account_values():
    """Regression test for the REAL structure captured during Phase 1
    diagnostics on a real Chrome install: credentials_enable_service was
    found ONLY nested under account_values, not at the top level."""
    raw = json.dumps({"account_values": {"credentials_enable_service": True}})
    result = parse_chrome_preferences(raw)
    assert result["autofill_passwords"] is True


def test_chrome_preferences_autofill_nested_account_values_false():
    raw = json.dumps({"account_values": {"credentials_enable_service": False}})
    result = parse_chrome_preferences(raw)
    assert result["autofill_passwords"] is False


def test_chrome_preferences_autofill_legacy_top_level_still_works():
    """The original top-level path must keep working for any Chrome
    version/profile where it's still present — this was the pre-fix
    behavior and must not regress."""
    raw = json.dumps({"credentials_enable_service": True})
    result = parse_chrome_preferences(raw)
    assert result["autofill_passwords"] is True


def test_chrome_preferences_autofill_top_level_takes_precedence_if_both_present():
    raw = json.dumps({
        "credentials_enable_service": True,
        "account_values": {"credentials_enable_service": False},
    })
    result = parse_chrome_preferences(raw)
    assert result["autofill_passwords"] is True


def test_chrome_preferences_autofill_neither_path_present():
    raw = json.dumps({"unrelated_key": 123})
    result = parse_chrome_preferences(raw)
    assert result["autofill_passwords"] is None


def test_chrome_preferences_empty_input():
    result = parse_chrome_preferences(None)
    assert result == {"safe_browsing": None, "autofill_passwords": None, "risky_extension_count": None}
    result2 = parse_chrome_preferences("")
    assert result2["safe_browsing"] is None


def test_chrome_preferences_malformed_json():
    result = parse_chrome_preferences("{not valid json")
    assert result["safe_browsing"] is None


def run_all():
    tests = [v for k, v in globals().items() if k.startswith("test_") and callable(v)]
    passed, failed = 0, 0
    for t in tests:
        try:
            t()
            passed += 1
        except AssertionError as e:
            failed += 1
            print(f"FAIL: {t.__name__}: {e}")
        except Exception as e:
            failed += 1
            print(f"ERROR: {t.__name__}: {type(e).__name__}: {e}")
    print(f"\n{passed} passed, {failed} failed, {passed+failed} total")
    return failed == 0


if __name__ == "__main__":
    ok = run_all()
    sys.exit(0 if ok else 1)
