# ESP32-IoT 智能监测平台

Smart Lab Sentinel：一个面向实验室/宿舍场景的多模态监测系统，强调“边缘采集 + 本地事件 + 双端管理”。

当前已跑通“四方联调”：
- HARDWARE（ESP32 / MicroPython）→ SERVER（Flask + WebSocket）
- WEB（Vite + Vue3 Dashboard）实时展示设备与 telemetry
- DESKTOP（Electron + BLE Bridge）本地直连运维 + 通过 Server 命令通道做 TF/SD 管理

## 核心特性
- 多模态传感：BMP280 温度/气压 + 光敏
- 双通道：WiFi（HTTP/WS）上报 + BLE 本地直连
- 服务端：REST + WebSocket（/ws/telemetry, /ws/dashboard），支持命令下发与回执
- 网页端：多设备列表、实时订阅、基础历史查询与参数下发入口
- 桌面端：BLE 配网/阈值设置/本地日志；TF/SD 管理（通过 Server 命令通道）
- 稳定性：非阻塞调度、失败队列、定时 GC、联网超时保护

## 目录结构
- hardware：ESP32端（采集、缓存、上传、轻AI、蓝牙、预警）
- server：服务端（Flask、SQLite、RESTful接口）
- web：网页端（Vue3、ECharts）
- desktop：桌面端（Electron）
- docs：项目文档（规范、联调、架构）
- tests：测试脚本（链路测试、联调测试）

## 开发约定
1. 敏感配置写入 `hardware/hw_config.py`，不提交仓库。
2. 运行时配置写入 `hardware/runtime_config.json`（由设备端自动生成）。
3. BLE 指令使用 JSON 格式，字段保持稳定。


## 开发计划
请先查看 docs/01_项目规划与阶段目标.md

## 快速开始（四方联调）

建议按顺序启动：Server → Web → Desktop → Hardware。

### 1) 启动 Server（Flask）

在 `ESP32/iot_ai_monitor/`：
- `python -m venv .venv`
- Windows：`\.venv\Scripts\Activate.ps1`
- `pip install -r server/requirements.txt`
- `python -m server.app`

验证：`GET http://127.0.0.1:5000/health`

### 2) 启动 Web（Vite）

在 `ESP32/iot_ai_monitor/web/`：
- 复制 `.env.local.example` 为 `.env.local`，设置 `VITE_API_BASE`（远程访问必须是云服务器公网地址）
- `npm install`
- `npm run dev`

访问：`http://127.0.0.1:5173/`

### 3) 启动 Desktop（Electron + BLE Bridge）

在 `ESP32/iot_ai_monitor/desktop/`：
- `npm install`
- 在 `desktop/python/`：`python -m pip install -r requirements.txt`
- 回到 `desktop/`：`npm start`

### 4) 启动 Hardware（ESP32 / MicroPython）

在设备文件系统中放置/更新：
- `hardware/` 目录下的模块
- `hardware/hw_config.py`（从 `hw_config.sample.py` 复制并改 WiFi/Server 地址/API Key）

运行入口：`hardware/main.py`

## 当前状态
- ESP32：BMP280 + 光敏采集稳定；WiFi 上报（WS/HTTP）稳定
- Server：REST + WebSocket 可用；设备/Telemetry/命令通道闭环
- Web：可实时显示设备与 telemetry；可通过命令通道下发配置/SD 指令（依赖固件支持）
- Desktop：BLE 仪表盘 + 配网/阈值 + TF/SD 管理入口可用

详细步骤见：`docs/04_Phase1_联调与部署步骤.md`

## BLE 指令格式
WiFi 配网：
```json
{"type":"wifi","ssid":"YOUR_SSID","password":"YOUR_PASS"}
```
阈值设置：
```json
{"type":"threshold","temp_high":30,"temp_low":15}
```
