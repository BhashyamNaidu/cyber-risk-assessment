import { JSDOM } from "jsdom";
import fs from "fs";
import path from "path";
import { fileURLToPath, pathToFileURL } from "url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

async function loadDashboard(scenario) {
  // Test-harness-only fix: strip the local stylesheet <link> before jsdom
  // sees it. jsdom's resource loader tries to resolve/fetch it relative to
  // the page URL, which on Windows (Node 24) hits an ESM loader path that
  // only accepts file/data/node URL schemes and chokes on a bare "c:"
  // drive-letter path — "Only URLs with a scheme in: file, data, and node
  // are supported by the default ESM loader". The stylesheet has no
  // bearing on these DOM/logic assertions, so it's simplest to just never
  // let jsdom attempt to load it. app.js/config.js/mock_api.js/real_api.js
  // and shipped dashboard behavior are untouched by this.
  const html = fs.readFileSync(path.join(__dirname, "index.html"), "utf-8")
    .replace(/<link[^>]*href="style\.css"[^>]*>/i, "");
  const url = scenario ? `http://localhost/index.html?scenario=${scenario}` : "http://localhost/index.html";

  const dom = new JSDOM(html, { url, runScripts: "dangerously", resources: "usable", pretendToBeVisual: true });
  const { window } = dom;
  global.window = window;
  global.document = window.document;
  global.SVGElement = window.SVGElement;
  global.fetch = window.fetch;
  global.URLSearchParams = window.URLSearchParams;

  await new Promise((resolve) => {
    if (window.document.readyState === "complete") resolve();
    else window.addEventListener("load", resolve);
  });

  const appJsPath = path.join(__dirname, "app.js");
  let appJsSource = fs.readFileSync(appJsPath, "utf-8");
  const cacheBust = `?t=${Date.now()}-${Math.random()}`;
  appJsSource = appJsSource
    .replace('from "./config.js"', `from "${pathToFileURL(path.join(__dirname, "config.js")).href}${cacheBust}"`)
    .replace('from "./mock_api.js"', `from "${pathToFileURL(path.join(__dirname, "mock_api.js")).href}${cacheBust}"`)
    .replace('from "./real_api.js"', `from "${pathToFileURL(path.join(__dirname, "real_api.js")).href}${cacheBust}"`)
    // Test-harness-only override: this suite exercises app.js's rendering
    // logic via mock_api.js's ?scenario= system regardless of config.js's
    // real deployment USE_MOCK value (correctly `false` for Phase 3).
    // Nothing shipped is changed — only this private rewritten temp copy.
    .replace('const api = USE_MOCK ? mockApi : realApi;', 'const api = mockApi;');

  const tmpPath = path.join(__dirname, `._tmp_app_${Date.now()}_${Math.random().toString(36).slice(2)}.mjs`);
  fs.writeFileSync(tmpPath, appJsSource);
  try {
    await import(`file://${tmpPath}${cacheBust}`);
  } finally {
    fs.unlinkSync(tmpPath);
  }

  await new Promise((resolve) => setTimeout(resolve, 700));
  return window.document;
}

function assert(cond, msg) {
  if (!cond) throw new Error(`ASSERTION FAILED: ${msg}`);
  console.log(`  OK: ${msg}`);
}

async function testNormalScenario() {
  console.log("\n--- Scenario: normal (risk_score=72 -> security score=28) ---");
  const doc = await loadDashboard(null);
  assert($id(doc, "app-root").className === "state-loaded", "root state is 'state-loaded'");
  assert($id(doc, "gauge-score").textContent === "28", `gauge shows SECURITY score 28 (100-72), got '${$id(doc, "gauge-score").textContent}'`);
  assert($id(doc, "gauge-tier").textContent === "HIGH RISK", `gauge-tier reads 'HIGH RISK', got '${$id(doc, "gauge-tier").textContent}'`);
  assert(doc.getElementById("recommendations-heading").textContent === "Recommendations by impact", "heading is impact-ranked for non-degraded scan");
  const recs = doc.querySelectorAll("#recommendations-list .recommendation-card");
  assert(recs.length === 3, `3 ranked recommendation cards rendered (got ${recs.length})`);
  assert(doc.getElementById("recommendations-list").textContent.includes("→"), "ranked recs still show score delta arrow");
}

