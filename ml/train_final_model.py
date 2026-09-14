"""
Train and persist the FINAL production Random Forest model.

Per the evidence-driven architecture redesign (docs/architecture_v2.md):
the model consumes ONLY raw telemetry (Pipeline A). The rule_score feature
was tested as an additional input (Pipeline B) and rejected — a 50-fold
paired comparison showed no statistically significant improvement
(p=0.31, Cohen's d=-0.15).
"""
import json
import joblib
from datetime import datetime, timezone
from paths import DATASET_PATH, MODEL_PATH, OBSERVABLE_MODEL_PATH, ENCODER_PATH, SCHEMA_PATH
import numpy as np
import pandas as pd
import sklearn
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, precision_recall_fscore_support, roc_auc_score, confusion_matrix
from sklearn.preprocessing import OneHotEncoder

FEATURES_NUMERIC = [
    "os_days_since_update", "firewall_enabled", "antivirus_enabled",
    "days_since_av_update", "browser_safe_browsing_enabled",
    "browser_autofill_passwords", "risky_extension_count",
]
OBSERVABLE_FEATURES_NUMERIC = [f for f in FEATURES_NUMERIC if f != "browser_safe_browsing_enabled"]
FEATURE_CATEGORICAL = ["os_type"]
OS_TYPES = ["Linux", "Windows", "macOS"]

TIER_MIDPOINT_0_100 = {"Low": 20.0, "Medium": 55.0, "High": 85.0}


def build_feature_matrix(df: pd.DataFrame, encoder: OneHotEncoder = None, features_numeric=None):
    features_numeric = features_numeric or FEATURES_NUMERIC
    if encoder is None:
        encoder = OneHotEncoder(sparse_output=False, handle_unknown="ignore", categories=[OS_TYPES])
        os_dummies = encoder.fit_transform(df[FEATURE_CATEGORICAL])
    else:
        os_dummies = encoder.transform(df[FEATURE_CATEGORICAL])
    os_cols = encoder.get_feature_names_out(FEATURE_CATEGORICAL)
    X = np.hstack([df[features_numeric].values, os_dummies])
    feature_names = features_numeric + list(os_cols)
    return X, feature_names, encoder


def expected_risk_score(proba: np.ndarray, classes: list) -> np.ndarray:
    midpoints = np.array([TIER_MIDPOINT_0_100[c] for c in classes])
    return proba @ midpoints


def _confidence_behavior(y_true, proba, classes):
    """Simple held-out reliability summary; confidence is not claimed calibrated."""
    predicted = np.asarray(classes)[proba.argmax(axis=1)]
    confidence = proba.max(axis=1)
    correct = (predicted == y_true).astype(float)
    bins = np.linspace(0.0, 1.0, 6)
    rows = []
    for lo, hi in zip(bins[:-1], bins[1:]):
        mask = (confidence >= lo) & ((confidence < hi) if hi < 1 else (confidence <= hi))
        if mask.any():
            rows.append({"range": f"{lo:.1f}-{hi:.1f}", "count": int(mask.sum()),
                         "mean_confidence": round(float(confidence[mask].mean()), 4),
                         "accuracy": round(float(correct[mask].mean()), 4)})
    return rows


def _metrics(y_true, proba, classes):
    predicted = np.asarray(classes)[proba.argmax(axis=1)]
    precision, recall, f1, _ = precision_recall_fscore_support(
        y_true, predicted, labels=classes, average="weighted", zero_division=0
    )
    return {
        "accuracy": round(float(accuracy_score(y_true, predicted)), 4),
        "precision_weighted": round(float(precision), 4),
        "recall_weighted": round(float(recall), 4),
        "f1_weighted": round(float(f1), 4),
        "roc_auc_ovr_weighted": round(float(roc_auc_score(y_true, proba, labels=classes, multi_class="ovr", average="weighted")), 4),
        "confusion_matrix": confusion_matrix(y_true, predicted, labels=classes).tolist(),
        "confidence_behavior": _confidence_behavior(y_true, proba, classes),
    }


