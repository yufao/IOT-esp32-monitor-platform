import time
import machine
import sys
import os

# 兼容不同运行目录：确保能找到 hw_config
try:
    from hw_config import (
        DEVICE_ID,
        USE_BMP280,
        USE_LIGHT_SENSOR,
        I2C_ID,
        I2C_FREQ,
        I2C_SDA_PIN,
        I2C_SCL_PIN,
        LIGHT_ADC_PIN,
    )
except ImportError:
    # 常见部署路径兜底（设备可能自动切回根目录）
    fallback_paths = [
        "/iot_ai_monitor/hardware",
        "/iot_ai_monitor",
        "/",
    ]
    for p in fallback_paths:
        if p not in sys.path:
            sys.path.append(p)
    from hw_config import (
        DEVICE_ID,
        USE_BMP280,
        USE_LIGHT_SENSOR,
        I2C_ID,
        I2C_FREQ,
        I2C_SDA_PIN,
        I2C_SCL_PIN,
        LIGHT_ADC_PIN,
    )

# ============ 高级配置 ============
CONFIG = {
    "read_interval_ms": 2000,          # 主输出间隔（毫秒）
    "adc_samples": 10,                 # ADC 采样次数（均值滤波）
    "adc_sample_interval_ms": 5,       # ADC 单次采样间隔（毫秒）
    "watchdog_timeout": 10000          # 看门狗 10 秒
}


# ============ BMP280 轻量驱动（无外部依赖）===========
class BMP280Simple:
    def __init__(self, i2c, addr):
        self.i2c = i2c
        self.addr = addr
        self._load_calibration()
        self._configure()

    def _read_u16(self, reg):
        data = self.i2c.readfrom_mem(self.addr, reg, 2)
        return data[0] | (data[1] << 8)

    def _read_s16(self, reg):
        val = self._read_u16(reg)
        return val - 65536 if val > 32767 else val

    def _load_calibration(self):
        self.dig_T1 = self._read_u16(0x88)
        self.dig_T2 = self._read_s16(0x8A)
        self.dig_T3 = self._read_s16(0x8C)
        self.dig_P1 = self._read_u16(0x8E)
        self.dig_P2 = self._read_s16(0x90)
        self.dig_P3 = self._read_s16(0x92)
        self.dig_P4 = self._read_s16(0x94)
        self.dig_P5 = self._read_s16(0x96)
        self.dig_P6 = self._read_s16(0x98)
        self.dig_P7 = self._read_s16(0x9A)
        self.dig_P8 = self._read_s16(0x9C)
        self.dig_P9 = self._read_s16(0x9E)

    def _configure(self):
        # 温度/气压过采样 x1，正常模式
        self.i2c.writeto_mem(self.addr, 0xF4, bytes([0x27]))
        # 待机 1000ms，滤波 x4
        self.i2c.writeto_mem(self.addr, 0xF5, bytes([0xA0]))

    def _read_raw(self):
        data = self.i2c.readfrom_mem(self.addr, 0xF7, 6)
        adc_p = (data[0] << 12) | (data[1] << 4) | (data[2] >> 4)
        adc_t = (data[3] << 12) | (data[4] << 4) | (data[5] >> 4)
        return adc_t, adc_p

    def read_compensated(self):
        adc_t, adc_p = self._read_raw()

        var1 = (((adc_t >> 3) - (self.dig_T1 << 1)) * self.dig_T2) >> 11
        var2 = (((((adc_t >> 4) - self.dig_T1) * ((adc_t >> 4) - self.dig_T1)) >> 12) * self.dig_T3) >> 14
        t_fine = var1 + var2
        temp_c = (t_fine * 5 + 128) >> 8

        var1 = t_fine - 128000
        var2 = var1 * var1 * self.dig_P6
        var2 = var2 + ((var1 * self.dig_P5) << 17)
        var2 = var2 + (self.dig_P4 << 35)
        var1 = ((var1 * var1 * self.dig_P3) >> 8) + ((var1 * self.dig_P2) << 12)
        var1 = (((1 << 47) + var1) * self.dig_P1) >> 33

        if var1 == 0:
            pressure = 0
        else:
            p = 1048576 - adc_p
            p = (((p << 31) - var2) * 3125) // var1
            var1 = (self.dig_P9 * (p >> 13) * (p >> 13)) >> 25
            var2 = (self.dig_P8 * p) >> 19
            pressure = ((p + var1 + var2) >> 8) + (self.dig_P7 << 4)

        return temp_c / 100.0, pressure / 25600.0

