"""
Ablation study — Pipeline A (raw telemetry) vs Pipeline B (raw telemetry +
rule_score_0_10 as an engineered feature).

Re-created artifact (D1). The original script this reproduces was
referenced in PROJECT_STATUS.md/docs/architecture_v2.md but was missing
from the repository — this file did not exist and its cited numbers
(90.68%/90.59% mean accuracy, p=0.31, Cohen's d=-0.15) could not be
regenerated from any artifact in the repo. This script implements the same
documented methodology (paired 5x10 repeated stratified CV, identical RF
hyperparameters and fold splits between pipelines) against the CURRENT
synthetic_dataset.csv and CURRENT train_final_model.py hyperparameters, and
reports whatever comes out — it does not force, adjust, or cherry-pick
results to match the previously-documented numbers. See
`previously_documented_values_for_comparison` in the output for a transparent
side-by-side; if this run's numbers differ from those, that is reported
honestly, not reconciled.

Does not touch data/rf_model.joblib, data/rf_observable_model.joblib, or
data/model_schema.json — every model trained here is a temporary, in-memory
model used only for this comparison and is discarded after each fold.

Run with: python ml/ablation_study.py  (from the ml/ directory, matching
every other script in this package)
"""
import json
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import scipy
import sklearn
from scipy import stats
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score

from paths import DATASET_PATH, DATA_DIR
from train_final_model import build_feature_matrix, FEATURES_NUMERIC
from rule_engine import rule_based_score

try:
    from sklearn.model_selection import RepeatedStratifiedKFold
except ImportError as e:  # pragma: no cover - environment guard, not a test path
    raise SystemExit(f"scikit-learn's RepeatedStratifiedKFold is required: {e}")

RESULTS_PATH = DATA_DIR / "ablation_study_results.json"

N_SPLITS = 5
N_REPEATS = 10
CV_RANDOM_STATE = 42
RF_KWARGS = dict(n_estimators=200, max_depth=8, min_samples_leaf=10, random_state=42)

# Numbers previously written into docs/architecture_v2.md / PROJECT_STATUS.md
# before this script existed. NOT assumed correct — included only so a
# reader can see this run's numbers next to what was previously claimed.
PREVIOUSLY_DOCUMENTED_VALUES = {
    "pipeline_a_mean_accuracy": 0.9068,
    "pipeline_a_std_accuracy": 0.0079,
    "pipeline_b_mean_accuracy": 0.9059,
    "pipeline_b_std_accuracy": 0.0084,
    "paired_t_test_p": 0.31,
    "wilcoxon_p": 0.28,
    "cohens_d": -0.15,
    "fold_wins_pipeline_a": 26,
    "fold_wins_pipeline_b": 21,
    "ties": 3,
    "source": "docs/architecture_v2.md, prior to this script's re-creation — provenance of these exact figures is not otherwise reproducible from this repository as of this artifact's creation.",
}


def _pipeline_a_fold(train_df: pd.DataFrame, test_df: pd.DataFrame):
    X_train, _, encoder = build_feature_matrix(train_df, features_numeric=FEATURES_NUMERIC)
    X_test, _, _ = build_feature_matrix(test_df, encoder=encoder, features_numeric=FEATURES_NUMERIC)
    return X_train, X_test


def _pipeline_b_fold(train_df: pd.DataFrame, test_df: pd.DataFrame):
    numeric = FEATURES_NUMERIC + ["rule_score_0_10"]
    scored_train = rule_based_score(train_df)
    scored_test = rule_based_score(test_df)
    X_train, _, encoder = build_feature_matrix(scored_train, features_numeric=numeric)
    X_test, _, _ = build_feature_matrix(scored_test, encoder=encoder, features_numeric=numeric)
    return X_train, X_test


