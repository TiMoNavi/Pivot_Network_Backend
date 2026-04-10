let windowSessionId = null;
let windowHeartbeatTimer = null;

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
  const headers = {
    "Content-Type": "application/json",
    ...(options.headers || {}),
  };
  if (windowSessionId) {
    headers["X-Window-Session-Id"] = windowSessionId;
  }

  const response = await fetch(path, {
    headers,
    ...options,
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = new Error(payload?.error?.message || payload?.detail?.message || payload?.detail || "Request failed");
    error.payload = payload;
    error.status = response.status;
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

function renderFeedback(id, payload, kind = "error") {
  const box = document.getElementById(id);
  if (!box) return;
  const error = payload?.error || payload;
  const title = error.message || "操作失败";
  const step = error.step ? `<p><strong>步骤:</strong> ${error.step}</p>` : "";
  const code = error.code ? `<p><strong>代码:</strong> ${error.code}</p>` : "";
  const hint = error.hint ? `<p><strong>建议:</strong> ${error.hint}</p>` : "";
  box.className = `feedback ${kind}`;
  box.innerHTML = `<h3>${title}</h3>${step}${code}${hint}`;
}

function renderScanReport(report) {
  const summary = document.getElementById("scan-summary");
  const checks = document.getElementById("scan-checks");
  summary.innerHTML = "";
  checks.innerHTML = "";
  if (!report || !report.summary) {
    return;
  }

  const statItems = [
    ["通过", report.summary.passed],
    ["警告", report.summary.warned],
    ["失败", report.summary.failed],
    ["总体", report.summary.overall_status || "unknown"],
  ];
  statItems.forEach(([label, value]) => {
    const card = document.createElement("article");
    card.className = "summary-card";
    card.innerHTML = `<span class="summary-label">${label}</span><strong class="summary-value">${value}</strong>`;
    summary.appendChild(card);
  });

  (report.checks || []).forEach((check) => {
    const card = document.createElement("article");
    card.className = `check-card status-${check.status}`;
    const blocking = check.blocking ? `<span class="badge badge-blocking">阻塞项</span>` : `<span class="badge">非阻塞</span>`;
    const hint = check.hint ? `<p class="check-hint">${check.hint}</p>` : "";
    card.innerHTML = `
      <div class="check-head">
        <div>
          <h3>${check.title || check.name}</h3>
          <p class="check-meta">${check.category || "general"} / ${check.name}</p>
        </div>
        <div class="check-tags">
          <span class="badge badge-${check.status}">${check.status}</span>
          ${blocking}
        </div>
      </div>
      <p class="check-detail">${check.detail || ""}</p>
      ${hint}
    `;
    checks.appendChild(card);
  });
}

function handleError(outputId, feedbackId, error) {
  const payload = error.payload || { error: { message: String(error) } };
  renderFeedback(feedbackId, payload.error || payload);
  writeOutput(outputId, payload);
  const scanReport = payload?.error?.details?.scan_report || payload?.error?.details?.report;
  if (scanReport) {
    renderScanReport(scanReport);
  }
}

async function pollJob(jobId, outputId) {
  writeOutput(outputId, { job_id: jobId, status: "queued" });
  while (true) {
    const payload = await api(`/local-api/jobs/${jobId}`, { method: "GET" });
    writeOutput(outputId, payload);
    if (payload.status === "succeeded" || payload.status === "failed") {
      return payload;
    }
    await new Promise((resolve) => setTimeout(resolve, 1500));
  }
}

function updateWindowSessionStatus(payload) {
  const el = document.getElementById("window-session-status");
  if (!el) return;
  if (!payload || !payload.session_id) {
    el.textContent = "浏览器窗口会话未初始化。";
    return;
  }
  el.textContent = `当前浏览器窗口会话: ${payload.session_id} / TTL ${payload.ttl_seconds}s`;
}

async function ensureWindowSession() {
  if (windowSessionId) {
    return;
  }
  const payload = await api("/local-api/window-session/open", {
    method: "POST",
    body: JSON.stringify({}),
    headers: {},
  });
  windowSessionId = payload.session_id;
  updateWindowSessionStatus(payload);
  if (windowHeartbeatTimer) {
    clearInterval(windowHeartbeatTimer);
  }
  windowHeartbeatTimer = window.setInterval(async () => {
    if (!windowSessionId) return;
    try {
      const heartbeat = await api("/local-api/window-session/heartbeat", {
        method: "POST",
        body: JSON.stringify({}),
      });
      updateWindowSessionStatus(heartbeat);
    } catch (error) {
      console.warn("window session heartbeat failed", error);
    }
  }, 15000);
}

function closeWindowSessionBeacon() {
  if (!windowSessionId) return;
  navigator.sendBeacon(`/local-api/window-session/close?session_id=${encodeURIComponent(windowSessionId)}`, new Blob(["{}"], { type: "application/json" }));
}

window.addEventListener("beforeunload", () => {
  closeWindowSessionBeacon();
});

window.addEventListener("load", async () => {
  try {
    await ensureWindowSession();
  } catch (error) {
    handleError("login-output", "login-feedback", error);
  }
});

document.getElementById("login-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  await ensureWindowSession();
  const form = new FormData(event.target);
  const payload = {
    email: form.get("email"),
    password: form.get("password"),
  };
  try {
    const result = await api("/local-api/auth/login", { method: "POST", body: JSON.stringify(payload) });
    clearFeedback("login-feedback");
    writeOutput("login-output", result);
  } catch (error) {
    handleError("login-output", "login-feedback", error);
  }
});

document.getElementById("start-onboarding").addEventListener("click", async () => {
  await ensureWindowSession();
  try {
    const result = await api("/local-api/onboarding/start", {
      method: "POST",
      body: JSON.stringify({ requested_accelerator: "gpu" }),
    });
    clearFeedback("scan-feedback");
    writeOutput("scan-output", result);
  } catch (error) {
    handleError("scan-output", "scan-feedback", error);
  }
});

document.getElementById("run-first-install").addEventListener("click", async () => {
  await ensureWindowSession();
  if (!window.confirm("这会以第一次运行流程执行 Windows Host 安装与检查脚本，继续吗？")) {
    return;
  }
  try {
    const job = await api("/local-api/windows-host/install-and-check", {
      method: "POST",
      body: JSON.stringify({ mode: "all" }),
    });
    clearFeedback("scan-feedback");
    const result = await pollJob(job.job_id, "scan-output");
    if (result.result) {
      renderScanReport(result.result);
    }
  } catch (error) {
    handleError("scan-output", "scan-feedback", error);
  }
});

document.getElementById("run-scan").addEventListener("click", async () => {
  await ensureWindowSession();
  try {
    const result = await api("/local-api/env/scan", { method: "POST", body: JSON.stringify({}) });
    clearFeedback("scan-feedback");
    renderScanReport(result);
    writeOutput("scan-output", result);
  } catch (error) {
    handleError("scan-output", "scan-feedback", error);
  }
});

document.getElementById("run-ubuntu-scan").addEventListener("click", async () => {
  await ensureWindowSession();
  try {
    const result = await api("/local-api/ubuntu/env/scan", { method: "POST", body: JSON.stringify({}) });
    clearFeedback("scan-feedback");
    renderScanReport(result);
    writeOutput("scan-output", result);
  } catch (error) {
    handleError("scan-output", "scan-feedback", error);
  }
});

document.getElementById("assistant-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  await ensureWindowSession();
  const form = new FormData(event.target);
  try {
    const job = await api("/local-api/assistant/message", {
      method: "POST",
      body: JSON.stringify({ message: form.get("message") }),
    });
    clearFeedback("assistant-feedback");
    await pollJob(job.job_id, "assistant-output");
  } catch (error) {
    handleError("assistant-output", "assistant-feedback", error);
  }
});

