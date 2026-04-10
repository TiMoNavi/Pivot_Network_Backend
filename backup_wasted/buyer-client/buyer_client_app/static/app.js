const tabs = document.querySelectorAll(".tab");
const panels = document.querySelectorAll(".panel");

tabs.forEach((button) => {
  button.addEventListener("click", () => {
    tabs.forEach((tab) => tab.classList.remove("is-active"));
    panels.forEach((panel) => panel.classList.remove("is-active"));
    button.classList.add("is-active");
    document.querySelector(`[data-panel="${button.dataset.tab}"]`).classList.add("is-active");
  });
});

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
    ...options,
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = new Error(payload?.error?.message || payload?.detail || "Request failed");
    error.payload = payload;
    throw error;
  }
  return payload;
}

function writeOutput(id, payload) {
  document.getElementById(id).textContent = JSON.stringify(payload, null, 2);
}

function clearFeedback(id) {
  const box = document.getElementById(id);
  if (!box) return;
  box.className = "feedback hidden";
  box.innerHTML = "";
}

function renderFeedback(id, payload) {
  const box = document.getElementById(id);
  if (!box) return;
  const error = payload?.error || payload;
  box.className = "feedback error";
  box.innerHTML = `
    <h3>${error.message || "操作失败"}</h3>
    ${error.step ? `<p><strong>步骤:</strong> ${error.step}</p>` : ""}
    ${error.code ? `<p><strong>代码:</strong> ${error.code}</p>` : ""}
    ${error.hint ? `<p><strong>建议:</strong> ${error.hint}</p>` : ""}
  `;
}

function renderScanReport(report) {
  const summary = document.getElementById("scan-summary");
  const checks = document.getElementById("scan-checks");
  summary.innerHTML = "";
  checks.innerHTML = "";
  if (!report?.summary) return;
  const items = [
    ["通过", report.summary.passed],
    ["警告", report.summary.warned],
    ["失败", report.summary.failed],
    ["总体", report.summary.overall_status || "unknown"],
  ];
  items.forEach(([label, value]) => {
    const card = document.createElement("article");
    card.className = "summary-card";
    card.innerHTML = `<span class="summary-label">${label}</span><strong class="summary-value">${value}</strong>`;
    summary.appendChild(card);
  });
  (report.checks || []).forEach((check) => {
    const card = document.createElement("article");
    card.className = `check-card status-${check.status}`;
    card.innerHTML = `
      <div class="check-head">
        <div>
          <h3>${check.title || check.name}</h3>
          <p class="check-meta">${check.category || "general"} / ${check.name}</p>
        </div>
        <div class="check-tags">
          <span class="badge badge-${check.status}">${check.status}</span>
          ${check.blocking ? '<span class="badge badge-blocking">阻塞项</span>' : '<span class="badge">非阻塞</span>'}
        </div>
      </div>
      <p class="check-detail">${check.detail || ""}</p>
      ${check.hint ? `<p class="check-hint">${check.hint}</p>` : ""}
    `;
    checks.appendChild(card);
  });
}

async function pollJob(jobId, outputId, feedbackId) {
  writeOutput(outputId, { job_id: jobId, status: "queued" });
  while (true) {
    const payload = await api(`/local-api/jobs/${jobId}`, { method: "GET" });
    writeOutput(outputId, payload);
    if (payload.status === "failed" && payload.error) {
      renderFeedback(feedbackId, { error: payload.error });
      return payload;
    }
    if (payload.status === "succeeded") {
      clearFeedback(feedbackId);
      return payload;
    }
    await new Promise((resolve) => setTimeout(resolve, 1500));
  }
}

document.getElementById("login-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = new FormData(event.target);
  try {
    const result = await api("/local-api/auth/login", {
      method: "POST",
      body: JSON.stringify({ email: form.get("email"), password: form.get("password") }),
    });
    clearFeedback("login-feedback");
    writeOutput("login-output", result);
  } catch (error) {
    renderFeedback("login-feedback", error.payload || { error: { message: String(error) } });
    writeOutput("login-output", error.payload || { error: String(error) });
  }
});

document.getElementById("fetch-catalog").addEventListener("click", async () => {
  try {
    const result = await api("/local-api/catalog/offers", { method: "GET" });
    clearFeedback("catalog-feedback");
    writeOutput("catalog-output", result);
  } catch (error) {
    renderFeedback("catalog-feedback", error.payload || { error: { message: String(error) } });
    writeOutput("catalog-output", error.payload || { error: String(error) });
  }
});

document.getElementById("order-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = new FormData(event.target);
  try {
    const result = await api("/local-api/orders", {
      method: "POST",
      body: JSON.stringify({
        offer_id: form.get("offer_id"),
        requested_duration_minutes: Number(form.get("requested_duration_minutes") || 60),
      }),
    });
    clearFeedback("catalog-feedback");
    writeOutput("catalog-output", result);
  } catch (error) {
    renderFeedback("catalog-feedback", error.payload || { error: { message: String(error) } });
    writeOutput("catalog-output", error.payload || { error: String(error) });
  }
});

document.getElementById("redeem-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = new FormData(event.target);
  try {
    const result = await api("/local-api/access-codes/redeem", {
      method: "POST",
      body: JSON.stringify({ access_code: form.get("access_code") }),
    });
    clearFeedback("catalog-feedback");
    writeOutput("catalog-output", result);
  } catch (error) {
    renderFeedback("catalog-feedback", error.payload || { error: { message: String(error) } });
    writeOutput("catalog-output", error.payload || { error: String(error) });
  }
});

