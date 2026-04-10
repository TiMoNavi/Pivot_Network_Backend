let windowSessionId = null;
let windowHeartbeatTimer = null;
let currentSnapshot = null;

const onboardingSessionStorageKey = "pivot-seller-current-session-id";

function getStoredOnboardingSessionId() {
  return window.localStorage.getItem(onboardingSessionStorageKey);
}

function setStoredOnboardingSessionId(sessionId) {
  if (!sessionId) {
    return;
  }
  window.localStorage.setItem(onboardingSessionStorageKey, sessionId);
  renderStoredSessionStatus(sessionId);
}

function clearStoredOnboardingSessionId() {
  window.localStorage.removeItem(onboardingSessionStorageKey);
  renderStoredSessionStatus(null);
}

function element(id) {
  return document.getElementById(id);
}

function safeString(value, fallback = "unknown") {
  const text = String(value || "").trim();
  return text || fallback;
}

function writeOutput(id, payload) {
  const target = element(id);
  if (!target) {
    return;
  }
  target.textContent = JSON.stringify(payload, null, 2);
}

function renderWindowSessionStatus(payload) {
  const target = element("window-session-status");
  if (!target) {
    return;
  }
  if (!payload || !payload.session_id) {
    target.textContent = "窗口 session 未初始化";
    return;
  }
  target.textContent = `窗口 session: ${payload.session_id} / TTL ${payload.ttl_seconds}s`;
}

function renderStoredSessionStatus(sessionId) {
  const target = element("stored-session-status");
  if (!target) {
    return;
  }
  target.textContent = sessionId
    ? `本地保存的 onboarding session_id: ${sessionId}`
    : "本地未保存 onboarding session_id";
}

async function api(path, options = {}) {
  const headers = { ...(options.headers || {}) };
  if (!headers["Content-Type"] && options.body !== undefined) {
    headers["Content-Type"] = "application/json";
  }
  if (windowSessionId) {
    headers["X-Window-Session-Id"] = windowSessionId;
  }
  const response = await fetch(path, { ...options, headers });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = new Error(payload?.error?.message || payload?.detail || "Request failed");
    error.payload = payload;
    error.status = response.status;
    throw error;
  }
  return payload;
}

function clearFeedback(id) {
  const box = element(id);
  if (!box) {
    return;
  }
  box.className = "feedback hidden";
  box.innerHTML = "";
}

function renderFeedback(id, payload, kind = "error") {
  const box = element(id);
  if (!box) {
    return;
  }
  const error = payload?.error || payload || {};
  const step = error.step ? `<p><strong>Step</strong> ${error.step}</p>` : "";
  const code = error.code ? `<p><strong>Code</strong> ${error.code}</p>` : "";
  const hint = error.hint ? `<p><strong>Hint</strong> ${error.hint}</p>` : "";
  box.className = `feedback ${kind}`;
  box.innerHTML = `<h3>${error.message || "Request failed"}</h3>${step}${code}${hint}`;
}

function handleError(outputId, feedbackId, error) {
  const payload = error.payload || { error: { message: String(error) } };
  renderFeedback(feedbackId, payload);
  writeOutput(outputId, payload);
}

function parseJsonEditor(id) {
  const raw = element(id)?.value.trim() || "";
  if (!raw) {
    return {};
  }
  return JSON.parse(raw);
}

function renderDraftEditors(drafts) {
  const payloads = drafts?.write_payloads || {};
  if (element("host-probe-editor")) {
    element("host-probe-editor").value = JSON.stringify(payloads.linux_host_probe || {}, null, 2);
  }
  if (element("substrate-probe-editor")) {
    element("substrate-probe-editor").value = JSON.stringify(payloads.linux_substrate_probe || {}, null, 2);
  }
  if (element("runtime-probe-editor")) {
    element("runtime-probe-editor").value = JSON.stringify(payloads.container_runtime_probe || {}, null, 2);
  }
  if (element("join-complete-editor")) {
    element("join-complete-editor").value = JSON.stringify(payloads.join_complete || {}, null, 2);
  }
}