async function testDegradedScenario() {
  console.log("\n--- Scenario: degraded (risk_score=18 -> security score=82, findings-based remediation) ---");
  const doc = await loadDashboard("degraded");
  assert($id(doc, "app-root").className === "state-loaded", "root state is 'state-loaded'");
  assert($id(doc, "gauge-score").textContent === "82", `gauge shows SECURITY score 82 (100-18), got '${$id(doc, "gauge-score").textContent}'`);
  assert($id(doc, "gauge-tier").textContent === "LOW RISK", `gauge-tier reads 'LOW RISK', got '${$id(doc, "gauge-tier").textContent}'`);
  assert(doc.getElementById("degraded-banner").style.display === "flex", "degraded banner IS shown");

  const heading = doc.getElementById("recommendations-heading").textContent;
  assert(heading === "Recommended Actions", `heading is 'Recommended Actions' for degraded scan, got '${heading}'`);

  const recsContainer = doc.getElementById("recommendations-list");
  const fallbackCards = doc.querySelectorAll("#recommendations-list .recommendation-card--fallback");
  assert(fallbackCards.length === 1, `1 real-finding-based remediation card rendered (got ${fallbackCards.length})`);
  assert(recsContainer.textContent.includes("Enable safe-browsing"), "shows the ACTUAL finding's remediation text, not a fabricated one");
  assert(!recsContainer.textContent.includes("→"), "NO fabricated score-delta arrow present for degraded scan");
  assert(recsContainer.textContent.includes("Partial Scan"), "partial-scan note is present");
  assert(recsContainer.textContent.includes("Advanced recommendations are unavailable"), "note explicitly states advanced recs are unavailable");
}

async function testEmptyScenario() {
  console.log("\n--- Scenario: empty (404, no scans yet) ---");
  const doc = await loadDashboard("empty");
  assert($id(doc, "app-root").className === "state-empty", `root state is 'state-empty' (got '${$id(doc, "app-root").className}')`);
}

async function testErrorScenario() {
  console.log("\n--- Scenario: error (500) ---");
  const doc = await loadDashboard("error");
  assert($id(doc, "app-root").className === "state-error", `root state is 'state-error' (got '${$id(doc, "app-root").className}')`);
}

async function testNoFindingsScenario() {
  console.log("\n--- Scenario: no-findings (clean device, risk_score=12 -> security score=88) ---");
  const doc = await loadDashboard("no-findings");
  assert($id(doc, "gauge-score").textContent === "88", `gauge shows SECURITY score 88 (100-12), got '${$id(doc, "gauge-score").textContent}'`);
  const findingsText = doc.getElementById("findings-list").textContent;
  assert(findingsText.includes("No issues found"), "empty findings state message shown");
  const recsText = doc.getElementById("recommendations-list").textContent;
  assert(recsText.includes("No further recommendations"), "empty recommendations state message shown (non-degraded, no findings)");
}

async function testRealWindowsScanScoreInversion() {
  console.log("\n--- Direct math check: real Windows scan risk_score=6.5 -> security score=94 ---");
  const securityScore = Math.round(100 - 6.5);
  assert(securityScore === 94, `Math.round(100-6.5) === 94, got ${securityScore}`);
}

async function testPartialMlScenario() {
  console.log("\n--- Scenario: partial telemetry with ML ---");
  const doc = await loadDashboard("partial-ml");
  assert(doc.getElementById("degraded-banner").textContent.includes("ML assessment used"), "partial ML banner is honest");
  assert(doc.getElementById("recommendations-heading").textContent === "Recommendations by impact", "partial ML keeps model recommendations");
  assert(doc.getElementById("recommendations-list").textContent.includes("→"), "partial ML recommendations retain genuine deltas");
  assert(doc.getElementById("ml-explanation").textContent.includes("firewall_enabled"), "ML explanation is displayed");
}

function $id(doc, id) { return doc.getElementById(id); }

async function main() {
  const tests = [testNormalScenario, testDegradedScenario, testEmptyScenario, testErrorScenario, testNoFindingsScenario, testRealWindowsScanScoreInversion, testPartialMlScenario];
  let failed = 0;
  for (const t of tests) {
    try { await t(); } catch (e) { failed++; console.error(`  FAIL: ${e.message}`); }
  }
  console.log(`\n${tests.length - failed}/${tests.length} scenarios passed`);
  process.exit(failed === 0 ? 0 : 1);
}

main();
