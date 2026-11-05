"""Chạy vòng câu thật từ dòng lệnh, không cần mở cửa sổ.

Chạy từ thư mục fishing-event: py -3 tools/run_live.py [số_lượt] [hệ_số]   (Ctrl+C để dừng)
"""

import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fishing_tool.device import FishAdb  # noqa: E402
from fishing_tool.flow import Runner  # noqa: E402


def main() -> None:
    casts = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    multiplier = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    adb = FishAdb()
    adb.ensure_device()
    stop = threading.Event()
    t0 = time.time()
    runner = Runner(adb, lambda text: print(f"[{time.time() - t0:5.1f}s] {text}", flush=True), stop, casts, multiplier)
    try:
        runner.run()
    except KeyboardInterrupt:
        stop.set()


if __name__ == "__main__":
    main()
