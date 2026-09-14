# Phase 3 — End-to-End Integration Test Procedure

Real Windows telemetry is a partial-but-ML-capable path: the known unavailable
Safe Browsing field selects the validated observable six-feature RF. The
Agent's real response must show `degraded=true`, `ml_used=true`, a non-null
`ml_confidence`, `ml_strategy="observable_6_feature"`, and no recommendation
for the unknown browser field.

## Why two parts (do not skip this context)

`browser_safe_browsing_enabled` is permanently `None` on real Windows
Chrome (Phase 1, investigation closed — no legitimate local source exists).
It remains explicitly unavailable, never false. The observable model is
trained without that feature, so the real agent executes RF inference rather
than falling back to rules.

---

## Part A — Real Windows Agent, full pipeline (degraded path)

Three terminals needed: backend, dashboard, agent.

**Terminal 1 — Backend**
```
cd backend
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
del ..\data\cyberrisk.db   (if it exists, for a clean run)
uvicorn app.main:app --host 0.0.0.0 --port 8000
```
Leave running. Confirm `http://localhost:8000/health` shows `model_loaded: true`.

**Terminal 2 — Dashboard**
```
cd dashboard
python -m http.server 5500
```
Leave running. Do NOT use a different port — `5500` is the exact origin whitelisted in the backend's CORS config.

**Terminal 3 — Agent**
```
cd agent
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python main.py
```
This performs a REAL scan. Confirm the console shows `[PARTIAL TELEMETRY — ML
assessment used available security signals]`, a model confidence, and
model-derived recommendations only for observed features.

**Find the agent's device_id and point the dashboard at it:**
```
type %USERPROFILE%\.cyberrisk_agent\device_id
```
Copy that value. Open `dashboard/config.js`, set:
```js
export const DEFAULT_DEVICE_ID = "<paste the value here>";
```
(This is the one file documented since Phase 2 as the only thing that should need to change — no other edit needed.) Refresh the dashboard server is not required; just reload the browser page after saving.

**Verify in browser:** open `http://localhost:5500/index.html`.
- Open DevTools console — confirm **zero CORS errors**.
- Confirm the gauge shows a real score/tier and ML confidence, the partial
  banner states that ML used observed signals, findings are populated as
  applicable, and recommendations show genuine RF deltas without Safe Browsing.

**Verify history updates (item 9):** run `python main.py` in Terminal 3 a second time, reload the dashboard, confirm the Risk History panel now shows 2 bars instead of 1.

This covers the real-agent ML, Rule Engine, counterfactual, persistence, and
dashboard path. Part B remains useful as a complete-telemetry regression test.

---

## Part B — RF + Counterfactual verification (real API, hand-built payload — NOT Windows Agent)

With the backend from Part A still running:

```
curl -X POST http://localhost:8000/scan -H "Content-Type: application/json" -d "{\"device_id\": \"device-synthetic-fullpayload-test\", \"os_type\": \"Windows\", \"os_days_since_update\": 150, \"firewall_enabled\": false, \"antivirus_enabled\": false, \"days_since_av_update\": 45, \"browser_safe_browsing_enabled\": false, \"browser_autofill_passwords\": true, \"risky_extension_count\": 3, \"collected_at\": \"2026-08-20T05:00:00Z\"}"
```

Uses a deliberately different `device_id` (`device-synthetic-fullpayload-test`) so it never mixes with the real Agent's scan history from Part A.

**Verify in the response JSON:**
- `"degraded": false`
- `"ml_confidence"` is a real number, not `null` — confirms RF ran
- `"recommendations"` is a non-empty, ranked list — confirms the Counterfactual Recommendation Engine ran
- `"findings"` populated with CVSS-justified entries — confirms Rule Engine ran (same as Part A, just alongside RF this time)

This is the same Rule Engine, same trained RF model, same Counterfactual Engine, same database, same API as Part A — only the telemetry input's *source* differs (hand-built vs. agent-collected), which is exactly why this is labeled separately rather than folded into "the Windows Agent test."

---

## What "pass" looks like

| Item | Verified by |
|---|---|
| 1. Agent collects telemetry | Part A, Terminal 3 console output |
| 2. Agent sends payload | Part A, Terminal 3 console output ("Sending scan" log) |
| 3. Backend accepts payload | Part A, HTTP 200 + scan_id returned |
| 4. Rule Engine generates findings | Part A, dashboard findings panel |
| 5. RF generates primary score/tier | Part B, `ml_confidence` non-null |
| 6. Counterfactual generates recommendations | Part B, non-empty `recommendations` |
| 7. Scan persisted | Part A + B, `GET /scans/{scan_id}` returns it |
| 8. Dashboard retrieves/displays | Part A, browser screenshot/console check |
| 9. Risk history updates | Part A, second agent run |
| 10. No silent mock/synthetic fallback | Both parts use the real API/Rule Engine/RF/Counterfactual/DB — Part B's synthetic *input* is explicit and labeled, never presented as Agent output |
