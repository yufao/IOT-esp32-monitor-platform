// Electron 主进程
// 说明：启动窗口 + 启动 Python BLE 服务

const { app, BrowserWindow, ipcMain } = require("electron");
const path = require("path");
const { spawn } = require("child_process");

let pyProc = null; // Python 子进程

function startPythonBridge() {
  // 启动 Python BLE Bridge，使用本地 WebSocket 通信
  const script = path.join(__dirname, "python", "ble_client.py");
  pyProc = spawn("python", [script], {
    stdio: ["ignore", "pipe", "pipe"],
    env: {
      ...process.env,
      BLE_BRIDGE_PORT: "8765"
    }
  });

  pyProc.stdout.on("data", (data) => {
    console.log("[ble-bridge]", data.toString().trim());
  });

  pyProc.stderr.on("data", (data) => {
    console.error("[ble-bridge-err]", data.toString().trim());
  });
}

function createWindow() {
  const win = new BrowserWindow({
    width: 1200,
    height: 760,
    backgroundColor: "#0b0f14",
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
    }
  });

  win.loadFile(path.join(__dirname, "renderer", "index.html"));
}

function createSdWindow() {
  const win = new BrowserWindow({
    width: 1200,
    height: 760,
    backgroundColor: "#0b0f14",
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  win.loadFile(path.join(__dirname, "renderer", "sd.html"));
}

function normalizeBaseUrl(baseUrl) {
  const s = String(baseUrl || "").trim().replace(/\/+$/, "");
  if (!s) throw new Error("baseUrl_required");
  if (!/^https?:\/\//i.test(s)) throw new Error("baseUrl_must_be_http");
  return s;
}

async function httpJson(url, { method = "GET", headers = {}, body = undefined } = {}) {
  const res = await fetch(url, {
    method,
    headers,
    body,
  });
  let data = null;
  try {
    data = await res.json();
  } catch (_) {
    data = null;
  }
  if (!res.ok) {
    const msg = data && data.error ? String(data.error) : `http_${res.status}`;
    throw new Error(msg);
  }
  return data;
}

ipcMain.handle("ui:openSdManager", async () => {
  createSdWindow();
  return { ok: true };
});

ipcMain.handle("server:sendCommand", async (_ev, args) => {
  const baseUrl = normalizeBaseUrl(args?.baseUrl);
  const apiKey = String(args?.apiKey || "").trim();
  const deviceId = String(args?.deviceId || "").trim();
  const command = args?.command;
  if (!apiKey) throw new Error("apiKey_required");
  if (!deviceId) throw new Error("deviceId_required");
  if (!command || typeof command !== "object") throw new Error("command_required");

  const url = `${baseUrl}/api/commands/send`;
  return httpJson(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${apiKey}`,
    },
    body: JSON.stringify({ device_id: deviceId, command }),
  });
});

ipcMain.handle("server:getCommandStatus", async (_ev, args) => {
  const baseUrl = normalizeBaseUrl(args?.baseUrl);
  const apiKey = String(args?.apiKey || "").trim();
  const cmdId = String(args?.cmdId || "").trim();
  if (!apiKey) throw new Error("apiKey_required");
  if (!cmdId) throw new Error("cmdId_required");

  const url = `${baseUrl}/api/commands/status?cmd_id=${encodeURIComponent(cmdId)}`;
  return httpJson(url, {
    headers: {
      Authorization: `Bearer ${apiKey}`,
    },
  });
});

app.whenReady().then(() => {
  startPythonBridge();
  createWindow();

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    }
  });
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") {
    app.quit();
  }
});

app.on("before-quit", () => {
  if (pyProc) {
    pyProc.kill();
  }
});
