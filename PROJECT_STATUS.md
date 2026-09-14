# PROJECT_STATUS.md

**Read this file before writing any code in a new session.** It is the
single source of truth for what exists, what's verified, what's broken,
and what's next. If this file and a memory/assumption disagree, this file
wins.

Last updated: **Observable-feature ML iteration in progress.** The backend now
selects a six-feature Random Forest for the documented real-Windows telemetry
shape where Safe Browsing is genuinely unavailable. It does not impute that
field. `degraded` now means partial telemetry; `ml_used` independently records
whether RF inference produced the primary score. Training metadata persists
held-out metrics, baseline comparison, global feature importance, feature order,
and reproducibility inputs. Real-machine execution remains required before
claiming the Windows E2E acceptance test has passed.

Previous dashboard status:
User-facing gauge now shows `security_score = 100 - risk_score` (higher =
better); underlying `risk_score` in the database/API is unchanged.
Degraded scans now show real Rule Engine finding remediation under
"Recommended Actions" instead of just "Unavailable" — no fabricated
counterfactual deltas. 6/6 dashboard regression tests passing.
`dashboard/config.js` remains `USE_MOCK=false`. No backend, ML, agent,
telemetry, Rule Engine, API contract, or database changes.

---

## Frozen (do not redesign — see docs/api_contract.md and docs/architecture_v2.md)

- **Desktop Agent — FROZEN as of real Windows smoke test PASS.** Final
  evidence, preserved verbatim:
  ```
  os_days_since_update: 8.20037203255787       OK
  firewall_enabled: True                         OK
  antivirus_status: (True, 0.0)                  OK
  browser_safe_browsing_enabled: None            ACCEPTED UNKNOWN
  browser_autofill_passwords: True               OK
  risky_extension_count: 0                        OK
  collection_errors from collect(): []
  ```
  5 of 6 fields collect real values. `browser_safe_browsing_enabled`
  remains permanently `None` — confirmed via 3 real-Windows diagnostics
  that no legitimate local Chrome Preferences boolean represents Safe
  Browsing protection state on this Chrome version; `None` here means
  "unknown/unavailable from this telemetry source" and must never be
  read as `False`. `collection_errors: []` confirms no silent failures.
  No further changes to telemetry collection architecture, schema,
  parsers, or WindowsProvider are planned.
- Research: literature review, research gap, novelty, methodology, evaluation protocol.
- ML: dataset generation (`ml/generate_dataset.py`), Rule Engine (`ml/rule_engine.py`),
  Random Forest (`ml/train_final_model.py`), Counterfactual Recommendation
  Engine (`ml/counterfactual_recommender.py`), statistical evaluation
  (`ml/ablation_study.py`), model artifacts (`data/rf_model.joblib` +
  `os_type_encoder.joblib` + `model_schema.json`).
- Architecture: telemetry schema, API contract, backend architecture,
  desktop agent architecture, database schema, dashboard component
  hierarchy and API mapping. All documented in `docs/api_contract.md`,
  `docs/architecture_v2.md`, `docs/dashboard_design.md`.

## Completed components

