"""Smart Lab Sentinel 主控入口（ESP32）。"""

import time  # 时间相关
import sys  # 导入路径控制
import os  # 路径工具
import gc  # 内存监控
import machine  # GPIO 与系统接口

try:
	import network  # WiFi 控制
except ImportError:
	network = None

# ---- 导入兜底：处理运行目录漂移 ----
try:
	from hw_config import DEVICE_ID, SERVER_URL, SAMPLE_INTERVAL_SEC, KEY1_PIN
except ImportError:
	_fallback_paths = [
		"/iot_ai_monitor/hardware",
		"/iot_ai_monitor",
		"/",
	]
	for _p in _fallback_paths:
		if _p not in sys.path:
			sys.path.append(_p)
	from hw_config import DEVICE_ID, SERVER_URL, SAMPLE_INTERVAL_SEC, KEY1_PIN

try:
	from hw_sensors import SensorManager
except ImportError:
	# Re-run fallback in case sensor module lives in another path
	from hw_sensors import SensorManager

try:
	from hw_wifi_uploader import WifiUploader
except ImportError:
	from hw_wifi_uploader import WifiUploader

try:
	from hw_ble_server import BleUartServer
except ImportError:
	BleUartServer = None


# ---- 信道切换（KEY1）----
# 按下切换 WIFI <-> BLE
KEY1 = machine.Pin(KEY1_PIN, machine.Pin.IN, machine.Pin.PULL_UP)  # 输入上拉
KEY_DEBOUNCE_MS = 200  # 按键防抖时间


# ---- 运行参数 ----
SEND_INTERVAL_MS = max(500, int(SAMPLE_INTERVAL_SEC * 1000))  # 上报间隔
RETRY_QUEUE_MAX = 20  # 失败缓存上限
MEM_LOG_INTERVAL_MS = 10000  # 内存日志间隔
GC_INTERVAL_MS = 30000  # 垃圾回收周期（防碎片）
CONNECT_RETRY_MS = 5000  # WiFi 非阻塞重连间隔
ENQUEUE_COOLDOWN_MS = 3000  # 断网入队冷却时间

def toggle_channel(current):
	"""在 WIFI 与 BLE 之间切换。"""
	return "BLE" if current == "WIFI" else "WIFI"


def enqueue(queue, item):
	"""向失败队列追加数据，并限制长度。"""
	if len(queue) >= RETRY_QUEUE_MAX:
		queue.pop(0)  # 丢弃最旧
	queue.append(item)  # 追加最新


def set_wifi_enabled(enable):
	"""按需启用/禁用 WiFi，避免与 BLE 干扰。"""
	if not network:
		return
	wlan = network.WLAN(network.STA_IF)
	try:
		wlan.active(True if enable else False)
	except Exception:
		pass


def main():
	"""主循环：采集数据并按信道上报。"""
	channel = "WIFI"  # 默认 WIFI
	print("channel:", channel)  # 打印当前模式
	set_wifi_enabled(True)  # 默认开启 WiFi

	sensor = SensorManager()  # 传感器管理器
	uploader = WifiUploader(url=SERVER_URL) if channel == "WIFI" else None  # WiFi 上报器
	ble = BleUartServer() if channel == "BLE" and BleUartServer else None  # BLE 服务
	if ble:
		print("ble ready:", ble.is_ready())  # 打印 BLE 可用状态

	retry_queue = []  # 失败数据缓存
	last_send = time.ticks_ms()  # 上次上报时间
	last_mem = time.ticks_ms()  # 上次内存日志时间
	last_key_change = time.ticks_ms()  # 防抖计时
	last_key_state = KEY1.value()  # 初始按键状态
	last_connect_try = time.ticks_ms()  # 上次连接尝试时间
	last_gc = time.ticks_ms()  # 上次 GC 时间
	last_enqueue_fail = time.ticks_ms()  # 上次入队失败时间

	# 启动阶段只触发一次非阻塞连接
	if channel == "WIFI" and uploader:
		uploader.connect_step(time.ticks_ms())  # 非阻塞连接

	while True:
		now = time.ticks_ms()  # 当前时间

		# 检测按键边沿并切换信道
		key_state = KEY1.value()
		if key_state != last_key_state:
			if time.ticks_diff(now, last_key_change) > KEY_DEBOUNCE_MS:
				last_key_change = now
				last_key_state = key_state
				if key_state == 0:
					channel = toggle_channel(channel)
					print("channel switched:", channel)
					if channel == "WIFI":
						set_wifi_enabled(True)
						uploader = WifiUploader(url=SERVER_URL)
						uploader.connect_step(now)  # 非阻塞连接
						ble = None
					else:
						set_wifi_enabled(False)
						uploader = None
						ble = BleUartServer() if BleUartServer else None
						if ble:
							print("ble ready:", ble.is_ready())  # 打印 BLE 可用状态

		# WiFi 模式下：定时尝试重连（非阻塞）
		if channel == "WIFI" and uploader:
			if time.ticks_diff(now, last_connect_try) >= CONNECT_RETRY_MS:
				uploader.connect_step(now)
				last_connect_try = now

		# 持续采集数据（传感器模块内部非阻塞）
		payload = sensor.collect_data(now)  # 构建数据包

		# 周期上报
		if time.ticks_diff(now, last_send) >= SEND_INTERVAL_MS:
			if channel == "WIFI" and uploader:
				ok, info = (False, "wifi-disconnected")
				# 优先重发队列
				if retry_queue:
					ok, info = uploader.post_json(retry_queue[0])  # 发送最旧
					if ok:
						retry_queue.pop(0)  # 成功则移除
				else:
					ok, info = uploader.post_json(payload)  # 发送当前

				# 断网时入队节流，避免内存膨胀
				if not ok:
					if info != "wifi-disconnected" or time.ticks_diff(now, last_enqueue_fail) >= ENQUEUE_COOLDOWN_MS:
						enqueue(retry_queue, payload)
						last_enqueue_fail = now

				print("send:", "ok" if ok else "fail", info)  # 上报状态
			else:
				# BLE 模式：发送数据到桌面端
				if ble and ble.is_ready():
					ble.send_json(payload)
				else:
					# BLE 不可用时输出摘要
					env = payload.get("environment", {})
					bmp = env.get("bmp280", {})
					light = env.get("light", {})
					print("ble mode: temp=", bmp.get("temp"), "press=", bmp.get("pressure"), "light%=", light.get("percent"))

			last_send = now  # 更新上报时间

		# 内存监控
		if time.ticks_diff(now, last_mem) >= MEM_LOG_INTERVAL_MS:
			print("mem_free:", gc.mem_free())  # 打印可用内存
			last_mem = now  # 更新日志时间

		# 定时 GC，减少碎片
		if time.ticks_diff(now, last_gc) >= GC_INTERVAL_MS:
			gc.collect()
			last_gc = now

		# 喂狗
		if hasattr(sensor, "feed_watchdog"):
			sensor.feed_watchdog()  # 喂狗

		time.sleep_ms(10)  # 让出 CPU


if __name__ == "__main__":
	main()  # 入口