document.getElementById("run-ubuntu-bootstrap").addEventListener("click", async () => {
  await ensureWindowSession();
  if (!window.confirm("这会在 WSL Ubuntu 中执行 bootstrap，继续吗？")) {
    return;
  }
  try {
    const result = await api("/local-api/ubuntu/bootstrap-run", {
      method: "POST",
      body: JSON.stringify({}),
    });
    clearFeedback("join-feedback");
    writeOutput("join-output", result);
  } catch (error) {
    handleError("join-output", "join-feedback", error);
  }
});

document.getElementById("pull-standard-image").addEventListener("click", async () => {
  await ensureWindowSession();
  if (!window.confirm("这会在 Ubuntu Docker 中拉取平台标准 seller swarm 容器，继续吗？")) {
    return;
  }
  try {
    const job = await api("/local-api/ubuntu/standard-image/pull", {
      method: "POST",
      body: JSON.stringify({}),
    });
    clearFeedback("join-feedback");
    await pollJob(job.job_id, "join-output");
  } catch (error) {
    handleError("join-output", "join-feedback", error);
  }
});

document.getElementById("verify-standard-image").addEventListener("click", async () => {
  await ensureWindowSession();
  if (!window.confirm("这会验证标准 seller swarm 容器的 CUDA、GPU、Python、WireGuard、Docker、Swarm helper 和网络能力，继续吗？")) {
    return;
  }
  try {
    const job = await api("/local-api/ubuntu/standard-image/verify", {
      method: "POST",
      body: JSON.stringify({}),
    });
    clearFeedback("join-feedback");
    await pollJob(job.job_id, "join-output");
  } catch (error) {
    handleError("join-output", "join-feedback", error);
  }
});

