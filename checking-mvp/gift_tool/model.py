"""Model: nối máy ảo, chạy nhận quà, rally, câu cá, chụp và kiểm tra nút.

Không biết cửa sổ. Presenter đưa callback log vào và nhận kết quả trả về.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

from gift_tool.adb_client import AdbClient
from gift_tool.flow import Runner
from gift_tool.paths import LOGS
from gift_tool.vision import Finder, draw_hits, imwrite

UID_MIN_LEN = 4
UID_MAX_LEN = 15
SCAN_COUNT_DEFAULT = 100
SCAN_COUNT_MAX = 5000
FISHING_DIR = Path(__file__).resolve().parent.parent.parent / "fishing-event"
RALLY_DIR = Path(__file__).resolve().parent.parent.parent / "auto-join-rally"
# Vòng đổi hệ số của game: x1, x2, x3, x5, x10, x20, x50, x100. Mỗi hệ số cần ảnh mẫu templates/mult_N.png.
FISHING_MULTIPLIERS = ("1", "2", "3", "5", "10", "20", "50")
FISHING_CASTS_DEFAULT = 10
FISHING_CASTS_MAX = 100000

PREVIEW_BUTTONS = (
    "search",
    "add",
    "apply",
    "visit",
    "gift",
    "select",
    "ok",
    "close",
    "missing_id",
    "friends",
    "community",
)


def parse_ids(text: str) -> tuple[list[str], list[str], int]:
    """Trả UID hợp lệ, dòng lỗi, và số ID trùng đã bỏ. Giữ thứ tự lần gặp đầu."""
    good, bad = [], []
    seen: set[str] = set()
    duplicated = 0
    chunks = text.replace(",", "\n").replace(";", "\n").splitlines()
    for chunk in chunks:
        # Dấu cách dính khi dán từ game hoặc bảng tính làm ADB gõ sai UID.
        token = "".join(chunk.split())
        if not token:
            continue
        if not (token.isdigit() and UID_MIN_LEN <= len(token) <= UID_MAX_LEN):
            bad.append(token)
            continue
        if token in seen:
            duplicated += 1
            continue
        seen.add(token)
        good.append(token)
    return good, bad, duplicated


def scan_ids(start: str, count: int) -> list[str]:
    """ID đầu, rồi cộng 1 cho mỗi lần quét. Giữ số chữ số ban đầu nếu có số 0 đứng trước."""
    width = len(start)
    first = int(start)
    ids = []
    for offset in range(count):
        uid = str(first + offset).zfill(width)
        if len(uid) > UID_MAX_LEN:
            break
        ids.append(uid)
    return ids


@dataclass
class CaptureResult:
    serial: str
    width: int
    height: int
    path: Path


@dataclass
class ButtonCheck:
    name: str
    score: float
    found: bool


@dataclass
class PreviewResult:
    serial: str
    width: int
    height: int
    checks: list[ButtonCheck]
    path: Path


class ToolModel:
    def __init__(self, finder: Finder | None = None):
        self.finder = finder or Finder()

    def open_adb(self) -> tuple[AdbClient, str]:
        adb = AdbClient()
        return adb, adb.ensure_device()

    def run_gifts(self, adb: AdbClient, ids: list[str], log, stop, detail):
        return Runner(adb, self.finder, log, stop, detail).run(ids)

    def run_rally(self, adb: AdbClient, log, stop):
        """Nạp tool rally lúc bấm chạy. Thiếu thư mục thì các tab kia vẫn mở được."""
        if str(RALLY_DIR) not in sys.path:
            sys.path.insert(0, str(RALLY_DIR))
        try:
            from rally_tool.flow import Runner as RallyRunner
        except ImportError as exc:
            raise RuntimeError(f"Không nạp được tool rally ở {RALLY_DIR}: {exc}") from exc
        return RallyRunner(adb, log, stop, self.finder).run()

    def open_fishing(self):
        """Nạp tool câu cá lúc bấm chạy. Thiếu thư mục thì các tab kia vẫn mở được."""
        if str(FISHING_DIR) not in sys.path:
            sys.path.insert(0, str(FISHING_DIR))
        try:
            from fishing_tool.device import FishAdb
            from fishing_tool.flow import Runner as FishRunner
        except ImportError as exc:
            raise RuntimeError(f"Không nạp được tool câu cá ở {FISHING_DIR}: {exc}") from exc
        adb = FishAdb()
        return adb, adb.ensure_device(), FishRunner

    def capture(self) -> CaptureResult:
        adb, serial = self.open_adb()
        shot = adb.screenshot()
        path = LOGS / "chup-thu.png"
        imwrite(path, shot)
        height, width = shot.shape[:2]
        return CaptureResult(serial, width, height, path)

    def preview(self) -> PreviewResult:
        adb, serial = self.open_adb()
        shot = adb.screenshot()
        hits = []
        checks = []
        for name in PREVIEW_BUTTONS:
            hit = self.finder.locate(shot, name)
            threshold = self.finder.templates[name][1]["threshold"]
            found = bool(hit.w) and hit.score >= threshold
            checks.append(ButtonCheck(name, hit.score, found))
            if found:
                hits.append(hit)
        path = LOGS / "kiem-tra.png"
        imwrite(path, draw_hits(shot, hits))
        height, width = shot.shape[:2]
        return PreviewResult(serial, width, height, checks, path)
