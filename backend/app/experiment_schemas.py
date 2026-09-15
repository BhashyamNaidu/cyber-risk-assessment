"""
Phase 2 Pydantic schemas — closed-loop intervention/validation experiment
data model. Mirrors the existing schemas.py/services.py split: these are
pure data-shape definitions, no scoring or orchestration logic.

Scope note: Phase 2 is the data model only. Fields that later phases (4-7)
populate — intervention execution, independent state verification, and
predicted-vs-actual validation — are Optional here with safe defaults, so a
trial can be created immediately after a recommendation is chosen and filled
in incrementally as those phases land. Nothing here computes or fabricates
those values.
"""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class ExperimentCreate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    endpoint_id: Optional[str] = None


class ExperimentResponse(BaseModel):
    experiment_id: str
    name: Optional[str] = None
    description: Optional[str] = None
    created_at: datetime
    endpoint_id: Optional[str] = None

    class Config:
        from_attributes = True


class ExperimentTrialCreate(BaseModel):
    experiment_id: str
    order_position: int
    baseline_scan_id: str
    model_version: str
    endpoint_id: Optional[str] = None

    # Recommendation under test — optional at creation time; a trial may be
    # created to record "we selected this recommendation" before execution.
    intervention_id: Optional[str] = None
    target_feature: Optional[str] = None
    predicted_post_risk_score: Optional[float] = None
    predicted_delta: Optional[float] = None

    # Intervention/verification/validation fields are NOT accepted at
    # creation time — they are only ever set by later phases' own logic
    # (execution, verification, rescan, metric computation), never fabricated
    # or guessed by a caller constructing the initial trial record.


class ExperimentTrialUpdate(BaseModel):
    """Phase 2 provides this shape for completeness/round-trip testing of the
    schema; no endpoint or service function applies it yet — that wiring
    belongs to Phases 4-7, which own the actual execution/verification/
    validation logic this would drive."""
    intervention_attempted: Optional[bool] = None
    intervention_executed: Optional[bool] = None
    intervention_executed_at: Optional[datetime] = None
    intervention_raw_result: Optional[dict] = None

    verification_expected_state: Optional[dict] = None
    verification_observed_state: Optional[dict] = None
    verified: Optional[bool] = None

    post_scan_id: Optional[str] = None

    actual_delta: Optional[float] = None
    prediction_error: Optional[float] = None
    valid_for_metrics: Optional[bool] = None

    notes: Optional[str] = None


class ExperimentTrialResponse(BaseModel):
    trial_id: str
    experiment_id: str
    order_position: int
    created_at: datetime
    endpoint_id: Optional[str] = None
    model_version: str

    baseline_scan_id: str
    intervention_id: Optional[str] = None
    target_feature: Optional[str] = None
    predicted_post_risk_score: Optional[float] = None
    predicted_delta: Optional[float] = None

    intervention_attempted: bool = False
    intervention_executed: bool = False
    intervention_executed_at: Optional[datetime] = None
    intervention_raw_result: Optional[dict] = None

    verification_expected_state: Optional[dict] = None
    verification_observed_state: Optional[dict] = None
    verified: bool = False

    post_scan_id: Optional[str] = None

    actual_delta: Optional[float] = None
    prediction_error: Optional[float] = None
    valid_for_metrics: bool = False

    notes: Optional[str] = None

    class Config:
        from_attributes = True
