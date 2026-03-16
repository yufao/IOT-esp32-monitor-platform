from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Set

from flask import Flask, jsonify, request
from flask_cors import CORS
from flask_sock import Sock

try:
	from . import config  # type: ignore
except Exception:
	# 兼容直接运行：python server/app.py 或在 server 目录下 python app.py
	import config  # type: ignore


app = Flask(__name__)
sock = Sock(app)


@dataclass
class DeviceState:
	device_id: str
	status: str = "offline"  # online/offline
	last_seen: Optional[int] = None
	firmware_version: Optional[str] = None
	capabilities: Dict[str, Any] = field(default_factory=dict)


_lock = threading.Lock()
_devices: Dict[str, DeviceState] = {}
_latest_telemetry: Dict[str, Dict[str, Any]] = {}
_dashboard_clients: Set[Any] = set()  # flask-sock WebSocket objects


def _now_ts() -> int:
	return int(time.time())


def _auth_ok(api_key: Optional[str]) -> bool:
	if not api_key:
		return False
	return api_key in config.API_KEYS


def _broadcast_dashboard(message: dict[str, Any]) -> None:
	payload = json.dumps(message, separators=(",", ":"), ensure_ascii=False)
	dead = []
	for ws in list(_dashboard_clients):
		try:
			ws.send(payload)
		except Exception:
			dead.append(ws)
	for ws in dead:
		_dashboard_clients.discard(ws)


def _set_device_status(device_id: str, status: str) -> None:
	with _lock:
		state = _devices.get(device_id) or DeviceState(device_id=device_id)
		state.status = status
		if status == "online":
			state.last_seen = _now_ts()
		_devices[device_id] = state

	_broadcast_dashboard(
		{
			"type": "device_status",
			"device_id": device_id,
			"status": status,
			"last_seen": _devices[device_id].last_seen,
		}
	)


@app.get("/health")
def health():
	return jsonify({"ok": True, "ts": _now_ts()})


@app.get("/api/devices")
def list_devices():
	with _lock:
		items = [
			{
				"device_id": d.device_id,
				"status": d.status,
				"last_seen": d.last_seen,
				"firmware_version": d.firmware_version,
				"capabilities": d.capabilities,
			}
			for d in _devices.values()
		]
	return jsonify({"items": sorted(items, key=lambda x: x["device_id"])})


@app.get("/api/telemetry/latest")
def telemetry_latest():
	with _lock:
		items = list(_latest_telemetry.values())
	return jsonify({"items": items})


@app.post("/api/devices/register")
def register_device():
	auth = request.headers.get("Authorization", "")
	token = auth[7:].strip() if auth.startswith("Bearer ") else ""
	if not _auth_ok(token):
		return jsonify({"ok": False, "error": "unauthorized"}), 401

	body = request.get_json(silent=True) or {}
	device_id = (body.get("device_id") or "").strip()
	if not device_id:
		return jsonify({"ok": False, "error": "device_id_required"}), 400

	firmware_version = (body.get("firmware_version") or "").strip() or None
	capabilities = body.get("capabilities") or {}
	if not isinstance(capabilities, dict):
		capabilities = {}

	with _lock:
		state = _devices.get(device_id) or DeviceState(device_id=device_id)
		state.firmware_version = firmware_version or state.firmware_version
		state.capabilities = capabilities or state.capabilities
		state.last_seen = _now_ts()
		_devices[device_id] = state

	return jsonify({"ok": True})


@sock.route("/ws/dashboard")
def ws_dashboard(ws):
	_dashboard_clients.add(ws)

	# 连接即推一份设备快照（便于首屏）
	try:
		with _lock:
			snapshot = {
				"type": "snapshot",
				"devices": [
					{
						"device_id": d.device_id,
						"status": d.status,
						"last_seen": d.last_seen,
						"firmware_version": d.firmware_version,
						"capabilities": d.capabilities,
					}
					for d in _devices.values()
				],
				"latest": list(_latest_telemetry.values()),
			}
		ws.send(json.dumps(snapshot, separators=(",", ":"), ensure_ascii=False))
	except Exception:
		pass

	# 阻塞读取，直到断开
	try:
		while True:
			msg = ws.receive()
			if msg is None:
				break
			# MVP：只接受 subscribe/ping，其他忽略
			# 这里不做严格校验，避免前端联调卡住
	finally:
		_dashboard_clients.discard(ws)


@sock.route("/ws/telemetry")
def ws_telemetry(ws):
	device_id: Optional[str] = None
	authed = False

	try:
		while True:
			raw = ws.receive()
			if raw is None:
				break

			try:
				data = json.loads(raw)
			except Exception:
				continue

			msg_type = data.get("type")
			if msg_type == "hello":
				device_id = (data.get("device_id") or "").strip() or None
				api_key = (data.get("api_key") or "").strip() or None
				if not device_id:
					ws.send(json.dumps({"type": "error", "error": "device_id_required"}))
					continue
				if not _auth_ok(api_key):
					ws.send(json.dumps({"type": "error", "error": "unauthorized"}))
					continue

				firmware_version = (data.get("firmware_version") or "").strip() or None
				capabilities = data.get("capabilities") or {}
				if not isinstance(capabilities, dict):
					capabilities = {}

				with _lock:
					state = _devices.get(device_id) or DeviceState(device_id=device_id)
					state.firmware_version = firmware_version or state.firmware_version
					state.capabilities = capabilities or state.capabilities
					state.status = "online"
					state.last_seen = _now_ts()
					_devices[device_id] = state

				_set_device_status(device_id, "online")
				authed = True
				ws.send(json.dumps({"type": "hello_ok", "ts": _now_ts()}))
				continue

			if msg_type == "telemetry":
				# 必须先 hello 认证，避免匿名写入
				if (not authed) or (not device_id):
					continue

				seq = data.get("seq")
				ts = data.get("timestamp")
				env = data.get("environment")

				if not isinstance(env, dict):
					env = {}

				record = {
					"type": "telemetry",
					"device_id": device_id,
					"seq": seq,
					"timestamp": ts,
					"environment": env,
					"is_buffered": bool(data.get("is_buffered", False)),
					"server_ts": _now_ts(),
				}

				with _lock:
					_latest_telemetry[device_id] = record
					state = _devices.get(device_id) or DeviceState(device_id=device_id)
					state.status = "online"
					state.last_seen = _now_ts()
					_devices[device_id] = state

				_broadcast_dashboard(record)

				# ACK：只要带 seq 就回
				if seq is not None:
					ws.send(json.dumps({"type": "ack", "seq": seq, "server_ts": _now_ts()}))
				continue

			# 其他消息：忽略

	finally:
		if device_id:
			_set_device_status(device_id, "offline")


def create_app() -> Flask:
	return app


def main() -> None:
	CORS(app, resources={r"/*": {"origins": config.CORS_ORIGINS}})
	app.run(host=config.HOST, port=config.PORT, debug=config.DEBUG)


if __name__ == "__main__":
	main()
