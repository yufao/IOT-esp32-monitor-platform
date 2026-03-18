# -*- coding: utf-8 -*-
"""TF/SD 持久化队列（Phase2）。

设计目标（MVP）：
- 仅在 cache_enabled=True 时启用；默认不开启。
- 将“上报失败的 telemetry”落盘到 /sd 下，断电不丢。
- 网络恢复后按队列顺序补发；补发成功自动删除已完成分片。
- 使用分片 NDJSON 文件（追加写 + 顺序读），避免频繁重写大文件。

文件结构（默认 base_dir=/sd/sls_queue）：
- meta.json: { write_idx, read_idx, read_offset }
- q_000001.ndjson: 每行一个 JSON record

注意：MicroPython 文件系统能力有限，本模块尽量避免复杂的目录遍历/大文件截断。
"""

import json

try:
    import uos as os
except Exception:  # pragma: no cover
    import os  # type: ignore


def _safe_mkdir(path):
    try:
        os.mkdir(path)
    except OSError:
        pass


def _read_json(path, default):
    try:
        with open(path, "r") as f:
            return json.load(f)
    except Exception:
        return default


def _write_json(path, obj):
    tmp = path + ".tmp"
    try:
        with open(tmp, "w") as f:
            json.dump(obj, f)
        try:
            os.remove(path)
        except Exception:
            pass
        os.rename(tmp, path)
        return True
    except Exception:
        try:
            os.remove(tmp)
        except Exception:
            pass
        return False


def _stat_size(path):
    try:
        st = os.stat(path)
        # MicroPython: (mode, ino, dev, nlink, uid, gid, size, atime, mtime, ctime)
        return int(st[6])
    except Exception:
        return 0


