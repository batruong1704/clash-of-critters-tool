"""Bộ nhớ học qua các phiên: ghi từng cú bấm thanh trượt, rút ra độ trễ thật của cú bấm.

Cú bấm đi từ lệnh ADB tới game mất một khoảng L (đo trên các lượt chiều 5/11 là khoảng 0,14 giây).
Sau mỗi cú bấm, tool thử nhiều L và lưu những L khiến mồi nằm trong hoặc ngoài vùng vàng đúng với kết quả.

Độ trễ chỉ rút từ cú trúng. Với cú trúng, các L khớp tạo một đoạn liền (lúc mồi đi ngang vùng vàng). Giữa đoạn đó
là lúc mồi ở giữa vùng. Trung vị của các lúc này, trên các cú trúng gần đây, là độ trễ dùng cho lần bấm sau.

Cú trượt không được đưa vào. Lúc trượt, gần như mọi L đều "khớp" vì mồi chỉ ở trong vùng một khoảnh ngắn, nên phiếu
bầu bị dàn đều từ -0,3 đến 0,9 giây và trung vị của cả dải đó trôi về 0. Phiên 13:38 tool đã bấm với độ trễ 0 và âm,
mồi ra khỏi vùng trước khi game nhận cú bấm.
"""

from __future__ import annotations

import json
import os
import time

import numpy as np

from fishing_tool.paths import DATA

MEMORY_FILE = DATA / "hoc.json"
KEEP_TAPS = 400  # số cú bấm giữ lại trong file
HIT_WINDOW = 40  # chỉ lấy chừng này cú trúng gần nhất khi tính độ trễ
MIN_TAPS = 8  # ít hơn thì chưa tin, dùng độ trễ mặc định
LATENCY_GRID = tuple(round(float(x), 2) for x in np.arange(-0.30, 0.91, 0.02))
FIT_RMS_MAX = 40.0  # đường mồi khớp tệ hơn mức này (px) thì không dùng để học
MIN_SAMPLES = 6
# Vùng ăn thật chỉ nhỏ hơn vùng vàng nhìn thấy: khớp 95% khi chỉ tính 50-80% nửa vùng, còn 90% khi tính cả vùng.
ZONE_TRUST = 0.7  # số mẫu tối thiểu của thanh để học từ cú bấm đó
# Độ trễ cú bấm hợp lý trên emulator: máy này 0,29s, máy chậm đã gặp 0,50s.
DELAY_MIN = 0.15
DELAY_MAX = 0.70
# Hồ sơ máy nhớ qua các phiên: số lần chữ nổ đã thấy (độ chắc của độ trễ), các khoảng chữ nổ gần nhất,
# thời gian chụp một ảnh, vệt trắng nền của thanh. Phiên mới không phải dò lại từ đầu.
FLASH_COUNT_CAP = 100
BRACKETS_KEEP = 8
# Lệch nhắm: game nhận cú bấm sớm hơn lúc nổ chữ một chút (video 7/11: mồi đứng yên 3 khung rồi mới nổ), nên độ trễ
# đo theo chữ nổ hơi muộn so với lúc game nhận. err_px không đo được phần này (mồi tại giờ tới giả định luôn ở tâm
# vì tool nhắm vào đó). Chỉ cú dò trúng mới cho biết: trượt sát tâm khi độ trễ đã chắc thì dò lệch ± đúng bán kính
# ăn, cú nào trúng thì phần bù của cú đó là một số đo. Trung vị các số đo gần nhất là lệch nhắm đem vào giờ bấm.
# Âm là phát lệnh muộn hơn độ trễ chữ nổ. Chữ nổ không thể tới trước lúc game nhận nên lệch dương chỉ cho vài phần trăm.
BIAS_WINDOW = 12
BIAS_MIN = -0.10
BIAS_MAX = 0.02


def _clamp_delay(value: float) -> float:
    return round(min(DELAY_MAX, max(DELAY_MIN, value)), 3)


