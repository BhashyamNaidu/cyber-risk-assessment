"""
Rule Engine — deterministic CVSS-grounded security policy checks.

Per the evidence-driven redesign (docs/architecture_v2.md), this component
has two distinct outputs:
  1. generate_findings(): structured, per-rule explanations (the actual
     production responsibility — explainable security reasoning).
  2. rule_based_score(): a scalar fallback score, used ONLY when the Random
     Forest cannot run (incomplete telemetry) — NOT fed into the ML model
     as an input feature, since a 50-fold paired evaluation showed this
     does not improve, and can slightly hurt, predictive accuracy
     (p=0.31, Cohen's d=-0.15).
"""
import numpy as np
import pandas as pd

from generate_dataset import (
    scale_os_update, scale_firewall, scale_av_enabled, scale_av_freshness,
    scale_safe_browsing, scale_autofill, scale_extensions, bucket_label, BUDGET,
)


def rule_based_score(df: pd.DataFrame) -> pd.DataFrame:
    """Returns a copy of df with rule_score_0_10 and rule_risk_tier columns."""
    s_os = scale_os_update(df["os_days_since_update"].values)
    s_fw = scale_firewall(df["firewall_enabled"].values)
    s_av = scale_av_enabled(df["antivirus_enabled"].values)
    s_avf = scale_av_freshness(df["days_since_av_update"].values, df["antivirus_enabled"].values)
    s_sb = scale_safe_browsing(df["browser_safe_browsing_enabled"].values)
    s_af = scale_autofill(df["browser_autofill_passwords"].values)
    s_ext = scale_extensions(df["risky_extension_count"].values)

    raw = s_os + s_fw + s_av + s_avf + s_sb + s_af + s_ext
    score = np.clip(raw, 0, 10)

    out = df.copy()
    out["rule_score_0_10"] = score.round(2)
    out["rule_risk_tier"] = bucket_label(score)
    return out


RULE_DEFINITIONS = [
    {
        "id": "R1_OS_UPDATE",
        "condition": lambda t: t["os_days_since_update"] > 90,
        "severity_fn": lambda t: float(scale_os_update(np.array([t["os_days_since_update"]]))[0]),
        "title": "Operating system not updated recently",
        "cvss_rationale": (
            "Unpatched OS vulnerabilities are frequently Network attack "
            "vector + Low complexity + No privileges required, placing "
            "them in the CVSS High/Critical band (7.0-10.0) for actively "
            "exploited CVEs."
        ),
        "recommendation": "Install pending OS updates as soon as possible.",
        "feature": "os_days_since_update",
    },
    {
        "id": "R2_FIREWALL",
        "condition": lambda t: t["firewall_enabled"] == 0,
        "severity_fn": lambda t: BUDGET["firewall"],
        "title": "Firewall disabled",
        "cvss_rationale": (
            "Disabling the firewall satisfies the Attack Vector: Network "
            "precondition for a large class of CVEs that would otherwise "
            "require local access."
        ),
        "recommendation": "Enable the OS firewall.",
        "feature": "firewall_enabled",
    },
    {
        "id": "R3_AV_DISABLED",
        "condition": lambda t: t["antivirus_enabled"] == 0,
        "severity_fn": lambda t: BUDGET["av_enabled"],
        "title": "Antivirus disabled",
        "cvss_rationale": (
            "Reduces likelihood of successful execution after initial "
            "access; CVSS Attack Complexity effectively shifts from Low to "
            "High when common malware is intercepted pre-execution."
        ),
        "recommendation": "Enable antivirus / endpoint protection.",
        "feature": "antivirus_enabled",
    },
    {
        "id": "R4_AV_STALE",
        "condition": lambda t: t["antivirus_enabled"] == 1 and t["days_since_av_update"] > 30,
        "severity_fn": lambda t: BUDGET["av_freshness"] * min(t["days_since_av_update"] / 60.0, 1.0),
        "title": "Antivirus signatures outdated",
        "cvss_rationale": "Outdated AV signatures behave like an unpatched local component, reducing detection of recent malware variants.",
        "recommendation": "Update antivirus definitions.",
        "feature": "days_since_av_update",
    },
    {
        "id": "R5_SAFE_BROWSING",
        "condition": lambda t: t["browser_safe_browsing_enabled"] == 0,
        "severity_fn": lambda t: BUDGET["safe_browsing"],
        "title": "Browser safe-browsing / phishing protection disabled",
        "cvss_rationale": "Network attack vector, low complexity, no privileges required — the standard profile for drive-by and phishing delivery.",
        "recommendation": "Enable safe-browsing / phishing protection in browser settings.",
        "feature": "browser_safe_browsing_enabled",
    },
    {
        "id": "R6_AUTOFILL",
        "condition": lambda t: t["browser_autofill_passwords"] == 1,
        "severity_fn": lambda t: BUDGET["autofill"],
        "title": "Browser password autofill enabled",
        "cvss_rationale": "Local attack vector but High confidentiality impact if the device is ever accessed by another party or compromised by malware.",
        "recommendation": "Disable browser-based password autofill; use a dedicated password manager instead.",
        "feature": "browser_autofill_passwords",
    },
    {
        "id": "R7_EXTENSIONS",
        "condition": lambda t: t["risky_extension_count"] >= 2,
        "severity_fn": lambda t: BUDGET["extensions"] * min(t["risky_extension_count"] / 5.0, 1.0),
        "title": "Multiple high-permission browser extensions installed",
        "cvss_rationale": "Each additional high-permission extension is an independent additional attack surface (CVSS Scope: Changed reasoning).",
        "recommendation": "Review and remove unnecessary high-permission extensions.",
        "feature": "risky_extension_count",
    },
    {
        "id": "R8_COMPOUND_FW_AV",
        "condition": lambda t: t["firewall_enabled"] == 0 and t["antivirus_enabled"] == 0,
        "severity_fn": lambda t: 1.4,
        "title": "Compounding risk: both firewall and antivirus disabled",
        "cvss_rationale": "Defense-in-depth failure — losing both the network-layer and endpoint-layer defenses simultaneously is disproportionately worse than either loss alone.",
        "recommendation": "Re-enable both firewall and antivirus immediately; this combination represents a compounding risk, not two independent issues.",
        "feature": None,
    },
]


def generate_findings(telemetry: dict) -> list:
    """Evaluate every rule against one telemetry record; return only the
    findings that fired, sorted by severity descending."""
    findings = []
    for rule in RULE_DEFINITIONS:
        try:
            if rule["condition"](telemetry):
                severity = round(float(rule["severity_fn"](telemetry)), 2)
                findings.append({
                    "id": rule["id"],
                    "title": rule["title"],
                    "severity_0_10": severity,
                    "cvss_rationale": rule["cvss_rationale"],
                    "recommendation": rule["recommendation"],
                    "feature": rule["feature"],
                })
        except (KeyError, TypeError):
            # Missing telemetry field -> skip this rule (graceful degradation).
            continue
    findings.sort(key=lambda f: f["severity_0_10"], reverse=True)
    return findings


if __name__ == "__main__":
    from paths import DATASET_PATH
    df = pd.read_csv(DATASET_PATH)
    scored = rule_based_score(df)
    agreement = (scored["rule_risk_tier"] == scored["risk_tier"]).mean()
    print(f"Rule engine vs. ground-truth label agreement: {agreement:.3f}")
    print(scored[["risk_tier", "rule_risk_tier"]].head(10))
