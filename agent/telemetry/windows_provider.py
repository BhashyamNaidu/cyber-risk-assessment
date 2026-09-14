"""
WindowsProvider — thin wrapper around PowerShell/WMI calls, delegating all
interpretation to parsers.py (which is unit-tested; this file is not, since
it requires an actual Windows host — see README note below).

*** VERIFICATION NOTE (read before trusting this in production) ***
This was written against documented PowerShell/WMI behavior and cannot be
executed in the development sandbox (Linux-only container). Before relying
on it: run `python -m agent.main --dry-run` on a real Windows machine and
confirm each field returns a plausible, non-None value. Treat any
persistent None as a signal the underlying command/format assumption needs
adjusting for that Windows build/locale, not as a bug in the parsers.
"""
import json
import logging
import subprocess
from pathlib import Path
from typing import Optional

from .base import TelemetryProvider
from .parsers import (
    parse_hotfix_date_to_days_since, parse_firewall_profiles_json,
    parse_av_product_state, parse_chrome_preferences,
)

logger = logging.getLogger("agent.telemetry.windows")

POWERSHELL_TIMEOUT_SECONDS = 15


def _run_powershell(command: str) -> Optional[str]:
    """Runs a PowerShell command, returns stdout or None on any failure.
    Never raises — the caller's `safe()` wrapper in base.py is a second
    layer of defense, but failing fast and locally here gives better log
    messages."""
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", command],
            capture_output=True, text=True, timeout=POWERSHELL_TIMEOUT_SECONDS,
        )
        if result.returncode != 0:
            logger.warning("PowerShell command failed (rc=%s): %s", result.returncode, result.stderr[:200])
            return None
        return result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
        logger.warning("PowerShell invocation error: %s", e)
        return None


class WindowsProvider(TelemetryProvider):
    @property
    def os_type(self) -> str:
        return "Windows"

    def get_os_days_since_update(self) -> Optional[float]:
        # Deliberately NOT using ConvertTo-Json here. Real evidence from
        # Phase 1 diagnostics (Windows 10, 10.0.26200) showed ConvertTo-Json
        # on a raw [datetime] serializes as a {value, DateTime} JSON OBJECT
        # rather than a bare string on this configuration. Requesting a
        # plain ISO-ish string via .ToString() sidesteps that ambiguity
        # entirely instead of parsing around it. (parsers.py still handles
        # the JSON-object form defensively as a fallback.)
        raw = _run_powershell(
            "Get-HotFix | Sort-Object -Property InstalledOn -Descending | "
            "Select-Object -First 1 -ExpandProperty InstalledOn | "
            "ForEach-Object { $_.ToString('yyyy-MM-ddTHH:mm:ss') }"
        )
        if raw is None:
            return None
        return parse_hotfix_date_to_days_since(raw.strip())

    def get_firewall_enabled(self) -> Optional[bool]:
        raw = _run_powershell("Get-NetFirewallProfile | Select-Object Enabled | ConvertTo-Json")
        return parse_firewall_profiles_json(raw)

    def get_antivirus_status(self) -> tuple[Optional[bool], Optional[float]]:
        raw = _run_powershell(
            "Get-CimInstance -Namespace root/SecurityCenter2 -ClassName AntiVirusProduct "
            "| Select-Object productState, timestamp | ConvertTo-Json"
        )
        if raw is None:
            return None, None
        try:
            data = json.loads(raw)
            if isinstance(data, list):
                data = data[0] if data else {}
            product_state = data.get("productState")
            enabled, up_to_date = parse_av_product_state(product_state)
            # timestamp field for freshness is AV-vendor-specific and often
            # unreliable across products — documented limitation: we report
            # up_to_date as a boolean (from the productState bitmask) rather
            # than a precise days-since-update figure, and pass a coarse
            # proxy (0 if up to date, 30 if not) to keep the same numeric
            # contract the backend expects.
            days_since_av_update = None if enabled is None else (0.0 if up_to_date else 30.0)
            return enabled, days_since_av_update
        except (json.JSONDecodeError, IndexError, TypeError) as e:
            logger.warning("Failed to parse antivirus WMI output: %s", e)
            return None, None

    def _read_chrome_preferences(self) -> Optional[str]:
        import os
        local_appdata = os.environ.get("LOCALAPPDATA")
        if not local_appdata:
            return None
        pref_path = Path(local_appdata) / "Google" / "Chrome" / "User Data" / "Default" / "Preferences"
        if not pref_path.exists():
            logger.info("Chrome Preferences file not found at %s (Chrome may not be installed)", pref_path)
            return None
        try:
            return pref_path.read_text(encoding="utf-8")
        except OSError as e:
            logger.warning("Could not read Chrome Preferences: %s", e)
            return None

    def get_browser_safe_browsing_enabled(self) -> Optional[bool]:
        raw = self._read_chrome_preferences()
        return parse_chrome_preferences(raw)["safe_browsing"] if raw else None

    def get_browser_autofill_passwords(self) -> Optional[bool]:
        raw = self._read_chrome_preferences()
        return parse_chrome_preferences(raw)["autofill_passwords"] if raw else None

    def get_risky_extension_count(self) -> Optional[int]:
        raw = self._read_chrome_preferences()
        return parse_chrome_preferences(raw)["risky_extension_count"] if raw else None
