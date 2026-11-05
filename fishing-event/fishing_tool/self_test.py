"""Kiểm tra nhận màn hình trên ảnh và video có sẵn trong resource/. Không cần emulator.

Chạy: py -3 -m fishing_tool.self_test
"""

from __future__ import annotations

import glob
import sys

import cv2
import numpy as np

from fishing_tool.paths import RESOURCE, VIDEO
from fishing_tool.vision import (
    MULTIPLIERS,
    Templates,
    fish_tile_point,
    normalize,
    read_gold,
    read_multiplier,
    read_rods,
    read_scene,
)


def _png(prefix: str):
    path = glob.glob(str(RESOURCE / f"{prefix}*.png"))[0]
    img = cv2.imdecode(np.fromfile(path, np.uint8), cv2.IMREAD_COLOR)
    return normalize(img)


def _test_memory(check) -> None:
    import tempfile
    from pathlib import Path

    from fishing_tool.memory import Memory, consistent_latencies
    from fishing_tool.predictor import Tracker

    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "hoc.json"
        memory = Memory(path)
        check("nhớ: chưa có dữ liệu thì chưa kết luận", memory.latency(), None)
        for _ in range(10):
            memory.record(0.34, True, 120, 230, ok=[0.30, 0.32, 0.34, 0.36])
        found = memory.latency()
        check("nhớ: độ trễ tốt nhất", found is not None and abs(found[0] - 0.33) <= 0.03, True)
        again = Memory(path)
        found = again.latency()
        check("nhớ: đọc lại từ file", (len(again.taps), found is not None and abs(found[0] - 0.33) <= 0.03), (10, True))
        off = Memory(path, enabled=False)
        off.record(0.9, True)
        check("nhớ: tắt học thì không ghi", len(Memory(path).taps), 10)

    # Mồi chạy 200px/s từ 199. Bấm lúc t=1.0 thì mồi ở 199+200*(1.0+L). Vùng vàng 400-480 chứa mồi khi L trong 0.0-0.4
    # (rồi lại vào vùng ở L từ 0.93 sau khi nảy ở đầu thanh, ngoài lưới thử).
    tracker = Tracker()
    def pointer(when: float) -> float:  # sóng tam giác 199..532, 200px/s
        phase = (200 * when) % (2 * 333)
        return 199 + (phase if phase <= 333 else 2 * 333 - phase)

    for step in range(8):
        tracker.add(0.4 * step, pointer(0.4 * step))
    good = consistent_latencies(tracker, 1.0, (400, 480), True)
    check("nhớ: L khớp khi trúng", good is not None and min(good) >= 0.0 and max(good) <= 0.5, True)
    miss = consistent_latencies(tracker, 1.0, (400, 480), False)
    check("nhớ: L khớp khi trượt không chứa L trúng", miss is not None and not set(miss) & set(good or []), True)


def main() -> int:
    video = cv2.VideoCapture(str(VIDEO))

    def frame(index: int):
        video.set(cv2.CAP_PROP_POS_FRAMES, index)
        ok, img = video.read()
        if not ok:
            raise RuntimeError(f"Không đọc được khung {index}")
        return normalize(img)

    templates = Templates()
    failed = 0

    def check(name: str, got, want) -> None:
        nonlocal failed
        ok = got == want
        failed += 0 if ok else 1
        print(f"{'OK  ' if ok else 'LOI '} {name}: {got!r}" + ("" if ok else f" (cần {want!r})"))

    scenes = [
        ("sân (video 30)", frame(30), "yard"),
        ("pinball (video 215)", frame(215), "pinball"),
        ("pinball (ảnh 2)", _png("2."), "pinball"),
        ("sân (ảnh 1)", _png("1."), "yard"),
        ("chờ quăng (video 290)", frame(290), "idle"),
        ("chờ quăng (ảnh 3)", _png("3."), "idle"),
        ("chờ cá cắn (video 480)", frame(480), "wait"),
        ("chờ cá cắn (ảnh 4)", _png("4."), "wait"),
        ("Reel it in (video 612)", frame(612), "reel"),
        ("Reel it in (ảnh 5)", _png("5."), "reel"),
        ("thanh trượt (video 640)", frame(640), "slider"),
        ("thanh trượt (ảnh 6)", _png("6."), "slider"),
        ("Cool, chuyển cảnh (video 672)", frame(672), "busy"),
        ("Time's up (ảnh 9)", _png("9."), "timesup"),
        ("kết quả (video 722)", frame(722), "result"),
        ("kết quả (ảnh 7)", _png("7."), "result"),
    ]
    for name, img, want in scenes:
        check(name, read_scene(img, templates).kind, want)

    slider = read_scene(frame(640), templates).detail["slider"]
    check("vùng vàng video 640", (slider.lo // 5 * 5, slider.hi // 5 * 5), (290, 435))
    print(f"     mồi ở {slider.pointer:.0f}")

    check("ô câu cá trên pinball", fish_tile_point(frame(215), templates) is not None, True)
    check("sân không có ô câu cá", fish_tile_point(frame(30), templates), None)
    check("hệ số ảnh 3", read_multiplier(_png("3."), templates), 1)
    # Dán từng ảnh mẫu hệ số lên nền giả ở chỗ viên hệ số để chắc các hệ số không bị nhận nhầm với nhau (x1/x10/x100...).
    for value in MULTIPLIERS:
        if not templates.has(f"mult_{value}"):
            continue
        canvas = np.full((1280, 720, 3), 200, np.uint8)
        tpl = templates.images[f"mult_{value}"]
        h, w = tpl.shape[:2]
        x, y = 488 - w // 2, 985 - h // 2
        canvas[y : y + h, x : x + w] = tpl
        check(f"nhận hệ số x{value}", read_multiplier(canvas, templates), value)
    check("rod ảnh 3", read_rods(_png("3.")), 110)
    check("gold video 722", read_gold(frame(722)), 548)
    check("gold video 716", read_gold(frame(716)), 548)
    check("không có gold ở video 760", read_gold(frame(760)), None)

    _test_memory(check)

    print("XONG" if failed == 0 else f"{failed} mục lỗi")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
