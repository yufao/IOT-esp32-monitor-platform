# ESP32-IoT-AI 智能监测平台（虚实结合版）

本目录为实战项目主目录，独立于原有学习/实验代码。目标：实现“ESP32实测+软件模拟”的智能监测平台，并支持网页端与桌面端双端管理。

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

## 快速开始（当前可用链路）
1. 硬件端：运行 `hardware/main.py`，按 KEY1 切换 BLE。
2. 桌面端：进入 `desktop` 目录执行 `npm start`。
3. BLE 连接成功后，可实时查看温度/气压/光敏数据。

## BLE 指令格式
WiFi 配网：
```json
{"type":"wifi","ssid":"YOUR_SSID","password":"YOUR_PASS"}
```
阈值设置：
```json
{"type":"threshold","temp_high":30,"temp_low":15}
```
