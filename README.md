# ESP32-IoT-AI 智能监测平台

Smart Lab Sentinel：一个面向实验室/宿舍场景的多模态监测系统，强调“边缘采集 + 本地事件 + 双端管理”。
当前已实现：BLE 桌面端实时仪表盘、WiFi 配网、BMP280 + 光敏采集、稳定的非阻塞主控框架。

## 核心特性
- 多模态传感：BMP280 温度/气压 + 光敏
- 双通道：WiFi 上报 + BLE 本地直连
- 桌面端：实时仪表盘、WiFi 配网、阈值设置、本地日志
- 稳定性：非阻塞调度、失败队列、定时 GC

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

## 当前状态
- ESP32：BMP280 + 光敏采集已稳定
- BLE：桌面端实时显示已打通
- WiFi：支持 BLE 配网并尝试自动连接
- Web/Server：待完善

## BLE 指令格式
WiFi 配网：
```json
{"type":"wifi","ssid":"YOUR_SSID","password":"YOUR_PASS"}
```
阈值设置：
```json
{"type":"threshold","temp_high":30,"temp_low":15}
```
