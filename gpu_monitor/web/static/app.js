const app = document.getElementById("app");
const body = document.body;
const mode = body.dataset.mode;
const value = body.dataset.value;
const refreshSeconds = Number(body.dataset.refresh || "30");

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

async function getJson(url) {
  const response = await fetch(url, { cache: "no-store" });
  if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
  return response.json();
}

function metric(label, value, extra = "") {
  return `<div class="panel"><div class="metric-label">${escapeHtml(label)}</div><div class="metric-value">${escapeHtml(value)}</div>${extra}</div>`;
}

function table(headers, rows) {
  if (!rows.length) return '<div class="status-line">No records</div>';
  return `<table><thead><tr>${headers.map((h) => `<th>${escapeHtml(h)}</th>`).join("")}</tr></thead><tbody>${rows.join("")}</tbody></table>`;
}

function emptyState(message) {
  return `<div class="status-line">${escapeHtml(message)}</div>`;
}

function gpuRows(gpus) {
  return gpus.map((gpu) => {
    const total = Number(gpu.total_memory_mb || 0);
    const used = Number(gpu.used_memory_mb || 0);
    const pct = total ? Math.min(100, Math.round((used / total) * 100)) : 0;
    const users = [...new Set((gpu.processes || []).map((p) => p.display_name || p.username))].join(", ") || "-";
    return `<tr>
      <td>GPU ${escapeHtml(gpu.gpu_index)}</td>
      <td>${escapeHtml(gpu.gpu_name || "-")}</td>
      <td>${escapeHtml(gpu.used_memory_gb)} / ${escapeHtml(gpu.total_memory_gb)} GB<div class="bar"><span style="width:${pct}%"></span></div></td>
      <td>${escapeHtml(gpu.gpu_util_percent ?? "-")}%</td>
      <td>${escapeHtml(users)}</td>
      <td>${escapeHtml((gpu.processes || []).length)}</td>
    </tr>`;
  });
}

function userRows(users) {
  return users.map((user) => `<tr>
    <td>${escapeHtml(user.display_name || user.username)}</td>
    <td>${escapeHtml((user.gpu_indexes || []).join(", "))}</td>
    <td>${escapeHtml(user.process_count ?? "-")}</td>
    <td>${escapeHtml(user.used_memory_gb ?? user.avg_memory_gb ?? "-")} GB</td>
    <td>${escapeHtml(user.duration_human ?? "-")}</td>
  </tr>`);
}

function userGpuRows(entries) {
  return entries.map((entry) => {
    const sessions = (entry.sessions || []).map((s) => `${s.start_time.slice(11, 19)} - ${s.end_time.slice(11, 19)}`).join("<br>");
    return `<tr>
      <td>${escapeHtml(entry.display_name || entry.username)}</td>
      <td>GPU ${escapeHtml(entry.gpu_index)}</td>
      <td>${sessions || "-"}</td>
      <td>${escapeHtml(entry.duration_human)}</td>
      <td>${escapeHtml(entry.avg_memory_gb)} GB</td>
      <td>${escapeHtml(entry.peak_memory_gb)} GB</td>
    </tr>`;
  });
}

function renderToday(current, today) {
  document.getElementById("subtitle").textContent = `Latest sample: ${current.sample_time || "none"}`;
  app.innerHTML = `
    <div class="toolbar">
      <h2>Today</h2>
      <div>
        <input id="dayInput" type="date" value="${today.report_date}">
        <button class="button" id="openDay">Open Day</button>
        <button class="button" id="openWeek">Open Week</button>
      </div>
    </div>
    <div class="grid">
      ${metric("Collector", current.collector_status, `<p class="${current.collector_status === "ok" ? "ok" : "warn"}">${escapeHtml(current.sample_time || "No samples yet")}</p>`)}
      ${metric("Active Users", today.overview.active_user_count)}
      ${metric("Used GPUs", today.overview.used_gpu_count)}
      ${metric("Total Usage", today.overview.total_usage_human)}
      ${metric("Unknown Processes", today.overview.unknown_process_count)}
      ${metric("Errors", today.overview.error_count)}
    </div>
    <section class="section">
      <h3>Current GPUs</h3>
      ${table(["GPU", "Model", "Memory", "Util", "Users", "Processes"], gpuRows(current.gpus || []))}
    </section>
    <section class="section">
      <h3>Current Users</h3>
      ${(current.users || []).length ? table(["User", "GPUs", "Processes", "Memory", "Duration"], userRows(current.users || [])) : emptyState("当前无 GPU 使用")}
    </section>
    <section class="section">
      <h3>Today Detail</h3>
      ${table(["User", "GPU", "Sessions", "Duration", "Avg Memory", "Peak Memory"], userGpuRows(today.user_gpu || []))}
    </section>
    ${renderIssues(today)}
  `;
  document.getElementById("openDay").onclick = () => {
    const v = document.getElementById("dayInput").value;
    if (v) window.location.href = `/day/${v}`;
  };
  document.getElementById("openWeek").onclick = () => {
    const v = document.getElementById("dayInput").value;
    if (v) window.location.href = `/week/${v}`;
  };
}

