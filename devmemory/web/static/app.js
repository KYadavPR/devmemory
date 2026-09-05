/**
 * DevMemory Dashboard Application Logic
 */

let projectData = null;
let versionsList = [];
let featuresList = [];
let currentDetailVersionId = null;
let currentTimelineFilter = "ALL";

// Initialize on DOM load
document.addEventListener("DOMContentLoaded", () => {
  setupNavigation();
  setupEventListeners();
  loadAllData();
});

// Setup tab switching
function setupNavigation() {
  const navButtons = document.querySelectorAll(".nav-btn");
  navButtons.forEach((btn) => {
    btn.addEventListener("click", () => {
      const tab = btn.getAttribute("data-tab");
      switchTab(tab);
    });
  });
}

function switchTab(tabId) {
  document.querySelectorAll(".nav-btn").forEach((b) => b.classList.remove("active"));
  document.querySelectorAll(".tab-content").forEach((c) => c.classList.remove("active"));

  const targetBtn = document.querySelector(`.nav-btn[data-tab="${tabId}"]`);
  const targetContent = document.getElementById(`tab-${tabId}`);

  if (targetBtn) targetBtn.classList.add("active");
  if (targetContent) targetContent.classList.add("active");

  // Specific tab initialization
  if (tabId === "compare" && versionsList.length >= 2) {
    populateCompareDropdowns();
  }
}

function setupEventListeners() {
  document.getElementById("btnRefresh").addEventListener("click", () => loadAllData());

  // Timeline filters
  document.querySelectorAll(".filter-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".filter-btn").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      currentTimelineFilter = btn.getAttribute("data-filter");
      renderTimeline();
    });
  });

  // Compare execution
  document.getElementById("btnExecuteCompare").addEventListener("click", () => {
    const vA = document.getElementById("compareSelectA").value;
    const vB = document.getElementById("compareSelectB").value;
    if (vA && vB) {
      loadComparison(vA, vB);
    }
  });

  // Detail restore
  document.getElementById("btnDetailRestore").addEventListener("click", () => {
    if (currentDetailVersionId) {
      triggerRestore(currentDetailVersionId);
    }
  });

  // Memory search
  const memSearch = document.getElementById("memorySearchInput");
  if (memSearch) {
    memSearch.addEventListener("input", (e) => {
      const q = e.target.value.trim();
      if (q.length > 1) {
        searchMemory(q);
      } else {
        loadMemoryWarnings();
      }
    });
  }
}

// Fetch all project data
async function loadAllData() {
  try {
    const [pRes, vRes, fRes, aRes] = await Promise.all([
      fetch("/api/project"),
      fetch("/api/versions?limit=100"),
      fetch("/api/features"),
      fetch("/api/analytics"),
    ]);

    projectData = await pRes.json();
    versionsList = await vRes.json();
    featuresList = await fRes.json();
    const analyticsData = await aRes.json();

    renderHeader();
    renderOverview();
    renderTimeline();
    renderFeatures();
    loadMemoryWarnings();
    renderAnalytics(analyticsData);

    // If there are versions, populate Detail tab with the latest
    if (versionsList.length > 0 && !currentDetailVersionId) {
      selectVersionDetail(versionsList[versionsList.length - 1].version_id);
    }
  } catch (err) {
    console.error("Failed to load DevMemory data:", err);
  }
}

// Render Header & Project Name
function renderHeader() {
  if (!projectData) return;
  const nameEl = document.getElementById("headerProjectName");
  nameEl.textContent = `${projectData.project_name || "DevMemory"} (v${projectData.current_version || 0})`;
}

