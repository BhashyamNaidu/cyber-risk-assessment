import { USE_MOCK, DEFAULT_DEVICE_ID, HISTORY_LIMIT } from "./config.js";
import { mockApi } from "./mock_api.js";
import { realApi } from "./real_api.js";

const api = USE_MOCK ? mockApi : realApi;

const TIER_COLORS = { Low: "#3DDC97", Medium: "#F5B342", High: "#F0553F" };
const GAUGE_MIN_ANGLE = -90;
const GAUGE_MAX_ANGLE = 90;

function $(id) {
  return document.getElementById(id);
}

function securityScoreOf(scan) {
  // USER-FACING metric only: Security Score = 100 - risk_score. scan.risk_score
  // itself is never mutated anywhere in this file — every function below reads
  // it fresh from the API response and only ever computes a display value.
  return Math.round(100 - scan.risk_score);
}

function formatRelativeTime(isoString) {
  const diffMs = Date.now() - new Date(isoString).getTime();
  const diffMin = Math.round(diffMs / 60000);
  if (diffMin < 1) return "just now";
  if (diffMin < 60) return `${diffMin} min ago`;
  const diffHr = Math.round(diffMin / 60);
  if (diffHr < 24) return `${diffHr} hr ago`;
  return `${Math.round(diffHr / 24)} day(s) ago`;
}

function formatAbsoluteDate(isoString) {
  const d = new Date(isoString);
  return d.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
}

function formatAbsoluteDateTime(isoString) {
  const d = new Date(isoString);
  return `${formatAbsoluteDate(isoString)}, ${d.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" })}`;
}

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}

// ---- Overview row (new, presentation-only, uses only existing scan fields) ----

function renderOverview(scan) {
  $("overview-score").textContent = `${securityScoreOf(scan)} / 100`;
  $("overview-risk-level").textContent = `${scan.risk_tier.toUpperCase()} RISK`;
  $("overview-risk-level").style.color = TIER_COLORS[scan.risk_tier];
  $("overview-findings").textContent = `${scan.findings.length} detected`;
  $("overview-status").textContent = scan.degraded ? (scan.ml_used ? "PARTIAL + ML" : "PARTIAL") : "COMPLETE + ML";
  $("overview-status").style.color = scan.degraded ? "#F5B342" : "#3DDC97";
}

// ---- Gauge card (existing tested elements untouched; new meta rows added) ----

function renderGauge(scan) {
  const securityScore = securityScoreOf(scan);
  const angle = GAUGE_MIN_ANGLE + (scan.risk_score / 100) * (GAUGE_MAX_ANGLE - GAUGE_MIN_ANGLE);
  const color = TIER_COLORS[scan.risk_tier];

  $("gauge-needle").setAttribute("transform", `rotate(${angle} 110 110)`);
  $("gauge-needle").setAttribute("stroke", color);
  $("gauge-score").textContent = securityScore;
  $("gauge-tier").textContent = `${scan.risk_tier.toUpperCase()} RISK`;
  $("gauge-tier").style.color = color;

  $("confidence-badge").style.display = scan.ml_confidence == null ? "none" : "inline-flex";
  if (scan.ml_confidence != null) {
    $("confidence-value").textContent = `${Math.round(scan.ml_confidence * 100)}%`;
  }

  $("degraded-banner").style.display = scan.degraded ? "flex" : "none";
  if (scan.degraded) {
    $("degraded-banner-text").textContent = scan.ml_used
      ? "⚠ Partial telemetry — ML assessment used the available security signals."
      : "⚠ Partial scan — ML was unavailable; score reflects fallback rules only.";
  }
  $("last-scan-time").textContent = `Last scan: ${formatRelativeTime(scan.scanned_at)}`;
  $("device-label").textContent = scan.device_id;

  // New informational rows — purely additive, use only fields already on `scan`.
  $("meta-risk-score").textContent = `${scan.risk_score.toFixed(1)} / 100`;
  $("meta-scan-status").textContent = scan.degraded ? "Partial" : "Complete";
  $("meta-last-scan").textContent = formatRelativeTime(scan.scanned_at);

  const tierPhrase = { Low: "low", Medium: "moderate", High: "high" }[scan.risk_tier] || scan.risk_tier.toLowerCase();
  let explanation = `Your device currently has a ${tierPhrase} measured security risk.`;
  explanation += scan.ml_used
    ? (scan.degraded ? " Some telemetry was unavailable, but ML assessed risk using the observed security signals."
      : " ML assessed overall risk from your device telemetry.")
    : " ML could not assess this incomplete telemetry, so the score uses fallback rules.";
  $("score-explanation").textContent = explanation;
}

// ---- Findings (structured cards; "No issues found" empty state text preserved) ----

