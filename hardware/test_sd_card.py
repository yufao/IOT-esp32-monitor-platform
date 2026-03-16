# -*- coding: utf-8 -*-
"""
TF 卡自检脚本
用途：在 ESP32 上快速验证 TF 卡是否可挂载、可读写、可卸载。
运行：import test_sd_card; test_sd_card.run_test()
"""

import uos
import time

try:
    from hw_sd_card import SDCardManager
except ImportError:
    import sys
    for _p in ["/iot_ai_monitor/hardware", "/iot_ai_monitor", "/"]:
        if _p not in sys.path:
            sys.path.append(_p)
    from hw_sd_card import SDCardManager


def run_test():
    print("[TF] 开始自检...")
    sd = SDCardManager()
    print("[TF] 当前配置:", sd.config)

    ok, msg = sd.mount()
    print("[TF] 挂载结果:", ok, msg)
    if not ok:
        print("[TF] 自检失败：无法挂载 TF 卡")
        return False

    try:
        print("[TF] 挂载点内容:", sd.list_root())

        ok, msg = sd.write_text("tf_test.txt", "hello tf card\n")
        print("[TF] 写入结果:", ok, msg)
        if not ok:
            return False

        ok, msg = sd.append_text("tf_test.txt", "append line\n")
        print("[TF] 追加结果:", ok, msg)
        if not ok:
            return False

        ok, content = sd.read_text("tf_test.txt")
        print("[TF] 读取结果:", ok)
        print("[TF] 文件内容:")
        print(content)
        if (not ok) or ("hello tf card" not in content) or ("append line" not in content):
            print("[TF] 自检失败：读写校验不通过")
            return False

        cap = sd.get_capacity()
        print("[TF] 容量信息:", cap)

        try:
            print("[TF] 最终目录:", uos.listdir(sd.mount_point))
        except Exception as e:
            print("[TF] 列目录异常:", e)
            return False

        print("[TF] 自检通过")
        return True
    finally:
        ok, msg = sd.unmount()
        print("[TF] 卸载结果:", ok, msg)


def run_diagnose():
    """分别测试 SPI_ONLY 与 SDMMC_ONLY，帮助定位到底是哪一路失败。"""
    print("[TF] 开始详细诊断...")
    for mode in ("SPI_ONLY", "SDMMC_ONLY"):
        print("\n[TF] 诊断模式:", mode)
        sd = SDCardManager(mode=mode)
        print("[TF] 当前配置:", sd.config)
        ok, msg = sd.mount()
        print("[TF] 挂载结果:", ok, msg)
        if ok:
            print("[TF] 目录:", sd.list_root())
            sd.unmount()
    print("\n[TF] 诊断结束")


def run_vendor_style_test():
    """按普中原厂实验代码方式做最小测试。"""
    print("[TF] 原厂方式测试开始...")
    sd = SDCardManager(mode="SPI_ONLY", baudrate=None)
    print("[TF] 当前配置:", sd.config)
    ok, msg = sd.mount()
    print("[TF] 挂载结果:", ok, msg)
    if not ok:
        print("[TF] 原厂方式挂载失败")
        return False

    try:
        try:
            uos.mkdir("/sd/EBOOK")
        except OSError:
            pass

        file_name = "/sd/EBOOK/text.txt"
        with open(file_name, "w") as f:
            f.write("大家好，欢迎使用普中-ESP32开发板，人生苦短，我选Python和MicroPython")
        time.sleep_ms(50)
        with open(file_name, "r") as f:
            txt = f.read()
        print("[TF] 文件内容:")
        print(txt)
        print("[TF] 目录:", uos.listdir("/sd"))
        print("[TF] 原厂方式测试通过")
        return True
    finally:
        ok, msg = sd.unmount()
        print("[TF] 卸载结果:", ok, msg)
