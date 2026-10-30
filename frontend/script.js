"use strict";

// ── API helper ────────────────────────────────────────────────────────────────
async function api(path, method = "GET") {
  const res  = await fetch(path, { method });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || `Request failed (${res.status})`);
  return data;
}

// ── Escape HTML to prevent XSS ────────────────────────────────────────────────
function esc(str) {
  if (!str) return "";
  const d = document.createElement("div");
  d.textContent = str;
  return d.innerHTML;
}

// ── Sidebar navigation ────────────────────────────────────────────────────────
document.querySelectorAll(".nav-item").forEach(link => {
  link.addEventListener("click", e => {
    e.preventDefault();
    const target = link.dataset.section;
    document.querySelectorAll(".nav-item").forEach(l => l.classList.remove("active"));
    document.querySelectorAll(".page").forEach(p => p.classList.remove("active"));
    link.classList.add("active");
    document.getElementById(target).classList.add("active");
  });
});

// ── Platform pill helper ───────────────────────────────────────────────────────
function platformPill(p) {
  return `<span class="pill pill-platform-${p}">${p}</span>`;
}

// ── Status bar helpers ────────────────────────────────────────────────────────
function setStatus(elId, msg, type = "idle") {
  const el = document.getElementById(elId);
  el.style.display = "flex";
  el.className = `status-bar ${type}`;
  el.innerHTML = `<span class="dot"></span> ${esc(msg)}`;
}

// ── Table client-side search ──────────────────────────────────────────────────
function filterTable(tableId, query) {
  const q    = query.toLowerCase();
  const rows = document.querySelectorAll(`#${tableId} tbody tr`);
  rows.forEach(row => {
    row.style.display = row.textContent.toLowerCase().includes(q) ? "" : "none";
  });
}

// ── Stats (sidebar + main dashboard) ─────────────────────────────────────────
async function refreshStats() {
  try {
    const s = await api("/api/stats");
    // main dashboard
    document.getElementById("st-total").textContent   = s.total   ?? "—";
    document.getElementById("st-passed").textContent  = s.passed  ?? "—";
    document.getElementById("st-sent").textContent    = s.sent    ?? "—";
    document.getElementById("st-skipped").textContent = s.skipped ?? "—";
    document.getElementById("st-failed").textContent  = s.failed  ?? "—";
    // sidebar mini-stats
    document.getElementById("s-total").textContent    = s.total   ?? "—";
    document.getElementById("s-passed").textContent   = s.passed  ?? "—";
    document.getElementById("s-sent").textContent     = s.sent    ?? "—";
  } catch (_) { /* silent — stats are non-critical */ }
}

// ── DISCOVER ──────────────────────────────────────────────────────────────────
async function runDiscovery() {
  const niche = document.getElementById("discNiche").value;
  const limit = document.getElementById("discLimit").value;
  const btn   = document.getElementById("btnDiscover");

  btn.disabled = true;
  setStatus("discStatus", `Discovering ${niche} influencers…`, "running");

  try {
    const data = await api(`/api/discover?niche=${niche}&limit=${limit}`, "POST");

    setStatus("discStatus", `✓ Discovered ${data.count} influencers (${data.new} new) in "${niche}"`, "success");

    const tbody = document.querySelector("#tblDisc tbody");
    tbody.innerHTML = data.influencers.map(i => `
      <tr>
        <td><strong>${esc(i.name)}</strong>
            <br><a href="${esc(i.profile_url)}" target="_blank" style="font-size:.75rem;color:var(--accent)">↗ Profile</a>
        </td>
        <td>${platformPill(i.platform)}</td>
        <td>${(i.follower_count || 0).toLocaleString()}</td>
        <td>${i.engagement_rate != null ? i.engagement_rate.toFixed(1) + "%" : "—"}</td>
        <td><span class="pill" style="background:var(--bg3)">${esc(i.niche || "—")}</span></td>
        <td class="truncate" title="${esc(i.contact_email)}">${esc(i.contact_email || "Not Found")}</td>
        <td><span class="truncate" title="${esc(i.bio)}">${esc(i.bio || "—")}</span></td>
      </tr>`).join("");

    document.getElementById("discResults").style.display = "block";
    document.getElementById("discCount").textContent = data.count;
    refreshStats();

  } catch (e) {
    setStatus("discStatus", "✗ " + e.message, "error");
  } finally {
    btn.disabled = false;
  }
}

