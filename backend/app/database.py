"""
Database layer. SQLite for development; swap DATABASE_URL for Postgres in
production via config.py / .env — no hardcoded path here anymore.
"""
import uuid
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import create_engine, Column, String, Float, Boolean, DateTime, JSON, ForeignKey, text
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
    device = relationship("Device", back_populates="scans")


def init_db():
    Base.metadata.create_all(bind=engine)
    # Lightweight SQLite migration for development databases created before
    # assessment_json existed. Other databases should use a normal migration.
    if DATABASE_URL.startswith("sqlite"):
        with engine.begin() as connection:
            columns = {row[1] for row in connection.execute(text("PRAGMA table_info(scans)"))}
            if "assessment_json" not in columns:
                connection.execute(text("ALTER TABLE scans ADD COLUMN assessment_json JSON"))


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