document.getElementById("runtime-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = new FormData(event.target);
  try {
    const result = await api("/local-api/runtime-sessions", {
      method: "POST",
      body: JSON.stringify({ access_code: form.get("access_code"), network_mode: "wireguard" }),
    });
    clearFeedback("runtime-feedback");
    writeOutput("runtime-output", result);
  } catch (error) {
    renderFeedback("runtime-feedback", error.payload || { error: { message: String(error) } });
    writeOutput("runtime-output", error.payload || { error: String(error) });
  }
});

document.getElementById("refresh-runtime").addEventListener("click", async () => {
  try {
    const result = await api("/local-api/runtime-sessions/current", { method: "GET" });
    clearFeedback("runtime-feedback");
    writeOutput("runtime-output", result);
  } catch (error) {
    renderFeedback("runtime-feedback", error.payload || { error: { message: String(error) } });
    writeOutput("runtime-output", error.payload || { error: String(error) });
  }
});

document.getElementById("stop-runtime").addEventListener("click", async () => {
  try {
    const result = await api("/local-api/runtime-sessions/stop", { method: "POST", body: JSON.stringify({}) });
    clearFeedback("runtime-feedback");
    writeOutput("runtime-output", result);
  } catch (error) {
    renderFeedback("runtime-feedback", error.payload || { error: { message: String(error) } });
    writeOutput("runtime-output", error.payload || { error: String(error) });
  }
});

document.getElementById("close-runtime").addEventListener("click", async () => {
  try {
    const result = await api("/local-api/runtime-sessions/close", { method: "POST", body: JSON.stringify({}) });
    clearFeedback("runtime-feedback");
    writeOutput("runtime-output", result);
  } catch (error) {
    renderFeedback("runtime-feedback", error.payload || { error: { message: String(error) } });
    writeOutput("runtime-output", error.payload || { error: String(error) });
  }
});

document.getElementById("run-scan").addEventListener("click", async () => {
  try {
    const result = await api("/local-api/env/scan", { method: "POST", body: JSON.stringify({}) });
    clearFeedback("scan-feedback");
    renderScanReport(result.report || result);
    writeOutput("scan-output", result);
  } catch (error) {
    renderFeedback("scan-feedback", error.payload || { error: { message: String(error) } });
    writeOutput("scan-output", error.payload || { error: String(error) });
  }
});

document.getElementById("wireguard-up").addEventListener("click", async () => {
  try {
    const result = await api("/local-api/wireguard/up", { method: "POST", body: JSON.stringify({}) });
    clearFeedback("shell-feedback");
    writeOutput("shell-output", result);
  } catch (error) {
    renderFeedback("shell-feedback", error.payload || { error: { message: String(error) } });
    writeOutput("shell-output", error.payload || { error: String(error) });
  }
});

document.getElementById("wireguard-down").addEventListener("click", async () => {
  try {
    const result = await api("/local-api/wireguard/down", { method: "POST", body: JSON.stringify({}) });
    clearFeedback("shell-feedback");
    writeOutput("shell-output", result);
  } catch (error) {
    renderFeedback("shell-feedback", error.payload || { error: { message: String(error) } });
    writeOutput("shell-output", error.payload || { error: String(error) });
  }
});

document.getElementById("refresh-shell").addEventListener("click", async () => {
  try {
    const result = await api("/local-api/shell/session", { method: "GET" });
    clearFeedback("shell-feedback");
    document.getElementById("shell-frame").src = result.shell_embed_url || "";
    writeOutput("shell-output", result);
  } catch (error) {
    renderFeedback("shell-feedback", error.payload || { error: { message: String(error) } });
    writeOutput("shell-output", error.payload || { error: String(error) });
  }
});

document.getElementById("workspace-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = new FormData(event.target);
  try {
    const result = await api("/local-api/workspace/select", {
      method: "POST",
      body: JSON.stringify({ path: form.get("path") }),
    });
    clearFeedback("workspace-feedback");
    writeOutput("workspace-output", result);
  } catch (error) {
    renderFeedback("workspace-feedback", error.payload || { error: { message: String(error) } });
    writeOutput("workspace-output", error.payload || { error: String(error) });
  }
});

document.getElementById("workspace-sync").addEventListener("click", async () => {
  try {
    const result = await api("/local-api/workspace/sync", { method: "POST", body: JSON.stringify({}) });
    clearFeedback("workspace-feedback");
    writeOutput("workspace-output", result);
  } catch (error) {
    renderFeedback("workspace-feedback", error.payload || { error: { message: String(error) } });
    writeOutput("workspace-output", error.payload || { error: String(error) });
  }
});

document.getElementById("assistant-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = new FormData(event.target);
  try {
    const job = await api("/local-api/assistant/message", {
      method: "POST",
      body: JSON.stringify({ message: form.get("message") }),
    });
    clearFeedback("workspace-feedback");
    await pollJob(job.job_id, "workspace-output", "workspace-feedback");
  } catch (error) {
    renderFeedback("workspace-feedback", error.payload || { error: { message: String(error) } });
    writeOutput("workspace-output", error.payload || { error: String(error) });
  }
});
