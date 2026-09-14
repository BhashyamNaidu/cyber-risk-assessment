"""Pydantic schemas — the runtime enforcement of docs/api_contract.md."""
from datetime import datetime
from typing import Optional, Literal
from pydantic import BaseModel, Field


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

    class Config:
        json_schema_extra = {
            "example": {
                "device_id": "device-abc123",
                "os_type": "Windows",
                "os_days_since_update": 150,
                "firewall_enabled": False,
                "antivirus_enabled": False,
                "days_since_av_update": 45,
                "browser_safe_browsing_enabled": False,
                "browser_autofill_passwords": True,
                "risky_extension_count": 3,
                "collected_at": "2026-08-06T10:00:00Z",
            }
        }


class Finding(BaseModel):
    id: str
    title: str
    severity_0_10: float
    cvss_rationale: str
    recommendation: str
    feature: Optional[str] = None


class Recommendation(BaseModel):
    action: str
    feature: str
    current_score: float
    expected_score_after_fix: float
    expected_reduction: float


class ModelExplanation(BaseModel):
    feature: str
    value: float | bool | int | None
    importance: float
    kind: Literal["global_model_importance"]


class ScanResponse(BaseModel):
    scan_id: str
    device_id: str
    scanned_at: datetime
    degraded: bool
    risk_score: float
    risk_tier: Literal["Low", "Medium", "High"]
    ml_confidence: Optional[float] = None
    ml_used: bool = False
    ml_strategy: Optional[str] = None
    telemetry_observed_features: list[str] = Field(default_factory=list)
    telemetry_unavailable_features: list[str] = Field(default_factory=list)
    ml_explanation: list[ModelExplanation] = Field(default_factory=list)
    findings: list[Finding] = Field(default_factory=list)
    recommendations: list[Recommendation] = Field(default_factory=list)


class ScanSummary(BaseModel):
    scan_id: str
    scanned_at: datetime
    risk_score: float
    risk_tier: Literal["Low", "Medium", "High"]


class DeviceScanHistory(BaseModel):
    device_id: str
    scans: list[ScanSummary]


class HealthResponse(BaseModel):
    status: str
    model_loaded: bool
    model_version: Optional[str] = None
