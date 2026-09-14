"""
Synthetic dataset generator for the Smart Personal Cyber Risk Score Calculator.

Implements the CVSS v3.1-grounded labeling methodology documented in
docs/dataset_methodology.md. Every weight/scaling choice below has a
one-line justification comment pointing back to that doc.
"""
import argparse
import numpy as np
import pandas as pd


# Each feature's maximum severity BUDGET on the composite 0-10 scale — these
# already bake in relative importance (Network-vector/Low-complexity classes
# like OS-update and firewall get the largest budgets). Budgets sum to ~11.0
# rather than exactly 10.0 so that a genuinely bad multi-factor profile can
# reach the High band (>=7.0) after noise, while any single bad factor alone
# stays well under it — a lone risky setting should not read as "High risk";
# only a compounding combination should.
BUDGET = {
    "os_update": 3.2,
    "firewall": 2.4,
    "av_enabled": 1.6,
    "av_freshness": 0.9,
    "safe_browsing": 1.4,
    "autofill": 0.5,
    "extensions": 1.0,
}


def scale_os_update(days_since_update: np.ndarray) -> np.ndarray:
    """0 -> budget as days since last OS update goes 0 -> 180+."""
    return np.clip(days_since_update / 180.0, 0, 1) * BUDGET["os_update"]


def scale_firewall(enabled: np.ndarray) -> np.ndarray:
    return np.where(enabled == 0, BUDGET["firewall"], 0.0)


def scale_av_enabled(enabled: np.ndarray) -> np.ndarray:
    return np.where(enabled == 0, BUDGET["av_enabled"], 0.0)


def scale_av_freshness(days_since_av_update: np.ndarray, av_enabled: np.ndarray) -> np.ndarray:
    """0 if AV disabled entirely (already captured by scale_av_enabled)."""
    base = np.clip(days_since_av_update / 60.0, 0, 1) * BUDGET["av_freshness"]
    return np.where(av_enabled == 0, 0.0, base)


def scale_safe_browsing(enabled: np.ndarray) -> np.ndarray:
    return np.where(enabled == 0, BUDGET["safe_browsing"], 0.0)


def scale_autofill(enabled: np.ndarray) -> np.ndarray:
    return np.where(enabled == 1, BUDGET["autofill"], 0.0)


def scale_extensions(risky_count: np.ndarray) -> np.ndarray:
    return np.clip(risky_count / 5.0, 0, 1) * BUDGET["extensions"]


def composite_score(df: pd.DataFrame) -> np.ndarray:
    """The TRUE underlying risk function used only for ground-truth label
    generation. Includes non-additive INTERACTION terms on top of the
    linear per-feature severity budget — representing the defense-in-depth
    principle that losing multiple independent security layers
    simultaneously is disproportionately worse than the sum of the
    individual losses. A naive linear rule engine that sums independent
    per-feature flags (see rule_engine.py) cannot represent these
    interaction terms — that gap is the concrete, testable mechanism
    behind the hybrid ML investigation (see docs/architecture_v2.md).
    """
    linear = (
        df["_s_os_update"]
        + df["_s_firewall"]
        + df["_s_av_enabled"]
        + df["_s_av_freshness"]
        + df["_s_safe_browsing"]
        + df["_s_autofill"]
        + df["_s_extensions"]
    )

    fw_off = (df["firewall_enabled"].values == 0)
    av_off = (df["antivirus_enabled"].values == 0)
    os_stale = (df["os_days_since_update"].values > 90)
    many_ext = (df["risky_extension_count"].values >= 3)
    autofill_on = (df["browser_autofill_passwords"].values == 1)
    safe_browse_off = (df["browser_safe_browsing_enabled"].values == 0)

    interaction_fw_av = np.where(fw_off & av_off, 1.4, 0.0)
    interaction_os_ext = np.where(os_stale & many_ext, 1.1, 0.0)
    interaction_autofill_phish = np.where(autofill_on & safe_browse_off, 0.9, 0.0)

    interaction_total = interaction_fw_av + interaction_os_ext + interaction_autofill_phish
    return linear + interaction_total


def bucket_label(score: np.ndarray) -> np.ndarray:
    """CVSS-style banding collapsed to 3 tiers for a non-expert user."""
    labels = np.empty(score.shape, dtype=object)
    labels[score < 4.0] = "Low"
    labels[(score >= 4.0) & (score < 7.0)] = "Medium"
    labels[score >= 7.0] = "High"
    return labels


def generate(n: int, seed: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)

    os_type = rng.choice(["Windows", "macOS", "Linux"], size=n, p=[0.55, 0.30, 0.15])

    # Latent "carelessness" factor z in [0,1] per simulated user, Beta(2,3).
    # This is what makes risk factors CORRELATE within a user instead of
    # being independently random.
    z = rng.beta(2.0, 3.0, size=n)

    os_days_since_update = rng.gamma(shape=2.0 + 3.0 * z, scale=20.0 + 40.0 * z, size=n)
    firewall_enabled = rng.binomial(1, p=np.clip(0.92 - 0.75 * z, 0.05, 0.97), size=n)
    av_enabled = rng.binomial(1, p=np.clip(0.90 - 0.70 * z, 0.05, 0.97), size=n)
    days_since_av_update = rng.gamma(shape=1.5 + 2.0 * z, scale=12.0 + 35.0 * z, size=n)
    safe_browsing_enabled = rng.binomial(1, p=np.clip(0.88 - 0.65 * z, 0.05, 0.97), size=n)
    autofill_passwords = rng.binomial(1, p=np.clip(0.30 + 0.55 * z, 0.05, 0.95), size=n)
    risky_extension_count = rng.poisson(lam=0.4 + 3.2 * z, size=n)

    df = pd.DataFrame({
        "os_type": os_type,
        "os_days_since_update": os_days_since_update.round(1),
        "firewall_enabled": firewall_enabled,
        "antivirus_enabled": av_enabled,
        "days_since_av_update": days_since_av_update.round(1),
        "browser_safe_browsing_enabled": safe_browsing_enabled,
        "browser_autofill_passwords": autofill_passwords,
        "risky_extension_count": risky_extension_count,
    })

    df["_s_os_update"] = scale_os_update(df["os_days_since_update"].values)
    df["_s_firewall"] = scale_firewall(df["firewall_enabled"].values)
    df["_s_av_enabled"] = scale_av_enabled(df["antivirus_enabled"].values)
    df["_s_av_freshness"] = scale_av_freshness(df["days_since_av_update"].values, df["antivirus_enabled"].values)
    df["_s_safe_browsing"] = scale_safe_browsing(df["browser_safe_browsing_enabled"].values)
    df["_s_autofill"] = scale_autofill(df["browser_autofill_passwords"].values)
    df["_s_extensions"] = scale_extensions(df["risky_extension_count"].values)

    raw_score = composite_score(df)
    noisy_score = np.clip(raw_score + rng.normal(0, 0.4, size=n), 0, 10)
    df["risk_score_0_10"] = noisy_score.round(2)
    df["risk_tier"] = bucket_label(noisy_score)

    df = df.drop(columns=[c for c in df.columns if c.startswith("_s_")])
    return df


def main():
    from paths import DATASET_PATH
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=5000)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", type=str, default=str(DATASET_PATH))
    args = ap.parse_args()

    df = generate(args.n, args.seed)
    df.to_csv(args.out, index=False)
    print(f"Wrote {len(df)} rows to {args.out}")
    print(df["risk_tier"].value_counts(normalize=True).round(3))


if __name__ == "__main__":
    main()
