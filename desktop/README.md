# 桌面端（Electron + BLE）

目标：提供 BLE 直连、实时仪表盘、WiFi 配网、阈值配置、本地日志。

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
