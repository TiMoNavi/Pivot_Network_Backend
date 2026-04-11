let windowSessionId = null;
let heartbeatTimer = null;
let latestSnapshot = null;

async function api(path, options = {}) {
  const headers = new Headers(options.headers || {});
  if (!headers.has("Content-Type") && options.body) {
    headers.set("Content-Type", "application/json");
  }
  if (windowSessionId) {
    headers.set("X-Window-Session-Id", windowSessionId);
  }
  const response = await fetch(path, {
    method: options.method || "GET",
    headers,
    body: options.body,
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = new Error(payload?.error?.message || `Request failed: ${response.status}`);
    error.payload = payload;
    throw error;
  }
  return payload;
}

function writeOutput(targetId, payload) {
  const target = document.getElementById(targetId);
  if (!target) {
    return;
  }
  target.textContent = JSON.stringify(payload, null, 2);
}

function setStatus(message) {
  const statusLine = document.getElementById("status-line");
  if (statusLine) {
    statusLine.textContent = message;
  }
}

function renderState(snapshot) {
  latestSnapshot = snapshot;
  writeOutput("state-output", snapshot);

  const runtimePlan = snapshot.runtime_access_plan || {};
  const shellUrl =
    runtimePlan.network_entry?.shell_embed_url ||
    snapshot.last_assistant_run?.shell?.shell_embed_url ||
    "";
  const shellFrame = document.getElementById("shell-frame");
  if (shellFrame && shellUrl) {
    shellFrame.src = shellUrl;
  }
}

function renderAssistantResult(payload) {
  writeOutput("assistant-output", payload);

  const shellUrl =
    payload.shell?.shell_embed_url ||
    payload.snapshot_after?.runtime_access_plan?.network_entry?.shell_embed_url ||
    "";
  if (shellUrl) {
    document.getElementById("shell-frame").src = shellUrl;
  }

  const taskPayload = {
    assistant_message: payload.assistant_message,
    task_result: payload.task_result,
    task_logs: payload.task_logs,
    workspace: payload.workspace,
    shell: payload.shell,
  };
  writeOutput("task-output", taskPayload);
}

async function refreshState() {
  const payload = await api("/local-api/runtime/current");
  renderState(payload);
  return payload;
}

async function openWindowSession() {
  const payload = await api("/local-api/window-session/open", { method: "POST", body: "{}" });
  windowSessionId = payload.session_id;
  setStatus(`浏览器会话已建立：${payload.session_id}`);
}

async function heartbeatWindowSession() {
  if (!windowSessionId) {
    return;
  }
  try {
    await api("/local-api/window-session/heartbeat", { method: "POST", body: "{}" });
  } catch (error) {
    setStatus(error.payload?.error?.message || String(error));
  }
}

function startHeartbeat() {
  if (heartbeatTimer) {
    clearInterval(heartbeatTimer);
  }
  heartbeatTimer = setInterval(heartbeatWindowSession, 30000);
}

function currentGrantCode() {
  return document.getElementById("grant-code").value.trim();
}

function currentWorkspacePath() {
  return document.getElementById("workspace-path").value.trim();
}

document.addEventListener("DOMContentLoaded", async () => {
  try {
    await openWindowSession();
    startHeartbeat();
    await refreshState();
  } catch (error) {
    setStatus(error.payload?.error?.message || String(error));
  }

  document.getElementById("login-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const payload = {
      email: document.getElementById("login-email").value,
      password: document.getElementById("login-password").value,
    };
    try {
      const result = await api("/local-api/auth/login", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      setStatus(`Buyer 登录成功：${result.user.display_name || result.user.email}`);
      await refreshState();
    } catch (error) {
      writeOutput("assistant-output", error.payload || { error: String(error) });
      setStatus(error.payload?.error?.message || String(error));
    }
  });

  document.getElementById("refresh-state").addEventListener("click", async () => {
    try {
      const payload = await refreshState();
      setStatus(`当前链路状态已刷新，runtime=${payload.runtime_session?.id || "none"}`);
    } catch (error) {
      setStatus(error.payload?.error?.message || String(error));
    }
  });

  document.getElementById("fetch-offers").addEventListener("click", async () => {
    try {
      const payload = await api("/local-api/offers");
      writeOutput("state-output", payload);
      setStatus(`已拉取 Offer：${payload.total}`);
    } catch (error) {
      writeOutput("state-output", error.payload || { error: String(error) });
      setStatus(error.payload?.error?.message || String(error));
    }
  });

  document.getElementById("fetch-grants").addEventListener("click", async () => {
    try {
      const payload = await api("/local-api/access-grants/active");
      writeOutput("state-output", payload);
      setStatus(`已拉取 Active Grants：${payload.total}`);
      await refreshState();
    } catch (error) {
      writeOutput("state-output", error.payload || { error: String(error) });
      setStatus(error.payload?.error?.message || String(error));
    }
  });

  document.getElementById("attach-grant").addEventListener("click", async () => {
    try {
      const payload = await api("/local-api/runtime/attach-active-grant", {
        method: "POST",
        body: JSON.stringify({}),
      });
      writeOutput("state-output", payload);
      setStatus(`已绑定 Active Grant：${payload.access_grant?.id || "first"}`);
      await refreshState();
    } catch (error) {
      writeOutput("state-output", error.payload || { error: String(error) });
      setStatus(error.payload?.error?.message || String(error));
    }
  });

  document.getElementById("import-grant").addEventListener("click", async () => {
    const grantCode = currentGrantCode();
    if (!grantCode) {
      setStatus("请先填写 Grant Code。");
      return;
    }
    try {
      const payload = await api("/local-api/access-grants/import-code", {
        method: "POST",
        body: JSON.stringify({ grant_code: grantCode }),
      });
      writeOutput("assistant-output", payload);
      setStatus(`Grant Code 已导入。`);
      await refreshState();
    } catch (error) {
      writeOutput("assistant-output", error.payload || { error: String(error) });
      setStatus(error.payload?.error?.message || String(error));
    }
  });

  document.getElementById("save-workspace").addEventListener("click", async () => {
    const workspacePath = currentWorkspacePath();
    if (!workspacePath) {
      setStatus("请先填写 Workspace 路径。");
      return;
    }
    try {
      const payload = await api("/local-api/workspace/select", {
        method: "POST",
        body: JSON.stringify({ path: workspacePath }),
      });
      writeOutput("assistant-output", payload);
      setStatus(`已保存 Workspace 路径：${workspacePath}`);
      await refreshState();
    } catch (error) {
      writeOutput("assistant-output", error.payload || { error: String(error) });
      setStatus(error.payload?.error?.message || String(error));
    }
  });

  document.getElementById("sync-workspace").addEventListener("click", async () => {
    try {
      const payload = await api("/local-api/workspace/sync", {
        method: "POST",
        body: JSON.stringify({ path: currentWorkspacePath() || null }),
      });
      writeOutput("task-output", payload);
      setStatus("工作区同步已完成。");
      await refreshState();
    } catch (error) {
      writeOutput("task-output", error.payload || { error: String(error) });
      setStatus(error.payload?.error?.message || String(error));
    }
  });

  document.getElementById("create-session").addEventListener("click", async () => {
    try {
      const payload = await api("/local-api/runtime-sessions/create", {
        method: "POST",
        body: JSON.stringify({ grant_code: currentGrantCode() || null }),
      });
      writeOutput("assistant-output", payload);
      setStatus(`Runtime session 已建立：${payload.runtime_session?.id || "unknown"}`);
      await refreshState();
    } catch (error) {
      writeOutput("assistant-output", error.payload || { error: String(error) });
      setStatus(error.payload?.error?.message || String(error));
    }
  });

  document.getElementById("wireguard-up").addEventListener("click", async () => {
    try {
      const payload = await api("/local-api/wireguard/up", {
        method: "POST",
        body: "{}",
      });
      writeOutput("task-output", payload);
      setStatus(`WireGuard 已拉起：${payload.interface_name || "unknown"}`);
      await refreshState();
    } catch (error) {
      writeOutput("task-output", error.payload || { error: String(error) });
      setStatus(error.payload?.error?.message || String(error));
    }
  });

  document.getElementById("open-shell").addEventListener("click", async () => {
    try {
      const payload = await api("/local-api/runtime-shell/open", {
        method: "POST",
        body: "{}",
      });
      document.getElementById("shell-frame").src = payload.shell_embed_url || "";
      writeOutput("task-output", payload);
      setStatus("Shell 已打开。");
    } catch (error) {
      writeOutput("task-output", error.payload || { error: String(error) });
      setStatus(error.payload?.error?.message || String(error));
    }
  });

  document.getElementById("run-assistant").addEventListener("click", async () => {
    const message = document.getElementById("assistant-message").value.trim();
    if (!message) {
      setStatus("请先输入自然语言请求。");
      return;
    }
    try {
      setStatus("正在通过网页自然语言入口驱动 Buyer_Client + MCP 链路。");
      const payload = await api("/local-api/assistant/message", {
        method: "POST",
        body: JSON.stringify({ message }),
      });
      renderAssistantResult(payload);
      setStatus(payload.ok ? "自然语言流程已完成。" : "自然语言流程失败，请看 assistant 输出。");
      await refreshState();
    } catch (error) {
      writeOutput("assistant-output", error.payload || { error: String(error) });
      setStatus(error.payload?.error?.message || String(error));
    }
  });
});
