# -*- coding: utf-8 -*-
"""Minimal WebSocket client for MicroPython (ws:// only).

Why this exists:
- Some firmwares ship a `uwebsocket` module without `connect()`.
- We want a dependable fallback to connect to Flask-Sock endpoints.

Scope (intentionally small):
- ws:// (no TLS)
- text frames only (JSON strings)
- client->server masking implemented
- recv() returns a decoded text message (str) or None on timeout/close

This is not a full RFC6455 implementation, but is sufficient for the project's
`/ws/telemetry` channel.
"""

try:
	import usocket as socket  # type: ignore
except Exception:  # pragma: no cover
	import socket  # type: ignore

try:
	import uhashlib as hashlib  # type: ignore
except Exception:  # pragma: no cover
	import hashlib  # type: ignore

try:
	import ubinascii as binascii  # type: ignore
except Exception:  # pragma: no cover
	import binascii  # type: ignore

try:
	import urandom as random  # type: ignore
except Exception:  # pragma: no cover
	import random  # type: ignore


_GUID = b"258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


def _rand_bytes(n: int) -> bytes:
	"""Generate n random bytes in a way compatible with MicroPython.

	Note: Some MicroPython builds only support urandom.getrandbits(k) with k<=32.
	"""
	# Prefer os.urandom if present
	try:
		import uos as _os  # type: ignore
		if hasattr(_os, "urandom"):
			return _os.urandom(n)
	except Exception:
		pass

	out = bytearray(n)
	i = 0
	while i < n:
		# 32-bit chunks
		try:
			r = random.getrandbits(32)
		except Exception:
			# last resort: time-based (weak, but better than crashing)
			try:
				import utime as _t  # type: ignore
				r = (_t.ticks_ms() * 1103515245 + 12345) & 0xFFFFFFFF
			except Exception:
				r = 0xA5A5A5A5
		b = int(r & 0xFFFFFFFF).to_bytes(4, "big")
	for j in range(4):
		if i >= n:
			break
		out[i] = b[j]
		i += 1
	return bytes(out)


def _b64(data: bytes) -> bytes:
	"""Return base64 encoded bytes without trailing newline."""
	out = binascii.b2a_base64(data)
	# MicroPython b2a_base64 usually adds a trailing newline
	return out.strip()


def _sha1(data: bytes) -> bytes:
	h = hashlib.sha1()
	h.update(data)
	return h.digest()


def _parse_ws_url(url: str):
	if not isinstance(url, str) or not url:
		raise ValueError("url_required")
	if not url.startswith("ws://"):
		raise ValueError("only_ws_supported")
	rest = url[5:]
	# rest: host[:port]/path
	slash = rest.find("/")
	if slash == -1:
		hostport = rest
		path = "/"
	else:
		hostport = rest[:slash]
		path = rest[slash:] or "/"
	# strip query for simplicity
	q = path.find("?")
	if q != -1:
		path = path[:q]
	if ":" in hostport:
		host, port_s = hostport.rsplit(":", 1)
		port = int(port_s)
	else:
		host, port = hostport, 80
	if not host:
		raise ValueError("host_required")
	return host, port, path


class _WsSocket:
	def __init__(self, sock):
		self.sock = sock

	def settimeout(self, t):
		try:
			self.sock.settimeout(t)
		except Exception:
			pass

	def _read_exact(self, n: int) -> bytes:
		buf = b""
		while len(buf) < n:
			chunk = self.sock.recv(n - len(buf))
			if not chunk:
				raise OSError("connection_closed")
			buf += chunk
		return buf

	def close(self):
		try:
			self.sock.close()
		except Exception:
			pass


