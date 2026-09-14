"""
LinuxProvider — PLACEHOLDER. Not implemented per the current scope freeze
(Windows-only for this milestone). Raising NotImplementedError explicitly
rather than returning all-None telemetry, so a caller on Linux gets a
clear signal at startup instead of a silently degraded scan.

When implemented, the intended data sources are:
  - OS update recency:      `/var/log/apt/history.log` (Debian/Ubuntu) or
                             `rpm -qa --last` (RHEL/Fedora)
  - Firewall status:        `ufw status` or `firewall-cmd --state`
  - Antivirus status:       ClamAV via `freshclam --version` / systemctl status clamav-daemon
                             (many Linux desktops have no AV — should return None honestly, not False)
  - Browser data:           same Chrome Preferences JSON approach as Windows,
                             at ~/.config/google-chrome/Default/Preferences
"""
from typing import Optional
from .base import TelemetryProvider


class LinuxProvider(TelemetryProvider):
    @property
    def os_type(self) -> str:
        return "Linux"

    def get_os_days_since_update(self) -> Optional[float]:
        raise NotImplementedError("LinuxProvider not yet implemented")

    def get_firewall_enabled(self) -> Optional[bool]:
        raise NotImplementedError("LinuxProvider not yet implemented")

    def get_antivirus_status(self) -> tuple:
        raise NotImplementedError("LinuxProvider not yet implemented")

    def get_browser_safe_browsing_enabled(self) -> Optional[bool]:
        raise NotImplementedError("LinuxProvider not yet implemented")

    def get_browser_autofill_passwords(self) -> Optional[bool]:
        raise NotImplementedError("LinuxProvider not yet implemented")

    def get_risky_extension_count(self) -> Optional[int]:
        raise NotImplementedError("LinuxProvider not yet implemented")