def main():
    df = pd.read_csv(DATASET_PATH)
    # One deterministic split is shared by both models, so their held-out
    # comparison has no leakage or split-selection advantage.
    train_df, test_df = train_test_split(df, test_size=0.25, random_state=42, stratify=df["risk_tier"])
    X_train, feature_names, encoder = build_feature_matrix(train_df)
    X_test, _, _ = build_feature_matrix(test_df, encoder=encoder)
    y_train = train_df["risk_tier"].values
    y_test = test_df["risk_tier"].values

    model = RandomForestClassifier(n_estimators=200, max_depth=8, min_samples_leaf=10, random_state=42)
    model.fit(X_train, y_train)

    full_proba = model.predict_proba(X_test)
    full_metrics = _metrics(y_test, full_proba, list(model.classes_))

    # This model is trained only on signals observable on the known real
    # Windows shape. It never represents an unavailable browser setting as 0/1.
    X_observed_train, observable_names, _ = build_feature_matrix(
        train_df, encoder=encoder, features_numeric=OBSERVABLE_FEATURES_NUMERIC
    )
    X_observed_test, _, _ = build_feature_matrix(
        test_df, encoder=encoder, features_numeric=OBSERVABLE_FEATURES_NUMERIC
    )
    observable_model = RandomForestClassifier(n_estimators=200, max_depth=8, min_samples_leaf=10, random_state=42)
    observable_model.fit(X_observed_train, y_train)
    observable_proba = observable_model.predict_proba(X_observed_test)
    observable_metrics = _metrics(y_test, observable_proba, list(observable_model.classes_))

    # Honest deterministic baseline evaluated on exactly the same held-out rows.
    from rule_engine import rule_based_score
    baseline = rule_based_score(test_df)["rule_risk_tier"].values
    baseline_metrics = {
        "accuracy": round(float(accuracy_score(y_test, baseline)), 4),
        "precision_weighted": round(float(precision_recall_fscore_support(y_test, baseline, average="weighted", zero_division=0)[0]), 4),
        "recall_weighted": round(float(precision_recall_fscore_support(y_test, baseline, average="weighted", zero_division=0)[1]), 4),
        "f1_weighted": round(float(precision_recall_fscore_support(y_test, baseline, average="weighted", zero_division=0)[2]), 4),
    }
    print(f"Full-model held-out accuracy: {full_metrics['accuracy']:.4f}")
    print(f"Observable-model held-out accuracy: {observable_metrics['accuracy']:.4f}")

    joblib.dump(model, MODEL_PATH)
    joblib.dump(observable_model, OBSERVABLE_MODEL_PATH)
    joblib.dump(encoder, ENCODER_PATH)
    with open(SCHEMA_PATH, "w") as f:
        json.dump({
            "model_version": "rf-v2-observable-windows",
            "training_dataset": {"path": str(DATASET_PATH.name), "rows": int(len(df)), "seed": 42},
            "library_versions": {"scikit_learn": sklearn.__version__, "pandas": pd.__version__, "numpy": np.__version__},
            "trained_at_utc": datetime.now(timezone.utc).isoformat(),
            "features_numeric": FEATURES_NUMERIC,
            "observable_features_numeric": OBSERVABLE_FEATURES_NUMERIC,
            "feature_categorical": FEATURE_CATEGORICAL,
            "os_types": OS_TYPES,
            "classes": list(model.classes_),
            "tier_midpoints_0_100": TIER_MIDPOINT_0_100,
            "preprocessing": "OneHotEncoder(os_type; fixed Linux/Windows/macOS order); numeric features passed through unchanged",
            "missingness_strategy": "Two validated observable-feature models: 7-feature RF for complete telemetry and 6-feature RF when browser_safe_browsing_enabled is unavailable. No value is imputed.",
            "hyperparameters": {"n_estimators": 200, "max_depth": 8, "min_samples_leaf": 10, "random_state": 42},
            "validation": {"split": "stratified 75/25 held-out, random_state=42", "full_model": full_metrics,
                           "observable_model": observable_metrics, "rule_based_baseline": baseline_metrics},
            "global_feature_importance": {
                "full": dict(zip(feature_names, [round(float(v), 6) for v in model.feature_importances_])),
                "observable": dict(zip(observable_names, [round(float(v), 6) for v in observable_model.feature_importances_])),
            },
        }, f, indent=2)

    print("\nSaved: rf_model.joblib, rf_observable_model.joblib, os_type_encoder.joblib, model_schema.json")


if __name__ == "__main__":
    main()
