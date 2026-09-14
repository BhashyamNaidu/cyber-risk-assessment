"""
Phase 1 smoke test — RUN THIS ON AN ACTUAL WINDOWS MACHINE.

This cannot be executed in the development sandbox (Linux-only container),
so it was never run end-to-end before today. It exercises WindowsProvider
directly (not through FakeProvider) and produces a structured report.

Usage (from the agent/ directory, on Windows):
    python tests\\windows_smoke_test.py

What to do with the output:
    1. Read the PASS/FAIL/NULL summary at the bottom.
    2. For any FAIL or unexpected NULL, copy the "raw output" shown for
       that field and send it back — that's almost always enough to fix
       the corresponding function in telemetry/parsers.py without needing
       another full round trip.
    3. Save the full report (it's also written to
       tests/windows_smoke_test_report.json) — this becomes the Phase 1
       entry in PROJECT_STATUS.md.
"""
import json
import sys
import platform
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from telemetry.windows_provider import WindowsProvider, _run_powershell


def check(label, fn):
    """Runs one collector, captures success/failure/value without letting
    an exception here stop the rest of the smoke test."""
    try:
        value = fn()
        status = "NULL (ran without error, but returned no data)" if value is None else "OK"
        return {"field": label, "status": status, "value": value, "error": None}
    except Exception as e:
        return {"field": label, "status": "FAIL", "value": None, "error": f"{type(e).__name__}: {e}"}


def main():
    print(f"Platform: {platform.system()} {platform.release()} ({platform.version()})")
    print(f"Python: {sys.version}\n")

    if platform.system() != "Windows":
        print("ERROR: this must be run on Windows. Aborting.")
        sys.exit(1)

    provider = WindowsProvider()
    results = []

    print("--- Checking raw PowerShell availability ---")
    ps_check = _run_powershell("Write-Output 'powershell-ok'")
    print(f"PowerShell reachable: {'YES' if ps_check == 'powershell-ok' else 'NO -> ' + repr(ps_check)}\n")

    print("--- Running each telemetry collector individually ---")
    results.append(check("os_days_since_update", provider.get_os_days_since_update))
    results.append(check("firewall_enabled", provider.get_firewall_enabled))

    av_result = check("antivirus_status (enabled, days_since_update)", lambda: provider.get_antivirus_status())
    results.append(av_result)

    results.append(check("browser_safe_browsing_enabled", provider.get_browser_safe_browsing_enabled))
    results.append(check("browser_autofill_passwords", provider.get_browser_autofill_passwords))
    results.append(check("risky_extension_count", provider.get_risky_extension_count))

    print("--- Running full collect() (as main.py would call it) ---")
    full = provider.collect()
    print(f"collection_errors from collect(): {full.collection_errors}\n")

    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    for r in results:
        print(f"[{r['status']:^45s}] {r['field']}: {r['value']!r}")
        if r["error"]:
            print(f"    -> {r['error']}")

    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "platform": f"{platform.system()} {platform.release()} ({platform.version()})",
        "powershell_reachable": ps_check == "powershell-ok",
        "field_results": results,
        "collect_result": {
            "os_type": full.os_type,
            "os_days_since_update": full.os_days_since_update,
            "firewall_enabled": full.firewall_enabled,
            "antivirus_enabled": full.antivirus_enabled,
            "days_since_av_update": full.days_since_av_update,
            "browser_safe_browsing_enabled": full.browser_safe_browsing_enabled,
            "browser_autofill_passwords": full.browser_autofill_passwords,
            "risky_extension_count": full.risky_extension_count,
            "collection_errors": full.collection_errors,
        },
    }
    out_path = Path(__file__).parent / "windows_smoke_test_report.json"
    out_path.write_text(json.dumps(report, indent=2))
    print(f"\nFull report written to: {out_path}")
    print("Send this file back (or paste its contents) to continue Phase 1.")


if __name__ == "__main__":
    main()
