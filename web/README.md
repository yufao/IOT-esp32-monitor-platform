# 网页端（平台层，Vue3 Dashboard 原型）

本目录为前端工程（独立运行，不由 Flask 托管静态文件）。

当前实现：Vue3 + Element Plus + Pinia + ECharts（用于多设备视角的实时监控雏形）。

当前目标：
- 能看到设备列表（在线/离线、last_seen、最新温度/气压/光照）
- 能实时接收并展示最新 telemetry（通过 `/ws/dashboard`）
- 能对单设备展示实时曲线（最近若干点）

当前状态：已完成与 Server/Hardware 的端到端联调；只要前端连对 `VITE_API_BASE`，即可看到设备与实时数据。

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

### 重要：远程访问时不要用 127.0.0.1

如果你在“另一台电脑/手机”通过公网访问云服务器的 `http://<server>:5173/`：

- 前端默认 `VITE_API_BASE=http://127.0.0.1:5000` 会指向**访问者自己的电脑**，不是云服务器。
- 表现就是页面顶部 `TypeError: Failed to fetch`、并且 `WS Disconnected`。

请把 `VITE_API_BASE` 改为云服务器的后端地址，例如：`http://8.134.151.27:5000`。

推荐做法：在本目录创建 `.env.local`（可参考 `.env.local.example`），然后重启 `npm run dev`。

> 注意：Vite 环境变量只在启动时注入，修改 `.env.local` 或环境变量后必须重启 dev server。

## 启动

在 `ESP32/iot_ai_monitor/web` 目录：

- `npm install`
- `npm run dev`

如果你需要让“其他电脑/手机”访问你这台机器/云服务器上的 5173：
- `npm run dev -- --host 0.0.0.0`
- 并确保安全组/防火墙放行 `5173`

浏览器访问：
- `http://127.0.0.1:5173/`

## 页面

- `/`：首页（监控 + 历史回放 + 配置参数框）
- `/device/:id`：设备详情页（信息/参数/配置下发 + TF/SD 卡管理）

说明：TF/SD 卡管理依赖设备固件支持 `sd_info/sd_list/sd_read_text/sd_delete/sd_clear_queue` 命令，并通过 server 的命令通道返回 `command_ack`。