class MinimalWsClient:
	"""Minimal WebSocket client.

	API surface compatible enough for `WsTelemetryClient`:
	- send(str)
	- recv() -> str|None
	- close()
	- sock attribute for timeout setting
	"""

	def __init__(self, url: str, timeout_s: float = 2.0):
		self.url = url
		self.timeout_s = timeout_s
		self.sock = None
		self._ws = None

	def connect(self):
		host, port, path = _parse_ws_url(self.url)
		s = socket.socket()
		try:
			s.settimeout(self.timeout_s)
		except Exception:
			pass
		# Use getaddrinfo for better compatibility across stacks
		addr = None
		try:
			ai = socket.getaddrinfo(host, port)
			if ai:
				addr = ai[0][-1]
		except Exception:
			addr = None
		s.connect(addr or (host, port))
		ws = _WsSocket(s)

		key = _rand_bytes(16)
		sec_key = _b64(key)
		req = (
			"GET %s HTTP/1.1\r\n"
			"Host: %s:%d\r\n"
			"Upgrade: websocket\r\n"
			"Connection: Upgrade\r\n"
			"Sec-WebSocket-Key: %s\r\n"
			"Sec-WebSocket-Version: 13\r\n"
			"\r\n"
		) % (path, host, port, sec_key.decode())
		ws.sock.send(req.encode())

		# Read HTTP response headers (very small)
		resp = b""
		while b"\r\n\r\n" not in resp:
			chunk = ws.sock.recv(256)
			if not chunk:
				raise OSError("handshake_no_response")
			resp += chunk
			if len(resp) > 4096:
				raise OSError("handshake_too_large")

		# Basic validation
		if not resp.startswith(b"HTTP/1.1 101"):
			# include a short snippet for diagnostics
			try:
				snip = resp[:120]
			except Exception:
				snip = b""
			raise OSError("handshake_failed:" + snip)

		# Validate Sec-WebSocket-Accept if present
		accept_expected = _b64(_sha1(sec_key + _GUID))
		low = resp.lower()
		idx = low.find(b"sec-websocket-accept:")
		if idx != -1:
			line_end = low.find(b"\r\n", idx)
			line = resp[idx:line_end]
			# line: b'Sec-WebSocket-Accept: xxx'
			try:
				val = line.split(b":", 1)[1].strip()
			except Exception:
				val = b""
			if val and (val != accept_expected):
				raise OSError("bad_accept")

		self.sock = s
		self._ws = ws
		return self

	def _mask(self, payload: bytes, mask_key: bytes) -> bytes:
		out = bytearray(len(payload))
		for i in range(len(payload)):
			out[i] = payload[i] ^ mask_key[i & 3]
		return bytes(out)

	def send(self, text: str):
		if not self._ws:
			raise OSError("not_connected")
		if isinstance(text, str):
			payload = text.encode()
		else:
			payload = bytes(text)

		# FIN + text frame
		head = bytearray()
		head.append(0x81)
		ln = len(payload)
		mask_bit = 0x80
		if ln < 126:
			head.append(mask_bit | ln)
		elif ln < 65536:
			head.append(mask_bit | 126)
			head.extend(ln.to_bytes(2, "big"))
		else:
			head.append(mask_bit | 127)
			head.extend(ln.to_bytes(8, "big"))

		mask_key = _rand_bytes(4)
		masked = self._mask(payload, mask_key)
		self._ws.sock.send(bytes(head) + mask_key + masked)

	def _send_control(self, opcode: int, payload: bytes = b""):
		if not self._ws:
			return
		ln = len(payload)
		mask_bit = 0x80
		head = bytearray()
		head.append(0x80 | (opcode & 0x0F))
		head.append(mask_bit | ln)
		mask_key = _rand_bytes(4)
		masked = self._mask(payload, mask_key) if payload else b""
		try:
			self._ws.sock.send(bytes(head) + mask_key + masked)
		except Exception:
			pass

	def recv(self):
		"""Return a text message or None on timeout/close."""
		if not self._ws:
			return None
		try:
			hdr = self._ws._read_exact(2)
		except Exception:
			return None

		b1 = hdr[0]
		b2 = hdr[1]
		opcode = b1 & 0x0F
		masked = (b2 & 0x80) != 0
		ln = b2 & 0x7F
		if ln == 126:
			ln = int.from_bytes(self._ws._read_exact(2), "big")
		elif ln == 127:
			ln = int.from_bytes(self._ws._read_exact(8), "big")

		mask_key = b""
		if masked:
			mask_key = self._ws._read_exact(4)
		payload = self._ws._read_exact(ln) if ln else b""
		if masked and payload:
			payload = self._mask(payload, mask_key)

		# Control frames
		if opcode == 0x8:  # close
			self.close()
			return None
		if opcode == 0x9:  # ping
			self._send_control(0xA, payload)  # pong
			return None
		if opcode == 0xA:  # pong
			return None

		if opcode == 0x1:  # text
			try:
				return payload.decode()
			except Exception:
				return None
		# ignore other opcodes
		return None

	def close(self):
		try:
			self._send_control(0x8, b"")
		except Exception:
			pass
		if self._ws:
			self._ws.close()
		self._ws = None
		self.sock = None
