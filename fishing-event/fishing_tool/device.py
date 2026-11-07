"""ADB cho tool câu cá: thêm đo giờ chụp và lệnh bấm qua một shell mở sẵn."""

from __future__ import annotations

import struct
import subprocess
import threading
import time

import cv2
import numpy as np

from fishing_tool import paths  # noqa: F401
from gift_tool.adb_client import NO_WINDOW, AdbClient

# screencap thô: 4 số (rộng, cao, định dạng, không gian màu) rồi điểm RGBA.
_RAW_HEADER = 16
_FRAME_WAIT = 1.5


def decode_screencap(data: bytes):
    """Ảnh BGR từ một khung screencap thô. Sai đầu khung thì None."""
    if len(data) < _RAW_HEADER:
        return None
    width, height, fmt, _space = struct.unpack_from("<IIII", data, 0)
    if fmt != 1 or not (2 <= width <= 4096 and 2 <= height <= 4096):
        return None
    count = width * height * 4
    if len(data) < _RAW_HEADER + count:
        return None
    pixels = np.frombuffer(data, dtype=np.uint8, count=count, offset=_RAW_HEADER)
    return cv2.cvtColor(pixels.reshape(height, width, 4), cv2.COLOR_RGBA2BGR)


class _BiteStream:
    """screencap chạy mãi, mỗi khung là một ảnh thô. Ảnh PNG mỗi lần phải mở lệnh mới."""

    def __init__(self, adb: str, serial: str):
        self.dead = False
        self._closed = False
        self._eof = False
        self._buf = bytearray()
        self._cond = threading.Condition()
        self.proc = subprocess.Popen(
            [adb, "-s", serial, "exec-out", "sh", "-c", "while true; do screencap; done"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            creationflags=NO_WINDOW,
        )
        self._thread = threading.Thread(target=self._pump, daemon=True)
        self._thread.start()

    def frame(self):
        """(ảnh, lúc bắt đầu chờ khung, lúc nhận xong). Hỏng thì None và đánh dấu chết."""
        started = time.time()
        header = self._take(_RAW_HEADER, started + _FRAME_WAIT)
        if header is None:
            self.dead = True
            return None
        width, height, fmt, _space = struct.unpack("<IIII", header)
        if fmt != 1 or not (2 <= width <= 4096 and 2 <= height <= 4096):
            self.dead = True
            return None
        pixels = self._take(width * height * 4, time.time() + _FRAME_WAIT)
        if pixels is None:
            self.dead = True
            return None
        image = decode_screencap(header + pixels)
        if image is None:
            self.dead = True
            return None
        return image, started, time.time()

    def close(self) -> None:
        self._closed = True
        proc = self.proc
        if proc.poll() is None:
            proc.kill()
        with self._cond:
            self._eof = True
            self._cond.notify_all()
        self._thread.join(timeout=0.5)

    def _pump(self) -> None:
        try:
            while not self._closed:
                chunk = self.proc.stdout.read(1 << 16)
                if not chunk:
                    break
                with self._cond:
                    self._buf.extend(chunk)
                    self._cond.notify_all()
        except OSError:
            pass
        finally:
            with self._cond:
                self._eof = True
                self._cond.notify_all()

    def _take(self, count: int, deadline: float) -> bytes | None:
        with self._cond:
            while len(self._buf) < count and not self._eof and not self._closed:
                left = deadline - time.time()
                if left <= 0:
                    return None
                self._cond.wait(left)
            if len(self._buf) < count:
                return None
            out = bytes(self._buf[:count])
            del self._buf[:count]
            return out


class FishAdb(AdbClient):
    def __init__(self):
        super().__init__()
        self._shell: subprocess.Popen | None = None
        self._bite: _BiteStream | None = None

    def timed_screenshot(self):
        """(ảnh, giờ bắt đầu chụp, giờ nhận xong). Ảnh thực ra được chụp ở giữa hai mốc này."""
        started = time.time()
        img = self.screenshot()
        return img, started, time.time()

    def bite_frame(self):
        """Một khung từ luồng screencap đang chạy. None khi luồng hỏng."""
        if not self.serial:
            self.ensure_device()
        if self._bite is None or self._bite.dead:
            self.close_bite()
            try:
                self._bite = _BiteStream(self.adb, self.serial)
            except OSError:
                return None
        return self._bite.frame()

    def close_bite(self) -> None:
        stream, self._bite = self._bite, None
        if stream is not None:
            stream.close()

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
        self.close_bite()
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