function currentExpectedWireGuardIp() {
  return (
    currentSnapshot?.onboarding_session?.expected_wireguard_ip ||
    element("session-form")?.querySelector('input[name="expected_wireguard_ip"]')?.value?.trim() ||
    ""
  );
}

function currentWireGuardConfigPath() {
  return element("wireguard-config-path")?.value?.trim() || null;
}

function currentWorkflow() {
  return currentSnapshot?.last_runtime_workflow || null;
}

function currentManagerTaskResult() {
  const workflow = currentWorkflow();
  if (!workflow) {
    return null;
  }
  if (workflow.kind === "guided_join_assessment" || workflow.kind === "execute_guided_join") {
    return workflow.manager_task_execution || null;
  }
  if (workflow.kind === "verify_manager_task_execution" || workflow.kind === "verify_manager_task") {
    return workflow.result || null;
  }
  return null;
}

function currentWireGuardPrepResult() {
  const workflow = currentWorkflow();
  if (!workflow) {
    return null;
  }
  if (workflow.kind === "guided_join_assessment" || workflow.kind === "execute_guided_join") {
    return workflow.wireguard_config_preparation || null;
  }
  if (workflow.kind === "prepare_machine_wireguard_config" || workflow.kind === "prepare_machine_wireguard") {
    return workflow.result || null;
  }
  if (workflow.kind === "standard_join_workflow") {
    return workflow.wireguard_config_preparation || workflow.workflow?.wireguard_config_preparation || null;
  }
  return null;
}

function renderSummary(snapshot) {
  const onboarding = snapshot?.onboarding_session || {};
  const health = snapshot?.local_health_snapshot || {};
  const docker = health?.docker || {};
  const summary = health?.summary || {};
  const managerAcceptance = onboarding?.manager_acceptance || {};
  const workflow = snapshot?.last_runtime_workflow || {};
  const joinEffect = workflow?.join_effect || {};
  const managerTaskResult = currentManagerTaskResult();
  const managerTaskPayload = managerTaskResult?.payload || {};
  const completionStandard = joinEffect?.success_standard || managerTaskPayload?.completion_standard || "manager_task_execution";

  element("env-status-pill").textContent = `环境状态: ${summary.status || "未检查"}`;
  element("onboarding-status-pill").textContent = `接入状态: ${onboarding?.status || "未开始"}`;
  element("truth-status-pill").textContent = `完成标准: ${completionStandard}`;

  element("summary-env").textContent = summary.status || "未检查";
  element("summary-env-detail").textContent = summary.warnings?.length
    ? `待关注: ${summary.warnings.join(", ")}`
    : "环境检查通过后，这里会显示风险摘要。";

  element("summary-swarm").textContent = docker?.local_node_state || "未知";
  element("summary-swarm-detail").textContent = docker?.node_addr
    ? `NodeAddr: ${docker.node_addr}`
    : "等待 Docker / Swarm 检查。";

  element("summary-manager").textContent = managerAcceptance?.status || "未知";
  element("summary-manager-detail").textContent = managerAcceptance?.observed_manager_node_addr
    ? `Manager 记录地址: ${managerAcceptance.observed_manager_node_addr}`
    : "等待 manager raw truth。";

  const managerTaskVerified = managerTaskResult?.ok || joinEffect?.manager_task_execution?.verified;
  const managerTaskStatus =
    joinEffect?.manager_task_execution?.status ||
    managerTaskPayload?.status ||
    (managerTaskVerified ? "verified" : "unknown");
  const proofSource = joinEffect?.manager_task_execution?.proof_source || managerTaskPayload?.proof_source || null;

  element("summary-target").textContent = managerTaskStatus || "未知";
  element("summary-target-detail").textContent = managerTaskVerified
    ? `Manager task verified${proofSource ? ` / ${proofSource}` : ""}`
    : `等待 manager 侧 task 执行验证${onboarding?.effective_target_addr ? ` / target ${onboarding.effective_target_addr}` : ""}`;
}

