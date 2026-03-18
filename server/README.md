# 服务端（Flask）

此目录存放服务端核心逻辑：接收、存储、查询、预警、文档。

后续文件规划：
- app.py：Flask入口
- config.py：配置
- models.py：SQLite表结构
- routes/：路由模块
- services/：业务逻辑（预警、导出）
- requirements.txt：依赖

---

## 快速启动（Phase 1）

1) 进入项目子根目录：`ESP32/iot_ai_monitor/`

2) 安装依赖：
- `python -m venv .venv`
- Windows：`.\.venv\Scripts\Activate.ps1`
- `pip install -r server/requirements.txt`

3) 启动：
- `python -m server.app`

4) 探活：
- `GET http://127.0.0.1:5000/health`

## WebSocket 路由（Phase 1）

- `ws://<host>:5000/ws/telemetry`
	- 设备必须先发送 `{"type":"hello","device_id":"...","api_key":"..."}` 完成鉴权
	- 鉴权通过后才接受 `type=telemetry` 消息，并返回 `type=ack`
- `ws://<host>:5000/ws/dashboard`
	- Web 订阅端，连接后会收到 `snapshot`，之后接收 `telemetry` 与 `device_status` 广播
	- 也会收到控制面事件：`command_sent` / `command_ack`

## HTTP（备用上报通道）

当设备端 WebSocket 不可用时，可使用 HTTP 作为兜底：

- `POST http://<host>:5000/api/telemetry`
- Header：`Authorization: Bearer <api_key>`（与环境变量 `SLS_API_KEYS` 对齐）
- Body：`{ device_id, timestamp, environment, seq?, is_buffered? }`

## 命令下发（控制面 MVP）

- `POST http://<host>:5000/api/commands/send`
	- Header：`Authorization: Bearer <api_key>`（与环境变量 `SLS_API_KEYS` 对齐）
	- Body：`{ device_id, command }`
		- `command.type = set_threshold`：`{type,temp_high,temp_low}`
		- `command.type = set_sample_interval`：`{type,sample_interval_sec}`

设备回执：设备通过 `/ws/telemetry` 回传 `type=cmd_ack`，server 会广播 `command_ack` 到 dashboard。

命令状态查询（给 Desktop/脚本轮询回执用）：

- `GET http://<host>:5000/api/commands/status?cmd_id=<cmd_id>`
	- Header：`Authorization: Bearer <api_key>`
	- 返回：`status = pending|acked|unknown`，acked 时会带上 `ok/result/error/command`

## Telemetry 历史（SQLite）

Phase1 起将 telemetry 持久化到 SQLite，便于回放/曲线与排障：

- `GET http://<host>:5000/api/telemetry/history?device_id=<id>&since=<ts>&until=<ts>&limit=<n>`
	- `since/until`：Unix 秒（可选）
	- `limit`：默认 200，最大 2000

数据库文件：
- 默认：`server/data/sls.db`
- 可通过环境变量覆盖：`SLS_DB_PATH`

可选禁用：若暂时不希望落库/DB 未部署，可设置 `SLS_ENABLE_SQLITE=0`。
此时 `/api/telemetry/history` 会返回 503（`sqlite_disabled`），但实时链路（WS/dashboard/HTTP telemetry）仍可用。

## 环境变量

- `SLS_HOST`：监听地址（默认 `0.0.0.0`）
- `SLS_PORT`：端口（默认 `5000`）
- `SLS_DEBUG`：是否调试（`1`/`0`）
- `SLS_API_KEYS`：逗号分隔的 api_key 列表（默认 `dev_key`）
- `SLS_CORS_ORIGINS`：REST 的 CORS 白名单（默认 `*`）
- `SLS_DEVICE_OFFLINE_TTL_SEC`：离线判定阈值（秒，默认 `60`；主要用于 HTTP 兜底设备）
- `SLS_ENABLE_SQLITE`：是否启用 SQLite（`1`/`0`，默认 `1`）
- `SLS_COMMAND_STATUS_TTL_SEC`：命令状态在内存中保留的 TTL（秒，默认 `600`）
