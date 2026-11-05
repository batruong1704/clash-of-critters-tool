"""Vòng tự câu cá. Mỗi lượt: chọn hệ số, quăng cần, chờ cá cắn, bấm Reel it in,
bấm đúng lúc mồi vào vùng vàng, đọc màn kết quả rồi bấm để về màn câu.

Tool chỉ nhìn ảnh ADB và bấm qua ADB. Không đụng chuột Windows.
"""

from __future__ import annotations

import csv
import random
import time
from dataclasses import dataclass, field
from datetime import datetime

from fishing_tool.device import FishAdb
from fishing_tool.memory import Memory, consistent_latencies
from fishing_tool.paths import LOGS
from fishing_tool.predictor import Tracker
from fishing_tool.vision import (
    BADGE,
    BUTTON,
    MULTIPLIERS,
    REF_H,
    REF_W,
    Scene,
    Templates,
    fish_tile_point,
    normalize,
    read_gold,
    read_multiplier,
    read_rods,
    read_scene,
)

BUTTON_XY = (int(BUTTON[0] * REF_W), int(BUTTON[1] * REF_H))
BADGE_XY = (int(BADGE[0] * REF_W), int(BADGE[1] * REF_H))
# Bấm bỏ qua màn kết quả. Đo trên máy thật: bấm giữa màn (360, 640), (360, 900) không đóng được màn
# "New Team Record". Bấm (360, 1100), phía trên nút câu đang tối, thì đóng. Tránh nút X ở đáy (y > 1180).
DISMISS_POINTS = ((130, 1100), (590, 1100), (360, 1100))
# (130, 1100) đóng được màn kết quả mà không rơi vào nút câu, nên không vô tình quăng thêm. (360, 1100) chỉ là
# phương án cuối: bấm trúng lúc màn đã đóng thì nó quăng cần.
DISMISS_RETRY = 5.0

# Từ lúc phát lệnh bấm tới lúc game nhận (khởi động `input` trên emulator). Đo lại nếu hay trượt.
TAP_LATENCY = 0.22
# Ảnh được chụp ở khoảng này của thời gian lệnh chụp (0 là lúc bắt đầu, 1 là lúc nhận xong).
CAPTURE_FRACTION = 0.40
# Sau cú bấm, ảnh đầu có thể chụp trước khi game nhận kịp. Bỏ qua quyết định trong khoảng này.
TAP_COOLDOWN = 0.9
# Độ trễ của cú bấm, từ lúc phát lệnh tới lúc game nhận (giây). Đo trên 52 cú bấm thật bằng tools/phan_tich.py:
# đúng 95% ở khoảng 0.30s khi coi vùng ăn thật là 70% nửa vùng vàng (memory.ZONE_TRUST). Tool tự dò lại số này sau mỗi cú bấm và nhớ qua các phiên.
BASE_LATENCY = 0.30
# Thử lệch thêm khi trượt liên tiếp (giây, dương là bấm muộn hơn).
MISS_OFFSETS = (0.0, 0.05, -0.05, 0.10, -0.10, 0.15, -0.15)
MIN_SAMPLES_BEFORE_TAP = 5
MAX_SAMPLES_BEFORE_TAP = 7
ZONE_SHIFT = 12

CAST_RETRY_AFTER = 3.0
CAST_MAX_RETRIES = 3
MULT_MAX_TAPS = 10
UNKNOWN_LIMIT = 12
WAIT_WARN = 60.0
NAV_LOAD = 3.0
TIMESUP_TAP_AFTER = 6.0
RESULT_SAMPLES = 4


class Stopped(Exception):
    pass


class Finished(Exception):
    pass


@dataclass
class Stats:
    casts: int = 0
    caught: int = 0
    failed: int = 0
    gold: int = 0
    taps: int = 0
    rods: int | None = None
    rows: list = field(default_factory=list)


