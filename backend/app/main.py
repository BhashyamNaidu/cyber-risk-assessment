"""
FastAPI backend — implements docs/api_contract.md exactly.
Run with: uvicorn app.main:app --reload --port 8000
Swagger UI: http://localhost:8000/docs
"""
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, Depends, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from . import schemas, services
from .database import init_db, get_db, Device, Scan
from .config import settings
from .logging_setup import setup_logging, RequestLoggingMiddleware

setup_logging(settings.log_level, settings.log_format)

app = FastAPI(
    title="Smart Personal Cyber Risk Score Calculator — API",
    version="1.0",
    description="Backend contract per docs/api_contract.md. The Desktop Agent is a thin client that only calls POST /scan.",
)
app.add_middleware(RequestLoggingMiddleware)

# Minimal CORS for local dashboard development only. Scoped to the exact
# origins the dashboard is served from (docs/phase3_e2e_procedure.md ->
# `python -m http.server 5500` from dashboard/), NOT a wildcard. No new
# routes, schemas, or auth introduced — this is integration/packaging
# plumbing so the already-frozen dashboard can reach the already-frozen
# API in a browser, not an architecture change.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5500", "http://127.0.0.1:5500"],
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


@app.on_event("startup")
def startup():
    init_db()


def _scan_to_response(scan: Scan) -> schemas.ScanResponse:
    assessment = scan.assessment_json or {}
    return schemas.ScanResponse(
        scan_id=scan.scan_id,
        device_id=scan.device_id,
        scanned_at=scan.scanned_at,
        degraded=scan.degraded,
        risk_score=scan.risk_score,
        risk_tier=scan.risk_tier,
        ml_confidence=scan.ml_confidence,
        ml_used=assessment.get("ml_used", False),
        ml_strategy=assessment.get("ml_strategy"),
        telemetry_observed_features=assessment.get("telemetry_observed_features", []),
        telemetry_unavailable_features=assessment.get("telemetry_unavailable_features", []),
        ml_explanation=assessment.get("ml_explanation", []),
        findings=scan.findings_json or [],
        recommendations=scan.recommendations_json or [],
    )


@app.post("/scan", response_model=schemas.ScanResponse)
def post_scan(payload: schemas.TelemetryPayload, db: Session = Depends(get_db)):
    # mode="json" converts datetime -> ISO string so it can be stored in the
    # SQLite JSON column below (a plain .model_dump() keeps it as a Python
    # datetime object, which json.dumps cannot serialize — caught this via
    # an end-to-end curl test against the running server, not just review).
    telemetry = payload.model_dump(mode="json")

    device = db.get(Device, payload.device_id)
    if device is None:
        device = Device(device_id=payload.device_id, os_type=payload.os_type)
        db.add(device)
        db.commit()

    result = services.run_pipeline(telemetry)

    scan = Scan(
        device_id=payload.device_id,
        scanned_at=datetime.now(timezone.utc),
        degraded=result["degraded"],
        risk_score=result["risk_score"],
        risk_tier=result["risk_tier"],
        ml_confidence=result["ml_confidence"],
        raw_telemetry=telemetry,
        findings_json=result["findings"],
        recommendations_json=result["recommendations"],
        assessment_json={
            "ml_used": result["ml_used"],
            "ml_strategy": result["ml_strategy"],
            "telemetry_observed_features": result["telemetry_observed_features"],
            "telemetry_unavailable_features": result["telemetry_unavailable_features"],
            "ml_explanation": result["ml_explanation"],
        },
    )
    db.add(scan)
    db.commit()
    db.refresh(scan)

    return _scan_to_response(scan)


@app.get("/scans/{scan_id}", response_model=schemas.ScanResponse)
def get_scan(scan_id: str, db: Session = Depends(get_db)):
    scan = db.get(Scan, scan_id)
    if scan is None:
        raise HTTPException(status_code=404, detail="Scan not found")
    return _scan_to_response(scan)


@app.get("/devices/{device_id}/scans", response_model=schemas.DeviceScanHistory)
def get_device_scans(device_id: str, limit: int = Query(20, le=100), db: Session = Depends(get_db)):
    device = db.get(Device, device_id)
    if device is None:
        raise HTTPException(status_code=404, detail="Device not found")
    scans = (
        db.query(Scan)
        .filter(Scan.device_id == device_id)
        .order_by(Scan.scanned_at.desc())
        .limit(limit)
        .all()
    )
    return schemas.DeviceScanHistory(
        device_id=device_id,
        scans=[
            schemas.ScanSummary(
                scan_id=s.scan_id, scanned_at=s.scanned_at,
                risk_score=s.risk_score, risk_tier=s.risk_tier,
            ) for s in scans
        ],
    )


@app.get("/devices/{device_id}/latest", response_model=schemas.ScanResponse)
def get_latest_scan(device_id: str, db: Session = Depends(get_db)):
    scan = (
        db.query(Scan)
        .filter(Scan.device_id == device_id)
        .order_by(Scan.scanned_at.desc())
        .first()
    )
    if scan is None:
        raise HTTPException(status_code=404, detail="No scans yet for this device")
    return _scan_to_response(scan)


@app.get("/health", response_model=schemas.HealthResponse)
def health():
    return schemas.HealthResponse(
        status="ok",
        model_loaded=services.model_is_loaded(),
        model_version=services.model_version_info().get("model_version"),
    )


@app.get("/model/info")
def model_info():
    info = services.model_version_info()
    if not info:
        raise HTTPException(status_code=503, detail="Model not loaded — run ml/train_final_model.py first")
    return info