def _hit_center(tap: dict) -> float | None:
    """Giữa khoảng thời gian mồi nằm trong vùng vàng ở một cú trúng. None nếu cú này không chỉ ra được lúc bấm tới."""
    if not tap.get("hit") or not tap.get("ok"):
        return None
    values = sorted({round(float(value), 2) for value in tap["ok"]})
    if not values:
        return None
    runs = [[values[0]]]
    for value in values[1:]:
        if abs(value - runs[-1][-1] - 0.02) < 0.005:
            runs[-1].append(value)
        else:
            runs.append([value])
    run = max(runs, key=len)
    span = run[-1] - run[0]
    # Ngắn hơn 0,06s là nhiễu một mẫu. Dài hơn 0,55s thì mồi bị coi là nằm trong vùng gần cả vòng, không chỉ ra lúc tới.
    if span < 0.06 or span > 0.55:
        return None
    center = float(np.median(run))
    if center < 0.05 or center > 0.40:
        return None
    return center


def consistent_latencies(tracker, tap_time: float, zone: tuple[int, int], hit: bool) -> list[float] | None:
    """Các độ trễ L mà giả sử cú bấm tới game sau L giây thì mồi trong/ngoài vùng khớp với kết quả. None nếu chưa đủ dữ liệu."""
    if zone is None or tracker.count < MIN_SAMPLES:
        return None
    fit = tracker.fit()
    if fit is None or fit[2] > FIT_RMS_MAX:
        return None
    center = (zone[0] + zone[1]) / 2
    half = (zone[1] - zone[0]) / 2 * ZONE_TRUST
    good = []
    for latency in LATENCY_GRID:
        pos = tracker.position(tap_time + latency)
        if (abs(pos - center) <= half) == hit:
            good.append(latency)
    return good