function renderFindings(findings) {
  const container = $("findings-list");
  container.innerHTML = "";

  if (findings.length === 0) {
    container.innerHTML = `<p class="empty-state">No issues found — this device looks good.</p>`;
    return;
  }

  for (const f of findings) {
    const severityBand = f.severity_0_10 >= 2.0 ? "High" : f.severity_0_10 >= 1.0 ? "Medium" : "Low";
    const card = document.createElement("div");
    card.className = "finding-card";
    card.innerHTML = `
      <div class="finding-header">
        <span class="severity-badge" style="background:${TIER_COLORS[severityBand]}22; color:${TIER_COLORS[severityBand]}; border-color:${TIER_COLORS[severityBand]}55;">${severityBand.toUpperCase()}</span>
        <span class="finding-title">${escapeHtml(f.title)}</span>
      </div>
      <div class="finding-recommendation-block">
        <span class="finding-recommendation-label">Recommendation</span>
        <p class="finding-recommendation">${escapeHtml(f.recommendation)}</p>
      </div>
    `;
    container.appendChild(card);
  }
}

// ---- Recommendations — heading text, card classes/counts, and arrow-vs-no-arrow
// rules are exactly what dashboard/test_dashboard.mjs asserts; only visual
// structure inside each branch was changed (numbering), never the text rules. ----

function renderRecommendations(scan) {
  const container = $("recommendations-list");
  const heading = $("recommendations-heading");
  container.innerHTML = "";

  if (scan.degraded && !scan.ml_used) {
    heading.textContent = "Recommended Actions";
    if (scan.findings.length > 0) {
      scan.findings.forEach((f, i) => {
        const card = document.createElement("div");
        card.className = "recommendation-card recommendation-card--fallback";
        card.innerHTML = `
          <span class="rec-number">${i + 1}</span>
          <span class="rec-action">${escapeHtml(f.recommendation)}</span>
        `;
        container.appendChild(card);
      });
    } else {
      container.innerHTML = `<p class="empty-state">No issues found — no remediation needed.</p>`;
    }
    const note = document.createElement("p");
    note.className = "partial-scan-note";
    note.textContent = "Partial Scan: Some telemetry could not be collected. Advanced recommendations are unavailable for this scan.";
    container.appendChild(note);
    return;
  }

  heading.textContent = "Recommendations by impact";
  if (scan.recommendations.length === 0) {
    container.innerHTML = `<p class="empty-state">No further recommendations.</p>`;
    return;
  }

  for (const r of scan.recommendations) {
    const card = document.createElement("div");
    card.className = "recommendation-card";
    card.innerHTML = `
      <span class="rec-action">${escapeHtml(r.action)}</span>
      <span class="rec-delta">
        ${r.current_score.toFixed(0)} &rarr; ${r.expected_score_after_fix.toFixed(0)}
        <span class="rec-reduction">(&minus;${r.expected_reduction.toFixed(0)})</span>
      </span>
    `;
    container.appendChild(card);
  }
}

// ---- History: honest empty/first-scan state instead of a broken-looking
// chart; real multi-scan trend when actual history data exists. No fabricated
// scans are ever introduced. ----

function renderHistory(scan, historyScans) {
  const container = $("history-sparkline");
  container.innerHTML = "";

  if (!historyScans || historyScans.length <= 1) {
    const securityScore = securityScoreOf(scan);
    const color = TIER_COLORS[scan.risk_tier];
    container.innerHTML = `
      <div class="history-first-scan">
        <div class="history-first-label">First recorded scan</div>
        <div class="history-first-date">${formatAbsoluteDate(scan.scanned_at)}</div>
        <div class="history-first-score"><span class="history-dot" style="background:${color}"></span>${securityScore} Security Score</div>
        <p class="history-first-note">No previous scans available. Run additional scans to see your security trend.</p>
      </div>
    `;
    return;
  }

  const ordered = historyScans.slice().reverse(); // oldest -> newest
  const scores = ordered.map((s) => Math.round(100 - s.risk_score));
  const tiers = ordered.map((s) => s.risk_tier);
  // The most recent history entry is "current" if it matches the displayed
  // scan (by scan_id, not just position) — highlighted distinctly so the
  // live score isn't visually confused with past ones.
  const currentIndex = ordered.findIndex((s) => s.scan_id === scan.scan_id);
  const width = 280, height = 60, barGap = 4;
  const barWidth = (width - barGap * (scores.length - 1)) / scores.length;

  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
  svg.setAttribute("class", "sparkline-svg");

  scores.forEach((score, i) => {
    const barHeight = Math.max((score / 100) * height, 2);
    const rect = document.createElementNS("http://www.w3.org/2000/svg", "rect");
    rect.setAttribute("x", i * (barWidth + barGap));
    rect.setAttribute("y", height - barHeight);
    rect.setAttribute("width", barWidth);
    rect.setAttribute("height", barHeight);
    rect.setAttribute("fill", TIER_COLORS[tiers[i]] || "#8A93A3");
    rect.setAttribute("rx", "1.5");
    if (i === currentIndex) {
      rect.setAttribute("stroke", "#E8EAED");
      rect.setAttribute("stroke-width", "1.5");
    }
    svg.appendChild(rect);
  });

  container.appendChild(svg);

  if (currentIndex !== -1) {
    const marker = document.createElement("div");
    marker.className = "history-current-marker";
    marker.innerHTML = `<span class="history-current-dot"></span>Current scan highlighted`;
    container.appendChild(marker);
  }

  const labels = document.createElement("div");
  labels.className = "history-date-labels";
  const firstIso = ordered[0].scanned_at;
  const lastIso = ordered[ordered.length - 1].scanned_at;
  const sameDay = formatAbsoluteDate(firstIso) === formatAbsoluteDate(lastIso);
  // Same-day history (e.g. several rescans in one sitting) reads as two
  // identical dates otherwise — show time-of-day instead so the labels
  // stay meaningful. Across different days, dates remain more useful.
  const labelFor = (iso) => (sameDay
    ? new Date(iso).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" })
    : formatAbsoluteDate(iso));
  labels.innerHTML = `<span>${labelFor(firstIso)}</span><span>${labelFor(lastIso)}</span>`;
  container.appendChild(labels);
}