// Render Overview Tab
function renderOverview() {
  if (!projectData) return;

  document.getElementById("statCurrentVersion").textContent = `v${projectData.current_version || 0}`;
  document.getElementById("statTotalVersions").textContent = projectData.total_versions || 0;

  const stEl = document.getElementById("statLatestStatus");
  const latestSt = projectData.latest_status || "N/A";
  stEl.innerHTML = `<span class="badge-status ${latestSt}">${latestSt}</span>`;

  // Test pass rate
  const passed = projectData.total_tests_passed || 0;
  const failed = projectData.total_tests_failed || 0;
  const total = passed + failed;
  const rate = total > 0 ? Math.round((passed / total) * 100) : 100;
  document.getElementById("statTestPassRate").textContent = `${rate}%`;
  document.getElementById("statTestCounts").textContent = `${passed} passed · ${failed} failed`;

  // Features count
  const compCount = (projectData.features || []).filter((f) => f.status === "COMPLETE").length;
  document.getElementById("statFeatureCount").textContent = (projectData.features || []).length;
  document.getElementById("statFeatureSummary").textContent = `${compCount} completed`;

  // Active Baseline Metrics
  const metricsBox = document.getElementById("overviewMetricsContainer");
  metricsBox.innerHTML = "";
  const metrics = projectData.latest_metrics || {};
  const metricKeys = Object.keys(metrics);

  if (metricKeys.length === 0) {
    metricsBox.innerHTML = `<span style="color: var(--text-muted); font-size: 0.88rem;">No metrics recorded yet.</span>`;
  } else {
    metricKeys.forEach((k) => {
      const chip = document.createElement("div");
      chip.className = "chip-metric";
      chip.style.padding = "6px 14px";
      chip.style.fontSize = "0.85rem";
      chip.innerHTML = `<span>${k}:</span> <b>${metrics[k]}</b>`;
      metricsBox.appendChild(chip);
    });
  }

  // Recent Versions List
  const recentBox = document.getElementById("recentVersionsList");
  recentBox.innerHTML = "";
  const recents = versionsList.slice(-4).reverse();

  if (recents.length === 0) {
    recentBox.innerHTML = `<div style="color: var(--text-muted);">No iterations recorded yet.</div>`;
    return;
  }

  recents.forEach((v) => {
    recentBox.appendChild(createVersionCardElement(v));
  });
}

// Render Timeline Tab
function renderTimeline() {
  const container = document.getElementById("timelineList");
  container.innerHTML = "";

  let filtered = [...versionsList].reverse();
  if (currentTimelineFilter !== "ALL") {
    filtered = filtered.filter((v) => v.status === currentTimelineFilter || (currentTimelineFilter === "REGRESSION" && v.is_regression));
  }

  if (filtered.length === 0) {
    container.innerHTML = `<div style="color: var(--text-muted); padding: 1.5rem; text-align: center;">No versions match filter '${currentTimelineFilter}'.</div>`;
    return;
  }

  filtered.forEach((v) => {
    container.appendChild(createVersionCardElement(v));
  });
}

function createVersionCardElement(v) {
  const card = document.createElement("div");
  const isReg = v.is_regression || v.status === "REGRESSION";
  const isSucc = v.status === "SUCCESS";
  card.className = `version-card glass ${isReg ? "is-regression" : isSucc ? "is-success" : ""}`;

  const metricsObj = v.metrics || {};
  const metricsChips = Object.keys(metricsObj)
    .slice(0, 3)
    .map((k) => `<span class="chip-metric">${k}: <b>${metricsObj[k]}</b></span>`)
    .join(" ");

  const cpTag = v.checkpoint_id
    ? `<span style="color: var(--accent-purple); font-size: 0.78rem;">Entire CP: ${v.checkpoint_id.substring(0, 10)}...</span>`
    : "";

  card.innerHTML = `
    <div class="v-card-top">
      <div style="display: flex; align-items: center; gap: 0.75rem;">
        <span class="v-id-tag">v${v.version_id}</span>
        <span class="badge-status ${v.status}">${v.status}</span>
        ${v.feature ? `<span style="font-size: 0.78rem; color: #93c5fd; background: rgba(59, 130, 246, 0.1); padding: 2px 8px; border-radius: 4px;">${v.feature}</span>` : ""}
      </div>
      <span style="font-size: 0.78rem; color: var(--text-muted);">${formatDate(v.timestamp)}</span>
    </div>
    <div class="v-intent">${escapeHtml(v.intent || "Development step")}</div>
    <div class="v-meta-row">
      <span class="v-meta-item" style="color: var(--accent-cyan);">
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"></path><circle cx="12" cy="7" r="4"></circle></svg>
        ${escapeHtml(v.agent || "human")}
      </span>
      <span class="v-meta-item mono">
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="18" r="3"></circle><circle cx="6" cy="6" r="3"></circle><circle cx="18" cy="6" r="3"></circle><path d="M18 9v2a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2V9"></path><path d="M12 12v3"></path></svg>
        ${(v.git_commit || "").substring(0, 7)}
      </span>
      <span>+${v.additions || 0} / -${v.deletions || 0} lines</span>
      ${metricsChips}
      ${cpTag}
    </div>
  `;

  card.addEventListener("click", () => {
    selectVersionDetail(v.version_id);
    switchTab("detail");
  });

  return card;
}

