"""
Second diagnostic — narrowly scoped to fix a real bug in
diagnose_null_fields.py: its keyword search only printed a key if the
key's OWN name contained "safebrowsing"/"safe_browsing", so once it
recursed INTO the safebrowsing dict, none of the children (e.g. "enabled")
matched that substring and were silently never printed, even though they
were visited. This script reports the safebrowsing dict's direct children
unconditionally instead.

Privacy: prints ONLY key names, Python types, and boolean VALUES. Never
prints strings, numbers, lists, or nested dict contents beyond one level —
matches exactly what was requested: child key names, their types, boolean
values only.

Usage:
    python tests\\diagnose_safebrowsing_keys.py
"""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def main():
    local_appdata = os.environ.get("LOCALAPPDATA")
    if not local_appdata:
        print("LOCALAPPDATA not set.")
        sys.exit(1)

    pref_path = Path(local_appdata) / "Google" / "Chrome" / "User Data" / "Default" / "Preferences"
    if not pref_path.exists():
        print(f"Preferences file not found at {pref_path}")
        sys.exit(1)

    data = json.loads(pref_path.read_text(encoding="utf-8"))
    safebrowsing = data.get("safebrowsing")

    if not isinstance(safebrowsing, dict):
        print(f"'safebrowsing' key is not a dict (type: {type(safebrowsing).__name__}) — nothing to inspect.")
        sys.exit(0)

    print(f"'safebrowsing' has {len(safebrowsing)} direct child keys:\n")
    for key, value in safebrowsing.items():
        type_name = type(value).__name__
        if isinstance(value, bool):
            print(f"  {key}  (type: {type_name})  value: {value}")
        elif isinstance(value, dict):
            print(f"  {key}  (type: {type_name}, {len(value)} items)  value: <withheld, nested dict>")
        elif isinstance(value, list):
            print(f"  {key}  (type: {type_name}, {len(value)} items)  value: <withheld, list>")
        else:
            print(f"  {key}  (type: {type_name})  value: <withheld, not boolean>")

    print("\nCopy everything above and send it back. No URLs, timestamps,")
    print("account info, or other string/numeric values are printed above —")
    print("only key names, types, and boolean values.")


if __name__ == "__main__":
    import platform
    if platform.system() != "Windows":
        print("This must be run on Windows.")
        sys.exit(1)
    main()
