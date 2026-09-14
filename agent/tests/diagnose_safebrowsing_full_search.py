"""
Third Safe Browsing diagnostic — broader than diagnose_safebrowsing_keys.py.

That script confirmed the `safebrowsing` object's 9 direct children contain
no `enabled`/protection-level boolean. This script does NOT assume the
relevant pref is nested under "safebrowsing" at all — Chrome may store it
elsewhere in the tree (this investigation already found one case,
credentials_enable_service, living under an unexpected path). It searches
the ENTIRE Preferences structure for boolean-valued keys whose name
suggests Safe Browsing / protection level / phishing-malware protection,
regardless of where they live.

Privacy: prints ONLY the key path, Python type, and the value IF it is a
boolean. Never prints strings, numbers, lists, timestamps, URLs, account
info, or nested dict/list contents.

Usage:
    python tests\\diagnose_safebrowsing_full_search.py
"""
import json
import os
import sys
from pathlib import Path

KEYWORDS = [
    "safe_browsing", "safebrowsing", "enhanced_protection", "standard_protection",
    "protection_level", "phishing", "malware", "real_time_protection",
]


def search(obj, path="", depth=0, max_depth=6, matches=None):
    if matches is None:
        matches = []
    if depth > max_depth:
        return matches
    if isinstance(obj, dict):
        for k, v in obj.items():
            current_path = f"{path}.{k}" if path else k
            if any(kw in k.lower() for kw in KEYWORDS) and isinstance(v, bool):
                matches.append((current_path, type(v).__name__, v))
            if isinstance(v, (dict, list)):
                search(v, current_path, depth + 1, max_depth, matches)
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            if isinstance(item, (dict, list)):
                search(item, f"{path}[{i}]", depth + 1, max_depth, matches)
    return matches


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

    matches = search(data, max_depth=6)

    print(f"Searched the entire Preferences tree (depth <= 6) for boolean keys matching: {KEYWORDS}\n")
    if not matches:
        print("NO boolean keys found anywhere in the tree matching these terms.")
        print("This is itself meaningful evidence — see the accompanying analysis.")
    else:
        print(f"Found {len(matches)} matching boolean key(s):\n")
        for path, type_name, value in matches:
            print(f"  {path}  (type: {type_name})  value: {value}")

    print("\nAlso listing ALL top-level keys for reference (names only, no values):")
    print(sorted(data.keys()))

    print("\nCopy everything above and send it back.")


if __name__ == "__main__":
    import platform
    if platform.system() != "Windows":
        print("This must be run on Windows.")
        sys.exit(1)
    main()
