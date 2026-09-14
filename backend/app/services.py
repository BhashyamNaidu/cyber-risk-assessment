"""Services layer — orchestration only, no scoring logic of its own."""
import sys
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "ml"))

import joblib
import pandas as pd

from rule_engine import generate_findings, rule_based_score
from train_final_model import (
    build_feature_matrix, expected_risk_score, FEATURES_NUMERIC,
    OBSERVABLE_FEATURES_NUMERIC,
)
from counterfactual_recommender import CounterfactualRecommender
from paths import MODEL_PATH, OBSERVABLE_MODEL_PATH, ENCODER_PATH, SCHEMA_PATH

_model = None
_observable_model = None
_encoder = None
_recommender = None
_schema = None


def _lazy_load():
    global _model, _observable_model, _encoder, _recommender, _schema
    if _model is None:
        _model = joblib.load(MODEL_PATH)
        _observable_model = joblib.load(OBSERVABLE_MODEL_PATH)
        _encoder = joblib.load(ENCODER_PATH)
        _recommender = CounterfactualRecommender(model=_model, encoder=_encoder, features_numeric=FEATURES_NUMERIC)
        with open(SCHEMA_PATH) as f:
            _schema = json.load(f)
    return _model, _observable_model, _encoder, _recommender, _schema


def model_is_loaded() -> bool:
    return MODEL_PATH.exists() and OBSERVABLE_MODEL_PATH.exists() and ENCODER_PATH.exists()


def model_version_info() -> dict:
    if not model_is_loaded():
        return {}
    _, _, _, _, schema = _lazy_load()
    return schema


def _available_features(telemetry: dict) -> tuple[list[str], list[str]]:
    observed = [f for f in FEATURES_NUMERIC if telemetry.get(f) is not None]
    return observed, [f for f in FEATURES_NUMERIC if f not in observed]


def _select_ml_strategy(telemetry: dict) -> tuple[str | None, list[str]]:
    """Return only a model that was trained for the observed feature shape."""
    if telemetry.get("os_type") is None:
        return None, []
    if all(telemetry.get(f) is not None for f in FEATURES_NUMERIC):
        return "full_7_feature", FEATURES_NUMERIC
    # The real Windows limitation is specifically an unknown safe-browsing
    # state. The observable model deliberately excludes it; other missing
    # signals still use the conservative rule-only fallback.
    if telemetry.get("browser_safe_browsing_enabled") is None and all(
        telemetry.get(f) is not None for f in OBSERVABLE_FEATURES_NUMERIC
    ):
        return "observable_6_feature", OBSERVABLE_FEATURES_NUMERIC
    return None, []


def _explanation(schema: dict, strategy: str, telemetry: dict, features: list[str]) -> list[dict]:
    importance_key = "full" if strategy == "full_7_feature" else "observable"
    importance = schema["global_feature_importance"][importance_key]
    # This is deliberately global RF importance, not a fabricated local or
    # causal explanation. Limit it to observed signals used by this scan.
    ranked = sorted(
        ((feature, importance.get(feature, 0.0)) for feature in features),
        key=lambda item: item[1], reverse=True,
    )[:3]
    return [{"feature": feature, "value": telemetry.get(feature), "importance": value,
             "kind": "global_model_importance"} for feature, value in ranked]


def run_pipeline(telemetry: dict) -> dict:
    model, observable_model, encoder, recommender, schema = _lazy_load()

    findings = generate_findings(telemetry)

    observed_features, unavailable_features = _available_features(telemetry)
    strategy, model_features = _select_ml_strategy(telemetry)

    if strategy is not None:
        selected_model = model if strategy == "full_7_feature" else observable_model
        df = pd.DataFrame([telemetry])
        X, _, _ = build_feature_matrix(df, encoder=encoder, features_numeric=model_features)
        proba = selected_model.predict_proba(X)[0]
        classes = list(selected_model.classes_)
        risk_score = float(expected_risk_score(proba.reshape(1, -1), classes)[0])
        risk_tier = classes[int(proba.argmax())]
        ml_confidence = float(proba.max())
        degraded = bool(unavailable_features)
        selected_recommender = recommender if strategy == "full_7_feature" else CounterfactualRecommender(
            model=selected_model, encoder=encoder, features_numeric=model_features
        )
        rec_result = selected_recommender.recommend(telemetry)
        recommendations = rec_result["recommendations"]
        ml_used = True
        ml_explanation = _explanation(schema, strategy, telemetry, model_features)
    else:
        df = pd.DataFrame([{**{f: telemetry.get(f) for f in FEATURES_NUMERIC}, "os_type": telemetry.get("os_type", "Windows")}])
        safe_defaults = {
            "os_days_since_update": 0, "firewall_enabled": 1, "antivirus_enabled": 1,
            "days_since_av_update": 0, "browser_safe_browsing_enabled": 1,
            "browser_autofill_passwords": 0, "risky_extension_count": 0,
        }
        for f, default in safe_defaults.items():
            if pd.isna(df.at[0, f]) or df.at[0, f] is None:
                df.at[0, f] = default
        # Filling individual cells can leave the column as object dtype
        # (mixing None and numbers), which breaks numpy's vectorized .round()
        # inside rule_based_score — force back to float64 before scoring.
        # Caught via an actual degraded-telemetry curl test, not by review.
        df[FEATURES_NUMERIC] = df[FEATURES_NUMERIC].astype(float)
        scored = rule_based_score(df)
        risk_score = float(scored["rule_score_0_10"].iloc[0]) * 10.0
        risk_tier = scored["rule_risk_tier"].iloc[0]
        ml_confidence = None
        degraded = True
        recommendations = []
        ml_used = False
        ml_explanation = []

    return {
        "degraded": degraded,
        "risk_score": round(risk_score, 1),
        "risk_tier": risk_tier,
        "ml_confidence": round(ml_confidence, 3) if ml_confidence is not None else None,
        "ml_used": ml_used,
        "ml_strategy": strategy,
        "telemetry_observed_features": observed_features,
        "telemetry_unavailable_features": unavailable_features,
        "ml_explanation": ml_explanation,
        "findings": findings,
        "recommendations": recommendations,
    }
