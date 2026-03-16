# Phase 1 联调与部署步骤（路线A：Flask + 原生 WebSocket）

更新时间：2026-03-16

目标：
- 先打通 ESP32 → Server 的 WebSocket 直连链路（/ws/telemetry）
- 再打通 Web 订阅链路（/ws/dashboard）
- 缓存功能默认关闭（KEY2 控制是否启用失败重试缓存，当前仅内存队列，不写 Flash/TF）

---

## 1. Server（本地/开发环境）快速启动

位置：`ESP32/iot_ai_monitor/server/`

建议先切到项目子根目录：`ESP32/iot_ai_monitor/`

1) 创建虚拟环境并安装依赖：
- `python -m venv .venv`
- Windows PowerShell：`.\.venv\Scripts\Activate.ps1`
- `pip install -r requirements.txt`

2) 启动（推荐模块模式）：
- `python -m server.app`

备选（直接运行）：
- `python server/app.py`

如需改端口：
- 环境变量：`SLS_PORT=5000`、`SLS_API_KEYS=dev_key`、`SLS_CORS_ORIGINS=*`

3) 健康检查：
- `GET http://127.0.0.1:5000/health`

---

## 2. WebSocket 联调（不依赖 Vue）

### 2.1 用浏览器验证 /ws/dashboard

在浏览器控制台执行：
- `const ws = new WebSocket('ws://127.0.0.1:5000/ws/dashboard');`
- `ws.onmessage = (e) => console.log('msg', e.data);`

预期：连接后收到一条 `snapshot`。

### 2.2 用脚本/工具验证 /ws/telemetry

建议做法（后续补测试脚本）：
- 先发送 `hello`（包含 api_key）
- 再周期发送 `telemetry`（带 seq）
- 观察 Server 返回 `ack`

备注：Server 默认 api key 集合来自环境变量 `SLS_API_KEYS`，默认值为 `dev_key`。

---

## 2.5 Web 前端（前后端分离，Node 22）

位置：`ESP32/iot_ai_monitor/web/`

1) 安装依赖：
- `npm install`

2) 配置后端地址（可选）：
- `VITE_API_BASE`：例如 `http://127.0.0.1:5000`

3) 启动开发服务器：
- `npm run dev`

4) 访问：
- `http://127.0.0.1:5173/`

预期：
- 页面收到 `snapshot` 后显示设备列表（在线/离线、last_seen、最新值）
- 当 server 广播 `telemetry/device_status` 时实时更新
- 右侧实时曲线随选中设备更新

---

## 3. ESP32 端（联调顺序）

### 3.1 先确认 MicroPython WebSocket 模块可用
在 REPL：
- `import websocket`
- `import uwebsocket`

如可 import，则进入下一步。

### 3.2 KEY2 缓存开关（仅内存队列）

硬件端入口：`ESP32/iot_ai_monitor/hardware/main.py`
- KEY2 绑定 `KEY2_PIN`（模板默认 GPIO27）
- 默认 `cache_enabled = False`
- 按下 KEY2：切换 `cache_enabled`，仅影响“WiFi 失败时是否入队 retry_queue”

注意：部分 ESP32 模组 GPIO6~11 可能连接板载 Flash，不一定可用；如你改到这些脚位且异常请更换 KEY2_PIN。

### 3.3 WebSocket 直连配置（路线A）

配置文件：`hardware/hw_config.py`（不提交仓库）

建议至少包含：
- `SERVER_WS_URL`：例如 `ws://<server>:5000/ws/telemetry`
- `API_KEY`：与服务端环境变量 `SLS_API_KEYS` 对齐
- `FIRMWARE_VERSION`：例如 `0.1.0`

备注：模板 `hw_config.sample.py` 已提供以上字段。

另外（可选）：HTTP 备用上报通道（当 WS 不可用/异常时兜底）
- `SERVER_URL`：例如 `http://<server>:5000/api/telemetry`
- 鉴权：硬件端会使用 `API_KEY` 自动加上 `Authorization: Bearer <api_key>`（与 `SLS_API_KEYS` 对齐）

---

## 4. 远端类 CentOS（阿里云）部署建议（生产/演示）

### 4.1 推荐运行方式
- 使用 `gunicorn` 托管 Flask
- WebSocket 建议配合 `gevent` 或 `eventlet`

（flask-sock 官方说明：开发服务器可用；生产可用 Gunicorn、Eventlet 或 Gevent。）

### 4.2 systemd 托管
- 创建 venv
- 安装 `requirements.txt` + `gunicorn` + `gevent`（或 eventlet）
- systemd 配置 `Restart=always`

### 4.3 Nginx 反代（可选，但推荐用于 TLS）
- 反代必须正确透传 `Upgrade` / `Connection` 头，否则 WebSocket 握手会失败

---

## 5. Phase 1 验收清单

- Server：`/health` OK
- ESP32：WS hello 成功，telemetry 周期发送并收到 ack
- Dashboard：能接收 telemetry 广播
- 离线：ESP32 断网不崩溃；缓存默认关闭（KEY2 可临时开启内存重试）