class SdTelemetryQueue:
    def __init__(
        self,
        mount_point="/sd",
        base_dir=None,
        max_total_bytes=2 * 1024 * 1024 * 1024,
        segment_max_bytes=512 * 1024,
    ):
        self.mount_point = mount_point.rstrip("/") or "/sd"
        self.base_dir = base_dir or (self.mount_point + "/sls_queue")
        self.meta_path = self.base_dir + "/meta.json"
        self.max_total_bytes = int(max_total_bytes) if max_total_bytes else 0
        self.segment_max_bytes = int(segment_max_bytes) if segment_max_bytes else 0

        _safe_mkdir(self.base_dir)
        self.meta = _read_json(self.meta_path, {"write_idx": 1, "read_idx": 1, "read_offset": 0})
        if not isinstance(self.meta, dict):
            self.meta = {"write_idx": 1, "read_idx": 1, "read_offset": 0}

        self._normalize_meta()
        self._persist_meta()

    def _normalize_meta(self):
        def _to_int(v, d):
            try:
                return int(v)
            except Exception:
                return d

        self.meta["write_idx"] = max(1, _to_int(self.meta.get("write_idx"), 1))
        self.meta["read_idx"] = max(1, _to_int(self.meta.get("read_idx"), 1))
        self.meta["read_offset"] = max(0, _to_int(self.meta.get("read_offset"), 0))

        if self.meta["read_idx"] > self.meta["write_idx"]:
            self.meta["read_idx"] = self.meta["write_idx"]
            self.meta["read_offset"] = 0

    def _persist_meta(self):
        _write_json(self.meta_path, self.meta)

    def _seg_path(self, idx):
        return "%s/q_%06d.ndjson" % (self.base_dir, int(idx))

    def _ensure_write_segment(self):
        p = self._seg_path(self.meta["write_idx"])
        if self.segment_max_bytes > 0 and _stat_size(p) >= self.segment_max_bytes:
            self.meta["write_idx"] += 1
            self._persist_meta()
            p = self._seg_path(self.meta["write_idx"])
        return p

    def _estimate_total_bytes(self):
        # 仅粗略估计：从 read_idx 到 write_idx 的分片累加
        total = 0
        try:
            r = int(self.meta.get("read_idx", 1))
            w = int(self.meta.get("write_idx", 1))
        except Exception:
            return 0
        for i in range(r, w + 1):
            total += _stat_size(self._seg_path(i))
        total += _stat_size(self.meta_path)
        return total

    def _enforce_limit_drop_oldest(self):
        if not self.max_total_bytes or self.max_total_bytes <= 0:
            return
        # 超限时丢弃最旧分片（可能会丢未补发数据：但这是上限保护，MVP 可接受）
        while True:
            total = self._estimate_total_bytes()
            if total <= self.max_total_bytes:
                return
            # 删除当前 read_idx 分片并推进 read_idx
            ridx = int(self.meta.get("read_idx", 1))
            widx = int(self.meta.get("write_idx", 1))
            if ridx > widx:
                return
            p = self._seg_path(ridx)
            try:
                os.remove(p)
            except Exception:
                pass
            self.meta["read_idx"] = min(widx, ridx + 1)
            self.meta["read_offset"] = 0
            self._persist_meta()

    def enqueue(self, record):
        """追加一条记录到队列。record 必须是 dict。"""
        if not isinstance(record, dict):
            return False, "record_not_dict"

        try:
            _safe_mkdir(self.base_dir)
        except Exception:
            pass

        p = self._ensure_write_segment()
        try:
            line = json.dumps(record, separators=(",", ":"), ensure_ascii=False) + "\n"
            with open(p, "a") as f:
                f.write(line)
            self._enforce_limit_drop_oldest()
            return True, "ok"
        except Exception as exc:
            return False, str(exc)

    def has_items(self):
        ridx = int(self.meta.get("read_idx", 1))
        widx = int(self.meta.get("write_idx", 1))
        if ridx < widx:
            return True
        # ridx == widx 时：看是否还有剩余内容
        p = self._seg_path(ridx)
        return _stat_size(p) > int(self.meta.get("read_offset", 0))

    def flush(self, send_func, max_items=10):
        """尝试补发队列头部，最多 max_items 条。

        send_func(record) -> bool 表示是否发送成功。
        """
        sent = 0
        if not callable(send_func):
            return 0, "send_func_required"

        for _ in range(int(max_items or 0)):
            ok, record = self._peek_one()
            if not ok:
                break

            try:
                if send_func(record):
                    self._pop_one()
                    sent += 1
                else:
                    break
            except Exception:
                break

        return sent, "ok"

    def _peek_one(self):
        ridx = int(self.meta.get("read_idx", 1))
        widx = int(self.meta.get("write_idx", 1))
        if ridx > widx:
            return False, None

        p = self._seg_path(ridx)
        try:
            with open(p, "r") as f:
                off = int(self.meta.get("read_offset", 0))
                try:
                    f.seek(off)
                except Exception:
                    # seek 不可用就只能从头读（不理想），直接报空避免死循环
                    return False, None
                line = f.readline()
                if not line:
                    # 分片读完
                    return False, None
                try:
                    if isinstance(line, bytes):
                        line = line.decode()
                except Exception:
                    pass
                try:
                    obj = json.loads(line)
                except Exception:
                    # 损坏行：跳过
                    return True, {"_corrupt": True}
                return True, obj
        except Exception:
            return False, None

    def _pop_one(self):
        ridx = int(self.meta.get("read_idx", 1))
        p = self._seg_path(ridx)
        try:
            with open(p, "r") as f:
                off = int(self.meta.get("read_offset", 0))
                f.seek(off)
                line = f.readline()
                if not line:
                    # EOF
                    self._advance_segment()
                    return
                try:
                    # tell() 在 MicroPython 上通常可用
                    new_off = f.tell()
                except Exception:
                    new_off = off + len(line)

            self.meta["read_offset"] = int(new_off)
            self._persist_meta()

            # 如果已经到 EOF，直接推进分片
            if _stat_size(p) <= int(self.meta.get("read_offset", 0)):
                self._advance_segment()
        except Exception:
            # 出错不推进
            return

    def _advance_segment(self):
        ridx = int(self.meta.get("read_idx", 1))
        widx = int(self.meta.get("write_idx", 1))
        p = self._seg_path(ridx)
        try:
            os.remove(p)
        except Exception:
            pass
        self.meta["read_idx"] = min(widx, ridx + 1)
        self.meta["read_offset"] = 0
        self._persist_meta()

    def clear(self):
        """清空队列（删除分片并重置 meta）。"""
        ridx = int(self.meta.get("read_idx", 1))
        widx = int(self.meta.get("write_idx", 1))
        for i in range(ridx, widx + 1):
            try:
                os.remove(self._seg_path(i))
            except Exception:
                pass
        self.meta = {"write_idx": 1, "read_idx": 1, "read_offset": 0}
        self._persist_meta()
        return True

    def stats(self):
        return {
            "mount_point": self.mount_point,
            "base_dir": self.base_dir,
            "read_idx": int(self.meta.get("read_idx", 1)),
            "write_idx": int(self.meta.get("write_idx", 1)),
            "read_offset": int(self.meta.get("read_offset", 0)),
            "approx_bytes": self._estimate_total_bytes(),
        }
