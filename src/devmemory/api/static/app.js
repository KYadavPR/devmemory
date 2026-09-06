// DevMemory dashboard — dependency-free SPA, hash-routed.

const API = "/api";
const $ = (sel, root = document) => root.querySelector(sel);
const view = $("#view");

// --- helpers ---------------------------------------------------------------

const esc = (s) =>
  String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

const short = (sha) => (sha ? String(sha).slice(0, 12) : "—");

async function api(path) {
  const r = await fetch(API + path);
  if (!r.ok) throw new Error((await r.text()) || r.statusText);
  const ct = r.headers.get("content-type") || "";
  return ct.includes("application/json") ? r.json() : r.text();
}

function toast(msg) {
  const t = document.createElement("div");
  t.className = "toast";
  t.textContent = msg;
  document.body.appendChild(t);
  setTimeout(() => t.remove(), 4000);
}

const badge = (label, cls) => `<span class="badge ${esc(cls ?? label)}"><span class="dot"></span>${esc(label)}</span>`;

const loading = () => `<div class="empty"><span class="spin"></span></div>`;
const empty = (big, sub) => `<div class="empty"><div class="big">${esc(big)}</div>${sub ? esc(sub) : ""}</div>`;

function metricChip(name, value) {
  return `<span class="pill">${esc(name)} <b>${esc(value)}</b></span>`;
}

function pageHead(title, sub) {
  return `<div class="page-head"><h1>${esc(title)}</h1>${sub ? `<p>${esc(sub)}</p>` : ""}</div>`;
}

// --- theme ---------------------------------------------------------------

function initTheme() {
  const saved = (() => {
    try { return localStorage.getItem("devmemory-theme"); } catch { return null; }
  })();
  if (saved) document.documentElement.setAttribute("data-theme", saved);
  updateThemeLabel();
  $("#themeToggle").addEventListener("click", () => {
    const cur = document.documentElement.getAttribute("data-theme");
    const next = cur === "dark" ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", next);
    try { localStorage.setItem("devmemory-theme", next); } catch {}
    updateThemeLabel();
  });
}
function updateThemeLabel() {
  const t = document.documentElement.getAttribute("data-theme");
  $("#themeLabel").textContent = t === "dark" ? "Dark" : t === "light" ? "Light" : "Theme";
}

// --- router ------------------------------------------------------------

const routes = {
  overview: renderOverview,
  timeline: renderTimeline,
  features: renderFeatures,
  feature: renderFeature,
  compare: renderCompare,
  memory: renderMemory,
  intelligence: renderIntelligence,
  search: renderSearch,
  version: renderVersion,
};

async function router() {
  const hash = location.hash.slice(2) || "overview";
  const [name, ...rest] = hash.split("/");
  const fn = routes[name] || renderOverview;
  document.querySelectorAll(".nav-link").forEach((a) => a.classList.toggle("active", a.dataset.route === name));
  view.innerHTML = loading();
  try {
    await fn(rest.join("/"));
  } catch (e) {
    view.innerHTML = pageHead("Something went wrong") + empty(String(e.message || e));
    toast(String(e.message || e));
  }
  view.scrollTo?.(0, 0);
}

// --- views -----------------------------------------------------------