// Version Detail View
async function selectVersionDetail(versionId) {
  currentDetailVersionId = versionId;
  try {
    const res = await fetch(`/api/versions/${versionId}`);
    const v = await res.json();

    document.getElementById("detailVersionId").textContent = `v${v.version_id}`;
    const badge = document.getElementById("detailStatusBadge");
    badge.className = `badge-status ${v.status}`;
    badge.textContent = v.status;

    document.getElementById("detailFeature").textContent = v.feature || "N/A";
    document.getElementById("detailAgent").textContent = v.agent || "human";
    document.getElementById("detailCommit").textContent = v.git_commit || "N/A";
    document.getElementById("detailCheckpoint").textContent = v.checkpoint_id || "None linked";
    document.getElementById("detailTimestamp").textContent = formatDate(v.timestamp);

    document.getElementById("detailIntent").textContent = v.intent || "No intent description";

    // Analysis
    const analysisBox = document.getElementById("detailAnalysisBox");
    if (v.is_regression || v.status === "REGRESSION") {
      analysisBox.className = "alert-box warning";
    } else {
      analysisBox.className = "alert-box info";
    }
    document.getElementById("detailAnalysisText").textContent = v.analysis || "No heuristic analysis available.";
    document.getElementById("detailRecommendationText").textContent = v.recommendation || "Maintain standard validation.";

    // Metrics Grid
    const mGrid = document.getElementById("detailMetricsGrid");
    mGrid.innerHTML = "";
    const metrics = v.metrics || {};
    const keys = Object.keys(metrics);
    if (keys.length === 0) {
      mGrid.innerHTML = `<span style="color: var(--text-muted); font-size: 0.85rem;">No metrics recorded.</span>`;
    } else {
      keys.forEach((k) => {
        const item = document.createElement("div");
        item.className = "chip-metric";
        item.style.padding = "8px 12px";
        item.innerHTML = `<div style="font-size: 0.72rem; color: var(--text-muted); text-transform: uppercase;">${k}</div><div style="font-size: 1.1rem; font-weight: 700; color: var(--accent-cyan);">${metrics[k]}</div>`;
        mGrid.appendChild(item);
      });
    }

    // Tests
    document.getElementById("detailTestsPassed").textContent = v.tests_passed !== null ? v.tests_passed : "-";
    document.getElementById("detailTestsFailed").textContent = v.tests_failed !== null ? v.tests_failed : "-";

    // Git Diff
    const diffStats = document.getElementById("detailDiffStats");
    diffStats.textContent = `+${v.additions || 0} / -${v.deletions || 0} lines in ${(v.changed_files || []).length} files`;

    // Fetch diff against previous version
    const prevVid = v.version_id > 1 ? v.version_id - 1 : v.version_id;
    const diffRes = await fetch(`/api/versions/compare?a=${prevVid}&b=${v.version_id}`);
    const diffData = await diffRes.json();
    renderDiffContent("detailDiffBody", diffData.diff_text || "No code diff available.");
  } catch (err) {
    console.error("Failed to load version detail:", err);
  }
}

