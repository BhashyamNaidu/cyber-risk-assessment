"""
Pure parsing functions for Windows telemetry sources — deliberately
separated from windows_provider.py's subprocess/registry calls so this
logic is unit-testable on ANY platform (see agent/tests/test_parsers.py).
windows_provider.py is a thin wrapper: call OS API -> pass raw output here.

Documented data sources (verify exact output format on a real Windows
machine before trusting this in production — see README note in
windows_provider.py):
  - OS update recency:      PowerShell `Get-HotFix | Sort InstalledOn -Descending`
  - Firewall status:        PowerShell `Get-NetFirewallProfile`
  - Antivirus status:       WMI root/SecurityCenter2 AntiVirusProduct.productState
  - Browser safe-browsing:  UNAVAILABLE from this telemetry source on
                             real Chrome installations (confirmed via
                             Phase 1 diagnostics on Windows 10, 10.0.26200
                             — see parse_chrome_preferences() below).
  - Browser autofill:       Chrome `Preferences` JSON, key "credentials_enable_service"
  - Extensions:             Chrome `Preferences` JSON, "extensions.settings" dict
"""
import json
from datetime import datetime, timezone
from typing import Optional


def parse_hotfix_date_to_days_since(date_str: str, now: Optional[datetime] = None) -> Optional[float]:
    """Parses the InstalledOn value from Get-HotFix into days-since-now.

    Two real formats have been observed on actual Windows/PowerShell
    machines (captured during Phase 1 diagnostics):
      1. A plain ISO-ish string, e.g. '2026-08-12T00:00:00' (what
         windows_provider.py now requests via .ToString(), see below).
      2. A JSON OBJECT (not a bare string) when a caller pipes InstalledOn
         directly through ConvertTo-Json on some PS/culture configs:
         {"value": "/Date(1786473000000)/", "DateTime": "12 August 2026 00:00:00"}
         Confirmed on Windows 10 (10.0.26200) during Phase 1 diagnostics —
         this is why windows_provider.py no longer uses ConvertTo-Json for
         this field, but this branch stays as a defensive fallback in case
         a future PS version reverts to this behavior.
    """
    if not date_str:
        return None
    now = now or datetime.now(timezone.utc)
    try:
        date_str = date_str.strip()
        if date_str.startswith("{"):
            try:
                obj = json.loads(date_str)
            except json.JSONDecodeError:
                return None
            date_str = obj.get("value") or ""
            if not date_str:
                return None
        if date_str.startswith("/Date(") and date_str.endswith(")/"):
            millis = int(date_str[6:-2].split("+")[0].split("-")[0])
            dt = datetime.fromtimestamp(millis / 1000.0, tz=timezone.utc)
        else:
            dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
        delta = now - dt
        return max(delta.total_seconds() / 86400.0, 0.0)
    except (ValueError, IndexError, TypeError):
        return None


def parse_firewall_profiles_json(raw_json: str) -> Optional[bool]:
    """`Get-NetFirewallProfile | Select Enabled | ConvertTo-Json` returns a
    list of {"Enabled": 1} or {"Enabled": 0} per profile (Domain/Private/
    Public). We treat the firewall as enabled only if ALL profiles are
    enabled — a single disabled profile is a real gap an attacker on that
    network type could exploit."""
    if not raw_json:
        return None
    try:
        data = json.loads(raw_json)
        if isinstance(data, dict):
            data = [data]
        if not data:
            return None
        return all(bool(profile.get("Enabled")) for profile in data)
    except (json.JSONDecodeError, TypeError):
        return None