function renderDay(summary) {
  document.getElementById("subtitle").textContent = `Day ${summary.report_date}`;
  app.innerHTML = `
    <div class="toolbar">
      <h2>Day ${escapeHtml(summary.report_date)}</h2>
      <div>
        <input id="dayInput" type="date" value="${summary.report_date}">
        <button class="button" id="openDay">Open</button>
      </div>
    </div>
    <div class="grid">
      ${metric("Active Users", summary.overview.active_user_count)}
      ${metric("Used GPUs", summary.overview.used_gpu_count)}
      ${metric("Total Usage", summary.overview.total_usage_human)}
      ${metric("Heartbeat Gaps", summary.overview.heartbeat_gap_count)}
      ${metric("Unknown Processes", summary.overview.unknown_process_count)}
      ${metric("Errors", summary.overview.error_count)}
    </div>
    <section class="section">
      <h3>User Detail</h3>
      ${table(["User", "GPU", "Sessions", "Duration", "Avg Memory", "Peak Memory"], userGpuRows(summary.user_gpu || []))}
    </section>
    ${renderIssues(summary)}
  `;
  document.getElementById("openDay").onclick = () => {
    const v = document.getElementById("dayInput").value;
    if (v) window.location.href = `/day/${v}`;
  };
}

function renderWeek(summary) {
  document.getElementById("subtitle").textContent = `Week ${summary.week_start} - ${summary.week_end}`;
  app.innerHTML = `
    <div class="toolbar">
      <h2>Week ${escapeHtml(summary.week_start)} - ${escapeHtml(summary.week_end)}</h2>
      <div>
        <input id="weekInput" type="date" value="${summary.week_start}">
        <button class="button" id="openWeek">Open</button>
      </div>
    </div>
    <div class="grid">
      ${metric("Active Users", summary.overview.active_user_count)}
      ${metric("Used GPUs", summary.overview.used_gpu_count)}
      ${metric("Total Usage", summary.overview.total_usage_human)}
      ${metric("Heartbeat Gaps", summary.overview.heartbeat_gap_count)}
      ${metric("Errors", summary.overview.error_count)}
      ${metric("Empty Days", (summary.overview.missing_or_empty_dates || []).length)}
    </div>
    <section class="section">
      <h3>Users</h3>
      ${table(["User", "GPUs", "Active Days", "Avg Memory", "Duration"], (summary.users || []).map((u) => `<tr><td>${escapeHtml(u.display_name || u.username)}</td><td>${escapeHtml(u.gpu_indexes.join(", "))}</td><td>${escapeHtml(u.active_days)}</td><td>${escapeHtml(u.avg_memory_gb)} GB</td><td>${escapeHtml(u.duration_human)}</td></tr>`))}
    </section>
    <section class="section">
      <h3>Daily</h3>
      ${table(["Date", "Users", "GPUs", "Usage", "Errors"], (summary.daily || []).map((d) => `<tr><td>${escapeHtml(d.date)}</td><td>${escapeHtml(d.active_user_count)}</td><td>${escapeHtml(d.used_gpu_count)}</td><td>${escapeHtml(d.total_usage_human)}</td><td>${escapeHtml(d.error_count)}</td></tr>`))}
    </section>
  `;
  document.getElementById("openWeek").onclick = () => {
    const v = document.getElementById("weekInput").value;
    if (v) window.location.href = `/week/${v}`;
  };
}

function renderHealth(health) {
  document.getElementById("subtitle").textContent = `Health ${health.status}`;
  const rows = Object.entries(health.counts || {}).map(([name, count]) => `<tr><td>${escapeHtml(name)}</td><td>${escapeHtml(count)}</td></tr>`);
  app.innerHTML = `
    <div class="toolbar"><h2>Health</h2></div>
    <div class="grid">
      ${metric("Status", health.status)}
      ${metric("Latest Sample", health.latest_sample_time || "none")}
      ${metric("Latest Heartbeat", health.latest_heartbeat_time || "none")}
      ${metric("Database", health.database_path)}
    </div>
    <section class="section">
      <h3>Rows</h3>
      ${table(["Table", "Count"], rows)}
    </section>
    ${health.latest_error ? `<section class="section"><h3>Latest Error</h3><div class="status-line bad">${escapeHtml(health.latest_error.event_time)} ${escapeHtml(health.latest_error.message)}</div></section>` : ""}
  `;
}

function renderIssues(summary) {
  const gaps = summary.heartbeat_gaps || [];
  const errors = summary.errors || [];
  if (!gaps.length && !errors.length) return "";
  return `<section class="section">
    <h3>Issues</h3>
    ${gaps.length ? table(["Start", "End", "Gap"], gaps.map((g) => `<tr><td>${escapeHtml(g.start_time)}</td><td>${escapeHtml(g.end_time)}</td><td>${escapeHtml(g.gap_human)}</td></tr>`)) : ""}
    ${errors.length ? table(["Time", "Type", "Severity", "Message"], errors.map((e) => `<tr><td>${escapeHtml(e.event_time)}</td><td>${escapeHtml(e.event_type)}</td><td>${escapeHtml(e.severity)}</td><td>${escapeHtml(e.message)}</td></tr>`)) : ""}
  </section>`;
}

async function load() {
  try {
    if (mode === "today") {
      const [current, today] = await Promise.all([getJson("/api/current"), getJson("/api/today")]);
      renderToday(current, today);
      return;
    }
    if (mode === "day") {
      renderDay(await getJson(`/api/day?date=${encodeURIComponent(value)}`));
      return;
    }
    if (mode === "week") {
      renderWeek(await getJson(`/api/week?date=${encodeURIComponent(value)}`));
      return;
    }
    if (mode === "health") {
      renderHealth(await getJson("/api/health"));
      return;
    }
  } catch (error) {
    app.innerHTML = `<div class="status-line bad">${escapeHtml(error.message)}</div>`;
  }
}

load();
if (mode === "today") {
  window.setInterval(load, refreshSeconds * 1000);
}
