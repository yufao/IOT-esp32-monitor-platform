# -*- coding: utf-8 -*-
"""
SD/TF 卡管理器（支持 SPI / SDMMC 自动切换）
说明：
- 当前项目默认按普中开发板资料优先使用 SPI
- 也保留 SDMMC 作为兼容兜底
"""

import time  # 时间戳
import uos  # MicroPython 文件系统

try:
    import machine  # ESP32 硬件
except ImportError:
    machine = None

try:
    import sdcard  # SD 卡驱动
except ImportError:
    sdcard = None

# 兼容不同运行目录：确保能找到 hw_config
try:
    from hw_config import (
        SD_MOUNT_MODE,
        SDMMC_SLOT,
        SD_SCK_PIN,
        SD_MOSI_PIN,
        SD_MISO_PIN,
        SD_CS_PIN,
        BAUDRATE,
        SPI_ID,
        mount_point,
    )
except ImportError:
    _fallback_paths = [
        "/iot_ai_monitor/hardware",
        "/iot_ai_monitor",
        "/",
    ]
    import sys
    for _p in _fallback_paths:
        if _p not in sys.path:
            sys.path.append(_p)
    from hw_config import (
        SD_MOUNT_MODE,
        SDMMC_SLOT,
        SD_SCK_PIN,
        SD_MOSI_PIN,
        SD_MISO_PIN,
        SD_CS_PIN,
        BAUDRATE,
        SPI_ID,
        mount_point,
    )


