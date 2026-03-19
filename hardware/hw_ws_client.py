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

# 项目内置：最小 WS 客户端兜底（当固件自带 websocket 库不提供 connect() 时使用）
try:
	from hw_ws_min_client import MinimalWsClient as _MinimalWsClient
except Exception:
	_MinimalWsClient = None


class WsTelemetryClient:
	def __init__(self, url, hello_payload, connect_timeout_s=2, io_timeout_s=0.3):
		self.url = url
		self.hello_payload = hello_payload
		self.connect_timeout_s = connect_timeout_s
		self.io_timeout_s = io_timeout_s
		self.ws = None
		self.last_error = None
		self.last_error_ms = 0
		self.last_connect_ms = 0
		self.last_connect_ok_ms = 0
		self._next_retry_ms = 0
		self._retry_ms = 2000
		self._max_retry_ms = 20000
		_u_ok = bool(_uwebsocket and hasattr(_uwebsocket, "connect"))
		_w_ok = bool(_websocket and hasattr(_websocket, "connect"))
		_m_ok = bool(_MinimalWsClient)
		if _u_ok:
			self._lib_name = "uwebsocket"
		elif _w_ok:
			self._lib_name = "websocket"
		elif _m_ok:
			self._lib_name = "minimal"
		else:
			self._lib_name = "none"

	def _set_ws_socket_timeout(self):
		"""尽力给底层 socket 设置超时，避免 ws.recv/send 卡死。"""
		if not self.ws:
			return
		try:
			# 有些实现把 socket 暴露为 ws.sock / ws._sock / ws.socket
			for attr in ("sock", "_sock", "socket"):
				s = getattr(self.ws, attr, None)
				if s and hasattr(s, "settimeout"):
					s.settimeout(self.io_timeout_s)
					return
			# 也可能 ws 本身就是 socket-like
			if hasattr(self.ws, "settimeout"):
				self.ws.settimeout(self.io_timeout_s)
		except Exception:
			pass

	def _is_timeout_exc(self, exc):
		try:
			# 常见：ETIMEDOUT=110, EAGAIN=11（不同固件/库可能不一致）
			if isinstance(exc, OSError):
				code = exc.args[0] if getattr(exc, "args", None) else None
				if code in (110, 11):
					return True
		except Exception:
			pass
		try:
			msg = str(exc).lower()
			return ("timed out" in msg) or ("etimedout" in msg)
		except Exception:
			return False

	def is_connected(self):
		return self.ws is not None

	def debug_snapshot(self):
		return {
			"connected": bool(self.ws),
			"lib": self._lib_name,
			"last_error": self.last_error,
			"retry_ms": self._retry_ms,
		}

	def _connect_impl(self):
		# 优先 uwebsocket.connect(url)
		if _uwebsocket and hasattr(_uwebsocket, "connect"):
			return _uwebsocket.connect(self.url)
		# 其次 websocket.connect(url)
		if _websocket and hasattr(_websocket, "connect"):
			return _websocket.connect(self.url)
		# 最后：使用项目内置 minimal client
		if _MinimalWsClient:
			return _MinimalWsClient(self.url, timeout_s=float(self.connect_timeout_s)).connect()
		raise RuntimeError("no websocket connect() available")

	def connect_step(self, now_ms):
		"""非阻塞重连：到点才尝试连接。"""
		if self.is_connected():
			return True

		if time.ticks_diff(now_ms, self._next_retry_ms) < 0:
			return False

		try:
			self.last_connect_ms = now_ms
			self.ws = self._connect_impl()
			self._set_ws_socket_timeout()
			# 连接成功，立刻发 hello
			self.send_json(self.hello_payload)
			# 重置退避
			self._retry_ms = 2000
			self.last_error = None
			self.last_error_ms = 0
			self.last_connect_ok_ms = now_ms
			return True
		except Exception as exc:
			self.ws = None
			try:
				self.last_error = str(exc)
			except Exception:
				self.last_error = "connect_failed"
			self.last_error_ms = now_ms
			self._next_retry_ms = time.ticks_add(now_ms, self._retry_ms)
			self._retry_ms = min(self._retry_ms * 2, self._max_retry_ms)
			return False

	def send_json(self, obj):
		if not self.ws:
			return False
		try:
			self._set_ws_socket_timeout()
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
			self._set_ws_socket_timeout()
			msg = self.ws.recv()
			return msg
		except Exception as exc:
			# 超时属于正常情况：表示暂时没消息
			if self._is_timeout_exc(exc):
				return None
			# 其他异常：认为连接已损坏，触发重连
			self.close()
			return None

	def close(self):
		if not self.ws:
			return
		try:
			self.ws.close()
		except Exception:
			pass
		self.ws = None
