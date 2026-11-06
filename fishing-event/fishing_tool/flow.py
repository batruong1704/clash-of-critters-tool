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

from fishing_tool.catch import classify
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
    read_slider,
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
# Mồi đã nằm trong vùng mà thanh mới hoặc màn kết quả có khi mãi 1,5–1,6s sau mới hiện.
# Gọi trượt lúc 0,9s sẽ đẩy độ trễ sai và bấm thêm một cú vào đúng thanh vừa trúng.
HIT_SETTLE = 1.70
# Độ trễ của cú bấm, từ lúc phát lệnh tới lúc game nhận (giây). Các lượt chiều 5/11 (bấm bằng tap_fast) có mồi
# ở giữa vùng vàng khoảng 0,14s sau lệnh. 0,30s là số cũ, đo trước khi bấm qua shell giữ sẵn, và làm cú bấm tới muộn.
# Tool tự dò lại số này từ các cú trúng và nhớ qua các phiên. Khi chưa đủ cú trúng thì dùng số này.
BASE_LATENCY = 0.15
# Thanh thứ 2 trở đi thường hẹp hơn 120px. Video4 (17:00): lúc phát lệnh mồi còn giữa,
# 0,10s sau đã vượt tâm 25–40px. Bấm sớm hơn chừng đó.
# Cửa sổ còn xa hơn REFINE_HORIZON thì chụp thêm, tính từ lúc quyết định chứ không từ lúc bắt đầu chụp.
# Tính từ lúc chụp sẽ trừ oan ~0,3s và bỏ cả cửa sổ sắp tới. Lượt 6 lúc 17:16 đứng 12s ở thanh 73px vì vậy.
# Trượt thì lấy ảnh mới tính lại, không xê ±0,03s (mới được khoảng 7px).
NARROW_ZONE = 120
NARROW_LEAD = 0.12
# Vùng rộng khoảng 147px. Video10: độ trễ học được 0,10s khiến lệnh tới khi mồi đã sát mép.
# Ba ảnh cùng một chiều là đủ vận tốc và pha. Lệnh của vùng rộng tính với 0,24s.
# Cửa sổ còn xa hơn 0,70s thì chụp tiếp để chỉnh pha, không ngủ đến lúc bấm.
WIDE_LATENCY = 0.24
WIDE_MIN_SAMPLES = 4
WIDE_FIT_RMS = 16.0
# Vùng rộng: ba ảnh khớp lệch ≤ 8px là bấm được, dù ba ảnh chưa đi một chiều (cú nảy nằm trong đó).
# Chờ ảnh thứ 4–6 thì lỡ lượt mồi đang đi ngang và phải đợi cả vòng quay lại, khoảng 1–2 giây.
WIDE_TIGHT_SAMPLES = 3
WIDE_TIGHT_RMS = 8.0
REFINE_HORIZON = 0.70
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
# Sau khi ghi xong lượt, còn chờ màn Time's up tự tắt (6 giây) rồi bấm đóng. Quá hạn này thì dừng dù màn chưa đổi.
STOP_SETTLE = 12.0
RESULT_SAMPLES = 4
# Chữ vàng chỉ hiện khi phá kỷ lục và biến trong chưa tới một giây. Không thấy chữ thì thôi chụp thêm.
GOLD_LOOK = 0.8
CALCULATING = "Đang tính toán kết quả."


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
                f"Chưa có ảnh mẫu của hệ số x{multiplier} (data/templates/mult_{multiplier}.png) nên tool không nhận ra được nó. "
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
        self._cast_tap_log: list[dict] = []
        self._slider_bar = 0
        self._last_obs: dict | None = None
        self._cast_tap_flushed = False
        self._cast_retries = 0
        self._last_cast_tap = 0.0
        self._mult_taps = 0
        self._mult_logged = False
        self._mult_ok = False
        self._mult_misses = 0
        self._nav_hold = 0.0
        self._reel_tap = 0.0
        self._timesup_since: float | None = None
        self._result_tap = 0.0

        self._zone: tuple[int, int] | None = None
        self._zone_seen: list[tuple[int, int]] = []
        self._cooldown_until = 0.0
        self._tap_at = 0.0
        self._tapped_zone = False
        self._miss_streak = 0
        # learn=False (mô phỏng, kiểm tra) thì không đọc cũng không ghi bộ nhớ học.
        self.memory = Memory(enabled=learn)
        self._latency = self._learned_latency() if learn else BASE_LATENCY
        self._latency_nudge = 0.0
        self._pending_tap: dict | None = None
        self._last_offset = 0.0
        self._csv = None
        self._writer = None
        self._tap_handle = None
        self._tap_writer = None
        self._trace_file = None
        self._t0 = time.time()
        self._last_kind = ""
        self._busy_saved = 0
        self._result_saved = 0
        self._dismiss_count = 0
        self._seen_gold: list[int] = []
        self._stop_noted = False
        self._settle_since: float | None = None

    # ----- vòng chính -----

    def run(self) -> Stats:
        LOGS.mkdir(parents=True, exist_ok=True)
        path = LOGS / f"cau-ca-{datetime.now():%Y%m%d-%H%M%S}.csv"
        self.log(f"Tự câu cá: {self.target} lượt, hệ số x{self.multiplier}.")
        self.log(f"Độ trễ cú bấm bắt đầu từ {self._latency:.2f}s ({self.memory.summary()}).")
        trace_path = path.with_name(path.stem + "-vet.txt")
        tap_path = path.with_name(path.stem + "-bam.csv")
        try:
            with (
                path.open("w", newline="", encoding="utf-8-sig") as handle,
                trace_path.open("w", encoding="utf-8") as trace,
                tap_path.open("w", newline="", encoding="utf-8-sig") as taps,
            ):
                self._trace_file = trace
                self._t0 = time.time()
                self._writer = csv.writer(handle)
                self._writer.writerow(["luot", "ket_qua", "vang", "loai", "pham", "so_lan_bam", "giay"])
                self._tap_handle = taps
                self._tap_writer = csv.writer(taps)
                self._tap_writer.writerow(
                    [
                        "luot",
                        "ket_qua",
                        "lan",
                        "thanh",
                        "lan_tren_thanh",
                        "ket_qua_bam",
                        "t_lenh",
                        "tu_quang",
                        "tre",
                        "lech",
                        "moi_du_doan",
                        "vung_lo",
                        "vung_hi",
                        "rong",
                        "vung_that_lo",
                        "vung_that_hi",
                        "toc_do",
                        "sai_so",
                        "so_mau",
                        "cho",
                        "mau_cuoi_t",
                        "mau_cuoi_moi",
                        "chup_dau",
                        "chup_cuoi",
                        "mau_sau_t",
                        "mau_sau_moi",
                        "mau_sau_lo",
                        "mau_sau_hi",
                        "err_px",
                    ]
                )
                try:
                    self._loop()
                finally:
                    if self._cast_open:
                        self._flush_cast_taps("dung")
        except Stopped:
            self.log("Đã dừng.")
        except Finished as done:
            self.log(str(done))
        finally:
            self.adb.close()
            self._writer = None
            self._tap_handle = None
            self._tap_writer = None
            self._trace_file = None
        s = self.stats
        self.log(
            f"Tổng kết: {s.casts} lượt quăng, {s.caught} thành công, {s.failed} thất bại, "
            f"{s.gold} Gold. Bảng chi tiết: {path}. Từng cú bấm: {tap_path}"
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
                # Đã có lệnh dừng thì không nhận thêm lượt mới.
                if self.stop.is_set():
                    raise Stopped()
                self.stats.casts += 1
                self._cast_open = True
                self._cast_started = time.time()
                self._cast_taps = 0
                self._prepare_cast_taps()
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
        if self.stop.is_set() and not self._cast_open:
            raise Stopped()
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
            self._prepare_cast_taps()
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
            self._follow_pointer(img, started, ended)
            self._pause(0.1)
            return
        self.log("Cá cắn. Bấm Reel it in.")
        self.adb.tap_fast(*BUTTON_XY)
        self._reel_tap = time.time()
        self._reset_slider()
        self._pause(0.3)

    def _on_busy(self, img, scene, started, ended) -> None:
        self._follow_pointer(img, started, ended)
        # Lưu vài ảnh để xem màn nào bị gọi là chuyển cảnh. Mỗi lần chạy tối đa 8 ảnh.
        if self._busy_saved < 8:
            from gift_tool.vision import imwrite

            self._busy_saved += 1
            slider = scene.detail.get("slider")
            imwrite(LOGS / f"cau-ca-busy-{self._busy_saved}.png", img)
            self._trace(f"busy lưu ảnh {self._busy_saved}: vùng={slider.lo}-{slider.hi} mồi={slider.pointer}")
        self._pause(0.05)

    def _follow_pointer(self, img, started: float, ended: float) -> None:
        """Ghi mồi khi nó đã chạy mà vùng vàng chưa hiện. Vàng hiện lên thì quỹ đạo có sẵn."""
        if not self._fished or self._zone is not None:
            return
        slider = read_slider(img)
        if slider.pointer is None:
            return
        when = started + CAPTURE_FRACTION * (ended - started)
        if self.tracker.samples:
            prev_t, prev_x = self.tracker.samples[-1]
            if when - prev_t < 0.12:
                return
            if when - prev_t < 0.50 and abs(slider.pointer - prev_x) < 8:
                return
        self.tracker.add(when, float(slider.pointer))
        self._trace(f"mồi trước vùng t={when - self._t0:.2f} mồi={slider.pointer:.0f}")

    def _carry_motion(self) -> None:
        """Giữ đoạn mồi đang chạy sang thanh mới. Bỏ mẫu đứng yên (cú trúng vừa đóng băng mồi)."""
        samples = list(self.tracker.samples)
        self.tracker.reset()
        if len(samples) < 2:
            return
        latest = samples[-1][0]
        recent = [(t, x) for t, x in samples if latest - t <= 1.2]
        while len(recent) >= 2 and abs(recent[-1][1] - recent[-2][1]) < 15:
            recent.pop()
        if len(recent) < 2 or latest - recent[-1][0] > 0.70:
            return
        if abs(recent[-1][1] - recent[0][1]) < 30:
            return
        for when, pointer in recent:
            self.tracker.add(when, pointer)

    def _command_latency(self, narrow: bool) -> float:
        base = self._latency + NARROW_LEAD if narrow else WIDE_LATENCY
        return min(0.40, max(0.08, base + self._latency_nudge))

    def _landing_error(self, row: dict) -> float | None:
        """Mồi lúc game nhận, trừ tâm vùng đang nhắm (px). Dương là lệch sang phải."""
        arrival = row["t_lenh"] + row["tre"]
        pts = [(t - self._t0, x) for t, x in self.tracker.samples]
        if row.get("mau_sau_t") is not None:
            pts.append((float(row["mau_sau_t"]), float(row["mau_sau_moi"])))
        pts = sorted({(round(t, 4), x) for t, x in pts})
        if len(pts) < 2:
            return None
        landed = None
        for (t0, x0), (t1, x1) in zip(pts, pts[1:]):
            if t0 <= arrival <= t1 and 0 < t1 - t0 <= 0.70:
                landed = x0 + (x1 - x0) * (arrival - t0) / (t1 - t0)
                break
        if landed is None:
            nearest = min(pts, key=lambda item: abs(item[0] - arrival))
            if abs(nearest[0] - arrival) > 0.60:
                return None
            idx = pts.index(nearest)
            if idx + 1 < len(pts) and pts[idx + 1][0] - nearest[0] <= 0.70:
                t0, x0 = nearest
                t1, x1 = pts[idx + 1]
            elif idx > 0 and nearest[0] - pts[idx - 1][0] <= 0.70:
                t0, x0 = pts[idx - 1]
                t1, x1 = nearest
            else:
                return None
            if t1 == t0:
                return None
            landed = nearest[1] + (x1 - x0) / (t1 - t0) * (arrival - nearest[0])
        return float(landed - (row["vung_lo"] + row["vung_hi"]) / 2)

    def _nudge_from_miss(self, row: dict) -> None:
        """Lệch cùng chiều vận tốc là lệnh tới muộn. Lần mồi quay lại phát lệnh sớm hơn đúng chừng đó.

        Lệch lớn hơn nửa vùng là mô hình sai pha, không phải độ trễ cú bấm. Xê trễ theo số đó
        đẩy cú sau ra khỏi vùng hẹp: lượt 5, vùng 36px lệch +29px rồi xê +0,08s, cú kế tới khi mồi còn ngoài vùng.
        """
        err = row.get("err_px")
        if err is None:
            return
        vel = self.tracker.velocity(self._t0 + row["t_lenh"] + row["tre"])
        if vel is None or abs(vel) < 80:
            return
        half = (float(row["vung_hi"]) - float(row["vung_lo"])) / 2
        if half > 0 and abs(err) > half:
            self._latency_nudge = 0.0
            self._trace("giữ trễ, mồi lệch quá nửa vùng nên không phải độ trễ")
            return
        cap = 0.08
        if half > 0:
            cap = min(0.08, max(0.015, (0.35 * half) / abs(vel)))
        self._latency_nudge = min(cap, max(-cap, err / vel))
        self._trace(f"chỉnh trễ {self._latency_nudge:+.2f}s cho lần mồi quay lại")

    def _on_slider(self, img, scene, started, ended) -> None:
        slider = scene.detail["slider"]
        when = started + CAPTURE_FRACTION * (ended - started)
        zone = (slider.lo, slider.hi)
        self._note_after_tap(when, slider.pointer, zone)
        if self._zone is not None and not _same_zone(zone, self._zone):
            # Vùng vàng đổi: cú bấm trước đã trúng, game sang thanh mới.
            self._on_hit()
            self._zone = None
        if self._zone is None:
            self._slider_bar += 1
            self._zone = zone
            self._zone_seen = []
            self._carry_motion()
            self._miss_streak = 0
            self._latency_nudge = 0.0
        else:
            # Mồi đè lên mép vùng vàng làm vùng trông hẹp hơn. Giữ bản rộng nhất để nhận ra còn cùng một thanh.
            self._zone = (min(self._zone[0], zone[0]), max(self._zone[1], zone[1]))
        self._zone_seen.append(zone)
        del self._zone_seen[:-3]
        aim = self._aim_zone()
        self.tracker.add(when, slider.pointer)
        self._last_obs = {
            "t": when - self._t0,
            "moi": float(slider.pointer),
            "chup_dau": started - self._t0,
            "chup_cuoi": ended - self._t0,
        }
        self._trace(
            f"mẫu t={when - self._t0:.2f} mồi={slider.pointer:.0f} vùng={zone[0]}-{zone[1]} "
            f"chụp {started - self._t0:.2f}-{ended - self._t0:.2f}"
        )

        now = time.time()
        if now < self._cooldown_until:
            return
        if self._tapped_zone:
            row = self._cast_tap_log[-1] if self._cast_tap_log else None
            err = self._landing_error(row) if row is not None else None
            half = (float(row["vung_hi"]) - float(row["vung_lo"])) / 2 if row is not None else 0.0
            if _hold_hit(now, self._tap_at, err, half):
                if row is not None and not row.get("cho_xac_nhan"):
                    row["cho_xac_nhan"] = True
                    self._trace(f"chờ xác nhận, mồi lệch {err:+.0f}px còn trong vùng")
                return
            # Đã bấm mà vẫn là vùng cũ: trượt. Mồi tiếp tục chạy nên giữ mô hình, ảnh sau tính lại giờ bấm.
            self._tapped_zone = False
            self._remember(hit=False)
            self._miss_streak += 1
            self.log(f"Trượt ({self._miss_streak}). Thử lại.")
            self._trace("TRƯỢT")
        count = self.tracker.count
        fit_now = self.tracker.fit()
        straight = self.tracker.straight()
        narrow = aim[1] - aim[0] < NARROW_ZONE
        clean = straight is not None and straight[1] <= (12.0 if narrow else 14.0)
        if narrow:
            ready = clean or (
                count >= MIN_SAMPLES_BEFORE_TAP and (self.tracker.confident() or count >= MAX_SAMPLES_BEFORE_TAP)
            )
            if not ready:
                return
            # Chưa có đoạn thẳng sạch thì lần bấm đầu của vùng hẹp vẫn chờ đường khớp hơn.
            if not clean and self._miss_streak == 0 and (count < 6 or fit_now is None or fit_now[2] > 18):
                return
            offset = 0.0
            latency = self._command_latency(narrow=True)
        else:
            # Ba ảnh khớp chặt, ba ảnh một chiều, hoặc bốn ảnh khớp, là bấm được. Không đợi đủ năm ảnh.
            tight = (
                count >= WIDE_TIGHT_SAMPLES
                and fit_now is not None
                and fit_now[2] <= WIDE_TIGHT_RMS
                and self.tracker.confident()
            )
            early = clean or tight or (
                count >= WIDE_MIN_SAMPLES
                and fit_now is not None
                and fit_now[2] <= WIDE_FIT_RMS
                and self.tracker.confident()
            )
            ready = early or (
                count >= MIN_SAMPLES_BEFORE_TAP and (self.tracker.confident() or count >= MAX_SAMPLES_BEFORE_TAP)
            )
            if not ready:
                return
            offset = 0.0
            latency = self._command_latency(narrow=False)
        measured = self.memory.eat_limit() if self.memory.enabled else None
        due = self.tracker.plan(now, latency, aim, eat=measured)
        if due is None:
            # Trong 2.4s tới không có lúc nào mồi chắc chắn nằm trong vùng ăn thật. Chờ mẫu mới rồi tính lại.
            return
        # Còn xa thì chụp thêm. Đoạn mồi chạy về là một đoạn thẳng sạch để chỉnh pha rồi mới bấm.
        if due - now > REFINE_HORIZON:
            return
        fit = self.tracker.fit()
        self._pending_tap = {
            "total": latency,
            "width": int(aim[1] - aim[0]),
            "speed": fit[0] if fit else None,
            "first": self._miss_streak == 0,
        }
        self._sleep_until(due)
        self.adb.tap_fast(*BUTTON_XY)
        tapped = time.time()
        self._pending_tap["time"] = tapped
        self._cast_tap_log.append(self._tap_row(tapped, latency, offset, aim, fit))
        self._trace(
            f"BẤM lệnh t={tapped - self._t0:.2f} dự kiến tới game {tapped - self._t0 + latency:.2f} "
            f"mồi dự đoán={self.tracker.position(tapped + latency):.0f} độ lệch={offset:+.2f} bias={self._bias:+.2f} trễ={latency:.2f}"
        )
        self.stats.taps += 1
        self._cast_taps += 1
        self._tapped_zone = True
        self._tap_at = tapped
        self._last_offset = offset
        self._cooldown_until = tapped + TAP_COOLDOWN
        self.log(
            f"Bấm thanh trượt: mồi {self.tracker.position(tapped + latency):.0f}, "
            f"vùng {aim[0]:.0f}-{aim[1]:.0f}, tốc độ {fit[0]:.0f}px/s."
        )

    def _on_timesup(self, img, scene, started, ended) -> None:
        now = time.time()
        if self._timesup_since is None:
            self._timesup_since = now
            if self._cast_open:
                self._record("that_bai", 0)
                self.log("Thất bại.")
        elif now - self._timesup_since > TIMESUP_TAP_AFTER:
            self._dismiss()
        self._reset_slider()
        self._pause(0.3)

    def _on_result(self, img, scene, started, ended) -> None:
        self._reset_slider(hit=True)
        if self._cast_open and self._fished:
            golds, frames = self._sample_result(img, ended)
            gold = _pick_gold(golds)
            # Đóng màn trước. So loài chạy trên ảnh đã giữ, không giữ người chờ cú bấm.
            self._dismiss()
            self.log(CALCULATING)
            catch = _classify_frames(frames)
            self._trace(f"loài={catch.label if catch else ''}")
            if catch is None:
                self.log("Câu được cá" + (f", +{gold} Gold." if gold else "."))
            else:
                self.log(f"Câu được {catch.label}" + (f", +{gold} Gold." if gold else "."))
            self._record("thanh_cong", gold, catch)
        elif self._cast_open:
            # Màn kết quả hiện ra khi cần chưa hề được quăng: popup khác chen vào, không tính lượt.
            self.log("Có popup chen vào, chưa tính lượt.")
            self._dismiss()
        else:
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

    def _sample_result(self, first, opened_at: float) -> tuple[list[int], list]:
        """Chụp thêm để đọc Gold, rồi trả ảnh để so loài sau khi đã bấm đóng màn.

        Dừng khi cùng một số xuất hiện hai lần. Không thấy chữ vàng thì dừng sau GOLD_LOOK giây
        kể từ ảnh kết quả đầu. Loài so trên ảnh đầu, lúc cá còn rõ.
        """
        golds = list(self._seen_gold)
        frames = [first]
        frame = first
        extra = 0
        # Ảnh đầu vừa được ghi Gold ở _note_gold. Đọc lại cùng ảnh sẽ đếm một số thành hai lần.
        pending = False
        if self._result_saved < 12:
            from gift_tool.vision import imwrite

            self._result_saved += 1
            imwrite(LOGS / f"cau-ca-ketqua-{self._result_saved}.png", first)
        while True:
            if pending:
                gold = read_gold(frame)
                if gold:
                    golds.append(gold)
            pending = True
            if _stop_gold_samples(golds, time.time() - opened_at, extra):
                break
            self._check()
            frame = normalize(self.adb.screenshot())
            extra += 1
            if read_scene(frame, self.templates).kind != "result":
                gold = read_gold(frame)
                if gold:
                    golds.append(gold)
                break
            frames.append(frame)
        self._trace(f"đọc gold={golds} ảnh={len(frames)}")
        self._seen_gold.clear()
        return golds, frames

    def _record(self, outcome: str, gold: int, catch=None) -> None:
        s = self.stats
        if outcome == "thanh_cong":
            s.caught += 1
            s.gold += gold
        elif outcome == "that_bai":
            s.failed += 1
        seconds = time.time() - self._cast_started
        label = catch.label if catch is not None else ""
        rarity = catch.rarity if catch is not None else ""
        if self._writer is not None:
            self._writer.writerow([s.casts, outcome, gold, label, rarity, self._cast_taps, f"{seconds:.1f}"])
        self._flush_cast_taps(outcome)
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
        self._mark_open_tap(hit)
        err = None
        for row in reversed(self._cast_tap_log):
            if row.get("ket_qua_bam") is not None:
                err = row.get("err_px")
                break
        ok = consistent_latencies(self.tracker, tap["time"], self._zone, hit) if self._zone is not None else None
        self.memory.record(tap["total"], hit, tap["width"], tap["speed"], tap["first"], ok, err)
        if self.memory.enabled:
            self._latency = self._learned_latency()

    @property
    def _bias(self) -> float:
        """Độ lệch giờ bấm so với giả định cũ TAP_LATENCY (dùng cho file vết)."""
        return TAP_LATENCY - self._latency

    def _learned_latency(self) -> float:
        found = self.memory.latency()
        if found is None:
            return BASE_LATENCY
        # 100 lượt vừa chạy: dưới 0,10s thì mồi ra khỏi vùng hẹp trước khi cú bấm tới, trên 0,18s thì tới quá sớm.
        return min(0.18, max(0.10, found[0]))

    def _prepare_cast_taps(self) -> None:
        """Xóa bảng cú bấm của lượt trước. Gọi lúc bắt đầu một lượt quăng."""
        self._cast_tap_log = []
        self._slider_bar = 0
        self._last_obs = None
        self._cast_tap_flushed = False

    def _note_after_tap(self, when: float, pointer: float, zone: tuple[int, int]) -> None:
        """Mẫu đầu tiên sau lệnh bấm. Dùng để biết mồi thật đang ở đâu lúc ảnh kế tiếp."""
        if not self._cast_tap_log:
            return
        row = self._cast_tap_log[-1]
        if row["mau_sau_t"] is not None:
            return
        if when - self._t0 <= row["t_lenh"] + 0.02:
            return
        row["mau_sau_t"] = when - self._t0
        row["mau_sau_moi"] = float(pointer)
        row["mau_sau_lo"] = zone[0]
        row["mau_sau_hi"] = zone[1]

    def _tap_row(self, tapped: float, latency: float, offset: float, aim: tuple[float, float], fit) -> dict:
        obs = self._last_obs or {}
        t_lenh = tapped - self._t0
        predicted = self.tracker.position(tapped + latency)
        widest = self._zone or (int(aim[0]), int(aim[1]))
        return {
            "lan": self._cast_taps + 1,
            "thanh": self._slider_bar,
            "lan_tren_thanh": self._miss_streak + 1,
            "ket_qua_bam": None,
            "t_lenh": t_lenh,
            "tu_quang": tapped - self._cast_started,
            "tre": latency,
            "lech": offset,
            "moi_du_doan": predicted,
            "vung_lo": aim[0],
            "vung_hi": aim[1],
            "rong": aim[1] - aim[0],
            "vung_that_lo": widest[0],
            "vung_that_hi": widest[1],
            "toc_do": None if fit is None else fit[0],
            "sai_so": None if fit is None else fit[2],
            "so_mau": self.tracker.count,
            "cho": None if not obs else t_lenh - obs["t"],
            "mau_cuoi_t": obs.get("t"),
            "mau_cuoi_moi": obs.get("moi"),
            "chup_dau": obs.get("chup_dau"),
            "chup_cuoi": obs.get("chup_cuoi"),
            "mau_sau_t": None,
            "mau_sau_moi": None,
            "mau_sau_lo": None,
            "mau_sau_hi": None,
            "err_px": None,
        }

    def _mark_open_tap(self, hit: bool) -> None:
        for row in reversed(self._cast_tap_log):
            if row["ket_qua_bam"] is None:
                row["ket_qua_bam"] = "trung" if hit else "truot"
                row["err_px"] = self._landing_error(row)
                if not hit:
                    self._nudge_from_miss(row)
                err = "không đo được" if row["err_px"] is None else f"{row['err_px']:+.0f}px"
                self._trace(f"err_px={err}")
                return

    def _flush_cast_taps(self, outcome: str) -> None:
        """Ghi mọi cú bấm của lượt này. Lượt không có thanh trượt vẫn được một dòng lan=0."""
        if self._cast_tap_flushed or self.stats.casts <= 0:
            return
        self._cast_tap_flushed = True
        rows = self._cast_tap_log
        for row in rows:
            if row["ket_qua_bam"] is None:
                row["ket_qua_bam"] = "truot" if outcome == "that_bai" else "khong_ro"
        n = len(rows)
        self._trace(f"lượt {self.stats.casts}: {n} lần bấm thanh trượt")
        self.log(f"Lượt {self.stats.casts}: {n} lần bấm thanh trượt.")
        if n == 0:
            self._write_tap_csv(outcome, None)
        for row in rows:
            sau = ""
            if row["mau_sau_t"] is not None:
                sau = (
                    f" sau t={row['mau_sau_t']:.2f} mồi={row['mau_sau_moi']:.0f}"
                    f" vùng sau={row['mau_sau_lo']}-{row['mau_sau_hi']}"
                )
            self._trace(
                f"  lần {row['lan']} thanh {row['thanh']} (lần {row['lan_tren_thanh']} trên thanh):"
                f" t={row['t_lenh']:.2f} từ quăng {row['tu_quang']:+.2f}s"
                f" trễ={row['tre']:.2f} lệch={row['lech']:+.2f}"
                f" mồi={_num(row['moi_du_doan'], '.0f')} vùng={row['vung_lo']:.0f}-{row['vung_hi']:.0f}"
                f" rộng={row['rong']:.0f} vùng thật={row['vung_that_lo']}-{row['vung_that_hi']}"
                f" tốc độ={_num(row['toc_do'], '.0f')} sai số={_num(row['sai_so'], '.0f')}px"
                f" mẫu={row['so_mau']} chờ={_num(row['cho'], '.2f')}s"
                f" ảnh cuối t={_num(row['mau_cuoi_t'], '.2f')} mồi={_num(row['mau_cuoi_moi'], '.0f')}"
                f" chụp {_num(row['chup_dau'], '.2f')}-{_num(row['chup_cuoi'], '.2f')}"
                f" err_px={_num(row.get('err_px'), '+.0f')}"
                f"{sau} {str(row['ket_qua_bam']).upper()}"
            )
            self._write_tap_csv(outcome, row)
        if self._tap_handle is not None:
            self._tap_handle.flush()
        self._cast_tap_log = []

    def _write_tap_csv(self, outcome: str, row: dict | None) -> None:
        if self._tap_writer is None:
            return
        if row is None:
            self._tap_writer.writerow([self.stats.casts, outcome, 0, "", "", "", *([""] * 23)])
            return
        self._tap_writer.writerow(
            [
                self.stats.casts,
                outcome,
                row["lan"],
                row["thanh"],
                row["lan_tren_thanh"],
                row["ket_qua_bam"],
                _num(row["t_lenh"], ".3f"),
                _num(row["tu_quang"], ".3f"),
                _num(row["tre"], ".3f"),
                _num(row["lech"], ".3f"),
                _num(row["moi_du_doan"], ".1f"),
                _num(row["vung_lo"], ".0f"),
                _num(row["vung_hi"], ".0f"),
                _num(row["rong"], ".0f"),
                row["vung_that_lo"],
                row["vung_that_hi"],
                _num(row["toc_do"], ".0f"),
                _num(row["sai_so"], ".1f"),
                row["so_mau"],
                _num(row["cho"], ".3f"),
                _num(row["mau_cuoi_t"], ".3f"),
                _num(row["mau_cuoi_moi"], ".1f"),
                _num(row["chup_dau"], ".3f"),
                _num(row["chup_cuoi"], ".3f"),
                _num(row["mau_sau_t"], ".3f"),
                _num(row["mau_sau_moi"], ".1f"),
                row["mau_sau_lo"] if row["mau_sau_lo"] is not None else "",
                row["mau_sau_hi"] if row["mau_sau_hi"] is not None else "",
                _num(row.get("err_px"), "+.1f"),
            ]
        )

    def _aim_zone(self) -> tuple[float, float]:
        """Vùng dùng để nhắm: giữa 3 lần đọc gần nhất.

        Mồi che một mép thì lần đọc vừa rồi hẹp hẳn so với bản rộng nhất của cùng thanh.
        Nhắm theo vệt hẹp đó (có lúc chỉ còn ~36px) thì cửa sổ giữa quá nhỏ, tool đứng chờ đến hết giờ.
        """
        los = sorted(zone[0] for zone in self._zone_seen)
        his = sorted(zone[1] for zone in self._zone_seen)
        mid = len(los) // 2
        recent = (float(los[mid]), float(his[mid]))
        if self._zone is None:
            return recent
        widest = (float(self._zone[0]), float(self._zone[1]))
        if recent[1] - recent[0] < 0.75 * (widest[1] - widest[0]):
            return widest
        return recent

    def _reset_slider(self, hit: bool = False) -> None:
        if hit and self._tapped_zone and self._zone is not None:
            self._on_hit()
        self._zone = None
        self._zone_seen = []
        self._tapped_zone = False
        self._cooldown_until = 0.0
        self.tracker.reset()

    def _fix_multiplier(self, img) -> bool:
        """True khi được phép quăng. False khi vừa bấm đổi hệ số, hoặc cần chụp lại.

        Đã thấy đúng hệ số một lần trong phiên này thì không bấm viên hệ số nữa. Một lần đọc nhầm
        cũng đủ đẩy x1 thành x50, vì game nhảy x20 → x50.
        """
        if self._mult_ok:
            return True
        current = read_multiplier(img, self.templates)
        if current is None:
            self._mult_misses += 1
            if self._mult_misses <= 4:
                self._pause(0.3)
                return False
            if not self._mult_logged:
                self.log("Không đọc được hệ số hiện tại. Giữ nguyên.")
                self._mult_logged = True
            return True
        self._mult_misses = 0
        if current == self.multiplier:
            self._mult_taps = 0
            self._mult_ok = True
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

    def _note_deferred_stop(self) -> None:
        if self._stop_noted:
            return
        self._stop_noted = True
        self.log("Đang câu dở. Câu nốt lượt này rồi dừng.")

    def _check(self) -> None:
        """Dừng ngay khi chưa vào lượt. Đang câu thì câu nốt, đóng màn kết quả, rồi mới dừng."""
        if not self.stop.is_set():
            self._settle_since = None
            return
        if self._cast_open:
            self._note_deferred_stop()
            self._settle_since = None
            return
        if self._last_kind in ("timesup", "result"):
            self._note_deferred_stop()
            if self._settle_since is None:
                self._settle_since = time.time()
            if time.time() - self._settle_since < STOP_SETTLE:
                return
        raise Stopped()


def _num(value, spec: str) -> str:
    if value is None:
        return ""
    return format(value, spec)


def _hold_hit(now: float, tapped: float, err: float | None, half: float) -> bool:
    """Cú đã rơi trong vùng vàng thì chờ game đổi thanh hoặc hiện kết quả, chưa gọi là trượt.

    Phiên 2026-11-06 00:08: lệch -8px và -23px vẫn câu được, nhưng result hiện lúc 1,5–1,6s.
    Gọi trượt lúc 1,2s làm tool bấm thêm một cú và đẩy độ trễ sai chiều.
    """
    if err is None or half <= 0 or abs(err) > half or tapped <= 0:
        return False
    return now < tapped + HIT_SETTLE


def _same_zone(new: tuple[int, int], known: tuple[int, int]) -> bool:
    """Cùng một thanh trượt hay đã sang thanh mới.

    Mồi đè lên vùng vàng làm vùng đọc được hẹp đi từ một phía, nhưng phía còn lại giữ nguyên. Thanh mới thì
    cả hai mép đổi. Trước đây chỉ so từng mép với ngưỡng nên vùng bị che bớt (lệch hơn 25px) bị tính là thanh mới,
    mô hình mồi bị xóa liên tục và tool không bao giờ gom đủ mẫu để bấm.
    Hai mép cùng trôi khoảng 30px mà vẫn chồng nhiều thì cũng là thanh đó: ánh sáng hoặc mồi làm vùng đọc
    dịch đi, không phải thanh mới. Thanh mới trong log nhảy tâm khoảng 80px trở lên.
    """
    overlap = min(new[1], known[1]) - max(new[0], known[0])
    width_new = new[1] - new[0]
    width_known = known[1] - known[0]
    smaller = max(1, min(width_new, width_known))
    edge_kept = abs(new[0] - known[0]) <= ZONE_SHIFT or abs(new[1] - known[1]) <= ZONE_SHIFT
    if edge_kept and overlap >= 0.4 * smaller:
        return True
    center_shift = abs((new[0] + new[1]) - (known[0] + known[1])) / 2
    wider = max(width_new, width_known, 1)
    return center_shift <= 40 and overlap >= 0.55 * smaller and smaller >= 0.7 * wider


def _stop_gold_samples(golds: list[int], elapsed: float, extra: int) -> bool:
    """Hết cần chụp thêm. extra là số ảnh đã chụp sau ảnh kết quả đầu."""
    if any(golds.count(value) >= 2 for value in set(golds)):
        return True
    if not golds and elapsed >= GOLD_LOOK:
        return True
    return extra >= RESULT_SAMPLES


# Ảnh Great!/Cool!/Loading/tên cá vẫn khớp nhầm một loài, điểm đo được nằm dưới 0,55.
# Thẻ cá đã hiện thì từ 0,67 trở lên. Ngưỡng này chỉ dùng khi chốt loài của một lượt.
CATCH_FLOOR = 0.60
# Đủ chắc thì không cần so thêm các ảnh còn lại.
CATCH_SURE = 0.80


def _choose_catch(catches: list):
    """Chọn loài trong các kết quả đã so, theo thứ tự ảnh cuối đến ảnh đầu.

    Ảnh cuối thường là thẻ cá đã đứng yên. Ảnh đầu hay còn chữ chuyển cảnh.
    Khớp dưới CATCH_FLOOR bị bỏ. Gặp khớp từ CATCH_SURE thì dừng.
    """
    best = None
    for catch in catches:
        if catch is None or catch.score < CATCH_FLOOR:
            continue
        if best is None or catch.score > best.score:
            best = catch
        if best.score >= CATCH_SURE:
            break
    return best


def _classify_frames(frames: list):
    """Loài chắc nhất trên các ảnh kết quả đã giữ. Không chốt ảnh chuyển cảnh."""
    found = []
    for frame in reversed(frames):
        found.append(classify(frame))
        chosen = _choose_catch(found)
        if chosen is not None and chosen.score >= CATCH_SURE:
            return chosen
    return _choose_catch(found)


def _pick_gold(golds: list[int]) -> int:
    """Chọn số Gold từ vài ảnh kết quả.

    Số chỉ nằm trên ảnh đầu rồi biến, nên một lần đọc từ 10 trở lên vẫn nhận (1.210 đọc được một lần là thật).
    Một chữ số lẻ (như 9 do tia sáng, hoặc mảnh đồng xu đọc thành 2) chỉ nhận khi lặp lại ở hai ảnh và không có số dài hơn.
    Số từ 10 trở lên thắng chữ số lẻ dù chữ số lẻ xuất hiện nhiều lần hơn: lượt +118 bị đọc thành [118, 118, 2, 2, 2, 2].
    """
    if not golds:
        return 0
    long = [value for value in golds if value >= 10]
    pool = long or golds
    best = max(set(pool), key=lambda value: (pool.count(value), value))
    if pool.count(best) >= 2 or best >= 10:
        return best
    return 0
