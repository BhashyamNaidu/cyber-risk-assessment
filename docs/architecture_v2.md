# Architecture v2 — Evidence-Driven Redesign (FROZEN)

This supersedes the original "hybrid improves accuracy" framing. Every
claim below is backed by an experiment whose code lives in this repo and
can be re-run.

## What changed, and why

**Original hypothesis:** combining the Rule Engine's score with Random
Forest as an engineered feature ("Hybrid-v2") would improve predictive
accuracy over Random Forest alone.

**Test performed:** isolated comparison of two pipelines, identical
train/test splits, identical hyperparameters, identical evaluation
protocol, repeated across 50 paired folds (5-fold stratified CV x 10
repeats) for statistical power:

- Pipeline A: raw telemetry -> Random Forest
- Pipeline B: raw telemetry + rule_score -> Random Forest

**Result:**

| | Mean Accuracy | Std |
|---|---|---|
| Pipeline A | 90.68% | 0.79% |
| Pipeline B | 90.59% | 0.84% |

Paired t-test p = 0.31; Wilcoxon signed-rank p = 0.28; Cohen's d = -0.15
(negligible, slightly negative). Pipeline B wins 21/50 folds, Pipeline A
wins 26/50, 3 ties. **No statistically significant difference.** The
hypothesis is rejected on evidence, not assumption.

**Interpretation:** Random Forest trained on the 7 raw telemetry features
already recovers the interaction structure the rule score was designed to
summarize (`firewall_enabled` and `os_days_since_update` alone account for
~58% of RF's feature importance). The rule score is a redundant, lossy
compression of information the model already has direct access to.

**Consequence:** the Rule Engine is removed from the ML input pipeline
entirely. It is retained for a different, independently justified reason
(below), not as a rescued accuracy claim.

---

## Final architecture

```
Desktop Agent
     |
     v
 Raw Telemetry (structured JSON)
     |
  -----------------------------
  |            |               |
  v            v               v
Rule Engine  Random Forest   Counterfactual
(independent) (independent)  Recommendation Engine
  |            |               ^  (queries trained RF
  |            |_______________|   per candidate fix)
  |                    |
  v                    v
      Response Aggregator
      (backend orchestration only — no scoring logic)
             |
             v
         Dashboard
```

See `docs/architecture_v2.png` for the rendered diagram.

## Component responsibilities (zero overlap)

| Component | Single responsibility | Explicitly NOT responsible for |
|---|---|---|
| **Desktop Agent** | Observe raw OS/browser state, package as structured telemetry, transmit | Any scoring or interpretation |
| **Rule Engine** (`rule_engine.py`) | Deterministic, CVSS-justified per-rule findings (`generate_findings()`) for the explanation panel; fallback scalar score (`rule_based_score()`) only when RF is unavailable or telemetry is incomplete | Feeding the ML model (evidence shows this doesn't help); ranking recommendations by impact |
| **Random Forest** (`train_final_model.py`) | Sole predictive risk-tier classifier. Uses a 7-feature model for complete telemetry and a separately validated 6-feature observable model when Windows Safe Browsing is unavailable | Rule findings/remediation; treating unknown telemetry as factual |
| **Counterfactual Recommendation Engine** (`counterfactual_recommender.py`) | Re-query the trained RF once per actionable fix, rank fixes by expected score reduction | Policy explanation (delegated to Rule Engine); its own model training |
| **Backend / Response Aggregator** | Orchestrate calls to the three components above, merge outputs into one payload, auth | Any scoring or ranking logic itself |
| **Database** | Persist telemetry history, scores, findings, accounts | Any computation |
| **Dashboard** | Present RF's risk tier as primary score, Rule Engine findings as explanation, ranked recommendations | Any scoring or simulation logic |

## Observable-feature strategy for real Windows

Real Windows cannot legitimately observe `browser_safe_browsing_enabled`.
Rather than impute it, the backend routes that exact shape to a second RF
trained without that feature. Both models use held-out validation and
`predict_proba()`. `degraded` records partial telemetry while `ml_used`
records ML availability. The Rule Engine always remains independent: it
returns auditable findings but never supplies the ML score. Counterfactuals
only mutate observed features that participate in the selected model.

The reproducible 75/25 held-out validation is persisted in
`data/model_schema.json`. For the current synthetic dataset, the complete RF
achieves accuracy/F1/ROC-AUC of 0.9104/0.9105/0.9817. The observable RF
achieves 0.7912/0.7907/0.9335; the same-split deterministic Rule Engine
baseline achieves accuracy/F1 of 0.8360/0.8357. This is reported as a
limitation, not hidden: excluding an informative but unobservable signal
reduces synthetic-label accuracy, so the observable model is justified by
deployment validity and its genuine probabilistic ML assessment—not a claim
that it outperforms the rule baseline on every metric. Both results are
synthetic-data evidence and are not real-world incidence estimates.

## Rule Engine's justified role (not an accuracy claim)

1. **Explainable security reasoning** — `generate_findings()` returns
   structured, per-rule output (condition, CVSS-grounded rationale,
   recommendation) for every violated policy, sorted by severity.
2. **Deterministic policy enforcement** — auditable rules, independent of
   any model's internal state.
3. **Graceful degradation** — when telemetry is incomplete,
   `generate_findings()` skips only the affected rule rather than failing,
   and `rule_based_score()` can still produce a fallback number.

## Counterfactual Recommendation Engine

Standard perturb-and-observe technique: for each actionable feature, flip
it to its "fixed" value, re-run the trained RF, measure the change in a
continuous expected risk score (RF class probabilities weighted by
CVSS-band midpoints: Low=20, Medium=55, High=85 on a 0-100 scale). Ranks
fixes by expected reduction. Uses the same model that produces the
dashboard's primary score.

---

## Rewritten research contribution

> We present an automated, explainable personal cyber-risk assessment
> system that (1) replaces manual self-report with automated OS/browser
> telemetry collection, (2) rigorously tests — via a 50-fold paired
> statistical comparison — whether injecting a CVSS-grounded expert rule
> score as an engineered ML feature improves predictive accuracy, finding
> that it does not (p = 0.31), and (3) redesigns the system architecture
> accordingly: a Random Forest classifier for prediction, an independent
> deterministic Rule Engine for explainability and policy auditability, and
> a counterfactual recommendation engine that quantifies expected risk
> reduction per remediation action using the same model that produces the
> displayed score.

**One-sentence paper contribution:**

> We demonstrate, through controlled statistical evaluation rather than
> assumption, that a CVSS-grounded rule engine does not improve Random
> Forest accuracy for personal device cyber-risk classification, and use
> that evidence to redesign the system around each component's genuinely
> justified role — predictive classification, explainable policy
> enforcement, and impact-quantified recommendation — rather than an
> unsupported hybrid-accuracy claim.

## Explicit limitations

- Synthetic training data — CVSS-band-grounded, not empirically fitted to
  real breach incidence for personal devices (no such public dataset
  exists).
- Interaction terms in the label-generation function are a documented
  design choice, not a literature-derived fact.
- The null result on Pipeline B is specific to this feature set and this
  RF configuration; it is not a universal claim that rule-engineered
  features never help tree-based models in other domains.
