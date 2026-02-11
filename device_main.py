# -*- coding: utf-8 -*-
"""
设备根目录 main.py 模板
说明：
- 把本文件复制到 ESP32 设备根目录并重命名为 main.py
- 依赖 iot_ai_monitor 作为包（需同步 __init__.py）
"""

import sys  # 导入路径

# 确保根目录在搜索路径
if "/" not in sys.path:
    sys.path.append("/")

# 入口：运行硬件主程序
import iot_ai_monitor.hardware.main as app

app.main()
