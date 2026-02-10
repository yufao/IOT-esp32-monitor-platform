// 渲染端逻辑：通过 WebSocket 与 BLE Bridge 通信

const wsStatus = document.getElementById("wsStatus");
const bleStatus = document.getElementById("bleStatus");
const tempEl = document.getElementById("temp");
const pressureEl = document.getElementById("pressure");
const lightEl = document.getElementById("light");
const rawEl = document.getElementById("raw");
const scanList = document.getElementById("scanList");

const ws = new WebSocket("ws://127.0.0.1:8765");

ws.addEventListener("open", () => {
  wsStatus.textContent = "Connected";
  wsStatus.classList.remove("warn");
});

ws.addEventListener("close", () => {
  wsStatus.textContent = "Disconnected";
  wsStatus.classList.add("warn");
});

ws.addEventListener("message", (ev) => {
  try {
    const msg = JSON.parse(ev.data);

    if (msg.type === "scan") {
      scanList.textContent = msg.items.join("\n");
      return;
    }

    if (msg.type === "status") {
      bleStatus.textContent = `BLE: ${msg.state}`;
      return;
    }

    if (msg.type === "data") {
      const env = msg.payload.environment || {};
      const bmp = env.bmp280 || {};
      const light = env.light || {};
      tempEl.textContent = bmp.temp ?? "--";
      pressureEl.textContent = bmp.pressure ?? "--";
      lightEl.textContent = light.percent ?? "--";
      rawEl.textContent = JSON.stringify(msg.payload, null, 2);
    }
  } catch (_) {
    // ignore
  }
});

function sendCmd(payload) {
  ws.send(JSON.stringify(payload));
}

document.getElementById("btnScan").addEventListener("click", () => {
  sendCmd({ type: "scan" });
});

document.getElementById("btnConnect").addEventListener("click", () => {
  const name = document.getElementById("deviceName").value || "SLS_ESP32";
  sendCmd({ type: "connect", name });
});

document.getElementById("btnWifi").addEventListener("click", () => {
  const ssid = document.getElementById("ssid").value;
  const password = document.getElementById("password").value;
  sendCmd({ type: "wifi", ssid, password });
});

document.getElementById("btnThresh").addEventListener("click", () => {
  const tempHigh = document.getElementById("tempHigh").value;
  const tempLow = document.getElementById("tempLow").value;
  sendCmd({ type: "threshold", temp_high: tempHigh, temp_low: tempLow });
});
