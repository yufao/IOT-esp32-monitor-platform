// Electron 主进程
// 说明：启动窗口 + 启动 Python BLE 服务

const { app, BrowserWindow } = require("electron");
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
      preload: path.join(__dirname, "preload.js")
    }
  });

  win.loadFile(path.join(__dirname, "renderer", "index.html"));
}

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
