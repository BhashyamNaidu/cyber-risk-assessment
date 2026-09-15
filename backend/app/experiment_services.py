"""
Phase 2 experiment persistence — orchestration only, no scoring logic, no
intervention/verification/validation logic. Mirrors services.py's existing
"orchestration only" convention.

Deliberately does NOT re-run or duplicate any scoring: `baseline_scan_id`
and `post_scan_id` must reference rows already created by the normal
`/scan` pipeline (services.run_pipeline via main.post_scan) — this module
never computes a risk score itself.
"""
from sqlalchemy.orm import Session

from . import experiment_schemas
from .database import Experiment, ExperimentTrial, Scan


def create_experiment(db: Session, payload: experiment_schemas.ExperimentCreate) -> Experiment:
    experiment = Experiment(
        name=payload.name,
        description=payload.description,
        endpoint_id=payload.endpoint_id,
    )
    db.add(experiment)
    db.commit()
    db.refresh(experiment)
    return experiment


def create_experiment_trial(db: Session, payload: experiment_schemas.ExperimentTrialCreate) -> ExperimentTrial:
    """Creates a trial row referencing an already-persisted baseline Scan.

    Raises ValueError if experiment_id or baseline_scan_id don't reference
    existing rows — fails loudly rather than silently creating an orphaned
    foreign key, since a broken trial record would be worse than no record.
    """
    if db.get(Experiment, payload.experiment_id) is None:
        raise ValueError(f"No experiment with experiment_id={payload.experiment_id!r}")
    if db.get(Scan, payload.baseline_scan_id) is None:
        raise ValueError(f"No scan with baseline_scan_id={payload.baseline_scan_id!r}")

    trial = ExperimentTrial(
        experiment_id=payload.experiment_id,
        order_position=payload.order_position,
        baseline_scan_id=payload.baseline_scan_id,
        model_version=payload.model_version,
        endpoint_id=payload.endpoint_id,
        intervention_id=payload.intervention_id,
        target_feature=payload.target_feature,
        predicted_post_risk_score=payload.predicted_post_risk_score,
        predicted_delta=payload.predicted_delta,
    )
    db.add(trial)
    db.commit()
    db.refresh(trial)
    return trial