async function renderOverview() {
  const [p, versions, features] = await Promise.all([
    api("/project"),
    api("/versions?limit=8"),
    api("/features"),
  ]);
  $("#brandRepo").textContent = p.name;
  $("#foot").innerHTML = `${esc(p.repo_path)}`;

  const recent = versions.slice().reverse();
  const done = features.filter((f) => f.status === "COMPLETE").length;

  view.innerHTML =
    pageHead(p.name, `${p.branch ? "on " + p.branch + " · " : ""}${short(p.head_sha)}${p.head_subject ? " · " + p.head_subject : ""}`) +
    `<div class="grid cols-4" style="margin-bottom:16px">
      ${stat("Versions", p.version_count, p.latest_version_id ? "latest " + p.latest_version_id.toUpperCase() : "none yet")}
      ${stat("Latest result", p.latest_status ? "" : "—", "", p.latest_status ? badge(p.latest_status) : "")}
      ${stat("Features", `${done}/${features.length}`, "complete")}
      ${stat("Entire", p.entire_enabled ? "enabled" : p.entire_installed ? "off" : "absent", p.entire_version || "", "", p.entire_enabled ? "SUCCESS" : "NEEDS_REVIEW")}
    </div>` +
    (Object.keys(p.latest_metrics || {}).length
      ? `<div class="card card-pad" style="margin-bottom:16px"><div style="display:flex;gap:8px;flex-wrap:wrap">${Object.entries(p.latest_metrics).map(([k, v]) => metricChip(k, v)).join("")}</div></div>`
      : "") +
    (p.head_sha && !p.head_has_version
      ? `<div class="card card-pad" style="margin-bottom:16px;border-color:var(--warn)">HEAD (${short(p.head_sha)}) is not recorded yet — run <code>devmemory checkpoint</code>.</div>`
      : "") +
    `<div class="grid cols-2">
      <div class="card">
        <div class="card-head">Recent versions</div>
        ${recent.length ? recent.map(vrow).join("") : `<div class="card-pad muted">No versions yet.</div>`}
      </div>
      <div class="card">
        <div class="card-head">Feature health</div>
        ${features.length ? features.map(featRow).join("") : `<div class="card-pad muted">No features tracked.</div>`}
      </div>
    </div>`;
}

function stat(label, value, foot, extra, valueClass) {
  return `<div class="card stat">
    <div class="label">${esc(label)}</div>
    <div class="value ${valueClass ? "" : ""}">${extra || esc(value)}</div>
    ${foot ? `<div class="foot">${esc(foot)}</div>` : ""}
  </div>`;
}

function vrow(v) {
  const metrics = Object.entries(v.metrics || {}).slice(0, 2).map(([k, x]) => `${k} ${x}`).join(" · ");
  return `<a class="vrow" href="#/version/${esc(v.version_id)}">
    <div class="vid">${esc(v.version_id.toUpperCase())}</div>
    <div>${badge(v.status)}</div>
    <div>
      <div class="vintent">${esc(v.intent || "—")}</div>
      <div class="vmeta">
        <span>${esc(v.agent || "—")}</span>
        ${v.feature ? `<span>${esc(v.feature)}</span>` : ""}
        <span class="plus">+${v.lines_added}</span><span class="minus">-${v.lines_removed}</span>
        ${metrics ? `<span>${esc(metrics)}</span>` : ""}
      </div>
    </div>
    <div class="pill">${esc(short(v.git_commit))}</div>
  </a>`;
}

function featRow(f) {
  const last = f.history[f.history.length - 1];
  return `<a class="vrow" style="grid-template-columns:1fr auto auto" href="#/feature/${encodeURIComponent(f.name)}">
    <div><div class="vintent">${esc(f.name)}</div><div class="vmeta"><span>${f.version_count} version${f.version_count === 1 ? "" : "s"}</span>${last ? `<span>${esc(last.version_id.toUpperCase())}</span>` : ""}</div></div>
    <div>${badge(f.status)}</div>
  </a>`;
}

async function renderTimeline() {
  const versions = await api("/versions?limit=500");
  const ordered = versions.slice().reverse();
  view.innerHTML =
    pageHead("Version timeline", `${versions.length} development version${versions.length === 1 ? "" : "s"}`) +
    (ordered.length
      ? `<div class="card card-pad"><div class="timeline">${ordered.map(tlItem).join("")}</div></div>`
      : empty("No versions yet", "Make a commit, then run devmemory checkpoint."));
}