# ============ 硬件初始化（带看门狗保护）===========
class SensorManager:
    def __init__(self):
        # 看门狗：防止死循环（仅 ESP32）
        try:
            self.wdt = machine.WDT(timeout=CONFIG["watchdog_timeout"])
        except:
            self.wdt = None
            
        # I2C 初始化（BMP280）
        self.i2c = machine.I2C(
            I2C_ID,
            scl=machine.Pin(I2C_SCL_PIN),
            sda=machine.Pin(I2C_SDA_PIN),
            freq=I2C_FREQ,
        )
        self._bmp280 = None
        self._bmp280_cache = {"temp": None, "pressure": None, "status": "init"}

        if USE_BMP280:
            self._bmp280 = self._init_bmp280()

        # 光敏 ADC 初始化（带滤波缓冲区）
        self._light_adc = None
        if USE_LIGHT_SENSOR:
            self._light_adc = machine.ADC(machine.Pin(LIGHT_ADC_PIN))
            self._light_adc.atten(machine.ADC.ATTN_11DB)
            self._light_adc.width(machine.ADC.WIDTH_12BIT)
        self._adc_samples = []  # ADC 采样缓冲区
        self._next_adc_sample = 0  # 下次采样时间戳
        self._light_cache = {"raw": None, "voltage": None, "percent": None}

    def _init_bmp280(self):
        """初始化 BMP280，自动识别地址。"""
        try:
            addrs = self.i2c.scan()
            for addr in (0x76, 0x77):
                if addr in addrs:
                    return BMP280Simple(self.i2c, addr)
        except Exception:
            return None
        return None
        
    def read_bmp280(self):
        """读取 BMP280，失败则返回缓存。"""
        if not USE_BMP280 or self._bmp280 is None:
            self._bmp280_cache = {"temp": None, "pressure": None, "status": "unavailable"}
            return self._bmp280_cache

        try:
            temp_c, pressure_hpa = self._bmp280.read_compensated()
            self._bmp280_cache = {
                "temp": temp_c,
                "pressure": pressure_hpa,
                "status": "ok",
            }
        except Exception as exc:
            self._bmp280_cache = {
                "temp": None,
                "pressure": None,
                "status": f"error: {exc}",
            }

        return self._bmp280_cache
                
    def read_light_filtered(self, now_ms):
        """非阻塞式光敏采样与均值滤波。"""
        if not USE_LIGHT_SENSOR or self._light_adc is None:
            self._light_cache = {"raw": None, "voltage": None, "percent": None}
            return self._light_cache

        if time.ticks_diff(now_ms, self._next_adc_sample) >= 0:
            self._adc_samples.append(self._light_adc.read())
            self._next_adc_sample = time.ticks_add(now_ms, CONFIG["adc_sample_interval_ms"])

        if len(self._adc_samples) >= CONFIG["adc_samples"]:
            samples = list(self._adc_samples)
            self._adc_samples = []
            samples.sort()
            if len(samples) > 4:
                filtered = samples[2:-2]
            else:
                filtered = samples
            avg = sum(filtered) // len(filtered)
            self._light_cache = {
                "raw": avg,
                "voltage": round(avg * 3.3 / 4095, 2),
                "percent": int((avg / 4095) * 100)
            }

        return self._light_cache
        
    def feed_watchdog(self):
        """喂狗"""
        if self.wdt:
            self.wdt.feed()
            
    def collect_data(self, now_ms):
        """非阻塞式数据采集。"""
        bmp_data = self.read_bmp280()
        light_data = self.read_light_filtered(now_ms)

        return {
            "device_id": DEVICE_ID,
            "timestamp": time.time(),
            "environment": {
                "bmp280": bmp_data,
                "light": light_data,
            },
        }

# ============ 主程序（异步非阻塞架构）===========
def main():
    print("高级传感器采集系统启动...")
    sensor = SensorManager()
    
    last_read = time.ticks_ms()
    
    while True:
        current = time.ticks_ms()
        
        # 非阻塞式定时（精确控制间隔，不占用 CPU）
        if time.ticks_diff(current, last_read) >= CONFIG["read_interval_ms"]:
            data = sensor.collect_data(current)
            print(data)
            last_read = current
        else:
            sensor.collect_data(current)
            
        # 喂狗（必须在看门狗超时前执行）
        sensor.feed_watchdog()
        
        # 短暂休眠让出 CPU（降低功耗）
        time.sleep_ms(5)

if __name__ == "__main__":
    main()