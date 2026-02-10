# 桌面端（Electron + BLE）

目标：提供 BLE 直连、实时仪表盘、WiFi 配网、阈值配置、本地日志。

## 启动方式
1. 安装依赖（Python）：
	- 进入 python 目录，安装 `bleak` 与 `websockets`
2. 安装依赖（Electron）：
	- `npm install`
3. 启动：
	- `npm start`

## 说明
- Electron 会自动启动 BLE Bridge（Python）并通过 WebSocket 通信。
- 本地日志保存在 `desktop/python/logs/sensor_log.csv`。