class Memory:
    def __init__(self, path=MEMORY_FILE, enabled: bool = True):
        self.path = path
        self.enabled = enabled
        self.taps: list[dict] = []
        self._tap_delay: float | None = None
        self.flash_count = 0
        self.brackets: list[tuple[float, float]] = []
        self.shot_dur: float | None = None
        self.white_base: float | None = None
        if enabled:
            self._load()

    def _load(self) -> None:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            taps = data.get("taps", [])
            self.taps = [t for t in taps if isinstance(t, dict) and "hit" in t]
            raw = data.get("tre_may")
            self._tap_delay = None if raw is None else _clamp_delay(float(raw))
            self.flash_count = min(FLASH_COUNT_CAP, max(0, int(data.get("chu_no") or 0)))
            self.brackets = [
                (float(lo), float(hi))
                for lo, hi in (data.get("khoang") or [])
                if DELAY_MIN - 0.05 <= float(lo) <= float(hi) <= DELAY_MAX + 0.05
            ][-BRACKETS_KEEP:]
            self.shot_dur = _optional(data.get("chup"), 0.10, 2.00)
            self.white_base = _optional(data.get("trang_nen"), 0.02, 0.30)
        except (OSError, ValueError, AttributeError, TypeError):
            self.taps = []
            self._tap_delay = None
            self.flash_count = 0
            self.brackets = []
            self.shot_dur = None
            self.white_base = None

    def _save(self) -> None:
        if not self.enabled:
            return
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(
                json.dumps(
                    {
                        "version": 4,
                        "tre_may": self._tap_delay,
                        "chu_no": self.flash_count,
                        "khoang": [[round(lo, 3), round(hi, 3)] for lo, hi in self.brackets[-BRACKETS_KEEP:]],
                        "chup": None if self.shot_dur is None else round(self.shot_dur, 3),
                        "trang_nen": None if self.white_base is None else round(self.white_base, 3),
                        "taps": self.taps[-KEEP_TAPS:],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            os.replace(tmp, self.path)
        except OSError:
            pass  # không ghi được thì vẫn câu bình thường, chỉ mất phần nhớ

    @property
    def hits(self) -> list[dict]:
        return [t for t in self.taps if t["hit"]]

    def tap_delay(self) -> float | None:
        """Độ trễ cú bấm của máy này (giây, lệnh tới lúc game nổ chữ), đo từ các lần thấy chữ nổ. None khi chưa đo."""
        return self._tap_delay

    def set_tap_delay(self, value: float) -> None:
        if not self.enabled:
            return
        self._tap_delay = _clamp_delay(float(value))
        self._save()

    def set_profile(
        self,
        flash_count: int | None = None,
        brackets: list[tuple[float, float]] | None = None,
        shot_dur: float | None = None,
        white_base: float | None = None,
    ) -> None:
        """Ghi hồ sơ máy để phiên sau bắt đầu ngay ở chỗ phiên này dừng."""
        if not self.enabled:
            return
        if flash_count is not None:
            self.flash_count = min(FLASH_COUNT_CAP, max(0, int(flash_count)))
        if brackets is not None:
            self.brackets = [(float(lo), float(hi)) for lo, hi in brackets][-BRACKETS_KEEP:]
        if shot_dur is not None:
            self.shot_dur = float(shot_dur)
        if white_base is not None:
            self.white_base = float(white_base)
        self._save()

    def aim_bias(self) -> tuple[float, int] | None:
        """(lệch nhắm, số cú dò trúng đã dùng), giây. None khi chưa có cú dò nào trúng.

        Mỗi cú dò trúng ghi `xe` = phần bù so với độ trễ chữ nổ lúc đó. Trung vị của các cú gần nhất là phần
        bù cho lần sau. Một cú trúng đã đủ dùng: vùng ăn ±10px nên cú đó chỉ ra lệch tới ±0,045s.
        """
        rows = [tap for tap in self.taps if tap.get("xe") is not None][-BIAS_WINDOW:]
        if not rows:
            return None
        bias = float(np.median([float(tap["xe"]) for tap in rows]))
        return round(min(BIAS_MAX, max(BIAS_MIN, bias)), 3), len(rows)

    def latency(self) -> tuple[float, int] | None:
        """(độ trễ tốt nhất, số cú trúng đã dùng). None khi chưa đủ cú trúng rõ ràng."""
        centers = [center for tap in self.taps if (center := _hit_center(tap)) is not None][-HIT_WINDOW:]
        if len(centers) < MIN_TAPS:
            return None
        return float(np.median(centers)), len(centers)

    def eat_limit(self) -> float | None:
        """Bán kính quanh tâm (px) mà các cú trúng còn nằm trong. None khi chưa đủ 20 cú có err_px.

        Lấy phân vị 80 của |err_px| các cú trúng. Nếu một cú trượt lệch ít hơn mức đó thì hạ xuống dưới cú trượt ấy.
        """
        rows = [tap for tap in self.taps if tap.get("err") is not None]
        if len(rows) < 20:
            return None
        hits = sorted(abs(float(tap["err"])) for tap in rows if tap.get("hit"))
        misses = sorted(abs(float(tap["err"])) for tap in rows if not tap.get("hit"))
        if len(hits) < 8:
            return None
        limit = hits[min(len(hits) - 1, int(round((len(hits) - 1) * 0.80)))]
        if misses and misses[0] - 2 >= 12:
            limit = min(limit, misses[0] - 2)
        return float(min(55.0, max(12.0, limit)))

    def record(
        self,
        total: float,
        hit: bool,
        width: int | None = None,
        speed: float | None = None,
        first: bool = False,
        ok: list[float] | None = None,
        err: float | None = None,
        xe: float | None = None,
    ) -> None:
        if not self.enabled:
            return
        self.taps.append(
            {
                "t": int(time.time()),
                "total": round(total, 3),
                "hit": bool(hit),
                "width": width,
                "speed": None if speed is None else round(speed),
                "first": first,
                "ok": ok,
                "err": None if err is None else round(float(err), 1),
                "xe": None if xe is None else round(float(xe), 3),
            }
        )
        if len(self.taps) > KEEP_TAPS:
            del self.taps[: len(self.taps) - KEEP_TAPS]
        self._save()

    def summary(self) -> str:
        total = len(self.taps)
        if not total:
            return "chưa có dữ liệu"
        hits = len(self.hits)
        parts = [f"{total} cú bấm đã nhớ, trúng {hits} ({100 * hits / total:.0f}%)"]
        if self.flash_count:
            parts.append(f"chữ nổ đã thấy {self.flash_count} lần")
        bias = self.aim_bias()
        if bias is not None:
            parts.append(f"lệch nhắm {bias[0]:+.2f}s theo {bias[1]} cú dò trúng")
        if self.shot_dur is not None:
            parts.append(f"chụp {self.shot_dur:.2f}s/ảnh")
        return ", ".join(parts)


def _optional(raw, lo: float, hi: float) -> float | None:
    if raw is None:
        return None
    value = float(raw)
    return value if lo <= value <= hi else None