function tlItem(v) {
  const metrics = Object.entries(v.metrics || {}).map(([k, x]) => metricChip(k, x)).join("");
  const conf = v.association_method === "trailer" || v.association_method === "none" ? "" :
    `<span class="badge uncertain"><span class="dot"></span>${esc(v.association_method)} ${v.association_confidence.toFixed(2)}</span>`;
  return `<div class="tl-item ${esc(v.status)}">
    <div class="tl-head">
      <a class="vid link" href="#/version/${esc(v.version_id)}">${esc(v.version_id.toUpperCase())}</a>
      ${badge(v.status)}
      ${v.checkpoint_id ? `<span class="pill">◈ ${esc(v.checkpoint_id.slice(0, 12))}</span>` : `<span class="badge missing"><span class="dot"></span>no checkpoint</span>`}
      ${conf}
      <span class="pill">${esc(short(v.git_commit))}</span>
    </div>
    <div class="tl-body">${esc(v.intent || "—")}</div>
    <div class="vmeta secondary" style="font-size:12.5px;margin-top:3px">
      ${esc(v.agent || "—")}${v.model ? " · " + esc(v.model) : ""}
      ${v.feature ? " · " + esc(v.feature) : ""}
      · <span class="plus">+${v.lines_added}</span> <span class="minus">-${v.lines_removed}</span> in ${v.files_changed} file${v.files_changed === 1 ? "" : "s"}
      ${v.tests_passed != null ? ` · ${v.tests_passed} passed / ${v.tests_failed} failed` : ""}
    </div>
    ${metrics ? `<div class="tl-metrics">${metrics}</div>` : ""}
  </div>`;
}

async function renderVersion(id) {
  const [v, trace, attempts, impact] = await Promise.all([
    api("/versions/" + id),
    api(`/versions/${id}/trace`),
    api(`/versions/${id}/attempts`).catch(() => []),
    api(`/versions/${id}/impact`).catch(() => null),
  ]);
  let diff = "";
  try { diff = await api(`/versions/${id}/diff`); } catch {}

  const cp = v.primary_checkpoint;
  view.innerHTML =
    pageHead(v.version_id.toUpperCase() + "  ·  " + v.status, v.intent || "") +
    `<div class="grid cols-2">
      <div class="card">
        <div class="card-head">Development trace</div>
        <div class="card-pad"><div class="trace">${trace.nodes.map(traceNode).join("")}</div></div>
      </div>
      <div>
        <div class="card" style="margin-bottom:16px">
          <div class="card-head">Record</div>
          <div class="card-pad">
            <dl class="kv">
              <dt>status</dt><dd>${badge(v.status)}</dd>
              <dt>agent</dt><dd>${esc(v.agent || "—")}${v.model ? ` <span class="muted">(${esc(v.model)})</span>` : ""}</dd>
              <dt>commit</dt><dd><span class="pill">${esc(short(v.git_commit))}</span> <span class="muted">parent ${esc(short(v.parent_commit))}</span></dd>
              <dt>branch</dt><dd>${esc(v.branch || "—")}</dd>
              <dt>feature</dt><dd>${v.feature_id ? esc(v.feature_id.split(":").pop()) : "—"}</dd>
              <dt>changes</dt><dd>${v.files_changed} files · <span class="plus">+${v.lines_added}</span> <span class="minus">-${v.lines_removed}</span></dd>
              ${v.tests && v.tests.command ? `<dt>tests</dt><dd>${v.tests.passed} passed / ${v.tests.failed} failed / ${v.tests.skipped} skipped</dd>` : ""}
              ${v.committed_at ? `<dt>committed</dt><dd class="muted">${esc(v.committed_at.slice(0, 16).replace("T", " "))}</dd>` : ""}
            </dl>
          </div>
        </div>
        ${cp ? `<div class="card" style="margin-bottom:16px">
          <div class="card-head">Entire checkpoint</div>
          <div class="card-pad">
            <dl class="kv">
              <dt>checkpoint</dt><dd><span class="pill">${esc(cp.checkpoint_id)}</span></dd>
              <dt>association</dt><dd>${badge(cp.association_method, cp.is_uncertain ? "uncertain" : "linked")} ${cp.association_confidence != null ? `<span class="muted">${cp.association_confidence.toFixed(2)}</span>` : ""}</dd>
              ${cp.agent ? `<dt>agent</dt><dd>${esc(cp.agent)}${cp.model ? " · " + esc(cp.model) : ""}</dd>` : ""}
              ${cp.tokens && cp.tokens.total ? `<dt>tokens</dt><dd>${(cp.tokens.total / 1000).toFixed(1)}k</dd>` : ""}
              ${cp.ref ? `<dt>ref</dt><dd class="muted mono" style="font-size:11px">${esc(cp.ref)}</dd>` : ""}
            </dl>
          </div>
        </div>` : ""}
        ${v.metrics && v.metrics.length ? `<div class="card">
          <div class="card-head">Metrics</div>
          <div class="card-pad">${v.metrics.map(metricRow).join("")}</div>
        </div>` : ""}
      </div>
    </div>` +
    (v.changed_files && v.changed_files.length ? `<div class="card" style="margin-top:16px">
      <div class="card-head">Files changed</div>
      <div class="card-pad files-list">${v.changed_files.map(fileRow).join("")}</div>
    </div>` : "") +
    (attempts.length ? `<div class="card" style="margin-top:16px;border-color:var(--warn)">
      <div class="card-head">⚠ Previous attempts touching this area</div>
      <div class="card-pad grid" style="gap:10px">${attempts.map(attemptCard).join("")}</div>
    </div>` : "") +
    (impact && impact.entities && impact.entities.length ? `<div class="card" style="margin-top:16px">
      <div class="card-head">Change impact <span class="muted" style="text-transform:none">· entire graph · ${impact.entities.length} entities</span></div>
      <div class="card-pad">${impactTable(impact)}</div>
    </div>` : "") +
    (v.analysis && v.analysis.summary ? `<div class="card" style="margin-top:16px">
      <div class="card-head">Analysis <span class="muted" style="text-transform:none">· ${esc(v.analysis.provider)}</span></div>
      <div class="card-pad"><p>${esc(v.analysis.summary)}</p>${v.analysis.recommendation ? `<p style="margin-top:8px"><b>Recommendation:</b> ${esc(v.analysis.recommendation)}</p>` : ""}</div>
    </div>` : "") +
    (diff ? `<div class="card" style="margin-top:16px">
      <div class="card-head">Diff · ${esc(short(v.parent_commit))} → ${esc(short(v.git_commit))}</div>
      ${renderDiff(diff)}
    </div>` : "");
}

