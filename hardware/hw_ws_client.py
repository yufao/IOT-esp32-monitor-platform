# -*- coding: utf-8 -*-
"""WebSocket Telemetry Client (MicroPython).

目标：
- 封装 MicroPython 环境中 websocket/uwebsocket 的差异
- 提供最小可用的 connect/send/recv/close 能力

约束：
- 以 MVP 为主：优先保障主循环不被网络阻塞
- 缓存默认关闭：ACK 仅用于联调观察，不作为强依赖
"""

import time
import json

try:
	import socket
except Exception:
	socket = None

# 兼容不同库：websocket / uwebsocket
try:
	import uwebsocket as _uwebsocket
except Exception:
	_uwebsocket = None

try:
	import websocket as _websocket
except Exception:
	_websocket = None


class WsTelemetryClient:
	def __init__(self, url, hello_payload, connect_timeout_s=2):
		self.url = url
		self.hello_payload = hello_payload
		self.connect_timeout_s = connect_timeout_s
		self.ws = None
		self._next_retry_ms = 0
		self._retry_ms = 2000
		self._max_retry_ms = 20000

		# 给底层 socket 一个保守的默认超时，避免 recv/send 卡死
		try:
			if socket:
				socket.setdefaulttimeout(connect_timeout_s)
		except Exception:
			pass

	def is_connected(self):
		return self.ws is not None

	def _connect_impl(self):
		# 优先 uwebsocket.connect(url)
		if _uwebsocket and hasattr(_uwebsocket, "connect"):
			return _uwebsocket.connect(self.url)
		# 其次 websocket.connect(url)
		if _websocket and hasattr(_websocket, "connect"):
			return _websocket.connect(self.url)
		raise RuntimeError("no websocket connect() available")

	def connect_step(self, now_ms):
		"""非阻塞重连：到点才尝试连接。"""
		if self.is_connected():
			return True

		if time.ticks_diff(now_ms, self._next_retry_ms) < 0:
			return False

		try:
			self.ws = self._connect_impl()
			# 连接成功，立刻发 hello
			self.send_json(self.hello_payload)
			# 重置退避
			self._retry_ms = 2000
			return True
		except Exception:
			self.ws = None
			self._next_retry_ms = time.ticks_add(now_ms, self._retry_ms)
			self._retry_ms = min(self._retry_ms * 2, self._max_retry_ms)
			return False

	def send_json(self, obj):
		if not self.ws:
			return False
		try:
			self.ws.send(json.dumps(obj))
			return True
		except Exception:
			self.close()
			return False

	def recv_once(self):
		"""尽力读取一条消息；无消息/异常返回 None。"""
		if not self.ws:
			return None
		try:
			msg = self.ws.recv()
			return msg
		except Exception:
			return None

	def close(self):
		if not self.ws:
			return
		try:
			self.ws.close()
		except Exception:
			pass
		self.ws = None
