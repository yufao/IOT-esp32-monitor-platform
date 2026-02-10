import machine
import dht
import time

# 确认这个引脚号与你实际接线一致！
DHT_PIN = 4  

# 尝试内部上拉（如果有外部电阻，PULL_UP 可去掉）
pin = machine.Pin(DHT_PIN, machine.Pin.IN, machine.Pin.PULL_UP)
sensor = dht.DHT11(pin)

print("测试 DHT11，请等待...")
time.sleep(2)  # 上电稳定

try:
    sensor.measure()
    print(f"成功！温度: {sensor.temperature()}°C, 湿度: {sensor.humidity()}%")
except Exception as e:
    print(f"失败: {e}")
    print("请检查：1.是否接了上拉电阻 2.引脚号是否正确 3.接线是否松动")