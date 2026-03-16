# -*- coding: utf-8 -*-
"""Server configuration.

保持 MVP 简单：
- API Key 先用环境变量配置（比赛/内网演示场景）
- 允许后续替换为数据库存储与更严格的鉴权
"""

from __future__ import annotations

import os


def _env(name: str, default: str = "") -> str:
    value = os.getenv(name)
    return default if value is None else value


HOST = _env("SLS_HOST", "0.0.0.0")
PORT = int(_env("SLS_PORT", "5000"))
DEBUG = _env("SLS_DEBUG", "0") == "1"

# CORS（主要给 REST；WebSocket 不走 CORS，但浏览器握手会受同源影响）
# 例："http://localhost:5173,http://127.0.0.1:5173"
CORS_ORIGINS = [o.strip() for o in _env("SLS_CORS_ORIGINS", "*").split(",") if o.strip()]

# API Key：逗号分隔，允许多个设备/环境共存
# 例："dev_key_1,dev_key_2"
API_KEYS = {k.strip() for k in _env("SLS_API_KEYS", "dev_key").split(",") if k.strip()}
