"""
TelemetryProvider — the abstraction every OS-specific collector implements.

Design principle: this package has ZERO dependencies on FastAPI, the ML
code, or the Rule Engine (requirement #3). It only knows how to produce a
telemetry dict matching the backend's contract (docs/api_contract.md) — it
has no opinion about what happens to that data afterward.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass
class RawTelemetry:
    """Mirrors the TelemetryPayload fields in docs/api_contract.md, minus
    device_id/collected_at (added by the caller, not the provider). Any
    field the provider genuinely cannot read stays None — this is what
    powers the backend's graceful-degradation path. A provider must never
    guess or default a value on the agent side; only the backend decides
    what a missing field means."""
    os_type: str
    os_days_since_update: Optional[float] = None
    firewall_enabled: Optional[bool] = None
    antivirus_enabled: Optional[bool] = None
    days_since_av_update: Optional[float] = None
    browser_safe_browsing_enabled: Optional[bool] = None
    browser_autofill_passwords: Optional[bool] = None
    risky_extension_count: Optional[int] = None
    collection_errors: Optional[list] = None  # field-name -> reason, for logging/debugging only


class TelemetryProvider(ABC):
    """One implementation per OS. Every method returns None on failure —
    never raises out of a collect_* method, and never fabricates a value.
    A failed individual check should not abort the whole scan."""

    @abstractmethod
    def get_os_days_since_update(self) -> Optional[float]:
        ...

    @abstractmethod
    def get_firewall_enabled(self) -> Optional[bool]:
        ...

    @abstractmethod
    def get_antivirus_status(self) -> tuple[Optional[bool], Optional[float]]:
        """Returns (antivirus_enabled, days_since_av_update)."""
        ...

    @abstractmethod
    def get_browser_safe_browsing_enabled(self) -> Optional[bool]:
        ...

    @abstractmethod
    def get_browser_autofill_passwords(self) -> Optional[bool]:
        ...

    @abstractmethod
    def get_risky_extension_count(self) -> Optional[int]:
        ...

    @property
    @abstractmethod
    def os_type(self) -> str:
        ...

    def collect(self) -> RawTelemetry:
        """Template method: calls every collector, isolates failures per
        field so one broken check (e.g. permission denied on AV status)
        doesn't take down the whole scan."""
        errors = []
        telemetry = RawTelemetry(os_type=self.os_type)

        def safe(fn_name, fn, *field_names):
            try:
                result = fn()
                if len(field_names) == 1:
                    setattr(telemetry, field_names[0], result)
                else:
                    for name, val in zip(field_names, result):
                        setattr(telemetry, name, val)
            except NotImplementedError:
                # A whole-platform "not implemented yet" is categorically
                # different from one field failing on a supported platform
                # (e.g. permission denied) — it must propagate immediately
                # so the caller (main.py) fails fast with a clear message,
                # rather than silently collecting an all-null payload and
                # sending it to the backend as if it were a real degraded
                # scan. Only genuine per-field runtime failures are caught
                # below.
                raise
            except Exception as e:
                errors.append(f"{fn_name}: {type(e).__name__}: {e}")

        safe("os_update", self.get_os_days_since_update, "os_days_since_update")
        safe("firewall", self.get_firewall_enabled, "firewall_enabled")
        safe("antivirus", self.get_antivirus_status, "antivirus_enabled", "days_since_av_update")
        safe("safe_browsing", self.get_browser_safe_browsing_enabled, "browser_safe_browsing_enabled")
        safe("autofill", self.get_browser_autofill_passwords, "browser_autofill_passwords")
        safe("extensions", self.get_risky_extension_count, "risky_extension_count")

        telemetry.collection_errors = errors
        return telemetry
