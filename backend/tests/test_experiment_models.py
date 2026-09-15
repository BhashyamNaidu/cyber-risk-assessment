"""
Phase 2 tests — experiment data model.

Uses an isolated, temp-file SQLite database for every test (never the real
dev database at data/cyberrisk.db) via a fresh engine/session built directly
from app.database's Base/ORM classes. This is deliberate: these tests must
never touch or depend on real scan history.
"""
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, Device, Scan, Experiment, ExperimentTrial, init_db
from app import experiment_schemas, experiment_services


def _make_isolated_session_factory():
    tmp_dir = tempfile.mkdtemp()
    db_path = Path(tmp_dir) / "test_experiments.db"
    test_engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    init_db(engine_=test_engine)
    return test_engine, sessionmaker(bind=test_engine)


def _seed_device_and_scan(session, device_id="device-test-1", is_experiment=False, risk_score=50.0):
    device = session.get(Device, device_id)
    if device is None:
        device = Device(device_id=device_id, os_type="Windows")
        session.add(device)
        session.commit()
    scan = Scan(
        device_id=device_id,
        degraded=False,
        risk_score=risk_score,
        risk_tier="Medium",
        ml_confidence=0.9,
        raw_telemetry={"os_type": "Windows"},
        findings_json=[],
        recommendations_json=[],
        assessment_json={"ml_used": True, "ml_strategy": "full_7_feature"},
        is_experiment=is_experiment,
    )
    session.add(scan)
    session.commit()
    session.refresh(scan)
    return scan


class DatabaseInitIdempotencyTests(unittest.TestCase):
    def test_init_db_creates_all_tables(self):
        engine, _ = _make_isolated_session_factory()
        table_names = set(Base.metadata.tables.keys())
        self.assertEqual(
            table_names,
            {"devices", "scans", "experiments", "experiment_trials"},
        )

    def test_init_db_is_idempotent(self):
        engine, Session = _make_isolated_session_factory()
        # Calling init_db a second time against the same (now-populated)
        # database must not raise, must not duplicate columns, and must not
        # touch existing rows.
        session = Session()
        _seed_device_and_scan(session, device_id="device-idempotency")
        session.close()

        init_db(engine_=engine)  # second call — must be a no-op beyond ensuring schema

        session = Session()
        scans = session.query(Scan).filter(Scan.device_id == "device-idempotency").all()
        self.assertEqual(len(scans), 1, "second init_db() call must not duplicate or lose existing rows")
        session.close()

    def test_scans_table_has_is_experiment_column_after_migration_path(self):
        # Simulates a pre-Phase-2 database: create the `scans` table via
        # Base.metadata WITHOUT the is_experiment column (as it would have
        # existed before this change), then run init_db()'s migration path
        # and confirm the column gets added without data loss — the same
        # pattern already proven for assessment_json.
        import sqlalchemy as sa
        tmp_dir = tempfile.mkdtemp()
        db_path = Path(tmp_dir) / "pre_phase2.db"
        engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})

        legacy_meta = sa.MetaData()
        sa.Table(
            "devices", legacy_meta,
            sa.Column("device_id", sa.String, primary_key=True),
            sa.Column("first_seen_at", sa.DateTime),
            sa.Column("os_type", sa.String),
        )
        sa.Table(
            "scans", legacy_meta,
            sa.Column("scan_id", sa.String, primary_key=True),
            sa.Column("device_id", sa.String),
            sa.Column("scanned_at", sa.DateTime),
            sa.Column("degraded", sa.Boolean),
            sa.Column("risk_score", sa.Float),
            sa.Column("risk_tier", sa.String),
            sa.Column("ml_confidence", sa.Float),
            sa.Column("raw_telemetry", sa.JSON),
            sa.Column("findings_json", sa.JSON),
            sa.Column("recommendations_json", sa.JSON),
            sa.Column("assessment_json", sa.JSON),
            # deliberately NO is_experiment column
        )
        legacy_meta.create_all(bind=engine)
        with engine.begin() as conn:
            conn.execute(sa.text(
                "INSERT INTO devices (device_id, os_type) VALUES ('pre-existing-device', 'Windows')"
            ))
            conn.execute(sa.text(
                "INSERT INTO scans (scan_id, device_id, degraded, risk_score, risk_tier) "
                "VALUES ('pre-existing-scan', 'pre-existing-device', 0, 12.3, 'Low')"
            ))

        init_db(engine_=engine)  # must add is_experiment via ALTER, not lose the row above

        with engine.begin() as conn:
            columns = {row[1] for row in conn.execute(sa.text("PRAGMA table_info(scans)"))}
            self.assertIn("is_experiment", columns)
            row = conn.execute(sa.text(
                "SELECT scan_id, is_experiment FROM scans WHERE scan_id='pre-existing-scan'"
            )).fetchone()
            self.assertIsNotNone(row, "pre-existing scan row must survive the migration")
            self.assertEqual(row[1], 0, "migrated column must default existing rows to not-experiment")