function renderSectionOutputs(snapshot) {
  const onboarding = snapshot?.onboarding_session || null;
  const health = snapshot?.local_health_snapshot || {};
  const workflow = snapshot?.last_runtime_workflow || null;
  const wireguardPrep = currentWireGuardPrepResult();
  const managerTask = currentManagerTaskResult();

  writeOutput("health-output", health || {});

  writeOutput("network-output", {
    wireguard_config_preparation: wireguardPrep,
    wireguard: health?.wireguard || {},
    runtime_workflow: workflow,
    runtime_evidence: snapshot?.runtime_evidence || {},
  });

  writeOutput("docker-output", {
    onboarding_session: onboarding,
    docker: health?.docker || {},
    join_workflow:
      workflow?.kind === "guided_join_assessment" || workflow?.kind === "execute_guided_join" ? workflow.join_workflow || workflow.workflow :
      workflow?.kind === "standard_join_workflow" || workflow?.kind === "execute_join_workflow" ? workflow.workflow :
      null,
    manager_task_execution: managerTask,
    join_effect: workflow?.kind === "guided_join_assessment" || workflow?.kind === "execute_guided_join" ? workflow.join_effect : null,
    runtime_workflow: workflow,
  });

  writeOutput("session-output", {
    current_user: snapshot?.current_user,
    auth_session: snapshot?.auth_session,
    onboarding_session: onboarding,
    paths: snapshot?.paths,
  });

  writeOutput(
    "join-material-output",
    onboarding
      ? {
          session_id: onboarding.session_id,
          expected_wireguard_ip: onboarding.expected_wireguard_ip,
          swarm_join_material: onboarding.swarm_join_material || {},
          required_labels: onboarding.required_labels || {},
          manager_acceptance: onboarding.manager_acceptance || {},
          effective_target_addr: onboarding.effective_target_addr,
          effective_target_source: onboarding.effective_target_source,
          truth_authority: onboarding.truth_authority,
          minimum_tcp_validation: onboarding.minimum_tcp_validation || {},
        }
      : {},
  );
}

async function ensureWindowSession() {
  if (windowSessionId) {
    return;
  }
  const payload = await api("/local-api/window-session/open", {
    method: "POST",
    body: JSON.stringify({}),
  });
  windowSessionId = payload.session_id;
  renderWindowSessionStatus(payload);
  if (windowHeartbeatTimer) {
    window.clearInterval(windowHeartbeatTimer);
  }
  windowHeartbeatTimer = window.setInterval(async () => {
    if (!windowSessionId) {
      return;
    }
    try {
      const heartbeat = await api("/local-api/window-session/heartbeat", {
        method: "POST",
        body: JSON.stringify({}),
      });
      renderWindowSessionStatus(heartbeat);
    } catch (error) {
      console.warn("window session heartbeat failed", error);
    }
  }, 15000);
}

async function pollJob(jobId, outputId, feedbackId) {
  while (true) {
    const payload = await api(`/local-api/jobs/${jobId}`, { method: "GET" });
    writeOutput(outputId, payload);
    if (payload.status === "succeeded" || payload.status === "failed") {
      if (payload.status === "failed") {
        renderFeedback(feedbackId, { error: payload.error || { message: "Job failed" } });
      } else {
        clearFeedback(feedbackId);
      }
      return payload;
    }
    await new Promise((resolve) => window.setTimeout(resolve, 1200));
  }
}

async function refreshSnapshot() {
  const snapshot = await api("/local-api/onboarding/current", { method: "GET" });
  currentSnapshot = snapshot;
  renderSummary(snapshot);
  renderSectionOutputs(snapshot);
  const sessionId = snapshot?.onboarding_session?.session_id || null;
  if (sessionId) {
    setStoredOnboardingSessionId(sessionId);
  }
  const suggestedHost =
    snapshot?.onboarding_session?.effective_target_addr ||
    snapshot?.onboarding_session?.expected_wireguard_ip ||
    "";
  if (suggestedHost && !element("tcp-host").value) {
    element("tcp-host").value = suggestedHost;
  }
  return snapshot;
}