function impactTable(impact) {
  const rows = impact.entities.slice().sort((a, b) => (b.dependents_count - a.dependents_count));
  const cls = { removed: "down", signature_changed: "down", renamed: "", added: "up", body_changed: "" };
  return `<table class="mini"><thead><tr><th>change</th><th>entity</th><th>file</th><th style="text-align:right">deps</th></tr></thead><tbody>${
    rows.slice(0, 40).map((e) => `<tr>
      <td>${badge(e.change_type, cls[e.change_type] || "")}</td>
      <td>${esc(e.kind)} <b>${esc(e.name)}</b></td>
      <td class="muted mono" style="font-size:11px">${esc(e.path)}</td>
      <td style="text-align:right">${e.dependents_count || ""}</td>
    </tr>`).join("")
  }</tbody></table>${rows.length > 40 ? `<div class="muted" style="margin-top:6px">+${rows.length - 40} more</div>` : ""}`;
}

function traceNode(n) {
  return `<div class="trace-node" data-source="${esc(n.source)}">
    <div class="t-label">${esc(n.label)}</div>
    <div>
      <div class="t-value">${esc(n.value)}${n.status ? " " + badge(n.status, n.status) : ""}</div>
      ${n.detail ? `<div class="t-detail">${esc(n.detail)}</div>` : ""}
    </div>
  </div>`;
}

function metricRow(m) {
  const cls = m.is_improvement ? "up" : m.is_worse ? "down" : "";
  const arrow = m.before != null ? `${m.before} <span class="arrow">→</span> ${m.after}` : `${m.after}`;
  return `<div style="display:flex;justify-content:space-between;padding:5px 0;border-bottom:1px solid var(--border)">
    <span>${esc(m.name)}</span>
    <span class="metric-delta">${arrow}${m.unit ? " " + esc(m.unit) : ""} ${cls ? badge(cls, cls) : ""}</span>
  </div>`;
}

