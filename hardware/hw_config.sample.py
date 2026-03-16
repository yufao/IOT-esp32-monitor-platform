# -*- coding: utf-8 -*-
"""
硬件端配置（引脚与常量）
说明：本文件只负责“给各模块分配引脚与参数”，不做具体硬件操作。
"""

# ============ 设备基础信息 ============
DEVICE_ID="ESP23_001"	# 设备唯一标识（后续上报用）


# ============ 功能开关（按阶段启用）===========
USE_DHT11 = False  # 暂不使用 DHT11
USE_BMP280 = True  # 启用 BMP280（温度/气压）
USE_LIGHT_SENSOR = True  # 启用光敏
USE_THERMISTOR = False  # 暂不使用热敏

# ============ DHT11 温湿度传感器引脚（预留）===========
# DHT11 数据线连接到 ESP32 的 GPIO 号（目前不使用，预留扩展）
# DHT11_PIN = 4  # 目前 GPIO4 空闲

# ============ I2C 总线（BMP280 / MPU6050 / LCD1602 可共享）===========
I2C_ID = 0
I2C_FREQ = 400000
I2C_SDA_PIN = 21
I2C_SCL_PIN = 22

# ============ ADC 模拟输入（ADC1，避免 WiFi 冲突）===========
# ADC1 可用 GPIO: 32~39
LIGHT_ADC_PIN = 34  # 光敏电阻（后续启用）
THERMISTOR_ADC_PIN = 35  # 热敏电阻（后续启用）

# 兼容旧代码（如仍使用单通道 ADC）
ADC_PIN = 34

# ============ SD 卡 SPI 接口引脚 ============
# 这里是常见 SPI 引脚配置
SD_SCK_PIN = 18  # SPI 时钟
SD_MOSI_PIN = 23  # SPI 主机输出
SD_MISO_PIN = 19  # SPI 主机输入
SD_CS_PIN = 5  # SPI 片选


# ============ WiFi 配置 ============
WIFI_SSID = "YOUR_SSID"  # WiFi 名称
WIFI_PASSWORD = "YOUR_PASSWORD"  # WiFi 密码

# ============ 服务端地址 ============
SERVER_URL = "http://httpbin.org/post"  # 后续上传用，先占位

# ============ WebSocket 直连（路线A）===========
# ESP32 直连服务端 WebSocket（telemetry 通道）
SERVER_WS_URL = "ws://127.0.0.1:5000/ws/telemetry"

# 设备鉴权（比赛/MVP 简化版）：与服务端环境变量 SLS_API_KEYS 对齐
API_KEY = "dev_key"

# 固件版本（可手动维护；后续 OTA 会用到）
FIRMWARE_VERSION = "0.1.0"


# ============ 采样与上报频率 ============
SAMPLE_INTERVAL_SEC = 1  # 采样间隔（秒）

# ============ 预警阈值（后续模块会用）===========
TEMP_ALERT_C = 30  # 温度预警阈值（摄氏度）

# ============ 其他可选配置 ============
TIMEZONE_OFFSET = 8  # 时区偏移（中国 = 8）  # 时区偏移（中国 = 8）

# ============ BLE 配置 ============
BLE_DEVICE_NAME = "SLS_ESP32"
BLE_ADV_INTERVAL_MS = 300

# ============ KEY1 按键配置 ============
KEY1_PIN = 14  # 目前 KEY1 接到 GPIO14

# ============ KEY2 按键配置（测试阶段：缓存开关）===========
# 注意：部分 ESP32 模组 GPIO6~11 可能连接板载 Flash，不一定可用。
# 如出现异常，可改为其他空闲 GPIO。
KEY2_PIN = 27  # KEY2 绑定 GPIO27（按下=启用失败重试缓存）
  