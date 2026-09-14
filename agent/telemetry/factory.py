"""Factory: selects the correct TelemetryProvider for the running platform."""
import platform
import logging

from .base import TelemetryProvider
from .windows_provider import WindowsProvider
from .linux_provider import LinuxProvider
from .mac_provider import MacProvider

logger = logging.getLogger("agent.telemetry.factory")


class UnsupportedPlatformError(RuntimeError):
    pass


def get_provider() -> TelemetryProvider:
    system = platform.system()
    if system == "Windows":
        return WindowsProvider()
    elif system == "Linux":
        logger.warning("LinuxProvider selected but not yet implemented — this will raise on collect()")
        return LinuxProvider()
    elif system == "Darwin":
        logger.warning("MacProvider selected but not yet implemented — this will raise on collect()")
        return MacProvider()
    else:
        raise UnsupportedPlatformError(f"No telemetry provider for platform: {system}")
