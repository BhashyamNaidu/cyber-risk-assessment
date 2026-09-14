"""
Diagnostic script for the three NULL fields found in the Phase 1 smoke
test. RUN THIS ON THE SAME WINDOWS MACHINE. It does not fix anything — it
only captures raw source data so the actual root cause can be identified
from evidence, not guessed.

Privacy note: for the Chrome Preferences inspection, this script does NOT
dump the whole file. It searches for keys matching known candidate names
and prints only keys whose value is a boolean (true/false) or explicitly
whitelisted as safe to show — never raw strings, form data, or anything
that could contain personal info. You can review the output before
sending it back.

Usage:
    python tests\\diagnose_null_fields.py
"""
import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from telemetry.windows_provider import _run_powershell


def section(title):
    print(f"\n{'=' * 70}\n{title}\n{'=' * 70}")


def run_ps_raw(label, command):
    print(f"\n--- {label} ---")
    print(f"Command: {command}")
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", command],
            capture_output=True, text=True, timeout=20,
        )
        print(f"Return code: {result.returncode}")
        print(f"STDOUT:\n{result.stdout}")
        if result.stderr.strip():
            print(f"STDERR:\n{result.stderr}")
    except Exception as e:
        print(f"FAILED TO RUN: {type(e).__name__}: {e}")


def diagnose_os_update():
    section("OS UPDATE RECENCY — raw diagnostics")

    run_ps_raw(
        "Get-HotFix, raw Format-List (shows if InstalledOn is genuinely null per-entry)",
        "Get-HotFix | Format-List HotFixID, InstalledOn",
    )
    run_ps_raw(
        "Get-HotFix count",
        "(Get-HotFix | Measure-Object).Count",
    )
    run_ps_raw(
        "Get-HotFix sorted descending, current agent command, raw (not stripped)",
        "Get-HotFix | Sort-Object -Property InstalledOn -Descending | Select-Object -First 1 -ExpandProperty InstalledOn | ConvertTo-Json",
    )
    run_ps_raw(
        "Get-HotFix filtered to non-null InstalledOn only, then sorted",
        "Get-HotFix | Where-Object { $_.InstalledOn -ne $null } | Sort-Object -Property InstalledOn -Descending | Select-Object -First 1 -ExpandProperty InstalledOn | ConvertTo-Json",
    )
    run_ps_raw(
        "Alternative source: registry LastSuccessTime for Windows Update",
        "(Get-ItemProperty 'HKLM:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\WindowsUpdate\\Auto Update\\Results\\Install' -ErrorAction SilentlyContinue).LastSuccessTime",
    )
    run_ps_raw(
        "Alternative source: Win32_QuickFixEngineering via CIM",
        "Get-CimInstance -ClassName Win32_QuickFixEngineering | Select-Object -First 3 HotFixID, InstalledOn | ConvertTo-Json",
    )


def diagnose_chrome_preferences():
    section("CHROME PREFERENCES — raw diagnostics (privacy-filtered)")

    local_appdata = os.environ.get("LOCALAPPDATA")
    print(f"LOCALAPPDATA: {local_appdata}")
    if not local_appdata:
        print("LOCALAPPDATA not set — cannot locate Chrome profile.")
        return

    pref_path = Path(local_appdata) / "Google" / "Chrome" / "User Data" / "Default" / "Preferences"
    print(f"Expected Preferences path: {pref_path}")
    print(f"File exists: {pref_path.exists()}")

    if not pref_path.exists():
        # Check if Chrome is installed at all under a different profile name
        chrome_user_data = Path(local_appdata) / "Google" / "Chrome" / "User Data"
        if chrome_user_data.exists():
            profiles = [p.name for p in chrome_user_data.iterdir() if p.is_dir()]
            print(f"Chrome User Data exists but 'Default' not found. Profiles present: {profiles}")
        else:
            print("Chrome User Data directory does not exist at all — Chrome may not be installed, "
                  "or is installed for a different user/in a non-standard location.")
        return

    try:
        raw = pref_path.read_text(encoding="utf-8")
    except OSError as e:
        print(f"Could not read file: {e}")
        return

    print(f"File read OK, {len(raw)} bytes")

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"JSON parse FAILED: {e}")
        return

    print("JSON parsed OK.")
    print(f"\nTop-level keys present in Preferences file ({len(data.keys())} total):")
    print(sorted(data.keys()))

    print("\n--- Searching for safe-browsing related keys (boolean values only, privacy-safe) ---")
    _search_and_print(data, ["safebrowsing", "safe_browsing"], path="")

    print("\n--- Searching for password/credential/autofill related keys (boolean values only) ---")
    _search_and_print(data, ["credential", "password", "autofill"], path="")


def _search_and_print(obj, keywords, path, depth=0, max_depth=4):
    if depth > max_depth:
        return
    if isinstance(obj, dict):
        for k, v in obj.items():
            current_path = f"{path}.{k}" if path else k
            if any(kw in k.lower() for kw in keywords):
                if isinstance(v, bool):
                    print(f"  {current_path} = {v}  (bool — safe to report)")
                elif isinstance(v, (dict, list)):
                    print(f"  {current_path} = <{type(v).__name__}, {len(v)} items> (inspecting children below)")
                else:
                    print(f"  {current_path} = <{type(v).__name__}> (value withheld — not a boolean, might be sensitive)")
            if isinstance(v, dict):
                _search_and_print(v, keywords, current_path, depth + 1, max_depth)


if __name__ == "__main__":
    import platform
    if platform.system() != "Windows":
        print("This must be run on Windows.")
        sys.exit(1)

    diagnose_os_update()
    diagnose_chrome_preferences()

    print("\n\n" + "=" * 70)
    print("Copy everything above and send it back. No passwords, form data,")
    print("or personal info should appear in this output — only key names")
    print("and boolean values relevant to our 3 telemetry fields.")
    print("=" * 70)