def run():
    df = pd.read_csv(DATASET_PATH)
    y = df["risk_tier"].values

    cv = RepeatedStratifiedKFold(n_splits=N_SPLITS, n_repeats=N_REPEATS, random_state=CV_RANDOM_STATE)

    acc_a, acc_b, fold_records = [], [], []
    for fold_idx, (train_idx, test_idx) in enumerate(cv.split(df, y)):
        train_df, test_df = df.iloc[train_idx].reset_index(drop=True), df.iloc[test_idx].reset_index(drop=True)
        y_train, y_test = y[train_idx], y[test_idx]

        Xa_train, Xa_test = _pipeline_a_fold(train_df, test_df)
        model_a = RandomForestClassifier(**RF_KWARGS)
        model_a.fit(Xa_train, y_train)
        acc_a_fold = accuracy_score(y_test, model_a.predict(Xa_test))

        Xb_train, Xb_test = _pipeline_b_fold(train_df, test_df)
        model_b = RandomForestClassifier(**RF_KWARGS)
        model_b.fit(Xb_train, y_train)
        acc_b_fold = accuracy_score(y_test, model_b.predict(Xb_test))

        acc_a.append(acc_a_fold)
        acc_b.append(acc_b_fold)
        fold_records.append({
            "fold": fold_idx,
            "pipeline_a_accuracy": round(float(acc_a_fold), 4),
            "pipeline_b_accuracy": round(float(acc_b_fold), 4),
        })

    acc_a = np.array(acc_a)
    acc_b = np.array(acc_b)
    diff = acc_a - acc_b  # positive => Pipeline A (no rule_score) more accurate this fold

    t_stat, t_p = stats.ttest_rel(acc_a, acc_b)

    if np.allclose(diff, 0.0):
        # Wilcoxon is undefined when every paired difference is exactly
        # zero — report this honestly instead of letting scipy raise.
        w_stat, w_p = None, None
        wilcoxon_note = "All paired differences were exactly zero; Wilcoxon signed-rank is undefined for this run."
    else:
        w_stat, w_p = stats.wilcoxon(acc_a, acc_b)
        wilcoxon_note = None

    diff_std = diff.std(ddof=1)
    cohens_d = float(diff.mean() / diff_std) if diff_std > 0 else 0.0

    wins_a = int((diff > 0).sum())
    wins_b = int((diff < 0).sum())
    ties = int((diff == 0).sum())

    alpha = 0.05
    if t_p < alpha:
        interpretation = (
            f"Paired t-test p={t_p:.4f} < {alpha}: a statistically significant difference "
            f"WAS found between Pipeline A and Pipeline B on this run, on this dataset. "
            "This differs from the previously-documented null result and should be reviewed "
            "before repeating the prior 'no significant difference' claim."
        )
    else:
        interpretation = (
            f"Paired t-test p={t_p:.4f} >= {alpha}: no statistically significant difference "
            "found between Pipeline A and Pipeline B on this run, consistent with the "
            "previously-documented conclusion that rule_score does not measurably help RF here."
        )

    results = {
        "methodology": {
            "description": (
                "Paired comparison: Pipeline A (raw 7-feature telemetry) vs Pipeline B "
                "(raw telemetry + rule_score_0_10 as an 8th engineered feature), identical "
                "RandomForest hyperparameters and identical fold splits per repeat."
            ),
            "cv": f"RepeatedStratifiedKFold(n_splits={N_SPLITS}, n_repeats={N_REPEATS}, random_state={CV_RANDOM_STATE}) -> {N_SPLITS * N_REPEATS} paired folds",
            "hyperparameters": RF_KWARGS,
            "dataset": {"path": DATASET_PATH.name, "rows": int(len(df))},
            "library_versions": {
                "scikit_learn": sklearn.__version__, "scipy": scipy.__version__,
                "pandas": pd.__version__, "numpy": np.__version__,
            },
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        },
        "pipeline_a_mean_accuracy": round(float(acc_a.mean()), 4),
        "pipeline_a_std_accuracy": round(float(acc_a.std(ddof=1)), 4),
        "pipeline_b_mean_accuracy": round(float(acc_b.mean()), 4),
        "pipeline_b_std_accuracy": round(float(acc_b.std(ddof=1)), 4),
        "paired_t_test": {"statistic": round(float(t_stat), 4), "p_value": round(float(t_p), 4)},
        "wilcoxon_signed_rank": {
            "statistic": (round(float(w_stat), 4) if w_stat is not None else None),
            "p_value": (round(float(w_p), 4) if w_p is not None else None),
            "note": wilcoxon_note,
        },
        "cohens_d": round(cohens_d, 4),
        "fold_wins": {"pipeline_a": wins_a, "pipeline_b": wins_b, "ties": ties},
        "interpretation": interpretation,
        "fold_level_results": fold_records,
        "previously_documented_values_for_comparison": PREVIOUSLY_DOCUMENTED_VALUES,
    }

    with open(RESULTS_PATH, "w") as f:
        json.dump(results, f, indent=2)

    print(f"Pipeline A (raw telemetry):            mean accuracy = {results['pipeline_a_mean_accuracy']:.4f} (std {results['pipeline_a_std_accuracy']:.4f})")
    print(f"Pipeline B (raw telemetry + rule_score): mean accuracy = {results['pipeline_b_mean_accuracy']:.4f} (std {results['pipeline_b_std_accuracy']:.4f})")
    print(f"Paired t-test: statistic={results['paired_t_test']['statistic']}, p={results['paired_t_test']['p_value']}")
    print(f"Wilcoxon signed-rank: statistic={results['wilcoxon_signed_rank']['statistic']}, p={results['wilcoxon_signed_rank']['p_value']}")
    print(f"Cohen's d: {results['cohens_d']}")
    print(f"Fold wins — A: {wins_a}, B: {wins_b}, ties: {ties}")
    print(f"\n{interpretation}")
    print(f"\nSaved: {RESULTS_PATH}")
    return results


if __name__ == "__main__":
    run()