class Runner:
    def __init__(self, adb: FishAdb, log, stop, casts: int, multiplier: int = 1, on_stats=None, learn: bool = True):
        if multiplier not in MULTIPLIERS:
            raise ValueError(f"Hệ số phải là một trong {MULTIPLIERS}")
        self.templates = Templates()
        if not self.templates.has(f"mult_{multiplier}"):
            raise ValueError(
                f"Chưa có ảnh mẫu của hệ số x{multiplier} (templates/mult_{multiplier}.png) nên tool không nhận ra được nó. "
                "Vòng đổi hệ số của game hiện có x1, x2, x3, x5, x10, x20, x50, x100."
            )
        self.adb = adb
        self.log = log
        self.stop = stop
        self.target = casts
        self.multiplier = multiplier
        self.on_stats = on_stats or (lambda stats: None)
        self.stats = Stats()
        self.tracker = Tracker()
        self.quick = False

        self._unknown = 0
        self._wait_since: float | None = None
        self._cast_open = False
        self._progressed = False
        self._fished = False  # lượt này đã thấy cần được quăng (chờ, reel, thanh trượt)
        self._cast_started = 0.0
        self._cast_taps = 0
        self._cast_retries = 0
        self._last_cast_tap = 0.0
        self._mult_taps = 0
        self._mult_logged = False
        self._nav_hold = 0.0
        self._reel_tap = 0.0
        self._timesup_since: float | None = None
        self._result_tap = 0.0

        self._zone: tuple[int, int] | None = None
        self._cooldown_until = 0.0
        self._tapped_zone = False
        self._miss_streak = 0
        # learn=False (mô phỏng, kiểm tra) thì không đọc cũng không ghi bộ nhớ học.
        self.memory = Memory(enabled=learn)
        self._latency = self._learned_latency() if learn else BASE_LATENCY
        self._pending_tap: dict | None = None
        self._last_offset = 0.0
        self._csv = None
        self._writer = None
        self._trace_file = None
        self._t0 = time.time()
        self._last_kind = ""
        self._busy_saved = 0
        self._result_saved = 0
        self._dismiss_count = 0
        self._seen_gold: list[int] = []

    # ----- vòng chính -----

    def run(self) -> Stats:
        LOGS.mkdir(parents=True, exist_ok=True)
        path = LOGS / f"cau-ca-{datetime.now():%Y%m%d-%H%M%S}.csv"
        self.log(f"Tự câu cá: {self.target} lượt, hệ số x{self.multiplier}.")
        self.log(f"Độ trễ cú bấm bắt đầu từ {self._latency:.2f}s ({self.memory.summary()}).")
        trace_path = path.with_name(path.stem + "-vet.txt")
        try:
            with path.open("w", newline="", encoding="utf-8-sig") as handle, trace_path.open("w", encoding="utf-8") as trace:
                self._trace_file = trace
                self._t0 = time.time()
                self._writer = csv.writer(handle)
                self._writer.writerow(["luot", "ket_qua", "vang", "so_lan_bam", "giay"])
                self._loop()
        except Stopped:
            self.log("Đã dừng.")
        except Finished as done:
            self.log(str(done))
        finally:
            self.adb.close()
            self._writer = None
            self._trace_file = None
        s = self.stats
        self.log(
            f"Tổng kết: {s.casts} lượt quăng, {s.caught} thành công, {s.failed} hết giờ, "
            f"{s.gold} Gold. Bảng chi tiết: {path}"
        )
        return s

    def _loop(self) -> None:
        while True:
            self._check()
            img, started, ended = self.adb.timed_screenshot()
            img = normalize(img)
            scene = read_scene(img, self.templates)
            self._track_unknown(scene, img)
            if scene.kind != self._last_kind:
                self._trace(f"màn {scene.kind} (chụp {started - self._t0:.2f}-{ended - self._t0:.2f}s)")
                self._last_kind = scene.kind
            if scene.kind != "wait":
                self._wait_since = None
            if scene.kind in ("wait", "reel", "slider") and not self._cast_open:
                # Cần đã được quăng mà tool không bấm (bắt đầu giữa chừng, hoặc cú bấm bỏ qua kết quả rơi vào nút câu).
                self.stats.casts += 1
                self._cast_open = True
                self._cast_started = time.time()
                self._cast_taps = 0
                self._fished = False
                self._seen_gold.clear()
                self.log(f"Lượt {self.stats.casts}: cần đã được quăng ngoài tool.")
                self.on_stats(self.stats)
            if scene.kind in ("wait", "reel", "slider", "busy"):
                self._fished = True
            # Chữ vàng chỉ hiện chưa tới 1 giây, ngay lúc chuyển từ Cool! sang màn kết quả.
            if self._fished and scene.kind in ("busy", "unknown", "result"):
                self._note_gold(img)
            if scene.kind in ("wait", "reel", "slider", "busy", "timesup", "result"):
                self._progressed = True
            if scene.kind not in ("result", "timesup"):
                self._dismiss_count = 0
            if scene.kind != "timesup":
                self._timesup_since = None
            getattr(self, f"_on_{scene.kind}")(img, scene, started, ended)

    # ----- từng màn -----

    def _on_yard(self, img, scene, started, ended) -> None:
        hit = self.templates.find(img, "pinball_btn", (560, 1200, 720, 1280))
        if hit is None or time.time() < self._nav_hold:
            self._pause(0.3)
            return
        self.log("Đang ở sân. Vào Pinball.")
        self.adb.tap(*hit)
        self._nav_hold = time.time() + 2.0
        self._pause(1.5)

    def _on_pinball(self, img, scene, started, ended) -> None:
        if time.time() < self._nav_hold:
            self._pause(0.3)
            return
        point = fish_tile_point(img, self.templates)
        if point is None:
            self.log("Ở Pinball nhưng chưa thấy ô Fishing Contest.")
            self._pause(1.0)
            return
        self.log("Vào Fishing Contest.")
        self.adb.tap(*point)
        self._nav_hold = time.time() + NAV_LOAD
        self._pause(NAV_LOAD)

    def _on_idle(self, img, scene, started, ended) -> None:
        if self._cast_open and self._progressed:
            # Cần đã chạy qua các bước câu mà không thấy màn kết quả (game tự đóng). Ghi lại rồi sang lượt mới.
            self.log("Không thấy màn kết quả của lượt trước.")
            self._record("khong_ro", 0)
        if self._cast_open and time.time() - self._last_cast_tap < CAST_RETRY_AFTER:
            self._pause(0.2)
            return
        if self.stats.casts >= self.target and not self._cast_open:
            raise Finished(f"Đã câu đủ {self.target} lượt.")
        if not self._fix_multiplier(img):
            return
        if self._cast_open:
            # Đã bấm quăng mà vẫn ở màn chờ quăng: bấm lại vài lần rồi bỏ.
            self._cast_retries += 1
            if self._cast_retries > CAST_MAX_RETRIES:
                raise Finished("Bấm quăng nhiều lần mà không có phản hồi. Có thể đã hết rod.")
            self.log("Chưa thấy cần được quăng. Bấm lại.")
        else:
            rods = read_rods(img)
            self.stats.rods = rods
            # Đo trên máy thật: hệ số xN tốn N rod mỗi lần quăng.
            if rods is not None and rods < self.multiplier:
                raise Finished(f"Hết rod (còn {rods}, hệ số x{self.multiplier} cần {self.multiplier}).")
            self.stats.casts += 1
            self._cast_open = True
            self._progressed = False
            self._fished = False
            self._seen_gold.clear()
            self._cast_retries = 0
            self._cast_started = time.time()
            self._cast_taps = 0
            self._reset_slider()
            text = "?" if rods is None else str(rods)
            self.log(f"Lượt {self.stats.casts}/{self.target}: quăng cần (còn {text} rod).")
            self.on_stats(self.stats)
        self.adb.tap(*BUTTON_XY)
        self._last_cast_tap = time.time()
        self._pause(random.uniform(0.5, 0.9))

    def _on_wait(self, img, scene, started, ended) -> None:
        now = time.time()
        if self._wait_since is None:
            self._wait_since = now
        elif now - self._wait_since > WAIT_WARN:
            self.log("Chờ cá cắn quá lâu. Vẫn tiếp tục chờ.")
            self._wait_since = now
        self._pause(0.1)

    def _on_reel(self, img, scene, started, ended) -> None:
        now = time.time()
        if now - self._reel_tap < 0.9:
            self._pause(0.1)
            return
        self.log("Cá cắn. Bấm Reel it in.")
        self.adb.tap_fast(*BUTTON_XY)
        self._reel_tap = time.time()
        self._reset_slider()
        self._pause(0.3)

    def _on_busy(self, img, scene, started, ended) -> None:
        # Lưu vài ảnh để xem màn nào bị gọi là chuyển cảnh. Mỗi lần chạy tối đa 8 ảnh.
        if self._busy_saved < 8:
            from gift_tool.vision import imwrite

            self._busy_saved += 1
            slider = scene.detail.get("slider")
            imwrite(LOGS / f"cau-ca-busy-{self._busy_saved}.png", img)
            self._trace(f"busy lưu ảnh {self._busy_saved}: vùng={slider.lo}-{slider.hi} mồi={slider.pointer}")
        self._pause(0.05)

    def _on_slider(self, img, scene, started, ended) -> None:
        slider = scene.detail["slider"]
        when = started + CAPTURE_FRACTION * (ended - started)
        zone = (slider.lo, slider.hi)
        if self._zone is not None and not _same_zone(zone, self._zone):
            # Vùng vàng đổi: cú bấm trước đã trúng, game sang thanh mới.
            self._on_hit()
            self._zone = None
        if self._zone is None:
            self._zone = zone
            self.tracker.reset()
            self._miss_streak = 0
        else:
            # Mồi đè lên mép vùng vàng làm vùng trông hẹp hơn. Giữ bản rộng nhất.
            self._zone = (min(self._zone[0], zone[0]), max(self._zone[1], zone[1]))
        self.tracker.add(when, slider.pointer)
        self._trace(f"mẫu t={when - self._t0:.2f} mồi={slider.pointer:.0f} vùng={zone[0]}-{zone[1]}")

        now = time.time()
        if now < self._cooldown_until:
            return
        if self._tapped_zone:
            # Đã bấm mà vẫn là vùng cũ: trượt. Mồi tiếp tục chạy nên giữ mô hình, chỉ đổi độ lệch giờ.
            self._tapped_zone = False
            self._remember(hit=False)
            self._miss_streak += 1
            self.log(f"Trượt ({self._miss_streak}). Thử lại.")
            self._trace("TRƯỢT")
        # Đo trên các lượt thật: đoán từ 3 mẫu lệch trung vị 22px, p90 77px (vùng vàng chỉ rộng ~110px); từ 5 mẫu p90 còn 45px.
        # Chờ thêm ~0.8s để đỡ trượt, vì mỗi lần trượt tốn 2s đồng hồ cộng với 2s bấm lại.
        count = self.tracker.count
        ready = count >= MIN_SAMPLES_BEFORE_TAP and (self.tracker.confident() or count >= MAX_SAMPLES_BEFORE_TAP)
        if not ready:
            return
        offset = MISS_OFFSETS[self._miss_streak % len(MISS_OFFSETS)]
        # Bấm muộn hơn offset giây nghĩa là coi như cú bấm tới game sớm hơn offset giây.
        latency = self._latency - offset
        due = self.tracker.plan(now, latency, self._zone)
        if due is None:
            # Vùng vàng hẹp nên trong 2.4s tới không có lúc nào mồi chắc chắn nằm trong vùng ăn thật. Chờ mẫu mới rồi tính lại.
            return
        fit = self.tracker.fit()
        self._pending_tap = {
            "total": latency,
            "width": self._zone[1] - self._zone[0],
            "speed": fit[0] if fit else None,
            "first": self._miss_streak == 0,
        }
        self._sleep_until(due)
        self.adb.tap_fast(*BUTTON_XY)
        tapped = time.time()
        self._pending_tap["time"] = tapped
        self._trace(
            f"BẤM lệnh t={tapped - self._t0:.2f} dự kiến tới game {tapped - self._t0 + latency:.2f} "
            f"mồi dự đoán={self.tracker.position(tapped + latency):.0f} độ lệch={offset:+.2f} bias={self._bias:+.2f} trễ={latency:.2f}"
        )
        self.stats.taps += 1
        self._cast_taps += 1
        self._tapped_zone = True
        self._last_offset = offset
        self._cooldown_until = tapped + TAP_COOLDOWN
        self.log(
            f"Bấm thanh trượt: mồi {self.tracker.position(tapped + latency):.0f}, "
            f"vùng {self._zone[0]}-{self._zone[1]}, tốc độ {fit[0]:.0f}px/s."
        )

    def _on_timesup(self, img, scene, started, ended) -> None:
        now = time.time()
        if self._timesup_since is None:
            self._timesup_since = now
            if self._cast_open:
                self._record("het_gio", 0)
                self.log("Hết giờ, cá thoát.")
        elif now - self._timesup_since > TIMESUP_TAP_AFTER:
            self._dismiss()
        self._reset_slider()
        self._pause(0.3)

    def _on_result(self, img, scene, started, ended) -> None:
        self._reset_slider(hit=True)
        if self._cast_open:
            if self._fished:
                golds = self._read_result(img)
                gold = _pick_gold(golds)
                self.log("Câu được cá" + (f", +{gold} Gold." if gold else "."))
                self._record("thanh_cong", gold)
            else:
                # Màn kết quả hiện ra khi cần chưa hề được quăng: popup khác chen vào, không tính lượt.
                self.log("Có popup chen vào, chưa tính lượt.")
        self._dismiss()
        self._pause(0.5)

    def _on_unknown(self, img, scene, started, ended) -> None:
        # Sau khi quăng, cảnh Cool! bị xếp vào màn lạ. Ngủ 0,8 giây ở đây sẽ bỏ lỡ chữ vàng.
        self._pause(0.05 if self._fished else 0.8)

    # ----- tiện ích -----

    def _note_gold(self, img) -> None:
        """Ghi số vàng nếu khung này còn chữ +Gold. Chữ biến trong chưa tới một giây."""
        value = read_gold(img)
        if value:
            self._seen_gold.append(value)

    def _read_result(self, first) -> list[int]:
        """Gold chỉ hiện thoáng khi phá kỷ lục, nên chụp thêm vài ảnh trước khi bấm bỏ qua."""
        golds = list(self._seen_gold)
        frame = first
        for index in range(RESULT_SAMPLES + 1):
            gold = read_gold(frame)
            if gold:
                golds.append(gold)
            if index == 0 and self._result_saved < 12:
                # Giữ ảnh kết quả đầu tiên để đối chiếu khi số Gold đọc sai.
                from gift_tool.vision import imwrite

                self._result_saved += 1
                imwrite(LOGS / f"cau-ca-ketqua-{self._result_saved}.png", frame)
            if index == RESULT_SAMPLES:
                break
            self._check()
            frame = normalize(self.adb.screenshot())
            if read_scene(frame, self.templates).kind != "result":
                break
        self._trace(f"đọc kết quả: gold={golds}")
        self._seen_gold.clear()
        return golds

    def _record(self, outcome: str, gold: int) -> None:
        s = self.stats
        if outcome == "thanh_cong":
            s.caught += 1
            s.gold += gold
        elif outcome == "het_gio":
            s.failed += 1
        seconds = time.time() - self._cast_started
        if self._writer is not None:
            self._writer.writerow([s.casts, outcome, gold, self._cast_taps, f"{seconds:.1f}"])
        self._cast_open = False
        self.on_stats(s)

    def _on_hit(self) -> None:
        if self._tapped_zone:
            self._tapped_zone = False
            self._trace("TRÚNG")
            self._remember(hit=True)
            self.log(f"Trúng vùng vàng. Độ trễ cú bấm đang dùng: {self._latency:.2f}s.")
        self._miss_streak = 0

    def _remember(self, hit: bool) -> None:
        """Ghi kết quả cú bấm vừa rồi vào bộ nhớ học và lấy lại độ lệch giờ bấm tốt nhất."""
        tap, self._pending_tap = self._pending_tap, None
        if tap is None:
            return
        ok = consistent_latencies(self.tracker, tap["time"], self._zone, hit) if self._zone is not None else None
        self.memory.record(tap["total"], hit, tap["width"], tap["speed"], tap["first"], ok)
        if self.memory.enabled:
            self._latency = self._learned_latency()

    @property
    def _bias(self) -> float:
        """Độ lệch giờ bấm so với giả định cũ TAP_LATENCY (dùng cho file vết)."""
        return TAP_LATENCY - self._latency

    def _learned_latency(self) -> float:
        found = self.memory.latency()
        return BASE_LATENCY if found is None else found[0]

    def _reset_slider(self, hit: bool = False) -> None:
        if hit and self._tapped_zone and self._zone is not None:
            self._on_hit()
        self._zone = None
        self._tapped_zone = False
        self._cooldown_until = 0.0
        self.tracker.reset()

    def _fix_multiplier(self, img) -> bool:
        """True khi hệ số đúng (hoặc không đọc được). False khi vừa bấm đổi và cần chụp lại."""
        current = read_multiplier(img, self.templates)
        if current is None:
            if not self._mult_logged:
                self.log("Không đọc được hệ số hiện tại. Giữ nguyên.")
                self._mult_logged = True
            return True
        if current == self.multiplier:
            self._mult_taps = 0
            return True
        self._mult_taps += 1
        if self._mult_taps > MULT_MAX_TAPS:
            raise Finished(f"Không đổi được hệ số về x{self.multiplier}.")
        self.log(f"Hệ số đang x{current}, đổi về x{self.multiplier}.")
        self.adb.tap(*BADGE_XY)
        self._pause(0.7)
        return False

    def _track_unknown(self, scene: Scene, img) -> None:
        if scene.kind != "unknown":
            self._unknown = 0
            return
        self._unknown += 1
        if self._unknown == 1:
            from gift_tool.vision import imwrite

            path = LOGS / "cau-ca-khong-nhan-ra-man.png"
            imwrite(path, img)
            self.log(f"Chưa nhận ra màn hình, không bấm. Ảnh: {path}")
        if self._unknown >= UNKNOWN_LIMIT:
            raise Finished("Không nhận ra màn hình quá lâu. Có thể đang có popup. Hãy xử lý rồi chạy lại.")

    def _dismiss(self) -> None:
        """Bấm bỏ qua màn kết quả hoặc Time's up. Không đóng thì đổi điểm bấm ở lần sau."""
        now = time.time()
        if now - self._result_tap < DISMISS_RETRY:
            return
        point = DISMISS_POINTS[self._dismiss_count % len(DISMISS_POINTS)]
        self._dismiss_count += 1
        self.adb.tap(*point)
        self._result_tap = time.time()
        self._trace(f"bấm bỏ qua kết quả tại {point}")

    def _trace(self, text: str) -> None:
        if self._trace_file is not None:
            self._trace_file.write(f"[{time.time() - self._t0:7.2f}] {text}\n")
            self._trace_file.flush()

    def _sleep_until(self, moment: float) -> None:
        while True:
            self._check()
            left = moment - time.time()
            if left <= 0:
                return
            time.sleep(min(left, 0.02))

    def _pause(self, seconds: float) -> None:
        self._check()
        if self.quick:
            return
        self._sleep_until(time.time() + seconds)

    def _check(self) -> None:
        if self.stop.is_set():
            raise Stopped()