// Compare Dropdowns & Execution
function populateCompareDropdowns() {
  const selA = document.getElementById("compareSelectA");
  const selB = document.getElementById("compareSelectB");
  selA.innerHTML = "";
  selB.innerHTML = "";

  versionsList.forEach((v) => {
    const optA = document.createElement("option");
    optA.value = v.version_id;
    optA.textContent = `v${v.version_id} - ${v.status} (${(v.intent || "").substring(0, 30)})`;

    const optB = document.createElement("option");
    optB.value = v.version_id;
    optB.textContent = `v${v.version_id} - ${v.status} (${(v.intent || "").substring(0, 30)})`;

    selA.appendChild(optA);
    selB.appendChild(optB);
  });

  // Default selection: last two versions
  if (versionsList.length >= 2) {
    selA.value = versionsList[versionsList.length - 2].version_id;
    selB.value = versionsList[versionsList.length - 1].version_id;
    loadComparison(selA.value, selB.value);
  }
}

async function loadComparison(vA, vB) {
  try {
    const res = await fetch(`/api/versions/compare?a=${vA}&b=${vB}`);
    const data = await res.json();

    const deltasBox = document.getElementById("compareDeltasContainer");
    deltasBox.innerHTML = "";

    // Render Metrics Deltas
    const mc = data.metric_changes || {};
    const mKeys = Object.keys(mc);

    mKeys.forEach((k) => {
      const info = mc[k];
      const card = document.createElement("div");
      const dir = info.direction || "unchanged";
      card.className = `delta-card ${dir}`;
      const changeSign = info.change > 0 ? `+${info.change}` : `${info.change}`;

      card.innerHTML = `
        <div style="font-size: 0.75rem; color: var(--text-muted); text-transform: uppercase;">${k}</div>
        <div style="font-size: 1.3rem; font-weight: 700; margin: 4px 0;">${info.after} <span style="font-size: 0.85rem; font-weight: normal; color: var(--text-muted);">(was ${info.before})</span></div>
        <div style="font-size: 0.8rem; font-weight: 600; color: ${dir === 'improved' ? '#34d399' : dir === 'regressed' ? '#fb7185' : '#94a3b8'};">
          Delta: ${changeSign} [${dir.toUpperCase()}]
        </div>
      `;
      deltasBox.appendChild(card);
    });

    // Tests card
    const tc = data.test_changes || {};
    const testCard = document.createElement("div");
    testCard.className = "delta-card";
    testCard.innerHTML = `
      <div style="font-size: 0.75rem; color: var(--text-muted); text-transform: uppercase;">Test Suite Delta</div>
      <div style="font-size: 1.1rem; font-weight: 600; margin: 4px 0;">
        Passed: <span style="color: #34d399;">${tc.passed >= 0 ? '+' : ''}${tc.passed || 0}</span> ·
        Failed: <span style="color: #fb7185;">${tc.failed >= 0 ? '+' : ''}${tc.failed || 0}</span>
      </div>
      <div style="font-size: 0.8rem; color: var(--text-secondary);">Files touched: ${data.files.length}</div>
    `;
    deltasBox.appendChild(testCard);

    // Render Diff Text
    renderDiffContent("compareDiffBody", data.diff_text || "No code changes found between selected versions.");
  } catch (err) {
    console.error("Failed to compare versions:", err);
  }
}

// Render Diff with syntax line colors
function renderDiffContent(containerId, diffText) {
  const container = document.getElementById(containerId);
  container.innerHTML = "";

  const lines = (diffText || "").split("\n");
  lines.forEach((line) => {
    const div = document.createElement("div");
    div.className = "diff-line";

    if (line.startsWith("+++") || line.startsWith("---")) {
      div.className += " hunk";
    } else if (line.startsWith("+")) {
      div.className += " add";
    } else if (line.startsWith("-")) {
      div.className += " del";
    } else if (line.startsWith("@@")) {
      div.className += " hunk";
    }

    div.textContent = line || " ";
    container.appendChild(div);
  });
}

