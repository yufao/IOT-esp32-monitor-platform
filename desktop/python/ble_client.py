# -*- coding: utf-8 -*-
"""
BLE 桥接服务（桌面端）
说明：
- 使用 bleak 扫描/连接 ESP32
- 通过 WebSocket 与 Electron 通信
- 接收 BLE 通知并转发到前端
"""

import asyncio  # 异步框架
import json  # JSON 编解码
import os  # 环境变量
import time  # 时间相关
from datetime import datetime  # 时间格式化

from bleak import BleakClient, BleakScanner  # BLE 客户端
import websockets  # WebSocket 服务端

BLE_NAME_DEFAULT = "SLS_ESP32"  # 默认设备名
WS_PORT = int(os.getenv("BLE_BRIDGE_PORT", "8765"))  # WebSocket 端口

# NUS UUID
UART_SERVICE = "6E400001-B5A3-F393-E0A9-E50E24DCCA9E"
UART_TX = "6E400003-B5A3-F393-E0A9-E50E24DCCA9E"
UART_RX = "6E400002-B5A3-F393-E0A9-E50E24DCCA9E"

current_client = None  # 当前 BLE 连接
subscribers = set()  # WebSocket 客户端集合


async def notify_handler(_, data):
    """接收 BLE 通知并广播给前端。"""
    try:
        text = data.decode("utf-8")
        payload = json.loads(text)
    except Exception:
        return

    msg = json.dumps({"type": "data", "payload": payload})
    await broadcast(msg)
    await append_log(payload)


async def broadcast(message):
    """广播消息给所有 WebSocket 客户端。"""
    for ws in list(subscribers):
        try:
            await ws.send(message)
        except Exception:
            subscribers.discard(ws)


async def scan_devices():
    """扫描周边 BLE 设备名。"""
    devices = await BleakScanner.discover(timeout=5.0)
    names = [d.name for d in devices if d.name]
    return list(dict.fromkeys(names))


async def connect_device(name):
    """按设备名连接 BLE 设备。"""
    global current_client

    await disconnect_device()

    devices = await BleakScanner.discover(timeout=5.0)
    target = None
    for d in devices:
        if d.name == name:
            target = d
            break

    if not target:
        return False

    client = BleakClient(target)
    await client.connect()
    await client.start_notify(UART_TX, notify_handler)
    current_client = client
    return True


async def disconnect_device():
    """断开当前 BLE 连接。"""
    global current_client
    if current_client:
        try:
            await current_client.stop_notify(UART_TX)
            await current_client.disconnect()
        except Exception:
            pass
    current_client = None


async def send_ble_cmd(payload):
    """通过 BLE 写入指令。"""
    if not current_client:
        return False
    # 末尾添加换行，便于 ESP32 按行解析
    data = (json.dumps(payload) + "\n").encode("utf-8")
    # BLE 写入常见单包 20 字节，手动分片发送
    chunk_size = 20
    try:
        for i in range(0, len(data), chunk_size):
            chunk = data[i : i + chunk_size]
            await current_client.write_gatt_char(UART_RX, chunk)
            await asyncio.sleep(0.02)
        print("ble send bytes:", len(data))
        return True
    except Exception:
        return False


async def append_log(payload):
    """追加 CSV 日志到本地。"""
    os.makedirs("logs", exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    env = payload.get("environment", {})
    bmp = env.get("bmp280", {})
    light = env.get("light", {})
    line = f"{ts},{bmp.get('temp')},{bmp.get('pressure')},{light.get('percent')}\n"
    with open(os.path.join("logs", "sensor_log.csv"), "a", encoding="utf-8") as f:
        f.write(line)


async def ws_handler(websocket):
    """WebSocket 入口：处理前端指令。"""
    subscribers.add(websocket)
    await websocket.send(json.dumps({"type": "status", "state": "idle"}))

    try:
        async for message in websocket:
            data = json.loads(message)
            if data.get("type") == "scan":
                names = await scan_devices()
                await websocket.send(json.dumps({"type": "scan", "items": names}))

            if data.get("type") == "connect":
                name = data.get("name", BLE_NAME_DEFAULT)
                ok = await connect_device(name)
                state = "connected" if ok else "not_found"
                await websocket.send(json.dumps({"type": "status", "state": state}))

            if data.get("type") == "wifi":
                ok = await send_ble_cmd({"type": "wifi", "ssid": data.get("ssid"), "password": data.get("password")})
                await websocket.send(json.dumps({"type": "status", "state": "wifi_sent" if ok else "wifi_failed"}))

            if data.get("type") == "threshold":
                ok = await send_ble_cmd({"type": "threshold", "temp_high": data.get("temp_high"), "temp_low": data.get("temp_low")})
                await websocket.send(json.dumps({"type": "status", "state": "threshold_sent" if ok else "threshold_failed"}))
    finally:
        subscribers.discard(websocket)


async def main():
    """启动 WebSocket 服务。"""
    print(f"BLE bridge listening on ws://127.0.0.1:{WS_PORT}")
    async with websockets.serve(ws_handler, "127.0.0.1", WS_PORT):
        while True:
            await asyncio.sleep(1)


if __name__ == "__main__":
    asyncio.run(main())
