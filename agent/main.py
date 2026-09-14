"""
Desktop Agent entrypoint.

Responsibilities (and ONLY these — see docs/architecture_v2.md):
  1. Collect telemetry (via telemetry.get_provider())
  2. Validate telemetry (client.validate_telemetry)
  3. Serialize telemetry (pydantic .model_dump inside client.send_scan)
  4. POST to backend (client.send_scan)
  5. Display backend results (client.display_result)

No scoring, no recommendation logic, no inference happens here — if you
find yourself computing anything risk-related in this file, it belongs on
the backend instead.
"""
import argparse
import logging
import sys

from pydantic import ValidationError
import requests

from config import settings
from logging_setup import setup_logging
from telemetry import get_provider, UnsupportedPlatformError
import client

logger = logging.getLogger("agent.main")


def run(dry_run: bool = False) -> int:
    setup_logging(settings.log_level, settings.log_format)

    try:
        provider = get_provider()
    except UnsupportedPlatformError as e:
        logger.error("Unsupported platform", extra={"error": str(e)})
        print(f"Error: {e}")
        return 1

    logger.info("Collecting telemetry", extra={"os_type": provider.os_type})
    try:
        raw = provider.collect()
    except NotImplementedError as e:
        logger.error("Provider not implemented for this platform", extra={"error": str(e)})
        print(f"Error: {e}")
        return 1

    if raw.collection_errors:
        logger.warning("Some telemetry fields failed to collect", extra={"errors": raw.collection_errors})

    device_id = client.get_or_create_device_id()

    try:
        payload = client.validate_telemetry(raw, device_id)
    except ValidationError as e:
        logger.error("Telemetry failed validation", extra={"error": str(e)})
        print(f"Error: collected telemetry failed validation:\n{e}")
        return 1

    if dry_run:
        print("Dry run — collected telemetry (not sent):")
        print(payload.model_dump_json(indent=2))
        if raw.collection_errors:
            print(f"\nCollection errors: {raw.collection_errors}")
        return 0

    try:
        result = client.send_scan(payload)
    except requests.RequestException as e:
        logger.error("Failed to send scan to backend", extra={"error": str(e)})
        print(f"Error: could not reach backend at {settings.backend_url}: {e}")
        return 1

    client.display_result(result)
    return 0


def main():
    parser = argparse.ArgumentParser(description="Cyber Risk Score Desktop Agent")
    parser.add_argument("--dry-run", action="store_true", help="Collect and validate telemetry but do not send it")
    args = parser.parse_args()
    sys.exit(run(dry_run=args.dry_run))


if __name__ == "__main__":
    main()
