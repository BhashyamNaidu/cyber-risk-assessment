"""
Counterfactual Recommendation Engine.

Single responsibility: given a user's current telemetry, quantify how much
each ACTIONABLE fix is expected to reduce their Random Forest-predicted
risk score, and rank fixes by that expected impact. Distinct from the Rule
Engine — uses RF's learned model, so estimates stay consistent with the
score actually shown on the dashboard.
"""
import joblib
import numpy as np
import pandas as pd

from train_final_model import (
    build_feature_matrix, expected_risk_score, FEATURES_NUMERIC, FEATURE_CATEGORICAL,
)
from paths import MODEL_PATH, ENCODER_PATH

ACTIONABLE_FIXES = [
    {"feature": "firewall_enabled", "fixed_value": 1, "label": "Enable firewall", "only_if": lambda t: t["firewall_enabled"] == 0},
    {"feature": "antivirus_enabled", "fixed_value": 1, "label": "Enable antivirus", "only_if": lambda t: t["antivirus_enabled"] == 0},
    {"feature": "os_days_since_update", "fixed_value": 0, "label": "Install pending OS updates", "only_if": lambda t: t["os_days_since_update"] > 30},
    {"feature": "days_since_av_update", "fixed_value": 0, "label": "Update antivirus signatures", "only_if": lambda t: t["antivirus_enabled"] == 1 and t["days_since_av_update"] > 14},
    {"feature": "browser_safe_browsing_enabled", "fixed_value": 1, "label": "Enable browser safe-browsing", "only_if": lambda t: t["browser_safe_browsing_enabled"] == 0},
    {"feature": "browser_autofill_passwords", "fixed_value": 0, "label": "Disable password autofill", "only_if": lambda t: t["browser_autofill_passwords"] == 1},
    {"feature": "risky_extension_count", "fixed_value": 0, "label": "Remove risky browser extensions", "only_if": lambda t: t["risky_extension_count"] >= 1},
]


class CounterfactualRecommender:
    def __init__(self, model_path=None, encoder_path=None, features_numeric=None, model=None, encoder=None):
        model_path = model_path or MODEL_PATH
        encoder_path = encoder_path or ENCODER_PATH
        self.model = model or joblib.load(model_path)
        self.encoder = encoder or joblib.load(encoder_path)
        self.features_numeric = features_numeric or FEATURES_NUMERIC

    def _score_for(self, telemetry: dict) -> float:
        df = pd.DataFrame([telemetry])
        X, _, _ = build_feature_matrix(df, encoder=self.encoder, features_numeric=self.features_numeric)
        proba = self.model.predict_proba(X)
        return float(expected_risk_score(proba, list(self.model.classes_))[0])

    def recommend(self, telemetry: dict, top_k: int = 5) -> dict:
        current_score = self._score_for(telemetry)
        recommendations = []

        for fix in ACTIONABLE_FIXES:
            # A what-if is valid only when its source signal is observed and
            # participates in the selected model. In particular, never turn
            # an unknown browser setting into a counterfactual recommendation.
            if fix["feature"] not in self.features_numeric or telemetry.get(fix["feature"]) is None:
                continue
            if not fix["only_if"](telemetry):
                continue
            hypothetical = dict(telemetry)
            hypothetical[fix["feature"]] = fix["fixed_value"]
            new_score = self._score_for(hypothetical)
            delta = current_score - new_score
            recommendations.append({
                "action": fix["label"],
                "feature": fix["feature"],
                "current_score": round(current_score, 1),
                "expected_score_after_fix": round(new_score, 1),
                "expected_reduction": round(delta, 1),
            })

        recommendations.sort(key=lambda r: r["expected_reduction"], reverse=True)
        return {
            "current_score": round(current_score, 1),
            "recommendations": recommendations[:top_k],
        }


if __name__ == "__main__":
    rec_engine = CounterfactualRecommender()
    test_case = {
        "os_type": "Windows",
        "os_days_since_update": 150,
        "firewall_enabled": 0,
        "antivirus_enabled": 0,
        "days_since_av_update": 45,
        "browser_safe_browsing_enabled": 0,
        "browser_autofill_passwords": 1,
        "risky_extension_count": 3,
    }
    result = rec_engine.recommend(test_case)
    print(f"Current expected risk score: {result['current_score']}/100\n")
    for r in result["recommendations"]:
        print(f"  {r['action']:40s} {result['current_score']:.1f} -> {r['expected_score_after_fix']:.1f}  (-{r['expected_reduction']:.1f})")
