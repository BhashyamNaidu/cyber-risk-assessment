# Dashboard Design — Phase 2

Read-only presentation layer. Per the frozen architecture, only the
Desktop Agent collects telemetry — the Dashboard has no scan-triggering
capability, only Refresh (re-fetch latest data).

## Component hierarchy

```
App
 ├─ Header (device_id, last scan timestamp, Refresh button)
 ├─ ScoreGaugePanel
 │    ├─ RiskGauge (score, tier)
 │    ├─ ConfidenceBadge (hidden if degraded)
 │    └─ DegradedBanner (shown only if degraded=true)
 ├─ RiskHistoryPanel → HistorySparkline
 ├─ FindingsPanel → FindingCard[]
 └─ RecommendationsPanel → RecommendationCard[]
```

## API mapping

| Component | Endpoint |
|---|---|
| ScoreGaugePanel, FindingsPanel, RecommendationsPanel | `GET /devices/{id}/latest` |
| RiskHistoryPanel | `GET /devices/{id}/scans?limit=10` |

## States implemented and tested

- **Loading**: skeleton placeholders on gauge/findings/recommendations panels.
- **Empty** (404 — no scans yet): onboarding message directing to run the Desktop Agent.
- **Error** (network/5xx): error banner with Retry.
- **Loaded, normal**: full gauge/findings/recommendations/history.
- **Loaded, degraded**: banner shown, confidence badge hidden, recommendations panel shows "Unavailable" instead of an empty list.
- **Loaded, no findings/recommendations** (clean device): distinct positive-framing empty-state messages, not blank panels.

All 5 states verified via `dashboard/test_dashboard.mjs` (17 assertions,
headless jsdom, actually executing app.js against mock_api.js — not just
reviewed) and visually via real headless-Chromium screenshots in
`docs/screenshots/`.

## Mock -> real backend switch

`dashboard/config.js`'s `USE_MOCK` flag is the only thing that changes.
`mock_api.js` and `real_api.js` implement an identical interface
(`getLatestScan`, `getDeviceHistory`), so `app.js` never needs to change.
Mock scenarios are selectable via `?scenario=` query param
(`degraded`, `empty`, `error`, `no-findings`), matching every state
`docs/api_contract.md` documents.

## Bugs found by actually testing (not just reviewing)

1. **Mobile layout bug**: desktop CSS Grid used explicit `grid-row`
   placement (2 columns x 2 rows). The mobile media query collapsed
   `grid-column` to 1 but did not reset `grid-row` — Gauge and Findings
   panels ended up in the same grid cell, overlapping, with Findings
   painting over the Gauge (invisible, not just misaligned). Only caught
   via an actual headless-Chromium screenshot at mobile viewport width;
   invisible from code review alone. Fixed by resetting `grid-row: auto`
   in the mobile breakpoint.
2. **Confidence badge spacing**: minor visual issue where "Model
   confidence:" and the percentage ran together without a space in
   flexbox layout. Fixed by splitting into two spans with an explicit
   `gap`.

## Known limitation

History sparkline currently reuses the same 10-scan mock dataset
regardless of which mock scenario is selected (e.g. the "degraded"
scenario still shows the "normal" scenario's history). Acceptable for
design/demo purposes; not a bug in the real-backend path, since
`GET /devices/{id}/scans` is a real, independent call once `USE_MOCK=false`.
