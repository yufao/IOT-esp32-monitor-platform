"""Smart Lab Sentinel 主控入口（ESP32）。"""

import time  # 时间相关
import sys  # 导入路径控制
import os  # 路径工具
import gc  # 内存监控
import machine  # GPIO 与系统接口
import json  # WS 命令解析

try:
	import network  # WiFi 控制
except ImportError:
	network = None

# ---- 导入兜底：处理运行目录漂移 ----
try:
	from hw_config import DEVICE_ID, SERVER_URL, SAMPLE_INTERVAL_SEC, KEY1_PIN, KEY2_PIN, WIFI_SSID, WIFI_PASSWORD
except ImportError:
	_fallback_paths = [
		"/iot_ai_monitor/hardware",
		"/iot_ai_monitor",
		"/",
	]
	for _p in _fallback_paths:
		if _p not in sys.path:
			sys.path.append(_p)
	try:
		from hw_config import DEVICE_ID, SERVER_URL, SAMPLE_INTERVAL_SEC, KEY1_PIN, KEY2_PIN, WIFI_SSID, WIFI_PASSWORD
	except ImportError:
		# 向后兼容：旧版 hw_config 没有 KEY2_PIN
		from hw_config import DEVICE_ID, SERVER_URL, SAMPLE_INTERVAL_SEC, KEY1_PIN, WIFI_SSID, WIFI_PASSWORD
		KEY2_PIN = 27

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
	from hw_ws_client import WsTelemetryClient
except ImportError:
	WsTelemetryClient = None

try:
	from hw_ble_server import BleUartServer
except ImportError:
	BleUartServer = None

try:
	from hw_runtime_config import load_config, save_config
except ImportError:
	load_config = None
	save_config = None

try:
	from hw_sd_card import SDCardManager
except ImportError:
	SDCardManager=None

try:
	from hw_sd_queue import SdTelemetryQueue
except ImportError:
	SdTelemetryQueue = None

# ---- 信道切换（KEY1）----
# 按下切换 WIFI <-> BLE
KEY1 = machine.Pin(KEY1_PIN, machine.Pin.IN, machine.Pin.PULL_UP)  # 输入上拉
# ---- 缓存开关（KEY2）----
# 按下切换“失败重试缓存”开关（默认关闭）。
# 开启后：失败上报会入队（优先 TF 队列，失败再退回内存），并按 2s/10 条节奏补发。
KEY2 = machine.Pin(KEY2_PIN, machine.Pin.IN, machine.Pin.PULL_UP)
KEY_DEBOUNCE_MS = 200  # 按键防抖时间


# ---- 运行参数 ----
SEND_INTERVAL_MS = max(500, int(SAMPLE_INTERVAL_SEC * 1000))  # 上报间隔
RETRY_QUEUE_MAX = 20  # 失败缓存上限
MEM_LOG_INTERVAL_MS = 10000  # 内存日志间隔
GC_INTERVAL_MS = 30000  # 垃圾回收周期（防碎片）
CONNECT_RETRY_MS = 5000  # WiFi 非阻塞重连间隔
ENQUEUE_COOLDOWN_MS = 3000  # 断网入队冷却时间