| Component | Status | Evidence |
|---|---|---|
| Synthetic dataset (CVSS-grounded, interaction terms) | Done | `ml/generate_dataset.py`, reproducible via fixed seed |
| Rule Engine (findings + fallback score) | Done | `ml/rule_engine.py`, tested via `generate_findings()` sample run |
| Random Forest (raw telemetry only) | Done | `ml/train_final_model.py`, held-out test accuracy 91.04% |
| Rejected hypothesis: rule score as ML feature | Done, documented as negative result | 50-fold paired test, p=0.31, Cohen's d=-0.15 — see `docs/architecture_v2.md` |
| Counterfactual Recommendation Engine | Done | `ml/counterfactual_recommender.py`, verified plausible ranking on test case |
| Backend API (all 6 endpoints) | Done | `backend/app/main.py`, all endpoints curl-tested incl. 404/422 paths |
| Degraded-mode pipeline | Done | `backend/app/services.py`, verified via integration test |
| Backend config + structured logging | Done | `backend/app/config.py`, `backend/app/logging_setup.py`, JSON request logs confirmed in server.log |
| Desktop Agent — provider abstraction | Done | `agent/telemetry/base.py`, `factory.py` |
| Desktop Agent — WindowsProvider (2 of 3 NULL fields have targeted fixes based on real evidence; **pending re-verification on Windows**; 1 field still blocked on more evidence) | Fixes made, **not yet re-verified on Windows** | `agent/telemetry/windows_provider.py`, `agent/telemetry/parsers.py` — see Known Issues |
| Desktop Agent — LinuxProvider / MacProvider | Placeholder (intentional, in scope) | Raise `NotImplementedError` cleanly, verified via dry-run test |
| Desktop Agent — thin client (validate/serialize/POST/display) | Done | `agent/client.py`, `agent/main.py` |
| Desktop Agent — config + structured logging | Done | `agent/config.py`, `agent/logging_setup.py` |
| Parser unit tests | Done, all passing, **7 new regression tests added from real evidence** | `agent/tests/test_parsers.py` — 24/24 pass |
| Agent-to-backend integration test (with stand-in provider) | Re-run after fixes, still passing | `agent/tests/integration_test.py` — full + degraded cases both pass |
| Windows smoke test | Run once on real Windows 10 (10.0.26200), Python 3.11.9. 3/6 fields OK, 3/6 NULL. **Not yet re-run since the fixes below.** | `agent/tests/windows_smoke_test.py` |
| Diagnostic script #1 for the 3 NULL fields | Run once. Found real evidence for `os_days_since_update` and `browser_autofill_passwords`. **Had a bug**: its keyword search only printed keys whose own name matched, so it never revealed `safebrowsing`'s child keys even though it recursed into them. | `agent/tests/diagnose_null_fields.py` |
| Diagnostic script #2 for `safebrowsing` structure | Written to fix diagnostic #1's bug — reports `safebrowsing`'s direct children unconditionally (name, type, boolean value only). **Not yet run.** | `agent/tests/diagnose_safebrowsing_keys.py` |
| Postman collection | Done | `backend/postman_collection.json`, 9 requests, all validated |
| **Dashboard — design (wireframe, component hierarchy, API mapping, states)** | **Done** | `docs/dashboard_design.md` |
| **Dashboard — implementation against mock API** | **Done** | `dashboard/index.html`, `app.js`, `style.css`, `mock_api.js`, `real_api.js`, `config.js` |
| **Dashboard — functional tests (5 scenarios, 17 assertions)** | **Done, all passing** | `dashboard/test_dashboard.mjs`, headless jsdom, real DOM execution |
| **Dashboard — visual QA (real headless-Chromium screenshots)** | **Done** | `docs/screenshots/screenshot_{normal,degraded,empty,mobile}.png` |
| **Dashboard — mobile grid-overlap bug** | **Found and fixed** | See `docs/dashboard_design.md` "Bugs found by actually testing" |

## Remaining work (roadmap order — do not skip ahead)

1. **Phase 1: COMPLETE. Desktop Agent FROZEN.** No further action.
2. **Phase 3 (IN PROGRESS):** Reproducible procedure written
   (`docs/phase3_e2e_procedure.md`), CORS/requirements verified via real
   headless-browser test against the live backend. **Not yet run on the
   real Windows machine.** Split into Part A (real Windows Agent, degraded
   path — items 1-4, 7-9) and Part B (hand-built full payload through the
   real API, clearly labeled as not-Agent-sourced — items 5-6), per
   explicit decision: real Windows telemetry always triggers degraded mode
   because `browser_safe_browsing_enabled` is permanently null, so RF/
   Counterfactual cannot be exercised by genuine Agent output alone.