class SDCardManager:
    """SD/TF 卡管理器（自动挂载、读写、容量检查）。"""

    def __init__(self, **config):
        # 合并配置（默认来自 hw_config）
        self.config = {
            "mode": SD_MOUNT_MODE,
            "sdmmc_slot": SDMMC_SLOT,
            "spi_id": SPI_ID,
            "sck": SD_SCK_PIN,
            "mosi": SD_MOSI_PIN,
            "miso": SD_MISO_PIN,
            "cs": SD_CS_PIN,
            "baudrate": BAUDRATE,
            "mount_point": mount_point,
        }
        self.config.update(config)

        baudrate = self.config.get("baudrate")
        if not isinstance(baudrate, int) or baudrate <= 0:
            self.config["baudrate"] = None

        self.mount_point = self.config["mount_point"]
        self._mounted = False
        self._spi = None
        self._sd = None
        self._vfs = None

    def _ensure_mount_dir(self):
        try:
            uos.mkdir(self.mount_point)
        except OSError:
            pass

    def _mount_sdmmc(self):
        try:
            self._sd = machine.SDCard(slot=self.config["sdmmc_slot"])
            self._ensure_mount_dir()
            self._vfs = uos.VfsFat(self._sd)
            uos.mount(self._vfs, self.mount_point)
            self._mounted = True
            return True, "mounted-sdmmc"
        except Exception as e:
            self._cleanup()
            return False, "sdmmc-failed: {}".format(e)

    def _mount_spi_once(self, baudrate):
        cs_pin = machine.Pin(self.config["cs"], machine.Pin.OUT, value=1)
        if baudrate is not None:
            self._spi = machine.SPI(
                self.config["spi_id"],
                baudrate=baudrate,
                polarity=0,
                phase=0,
                sck=machine.Pin(self.config["sck"]),
                mosi=machine.Pin(self.config["mosi"]),
                miso=machine.Pin(self.config["miso"]),
            )
        else:
            # 与普中原厂示例完全保持一致
            self._spi = machine.SPI(
                self.config["spi_id"],
                sck=machine.Pin(self.config["sck"]),
                mosi=machine.Pin(self.config["mosi"]),
                miso=machine.Pin(self.config["miso"]),
            )
        self._sd = sdcard.SDCard(self._spi, cs_pin)
        self._ensure_mount_dir()
        # 按原厂示例直接挂载块设备；部分固件对这种方式兼容性更好
        uos.mount(self._sd, self.mount_point)
        self._mounted = True
        return True, "mounted-spi@{}".format("default" if baudrate is None else baudrate)

    def _mount_spi(self):
        if sdcard is None:
            return False, "sdcard-missing"

        errors = []
        tried = []
        for baudrate in (self.config["baudrate"], 400000, 1000000, 200000):
            if baudrate in tried:
                continue
            tried.append(baudrate)
            try:
                return self._mount_spi_once(baudrate)
            except Exception as e:
                errors.append("{}@{}".format(e, "default" if baudrate is None else baudrate))
                self._cleanup()
        return False, "spi-failed: {}".format(" | ".join(errors))

    def mount(self):
        """尝试挂载 SD 卡（先 SDMMC，再 SPI）。"""
        if machine is None:
            return False, "machine-missing"

        if self._mounted:
            return True, "already-mounted"

        mode = self.config.get("mode", "SPI_FIRST")
        attempts = []

        if mode in ("SPI_FIRST", "SPI_ONLY"):
            attempts = [self._mount_spi]
            if mode == "SPI_FIRST":
                attempts.append(self._mount_sdmmc)
        elif mode in ("SDMMC_FIRST", "SDMMC_ONLY"):
            attempts = [self._mount_sdmmc]
            if mode == "SDMMC_FIRST":
                attempts.append(self._mount_spi)
        else:
            attempts = [self._mount_spi, self._mount_sdmmc]

        errors = []
        for fn in attempts:
            try:
                ok, msg = fn()
                if ok:
                    return ok, msg
                errors.append(msg)
            except Exception as e:
                errors.append("{}-exception: {}".format(fn.__name__, e))
                self._cleanup()

        return False, "mount-failed: {}".format(" | ".join(errors))

    def unmount(self):
        """卸载 SD 卡。"""
        if not self._mounted:
            return True, "already-unmounted"
        try:
            uos.umount(self.mount_point)
            self._cleanup()
            return True, "unmounted"
        except Exception as e:
            return False, str(e)

    def _cleanup(self):
        """清理资源。"""
        self._mounted = False
        self._vfs = None
        self._sd = None
        self._spi = None

    def is_mounted(self):
        """是否已挂载。"""
        return self._mounted

    def list_root(self):
        """列出根目录文件。"""
        if not self._mounted:
            return []
        try:
            return uos.listdir(self.mount_point)
        except Exception:
            return []

    def write_text(self, filename, text):
        """写文本（覆盖）。"""
        if not self._mounted:
            return False, "not-mounted"
        try:
            path = self.mount_point + "/" + filename
            with open(path, "w") as f:
                f.write(text)
            return True, "ok"
        except Exception as e:
            return False, str(e)

    def append_text(self, filename, text):
        """追加文本。"""
        if not self._mounted:
            return False, "not-mounted"
        try:
            path = self.mount_point + "/" + filename
            with open(path, "a") as f:
                f.write(text)
            return True, "ok"
        except Exception as e:
            return False, str(e)

    def read_text(self, filename):
        """读文本。"""
        if not self._mounted:
            return False, "not-mounted"
        try:
            path = self.mount_point + "/" + filename
            with open(path, "r") as f:
                return True, f.read()
        except Exception as e:
            return False, str(e)

    def get_capacity(self):
        """获取容量信息。"""
        if not self._mounted:
            return None
        try:
            stat = uos.statvfs(self.mount_point)
            block_size = stat[0]
            total_blocks = stat[2]
            free_blocks = stat[3]
            total = block_size * total_blocks
            free = block_size * free_blocks
            used = total - free
            return {
                "total_bytes": total,
                "used_bytes": used,
                "free_bytes": free,
            }
        except Exception:
            return None

    def log_line(self, filename, message):
        """追加带时间戳的一行日志。"""
        if not self._mounted:
            return False, "not-mounted"
        ts = time.localtime()
        time_str = "{}-{:02d}-{:02d} {:02d}:{:02d}:{:02d}".format(
            ts[0], ts[1], ts[2], ts[3], ts[4], ts[5]
        )
        line = "[{}] {}\n".format(time_str, message)
        return self.append_text(filename, line)

    def __enter__(self):
        self.mount()
        return self

    def __exit__(self, exc_type, exc, tb):
        self.unmount()
        return False
