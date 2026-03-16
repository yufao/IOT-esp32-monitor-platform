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
	from . import db  # type: ignore
except Exception:
	# 兼容直接运行：python server/app.py 或在 server 目录下 python app.py
	import config  # type: ignore
	import db  # type: ignore


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
_device_ws: Dict[str, Any] = {}  # device_id -> /ws/telemetry WebSocket
_pending_cmd: Dict[str, Dict[str, Any]] = {}  # cmd_id -> {device_id, command, ts}
_cmd_counter = 0


def _now_ts() -> int:
	return int(time.time())


def _effective_status(status: str, last_seen: Optional[int]) -> str:
	"""基于 last_seen 的离线判定。

	WS 连接断开时我们会主动设置 offline；但 HTTP 兜底没有“断开事件”，
	因此需要用 TTL 进行推断。
	"""
	try:
		ttl = int(getattr(config, "DEVICE_OFFLINE_TTL_SEC", 30))
	except Exception:
		ttl = 30
	if ttl <= 0:
		return status
	if not last_seen:
		return "offline"
	return "offline" if (_now_ts() - int(last_seen)) > ttl else status


def _device_to_dict(d: DeviceState) -> dict[str, Any]:
	return {
		"device_id": d.device_id,
		"status": _effective_status(d.status, d.last_seen),
		"last_seen": d.last_seen,
		"firmware_version": d.firmware_version,
		"capabilities": d.capabilities,
	}


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


def _broadcast_command_status(message: dict[str, Any]) -> None:
	# 命令面向 dashboard 推送，结构与 telemetry/device_status 一致
	message = dict(message)
	message.setdefault("server_ts", _now_ts())
	_broadcast_dashboard(message)


def _next_cmd_id() -> str:
	global _cmd_counter
	with _lock:
		_cmd_counter += 1
		c = _cmd_counter
	return f"cmd_{_now_ts()}_{c}"


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
		items = [_device_to_dict(d) for d in _devices.values()]
	return jsonify({"items": sorted(items, key=lambda x: x["device_id"])})


@app.get("/api/telemetry/latest")
def telemetry_latest():
	with _lock:
		items = list(_latest_telemetry.values())
	return jsonify({"items": items})


@app.get("/api/telemetry/history")
def telemetry_history():
	"""查询 telemetry 历史（SQLite）。

	参数：
	- device_id (required)
	- since (optional, unix seconds)
	- until (optional, unix seconds)
	- limit (optional, default 200, max 2000)
	"""
	device_id = (request.args.get("device_id") or "").strip()
	if not device_id:
		return jsonify({"ok": False, "error": "device_id_required"}), 400

	def _to_int(name: str) -> Optional[int]:
		v = (request.args.get(name) or "").strip()
		if not v:
			return None
		try:
			return int(float(v))
		except Exception:
			return None

	since_ts = _to_int("since")
	until_ts = _to_int("until")
	limit = _to_int("limit") or 200

	try:
		items = db.query_telemetry(device_id=device_id, since_ts=since_ts, until_ts=until_ts, limit=limit)
		return jsonify({"ok": True, "items": items})
	except Exception as exc:
		return jsonify({"ok": False, "error": str(exc)}), 500


@app.post("/api/telemetry")
def telemetry_ingest_http():
	"""HTTP 备用上报通道（Phase1）。

	- 用于设备端在 WS 不可用时的兜底
	- 认证方式：Authorization: Bearer <api_key>
	"""
	auth = request.headers.get("Authorization", "")
	token = auth[7:].strip() if auth.startswith("Bearer ") else ""
	if not _auth_ok(token):
		return jsonify({"ok": False, "error": "unauthorized"}), 401

	body = request.get_json(silent=True) or {}
	device_id = (body.get("device_id") or "").strip()
	if not device_id:
		return jsonify({"ok": False, "error": "device_id_required"}), 400

	env = body.get("environment")
	if not isinstance(env, dict):
		env = {}

	record = {
		"type": "telemetry",
		"device_id": device_id,
		"seq": body.get("seq"),
		"timestamp": body.get("timestamp"),
		"environment": env,
		"is_buffered": bool(body.get("is_buffered", False)),
		"server_ts": _now_ts(),
	}

	with _lock:
		_latest_telemetry[device_id] = record
		state = _devices.get(device_id) or DeviceState(device_id=device_id)
		state.status = "online"
		state.last_seen = _now_ts()
		_devices[device_id] = state

	_broadcast_dashboard(record)
	try:
		db.insert_telemetry(record)
	except Exception:
		pass
	return jsonify({"ok": True, "server_ts": _now_ts()})


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