class IsExperimentBehaviorTests(unittest.TestCase):
    def setUp(self):
        self.engine, self.Session = _make_isolated_session_factory()

    def test_is_experiment_defaults_to_false(self):
        session = self.Session()
        scan = _seed_device_and_scan(session, device_id="device-default")
        self.assertFalse(scan.is_experiment)
        session.close()

    def test_is_experiment_true_is_distinguishable(self):
        session = self.Session()
        normal = _seed_device_and_scan(session, device_id="device-mixed", is_experiment=False, risk_score=10.0)
        experiment = _seed_device_and_scan(session, device_id="device-mixed", is_experiment=True, risk_score=99.0)
        self.assertFalse(normal.is_experiment)
        self.assertTrue(experiment.is_experiment)
        session.close()

    def test_history_query_pattern_excludes_experiment_scans(self):
        # Mirrors exactly the filter main.py's get_device_scans now applies.
        session = self.Session()
        _seed_device_and_scan(session, device_id="device-history", is_experiment=False, risk_score=10.0)
        _seed_device_and_scan(session, device_id="device-history", is_experiment=True, risk_score=99.0)
        _seed_device_and_scan(session, device_id="device-history", is_experiment=False, risk_score=20.0)

        visible = (
            session.query(Scan)
            .filter(Scan.device_id == "device-history", Scan.is_experiment == False)  # noqa: E712
            .all()
        )
        self.assertEqual(len(visible), 2, "history must exclude the is_experiment=True row")
        self.assertTrue(all(not s.is_experiment for s in visible))
        self.assertTrue(all(s.risk_score != 99.0 for s in visible))
        session.close()


class ExperimentCreationTests(unittest.TestCase):
    def setUp(self):
        self.engine, self.Session = _make_isolated_session_factory()

    def test_create_experiment(self):
        session = self.Session()
        payload = experiment_schemas.ExperimentCreate(
            name="firewall-remediation-pilot", description="Pilot trial batch", endpoint_id="vm-snap-001",
        )
        experiment = experiment_services.create_experiment(session, payload)
        self.assertIsNotNone(experiment.experiment_id)
        self.assertEqual(experiment.name, "firewall-remediation-pilot")
        self.assertEqual(experiment.endpoint_id, "vm-snap-001")
        session.close()

    def test_create_experiment_round_trip_via_pydantic(self):
        session = self.Session()
        created = experiment_services.create_experiment(
            session, experiment_schemas.ExperimentCreate(name="rt-check")
        )
        session.close()

        session2 = self.Session()
        fetched = session2.get(Experiment, created.experiment_id)
        response = experiment_schemas.ExperimentResponse.model_validate(fetched)
        self.assertEqual(response.experiment_id, created.experiment_id)
        self.assertEqual(response.name, "rt-check")
        session2.close()


