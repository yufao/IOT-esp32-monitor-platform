# -*- coding: utf-8 -*-
"""
BLE GATT 服务（ESP32 端）
说明：
- 提供一个简单的 BLE 通道，用于桌面端连接与数据下发。
- 使用 Nordic UART Service（NUS）风格：
  - TX 特征：ESP32 -> 电脑（通知）
  - RX 特征：电脑 -> ESP32（写入）
"""

import sys  # 导入路径控制
import os  # 路径工具
import time  # 时间相关
import json  # 数据序列化

# 兼容不同运行目录：确保能找到 hw_config
try:
  from hw_config import BLE_DEVICE_NAME, BLE_ADV_INTERVAL_MS
except ImportError:
  _fallback_paths = [
    "/iot_ai_monitor/hardware",
    "/iot_ai_monitor",
    "/",
  ]
  for _p in _fallback_paths:
    if _p not in sys.path:
      sys.path.append(_p)
  from hw_config import BLE_DEVICE_NAME, BLE_ADV_INTERVAL_MS

try:
  import bluetooth
except ImportError:
  bluetooth = None


# === BLE 事件常量（MicroPython 约定） ===
_IRQ_CENTRAL_CONNECT = 1
_IRQ_CENTRAL_DISCONNECT = 2
_IRQ_GATTS_WRITE = 3


def _advertising_payload(name):
  """生成广播数据（包含 Flags + 设备名称）。"""
  name_bytes = name.encode()
  payload = bytearray()
  # Flags: 通用可发现 + 不支持 BR/EDR
  payload += bytes([2, 0x01, 0x06])
  # Complete Local Name
  payload += bytes([len(name_bytes) + 1, 0x09]) + name_bytes
  return payload


class BleUartServer:
  """BLE UART 风格 GATT 服务。"""

  def __init__(self, name=BLE_DEVICE_NAME):
    if bluetooth is None:
      self._ble = None
      self._ready = False
      return

    self._ble = bluetooth.BLE()
    self._ble.active(True)
    self._ble.irq(self._irq)

    # NUS UUID
    self._uuid_service = bluetooth.UUID("6E400001-B5A3-F393-E0A9-E50E24DCCA9E")
    self._uuid_tx = bluetooth.UUID("6E400003-B5A3-F393-E0A9-E50E24DCCA9E")
    self._uuid_rx = bluetooth.UUID("6E400002-B5A3-F393-E0A9-E50E24DCCA9E")

    # 特征定义
    self._tx = (self._uuid_tx, bluetooth.FLAG_NOTIFY)
    self._rx = (self._uuid_rx, bluetooth.FLAG_WRITE)
    self._service = (self._uuid_service, (self._tx, self._rx))

    ((self._tx_handle, self._rx_handle),) = self._ble.gatts_register_services((self._service,))

    self._connections = set()  # 连接句柄集合
    self._last_cmd = None  # 最近收到的命令
    self._ready = True

    self._advertise(name)  # 开始广播

  def _advertise(self, name):
    """启动广播。"""
    if not self._ble:
      return
    payload = _advertising_payload(name)
    # gap_advertise 的单位是微秒，配置使用毫秒需转换
    interval_us = int(BLE_ADV_INTERVAL_MS) * 1000
    self._ble.gap_advertise(interval_us, adv_data=payload)

  def _irq(self, event, data):
    """BLE 事件回调。"""
    if event == _IRQ_CENTRAL_CONNECT:
      conn_handle, _, _ = data
      self._connections.add(conn_handle)
    elif event == _IRQ_CENTRAL_DISCONNECT:
      conn_handle, _, _ = data
      if conn_handle in self._connections:
        self._connections.remove(conn_handle)
      self._advertise(BLE_DEVICE_NAME)  # 断开后继续广播
    elif event == _IRQ_GATTS_WRITE:
      conn_handle, value_handle = data
      if value_handle == self._rx_handle:
        raw = self._ble.gatts_read(self._rx_handle)
        try:
          self._last_cmd = json.loads(raw.decode())
        except Exception:
          self._last_cmd = {"raw": raw}

  def is_ready(self):
    """BLE 是否可用。"""
    return self._ready

  def is_connected(self):
    """是否已有连接。"""
    return len(self._connections) > 0

  def pop_last_cmd(self):
    """获取并清空最近命令。"""
    cmd = self._last_cmd
    self._last_cmd = None
    return cmd

  def send_json(self, payload):
    """发送 JSON（通知）。"""
    if not self._ble or not self._connections:
      return False
    try:
      data = json.dumps(payload)
    except Exception:
      return False

    for conn_handle in self._connections:
      try:
        self._ble.gatts_notify(conn_handle, self._tx_handle, data)
      except Exception:
        pass
    return True
