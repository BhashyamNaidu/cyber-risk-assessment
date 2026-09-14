# Synthetic Dataset Generation Methodology

## Why synthetic data, and why this isn't arbitrary

No public dataset maps "an individual device's OS/browser configuration"
to a ground-truth compromise outcome — this is the same gap the SYNASC'25
psychometric paper and the Tamanna et al. patch-delay paper each hit and
solved differently (synthetic labels; a controlled user study). We generate
synthetic data too, but instead of assigning risk labels arbitrarily or
uniformly at random, each feature's contribution to the label is grounded in
the **CVSS v3.1 qualitative severity rating scale** (FIRST.org), which is the
industry-standard mapping from a 0-10 severity score to a qualitative band:

| CVSS Score Range | Qualitative Severity |
|---|---|
| 0.0 | None |
| 0.1 - 3.9 | Low |
| 4.0 - 6.9 | Medium |
| 7.0 - 8.9 | High |
| 9.0 - 10.0 | Critical |

## Feature -> severity-contribution mapping

Each telemetry feature is mapped to a severity weight (0-10 scale) based on
the CVSS Base Metric reasoning for the *class* of vulnerability that feature
represents (Attack Vector, Attack Complexity, Privileges Required). This is
a documented, defensible design choice — not a claim that we scraped live
CVE data.

| Feature | Represents (vulnerability class) | CVSS reasoning | Assigned severity budget (0-10 scale) |
|---|---|---|---|
| `os_days_since_update` | Unpatched remote-code-execution class CVEs | Network vector, low complexity, no privileges required -> High/Critical band | Scales 0 -> 3.2 as days since update goes 0 -> 180+ |
| `firewall_enabled` | Removes a Network-vector precondition | Disabling the firewall satisfies "Attack Vector: Network" for a large CVE class | 2.4 if disabled, 0 if enabled |
| `antivirus_enabled` | Malware execution / local privilege escalation class | Reduces likelihood of successful execution after initial access | 1.6 if disabled, 0 if enabled |
| `antivirus_up_to_date` | Signature-evasion of known malware | Outdated AV signatures behave like an unpatched local component | Scales 0 -> 0.9 as days since AV update increases |
| `browser_safe_browsing_enabled` | Phishing / malicious site delivery vector | Network attack vector, low complexity, no privileges required | 1.4 if disabled, 0 if enabled |
| `browser_autofill_passwords` | Credential exposure on shared/compromised devices | Local attack vector but High confidentiality impact | 0.5 if enabled, 0 if disabled |
| `risky_extension_count` | Extension-based data exfiltration / supply-chain risk | Each additional high-permission extension is an independent attack surface | Scales 0 -> 1.0 as count goes 0 -> 5+ |
| `os_type` | Baseline platform exposure | Not a vulnerability itself; covariate only | 0 (no direct weight) |

Severity budgets sum to ~11.0 rather than exactly 10.0 so a genuinely bad
multi-factor profile can reach the High band (>=7.0) after noise, while any
single bad factor alone stays well under it — a lone risky setting should
not read as "High risk"; only a compounding combination should.

## Composite score and label

For each synthetic sample:

1. Draw feature values from realistic, correlated distributions (see
   `generate_dataset.py` — a latent per-user "carelessness" factor makes
   risk behaviours co-occur realistically).
2. Compute a **linear** weighted severity score using the per-feature
   severity budgets above.
3. Add **non-linear interaction bonuses** on top of the linear score when
   specific combinations of risk factors co-occur (firewall AND AV both
   disabled at once; stale OS AND many risky extensions at once; autofill
   enabled while safe-browsing is off) — a defense-in-depth argument: losing
   multiple independent security layers simultaneously is disproportionately
   worse than the sum of losing each alone. This interaction structure is
   what a naive linear rule engine cannot represent, and is the concrete
   basis for the hybrid rule+ML ablation comparison (see `architecture_v2.md`).
4. Add small Gaussian noise (sigma = 0.4) to avoid a perfectly deterministic
   mapping.
5. Bucket the noisy composite score into Low / Medium / High using CVSS-style
   bands (collapsing None+Low -> Low, Medium -> Medium, High+Critical -> High).

## Explicit limitation (state this in the viva)

This grounds the *shape* of the labeling function in a real, citable
standard (CVSS v3.1) and a standard defense-in-depth security argument,
rather than inventing weights arbitrarily. It does **not** claim these are
empirically fitted weights or interaction terms from real breach incidence
data for personal devices — no such public dataset exists, which is
precisely the gap this project's literature review identifies. The specific
interaction terms are a designed, documented modeling choice for this
project, not a literature-derived fact — be upfront about this if asked.