class ExperimentTrialCreationTests(unittest.TestCase):
    def setUp(self):
        self.engine, self.Session = _make_isolated_session_factory()
        session = self.Session()
        baseline_scan = _seed_device_and_scan(session, device_id="device-trial-target", risk_score=72.0)
        experiment = experiment_services.create_experiment(
            session, experiment_schemas.ExperimentCreate(name="autofill-trial")
        )
        # Capture plain IDs now — SQLAlchemy expires ORM attributes on every
        # commit() within a session (including a later, unrelated commit),
        # so holding onto the live objects across setUp -> test method
        # boundaries (with the session closed in between) is not reliable.
        self.baseline_scan_id = baseline_scan.scan_id
        self.experiment_id = experiment.experiment_id
        session.close()

    def test_create_experiment_trial(self):
        session = self.Session()
        payload = experiment_schemas.ExperimentTrialCreate(
            experiment_id=self.experiment_id,
            order_position=0,
            baseline_scan_id=self.baseline_scan_id,
            model_version="rf-v2-observable-windows",
            intervention_id="DISABLE_AUTOFILL",
            target_feature="browser_autofill_passwords",
            predicted_post_risk_score=20.3,
            predicted_delta=1.6,
        )
        trial = experiment_services.create_experiment_trial(session, payload)
        self.assertIsNotNone(trial.trial_id)
        self.assertEqual(trial.experiment_id, self.experiment_id)
        self.assertEqual(trial.baseline_scan_id, self.baseline_scan_id)
        self.assertEqual(trial.model_version, "rf-v2-observable-windows")
        # Phase 2 must not fabricate execution/verification/validation state.
        self.assertFalse(trial.intervention_attempted)
        self.assertFalse(trial.intervention_executed)
        self.assertFalse(trial.verified)
        self.assertIsNone(trial.post_scan_id)
        self.assertIsNone(trial.actual_delta)
        self.assertIsNone(trial.prediction_error)
        self.assertFalse(trial.valid_for_metrics)
        session.close()

    def test_experiment_trial_persistence_round_trip_via_pydantic(self):
        session = self.Session()
        created = experiment_services.create_experiment_trial(
            session,
            experiment_schemas.ExperimentTrialCreate(
                experiment_id=self.experiment_id,
                order_position=1,
                baseline_scan_id=self.baseline_scan_id,
                model_version="rf-v2-observable-windows",
                intervention_id="ENABLE_FIREWALL",
                target_feature="firewall_enabled",
                predicted_post_risk_score=48.0,
                predicted_delta=24.0,
            ),
        )
        created_trial_id = created.trial_id
        session.close()

        session2 = self.Session()
        fetched = session2.get(ExperimentTrial, created_trial_id)
        response = experiment_schemas.ExperimentTrialResponse.model_validate(fetched)
        self.assertEqual(response.trial_id, created_trial_id)
        self.assertEqual(response.intervention_id, "ENABLE_FIREWALL")
        self.assertEqual(response.predicted_delta, 24.0)
        self.assertEqual(response.baseline_scan_id, self.baseline_scan_id)
        session2.close()

    def test_create_trial_rejects_unknown_experiment_id(self):
        session = self.Session()
        payload = experiment_schemas.ExperimentTrialCreate(
            experiment_id="does-not-exist",
            order_position=0,
            baseline_scan_id=self.baseline_scan_id,
            model_version="rf-v2-observable-windows",
        )
        with self.assertRaises(ValueError):
            experiment_services.create_experiment_trial(session, payload)
        session.close()

    def test_create_trial_rejects_unknown_baseline_scan_id(self):
        session = self.Session()
        payload = experiment_schemas.ExperimentTrialCreate(
            experiment_id=self.experiment_id,
            order_position=0,
            baseline_scan_id="does-not-exist",
            model_version="rf-v2-observable-windows",
        )
        with self.assertRaises(ValueError):
            experiment_services.create_experiment_trial(session, payload)
        session.close()


if __name__ == "__main__":
    unittest.main()
