"""
Thin client — collect, validate, serialize, POST, display. No scoring, no
recommendation logic, no inference. Every intelligent decision happens on
the backend; this file is intentionally boring.
"""
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import requests
from pydantic import BaseModel, ValidationError, Field
from typing import Literal

from telemetry.base import RawTelemetry
from config import settings

logger = logging.getLogger("agent.client")


# Mirrors backend/app/schemas.py::TelemetryPayload exactly. Deliberately
# duplicated rather than imported — the agent package must stay independent
# of the backend (requirement #3). If the contract in docs/api_contract.md
# changes, BOTH this class and backend/app/schemas.py must be updated
# together; this is a known, accepted coupling cost of the independence
# requirement, not an oversight.
class TelemetryPayload(BaseModel):
    device_id: str
    os_type: Literal["Windows", "macOS", "Linux"]
    os_days_since_update: Optional[float] = None
    firewall_enabled: Optional[bool] = None
    antivirus_enabled: Optional[bool] = None
    days_since_av_update: Optional[float] = None
    browser_safe_browsing_enabled: Optional[bool] = None
    browser_autofill_passwords: Optional[bool] = None
    risky_extension_count: Optional[int] = None
    collected_at: datetime


def get_or_create_device_id() -> str:
    """Stable per-device identifier, persisted locally so repeat scans from
    the same machine link to the same scan history on the backend."""
    path = Path(settings.device_id_file).expanduser()
    if path.exists():
        return path.read_text().strip()
    path.parent.mkdir(parents=True, exist_ok=True)
    new_id = f"device-{uuid.uuid4().hex[:12]}"
    path.write_text(new_id)
    logger.info("Generated new device_id", extra={"device_id": new_id})
    return new_id


def validate_telemetry(raw: RawTelemetry, device_id: str) -> TelemetryPayload:
    """Raises pydantic.ValidationError if the collected telemetry can't
    even form a structurally valid payload (e.g. os_type somehow empty).
    This is a client-side sanity check — it does NOT decide whether the
    scan is "good enough"; that's the backend's degraded-mode logic."""
    return TelemetryPayload(
        device_id=device_id,
        os_type=raw.os_type,
        os_days_since_update=raw.os_days_since_update,
        firewall_enabled=raw.firewall_enabled,
        antivirus_enabled=raw.antivirus_enabled,
        days_since_av_update=raw.days_since_av_update,
        browser_safe_browsing_enabled=raw.browser_safe_browsing_enabled,
        browser_autofill_passwords=raw.browser_autofill_passwords,
        risky_extension_count=raw.risky_extension_count,
        collected_at=datetime.now(timezone.utc),
    )


def send_scan(payload: TelemetryPayload) -> dict:
    """POST to /scan. Raises requests.RequestException on network failure
    or a non-2xx response — the caller (main.py) decides how to present
    that to the user; this function does not swallow errors silently."""
    url = f"{settings.backend_url}/scan"
    body = payload.model_dump(mode="json")
    logger.info("Sending scan", extra={"url": url, "device_id": payload.device_id})

    response = requests.post(url, json=body, timeout=settings.request_timeout_seconds)
    response.raise_for_status()

    result = response.json()
    logger.info(
        "Scan complete",
        extra={
            "scan_id": result.get("scan_id"),
            "risk_score": result.get("risk_score"),
            "risk_tier": result.get("risk_tier"),
            "degraded": result.get("degraded"),
        },
    )
    return result


def display_result(result: dict):
    """Plain console display — the real dashboard is a separate,
    not-yet-built component. This exists so the agent is usable/testable
    standalone before that UI exists."""
    print(f"\nCyber Risk Score: {result['risk_score']}/100  ({result['risk_tier']})")
    if result.get("degraded"):
        if result.get("ml_used"):
            print("  [PARTIAL TELEMETRY — ML assessment used available security signals]")
        else:
            print("  [PARTIAL SCAN — ML was unavailable; score uses fallback rules only]")
    if result.get("ml_confidence") is not None:
        print(f"  Model confidence: {result['ml_confidence']:.0%}")

    findings = result.get("findings", [])
    if findings:
        print(f"\nFindings ({len(findings)}):")
        for f in findings:
            print(f"  [{f['severity_0_10']:.1f}] {f['title']}")
            print(f"        -> {f['recommendation']}")

    recs = result.get("recommendations", [])
    if recs:
        print(f"\nTop recommendations by expected impact:")
        for r in recs:
            print(f"  {r['action']:40s} -{r['expected_reduction']:.1f} points")
