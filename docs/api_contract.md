# API Contract v1 (FROZEN before Desktop Agent implementation)

This is the interface contract between every component. The Desktop Agent's
entire job is to produce a valid `TelemetryPayload` and POST it to `/scan`
— it has zero intelligence beyond collection and transmission.

## 1. Telemetry Schema (the contract)

```jsonc
{
  "device_id": "string, required",
  "os_type": "Windows" | "macOS" | "Linux",  // required
  "os_days_since_update": "number | null",
  "firewall_enabled": "boolean | null",
  "antivirus_enabled": "boolean | null",
  "days_since_av_update": "number | null",
  "browser_safe_browsing_enabled": "boolean | null",
  "browser_autofill_passwords": "boolean | null",
  "risky_extension_count": "integer | null",
  "collected_at": "ISO-8601 datetime, required"
}
```

Only `device_id`, `os_type`, and `collected_at` are hard-required. Every
telemetry value may be `null` — this is what the Rule Engine's
`generate_findings()` tolerates, and what determines whether the backend
runs full RF inference or falls back to the Rule Engine's scalar score.

## 2. REST Endpoints

### `POST /scan`
Accepts one `TelemetryPayload`, runs the full pipeline (Rule Engine +
RF-or-fallback + Counterfactual Recommender), persists the result, returns
the aggregated response.

**Response 200:**
```jsonc
{
  "scan_id": "uuid",
  "device_id": "string",
  "scanned_at": "ISO-8601 datetime",
  "degraded": false,
  "risk_score": 84.7,
  "risk_tier": "Low" | "Medium" | "High",
  "ml_confidence": 0.91,
  "ml_used": true,
  "ml_strategy": "full_7_feature" | "observable_6_feature" | null,
  "telemetry_observed_features": ["..."],
  "telemetry_unavailable_features": ["..."],
  "ml_explanation": [ { "feature": "firewall_enabled", "value": false, "importance": 0.32, "kind": "global_model_importance" } ],
  "findings": [ { "id": "...", "title": "...", "severity_0_10": 2.4, "cvss_rationale": "...", "recommendation": "...", "feature": "..." } ],
  "recommendations": [ { "action": "...", "feature": "...", "current_score": 84.7, "expected_score_after_fix": 73.5, "expected_reduction": 11.2 } ]
}
```
`ml_used` identifies whether the primary score came from RF inference.
`ml_confidence` is the maximum RF class probability, not a guaranteed or
calibrated probability. `ml_explanation` is global RF feature importance for
observed signals, not causal or per-scan attribution.

**Response 422:** validation error (missing required fields, wrong types).

### `GET /scans/{scan_id}`
Retrieve one past scan by ID. **404** if not found.

### `GET /devices/{device_id}/scans?limit=20`
Scan history for a device, most recent first (summary rows only).

### `GET /devices/{device_id}/latest`
Most recent full scan result for a device. **404** if no scans yet.

### `GET /health`
Liveness check: `{"status": "ok", "model_loaded": true, "model_version": "..."}`

### `GET /model/info`
Debug/transparency endpoint — contents of `data/model_schema.json`.

## 3. Partial telemetry and ML availability

`degraded=true` means at least one telemetry field was unavailable; it does
**not** mean ML was unavailable.

1. All seven numeric signals observed: `full_7_feature` RF runs.
2. Only `browser_safe_browsing_enabled` unavailable and all six documented
   observable signals present: `observable_6_feature` RF runs. The unknown
   setting is not imputed or used in recommendations.
3. Any other incomplete shape: the marked rule fallback runs (`ml_used=false`,
   `ml_confidence=null`, `recommendations=[]`). Missing telemetry remains
   unknown and contributes no rule severity.

## 4. Database schema (SQLite via SQLAlchemy, dev; swappable to Postgres)

```
devices
  device_id      TEXT PRIMARY KEY
  first_seen_at  DATETIME
  os_type        TEXT

scans
  scan_id        TEXT PRIMARY KEY (uuid)
  device_id      TEXT FOREIGN KEY -> devices.device_id
  scanned_at     DATETIME
  degraded       BOOLEAN
  risk_score     FLOAT
  risk_tier      TEXT
  ml_confidence  FLOAT NULLABLE
  raw_telemetry  JSON
  findings_json  JSON
  recommendations_json JSON
  assessment_json JSON  // ML availability, strategy, feature availability, explanation
```

## 5. Testing without the Desktop Agent

`POST /scan` accepts hand-built JSON, so every component is fully
exercisable via Postman/Swagger (`/docs`) before any agent code exists.
`backend/postman_collection.json` covers: a full-telemetry scan, a
degraded (partial-null) scan, scan history lookup, and the
health/model-info endpoints.