2. **Phase 2 (DESIGN + MOCK IMPLEMENTATION DONE):** Once Phase 1
   completes, flip `dashboard/config.js`'s `USE_MOCK` to `false` and
   re-run integration testing against the real backend + real agent. No
   other dashboard code changes anticipated by design (see
   `docs/dashboard_design.md`).
3. **Phase 3 (blocked on Phase 1 + Phase 2 switch to real backend):** Full
   end-to-end integration testing (real agent + real backend + real
   dashboard, not stand-ins) across normal / degraded / invalid input /
   missing telemetry / backend-failure cases.
4. **Phase 4 (blocked on Phase 3):** Polish — error handling, loading
   states (dashboard loading states already done; recheck against real
   backend timing), README, deployment guide, architecture diagrams, API docs.
5. **Phase 5 (blocked on Phase 4):** Demo prep — realistic demo dataset,
   screenshots (mock versions already exist, may need real-backend
   versions), sample scans, walkthrough.

## Known issues

- **`os_days_since_update` — FIXED, pending re-verification.** Root
  cause: `ConvertTo-Json` on a raw `[datetime]` serialized as a
  `{value, DateTime}` JSON object on this PS/culture configuration, not a
  bare string, confirmed via real captured output. Fix: PowerShell command
  now requests a plain ISO-ish string via `.ToString()` instead of
  `ConvertTo-Json`; parser also defensively handles the JSON-object shape
  should it recur. Regression tests added using the exact captured string.
- **`browser_autofill_passwords` — FIXED with a documented caveat,
  pending re-verification.** Root cause: `credentials_enable_service` was
  only found nested under `account_values` on the real machine, not at
  top level as originally assumed. Fix: parser checks the nested path,
  falling back to the original top-level path for compatibility.
  **Unconfirmed caveat:** whether `account_values` scoping means this
  value is only present/meaningful for a signed-in Chrome account is not
  yet verified — flagged in code comments, not hidden.
- **`browser_safe_browsing_enabled` — INVESTIGATION CLOSED, permanent
  `None` by design, documented as a telemetry-source limitation.** Three
  real-Windows diagnostics confirmed no legitimate local Chrome
  Preferences boolean represents Safe Browsing protection state on this
  Chrome version: no `safebrowsing.enabled`; a full-tree search
  (depth<=6) for Safe-Browsing/protection-level/phishing/malware-related
  boolean keys found none anywhere in the file;
  `scout_reporting_enabled_when_deprecated` was explicitly confirmed
  semantically wrong (a metrics-reporting toggle) and rejected as a
  substitute. Semantics: `None` here means "unknown/unavailable from this
  telemetry source," never "disabled." No further diagnostics planned for
  this field.
- **Diagnostic script #1 bug (meta-issue, not a telemetry bug):**
  `diagnose_null_fields.py`'s `_search_and_print()` only printed a line
  when a key's own name contained a keyword like "safebrowsing" — so
  after correctly recursing into the `safebrowsing` dict, its children
  (e.g. a plausible `enabled` key) never matched that substring and were
  silently never printed, despite being visited. This is why the first
  diagnostic run reported `safebrowsing = <dict, 9 items>` with no further
  detail. Fixed by writing a narrowly-scoped second script instead of
  patching the first (keeping the original script's behavior for the two
  fields it already successfully diagnosed unchanged).
- **AV freshness is a coarse proxy, not a real day-count.**
  `get_antivirus_status()` reports `0.0` (up to date) or `30.0` (stale) —
  a boolean converted to two fixed numbers — because
  `SecurityCenter2.AntiVirusProduct`'s timestamp field is vendor-specific
  and unreliable across products. Documented in `windows_provider.py`;
  acceptable for this project's scope, not a bug.
- **`productState` bitmask decoding provenance:** the byte layout used in
  `parsers.py::parse_av_product_state` is community-reverse-engineered,
  not officially documented by Microsoft. State this honestly if asked in
  viva — flagged in the code comment already.
