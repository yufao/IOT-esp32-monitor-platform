# -*- coding: utf-8 -*-
"""
运行时配置（可写入设备文件系统）
说明：
- 用于保存 WiFi 配置、阈值等可变参数。
- 避免把敏感信息写入仓库。
"""

import json  # JSON 读写
import os  # 文件操作

CONFIG_PATH = "runtime_config.json"  # 保存到硬件端目录

DEFAULTS = {
    "wifi": {
        "ssid": "",
        "password": "",
    },
    "threshold": {
        "temp_high": 30,
        "temp_low": 15,
    },
}


def load_config():
    """读取运行时配置。"""
    if not exists():
        return DEFAULTS.copy()

    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return DEFAULTS.copy()

    return merge_defaults(data)


def save_config(data):
    """保存运行时配置。"""
    payload = merge_defaults(data)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f)


def merge_defaults(data):
    """合并默认值，确保结构完整。"""
    merged = DEFAULTS.copy()
    merged["wifi"].update(data.get("wifi", {}))
    merged["threshold"].update(data.get("threshold", {}))
    return merged


def exists():
    """判断配置文件是否存在。"""
    try:
        return CONFIG_PATH in os.listdir()
    except Exception:
        return False
