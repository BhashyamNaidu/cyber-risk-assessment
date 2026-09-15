"""
Database layer. SQLite for development; swap DATABASE_URL for Postgres in
production via config.py / .env — no hardcoded path here anymore.
"""
import uuid
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import create_engine, Column, String, Float, Boolean, DateTime, JSON, ForeignKey, Integer, text
from sqlalchemy.orm import declarative_base, sessionmaker, relationship

from .config import settings

Path(settings.model_dir).mkdir(exist_ok=True)
DATABASE_URL = settings.database_url

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class Device(Base):
    __tablename__ = "devices"
    device_id = Column(String, primary_key=True)
    first_seen_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    os_type = Column(String)
    scans = relationship("Scan", back_populates="device")


class Scan(Base):
    __tablename__ = "scans"
    scan_id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    device_id = Column(String, ForeignKey("devices.device_id"))
    scanned_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    degraded = Column(Boolean, default=False)
    risk_score = Column(Float)
    risk_tier = Column(String)
    ml_confidence = Column(Float, nullable=True)
    raw_telemetry = Column(JSON)
    findings_json = Column(JSON)
    recommendations_json = Column(JSON)
    assessment_json = Column(JSON)
    # Phase 2 (closed-loop intervention/validation system): marks a scan as
    # produced by the controlled-experiment path (baseline or post-intervention
    # rescan) rather than normal production agent use. Default False so every
    # pre-existing and ordinary scan is unaffected. Lets the dashboard's risk
    # history exclude experiment noise without needing a second scan table —
    # experiment scans still go through the exact same /scan scoring path and
    # are stored in this same table, just flagged.
    is_experiment = Column(Boolean, default=False, nullable=False)
    device = relationship("Device", back_populates="scans")


class Experiment(Base):
    """Phase 2: one row per experiment run (a batch of randomized trials
    against a specific disposable VM/endpoint). Holds no scoring logic and
    no duplicated telemetry — see ExperimentTrial for why."""
    __tablename__ = "experiments"
    experiment_id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String, nullable=True)
    description = Column(String, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    endpoint_id = Column(String, nullable=True)  # VM/snapshot identifier for this run, if fixed for the whole run
    trials = relationship("ExperimentTrial", back_populates="experiment")


class ExperimentTrial(Base):
    """Phase 2: one row per intervention trial. Baseline and post-intervention
    telemetry/risk/tier/findings are NEVER duplicated here — they live in the
    existing `scans` table (created via the exact same production /scan path)
    and are referenced by foreign key. This table only holds what's genuinely
    trial-specific: the recommendation being tested, the intervention's
    execution/verification outcome, and the resulting prediction-vs-actual
    validation numbers. `model_version` is persisted per trial (not just per
    experiment) without exception, per the project's reproducibility
    requirement — an experiment run must never be the unit that pins model
    version, in case models are ever retrained mid-run.

    Phase 2 provides ONLY this schema plus create/read persistence. No
    intervention execution, state verification, or validation-metric
    computation logic is implemented yet — those are Phases 4-7. Fields that
    those phases will populate (intervention/verification/validation columns)
    are all nullable/defaulted here so a trial row can be created immediately
    after a recommendation is chosen, then filled in incrementally.
    """
    __tablename__ = "experiment_trials"
    trial_id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    experiment_id = Column(String, ForeignKey("experiments.experiment_id"), nullable=False)
    order_position = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    endpoint_id = Column(String, nullable=True)  # VM/snapshot identifier, if it varies per trial
    model_version = Column(String, nullable=False)

    # Baseline — resolved via join to `scans`, never duplicated here.
    baseline_scan_id = Column(String, ForeignKey("scans.scan_id"), nullable=False)

    # Recommendation under test (from the counterfactual engine's existing output).
    intervention_id = Column(String, nullable=True)
    target_feature = Column(String, nullable=True)
    predicted_post_risk_score = Column(Float, nullable=True)
    predicted_delta = Column(Float, nullable=True)

    # Intervention execution (Phase 4+ populates these; Phase 2 only stores them).
    intervention_attempted = Column(Boolean, default=False, nullable=False)
    intervention_executed = Column(Boolean, default=False, nullable=False)
    intervention_executed_at = Column(DateTime, nullable=True)
    intervention_raw_result = Column(JSON, nullable=True)

    # Independent state verification (Phase 5+). Execution success and
    # verification success are intentionally two separate booleans — never
    # conflate "we ran the script" with "the state actually changed."
    verification_expected_state = Column(JSON, nullable=True)
    verification_observed_state = Column(JSON, nullable=True)
    verified = Column(Boolean, default=False, nullable=False)

    # Post-intervention rescan — only populated once verified=True, and only
    # ever a real Scan row produced by the same /scan path (Phase 6+).
    post_scan_id = Column(String, ForeignKey("scans.scan_id"), nullable=True)

    # Validation (Phase 7+). valid_for_metrics must be False until verified=True
    # AND a post_scan exists — Phase 7's metric computation must only ever
    # read trials where this is True.
    actual_delta = Column(Float, nullable=True)
    prediction_error = Column(Float, nullable=True)
    valid_for_metrics = Column(Boolean, default=False, nullable=False)

    notes = Column(String, nullable=True)

    experiment = relationship("Experiment", back_populates="trials")
    baseline_scan = relationship("Scan", foreign_keys=[baseline_scan_id])
    post_scan = relationship("Scan", foreign_keys=[post_scan_id])


def init_db(engine_=None):
    """Creates all tables and applies lightweight additive migrations.

    Accepts an optional engine so tests can exercise this exact function
    (including the migration branch) against an isolated database instead of
    the module-level dev engine. Existing callers (main.py's startup hook)
    call this with no arguments and get identical behavior to before.
    """
    target_engine = engine_ or engine
    target_url = str(target_engine.url)
    Base.metadata.create_all(bind=target_engine)
    # Lightweight SQLite migration for development databases created before
    # a given column existed. Other databases should use a normal migration.
    if target_url.startswith("sqlite"):
        with target_engine.begin() as connection:
            columns = {row[1] for row in connection.execute(text("PRAGMA table_info(scans)"))}
            if "assessment_json" not in columns:
                connection.execute(text("ALTER TABLE scans ADD COLUMN assessment_json JSON"))
            if "is_experiment" not in columns:
                connection.execute(text("ALTER TABLE scans ADD COLUMN is_experiment BOOLEAN DEFAULT 0 NOT NULL"))


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