document.getElementById("context-sync-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  await ensureWindowSession();
  const form = new FormData(event.target);
  const payload = {
    local_path: form.get("local_path"),
    ubuntu_target_path: form.get("ubuntu_target_path") || null,
  };
  try {
    const result = await api("/local-api/ubuntu/context-sync", { method: "POST", body: JSON.stringify(payload) });
    clearFeedback("join-feedback");
    writeOutput("join-output", result);
  } catch (error) {
    handleError("join-output", "join-feedback", error);
  }
});

document.getElementById("run-join").addEventListener("click", async () => {
  await ensureWindowSession();
  if (!window.confirm("这会让 Ubuntu 宿主 Docker 执行 swarm join，并使用后端下发的 WireGuard advertise/data-path 地址，继续吗？")) {
    return;
  }
  try {
    const result = await api("/local-api/ubuntu/swarm-join", {
      method: "POST",
      body: JSON.stringify({}),
    });
    clearFeedback("join-feedback");
    writeOutput("join-output", result);
  } catch (error) {
    handleError("join-output", "join-feedback", error);
  }
});

document.getElementById("check-wireguard-status").addEventListener("click", async () => {
  await ensureWindowSession();
  try {
    const result = await api("/local-api/node/wireguard-status", {
      method: "GET",
    });
    clearFeedback("join-feedback");
    writeOutput("join-output", result);
  } catch (error) {
    handleError("join-output", "join-feedback", error);
  }
});

document.getElementById("mark-compute-ready").addEventListener("click", async () => {
  await ensureWindowSession();
  if (!window.confirm("只有当本机和平台都显示为 WireGuard 地址时才会成功回写 compute-ready，继续吗？")) {
    return;
  }
  try {
    const result = await api("/local-api/ubuntu/compute-ready", {
      method: "POST",
      body: JSON.stringify({}),
    });
    clearFeedback("join-feedback");
    writeOutput("join-output", result);
  } catch (error) {
    handleError("join-output", "join-feedback", error);
  }
});

