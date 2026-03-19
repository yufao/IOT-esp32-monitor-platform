# 桌面端（Electron + BLE）

目标：提供 BLE 直连、实时仪表盘、WiFi 配网、阈值配置、本地日志。

当前状态：已与 Server/Web/Hardware 完成“四方联调”。桌面端既能做 BLE 本地运维，也能通过 Server 的命令通道对在线设备做 TF/SD 管理。

## 启动方式
1. 安装依赖（Python）：
	- 进入 python 目录，安装 `bleak` 与 `websockets`
	- 命令：`python -m pip install -r requirements.txt`
2. 安装依赖（Electron）：
	- 命令：`npm install`
3. 启动：
	- 命令：`npm start`

## 说明
- Electron 会自动启动 BLE Bridge（Python）并通过 WebSocket 通信。
- 本地日志保存在 `desktop/python/logs/sensor_log.csv`。
- BLE 设备名默认 `SLS_ESP32`，可在硬件端配置修改。

## TF/SD 管理（通过 Server 命令通道）
桌面端主页面右上角新增 `TF/SD 管理` 按钮：点击后会打开一个独立的新页面（窗口），用于向 Server 下发 `sd_*` 命令并轮询回执。

使用步骤：
1. 确保 Flask Server 已启动，并且设备已连上 WiFi（让设备能从 Server 收到 command 并回 `cmd_ack`）。
2. 在 `TF/SD 管理` 页面填写：
	- `Server Base URL`：例如 `http://127.0.0.1:5000`
	- `API Key`：填 token 本体（页面会自动加 `Bearer` 前缀）
	- `Device ID`：与设备上报/注册一致的 device_id
3. 点击 `测试连接`（实际会发送 `sd_info` 并轮询 `/api/commands/status`）。
4. 常用命令：
	- `sd_info`：查看挂载/容量信息
	- `sd_list`：列目录（默认 `/sd/`）
	- `sd_read_text`：读取文本（可填 max_lines）
	- `sd_delete`：删除文件/目录（按设备端实现）
	- `sd_clear_queue`：清空 TF 缓存队列

说明：
- 桌面端页面通过主进程代理调用 Server 的 `/api/commands/send` 与 `/api/commands/status`，避免 `file://` 页面跨域限制。
