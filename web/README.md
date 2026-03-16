# 网页端（平台层，Vue3 Dashboard 原型）

本目录为前端工程（独立运行，不由 Flask 托管静态文件）。

当前实现：Vue3 + Element Plus + Pinia + ECharts（用于多设备视角的实时监控雏形）。

当前目标：
- 能看到设备列表（在线/离线、last_seen、最新温度/气压/光照）
- 能实时接收并展示最新 telemetry（通过 `/ws/dashboard`）
- 能对单设备展示实时曲线（最近若干点）

## 环境要求

- Node.js >= 22

## 配置

使用 Vite 环境变量：

- `VITE_API_BASE`：后端 HTTP 基地址（默认 `http://127.0.0.1:5000`）
- `VITE_WS_DASHBOARD_URL`：dashboard WebSocket 地址（默认从 API_BASE 推导为 `ws://.../ws/dashboard`）
- `VITE_API_KEY`：用于调用需要鉴权的接口（例如 `POST /api/commands/send`）的 Bearer Key

示例（Windows PowerShell）：
- `$env:VITE_API_BASE = "http://127.0.0.1:5000"`
- `$env:VITE_API_KEY = "<your_api_key>"`

## 启动

在 `ESP32/iot_ai_monitor/web` 目录：

- `npm install`
- `npm run dev`

浏览器访问：
- `http://127.0.0.1:5173/`

## 页面

- `/`：首页（监控 + 历史回放 + 配置参数框）
- `/device/:id`：设备详情页（信息/参数/配置下发）
