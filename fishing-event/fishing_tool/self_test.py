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
    read_flash,
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
    from fishing_tool.predictor import Tracker, aim_radius

    check("vùng 147 nhắm 55% nửa vùng", aim_radius(147), 147 / 2 * 0.55)
    check("vùng 109 vẫn tính là thanh rộng", aim_radius(109), 109 / 2 * 0.55)
    check("vùng 73 giữ 40% giữa", aim_radius(73), 73 / 2 * 0.40)
    check("vùng 36 giữ 40% giữa", aim_radius(36), 36 / 2 * 0.40)
    check("vùng hẹp không rộng hơn mức đã đo", aim_radius(36, 5), 5.0)
    check("vùng rộng không bị mức đo hẹp kéo lại", aim_radius(147, 12), 147 / 2 * 0.55)

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
        check("nhớ: chưa đo độ trễ máy", again.tap_delay(), None)
        again.set_tap_delay(0.9)
        check("nhớ: độ trễ máy kẹp trong 0,15–0,70 và đọc lại được", Memory(path).tap_delay(), 0.70)
        check("nhớ: hồ sơ máy trống khi chưa câu", (again.flash_count, again.brackets, again.shot_dur), (0, [], None))
        again.set_profile(flash_count=250, brackets=[(0.2, 0.3), (0.22, 0.33)], shot_dur=0.65, white_base=0.15)
        back = Memory(path)
        check(
            "nhớ: hồ sơ máy đọc lại được, số lần chữ nổ chặn ở 100",
            (back.flash_count, back.brackets, back.shot_dur, back.white_base),
            (100, [(0.2, 0.3), (0.22, 0.33)], 0.65, 0.15),
        )
        check("nhớ: chưa có cú dò trúng thì chưa có lệch nhắm", back.aim_bias(), None)
        back.record(0.25, True, 36, 230, xe=-0.05)
        check("nhớ: một cú dò trúng đã cho lệch nhắm", back.aim_bias(), (-0.05, 1))
        for xe in (-0.04, -0.06, -0.15, 0.05):
            back.record(0.25, True, 36, 230, xe=xe)
        check("nhớ: lệch nhắm là trung vị các cú dò trúng, đọc lại được", Memory(path).aim_bias(), (-0.05, 5))
        for _ in range(12):
            back.record(0.25, True, 36, 230, xe=0.08)
        check("nhớ: lệch dương kẹp ở +0,02", back.aim_bias(), (0.02, 12))

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

    from fishing_tool.flow import (
        GOLD_LOOK,
        HIT_SETTLE,
        RESULT_SAMPLES,
        _flash_age,
        _hold_hit,
        _pick_gold,
        _pointer_at,
        _same_zone,
        _stop_gold_samples,
        _zone_link,
    )

    check("cùng thanh khi mép giữ nguyên", _same_zone((237, 282), (236, 382)), True)
    check("cùng thanh khi cả hai mép trôi 27px", _same_zone((290, 373), (317, 400)), True)
    check("thanh mới gần như không chồng", _same_zone((219, 329), (326, 473)), False)
    check("thanh mới lệch tâm xa", _same_zone((383, 492), (284, 430)), False)
    check("thanh mới khi tâm nhảy 42px dù còn chồng", _same_zone((412, 521), (370, 480)), False)
    check("mép nhảy mà mồi ở xa là thanh mới", _same_zone((297, 406), (307, 453), 213), False)
    check("mồi che mép thì vẫn cùng thanh", _same_zone((292, 343), (292, 365), 364), True)
    check("cùng thanh vì mép phải giữ", _zone_link((411, 447), (365, 438)), "mep_phai")
    check("chưa đo được lệch thì vẫn chờ", _hold_hit(11.2, 10.0, None, 73), True)
    check("hết giờ chờ dù không đo được lệch", _hold_hit(10.0 + HIT_SETTLE + 0.05, 10.0, None, 73), False)
    check("hai mép đổi thì là thanh mới", _zone_link((412, 521), (370, 480)), "thanh_moi")
    check("nội suy mồi giữa hai mẫu", _pointer_at([(0.0, 0.0), (0.4, 100.0)], 0.1), 25.0)
    # Phiên 02:06 lượt 5 cú 1: ảnh trước cách 0,9s, ảnh sau là thanh mới đã bị lọc, chỉ còn ảnh cách 0,012s.
    lone = [(82.11, 486.0), (82.77, 430.0), (83.43, 282.0), (84.339, 334.5)]
    near = _pointer_at(lone, 84.351, 227.0)
    check("ảnh sát giờ bấm tới thì chạy tiếp theo vận tốc", near is not None and abs(near - 337.2) < 0.5, True)
    check("không có vận tốc mà ảnh gần như trùng giờ vẫn nhận", _pointer_at(lone, 84.351), 334.5)
    check("không có vận tốc, ảnh cách 0,15s thì chịu", _pointer_at(lone, 84.49), None)
    check("ảnh cách quá NEAR_SAMPLE thì chịu", _pointer_at(lone, 84.65, 227.0), None)
    # Phiên 02:43 cú 1: hai ảnh 464 → 528 đi sang phải, kéo thẳng 0,43s nữa ra 610. Mồi nảy ở 536 nên phải là 462.
    bounce = [(9.90, 382.0), (10.24, 464.0), (10.58, 528.0)]
    folded = _pointer_at(bounce, 11.01, -227.0)
    check("kéo dài qua đầu thanh thì gấp lại", folded is not None and abs(folded - 462.0) < 2.0, True)
    # Lượt 6 cú 4: hai ảnh kề cách 0,72s kẹp lấy giờ tới, ngưỡng cũ 0,70 bỏ qua.
    pair = [(118.058, 266.5), (119.235, 416.5), (119.96, 307.0)]
    got = _pointer_at(pair, 119.273, 224.0)
    check("hai ảnh cách 0,72s vẫn nội suy", got is not None and abs(got - 410.8) < 0.5, True)
    check("ảnh busy xen giữa (cách 1,3s) không nội suy", _pointer_at([(10.0, 300.0), (11.3, 420.0)], 10.65), None)
    from fishing_tool.flow import _other_bar

    check("mẫu sang thanh mới bị loại", _other_bar((322, 469), (322, 431), 305.0), True)
    check("mẫu cùng thanh được giữ", _other_bar((368, 515), (368, 515), 440.0), False)
    check("thiếu mốc thì coi như cùng thanh", _other_bar((None, None), (368, 515), 440.0), False)
    check("ảnh busy không đọc được vùng (0, 0) thì giữ mẫu", _other_bar((368, 515), (0, 0), 440.0), False)

    import threading

    from fishing_tool.flow import Runner
    from fishing_tool.vision import Scene, Slider

    check("vệt trắng mới nổ", _flash_age(0.41, 0), (0.0, 0.10))
    check("vệt trắng khung thứ tư", _flash_age(0.30, 0), (0.10, 0.13))
    check("vệt trắng đang tắt", _flash_age(0.16, 0), (0.13, 0.30))
    check("chỉ còn chữ Great", _flash_age(0.12, 8000), (0.25, 0.90))
    check("thanh thường không phải chữ nổ", _flash_age(0.12, 300), None)
    check("máy có nền sáng thì vệt mờ chưa tính", _flash_age(0.16, 0, base=0.13), None)

    learn = Runner(object(), lambda _text: None, threading.Event(), 1, learn=False)
    check("độ trễ mặc định 0,30s", learn._latency, 0.30)
    learn._learn_delay(0.48, 0.60)
    check("máy chậm: mỗi lần nhích tối đa 0,08s", learn._latency, 0.38)
    learn._learn_delay(0.48, 0.60)
    learn._learn_delay(0.48, 0.60)
    check("máy chậm: dừng ở mép khoảng", learn._latency, 0.48)
    learn._learn_delay(0.40, 0.55)
    check("đang trong khoảng thì giữ", learn._latency, 0.48)
    learn._learn_delay(0.10, 0.30)
    check("thấy chữ sớm thì hạ xuống", learn._latency, 0.40)
    check("độ trễ lệnh không tách vùng rộng hẹp", learn._command_latency(), 0.40)
    slipped = {"err_px": -1.4, "t_lenh": 1.0, "tre": 0.40, "vung_lo": 300, "vung_hi": 336}
    learn._nudge_from_miss(slipped)
    check("trượt giữa vùng: dò muộn hơn trước", (learn._latency_nudge, learn._probe), (0.10, True))
    learn._miss_streak = 1
    learn._nudge_from_miss(slipped)
    check("trượt lần hai: dò sớm hơn", learn._latency_nudge, -0.10)
    learn._miss_streak = 2
    learn._nudge_from_miss(slipped)
    check("trượt lần ba: dò xa hơn", learn._latency_nudge, 0.20)
    learn._flash_seen = 3
    learn._miss_streak = 0
    sure = dict(slipped, van_toc=230.0, an=7.2)
    learn._nudge_from_miss(sure)
    check("độ trễ đã chắc: trượt sát tâm thì dò âm một bán kính ăn (7,2+4px)/230", (learn._latency_nudge, learn._probe), (-0.049, True))
    learn._miss_streak = 1
    learn._nudge_from_miss(sure)
    check("cú dò thứ hai sang phía dương", learn._latency_nudge, 0.049)
    learn._miss_streak = 2
    learn._nudge_from_miss(sure)
    check("cú dò thứ ba âm gấp đôi", learn._latency_nudge, -0.097)
    learn._latency_nudge = -0.049
    learn._miss_streak = 0
    learn._pending_tap = {"time": 5.0, "total": 0.35, "width": 36, "speed": 240, "first": False}
    learn._cast_tap_log = [dict(sure, ket_qua_bam=None, tre=0.351, hoc=0.40, do=True, moc_lo=300, moc_hi=336, mau_tiep=[])]
    learn._remember(True)
    check("cú dò trúng khi độ trễ đã chắc: thành lệch nhắm, độ trễ chữ nổ giữ nguyên", (learn._bias, learn._latency), (-0.049, 0.40))
    learn._latency_nudge = 0.0
    check("lệch nhắm cộng vào độ trễ lệnh", round(learn._command_latency(), 3), 0.351)
    learn._bias = 0.0
    learn._flash_seen = 30
    learn._learn_delay(0.10, 0.20)
    check("đã thấy chữ nổ 30 lần: mỗi lần chỉ nhích 0,02s", learn._latency, 0.38)
    learn._latency = 0.40
    learn._flash_seen = 0
    from fishing_tool.flow import _delay_target

    kept: list = []
    check("một khoảng chữ nổ: dùng nguyên khoảng", _delay_target(kept, (0.20, 0.33)), (0.20, 0.33))
    got = _delay_target(kept, (0.21, 0.35))
    check("hai khoảng: nhắm giữa phần giao 0,21–0,33", (round(got[0], 3), round(got[1], 3)), (0.26, 0.28))
    got = _delay_target(kept, (0.50, 0.60))
    check("khoảng lạc không giao: bỏ khoảng cũ", (got, len(kept)), ((0.50, 0.60), 1))
    learn._pending_tap = {"time": 5.0, "total": 0.30, "width": 36, "speed": 240, "first": False}
    learn._cast_tap_log = [dict(slipped, ket_qua_bam=None, tre=0.30, do=True, moc_lo=300, moc_hi=336, mau_tiep=[])]
    learn._remember(True)
    check("cú dò trúng thì độ trễ máy dời theo", learn._latency, 0.34)

    # Ảnh canh lúc chữ nổ (0,34s sau lệnh) còn thấy thanh cũ, sau đó thanh đổi: cú bấm tới muộn hơn 0,34s.
    late = Runner(object(), lambda _text: None, threading.Event(), 1, learn=False)
    late._tapped_zone = True
    late._tap_at = 100.0
    late._zone_anchor = (300, 410)
    old_bar = Scene("slider", "purple", {"slider": Slider(300, 410, 350.0), "flash": (0.10, 0)})
    check("thanh cũ chưa nổ chữ: chưa chốt", late._flash_check(old_bar, 100.2, 100.56), False)
    check("ghi mốc cú bấm tới muộn hơn", late._flash_lo is not None and abs(late._flash_lo - 0.344) < 0.01, True)
    late._on_hit()
    check("trúng muộn thì tăng độ trễ máy", abs(late._latency - 0.364) < 0.01, True)
    # Vùng 36px bị mồi che đúng lúc chữ sắp nổ: ảnh busy không vệt trắng, không vùng. Cũng là "chưa nổ".
    late._tapped_zone = True
    late._tap_at = 150.0
    late._flash_lo = None
    hidden = Scene("busy", "purple", {"slider": Slider(None, None, None), "flash": (0.05, 0)})
    check("mồi che vùng hẹp, chưa nổ chữ: chưa chốt", late._flash_check(hidden, 150.2, 150.56), False)
    check("ảnh che ghi mốc dưới", late._flash_lo is not None and abs(late._flash_lo - 0.344) < 0.01, True)
    # Ảnh canh đã thấy thanh mới (0,60s sau lệnh): chữ nổ xong trước đó, độ trễ ≤ 0,33.
    late._latency = 0.50
    late._tapped_zone = True
    late._tap_at = 170.0
    late._flash_lo = None
    late._zone_anchor = (300, 410)
    new_bar = Scene("slider", "purple", {"slider": Slider(450, 486, 240.0), "flash": (0.10, 0)})
    check("thanh mới chưa phải chữ nổ", late._flash_check(new_bar, 170.46, 170.82), False)
    check("thanh mới ghi mốc trên", late._flash_hi is not None and abs(late._flash_hi - 0.334) < 0.01, True)
    late._brackets = []
    late._on_hit()
    check("thấy thanh mới sớm thì hạ độ trễ", abs(late._latency - 0.42) < 0.01, True)
    late._latency = 0.364
    late._brackets = []
    late._tapped_zone = True
    late._tap_at = 200.0
    burst = Scene("busy", "purple", {"slider": Slider(None, None, None), "flash": (0.42, 0)})
    check("chữ nổ là trúng", late._flash_check(burst, 200.25, 200.61), True)
    check("chữ nổ chốt cú bấm", late._tapped_zone, False)
    check("độ trễ nằm trong khoảng chữ nổ", abs(late._latency - 0.364) < 0.01, True)

    edge = Runner(object(), lambda _text: None, threading.Event(), 1, learn=False)
    edge._t0 = 0.0
    edge.tracker.add(0.8, 200)
    edge.tracker.add(1.5, 340)
    edge._zone = (180, 320)
    edge._pending_tap = {"time": 1.0, "total": 0.24, "width": 147, "speed": 200, "first": True}
    edge._cast_tap_log = [
        {
            "ket_qua_bam": None,
            "err_px": None,
            "t_lenh": 1.0,
            "tre": 0.24,
            "vung_lo": 180,
            "vung_hi": 320,
            "moc_lo": 180,
            "moc_hi": 320,
            "mau_sau_t": None,
            "mau_sau_moi": None,
            "mau_sau_lo": None,
            "mau_sau_hi": None,
            "mau_tiep": [],
        }
    ]
    edge._note_after_tap(1.5, 340.0, (180, 320))
    check("ảnh chuyển cảnh ghi được mồi", edge._cast_tap_log[0]["mau_sau_moi"], 340.0)
    edge._remember(True)
    check("chốt cú bấm xong ghi kết quả", edge._cast_tap_log[0]["ket_qua_bam"], "trung")
    check("chờ xác nhận khi mồi còn trong vùng", _hold_hit(11.2, 10.0, -8, 73), True)
    check("hết giờ chờ thì được gọi trượt", _hold_hit(10.0 + HIT_SETTLE + 0.05, 10.0, -8, 73), False)
    check("mồi ra khỏi vùng thì không chờ", _hold_hit(11.2, 10.0, -78, 36), False)

    check("gold đọc một lần", _pick_gold([1210]), 1210)
    check("gold +7 vẫn nhận", _pick_gold([7]), 7)
    check("gold +1 vẫn nhận", _pick_gold([1]), 1)
    check("gold +2 lặp vẫn nhận", _pick_gold([2, 2]), 2)
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
    check("thanh thường không có vệt trắng (video 640)", read_flash(frame(640))[0] < 0.14, True)
    check("vệt trắng lúc mới nổ (video 667)", read_flash(frame(667))[0] >= 0.33, True)
    check("vệt trắng lúc sắp tắt (video 672)", 0.14 <= read_scene(frame(672), templates).detail["flash"][0] < 0.22, True)
    check("sau chữ nổ thanh lại thường (video 680)", read_flash(frame(680))[0] < 0.14, True)

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
    # Tia sáng dính vào đỉnh chữ 4 lúc chữ đang nảy. Trước đọc thiếu chữ thành 58 (lượt +50 ngày 7/11 ghi 5).
    check("gold video 710, tia sáng dính chữ", read_gold(frame(710)), 548)
    check("gold video 712, tia sáng dính chữ", read_gold(frame(712)), 548)
    check("gold video 711, chữ dính tia sáng không đọc được thì bỏ ảnh", read_gold(frame(711)), None)
    check("không có gold ở video 760", read_gold(frame(760)), None)
    one = frame(722).copy()
    one[410:445, 520:575] = one[430, 650]
    check("gold một chữ số có dấu cộng", read_gold(one), 5)
    one[422:440, 400:428] = one[430, 650]
    check("gold một chữ số mất dấu cộng thì bỏ", read_gold(one), None)
    wide = frame(722).copy()
    wide[408:448, 520:640] = wide[430, 650]
    digit = frame(722)[408:446, 498:524]
    wide[408:446, 552:578] = digit
    check("gold hai chữ cách xa vẫn đủ", read_gold(wide), 55)

    _test_catch(check)
    _test_memory(check)
    _test_stop(check)

    print("XONG" if failed == 0 else f"{failed} mục lỗi")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
