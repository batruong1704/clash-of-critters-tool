"""Chạy luồng thật trên emulator với vài UID và chia thời gian từng UID theo loại việc.

Chạy: py -3 tools/profile_flow.py 42270070 42270085
Cần emulator đang mở và không có lượt quét nào khác chạy cùng lúc.
"""

from __future__ import annotations

import sys
import threading
import time
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from gift_tool.adb_client import AdbClient  # noqa: E402
from gift_tool.flow import Runner  # noqa: E402
from gift_tool.vision import Finder  # noqa: E402

ADB_TIMED = {"screenshot": "chụp", "tap": "bấm/gõ", "input_text": "bấm/gõ", "clear_text": "bấm/gõ"}
FINDER_TIMED = ("find", "locate", "find_below")


class Meter:
    def __init__(self):
        self.spent = defaultdict(float)
        self.calls = defaultdict(int)

    def reset(self):
        self.spent.clear()
        self.calls.clear()

    def add(self, key: str, seconds: float):
        self.spent[key] += seconds
        self.calls[key] += 1


class TimedAdb:
    def __init__(self, inner: AdbClient, meter: Meter):
        self._inner = inner
        self._meter = meter

    def __getattr__(self, name):
        target = getattr(self._inner, name)
        label = ADB_TIMED.get(name)
        if label is None:
            return target

        def timed(*args, **kwargs):
            started = time.perf_counter()
            try:
                return target(*args, **kwargs)
            finally:
                self._meter.add(label, time.perf_counter() - started)
                if name == "screenshot":
                    self._meter.add("_ảnh", 0.0)

        return timed


class TimedFinder:
    def __init__(self, inner: Finder, meter: Meter):
        self._inner = inner
        self._meter = meter

    def __getattr__(self, name):
        target = getattr(self._inner, name)
        if name not in FINDER_TIMED:
            return target

        def timed(*args, **kwargs):
            started = time.perf_counter()
            try:
                return target(*args, **kwargs)
            finally:
                self._meter.add("so ảnh", time.perf_counter() - started)

        return timed


def main():
    uids = sys.argv[1:]
    if not uids:
        raise SystemExit("Cách dùng: profile_flow.py <uid> [<uid> ...]")
    meter = Meter()
    adb = AdbClient()
    adb.ensure_device()
    runner = Runner(TimedAdb(adb, meter), TimedFinder(Finder(), meter), lambda m: None, threading.Event(), print)

    original_pause = runner._pause

    def timed_pause(low, high):
        started = time.perf_counter()
        original_pause(low, high)
        meter.add("nghỉ cố định", time.perf_counter() - started)

    runner._pause = timed_pause

    rows = []
    for uid in uids:
        meter.reset()
        runner._clock = time.time()
        started = time.perf_counter()
        status, note, _ = runner.process_one(uid)
        total = time.perf_counter() - started
        accounted = sum(v for k, v in meter.spent.items() if not k.startswith("_"))
        rows.append((uid, status, total, dict(meter.spent), dict(meter.calls), total - accounted))
        print(f"\n=== {uid}: {status} ({note}) {total:.1f}s ===")
        for key in ("chụp", "bấm/gõ", "so ảnh", "nghỉ cố định"):
            calls = meter.calls.get(key, 0)
            spent = meter.spent.get(key, 0.0)
            each = f", {spent / calls * 1000:.0f} ms/lần" if calls else ""
            print(f"  {key:13} {spent:5.1f}s  {spent / total * 100:3.0f}%  ({calls} lần{each})")
        rest = total - accounted
        print(f"  {'còn lại':13} {rest:5.1f}s  {rest / total * 100:3.0f}%  (gồm chờ game tải, python)\n")
        # Sau mỗi UID, tự về ô nhập như luồng thật.
        if not runner._search_ready(adb.screenshot()):
            runner._open_uid_field()

    print("Tổng:", f"{sum(r[2] for r in rows):.1f}s cho {len(rows)} UID")


if __name__ == "__main__":
    main()
