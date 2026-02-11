# -*- coding: utf-8 -*-
"""
设备根目录 boot.py 模板
说明：
- 可选：只做轻量初始化，避免在 boot 中启动主逻辑
- 若使用此模板，可直接替换设备根目录 boot.py
"""

# 保持 boot 轻量，必要时可关闭调试信息
try:
    import esp
    esp.osdebug(None)
except Exception:
    pass