function fileRow(f) {
  const mk = { added: "A", modified: "M", deleted: "D", renamed: "R", copied: "C", type_changed: "T" }[f.change_type] || "?";
  return `<div class="f"><span class="mark ${mk}">${mk}</span><span>${esc(f.path)}</span>${
    f.binary ? `<span class="muted">binary</span>` : `<span><span class="plus">+${f.additions}</span> <span class="minus">-${f.deletions}</span></span>`
  }</div>`;
}

function renderDiff(text) {
  const lines = text.split("\n").slice(0, 4000).map((l) => {
    let cls = "";
    if (l.startsWith("+++") || l.startsWith("---") || l.startsWith("diff ") || l.startsWith("index ")) cls = "meta";
    else if (l.startsWith("@@")) cls = "hunk";
    else if (l.startsWith("+")) cls = "add";
    else if (l.startsWith("-")) cls = "del";
    return `<span class="l ${cls}">${esc(l) || " "}</span>`;
  });
  return `<div class="diff">${lines.join("")}</div>`;
}

async function renderFeatures() {
  const features = await api("/features");
  view.innerHTML =
    pageHead("Features", "How each feature area evolved across versions") +
    (features.length
      ? `<div class="grid cols-2">${features.map(featCard).join("")}</div>`
      : empty("No features tracked yet", "Run devmemory checkpoint --feature <name>."));
}

function featCard(f) {
  const spark = f.history.map((h) => `<a href="#/version/${esc(h.version_id)}" title="${esc(h.version_id.toUpperCase())} · ${esc(h.status)}">${badge(h.version_id.toUpperCase(), h.status)}</a>`).join(" ");
  return `<a class="card card-pad" href="#/feature/${encodeURIComponent(f.name)}" style="display:block">
    <div style="display:flex;justify-content:space-between;align-items:center">
      <b>${esc(f.name)}</b>${badge(f.status)}
    </div>
    <div class="muted" style="font-size:13px;margin:6px 0">${f.version_count} version${f.version_count === 1 ? "" : "s"}${
      Object.keys(f.latest_metrics).length ? " · " + Object.entries(f.latest_metrics).map(([k, v]) => `${k} ${v}`).join(", ") : ""
    }</div>
    <div style="display:flex;gap:5px;flex-wrap:wrap">${spark}</div>
  </a>`;
}

async function renderFeature(name) {
  const f = await api("/features/" + encodeURIComponent(name));
  view.innerHTML =
    pageHead(f.name, `${badge(f.status)}`.replace(/<[^>]+>/g, "") + ` · ${f.version_count} versions`) +
    `<div class="card card-pad"><div class="timeline">${f.history
      .slice()
      .reverse()
      .map(
        (h) => `<div class="tl-item ${esc(h.status)}">
          <div class="tl-head"><a class="vid link" href="#/version/${esc(h.version_id)}">${esc(h.version_id.toUpperCase())}</a> ${badge(h.status)}</div>
          ${Object.keys(h.metrics).length ? `<div class="tl-metrics">${Object.entries(h.metrics).map(([k, v]) => metricChip(k, v)).join("")}</div>` : ""}
        </div>`
      )
      .join("")}</div></div>`;
}

async function renderCompare(arg) {
  const versions = await api("/versions?limit=500");
  const [a, b] = (arg || "").split("...");
  const opts = (sel) => versions.map((v) => `<option value="${esc(v.version_id)}" ${v.version_id === sel ? "selected" : ""}>${esc(v.version_id.toUpperCase())} — ${esc((v.intent || "").slice(0, 50))}</option>`).join("");

  view.innerHTML =
    pageHead("Compare versions", "What actually changed between two development states") +
    `<div class="card card-pad" style="margin-bottom:16px;display:flex;gap:12px;align-items:center">
      <select class="search-box" id="cmpA" style="flex:1">${opts(a)}</select>
      <span class="muted">→</span>
      <select class="search-box" id="cmpB" style="flex:1">${opts(b || (versions[versions.length - 1] || {}).version_id)}</select>
    </div>
    <div id="cmpResult">${empty("Pick two versions")}</div>`;

  const run = async () => {
    const av = $("#cmpA").value, bv = $("#cmpB").value;
    location.hash = `#/compare/${av}...${bv}`;
    if (!av || !bv || av === bv) { $("#cmpResult").innerHTML = empty("Pick two different versions"); return; }
    $("#cmpResult").innerHTML = loading();
    try {
      const c = await api(`/compare?from=${encodeURIComponent(av)}&to=${encodeURIComponent(bv)}`);
      $("#cmpResult").innerHTML = compareResult(c);
    } catch (e) {
      $("#cmpResult").innerHTML = empty(String(e.message || e));
    }
  };
  $("#cmpA").addEventListener("change", run);
  $("#cmpB").addEventListener("change", run);
  if (a && b) run();
}