async function attachStoredSession() {
  const sessionId = getStoredOnboardingSessionId();
  if (!sessionId) {
    throw new Error("No saved onboarding session_id in browser storage.");
  }
  const payload = await api("/local-api/onboarding/attach", {
    method: "POST",
    body: JSON.stringify({ session_id: sessionId }),
  });
  clearFeedback("session-feedback");
  setStoredOnboardingSessionId(payload.session.session_id);
  renderDraftEditors(payload.phase1_drafts);
  writeOutput("session-output", payload);
  await refreshSnapshot();
  return payload;
}

async function submitProbe(path, editorId) {
  const payload = parseJsonEditor(editorId);
  const result = await api(path, {
    method: "POST",
    body: JSON.stringify(payload),
  });
  const sessionId = result?.session_id || result?.last_join_complete?.join_session_id || getStoredOnboardingSessionId();
  if (sessionId) {
    setStoredOnboardingSessionId(sessionId);
  }
  writeOutput("session-output", result);
  await refreshSnapshot();
  return result;
}

async function startJob(path, body, outputId, feedbackId) {
  const job = await api(path, {
    method: "POST",
    body: JSON.stringify(body || {}),
  });
  clearFeedback(feedbackId);
  const result = await pollJob(job.job_id, outputId, feedbackId);
  await refreshSnapshot();
  return result;
}

function compactPayload(payload) {
  return Object.fromEntries(
    Object.entries(payload).filter(([, value]) => value !== undefined && value !== null && value !== ""),
  );
}

function wireGuardPreparationRequest() {
  return compactPayload({
    source_path: currentWireGuardConfigPath(),
    expected_wireguard_ip: currentExpectedWireGuardIp() || null,
  });
}

function standardJoinWorkflowRequest() {
  const expectedWireGuardIp = currentExpectedWireGuardIp() || null;
  return compactPayload({
    join_mode: "wireguard",
    advertise_address: expectedWireGuardIp,
    data_path_address: expectedWireGuardIp,
    wireguard_config_path: currentWireGuardConfigPath(),
  });
}

function guidedJoinAssessmentRequest() {
  return compactPayload({
    join_mode: "wireguard",
    expected_wireguard_ip: currentExpectedWireGuardIp() || null,
    wireguard_config_path: currentWireGuardConfigPath(),
    overlay_sample_count: 2,
    overlay_interval_seconds: 1,
    post_join_probe_count: 8,
    probe_interval_seconds: 1,
    manager_probe_count: 4,
    manager_probe_interval_seconds: 2,
    task_probe_timeout_seconds: 60,
    task_probe_interval_seconds: 3,
  });
}

window.addEventListener("beforeunload", () => {
  if (!windowSessionId) {
    return;
  }
  fetch("/local-api/window-session/close", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Window-Session-Id": windowSessionId,
    },
    body: JSON.stringify({}),
    keepalive: true,
  }).catch(() => {});
});

window.addEventListener("load", async () => {
  renderStoredSessionStatus(getStoredOnboardingSessionId());
  try {
    await ensureWindowSession();
    await refreshSnapshot();
  } catch (error) {
    handleError("session-output", "session-feedback", error);
  }
});

element("login-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  await ensureWindowSession();
  const form = new FormData(event.target);
  try {
    const result = await api("/local-api/auth/login", {
      method: "POST",
      body: JSON.stringify({
        email: form.get("email"),
        password: form.get("password"),
      }),
    });
    clearFeedback("session-feedback");
    writeOutput("session-output", result);
    if (getStoredOnboardingSessionId()) {
      await attachStoredSession();
    } else {
      await refreshSnapshot();
    }
  } catch (error) {
    handleError("session-output", "session-feedback", error);
  }
});

