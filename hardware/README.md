# 硬件端（ESP32 / MicroPython）

此目录存放硬件端核心逻辑：采集、缓存、上传、异常检测、蓝牙备用、LED/蜂鸣器预警。

后续文件规划：
- hw_config.py：引脚与常量配置（不提交仓库）
- hw_config.sample.py：配置模板（提交仓库）
- hw_runtime_config.py：运行时配置读写
- runtime_config.json：设备运行时生成
- hw_sensors.py：BMP280 + 光敏采集与标准化
- hw_wifi_uploader.py：WiFi连接与HTTP上传
- hw_ble_server.py：BLE GATT 服务
- main.py：主入口（信道切换、上报、BLE指令）