function compareResult(c) {
  const mrows = c.metric_changes.map((m) => `<div style="display:flex;justify-content:space-between;padding:5px 0;border-bottom:1px solid var(--border)">
    <span>${esc(m.name)}</span>
    <span class="metric-delta">${m.before ?? "—"} <span class="arrow">→</span> ${m.after ?? "—"} ${m.delta != null ? `<span class="${m.delta >= 0 ? "plus" : "minus"}">(${m.delta >= 0 ? "+" : ""}${m.delta})</span>` : ""}</span>
  </div>`).join("");
  return `<div class="grid cols-2" style="margin-bottom:16px">
      <div class="card stat"><div class="label">Lines</div><div class="value"><span class="plus">+${c.stat.additions}</span> <span class="minus">-${c.stat.deletions}</span></div><div class="foot">${c.stat.files_changed} files</div></div>
      <div class="card stat"><div class="label">Status</div><div class="value">${badge(c.status_from)} → ${badge(c.status_to)}</div></div>
    </div>
    ${mrows ? `<div class="card" style="margin-bottom:16px"><div class="card-head">Metric changes</div><div class="card-pad">${mrows}</div></div>` : ""}
    ${c.test_changes && (c.test_changes.passed != null) ? `<div class="card card-pad" style="margin-bottom:16px">Tests: passed ${c.test_changes.passed >= 0 ? "+" : ""}${c.test_changes.passed}, failed ${c.test_changes.failed >= 0 ? "+" : ""}${c.test_changes.failed}</div>` : ""}
    <div class="card" style="margin-bottom:16px"><div class="card-head">Files</div><div class="card-pad files-list">${c.files.map(fileRow).join("") || `<span class="muted">no file changes</span>`}</div></div>
    ${c.diff_text ? `<div class="card"><div class="card-head">Diff</div>${renderDiff(c.diff_text)}</div>` : ""}`;
}

async function renderMemory(arg) {
  const q = decodeURIComponent(arg || "");
  const attempts = await api("/attempts?limit=50" + (q ? "&q=" + encodeURIComponent(q) : ""));
  view.innerHTML =
    pageHead("Development memory", "Approaches that failed or regressed — so the next agent doesn't repeat them") +
    `<input class="search-box" id="mq" placeholder="scope by intent: token expiry, learning rate, auth …" value="${esc(q)}" style="margin-bottom:16px" />
     <div id="mres">${attemptList(attempts)}</div>`;
  const input = $("#mq");
  let t;
  input.addEventListener("input", () => {
    clearTimeout(t);
    t = setTimeout(async () => {
      const v = input.value.trim();
      location.hash = "#/memory/" + encodeURIComponent(v);
      $("#mres").innerHTML = loading();
      $("#mres").innerHTML = attemptList(await api("/attempts?limit=50" + (v ? "&q=" + encodeURIComponent(v) : "")));
    }, 250);
  });
}

function attemptList(attempts) {
  if (!attempts.length) return empty("No relevant previous attempts", "Nothing to avoid — yet.");
  return `<div class="grid" style="gap:12px">${attempts.map(attemptCard).join("")}</div>`;
}