# SecurityCenter2 AntiVirusProduct.productState is a 3-byte bitmask.
# Byte layout (widely documented, reverse-engineered by the security
# community since Microsoft never published it officially — flag this
# provenance honestly in the viva if asked):
#   middle byte: enabled/disabled state (0x10 = enabled for some products,
#   0x11 = enabled for others depending on product type bit)
#   last byte:   0x00 = up to date, non-zero = out of date (approximate)
def parse_av_product_state(product_state: Optional[int]) -> tuple[Optional[bool], Optional[bool]]:
    """Returns (enabled, up_to_date). Both None if product_state is None."""
    if product_state is None:
        return None, None
    hex_str = f"{product_state:06x}"
    middle_byte = int(hex_str[2:4], 16)
    last_byte = int(hex_str[4:6], 16)
    enabled = middle_byte in (0x10, 0x11)
    up_to_date = last_byte == 0x00
    return enabled, up_to_date


def parse_chrome_preferences(raw_json: str) -> dict:
    """Returns {'safe_browsing': bool|None, 'autofill_passwords': bool|None,
    'risky_extension_count': int|None} from a Chrome Preferences file's
    raw text content. Missing keys -> None for that field specifically,
    not for the whole result (partial data is still useful)."""
    result = {"safe_browsing": None, "autofill_passwords": None, "risky_extension_count": None}
    if not raw_json:
        return result
    try:
        data = json.loads(raw_json)
    except json.JSONDecodeError:
        return result

    # browser_safe_browsing_enabled: INTENTIONALLY always None. Confirmed
    # via Phase 1 diagnostics on a real Windows 10 (10.0.26200) machine
    # that no legitimate local Chrome Preferences boolean reliably
    # represents Safe Browsing protection state:
    #   - safebrowsing.enabled does not exist in this Chrome version.
    #   - A full-tree search (depth<=6) for keys matching safe_browsing/
    #     safebrowsing/enhanced_protection/standard_protection/
    #     protection_level/phishing/malware/real_time_protection found no
    #     matching boolean anywhere in the file.
    #   - safebrowsing.scout_reporting_enabled_when_deprecated is a
    #     metrics-reporting toggle, NOT the protection state, and must
    #     NEVER be substituted here (explicitly rejected, not an oversight).
    # This is a genuine telemetry-source limitation, not a parser bug.
    # Semantics: "unknown/unavailable from this telemetry source" —
    # None here must never be treated as "disabled".

    if "credentials_enable_service" in data:
        result["autofill_passwords"] = bool(data["credentials_enable_service"])
    elif isinstance(data.get("account_values"), dict) and "credentials_enable_service" in data["account_values"]:
        # PRIMARY path on modern Chrome (confirmed via real Windows 10
        # diagnostics, Phase 1): this key was NOT found at the top level on
        # a real Chrome installation, only nested under "account_values".
        # Top-level check above is kept as a fallback for older Chrome
        # versions that may still use it, checked first only because it was
        # this module's original assumption, not because it's more likely.
        # CAVEAT (unconfirmed): "account_values" may denote a signed-in
        # Chrome account's synced setting. Behavior for signed-out
        # profiles is not yet verified — if this field is unexpectedly
        # None on a signed-out machine, that is the next thing to check,
        # not a regression.
        result["autofill_passwords"] = bool(data["account_values"]["credentials_enable_service"])

    extensions_present = "extensions" in data
    extensions = data.get("extensions", {}).get("settings", {})
    if extensions_present and isinstance(extensions, dict):
        # Heuristic (documented limitation): count enabled extensions
        # requesting broad host permissions ("<all_urls>" or "*://*/*") as
        # "risky". Extensions without a readable manifest are skipped, not
        # counted as risky by default (avoid overcounting on incomplete data).
        risky = 0
        for ext_id, ext_data in extensions.items():
            if not isinstance(ext_data, dict) or ext_data.get("state") != 1:  # 1 = enabled
                continue
            manifest = ext_data.get("manifest", {})
            perms = manifest.get("permissions", []) + manifest.get("host_permissions", [])
            if any(p in ("<all_urls>", "*://*/*", "http://*/*", "https://*/*") for p in perms):
                risky += 1
        result["risky_extension_count"] = risky

    return result
