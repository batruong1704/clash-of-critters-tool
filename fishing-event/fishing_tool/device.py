"""ADB cho tool câu cá: thêm đo giờ chụp và lệnh bấm qua một shell mở sẵn."""

from __future__ import annotations

import subprocess
import time

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