document.getElementById("claim-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  await ensureWindowSession();
  if (!window.confirm("这会把 Ubuntu compute 的 Swarm 节点提交给平台 claim，继续吗？")) {
    return;
  }
  const form = new FormData(event.target);
  const payload = {
    node_ref: form.get("node_ref") || null,
    compute_node_id: form.get("compute_node_id") || null,
    requested_accelerator: form.get("requested_accelerator") || null,
  };
  try {
    const result = await api("/local-api/node/claim", { method: "POST", body: JSON.stringify(payload) });
    clearFeedback("join-feedback");
    writeOutput("join-output", result);
  } catch (error) {
    handleError("join-output", "join-feedback", error);
  }
});

document.getElementById("image-build-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  await ensureWindowSession();
  if (!window.confirm("这会在 WSL Ubuntu 的 Docker Engine 中执行 docker build，继续吗？")) {
    return;
  }
  const form = new FormData(event.target);
  const extraLines = String(form.get("extra_dockerfile_lines") || "")
    .split("\n")
    .map((line) => line.trimEnd())
    .filter((line) => line.trim());
  try {
    const job = await api("/local-api/ubuntu/image/build", {
      method: "POST",
      body: JSON.stringify({
        repository: form.get("repository"),
        tag: form.get("tag"),
        registry: form.get("registry"),
        extra_dockerfile_lines: extraLines,
        resource_profile: { gpu_enabled: true },
      }),
    });
    clearFeedback("image-feedback");
    await pollJob(job.job_id, "image-output");
  } catch (error) {
    handleError("image-output", "image-feedback", error);
  }
});

document.getElementById("image-push-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  await ensureWindowSession();
  if (!window.confirm("这会在 WSL Ubuntu 的 Docker Engine 中执行 docker push，继续吗？")) {
    return;
  }
  const form = new FormData(event.target);
  try {
    const job = await api("/local-api/ubuntu/image/push", {
      method: "POST",
      body: JSON.stringify({ image_ref: form.get("image_ref") || null }),
    });
    clearFeedback("image-feedback");
    await pollJob(job.job_id, "image-output");
  } catch (error) {
    handleError("image-output", "image-feedback", error);
  }
});

document.getElementById("image-report-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  await ensureWindowSession();
  if (!window.confirm("这会把 Runtime 镜像上报到平台，继续吗？")) {
    return;
  }
  const form = new FormData(event.target);
  try {
    const job = await api("/local-api/image/report", {
      method: "POST",
      body: JSON.stringify({
        node_ref: form.get("node_ref"),
        runtime_image_ref: form.get("runtime_image_ref"),
        repository: form.get("repository"),
        tag: form.get("tag"),
        registry: form.get("registry"),
      }),
    });
    clearFeedback("image-feedback");
    await pollJob(job.job_id, "image-output");
  } catch (error) {
    handleError("image-output", "image-feedback", error);
  }
});

document.getElementById("refresh-state").addEventListener("click", async () => {
  await ensureWindowSession();
  try {
    const result = await api("/local-api/onboarding/current", { method: "GET" });
    clearFeedback("state-feedback");
    writeOutput("state-output", result);
  } catch (error) {
    handleError("state-output", "state-feedback", error);
  }
});

document.getElementById("close-onboarding").addEventListener("click", async () => {
  await ensureWindowSession();
  if (!window.confirm("这会关闭接入会话并清理当前浏览器窗口的 Codex/MCP 会话，继续吗？")) {
    return;
  }
  try {
    const result = await api("/local-api/onboarding/close", { method: "POST", body: JSON.stringify({}) });
    await api(`/local-api/window-session/close?session_id=${encodeURIComponent(windowSessionId)}`, {
      method: "POST",
      body: JSON.stringify({}),
    });
    windowSessionId = null;
    updateWindowSessionStatus(null);
    clearFeedback("state-feedback");
    writeOutput("state-output", result);
  } catch (error) {
    handleError("state-output", "state-feedback", error);
  }
});