@app.post("/api/commands/send")
def send_command():
	"""Web 控制面：向指定设备下发命令（MVP，不做可靠投递）。

	Header：Authorization: Bearer <api_key>
	Body：{ device_id, command: { type: 'set_threshold'|'set_sample_interval', ... } }
	"""
	auth = request.headers.get("Authorization", "")
	token = auth[7:].strip() if auth.startswith("Bearer ") else ""
	if not _auth_ok(token):
		return jsonify({"ok": False, "error": "unauthorized"}), 401

	body = request.get_json(silent=True) or {}
	device_id = (body.get("device_id") or "").strip()
	command = body.get("command")
	if not device_id:
		return jsonify({"ok": False, "error": "device_id_required"}), 400
	if not isinstance(command, dict):
		return jsonify({"ok": False, "error": "command_required"}), 400
	cmd_type = (command.get("type") or "").strip()
	if not cmd_type:
		return jsonify({"ok": False, "error": "command_type_required"}), 400

	with _lock:
		ws = _device_ws.get(device_id)
		state = _devices.get(device_id)
		status = state.status if state else "offline"

	if not ws or _effective_status(status, state.last_seen if state else None) != "online":
		return jsonify({"ok": False, "error": "device_offline"}), 409

	cmd_id = _next_cmd_id()
	payload = {"type": "command", "cmd_id": cmd_id, "command": command}

	try:
		ws.send(json.dumps(payload, separators=(",", ":"), ensure_ascii=False))
	except Exception:
		with _lock:
			_device_ws.pop(device_id, None)
		return jsonify({"ok": False, "error": "send_failed"}), 500

	with _lock:
		_pending_cmd[cmd_id] = {"device_id": device_id, "command": command, "ts": _now_ts()}

	_broadcast_command_status(
		{
			"type": "command_sent",
			"device_id": device_id,
			"cmd_id": cmd_id,
			"command": command,
		}
	)
	return jsonify({"ok": True, "cmd_id": cmd_id})


@sock.route("/ws/dashboard")
def ws_dashboard(ws):
	_dashboard_clients.add(ws)

	# 连接即推一份设备快照（便于首屏）
	try:
		with _lock:
			snapshot = {
				"type": "snapshot",
				"devices": [_device_to_dict(d) for d in _devices.values()],
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
					_device_ws[device_id] = ws

				_set_device_status(device_id, "online")
				authed = True
				ws.send(json.dumps({"type": "hello_ok", "ts": _now_ts()}))
				continue

			if msg_type == "cmd_ack":
				if (not authed) or (not device_id):
					continue
				cmd_id = (data.get("cmd_id") or "").strip()
				ok = bool(data.get("ok", False))
				result = data.get("result")
				err = data.get("error")
				if not cmd_id:
					continue

				pending = None
				with _lock:
					pending = _pending_cmd.get(cmd_id)
					# 根据下发命令更新“最后已知配置”（MVP：仅记录阈值/采样间隔）
					if pending and ok:
						cmd = pending.get("command") or {}
						t = (cmd.get("type") or "").strip()
						state = _devices.get(device_id) or DeviceState(device_id=device_id)
						cfg = state.capabilities.get("config") if isinstance(state.capabilities, dict) else None
						if not isinstance(cfg, dict):
							cfg = {}
						if t == "set_threshold":
							cfg["temp_high"] = cmd.get("temp_high")
							cfg["temp_low"] = cmd.get("temp_low")
						if t == "set_sample_interval":
							cfg["sample_interval_sec"] = cmd.get("sample_interval_sec")
						state.capabilities["config"] = cfg
						_devices[device_id] = state

				_broadcast_command_status(
					{
						"type": "command_ack",
						"device_id": device_id,
						"cmd_id": cmd_id,
						"ok": ok,
						"error": err,
						"result": result,
						"command": pending.get("command") if isinstance(pending, dict) else None,
					}
				)
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

				try:
					db.insert_telemetry(record)
				except Exception:
					pass

				# ACK：只要带 seq 就回
				if seq is not None:
					ws.send(json.dumps({"type": "ack", "seq": seq, "server_ts": _now_ts()}))
				continue

			# 其他消息：忽略

	finally:
		if device_id:
			with _lock:
				_device_ws.pop(device_id, None)
			_set_device_status(device_id, "offline")


def create_app() -> Flask:
	try:
		db.init_db()
	except Exception:
		pass
	return app


def main() -> None:
	try:
		db.init_db()
	except Exception:
		pass
	CORS(app, resources={r"/*": {"origins": config.CORS_ORIGINS}})
	app.run(host=config.HOST, port=config.PORT, debug=config.DEBUG)


if __name__ == "__main__":
	main()