function attemptCard(a) {
  return `<div class="card card-pad" style="border-left:3px solid ${a.is_adverse ? "var(--bad)" : "var(--border-strong)"}">
    <div style="display:flex;align-items:center;gap:10px;margin-bottom:6px">
      <a class="vid link" href="#/version/${esc(a.version_id)}">${esc(a.version_id.toUpperCase())}</a>
      ${badge(a.status)}
      ${a.feature ? `<span class="pill">${esc(a.feature)}</span>` : ""}
      <span class="muted" style="margin-left:auto;font-size:12px">${esc(a.matched_on.join(" · "))}</span>
    </div>
    <div style="font-size:14px">${esc(a.intent || a.change_summary)}</div>
    <div class="secondary" style="font-size:13px;margin-top:4px">result: ${esc(a.result)}</div>
    ${a.recommendation ? `<div style="font-size:13px;margin-top:6px;color:var(--accent)">→ ${esc(a.recommendation)}</div>` : ""}
  </div>`;
}

async function renderIntelligence() {
  const a = await api("/analytics");
  const t = (rows, cols) => `<table style="width:100%;border-collapse:collapse;font-size:13px">
    <thead><tr>${cols.map((c) => `<th style="text-align:${c.r ? "right" : "left"};padding:6px 8px;color:var(--text-muted);font-weight:500;border-bottom:1px solid var(--border)">${esc(c.h)}</th>`).join("")}</tr></thead>
    <tbody>${rows.map((row) => `<tr>${cols.map((c) => `<td style="text-align:${c.r ? "right" : "left"};padding:6px 8px;border-bottom:1px solid var(--border)">${row[c.k]}</td>`).join("")}</tr>`).join("")}</tbody></table>`;

  view.innerHTML =
    pageHead("Development intelligence", `source: ${a.source} · ${a.version_count} versions · ${a.regression_count} regressions · ${a.success_rate}% success`) +
    `<div class="grid cols-3" style="margin-bottom:16px">
      ${stat("Success rate", a.success_rate + "%", `${a.version_count} versions`)}
      ${stat("Regressions", a.regression_count, "flagged")}
      ${stat("Features", a.features.length, "tracked")}
    </div>
    <div class="grid cols-2">
      <div class="card"><div class="card-head">Regression leaderboard</div><div class="card-pad">${
        a.regressions.length ? t(a.regressions.map((r) => ({ v: `<a class="link" href="#/version/${r.version_id}">${r.version_id.toUpperCase()}</a>`, s: badge(r.severity, r.severity === "HIGH" ? "REGRESSION" : "PARTIAL_SUCCESS"), f: esc(r.feature || "-"), d: esc(r.detail) })), [{ h: "", k: "v" }, { h: "sev", k: "s" }, { h: "feature", k: "f" }, { h: "detail", k: "d" }]) : `<span class="muted">none</span>`
      }</div></div>
      <div class="card"><div class="card-head">Feature attempts</div><div class="card-pad">${
        t(a.features.map((f) => ({ n: esc(f.feature), a: f.attempts, s: f.success_rate + "%", r: f.regressions })), [{ h: "feature", k: "n" }, { h: "attempts", k: "a", r: 1 }, { h: "success", k: "s", r: 1 }, { h: "regr", k: "r", r: 1 }])
      }</div></div>
      <div class="card"><div class="card-head">File churn</div><div class="card-pad">${
        t(a.file_churn.map((f) => ({ p: `<span class="mono">${esc(f.path)}</span>`, c: f.changes, x: f.adverse_changes })), [{ h: "file", k: "p" }, { h: "changes", k: "c", r: 1 }, { h: "adverse", k: "x", r: 1 }])
      }</div></div>
      <div class="card"><div class="card-head">Agent effectiveness</div><div class="card-pad">${
        t(a.agents.map((g) => ({ a: esc(g.agent), v: g.versions, s: g.success_rate + "%", tk: g.tokens_per_success ? (g.tokens_per_success / 1000).toFixed(0) + "k" : "-" })), [{ h: "agent", k: "a" }, { h: "versions", k: "v", r: 1 }, { h: "success", k: "s", r: 1 }, { h: "tok/success", k: "tk", r: 1 }])
      }</div></div>
    </div>` +
    (a.trend.length > 1 ? `<div class="card" style="margin-top:16px"><div class="card-head">Trend</div><div class="card-pad">${sparkRow(a.trend)}</div></div>` : "") +
    (a.failed_approaches.length ? `<div class="card" style="margin-top:16px;border-color:var(--bad)">
      <div class="card-head">Repeatedly-failed approaches</div>
      <div class="card-pad">${a.failed_approaches.map((f) => `<div style="padding:6px 0;border-bottom:1px solid var(--border)"><b>${f.occurrences}×</b> <span class="mono">${esc(f.signature.join(", "))}</span> <span class="muted">${esc(f.example_intent || "")}</span> — ${f.version_ids.map((v) => `<a class="link" href="#/version/${v}">${v.toUpperCase()}</a>`).join(" ")}</div>`).join("")}</div>
    </div>` : "") +
    `<p class="muted" style="margin-top:16px;font-size:12px">${a.source === "databricks" ? "Live from Databricks Delta tables." : "Computed locally. Configure DATABRICKS_* to publish and query in Databricks."}</p>`;
}

