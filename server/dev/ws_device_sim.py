"""WebSocket device simulator for Phase 1.

用途：
- 在不连接 ESP32 的情况下，验证 server 的 /ws/telemetry 是否可用
- 测试 hello 鉴权、telemetry 上报、ack 返回

依赖：
- pip install -r server/dev/requirements.txt

运行：
- 在 ESP32/iot_ai_monitor 目录下：python server/dev/ws_device_sim.py

环境变量：
- SLS_SIM_URL (默认 ws://127.0.0.1:5000/ws/telemetry)
- SLS_SIM_DEVICE_ID (默认 ESP32_SIM_001)
- SLS_SIM_API_KEY (默认 dev_key)
"""

import asyncio
import json
import os
import time

import websockets


def env(name: str, default: str) -> str:
    v = os.getenv(name)
    return default if v is None or v == "" else v


URL = env("SLS_SIM_URL", "ws://127.0.0.1:5000/ws/telemetry")
DEVICE_ID = env("SLS_SIM_DEVICE_ID", "ESP32_SIM_001")
API_KEY = env("SLS_SIM_API_KEY", "dev_key")


async def main() -> None:
    async with websockets.connect(URL) as ws:
        hello = {
            "type": "hello",
            "device_id": DEVICE_ID,
            "api_key": API_KEY,
            "firmware_version": "sim-0.1.0",
            "protocol": 1,
            "capabilities": {"bmp280": True, "light": True},
        }
        await ws.send(json.dumps(hello, ensure_ascii=False))
        print("-> hello")

        # 读取 hello_ok / error
        try:
            msg = await asyncio.wait_for(ws.recv(), timeout=2)
            print("<-", msg)
        except Exception as exc:
            print("no hello response:", exc)

        seq = 0
        while True:
            seq += 1
            payload = {
                "type": "telemetry",
                "device_id": DEVICE_ID,
                "seq": seq,
                "timestamp": int(time.time()),
                "environment": {
                    "bmp280": {"temp": 20.0 + (seq % 5), "pressure": 1013.0, "status": "ok"},
                    "light": {"raw": 1000 + seq, "voltage": 1.1, "percent": 30},
                },
                "is_buffered": False,
            }
            await ws.send(json.dumps(payload, ensure_ascii=False))
            print("-> telemetry seq=", seq)

            # 期望 ack
            try:
                ack = await asyncio.wait_for(ws.recv(), timeout=2)
                print("<-", ack)
            except Exception as exc:
                print("no ack:", exc)

            await asyncio.sleep(2)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("stopped")
    except asyncio.CancelledError:
        print("stopped")