// Features Tab
function renderFeatures() {
  const container = document.getElementById("featuresList");
  container.innerHTML = "";

  if (!featuresList || featuresList.length === 0) {
    container.innerHTML = `<div style="color: var(--text-muted); padding: 1.5rem;">No features tracked yet.</div>`;
    return;
  }

  featuresList.forEach((f) => {
    const card = document.createElement("div");
    card.className = "feature-card glass";

    const metricsObj = f.latest_metrics || {};
    const metricsStr = Object.keys(metricsObj)
      .map((k) => `${k}: ${metricsObj[k]}`)
      .join(" · ");

    const historyBadges = (f.history || [])
      .map((h) => `<span class="badge-status ${h.status}" style="font-size: 0.68rem; padding: 1px 6px;">v${h.version_id}</span>`)
      .join(" ");

    card.innerHTML = `
      <div>
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.75rem;">
          <h3 style="font-family: 'Outfit', sans-serif; font-size: 1.15rem; color: white;">${escapeHtml(f.name)}</h3>
          <span class="badge-status ${f.status}">${f.status}</span>
        </div>
        <div style="font-size: 0.82rem; color: var(--text-secondary); margin-bottom: 0.75rem;">
          Iterations: <b>${f.version_count || 0}</b> ${metricsStr ? `· Latest: ${metricsStr}` : ""}
        </div>
      </div>
      <div>
        <div style="font-size: 0.75rem; color: var(--text-muted); margin-bottom: 0.35rem; text-transform: uppercase;">Version History:</div>
        <div style="display: flex; gap: 0.35rem; flex-wrap: wrap;">${historyBadges || "None"}</div>
      </div>
    `;

    container.appendChild(card);
  });
}

// AI Memory & Warnings Tab
async function loadMemoryWarnings() {
  try {
    const res = await fetch("/api/warnings");
    const data = await res.json();

    const list = document.getElementById("memoryWarningsList");
    list.innerHTML = "";

    const warnings = data.warnings || [];
    if (warnings.length === 0) {
      list.innerHTML = `<div style="color: #34d399; font-size: 0.9rem; padding: 0.5rem 0;">✅ No regressions or repeated mistakes recorded in project memory.</div>`;
    } else {
      warnings.forEach((w) => {
        const item = document.createElement("div");
        item.className = "alert-box warning";
        item.style.marginBottom = "0.75rem";
        item.innerHTML = `
          <div>
            <div style="font-weight: 700; color: #fb7185; margin-bottom: 0.25rem;">
              v${w.version_id} [${w.status}] - Feature: ${w.feature || 'Global'} (${w.agent || 'AI'})
            </div>
            <div style="font-size: 0.88rem; color: #fecdd3; margin-bottom: 0.25rem;">
              <b>Intent:</b> "${escapeHtml(w.intent || '')}"
            </div>
            <div style="font-size: 0.85rem; color: #cbd5e1;">
              <b>Warning:</b> ${escapeHtml(w.recommendation || w.analysis || '')}
            </div>
          </div>
        `;
        list.appendChild(item);
      });
    }

    // Prompt Snippet
    document.getElementById("memoryPromptSnippet").textContent = data.prompt_snippet || "No snippet available.";
  } catch (err) {
    console.error("Failed to load memory warnings:", err);
  }
}

async function searchMemory(query) {
  try {
    const res = await fetch(`/api/search?q=${encodeURIComponent(query)}`);
    const results = await res.json();

    const list = document.getElementById("memoryWarningsList");
    list.innerHTML = `<div style="color: var(--text-muted); font-size: 0.85rem; margin-bottom: 0.75rem;">Found ${results.length} matches for "${escapeHtml(query)}":</div>`;

    results.forEach((r) => {
      const item = document.createElement("div");
      item.className = "alert-box info";
      item.style.marginBottom = "0.5rem";
      item.innerHTML = `
        <div>
          <span class="badge-status ${r.status}">v${r.version_id} ${r.status}</span>
          <span style="font-weight: 600; color: white; margin-left: 0.5rem;">${escapeHtml(r.intent || '')}</span>
          <div style="font-size: 0.82rem; color: var(--text-secondary); margin-top: 0.25rem;">
            Agent: ${r.agent} · Feature: ${r.feature || 'N/A'} · Commit: ${(r.git_commit || '').substring(0, 7)}
          </div>
        </div>
      `;
      list.appendChild(item);
    });
  } catch (err) {
    console.error("Search failed:", err);
  }
}

