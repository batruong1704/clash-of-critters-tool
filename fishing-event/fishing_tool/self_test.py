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
    POINTER_HI,
    POINTER_LO,
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

    # Mồi chạy 200px/s từ đầu thanh. Bấm lúc t=1.0 thì mồi ở POINTER_LO+200. Vùng vàng 400-480 chứa mồi
    # khi L trong khoảng ngắn sau đó (rồi lại vào vùng sau khi nảy, ngoài lưới thử).
    tracker = Tracker()
    span = POINTER_HI - POINTER_LO

    def pointer(when: float) -> float:  # sóng tam giác theo hai đầu thanh, 200px/s
        phase = (200 * when) % (2 * span)
        return POINTER_LO + (phase if phase <= span else 2 * span - phase)

    for step in range(8):
        tracker.add(0.4 * step, pointer(0.4 * step))
    good = consistent_latencies(tracker, 1.0, (400, 480), True)
    check("nhớ: L khớp khi trúng", good is not None and min(good) >= 0.0 and max(good) <= 0.5, True)
    miss = consistent_latencies(tracker, 1.0, (400, 480), False)
    check("nhớ: L khớp khi trượt không chứa L trúng", miss is not None and not set(miss) & set(good or []), True)

    from fishing_tool.flow import GOLD_LOOK, HIT_SETTLE, RESULT_SAMPLES, _hold_hit, _pick_gold, _same_zone, _stop_gold_samples

    check("cùng thanh khi mép giữ nguyên", _same_zone((237, 282), (236, 382)), True)
    check("cùng thanh khi cả hai mép trôi 27px", _same_zone((290, 373), (317, 400)), True)
    check("thanh mới gần như không chồng", _same_zone((219, 329), (326, 473)), False)
    check("thanh mới lệch tâm xa", _same_zone((383, 492), (284, 430)), False)
    check("chờ xác nhận khi mồi còn trong vùng", _hold_hit(11.2, 10.0, -8, 73), True)
    check("hết giờ chờ thì được gọi trượt", _hold_hit(10.0 + HIT_SETTLE + 0.05, 10.0, -8, 73), False)
    check("mồi ra khỏi vùng thì không chờ", _hold_hit(11.2, 10.0, -78, 36), False)

    check("gold đọc một lần", _pick_gold([1210]), 1210)
    check("gold một chữ số không nhận", _pick_gold([9]), 0)
    check("gold một chữ số lặp không nhận", _pick_gold([2, 2]), 0)
    check("gold lấy số đủ chữ", _pick_gold([210, 1210]), 1210)
    check("gold không để số 2 đè 118", _pick_gold([118, 118, 2, 2, 2, 2]), 118)
    check("gold dừng khi số lặp", _stop_gold_samples([118, 118], 0.1, 1), True)
    check("gold chữ số lẻ lặp không chặn", _stop_gold_samples([2, 2], 0.1, 1), False)
    check("gold chữ số lẻ hết giờ thì thôi", _stop_gold_samples([2, 2], GOLD_LOOK, 1), True)
    check("gold chưa thấy chữ thì chờ", _stop_gold_samples([], GOLD_LOOK - 0.1, 1), False)
    check("gold hết cửa sổ thì thôi", _stop_gold_samples([], GOLD_LOOK, 1), True)
    check("gold một lần đọc vẫn chụp thêm", _stop_gold_samples([548], 0.2, 1), False)
    check("gold chụp đủ thì dừng", _stop_gold_samples([548], 0.2, RESULT_SAMPLES), True)


def _test_stop(check) -> None:
    import threading
    import time

    from fishing_tool.flow import Runner, Stopped

    stop = threading.Event()
    notes: list[str] = []
    runner = Runner(object(), notes.append, stop, 3, learn=False)
    stop.set()

    def raises() -> bool:
        try:
            runner._check()
        except Stopped:
            return True
        return False

    runner._last_kind = "idle"
    check("dừng ngay khi chưa vào lượt", raises(), True)

    runner._cast_open = True
    runner._last_kind = "slider"
    check("đang câu thì chưa dừng", raises(), False)
    check("đang câu thì chưa dừng, lần hai", raises(), False)
    check("báo câu nốt một lần", notes.count("Đang câu dở. Câu nốt lượt này rồi dừng."), 1)

    runner._cast_open = False
    runner._last_kind = "result"
    runner._settle_since = None
    check("còn màn kết quả thì chưa dừng", raises(), False)

    runner._settle_since = time.time() - 30
    check("màn kết quả kẹt thì dừng", raises(), True)

    try:
        runner._on_idle(None, None, 0, 0)
        idle_stopped = False
    except Stopped:
        idle_stopped = True
    check("không quăng lượt mới sau khi dừng", idle_stopped, True)


def _test_catch(check) -> None:
    from fishing_tool.catch import classify

    cases = (
        ("7.", "Cá Mỏ Dài", "tim", None),
        ("8.", "Cá Chóa", "xanh", None),
    )
    for prefix, name, tone, _count in cases:
        hit = classify(_png(prefix))
        check(f"loài ảnh {prefix[0]}", (hit.label, hit.tone) if hit else None, (name, tone))

    folder = RESOURCE / "type_fish"
    candy = classify(normalize(cv2.imdecode(np.fromfile(folder / "kẹo.png", np.uint8), cv2.IMREAD_COLOR)))
    check("kẹo", (candy.label, candy.count, candy.tone) if candy else None, ("x767 kẹo", 767, "trang"))
    pinball = classify(normalize(cv2.imdecode(np.fromfile(folder / "pinball.png", np.uint8), cv2.IMREAD_COLOR)))
    check("pinball", (pinball.label, pinball.count, pinball.tone) if pinball else None, ("x3 pinball", 3, "trang"))
    both = classify(normalize(cv2.imdecode(np.fromfile(folder / "pinball-va-tui.png", np.uint8), cv2.IMREAD_COLOR)))
    check("pinball và túi mồi", (both.label, both.tone) if both else None, ("x3 pinball, x1 túi mồi", "trang"))
    from fishing_tool.catch import tone_for

    check("Cá Mập Địch phẩm đỏ", tone_for("Cá Mập Địch"), "do")

    from fishing_tool.catch import Catch
    from fishing_tool.flow import _choose_catch

    weak = Catch("Cá Pixel", "ca", "tim", None, 0.43)
    candy = Catch("kẹo", "keo", "trang", 9721, 0.54)
    card = Catch("Bạch Tuộc", "ca", "tim", None, 0.85)
    whale = Catch("Cá Mập Voi", "ca", "vang", None, 0.67)
    check("chốt thẻ cá, bỏ khung chuyển cảnh", _choose_catch([card, weak]).name, "Bạch Tuộc")
    check("không nhận khớp dưới sàn", _choose_catch([weak, candy]), None)
    check("thẻ cá điểm vừa vẫn nhận", _choose_catch([whale]).name, "Cá Mập Voi")


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

    _test_catch(check)
    _test_memory(check)
    _test_stop(check)

    print("XONG" if failed == 0 else f"{failed} mục lỗi")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