// ── FILTER ────────────────────────────────────────────────────────────────────
async function runFilter() {
  const niche = document.getElementById("filtNiche").value;
  setStatus("filtStatus", `Filtering & classifying "${niche}" influencers…`, "running");

  try {
    const data = await api(`/api/filter?niche=${niche}`, "POST");
    setStatus("filtStatus", `✓ ${data.passed} passed, ${data.failed} failed out of ${data.total} total`, "success");

    document.getElementById("passedCount").textContent = data.passed;
    document.getElementById("failedCount").textContent = data.failed;

    const makeCards = (list, cls) =>
      list.length
        ? list.map(i => `
          <div class="filter-card ${cls}">
            <div class="filter-card-name">${esc(i.name)}</div>
            <div class="filter-card-meta">
              ${platformPill(i.platform)} &nbsp;
              <strong>${(i.follower_count||0).toLocaleString()}</strong> followers &nbsp;·&nbsp;
              <strong>${i.engagement_rate?.toFixed(1) ?? "—"}%</strong> engagement &nbsp;·&nbsp;
              Category: <strong>${esc(i.category)}</strong>
            </div>
            <div class="filter-card-meta">
              Email: ${esc(i.contact_email || "Not Found")}
            </div>
            <div class="filter-card-reason">${esc(i.filter_reason)}</div>
          </div>`).join("")
        : `<p style="color:var(--text-sub);padding:10px">None</p>`;

    document.getElementById("tabPassed").innerHTML = makeCards(data.passed_list, "passed");
    document.getElementById("tabFailed").innerHTML  = makeCards(data.failed_list, "failed");
    document.getElementById("filtResults").style.display = "block";
    refreshStats();

  } catch (e) {
    setStatus("filtStatus", "✗ " + e.message, "error");
  }
}

function switchTab(which, btn) {
  document.querySelectorAll(".tab-btn").forEach(b => b.classList.remove("active"));
  btn.classList.add("active");
  document.getElementById("tabPassed").style.display = which === "passed" ? "grid" : "none";
  document.getElementById("tabFailed").style.display  = which === "failed"  ? "grid" : "none";
}

// ── PERSONALIZE ───────────────────────────────────────────────────────────────
async function runPersonalize() {
  setStatus("persStatus", "Generating AI-personalized messages via Groq…", "running");
  document.getElementById("persStatus").style.display = "flex";

  try {
    const data = await api("/api/personalize", "POST");
    setStatus("persStatus", `✓ Generated ${data.count} message sets`, "success");

    const wc = t => (t || "").trim().split(/\s+/).filter(Boolean).length;

    document.getElementById("persResults").style.display = "grid";
    document.getElementById("persResults").innerHTML = data.messages.map(m => `
      <div class="msg-card">
        <div class="msg-card-name">${esc(m.influencer.name)}</div>
        <div class="msg-card-meta">
          ${platformPill(m.influencer.platform)} &nbsp;
          ${esc(m.influencer.niche)} &nbsp;·&nbsp;
          ${(m.influencer.follower_count||0).toLocaleString()} followers
        </div>

        <div class="msg-label">📧 Email Subject</div>
        <div class="msg-subject">${esc(m.email_subject)}</div>

        <div class="msg-label">📧 Email Body</div>
        <div class="msg-body">${esc(m.email_body)}</div>
        <div class="word-count">${wc(m.email_body)} words</div>

        <div class="msg-label">💬 Instagram / TikTok DM</div>
        <div class="msg-dm">${esc(m.dm_text)}</div>
        <div class="word-count">${wc(m.dm_text)} words</div>
      </div>`).join("");

  } catch (e) {
    setStatus("persStatus", "✗ " + e.message, "error");
  }
}

// ── SEND ──────────────────────────────────────────────────────────────────────
async function runSend() {
  setStatus("sendStatus", "Sending outreach…", "running");
  document.getElementById("sendStatus").style.display = "flex";
  document.getElementById("sendResults").innerHTML = "";

  try {
    const data = await api("/api/send", "POST");
    const sentList = data.sent || [];
    const sent    = sentList.filter(s => s.status.startsWith("sent")).length;
    const skipped = sentList.filter(s => s.status.startsWith("skipped")).length;
    const failed  = sentList.filter(s => s.status === "failed").length;

    setStatus("sendStatus", `✓ Sent: ${sent} · Skipped: ${skipped} · Failed: ${failed}`, "success");

    document.getElementById("sendResults").innerHTML = sentList.map(r => {
      let pillCls = "pill-skipped";
      if (r.status.startsWith("sent"))    pillCls = r.status.includes("simulated") ? "pill-simulated" : "pill-sent";
      if (r.status === "failed")          pillCls = "pill-failed";
      return `
        <div class="send-row">
          <div>
            <div class="send-name">${esc(r.influencer)}</div>
            <div class="send-email">${esc(r.email || "No email")}</div>
          </div>
          <span class="pill ${pillCls}">${esc(r.status)}</span>
        </div>`;
    }).join("");

    refreshStats();
    refreshLog();

  } catch (e) {
    setStatus("sendStatus", "✗ " + e.message, "error");
  }
}

