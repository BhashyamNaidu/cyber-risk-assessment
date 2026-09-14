"""
MacProvider — PLACEHOLDER. Not implemented per the current scope freeze.

When implemented, the intended data sources are:
  - OS update recency:      `softwareupdate --history` or `system_profiler SPInstallHistoryDataType`
  - Firewall status:        `/usr/libexec/ApplicationFirewall/socketfilterfw --getglobalstate`
  - Antivirus status:       macOS has no built-in third-party AV registry equivalent to
                             SecurityCenter2 — would need per-vendor detection (XProtect is
                             built-in but not user-toggleable, so likely reports enabled=True
                             with a documented caveat, or None if not modeling XProtect)
  - Browser data:           same Chrome Preferences JSON approach, at
                             ~/Library/Application Support/Google/Chrome/Default/Preferences
"""
from typing import Optional
from .base import TelemetryProvider


class MacProvider(TelemetryProvider):
    @property
    def os_type(self) -> str:
        return "macOS"

    def get_os_days_since_update(self) -> Optional[float]:
        raise NotImplementedError("MacProvider not yet implemented")

    def get_firewall_enabled(self) -> Optional[bool]:
        raise NotImplementedError("MacProvider not yet implemented")

    def get_antivirus_status(self) -> tuple:
        raise NotImplementedError("MacProvider not yet implemented")

    def get_browser_safe_browsing_enabled(self) -> Optional[bool]:
        raise NotImplementedError("MacProvider not yet implemented")

    def get_browser_autofill_passwords(self) -> Optional[bool]:
        raise NotImplementedError("MacProvider not yet implemented")

    def get_risky_extension_count(self) -> Optional[int]:
        raise NotImplementedError("MacProvider not yet implemented")