element("register-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  await ensureWindowSession();
  const form = new FormData(event.target);
  try {
    const result = await api("/local-api/auth/register", {
      method: "POST",
      body: JSON.stringify({
        email: form.get("email"),
        display_name: form.get("display_name"),
        password: form.get("password"),
      }),
    });
    clearFeedback("session-feedback");
    writeOutput("session-output", result);
    await refreshSnapshot();
  } catch (error) {
    handleError("session-output", "session-feedback", error);
  }
});

element("session-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  await ensureWindowSession();
  const form = new FormData(event.target);
  try {
    const result = await api("/local-api/onboarding/start", {
      method: "POST",
      body: JSON.stringify({
        requested_accelerator: form.get("requested_accelerator"),
        requested_compute_node_id: form.get("requested_compute_node_id") || null,
        requested_offer_tier: form.get("requested_offer_tier") || null,
        expected_wireguard_ip: form.get("expected_wireguard_ip") || null,
      }),
    });
    clearFeedback("session-feedback");
    setStoredOnboardingSessionId(result.session.session_id);
    renderDraftEditors(result.phase1_drafts);
    writeOutput("session-output", result);
    await refreshSnapshot();
  } catch (error) {
    handleError("session-output", "session-feedback", error);
  }
});

element("attach-session").addEventListener("click", async () => {
  try {
    await ensureWindowSession();
    await attachStoredSession();
  } catch (error) {
    handleError("session-output", "session-feedback", error);
  }
});

element("load-join-material").addEventListener("click", async () => {
  try {
    await ensureWindowSession();
    const result = await api("/local-api/onboarding/join-material", { method: "GET" });
    clearFeedback("session-feedback");
    writeOutput("join-material-output", result);
    await refreshSnapshot();
  } catch (error) {
    handleError("join-material-output", "session-feedback", error);
  }
});

element("load-drafts").addEventListener("click", async () => {
  try {
    await ensureWindowSession();
    const drafts = await api("/local-api/onboarding/phase1-drafts", { method: "GET" });
    clearFeedback("session-feedback");
    renderDraftEditors(drafts);
    writeOutput("session-output", drafts);
  } catch (error) {
    handleError("session-output", "session-feedback", error);
  }
});

element("close-session").addEventListener("click", async () => {
  try {
    await ensureWindowSession();
    const result = await api("/local-api/onboarding/close", {
      method: "POST",
      body: JSON.stringify({}),
    });
    clearFeedback("session-feedback");
    clearStoredOnboardingSessionId();
    writeOutput("session-output", result);
    await refreshSnapshot();
  } catch (error) {
    handleError("session-output", "session-feedback", error);
  }
});

element("run-system-check").addEventListener("click", async () => {
  try {
    await ensureWindowSession();
    await startJob("/local-api/system/check", {}, "health-output", "system-feedback");
  } catch (error) {
    handleError("health-output", "system-feedback", error);
  }
});

element("run-system-repair").addEventListener("click", async () => {
  try {
    await ensureWindowSession();
    await startJob("/local-api/system/repair", {}, "health-output", "system-feedback");
  } catch (error) {
    handleError("health-output", "system-feedback", error);
  }
});

element("export-diagnostics").addEventListener("click", async () => {
  try {
    await ensureWindowSession();
    await startJob("/local-api/system/export-diagnostics", {}, "health-output", "system-feedback");
  } catch (error) {
    handleError("health-output", "system-feedback", error);
  }
});

element("prepare-wireguard-config").addEventListener("click", async () => {
  try {
    await ensureWindowSession();
    await startJob(
      "/local-api/runtime/prepare-wireguard-config",
      wireGuardPreparationRequest(),
      "network-output",
      "network-feedback",
    );
  } catch (error) {
    handleError("network-output", "network-feedback", error);
  }
});

element("run-overlay-check").addEventListener("click", async () => {
  try {
    await ensureWindowSession();
    await startJob("/local-api/runtime/overlay-check", {}, "network-output", "network-feedback");
  } catch (error) {
    handleError("network-output", "network-feedback", error);
  }
});