// ── TRACKER ───────────────────────────────────────────────────────────────────
async function refreshLog() {
  try {
    const data = await api("/api/log");
    const tbody = document.querySelector("#tblLog tbody");

    if (!data.log || data.log.length === 0) {
      tbody.innerHTML = `<tr><td colspan="7" class="empty-row">No outreach records yet.</td></tr>`;
      return;
    }

    tbody.innerHTML = data.log.map(l => {
      let pillCls = "pill-skipped";
      if (l.status?.startsWith("sent") && l.status.includes("simulated")) pillCls = "pill-simulated";
      else if (l.status?.startsWith("sent"))  pillCls = "pill-sent";
      else if (l.status === "failed")          pillCls = "pill-failed";

      const sentAt = l.sent_at
        ? new Date(l.sent_at).toLocaleString(undefined, { dateStyle:"short", timeStyle:"short" })
        : "—";

      return `<tr>
        <td><strong>${esc(l.name)}</strong>
            <br><a href="${esc(l.profile_url)}" target="_blank" style="font-size:.75rem;color:var(--accent)">↗</a>
        </td>
        <td>${platformPill(l.platform)}</td>
        <td><span class="truncate" title="${esc(l.email)}">${esc(l.email || "Not Found")}</span></td>
        <td><span class="truncate" title="${esc(l.email_subject)}">${esc(l.email_subject || "—")}</span></td>
        <td><span class="truncate" title="${esc(l.dm_text)}">${esc((l.dm_text || "").slice(0, 50))}…</span></td>
        <td style="white-space:nowrap">${sentAt}</td>
        <td><span class="pill ${pillCls}">${esc(l.status)}</span></td>
      </tr>`;
    }).join("");

  } catch (e) {
    console.error("Log refresh failed:", e);
  }
}

// ── AUTOMATION ────────────────────────────────────────────────────────────────
let _autoPoller = null;

async function startAuto() {
  const niche    = document.getElementById("autoNiche").value;
  const interval = document.getElementById("autoInterval").value;
  try {
    await api(`/api/automation/start?niche=${niche}&interval_minutes=${interval}`, "POST");
    setStatus("autoStatus", `Running every ${interval} min for "${niche}"`, "running");
    if (!_autoPoller) _autoPoller = setInterval(pollAutoStatus, 5_000);
    pollAutoStatus();
  } catch (e) {
    setStatus("autoStatus", "✗ " + e.message, "error");
  }
}

async function stopAuto() {
  try {
    await api("/api/automation/stop", "POST");
    setStatus("autoStatus", "⏹ Automation stopped", "idle");
    document.getElementById("autoJobs").textContent = "";
    if (_autoPoller) { clearInterval(_autoPoller); _autoPoller = null; }
  } catch (e) {
    setStatus("autoStatus", "✗ " + e.message, "error");
  }
}

async function runOnce() {
  const niche = document.getElementById("autoNiche").value;
  setStatus("autoStatus", `Running full pipeline once for "${niche}"…`, "running");
  try {
    const data = await api(`/api/automation/run-once?niche=${niche}`, "POST");
    const ok   = Object.values(data.results || {}).filter(v => v.startsWith("ok")).length;
    const total = Object.keys(data.results || {}).length;
    setStatus("autoStatus", `✓ Pipeline complete — ${ok}/${total} stages succeeded`, "success");
    refreshStats();
    refreshLog();
  } catch (e) {
    setStatus("autoStatus", "✗ " + e.message, "error");
  }
}

async function pollAutoStatus() {
  try {
    const s = await api("/api/automation/status");
    const jobs = document.getElementById("autoJobs");
    if (s.running) {
      const next = (s.jobs || []).map(j => `next run: ${j.next_run}`).join(" | ");
      jobs.innerHTML = `🟢 Scheduler active — niche: <strong>${s.config?.niche}</strong>, interval: <strong>${s.config?.interval_minutes}m</strong>${next ? ` &nbsp;|&nbsp; ${next}` : ""}`;
    } else {
      jobs.textContent = "";
    }
  } catch (_) { /* ignore */ }
}

// ── Init ──────────────────────────────────────────────────────────────────────
(function init() {
  refreshStats();
  pollAutoStatus();
  refreshLog();
  // Auto-refresh stats every 15s while the page is open
  setInterval(refreshStats, 15_000);
})();
