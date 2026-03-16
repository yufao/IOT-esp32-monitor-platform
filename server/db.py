# -*- coding: utf-8 -*-
"""SQLite storage for Phase 1.

目标：
- 将 telemetry 做最小持久化，支持后续历史查询/回放
- 不引入额外依赖，使用标准库 sqlite3

注意：
- 采用“每次操作短连接”的方式，避免在 WS/多线程环境下复用连接带来的线程问题。
- Phase1 只存 telemetry，不做复杂清洗/聚合。
"""

from __future__ import annotations

import json
import os
import sqlite3
from typing import Any, Dict, List, Optional, Tuple


def _env(name: str, default: str = "") -> str:
    v = os.getenv(name)
    return default if v is None else v


def get_db_path() -> str:
    # 允许外部覆盖：SLS_DB_PATH
    p = _env("SLS_DB_PATH", "").strip()
    if p:
        return p

    # 默认：server/data/sls.db（相对当前文件）
    base_dir = os.path.dirname(os.path.abspath(__file__))
    data_dir = os.path.join(base_dir, "data")
    os.makedirs(data_dir, exist_ok=True)
    return os.path.join(data_dir, "sls.db")


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(get_db_path(), timeout=5)
    conn.row_factory = sqlite3.Row
    # 基础可靠性设置
    try:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
    except Exception:
        pass
    return conn


def init_db() -> None:
    conn = _connect()
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS telemetry (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_id TEXT NOT NULL,
                ts INTEGER,
                server_ts INTEGER,
                seq INTEGER,
                is_buffered INTEGER DEFAULT 0,
                env_json TEXT NOT NULL
            );
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_telemetry_device_ts ON telemetry(device_id, ts);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_telemetry_server_ts ON telemetry(server_ts);")
        conn.commit()
    finally:
        conn.close()


def insert_telemetry(record: Dict[str, Any]) -> None:
    """写入一条 telemetry。

    record 格式：与 server 广播的 record 对齐（type/device_id/timestamp/environment/...）。
    """
    device_id = (record.get("device_id") or "").strip()
    if not device_id:
        return

    ts = record.get("timestamp")
    server_ts = record.get("server_ts")
    seq = record.get("seq")
    is_buffered = 1 if record.get("is_buffered") else 0
    env = record.get("environment")
    if not isinstance(env, dict):
        env = {}

    conn = _connect()
    try:
        conn.execute(
            "INSERT INTO telemetry(device_id, ts, server_ts, seq, is_buffered, env_json) VALUES(?,?,?,?,?,?)",
            (
                device_id,
                int(ts) if isinstance(ts, (int, float)) else None,
                int(server_ts) if isinstance(server_ts, (int, float)) else None,
                int(seq) if isinstance(seq, (int, float)) else None,
                int(is_buffered),
                json.dumps(env, ensure_ascii=False, separators=(",", ":")),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def query_telemetry(
    device_id: str,
    since_ts: Optional[int] = None,
    until_ts: Optional[int] = None,
    limit: int = 200,
) -> List[Dict[str, Any]]:
    """按设备查询 telemetry 历史（默认返回最近 limit 条，按时间升序）。"""
    device_id = (device_id or "").strip()
    if not device_id:
        return []

    limit = max(1, min(int(limit or 200), 2000))

    where = ["device_id = ?"]
    params: List[Any] = [device_id]

    if since_ts is not None:
        where.append("ts >= ?")
        params.append(int(since_ts))
    if until_ts is not None:
        where.append("ts <= ?")
        params.append(int(until_ts))

    sql = (
        "SELECT device_id, ts, server_ts, seq, is_buffered, env_json "
        "FROM telemetry "
        f"WHERE {' AND '.join(where)} "
        "ORDER BY ts DESC, id DESC "
        "LIMIT ?"
    )
    params.append(limit)

    conn = _connect()
    try:
        rows = conn.execute(sql, params).fetchall()
    finally:
        conn.close()

    items: List[Dict[str, Any]] = []
    for r in rows:
        try:
            env = json.loads(r["env_json"]) if r["env_json"] else {}
        except Exception:
            env = {}
        items.append(
            {
                "type": "telemetry",
                "device_id": r["device_id"],
                "seq": r["seq"],
                "timestamp": r["ts"],
                "environment": env,
                "is_buffered": bool(r["is_buffered"]),
                "server_ts": r["server_ts"],
            }
        )

    # 反转为时间升序，利于前端画曲线
    items.reverse()
    return items