def _same_zone(new: tuple[int, int], known: tuple[int, int]) -> bool:
    """Cùng một thanh trượt hay đã sang thanh mới.

    Mồi đè lên vùng vàng làm vùng đọc được hẹp đi từ một phía, nhưng phía còn lại giữ nguyên. Thanh mới thì
    cả hai mép đổi. Trước đây chỉ so từng mép với ngưỡng nên vùng bị che bớt (lệch hơn 25px) bị tính là thanh mới,
    mô hình mồi bị xóa liên tục và tool không bao giờ gom đủ mẫu để bấm.
    """
    edge_kept = abs(new[0] - known[0]) <= ZONE_SHIFT or abs(new[1] - known[1]) <= ZONE_SHIFT
    overlap = min(new[1], known[1]) - max(new[0], known[0])
    smaller = max(1, min(new[1] - new[0], known[1] - known[0]))
    return edge_kept and overlap >= 0.4 * smaller


def _pick_gold(golds: list[int]) -> int:
    """Chọn số Gold từ vài ảnh kết quả.

    Số chỉ nằm trên ảnh đầu rồi biến, nên một lần đọc từ 10 trở lên vẫn nhận (1.210 đọc được một lần là thật).
    Một chữ số lẻ (như 9 do tia sáng) chỉ nhận khi lặp lại ở hai ảnh. Nhiều số khác nhau thì lấy số lớn hơn, vì số nhỏ thường là đọc hụt chữ.
    """
    if not golds:
        return 0
    best = max(set(golds), key=lambda value: (golds.count(value), value))
    if golds.count(best) >= 2 or best >= 10:
        return best
    return 0
