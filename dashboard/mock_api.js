/**
 * Mock API — every shape here matches docs/api_contract.md EXACTLY.
 * Swap to the real backend by changing USE_MOCK to false in config.js.
 * No other code should need to change when that flag flips.
 */

const MOCK_LATENCY_MS = 400; // simulates real network timing for realistic loading states

const MOCK_LATEST_SCAN = {
  scan_id: "mock-scan-001",
  device_id: "device-abc123",
  scanned_at: new Date(Date.now() - 2 * 60 * 1000).toISOString(),
  degraded: false,
  risk_score: 72.0,
  risk_tier: "High",
  ml_confidence: 0.91,
  ml_used: true,
  ml_strategy: "full_7_feature",
  telemetry_observed_features: ["os_days_since_update", "firewall_enabled", "antivirus_enabled", "days_since_av_update", "browser_safe_browsing_enabled", "browser_autofill_passwords", "risky_extension_count"],
  telemetry_unavailable_features: [],
  ml_explanation: [{ feature: "firewall_enabled", importance: 0.32, kind: "global_model_importance" }],
  findings: [
    {
      id: "R2_FIREWALL",
      title: "Firewall disabled",
      severity_0_10: 2.4,
      cvss_rationale: "Disabling the firewall satisfies the Attack Vector: Network precondition for a large class of CVEs that would otherwise require local access.",
      recommendation: "Enable the OS firewall.",
      feature: "firewall_enabled",
    },
    {
      id: "R4_AV_STALE",
      title: "Antivirus signatures outdated",
      severity_0_10: 1.8,
      cvss_rationale: "Outdated AV signatures behave like an unpatched local component, reducing detection of recent malware variants.",
      recommendation: "Update antivirus definitions.",
      feature: "days_since_av_update",
    },
    {
      id: "R1_OS_UPDATE",
      title: "Operating system not updated recently",
      severity_0_10: 1.5,
      cvss_rationale: "Unpatched OS vulnerabilities are frequently Network attack vector + Low complexity + No privileges required, placing them in the CVSS High/Critical band.",
      recommendation: "Install pending OS updates as soon as possible.",
      feature: "os_days_since_update",
    },
  ],
  recommendations: [
    { action: "Enable firewall", feature: "firewall_enabled", current_score: 72.0, expected_score_after_fix: 48.0, expected_reduction: 24.0 },
    { action: "Install pending OS updates", feature: "os_days_since_update", current_score: 72.0, expected_score_after_fix: 61.0, expected_reduction: 11.0 },
    { action: "Enable browser safe-browsing", feature: "browser_safe_browsing_enabled", current_score: 72.0, expected_score_after_fix: 66.0, expected_reduction: 6.0 },
  ],
};

const MOCK_DEGRADED_SCAN = {
  scan_id: "mock-scan-002",
  device_id: "device-degraded-1",
  scanned_at: new Date(Date.now() - 5 * 60 * 1000).toISOString(),
  degraded: true,
  risk_score: 18.0,
  risk_tier: "Low",
  ml_confidence: null,
  ml_used: false,
  ml_strategy: null,
  telemetry_observed_features: [],
  telemetry_unavailable_features: ["browser_safe_browsing_enabled"],
  ml_explanation: [],
  findings: [
    {
      id: "R5_SAFE_BROWSING",
      title: "Browser safe-browsing / phishing protection disabled",
      severity_0_10: 1.4,
      cvss_rationale: "Network attack vector, low complexity, no privileges required — the standard profile for drive-by and phishing delivery.",
      recommendation: "Enable safe-browsing / phishing protection in browser settings.",
      feature: "browser_safe_browsing_enabled",
    },
  ],
  recommendations: [],
};

const MOCK_PARTIAL_ML_SCAN = {
  ...MOCK_LATEST_SCAN,
  scan_id: "mock-scan-partial-ml",
  device_id: "device-partial-ml-1",
  degraded: true,
  ml_used: true,
  ml_strategy: "observable_6_feature",
  telemetry_observed_features: ["os_days_since_update", "firewall_enabled", "antivirus_enabled", "days_since_av_update", "browser_autofill_passwords", "risky_extension_count"],
  telemetry_unavailable_features: ["browser_safe_browsing_enabled"],
  recommendations: [{ action: "Enable firewall", feature: "firewall_enabled", current_score: 72, expected_score_after_fix: 48, expected_reduction: 24 }],
};

const MOCK_HISTORY = {
  device_id: "device-abc123",
  scans: [
    { scan_id: "s10", scanned_at: daysAgo(0), risk_score: 72.0, risk_tier: "High" },
    { scan_id: "s9", scanned_at: daysAgo(1), risk_score: 68.0, risk_tier: "High" },
    { scan_id: "s8", scanned_at: daysAgo(2), risk_score: 74.0, risk_tier: "High" },
    { scan_id: "s7", scanned_at: daysAgo(3), risk_score: 55.0, risk_tier: "Medium" },
    { scan_id: "s6", scanned_at: daysAgo(4), risk_score: 60.0, risk_tier: "Medium" },
    { scan_id: "s5", scanned_at: daysAgo(5), risk_score: 45.0, risk_tier: "Medium" },
    { scan_id: "s4", scanned_at: daysAgo(6), risk_score: 38.0, risk_tier: "Low" },
    { scan_id: "s3", scanned_at: daysAgo(7), risk_score: 41.0, risk_tier: "Low" },
    { scan_id: "s2", scanned_at: daysAgo(8), risk_score: 33.0, risk_tier: "Low" },
    { scan_id: "s1", scanned_at: daysAgo(9), risk_score: 30.0, risk_tier: "Low" },
  ],
};

function daysAgo(n) {
  return new Date(Date.now() - n * 24 * 60 * 60 * 1000).toISOString();
}

function delay(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/**
 * Mock scenario switch — lets the dashboard be demoed/tested against every
 * documented case without a live backend. Set via ?scenario= query param.
 */
function getScenario() {
  const params = new URLSearchParams(window.location.search);
  return params.get("scenario") || "normal";
}

export const mockApi = {
  async getLatestScan(deviceId) {
    await delay(MOCK_LATENCY_MS);
    const scenario = getScenario();
    if (scenario === "empty") {
      const err = new Error("No scans yet for this device");
      err.status = 404;
      throw err;
    }
    if (scenario === "error") {
      const err = new Error("Internal server error");
      err.status = 500;
      throw err;
    }
    if (scenario === "degraded") {
      return { ...MOCK_DEGRADED_SCAN, device_id: deviceId };
    }
    if (scenario === "partial-ml") {
      return { ...MOCK_PARTIAL_ML_SCAN, device_id: deviceId };
    }
    if (scenario === "no-findings") {
      return { ...MOCK_LATEST_SCAN, device_id: deviceId, risk_score: 12.0, risk_tier: "Low", findings: [], recommendations: [] };
    }
    return { ...MOCK_LATEST_SCAN, device_id: deviceId };
  },

  async getDeviceHistory(deviceId, limit = 20) {
    await delay(MOCK_LATENCY_MS);
    const scenario = getScenario();
    if (scenario === "empty") {
      const err = new Error("Device not found");
      err.status = 404;
      throw err;
    }
    return { ...MOCK_HISTORY, device_id: deviceId, scans: MOCK_HISTORY.scans.slice(0, limit) };
  },
};
