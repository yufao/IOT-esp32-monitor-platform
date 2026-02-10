# 硬件端（ESP32 / MicroPython）

此目录存放硬件端核心逻辑：采集、缓存、上传、异常检测、蓝牙备用、LED/蜂鸣器预警。

后续文件规划：
- hw_config.py：引脚与常量配置
- hw_sensors.py：DHT11/ADC采集与标准化
- hw_storage.py：SD卡缓存
- hw_wifi.py：WiFi连接与HTTP上传
- hw_ai.py：轻量异常检测
- hw_alert.py：LED/蜂鸣器预警
- main.py：主入口
