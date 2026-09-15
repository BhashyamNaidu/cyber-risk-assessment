"""
Phase 2 backward-compatibility tests.

Exercises the actual FastAPI route functions in app.main directly (not via
HTTP — httpx/TestClient are not installed in this environment, and adding a
new dependency for this is out of Phase 2's scope). Calling the route
functions directly runs the exact same code FastAPI would call per request;
only the transport layer is skipped, not the logic under test.

Uses an isolated temp-file SQLite database for every test — never the real
dev database at data/cyberrisk.db.
"""
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import init_db, Scan
from app import schemas, main as app_main


def _isolated_session():
    tmp_dir = tempfile.mkdtemp()
    db_path = Path(tmp_dir) / "test_backward_compat.db"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    init_db(engine_=engine)
    Session = sessionmaker(bind=engine)
    return Session()


FULL_PAYLOAD = schemas.TelemetryPayload(
    device_id="device-compat-full",
    os_type="Windows",
    os_days_since_update=150,
    firewall_enabled=False,
    antivirus_enabled=False,
    days_since_av_update=45,
    browser_safe_browsing_enabled=False,
    browser_autofill_passwords=True,
    risky_extension_count=3,
    collected_at=datetime.now(timezone.utc),
)

WINDOWS_PARTIAL_PAYLOAD = schemas.TelemetryPayload(
    device_id="device-compat-partial",
    os_type="Windows",
    os_days_since_update=8.0,
    firewall_enabled=True,
    antivirus_enabled=True,
    days_since_av_update=0.0,
    browser_safe_browsing_enabled=None,
    browser_autofill_passwords=True,
    risky_extension_count=0,
    collected_at=datetime.now(timezone.utc),
)


class PostScanBackwardCompatTests(unittest.TestCase):
    def test_post_scan_full_payload_unchanged_shape(self):
        db = _isolated_session()
        response = app_main.post_scan(FULL_PAYLOAD, db=db)
        self.assertIsInstance(response, schemas.ScanResponse)
        self.assertFalse(response.degraded)
        self.assertTrue(response.ml_used)
        self.assertEqual(response.ml_strategy, "full_7_feature")
        # is_experiment must NOT be part of the public response contract —
        # Phase 2 deliberately does not expand the API surface.
        self.assertNotIn("is_experiment", response.model_dump())
        db.close()

    def test_post_scan_creates_non_experiment_scan_by_default(self):
        db = _isolated_session()
        response = app_main.post_scan(FULL_PAYLOAD, db=db)
        stored = db.get(Scan, response.scan_id)
        self.assertFalse(stored.is_experiment, "scans created via normal /scan must default is_experiment=False")
        db.close()

    def test_post_scan_windows_partial_shape_unchanged(self):
        db = _isolated_session()
        response = app_main.post_scan(WINDOWS_PARTIAL_PAYLOAD, db=db)
        self.assertTrue(response.degraded)
        self.assertTrue(response.ml_used)
        self.assertEqual(response.ml_strategy, "observable_6_feature")
        self.assertIn("browser_safe_browsing_enabled", response.telemetry_unavailable_features)
        db.close()


class GetScanBackwardCompatTests(unittest.TestCase):
    def test_get_scan_by_id_still_works(self):
        db = _isolated_session()
        created = app_main.post_scan(FULL_PAYLOAD, db=db)
        fetched = app_main.get_scan(created.scan_id, db=db)
        self.assertEqual(fetched.scan_id, created.scan_id)
        db.close()

    def test_get_scan_404_still_works(self):
        from fastapi import HTTPException
        db = _isolated_session()
        with self.assertRaises(HTTPException) as ctx:
            app_main.get_scan("does-not-exist", db=db)
        self.assertEqual(ctx.exception.status_code, 404)
        db.close()


class DeviceHistoryExcludesExperimentScansTests(unittest.TestCase):
    def test_device_scans_excludes_experiment_rows(self):
        db = _isolated_session()
        device_id = "device-compat-history"
        payload1 = FULL_PAYLOAD.model_copy(update={"device_id": device_id})
        payload2 = WINDOWS_PARTIAL_PAYLOAD.model_copy(update={"device_id": device_id})
        app_main.post_scan(payload1, db=db)
        app_main.post_scan(payload2, db=db)

        # Simulate a future experiment-generated scan the way Phase 6+ will:
        # produced by the same pipeline, then flagged is_experiment=True.
        experiment_response = app_main.post_scan(
            FULL_PAYLOAD.model_copy(update={"device_id": device_id, "risky_extension_count": 0}), db=db,
        )
        experiment_scan = db.get(Scan, experiment_response.scan_id)
        experiment_scan.is_experiment = True
        db.commit()

        history = app_main.get_device_scans(device_id, limit=20, db=db)
        self.assertEqual(len(history.scans), 2, "experiment-flagged scan must not appear in device history")
        returned_ids = {s.scan_id for s in history.scans}
        self.assertNotIn(experiment_response.scan_id, returned_ids)
        db.close()

    def test_device_scans_unaffected_when_no_experiment_scans_exist(self):
        # Pure regression check: a device with only ordinary scans sees
        # identical history behavior to before this change.
        db = _isolated_session()
        device_id = "device-compat-no-experiments"
        payload = FULL_PAYLOAD.model_copy(update={"device_id": device_id})
        app_main.post_scan(payload, db=db)
        app_main.post_scan(payload, db=db)

        history = app_main.get_device_scans(device_id, limit=20, db=db)
        self.assertEqual(len(history.scans), 2)
        db.close()


class LatestScanAndHealthBackwardCompatTests(unittest.TestCase):
    def test_get_latest_scan_still_works(self):
        db = _isolated_session()
        device_id = "device-compat-latest"
        payload = FULL_PAYLOAD.model_copy(update={"device_id": device_id})
        created = app_main.post_scan(payload, db=db)
        latest = app_main.get_latest_scan(device_id, db=db)
        self.assertEqual(latest.scan_id, created.scan_id)
        db.close()

    def test_health_endpoint_unaffected(self):
        health = app_main.health()
        self.assertEqual(health.status, "ok")
        self.assertTrue(health.model_loaded)

    def test_model_info_endpoint_unaffected(self):
        info = app_main.model_info()
        self.assertIn("model_version", info)
        self.assertIn("observable_features_numeric", info)


if __name__ == "__main__":
    unittest.main()
