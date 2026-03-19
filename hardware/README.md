# 硬件端（ESP32 / MicroPython）

此目录存放硬件端核心逻辑：采集、缓存、上传、异常检测、蓝牙备用、LED/蜂鸣器预警。

本阶段已跑通：
- WiFi → Server：WebSocket（主通道）+ HTTP（兜底）
- BLE → Desktop：本地直连仪表盘 / 配网 / 基础配置
- Server → Device：命令下发与 cmd_ack 回执（供 Web/Desktop 使用）

后续文件规划：
- hw_config.py：引脚与常量配置（不提交仓库）
- hw_config.sample.py：配置模板（提交仓库）
- hw_runtime_config.py：运行时配置读写
- runtime_config.json：设备运行时生成
- hw_sensors.py：BMP280 + 光敏采集与标准化
- hw_wifi_uploader.py：WiFi连接与HTTP上传
- hw_ble_server.py：BLE GATT 服务
- main.py：主入口（信道切换、上报、BLE指令）

---

## 1) 必改配置（hw_config.py）

从 `hw_config.sample.py` 复制为 `hw_config.py`（此文件不要提交仓库），至少修改：
- `DEVICE_ID`
- `WIFI_SSID` / `WIFI_PASSWORD`
- `SERVER_WS_URL`：例如 `ws://<server>:5000/ws/telemetry`
- `SERVER_URL`（可选兜底）：例如 `http://<server>:5000/api/telemetry`
- `API_KEY`：与服务端环境变量 `SLS_API_KEYS` 对齐（默认 `dev_key`）

注意：
- 远程公网联调时，`<server>` 必须是云服务器公网 IP/域名，端口 `5000` 必须放行。
- KEY2 默认 GPIO27；不要用 GPIO6~11（部分模组连接板载 Flash）。

---

## 2) 运行方式

入口是 `main.py`（同目录）。常见运行路径：
- Thonny 直接运行 `hardware/main.py`
- 或将 `hardware/` 下模块同步到设备文件系统后，在 REPL 执行 `import main`

---

## 3) 最小“需要同步到设备”的文件范围

你不需要每次全量重刷；一般只同步改动过的模块即可。

如果你只关心“WiFi + WS 能稳定连上 Server”，最小同步集通常是：
- `hw_config.py`
- `hw_ws_client.py`
- `hw_ws_min_client.py`（当固件 websocket 库不完整时的兜底实现）
- `hw_wifi_uploader.py`（HTTP 兜底/联网相关）
- `main.py`

如果你只改了传感器侧节流/读取逻辑，再同步：
- `hw_sensors.py`

---

## 4) 快速排障

1) Server 端口未放行的典型现象：
- 设备端出现长时间卡住/重启（网络调用阻塞）
- Web 端 `Failed to fetch` 或 `WS Disconnected`

2) Web 端没设备但 Server 正常：
- 检查 Web 的 `.env.local`：`VITE_API_BASE` 必须指向 `http://<server>:5000`，修改后必须重启 `npm run dev`

3) WS 可用性：
- 设备会优先走 `/ws/telemetry`；如果固件自带 websocket 客户端缺失/不兼容，会自动兜底到最小 WS 客户端实现
