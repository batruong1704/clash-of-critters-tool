"""Đọc các file vết `logs/*-vet.txt`, tính lại kết quả từng cú bấm thanh trượt và dò độ trễ thật của cú bấm.

Không tin dòng TRÚNG/TRƯỢT trong file vết vì bản cũ của tool hay báo TRÚNG nhầm: mồi đè lên vùng vàng làm vùng đọc
được hẹp đi, tool tưởng sang thanh mới. Ở đây kết quả được tính lại bằng cùng cách nhận thanh mới như `flow._same_zone`:
- Có mẫu sau cú bấm (cách ít nhất 0.3s để lệnh kịp tới game) rơi vào thanh mới, hoặc màn kết quả hiện ra: TRÚNG.
- Sau 0.9s vẫn là thanh cũ: TRƯỢT.
- Hết thanh trượt vì lý do khác (Time's up, quăng lại): bỏ qua cú đó.

Dò độ trễ: với mỗi cú bấm, khớp đường đi của mồi bằng mọi mẫu của thanh đó (cả trước lẫn sau cú bấm), rồi thử từng
độ trễ L và xem mồi có nằm trong vùng vàng ở giờ (lệnh bấm + L) khớp với trúng/trượt hay không. L tốt nhất cho biết
mồi thật sự bị "đóng băng" ở lúc nào so với giờ phát lệnh.

Chạy: py -3 tools/phan_tich.py            (chỉ in thống kê)
      py -3 tools/phan_tich.py --nhap     (xóa data/hoc.json và nạp lại từ các file vết)
Bỏ qua file có bias=+0.00 ở cú bấm đầu: đó là chạy mô phỏng, không phải game thật.
"""

from __future__ import annotations

import re
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from fishing_tool.flow import TAP_LATENCY, _same_zone  # noqa: E402
from fishing_tool.memory import MEMORY_FILE, ZONE_TRUST, Memory, consistent_latencies  # noqa: E402
from fishing_tool.paths import LOGS  # noqa: E402
from fishing_tool.predictor import Tracker  # noqa: E402

TAP = re.compile(r"\[\s*([\d.]+)\] BẤM lệnh t=([\d.]+) .*độ lệch=([+-][\d.]+) bias=([+-][\d.]+)")
SAMPLE = re.compile(r"mẫu t=([\d.]+) mồi=(\d+) vùng=(\d+)-(\d+)")
END = re.compile(r"màn (result|reel|idle|wait|timesup|busy)")
LANDING = 0.30  # mẫu chụp sau cú bấm chừng này mới có thể đã thấy thanh mới
MISS_AFTER = 0.90  # tool chỉ kết luận trượt sau khoảng này (TAP_COOLDOWN)


def parse(path: Path) -> list[dict]:
    taps: list[dict] = []
    known: tuple[int, int] | None = None
    session: list[tuple[float, float]] = []
    pending: dict | None = None

    def finish(hit: bool | None) -> None:
        nonlocal pending
        if pending is not None and hit is not None:
            pending["hit"] = hit
            taps.append(pending)
        pending = None

    for line in path.read_text(encoding="utf-8").splitlines():
        m = TAP.search(line)
        if m:
            finish(None)
            pending = {
                "t": float(m.group(2)),
                "total": float(m.group(3)) + float(m.group(4)),
                "width": (known[1] - known[0]) if known else 0,
                "known": known,
                "session": session,  # danh sách dùng chung, còn được thêm mẫu sau cú bấm
                "hit": None,
            }
            continue
        m = SAMPLE.search(line)
        if m:
            when, pointer = float(m.group(1)), float(m.group(2))
            zone = (int(m.group(3)), int(m.group(4)))
            new = known is None or not _same_zone(zone, known)
            if pending is not None and when >= pending["t"] + LANDING:
                before = pending["known"]
                if before is None or not _same_zone(zone, before):
                    finish(True)
                elif when >= pending["t"] + MISS_AFTER:
                    finish(False)
            if new:
                session = []
                known = zone
            else:
                known = (min(known[0], zone[0]), max(known[1], zone[1]))
            session.append((when, pointer))
            continue
        m = END.search(line)
        if m:
            finish(True if m.group(1) == "result" else None)
            known = None
            session = []
    for tap in taps:
        tap["session"] = list(tap["session"])
    return taps