// ---- Scan Details (new, purely additive, only existing API fields) ----

function renderScanDetails(scan) {
  const container = $("scan-details");
  container.innerHTML = "";

  const rows = [
    ["Device ID", scan.device_id],
    ["Scan ID", scan.scan_id],
    ["Scan Time", formatAbsoluteDateTime(scan.scanned_at)],
    ["Scan Status", scan.degraded ? "Partial" : "Complete"],
    ["ML Assessment", scan.ml_used ? "Used" : "Unavailable"],
    ["ML Strategy", scan.ml_strategy || "Rule fallback"],
    ["Telemetry", `${(scan.telemetry_observed_features || []).length}/7 observed`],
    ["Risk Score", `${scan.risk_score.toFixed(1)} / 100`],
    ["Risk Tier", scan.risk_tier],
    ["ML Confidence", scan.ml_confidence != null ? `${Math.round(scan.ml_confidence * 100)}%` : "Not available"],
  ];

  for (const [label, value] of rows) {
    const row = document.createElement("div");
    row.className = "scan-detail-row";
    row.innerHTML = `<span class="scan-detail-label">${escapeHtml(label)}</span><span class="scan-detail-value">${escapeHtml(String(value))}</span>`;
    container.appendChild(row);
  }
}

function renderModelExplanation(scan) {
  const container = $("ml-explanation");
  container.innerHTML = "";
  if (!scan.ml_used) {
    $("ml-explanation-note").textContent = "No ML explanation is available because this scan used the rule fallback.";
    return;
  }
  $("ml-explanation-note").textContent = "Global Random Forest feature importance for the observed signals used by this model. It describes model influence, not causality for this individual scan.";
  for (const item of scan.ml_explanation || []) {
    const row = document.createElement("div");
    row.className = "scan-detail-row";
    row.innerHTML = `<span class="scan-detail-label">${escapeHtml(item.feature)}</span><span class="scan-detail-value">importance ${Number(item.importance).toFixed(3)}</span>`;
    container.appendChild(row);
  }
}

// ---- Score explainer (new, static band legend + current numbers) ----

function renderScoreExplainer(scan) {
  $("score-explainer-current").innerHTML = `
    <div class="score-meta-row"><span>Current Security Score</span><span>${securityScoreOf(scan)}</span></div>
    <div class="score-meta-row"><span>Underlying Risk Score</span><span>${scan.risk_score.toFixed(1)}</span></div>
  `;
}

function showLoading() { $("app-root").className = "state-loading"; }
function showEmpty() { $("app-root").className = "state-empty"; }
function showError(message) {
  $("app-root").className = "state-error";
  $("error-message").textContent = message;
}
function showLoaded() { $("app-root").className = "state-loaded"; }

async function loadDashboard() {
  showLoading();
  const deviceId = DEFAULT_DEVICE_ID;
  $("device-label").textContent = deviceId;

  try {
    const [scan, history] = await Promise.all([
      api.getLatestScan(deviceId),
      api.getDeviceHistory(deviceId, HISTORY_LIMIT).catch(() => ({ scans: [] })),
    ]);

    renderOverview(scan);
    renderGauge(scan);
    renderFindings(scan.findings);
    renderRecommendations(scan);
    renderHistory(scan, history.scans);
    renderScanDetails(scan);
    renderModelExplanation(scan);
    renderScoreExplainer(scan);
    showLoaded();
  } catch (err) {
    if (err.status === 404) {
      showEmpty();
    } else {
      showError(err.message || "Could not load dashboard data. Check your connection and try again.");
    }
  }
}

$("refresh-button").addEventListener("click", loadDashboard);
$("retry-button").addEventListener("click", loadDashboard);

loadDashboard();