element("run-guided-join-assessment").addEventListener("click", async () => {
  try {
    await ensureWindowSession();
    await startJob(
      "/local-api/runtime/guided-join-assessment",
      guidedJoinAssessmentRequest(),
      "docker-output",
      "docker-feedback",
    );
  } catch (error) {
    handleError("docker-output", "docker-feedback", error);
  }
});

element("run-join-workflow").addEventListener("click", async () => {
  try {
    await ensureWindowSession();
    await startJob(
      "/local-api/runtime/join-workflow",
      standardJoinWorkflowRequest(),
      "docker-output",
      "docker-feedback",
    );
  } catch (error) {
    handleError("docker-output", "docker-feedback", error);
  }
});

element("verify-manager-task-execution").addEventListener("click", async () => {
  try {
    await ensureWindowSession();
    await startJob(
      "/local-api/runtime/verify-manager-task-execution",
      {
        task_probe_timeout_seconds: 60,
        task_probe_interval_seconds: 3,
      },
      "docker-output",
      "docker-feedback",
    );
  } catch (error) {
    handleError("docker-output", "docker-feedback", error);
  }
});

element("clear-join-state").addEventListener("click", async () => {
  try {
    await ensureWindowSession();
    await startJob("/local-api/runtime/clear-join-state", {}, "docker-output", "docker-feedback");
  } catch (error) {
    handleError("docker-output", "docker-feedback", error);
  }
});

element("refresh-status").addEventListener("click", async () => {
  try {
    await ensureWindowSession();
    clearFeedback("docker-feedback");
    await api("/local-api/onboarding/refresh", {
      method: "POST",
      body: JSON.stringify({}),
    });
    await refreshSnapshot();
  } catch (error) {
    handleError("docker-output", "docker-feedback", error);
  }
});

element("tcp-validation-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  await ensureWindowSession();
  const form = new FormData(event.target);
  try {
    const result = await api("/local-api/onboarding/tcp-validation", {
      method: "POST",
      body: JSON.stringify({
        host: form.get("host"),
        port: Number(form.get("port")),
        target_label: "manual_tcp_validation",
      }),
    });
    clearFeedback("network-feedback");
    writeOutput("network-output", result);
    await refreshSnapshot();
  } catch (error) {
    handleError("network-output", "network-feedback", error);
  }
});

element("submit-host-probe").addEventListener("click", async () => {
  try {
    await ensureWindowSession();
    clearFeedback("session-feedback");
    await submitProbe("/local-api/onboarding/probes/linux-host", "host-probe-editor");
  } catch (error) {
    handleError("session-output", "session-feedback", error);
  }
});

element("submit-substrate-probe").addEventListener("click", async () => {
  try {
    await ensureWindowSession();
    clearFeedback("session-feedback");
    await submitProbe("/local-api/onboarding/probes/linux-substrate", "substrate-probe-editor");
  } catch (error) {
    handleError("session-output", "session-feedback", error);
  }
});

element("submit-runtime-probe").addEventListener("click", async () => {
  try {
    await ensureWindowSession();
    clearFeedback("session-feedback");
    await submitProbe("/local-api/onboarding/probes/container-runtime", "runtime-probe-editor");
  } catch (error) {
    handleError("session-output", "session-feedback", error);
  }
});

element("submit-join-complete").addEventListener("click", async () => {
  try {
    await ensureWindowSession();
    clearFeedback("session-feedback");
    await submitProbe("/local-api/onboarding/join-complete", "join-complete-editor");
  } catch (error) {
    handleError("session-output", "session-feedback", error);
  }
});

element("assistant-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  await ensureWindowSession();
  const form = new FormData(event.target);
  try {
    const job = await api("/local-api/assistant/message", {
      method: "POST",
      body: JSON.stringify({ message: form.get("message") }),
    });
    clearFeedback("assistant-feedback");
    const result = await pollJob(job.job_id, "assistant-output", "assistant-feedback");
    if (result.result) {
      writeOutput("assistant-output", result.result);
    }
    await refreshSnapshot();
  } catch (error) {
    handleError("assistant-output", "assistant-feedback", error);
  }
});
