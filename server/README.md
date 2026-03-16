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

## 环境变量

- `SLS_HOST`：监听地址（默认 `0.0.0.0`）
- `SLS_PORT`：端口（默认 `5000`）
- `SLS_DEBUG`：是否调试（`1`/`0`）
- `SLS_API_KEYS`：逗号分隔的 api_key 列表（默认 `dev_key`）
- `SLS_CORS_ORIGINS`：REST 的 CORS 白名单（默认 `*`）