- **Agent's `TelemetryPayload` duplicates the backend's schema** by
  design (requirement: agent package must stay independent of backend
  code). This is an accepted coupling cost: if `docs/api_contract.md`
  changes, both `agent/client.py` and `backend/app/schemas.py` must be
  updated together, and nothing currently enforces that automatically.
- **Dashboard history sparkline reuses one fixed mock dataset across all
  mock scenarios** (documented limitation, not a bug — resolves itself
  once `USE_MOCK=false`, since `GET /devices/{id}/scans` becomes a real,
  independent call).

## Integration/packaging fixes (Phase 3 prep — NOT architecture changes)

- **`backend/requirements.txt` created.** Previously undocumented —
  dependencies were installed ad hoc; anyone cloning the repo had no way
  to reliably install them. Contains exactly what the backend already
  imports (fastapi, uvicorn, sqlalchemy, pydantic/pydantic-settings,
  python-dotenv, pandas, numpy, scikit-learn, joblib — the last 4 because
  the backend imports `ml/` modules directly). No new packages added.
- **Minimal CORS middleware added to `backend/app/main.py`.** The
  browser-based dashboard and the API run on different local ports, which
  browsers treat as different origins — without this, every dashboard
  fetch to the backend is silently blocked. Scoped to exactly
  `http://localhost:5500` / `http://127.0.0.1:5500` (the dashboard's dev
  server origin, see Phase 3 procedure below), `GET`/`POST` only,
  `Content-Type` header only — no wildcard origins. No routes, schemas,
  or auth changed. **Verified via a real headless-Chromium browser run
  against the live backend: 0 CORS console errors, dashboard correctly
  rendered a real (non-mock) scan response including the degraded-mode
  banner and findings.**
- `dashboard/config.js`'s `USE_MOCK` flipped to `false` — the swap this
  flag was built for since Phase 2. No other dashboard code changed, as
  designed.
- Existing regression suite (`agent/tests/integration_test.py`,
  `agent/tests/test_parsers.py`) re-run after both changes: all still pass.

## Technical debt

- `ml/rule_engine.py::RULE_DEFINITIONS` and
  `ml/counterfactual_recommender.py::ACTIONABLE_FIXES` are two separately
  maintained lists describing the same underlying features. Adding an 8th
  telemetry field requires remembering to update both. Not urgent at
  current scope (7 features); worth a shared feature registry if the rule
  set grows significantly.
- No automated contract test enforcing that `agent/client.py`'s
  `TelemetryPayload` and `backend/app/schemas.py`'s `TelemetryPayload`
  stay in sync — currently a manual discipline, not a checked invariant.
- Same class of duplication now exists a third time:
  `dashboard/mock_api.js`'s mock response shapes must also be kept in sync
  with `backend/app/schemas.py`'s `ScanResponse`/`DeviceScanHistory` by
  hand. Worth a shared JSON-schema source of truth if the contract changes
  frequently going forward; not urgent now since the contract is frozen.

## Deferred improvements (recorded per decision rule: does not improve reliability/correctness -> not implemented now)

- Linux/macOS telemetry providers (explicitly out of scope for this
  milestone, placeholders only).
- Confidence-interval display beyond the single `ml_confidence` scalar
  already returned by the backend.
- Any additional telemetry fields beyond the original 7 (MFA usage,
  password manager detection, etc.) — explicitly ruled unrealistic in the
  original scope-narrowing decision.
- Clicking into a past scan from the history sparkline
  (`GET /scans/{scan_id}`) — deliberately left out of Dashboard v1 to
  avoid visual clutter per explicit instruction; history is currently
  display-only.

## Next milestone

**Phase 1 completion (unblocks Desktop Agent freeze + real-backend
dashboard switch):** Bhash runs `agent/tests/windows_smoke_test.py` on a
real Windows machine and reports results. Once every field is verified
(or documented issues are fixed and re-verified), the Desktop Agent is
frozen, `dashboard/config.js`'s `USE_MOCK` flips to `false`, and Phase 3
(full real-stack integration testing) begins.
