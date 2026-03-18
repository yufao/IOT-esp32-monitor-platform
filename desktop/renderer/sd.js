function qs(id) {
  const el = document.getElementById(id);
  if (!el) throw new Error(`missing_element_${id}`);
  return el;
}

function nowMs() {
  return Date.now();
}

function safeJsonStringify(obj) {
  try {
    return JSON.stringify(obj, null, 2);
  } catch (_) {
    return String(obj);
  }
}

function readConn() {
  return {
    baseUrl: String(qs("baseUrl").value || "").trim().replace(/\/+$/, ""),
    apiKey: String(qs("apiKey").value || "").trim(),
    deviceId: String(qs("deviceId").value || "").trim(),
  };
}

function writeConn(conn) {
  if (conn.baseUrl != null) qs("baseUrl").value = conn.baseUrl;
  if (conn.apiKey != null) qs("apiKey").value = conn.apiKey;
  if (conn.deviceId != null) qs("deviceId").value = conn.deviceId;
}

function loadConn() {
  const raw = localStorage.getItem("sls_sd_conn");
  if (!raw) return;
  try {
    const conn = JSON.parse(raw);
    writeConn(conn);
  } catch (_) {
    // ignore
  }
}

function saveConn() {
  const conn = readConn();
  localStorage.setItem("sls_sd_conn", JSON.stringify(conn));
  return conn;
}

function setBadge(ok, text) {
  const badge = qs("sdConnBadge");
  badge.textContent = text;
  badge.style.borderColor = ok ? "#2ea043" : "#d29922";
  badge.style.color = ok ? "#2ea043" : "#d29922";
}

function setHint(id, msg) {
  qs(id).textContent = msg || "";
}

function setOutput(msg) {
  qs("output").value = msg || "";
}

function getPath() {
  const p = String(qs("path").value || "").trim();
  return p || "/sd/";
}

function getMaxLines() {
  const raw = String(qs("maxLines").value || "").trim();
  if (!raw) return null;
  const n = Number(raw);
  if (!Number.isFinite(n) || n <= 0) return null;
  return Math.floor(n);
}

async function sendCommand(command) {
  if (!window.slsApi?.sendCommand) throw new Error("slsApi_sendCommand_unavailable");
  const conn = readConn();
  if (!conn.baseUrl) throw new Error("baseUrl_required");
  if (!conn.apiKey) throw new Error("apiKey_required");
  if (!conn.deviceId) throw new Error("deviceId_required");

  return window.slsApi.sendCommand({
    baseUrl: conn.baseUrl,
    apiKey: conn.apiKey,
    deviceId: conn.deviceId,
    command,
  });
}

async function getCommandStatus(cmdId) {
  if (!window.slsApi?.getCommandStatus) throw new Error("slsApi_getCommandStatus_unavailable");
  const conn = readConn();
  if (!conn.baseUrl) throw new Error("baseUrl_required");
  if (!conn.apiKey) throw new Error("apiKey_required");
  return window.slsApi.getCommandStatus({
    baseUrl: conn.baseUrl,
    apiKey: conn.apiKey,
    cmdId,
  });
}

async function pollCmdAck(cmdId, { timeoutMs = 15000, intervalMs = 600 } = {}) {
  const start = nowMs();
  while (nowMs() - start < timeoutMs) {
    const st = await getCommandStatus(cmdId);
    if (st && st.status === "done") {
      return st;
    }
    if (st && st.status === "unknown") {
      // command id expired/not found; stop early
      return st;
    }
    await new Promise((r) => setTimeout(r, intervalMs));
  }
  return { status: "timeout", cmd_id: cmdId };
}

function displayResult(title, payload) {
  const lastCmdIdEl = qs("lastCmdId");
  if (payload && payload.cmd_id) lastCmdIdEl.textContent = String(payload.cmd_id);

  const out = {
    title,
    payload,
  };
  setOutput(safeJsonStringify(out));
}

async function runCommandFlow(title, command) {
  setHint("cmdHint", "发送中...");
  setOutput("");
  try {
    const sendRes = await sendCommand(command);
    const cmdId = sendRes?.cmd_id || sendRes?.id || null;
    qs("lastCmdId").textContent = cmdId ? String(cmdId) : "-";

    if (!cmdId) {
      displayResult(title, { sendRes, note: "未返回 cmd_id，无法轮询" });
      setHint("cmdHint", "已发送（未返回 cmd_id）");
      return;
    }

    setHint("cmdHint", `已发送，轮询状态：${cmdId}`);
    const st = await pollCmdAck(cmdId);
    displayResult(title, st);

    if (st.status === "done") setHint("cmdHint", "完成（done）");
    else if (st.status === "timeout") setHint("cmdHint", "超时（timeout）");
    else setHint("cmdHint", `状态：${st.status || "unknown"}`);
  } catch (e) {
    setHint("cmdHint", "失败");
    displayResult(title, { error: String(e?.message || e) });
  }
}

async function testConnection() {
  setHint("connHint", "测试中...");
  setOutput("");

  try {
    const sendRes = await sendCommand({ type: "sd_info" });
    const cmdId = sendRes?.cmd_id || sendRes?.id || null;
    qs("lastCmdId").textContent = cmdId ? String(cmdId) : "-";
    if (!cmdId) throw new Error("no_cmd_id");

    const st = await pollCmdAck(cmdId, { timeoutMs: 8000, intervalMs: 500 });
    displayResult("test(sd_info)", st);
    if (st.status !== "done") throw new Error(st.status || "not_done");

    setBadge(true, "已连接");
    setHint("connHint", "OK");
  } catch (e) {
    setBadge(false, "未连接");
    setHint("connHint", String(e?.message || e));
    displayResult("test(sd_info)", { error: String(e?.message || e) });
  }
}

function bind() {
  qs("btnBack").addEventListener("click", () => {
    window.close();
  });

  qs("btnSave").addEventListener("click", () => {
    saveConn();
    setHint("connHint", "已保存");
  });

  qs("btnTest").addEventListener("click", async () => {
    saveConn();
    await testConnection();
  });

  qs("btnInfo").addEventListener("click", async () => {
    await runCommandFlow("sd_info", { type: "sd_info" });
  });

  qs("btnList").addEventListener("click", async () => {
    await runCommandFlow("sd_list", { type: "sd_list", path: getPath() });
  });

  qs("btnRead").addEventListener("click", async () => {
    const cmd = { type: "sd_read_text", path: getPath() };
    const maxLines = getMaxLines();
    if (maxLines) cmd.max_lines = maxLines;
    await runCommandFlow("sd_read_text", cmd);
  });

  qs("btnDelete").addEventListener("click", async () => {
    await runCommandFlow("sd_delete", { type: "sd_delete", path: getPath() });
  });

  qs("btnClearQueue").addEventListener("click", async () => {
    await runCommandFlow("sd_clear_queue", { type: "sd_clear_queue" });
  });

  qs("btnCopyCmdId").addEventListener("click", async () => {
    const text = String(qs("lastCmdId").textContent || "").trim();
    if (!text || text === "-") return;
    try {
      await navigator.clipboard.writeText(text);
      setHint("cmdHint", "cmd_id 已复制");
    } catch (_) {
      // ignore
    }
  });
}

(function init() {
  loadConn();
  setBadge(false, "未连接");
  bind();
})();