// Databricks Analytics Tab
function renderAnalytics(data) {
  if (!data) return;

  const isConn = data.is_databricks_connected;
  const statusEl = document.getElementById("dbStatusBadge");
  statusEl.textContent = isConn ? "Connected (Live SQL)" : "Local Engine (Delta Sync Queue)";
  statusEl.style.color = isConn ? "var(--accent-emerald)" : "var(--accent-cyan)";

  document.getElementById("dbTotalRegressions").textContent = data.total_regressions || 0;

  // Agent Performance Table
  const tableBox = document.getElementById("dbAgentTable");
  const agents = data.agent_performance || [];

  if (agents.length === 0) {
    tableBox.innerHTML = `<div style="color: var(--text-muted);">No agent records available.</div>`;
  } else {
    let html = `
      <table style="width: 100%; border-collapse: collapse; font-size: 0.88rem; text-align: left;">
        <thead>
          <tr style="border-bottom: 1px solid var(--border-subtle); color: var(--text-muted); font-size: 0.75rem; text-transform: uppercase;">
            <th style="padding: 8px 12px;">Agent Name</th>
            <th style="padding: 8px 12px;">Total Versions</th>
            <th style="padding: 8px 12px;">Regressions</th>
            <th style="padding: 8px 12px;">Success Rate</th>
          </tr>
        </thead>
        <tbody>
    `;

    agents.forEach((a) => {
      const succRate = a.success_rate !== undefined ? `${a.success_rate}%` : "-";
      html += `
        <tr style="border-bottom: 1px solid rgba(255,255,255,0.03);">
          <td style="padding: 10px 12px; font-weight: 600; color: white;">${escapeHtml(a.agent)}</td>
          <td style="padding: 10px 12px;">${a.total}</td>
          <td style="padding: 10px 12px; color: ${a.regressions > 0 ? '#fb7185' : 'inherit'};">${a.regressions}</td>
          <td style="padding: 10px 12px; color: #34d399; font-weight: 600;">${succRate}</td>
        </tr>
      `;
    });
    html += `</tbody></table>`;
    tableBox.innerHTML = html;
  }

  // Risky Files
  const riskyBox = document.getElementById("dbRiskyFiles");
  const files = data.risky_files || [];
  if (files.length === 0) {
    riskyBox.innerHTML = `<div style="color: var(--text-muted);">No regression-prone files identified.</div>`;
  } else {
    let fHtml = `<div style="display: flex; flex-direction: column; gap: 0.5rem;">`;
    files.forEach((f) => {
      fHtml += `
        <div style="display: flex; justify-content: space-between; padding: 8px 12px; background: rgba(255,255,255,0.02); border-radius: 6px;">
          <span class="mono" style="color: #cbd5e1; font-size: 0.82rem;">${escapeHtml(f.file)}</span>
          <span style="color: #fb7185; font-weight: 600; font-size: 0.82rem;">${f.fail_count} failures</span>
        </div>
      `;
    });
    fHtml += `</div>`;
    riskyBox.innerHTML = fHtml;
  }
}

// Restore Action
async function triggerRestore(versionId) {
  if (!confirm(`Are you sure you want to safely restore project code to version v${versionId}? A new recovery branch will be checked out.`)) {
    return;
  }
  try {
    const res = await fetch(`/api/versions/${versionId}/restore`, { method: "POST" });
    const data = await res.json();
    if (data.status === "success") {
      alert(`✅ ${data.message}`);
      loadAllData();
    } else {
      alert(`❌ Restore failed: ${data.detail || data.error}`);
    }
  } catch (err) {
    alert(`Error triggering restore: ${err.message}`);
  }
}

// Helpers
function formatDate(isoStr) {
  if (!isoStr) return "";
  try {
    const d = new Date(isoStr);
    return d.toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
  } catch (e) {
    return isoStr;
  }
}

function escapeHtml(str) {
  if (!str) return "";
  return str.replace(/[&<>'"]/g, (tag) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    "'": "&#39;",
    '"': "&quot;",
  }[tag] || tag));
}