function sparkRow(trend) {
  const w = 620, h = 60, n = trend.length;
  const vals = trend.map((p) => (p.key_metric != null ? p.key_metric : p.test_pass_rate)).filter((x) => x != null);
  if (!vals.length) return `<span class="muted">no metric to trend</span>`;
  const mn = Math.min(...vals), mx = Math.max(...vals), rng = mx - mn || 1;
  const pts = trend.map((p, i) => {
    const v = p.key_metric != null ? p.key_metric : p.test_pass_rate;
    const x = (i / Math.max(1, n - 1)) * w;
    const y = v == null ? null : h - ((v - mn) / rng) * (h - 8) - 4;
    return { x, y, p };
  });
  const path = pts.filter((q) => q.y != null).map((q, i) => `${i ? "L" : "M"}${q.x.toFixed(1)},${q.y.toFixed(1)}`).join(" ");
  return `<svg viewBox="0 0 ${w} ${h}" style="width:100%;height:${h}px">
    <path d="${path}" fill="none" stroke="var(--accent)" stroke-width="2"/>
    ${pts.filter((q) => q.y != null).map((q) => `<circle cx="${q.x.toFixed(1)}" cy="${q.y.toFixed(1)}" r="3" fill="${q.p.status === "REGRESSION" || q.p.status === "ERROR" ? "var(--bad)" : "var(--accent)"}"><title>${esc(q.p.version_id.toUpperCase())}: ${q.p.key_metric ?? q.p.test_pass_rate}</title></circle>`).join("")}
  </svg>`;
}

async function renderSearch(q) {
  q = decodeURIComponent(q || "");
  view.innerHTML =
    pageHead("Search", "Across intent, agent, feature, files, commits, checkpoints, analysis") +
    `<input class="search-box" id="q" placeholder="authentication · learning rate · model.py · Codex …" value="${esc(q)}" style="margin-bottom:16px" />
     <div id="results">${q ? loading() : empty("Type to search")}</div>`;
  const input = $("#q");
  input.focus();
  let timer;
  const run = async () => {
    const val = input.value.trim();
    location.hash = "#/search/" + encodeURIComponent(val);
    if (!val) { $("#results").innerHTML = empty("Type to search"); return; }
    $("#results").innerHTML = loading();
    try {
      const r = await api("/search?q=" + encodeURIComponent(val));
      $("#results").innerHTML = r.count
        ? `<div class="card">${r.results.map((h) => `<a class="vrow" href="#/version/${esc(h.version_id)}">
            <div class="vid">${esc(h.version_id.toUpperCase())}</div>
            <div>${badge(h.status)}</div>
            <div><div class="vintent">${esc(h.snippet || h.intent || "—")}</div><div class="vmeta">${esc(h.agent || "—")}${h.feature ? " · " + esc(h.feature) : ""}</div></div>
            <div class="pill">${esc(short(h.git_commit))}</div>
          </a>`).join("")}</div>`
        : empty(`No matches for “${val}”`);
    } catch (e) {
      $("#results").innerHTML = empty(String(e.message || e));
    }
  };
  input.addEventListener("input", () => { clearTimeout(timer); timer = setTimeout(run, 250); });
  if (q) run();
}

// --- boot ------------------------------------------------------------

initTheme();
window.addEventListener("hashchange", router);
api("/project")
  .then((p) => { $("#brandRepo").textContent = p.name; })
  .catch(() => {});
router();