def votes_for(tap: dict) -> list[float] | None:
    near = [s for s in tap["session"] if abs(s[0] - tap["t"]) <= 3.0]
    tracker = Tracker()
    for sample in near:
        tracker.add(*sample)
    return consistent_latencies(tracker, tap["t"], tap["known"], tap["hit"])


def calibrate(rows: list[dict]) -> None:
    """Thử từng độ trễ L, đếm số cú bấm mà 'mồi trong vùng ở lúc bấm + L' khớp với trúng/trượt."""
    usable = []
    for tap in rows:
        zone = tap["known"]
        near = [s for s in tap["session"] if abs(s[0] - tap["t"]) <= 3.0]
        if zone is None or len(near) < 6:
            continue
        tracker = Tracker()
        for sample in near:
            tracker.add(*sample)
        fit = tracker.fit()
        if fit is None or fit[2] > 40:
            continue
        usable.append((tap, tracker, zone))
    if not usable:
        print("\nChưa đủ cú bấm có đủ mẫu để dò độ trễ.")
        return
    print(f"\nDò độ trễ trên {len(usable)} cú bấm có đường mồi khớp tốt:")
    best = None
    for latency in np.arange(-0.30, 0.91, 0.02):
        right = 0
        for tap, tracker, zone in usable:
            pos = tracker.position(tap["t"] + latency)
            inside = abs(pos - (zone[0] + zone[1]) / 2) <= (zone[1] - zone[0]) / 2 * ZONE_TRUST
            right += inside == tap["hit"]
        rate = right / len(usable)
        best = max(best or (0, 0), (rate, latency))
        print(f"  L={latency:+.2f}s: đúng {right}/{len(usable)} ({100 * rate:.0f}%)")
    print(f"L tốt nhất {best[1]:+.2f}s. Bias tương ứng = {TAP_LATENCY - best[1]:+.2f}s.")


def main() -> None:
    rows: list[dict] = []
    for path in sorted(LOGS.glob("*-vet.txt")):
        taps = parse(path)
        if not taps or abs(taps[0]["total"]) < 0.01:
            continue
        rows.extend(taps)
    if not rows:
        print("Chưa có dữ liệu.")
        return

    hits = sum(t["hit"] for t in rows)
    print(f"{len(rows)} cú bấm, trúng {hits} ({100 * hits / len(rows):.0f}%)")

    by_total: dict[float, list[bool]] = defaultdict(list)
    for t in rows:
        by_total[round(t["total"], 2)].append(t["hit"])
    print("\nTheo tổng độ lệch giờ (giây):")
    for total in sorted(by_total):
        v = by_total[total]
        print(f"  {total:+.2f}: {sum(v):2d}/{len(v):2d} trúng")

    by_width: dict[int, list[bool]] = defaultdict(list)
    for t in rows:
        by_width[t["width"] // 25 * 25].append(t["hit"])
    print("\nTheo độ rộng vùng vàng (px):")
    for width in sorted(by_width):
        v = by_width[width]
        print(f"  {width}-{width + 24}: {sum(v):2d}/{len(v):2d} trúng")

    calibrate(rows)

    if "--nhap" in sys.argv:
        MEMORY_FILE.unlink(missing_ok=True)
        memory = Memory()
        for t in rows:
            memory.record(t["total"], t["hit"], t["width"], None, ok=votes_for(t))
        found = memory.latency()
        print(f"\nĐã nạp lại data/hoc.json: {memory.summary()}, độ trễ tốt nhất {found[0]:.2f}s." if found else "\nĐã nạp lại data/hoc.json.")


if __name__ == "__main__":
    main()
