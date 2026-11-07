"""ADB cho tool câu cá: thêm đo giờ chụp và lệnh bấm qua một shell mở sẵn."""

from __future__ import annotations

import struct
import subprocess
import time

import cv2
import numpy as np

from fishing_tool import paths  # noqa: F401
from gift_tool.adb_client import NO_WINDOW, AdbClient


class FishAdb(AdbClient):
    def __init__(self):
        super().__init__()
        self._shell: subprocess.Popen | None = None

    def timed_screenshot(self):
        """(ảnh, giờ bắt đầu chụp, giờ nhận xong). Ảnh thực ra được chụp ở giữa hai mốc này."""
        started = time.time()
        img = self.screenshot()
        return img, started, time.time()

    def frames(self):
        """Ảnh raw liên tiếp từ một lệnh screencap không tắt.

        Mỗi lần chụp PNG phải khởi động lại adb, trên máy này khoảng 0,4 giây, máy chậm khoảng 0,7 giây.
        Giữ screencap chạy thì ảnh về khoảng 0,17 giây/khung. Dùng lúc chờ cá cắn: thanh vàng hiện có nửa
        giây là phải bấm. `started` là lúc bắt đầu nhận khung, `ended` là lúc nhận xong.
        """
        if not self.serial:
            self.ensure_device()
        proc = subprocess.Popen(
            [self.adb, "-s", self.serial, "exec-out", "sh", "-c", "while true; do screencap; done"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            creationflags=NO_WINDOW,
        )
        try:
            while True:
                started = time.time()
                # Bốn số: rộng, cao, định dạng, không gian màu. Bỏ số thứ tư thì khung sau lệch 4 byte và luồng đứt.
                header = _read_exact(proc.stdout, 16)
                if header is None:
                    return
                width, height, fmt, _colorspace = struct.unpack("<IIII", header)
                if fmt != 1 or not (16 <= width <= 4096 and 16 <= height <= 4096):
                    return
                pixels = _read_exact(proc.stdout, width * height * 4)
                if pixels is None:
                    return
                yield decode_raw_frame(pixels, width, height), started, time.time()
        finally:
            proc.kill()
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                pass

    def _ensure_shell(self) -> subprocess.Popen:
        if self._shell is not None and self._shell.poll() is None:
            return self._shell
        if not self.serial:
            self.ensure_device()
        self._shell = subprocess.Popen(
            [self.adb, "-s", self.serial, "shell"],
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=NO_WINDOW,
        )
        return self._shell

    def tap_fast(self, x: int, y: int) -> None:
        """Bấm qua shell đã mở, bớt thời gian khởi động adb ở mỗi cú bấm. Hỏng thì bấm kiểu thường."""
        try:
            shell = self._ensure_shell()
            shell.stdin.write(f"input tap {int(x)} {int(y)}\n".encode())
            shell.stdin.flush()
        except (OSError, ValueError):
            self._shell = None
            self.tap(x, y)

    def close(self) -> None:
        shell, self._shell = self._shell, None
        if shell is None:
            return
        try:
            shell.stdin.write(b"exit\n")
            shell.stdin.flush()
        except (OSError, ValueError):
            pass
        try:
            shell.wait(timeout=3)
        except subprocess.TimeoutExpired:
            shell.kill()


def decode_raw_frame(pixels: bytes, width: int, height: int):
    """Ảnh BGR từ phần điểm ảnh của screencap raw (mỗi điểm R, G, B, A)."""
    view = np.frombuffer(pixels, np.uint8, width * height * 4).reshape(height, width, 4)
    return cv2.cvtColor(view, cv2.COLOR_RGBA2BGR)


def _read_exact(stream, count: int) -> bytes | None:
    buf = bytearray()
    while len(buf) < count:
        chunk = stream.read(count - len(buf))
        if not chunk:
            return None
        buf += chunk
    return bytes(buf)