# TF 持久化队列：补发节奏
SD_FLUSH_INTERVAL_MS = 2000  # 每 2s 尝试补发
SD_FLUSH_MAX_ITEMS = 10  # 每次最多补发 10 条
SD_QUEUE_MAX_BYTES = 2 * 1024 * 1024 * 1024  # 2GB

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

	cache_enabled = False  # 失败重试缓存开关（默认关闭）
	print("cache_enabled:", cache_enabled)

	send_interval_ms = SEND_INTERVAL_MS

	# SD卡挂载
	sd=None
	sd_queue = None
	if SDCardManager:
		# 启动延迟，降低瞬时电流导致的 brownout 风险
		time.sleep_ms(1200)
		sd = SDCardManager()
		ok,info=sd.mount()
		print("sd mount:", "ok" if ok else "fail", info)
		if ok:
			sd.log_line("runtime.log","boot ok")
			# 初始化 TF 持久化队列（仅当模块存在）
			if SdTelemetryQueue:
				try:
					sd_queue = SdTelemetryQueue(mount_point=sd.mount_point, max_total_bytes=SD_QUEUE_MAX_BYTES)
				except Exception as _e:
					sd_queue = None

	# 读取运行时配置（WiFi/阈值）
	runtime_cfg = load_config() if load_config else {"wifi": {}, "threshold": {}}
	# 运行时采样周期（可被命令下发修改）
	try:
		_cfg_interval = runtime_cfg.get("sample", {}).get("interval_sec")
		if _cfg_interval is not None:
			send_interval_ms = max(500, int(float(_cfg_interval) * 1000))
	except Exception:
		pass
	ssid = (runtime_cfg.get("wifi", {}).get("ssid") or WIFI_SSID or "").strip()
	password = (runtime_cfg.get("wifi", {}).get("password") or WIFI_PASSWORD or "").strip()
	print("wifi ssid:", ssid, "pwd:", "***" if password else "(empty)")

	sensor = SensorManager()  # 传感器管理器
	uploader = WifiUploader(ssid=ssid, password=password, url=SERVER_URL) if channel == "WIFI" else None  # HTTP 备用上报

	# WebSocket 直连（优先使用；如配置缺失或模块不可用则跳过）
	ws_client = None
	seq = 0
	if channel == "WIFI" and WsTelemetryClient:
		try:
			from hw_config import SERVER_WS_URL, API_KEY, FIRMWARE_VERSION
		except Exception:
			SERVER_WS_URL, API_KEY, FIRMWARE_VERSION = None, None, None
		if SERVER_WS_URL and str(SERVER_WS_URL).startswith("ws") and API_KEY:
			hello = {
				"type": "hello",
				"device_id": DEVICE_ID,
				"api_key": API_KEY,
				"firmware_version": FIRMWARE_VERSION or "0.0.0",
				"protocol": 1,
				"capabilities": {"bmp280": True, "light": True},
			}
			ws_client = WsTelemetryClient(url=SERVER_WS_URL, hello_payload=hello, connect_timeout_s=2, io_timeout_s=0.3)
	ble = BleUartServer() if channel == "BLE" and BleUartServer else None  # BLE 服务
	if ble:
		print("ble ready:", ble.is_ready())  # 打印 BLE 可用状态

	retry_queue = []  # 失败数据缓存
	last_send = time.ticks_ms()  # 上次上报时间
	last_mem = time.ticks_ms()  # 上次内存日志时间
	last_status_log = time.ticks_ms()  # 上次网络状态日志时间
	last_send_log = time.ticks_ms()  # 上次 send 结果日志时间
	last_loop_log = time.ticks_ms()  # 上次 loop 心跳日志时间
	last_send_state = None
	send_ok_cnt = 0
	send_fail_cnt = 0
	wifi_disc_cnt = 0
	last_key_change = time.ticks_ms()  # 防抖计时
	last_key_state = KEY1.value()  # 初始按键状态
	last_key2_change = time.ticks_ms()
	last_key2_state = KEY2.value()
	last_connect_try = time.ticks_ms()  # 上次连接尝试时间
	last_ws_connect_try = time.ticks_ms()
	last_gc = time.ticks_ms()  # 上次 GC 时间
	last_enqueue_fail = time.ticks_ms()  # 上次入队失败时间
	last_sd_flush = time.ticks_ms()  # 上次 TF 队列补发时间
	last_ble_report = time.ticks_ms()  # BLE 状态输出时间
	last_sd_log = time.ticks_ms()	#上次挂载的时间

	# 启动阶段只触发一次非阻塞连接
	if channel == "WIFI" and uploader:
		uploader.connect_step(time.ticks_ms())  # 非阻塞连接
	if channel == "WIFI" and ws_client:
		ws_client.connect_step(time.ticks_ms())

	while True:
		now = time.ticks_ms()  # 当前时间

		# loop 心跳（节流，避免串口 print 堵塞）
		if time.ticks_diff(now, last_loop_log) >= 10000:
			try:
				print("loop alive, ms:", now)
			except Exception:
				pass
			last_loop_log = now

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
						uploader = WifiUploader(ssid=ssid, password=password, url=SERVER_URL)
						uploader.connect_step(now)  # 非阻塞连接
						# 切回 WIFI 时重新初始化 WS 客户端（如果配置可用）
						ws_client = None
						if WsTelemetryClient:
							try:
								from hw_config import SERVER_WS_URL, API_KEY, FIRMWARE_VERSION
							except Exception:
								SERVER_WS_URL, API_KEY, FIRMWARE_VERSION = None, None, None
							if SERVER_WS_URL and str(SERVER_WS_URL).startswith("ws") and API_KEY:
								hello = {
									"type": "hello",
									"device_id": DEVICE_ID,
									"api_key": API_KEY,
									"firmware_version": FIRMWARE_VERSION or "0.0.0",
									"protocol": 1,
									"capabilities": {"bmp280": True, "light": True},
								}
								ws_client = WsTelemetryClient(url=SERVER_WS_URL, hello_payload=hello)
						ble = None
					else:
						set_wifi_enabled(False)
						uploader = None
						ws_client = None
						ble = BleUartServer() if BleUartServer else None
						if ble:
							print("ble ready:", ble.is_ready())  # 打印 BLE 可用状态

		# KEY2：切换失败重试缓存开关（失败上报入队/补发）
		key2_state = KEY2.value()
		if key2_state != last_key2_state:
			if time.ticks_diff(now, last_key2_change) > KEY_DEBOUNCE_MS:
				last_key2_change = now
				last_key2_state = key2_state
				if key2_state == 0:
					cache_enabled = not cache_enabled
					print("cache_enabled switched:", cache_enabled)

		# BLE 指令处理（WiFi 配网 / 阈值设置）
		if channel == "BLE" and ble and ble.is_ready():
			cmd = ble.pop_last_cmd()
			if isinstance(cmd, dict):
				print("ble cmd:", cmd)
				cmd_type = cmd.get("type")
				if cmd_type == "wifi":
					ssid = cmd.get("ssid", "")
					password = cmd.get("password", "")
					runtime_cfg["wifi"] = {"ssid": ssid, "password": password}
					if save_config:
						save_config(runtime_cfg)
					print("wifi updated via ble:", ssid, "pwd:", "***" if password else "(empty)")
					# 立刻切回 WiFi 尝试连接
					channel = "WIFI"
					set_wifi_enabled(True)
					uploader = WifiUploader(ssid=ssid, password=password, url=SERVER_URL)
					uploader.connect_step(now)
					ble = None
					# 也初始化 WS（如果配置可用）
					ws_client = None
					if WsTelemetryClient:
						try:
							from hw_config import SERVER_WS_URL, API_KEY, FIRMWARE_VERSION
						except Exception:
							SERVER_WS_URL, API_KEY, FIRMWARE_VERSION = None, None, None
						if SERVER_WS_URL and str(SERVER_WS_URL).startswith("ws") and API_KEY:
							hello = {
								"type": "hello",
								"device_id": DEVICE_ID,
								"api_key": API_KEY,
								"firmware_version": FIRMWARE_VERSION or "0.0.0",
								"protocol": 1,
								"capabilities": {"bmp280": True, "light": True},
							}
							ws_client = WsTelemetryClient(url=SERVER_WS_URL, hello_payload=hello)
				elif cmd_type == "threshold":
					try:
						high = float(cmd.get("temp_high"))
						low = float(cmd.get("temp_low"))
					except Exception:
						high, low = None, None
					if high is not None and low is not None:
						runtime_cfg["threshold"] = {"temp_high": high, "temp_low": low}
						if save_config:
							save_config(runtime_cfg)
						print("threshold updated via ble")

		# WiFi 模式下：定时尝试重连（非阻塞）
		if channel == "WIFI" and uploader:
			if time.ticks_diff(now, last_connect_try) >= CONNECT_RETRY_MS:
				_t0 = time.ticks_ms()
				try:
					uploader.connect_step(now)
				except Exception as _e:
					try:
						print("wifi connect_step exc:", _e)
					except Exception:
						pass
				_dt = time.ticks_diff(time.ticks_ms(), _t0)
				if _dt > 300:
					try:
						print("wifi connect_step slow(ms):", _dt)
					except Exception:
						pass
				last_connect_try = now
		if channel == "WIFI" and ws_client:
			# 只有 WiFi 真正连上（拿到 IP）才尝试 WS 握手，避免在 CONNECTING 状态下卡死
			_ws_should_try = False
			try:
				_ws_should_try = bool(uploader and uploader.is_connected())
			except Exception:
				_ws_should_try = False
			# WS 需要独立重连节奏，否则会被 uploader 的 last_connect_try“饿死”
			if _ws_should_try and time.ticks_diff(now, last_ws_connect_try) >= CONNECT_RETRY_MS:
				_t0 = time.ticks_ms()
				try:
					ws_client.connect_step(now)
				except Exception as _e:
					try:
						print("ws connect_step exc:", _e)
					except Exception:
						pass
				_dt = time.ticks_diff(time.ticks_ms(), _t0)
				if _dt > 300:
					try:
						print("ws connect_step slow(ms):", _dt)
					except Exception:
						pass
				last_ws_connect_try = now

		# 网络状态打印（节流）
		if channel == "WIFI" and time.ticks_diff(now, last_status_log) >= 5000:
			try:
				if uploader and getattr(uploader, "wlan", None):
					w = uploader.wlan
					st = None
					try:
						st = w.status()
					except Exception:
						st = None
					print("wifi:", "connected" if w.isconnected() else "down", "status:", st)
					if w.isconnected():
						try:
							print("ifconfig:", w.ifconfig())
						except Exception:
							pass
			except Exception:
				pass
			try:
				if ws_client:
					st = "connected" if ws_client.is_connected() else "down"
					snap = None
					try:
						snap = ws_client.debug_snapshot() if hasattr(ws_client, "debug_snapshot") else None
					except Exception:
						snap = None
					if snap and (not ws_client.is_connected()):
						print("ws:", st, "lib:", snap.get("lib"), "err:", snap.get("last_error"))
					else:
						print("ws:", st)
				else:
					print("ws:", "disabled")
			except Exception:
				pass
			last_status_log = now

		# 持续采集数据（调试隔离：WiFi 未连上时，尽量不碰 I2C/ADC，先把 WDT 根因缩小范围）
		wifi_connected = False
		try:
			if channel == "WIFI" and uploader and uploader.is_connected():
				wifi_connected = True
		except Exception:
			wifi_connected = False

		if wifi_connected:
			_t0 = time.ticks_ms()
			payload = sensor.collect_data(now)  # 构建数据包
			_dt = time.ticks_diff(time.ticks_ms(), _t0)
			if _dt > 200:
				try:
					print("collect_data slow(ms):", _dt)
				except Exception:
					pass
		else:
			# WiFi 未连上：只生成最小 payload，避免 I2C/ADC 偶发卡死
			payload = {
				"device_id": DEVICE_ID,
				"timestamp": time.time(),
				"environment": {},
			}

		# 周期上报
		if time.ticks_diff(now, last_send) >= send_interval_ms:
			if channel == "WIFI" and uploader:
				ok, info = (False, "not-sent")
				seq += 1
				http_payload = {
					"device_id": DEVICE_ID,
					"timestamp": payload.get("timestamp"),
					"environment": payload.get("environment"),
					"seq": seq,
					"is_buffered": False,
				}

				# 优先使用 WebSocket 直连
				if ws_client and ws_client.is_connected():
					ws_msg = {
						"type": "telemetry",
						"device_id": DEVICE_ID,
						"seq": seq,
						"timestamp": payload.get("timestamp"),
						"environment": payload.get("environment"),
						"is_buffered": False,
					}
					ok = ws_client.send_json(ws_msg)
					info = "ws" if ok else "ws-fail"
					# WS 发送失败时：立刻尝试 HTTP 备用
					if not ok:
						ok, info = uploader.post_json(http_payload)
						info = "http-after-ws" if ok else info
				else:
					# WebSocket 不可用时，HTTP 作为备用链路
					# 优先重发队列（仅当 cache_enabled=True 时才会入队）
					if retry_queue:
						ok, info = uploader.post_json(retry_queue[0])
						if ok:
							retry_queue.pop(0)
					else:
						ok, info = uploader.post_json(http_payload)

				# 断网/失败时入队节流（仅当 cache_enabled=True）
				if not ok and cache_enabled:
					if info != "wifi-disconnected" or time.ticks_diff(now, last_enqueue_fail) >= ENQUEUE_COOLDOWN_MS:
						http_payload["is_buffered"] = True
						# 优先落盘到 TF 队列；如不可用则退回内存队列
						if sd_queue:
							_sd_ok, _sd_msg = sd_queue.enqueue(http_payload)
							info = "sd-queue" if _sd_ok else ("sd-queue-fail:" + str(_sd_msg))
							if not _sd_ok:
								enqueue(retry_queue, http_payload)
						else:
							enqueue(retry_queue, http_payload)
						last_enqueue_fail = now

				# 尽力读取服务器消息：command（不强依赖）
				if ws_client and ws_client.is_connected():
					raw = ws_client.recv_once()
					if raw:
						try:
							if isinstance(raw, bytes):
								raw = raw.decode()
							msg = json.loads(raw)
						except Exception:
							msg = None

						if isinstance(msg, dict) and msg.get("type") == "command":
							cmd_id = msg.get("cmd_id")
							cmd = msg.get("command")
							ok_cmd = False
							err = None
							result = None
							try:
								if not isinstance(cmd, dict):
									raise ValueError("command_required")
								t = (cmd.get("type") or "").strip()
								if t == "set_threshold":
									high = float(cmd.get("temp_high"))
									low = float(cmd.get("temp_low"))
									runtime_cfg["threshold"] = {"temp_high": high, "temp_low": low}
									if save_config:
										save_config(runtime_cfg)
									result = {"temp_high": high, "temp_low": low}
									ok_cmd = True
								elif t == "set_sample_interval":
									interval_sec = float(cmd.get("sample_interval_sec"))
									interval_sec = 0.5 if interval_sec < 0.5 else interval_sec
									runtime_cfg.setdefault("sample", {})
									runtime_cfg["sample"]["interval_sec"] = interval_sec
									if save_config:
										save_config(runtime_cfg)
									send_interval_ms = max(500, int(interval_sec * 1000))
									result = {"sample_interval_sec": interval_sec}
									ok_cmd = True
								elif t == "sd_info":
									if not sd:
										raise ValueError("sd_not_available")
									mp = getattr(sd, "mount_point", "/sd")
									res = {"mount_point": mp}
									try:
										st = os.statvfs(mp)
										bsize = st[0]
										blocks = st[2]
										bfree = st[3]
										res.update({
											"block_size": bsize,
											"total_bytes": int(blocks * bsize),
											"free_bytes": int(bfree * bsize),
										})
									except Exception:
										pass
									result = res
									ok_cmd = True
								elif t == "sd_list":
									if not sd:
										raise ValueError("sd_not_available")
									mp = getattr(sd, "mount_point", "/sd")
									path = cmd.get("path") if isinstance(cmd.get("path"), str) else mp
									path = (path or mp).strip()
									if not path.startswith(mp):
										raise ValueError("path_outside_mount")
									items = []
									if hasattr(os, "ilistdir"):
										for it in os.ilistdir(path):
											name = it[0]
											type_ = it[1]
											sz = it[3] if len(it) > 3 else None
											items.append({"name": name, "is_dir": bool(type_ & 0x4000), "size": sz})
									else:
										for name in os.listdir(path):
											full = path.rstrip("/") + "/" + name
											try:
												st = os.stat(full)
												is_dir = bool(st[0] & 0x4000)
												size = st[6] if not is_dir else None
											except Exception:
												is_dir, size = False, None
											items.append({"name": name, "is_dir": is_dir, "size": size})
									result = {"path": path, "items": items}
									ok_cmd = True
								elif t == "sd_read_text":
									if not sd:
										raise ValueError("sd_not_available")
									mp = getattr(sd, "mount_point", "/sd")
									path = cmd.get("path")
									if not isinstance(path, str) or not path:
										raise ValueError("path_required")
									if not path.startswith(mp):
										raise ValueError("path_outside_mount")
									try:
										max_bytes = int(cmd.get("max_bytes") or 4096)
									except Exception:
										max_bytes = 4096
									if max_bytes < 1:
										max_bytes = 1
									if max_bytes > 16384:
										max_bytes = 16384
									with open(path, "r") as f:
										text = f.read(max_bytes)
									result = {"path": path, "text": text, "truncated": True if len(text) >= max_bytes else False}
									ok_cmd = True
								elif t == "sd_delete":
									if not sd:
										raise ValueError("sd_not_available")
									mp = getattr(sd, "mount_point", "/sd")
									path = cmd.get("path")
									if not isinstance(path, str) or not path:
										raise ValueError("path_required")
									if not path.startswith(mp):
										raise ValueError("path_outside_mount")
									os.remove(path)
									result = {"path": path, "deleted": True}
									ok_cmd = True
								elif t == "sd_clear_queue":
									if not sd:
										raise ValueError("sd_not_available")
									if not SdTelemetryQueue:
										raise ValueError("sd_queue_module_missing")
									q = sd_queue
									if not q:
										q = SdTelemetryQueue(mount_point=getattr(sd, "mount_point", "/sd"), max_total_bytes=SD_QUEUE_MAX_BYTES)
									q.clear()
									sd_queue = q
									result = {"cleared": True}
									ok_cmd = True
								else:
									raise ValueError("unknown_command_type")
							except Exception as exc:
								ok_cmd = False
								err = str(exc)

							# 回执给 server（best-effort）
							try:
								ack = {
									"type": "cmd_ack",
									"device_id": DEVICE_ID,
									"cmd_id": cmd_id,
									"ok": bool(ok_cmd),
									"result": result,
									"error": err,
									"timestamp": time.time(),
								}
								ws_client.send_json(ack)
							except Exception:
								pass
				# send 日志节流：避免串口堵塞反过来触发 task_wdt
				state = ("ok" if ok else "fail", str(info))
				if ok:
					send_ok_cnt += 1
				else:
					send_fail_cnt += 1
					if info == "wifi-disconnected":
						wifi_disc_cnt += 1
				if (state != last_send_state) or (time.ticks_diff(now, last_send_log) >= 5000):
					try:
						print(
							"send:",
							state[0],
							state[1],
							"cnt(ok/fail/wifi_disc):",
							send_ok_cnt,
							send_fail_cnt,
							wifi_disc_cnt,
						)
					except Exception:
						pass
					last_send_state = state
					last_send_log = now
			else:
				# BLE 模式：仅在连接后发送数据
				if ble and ble.is_ready() and ble.is_connected():
					ble.send_json(payload)
				else:
					if time.ticks_diff(now, last_ble_report) >= 3000:
						print("ble: not connected")
						last_ble_report = now

			last_send = now

		# TF 队列补发：独立于采样周期，每 2s 最多 10 条。
		# 仅当 cache_enabled=True 时执行。
		if channel == "WIFI" and uploader and sd_queue and cache_enabled:
			if time.ticks_diff(now, last_sd_flush) >= SD_FLUSH_INTERVAL_MS:
				last_sd_flush = now

				def try_send_one(rec):
					"""优先 WS，失败再 HTTP。返回 bool。"""
					try:
						if ws_client and ws_client.is_connected():
							_ok_ws = ws_client.send_json({
								"type": "telemetry",
								"device_id": DEVICE_ID,
								"seq": rec.get("seq"),
								"timestamp": rec.get("timestamp"),
								"environment": rec.get("environment") or {},
								"is_buffered": bool(rec.get("is_buffered", False)),
							})
							if _ok_ws:
								return True
					except Exception:
						pass
					try:
						_ok_http, _ = uploader.post_json(rec)
						return bool(_ok_http)
					except Exception:
						return False

				try:
					sent, _ = sd_queue.flush(try_send_one, max_items=SD_FLUSH_MAX_ITEMS)
					if sent:
						print("sd flush sent:", sent)
				except Exception:
					pass

		# 调试隔离：WiFi 还没连上时，先不写 TF 卡 runtime.log（避免文件系统偶发卡住触发 WDT）
		if sd and time.ticks_diff(now, last_sd_log) >= 60000:
			_should_log = True
			try:
				if channel == "WIFI" and uploader and (not uploader.is_connected()):
					_should_log = False
			except Exception:
				_should_log = True
			if _should_log:
				try:
					sd.log_line("runtime.log", "alive")
				except Exception:
					pass
			last_sd_log = now

		# 内存监控
		if time.ticks_diff(now, last_mem) >= MEM_LOG_INTERVAL_MS:
			print("mem_free:", gc.mem_free())
			last_mem = now

		# 定时 GC
		if time.ticks_diff(now, last_gc) >= GC_INTERVAL_MS:
			gc.collect()
			last_gc = now

		# 喂狗
		if hasattr(sensor, "feed_watchdog"):
			sensor.feed_watchdog()

		time.sleep_ms(10)


if __name__ == "__main__":

	main()  # 入口
