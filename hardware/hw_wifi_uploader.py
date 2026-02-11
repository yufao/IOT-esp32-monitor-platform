# -*- coding: utf-8 -*-
"""
WiFi 连接与数据上报（非阻塞/可扩展）
说明：
- 负责 WiFi 连接、自动重连、HTTP POST 上报。
- 不做传感器采集，数据由外部传入。
"""

import time
import sys
import os
import socket

# 兼容不同运行目录：确保能找到 hw_config
try:
    from hw_config import WIFI_SSID, WIFI_PASSWORD, SERVER_URL
except ImportError:
    fallback_paths = [
        "/iot_ai_monitor/hardware",
        "/iot_ai_monitor",
        "/",
    ]
    for p in fallback_paths:
        if p not in sys.path:
            sys.path.append(p)
    from hw_config import WIFI_SSID, WIFI_PASSWORD, SERVER_URL

try:
    import network
except ImportError:
    network = None

try:
    import urequests as requests
except ImportError:
    requests = None


class WifiUploader:
    """WiFi 连接管理 + 上报封装（非阻塞调度）。"""

    def __init__(self, ssid=WIFI_SSID, password=WIFI_PASSWORD, url=SERVER_URL):
        self.ssid = ssid
        self.password = password
        self.url = url
        self.wlan = network.WLAN(network.STA_IF) if network else None
        self._next_retry = 0
        self._retry_interval_ms = 3000
        self._max_retry_ms = 20000
        self._timeout_s=5        # 超时秒数

        if self.wlan:
            self.wlan.active(True)
        try:
            socket.setdefaulttimeout(self._timeout_s)  # 设置全局默认超时
        except Exception:
            pass

    def is_connected(self):
        return self.wlan and self.wlan.isconnected()

    def connect_step(self, now_ms):
        """非阻塞连接步骤：到时间才尝试连接。"""
        if not self.wlan:
            return False

        if self.is_connected():
            return True

        if time.ticks_diff(now_ms, self._next_retry) < 0:
            return False

        try:
            self.wlan.connect(self.ssid, self.password)
        except Exception:
            pass

        self._next_retry = time.ticks_add(now_ms, self._retry_interval_ms)
        self._retry_interval_ms = min(self._retry_interval_ms * 2, self._max_retry_ms)
        return False

    def ensure_connected(self, timeout_ms=8000):
        """阻塞式连接（仅用于启动阶段测试）。"""
        start = time.ticks_ms()
        while time.ticks_diff(time.ticks_ms(), start) < timeout_ms:
            self.connect_step(time.ticks_ms())
            if self.is_connected():
                return True
            time.sleep_ms(200)
        return False

    def post_json(self, payload, timeout=3):
        """发送 JSON 数据（自动处理连接状态）。"""
        if not self.is_connected():
            return False, "wifi-disconnected"

        if requests is None:
            return False, "urequests-missing"

        try:
            resp = requests.post(self.url, json=payload)
            status = resp.status_code
            resp.close()
            return True, status
        except Exception as exc:
            return False, str(exc)


def demo_send_once():
    """简单自测：连接 WiFi 并发送测试包。"""
    uploader = WifiUploader()
    ok = uploader.ensure_connected()
    print("wifi connected:", ok)

    test_payload = {
        "device_id": "TEST_DEVICE",
        "timestamp": int(time.time()),
        "environment": {"bmp280": {"temp": 25.0, "pressure": 1013.0}, "light": {"raw": 1000}},
    }

    ok, info = uploader.post_json(test_payload)
    print("post result:", ok, info)


if __name__ == "__main__":
    demo_send_once()
