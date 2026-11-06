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
        self._late_lead = 0.0
        if enabled:
            self._load()

    def _load(self) -> None:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            taps = data.get("taps", [])
            self.taps = [t for t in taps if isinstance(t, dict) and "hit" in t]
            self._late_lead = min(0.20, max(0.0, float(data.get("late_lead") or 0.0)))
        except (OSError, ValueError, AttributeError, TypeError):
            self.taps = []
            self._late_lead = 0.0

    def _save(self) -> None:
        if not self.enabled:
            return
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(
                json.dumps(
                    {"version": 2, "late_lead": self._late_lead, "taps": self.taps[-KEEP_TAPS:]},
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

    def late_lead(self) -> float:
        """Giây bù thêm khi cú bấm tới muộn hơn giả định. 0 nếu máy này chưa trượt kiểu đó."""
        return self._late_lead

    def set_late_lead(self, value: float) -> None:
        if not self.enabled:
            return
        self._late_lead = round(min(0.20, max(0.0, float(value))), 3)
        self._save()

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
        learned = sum(1 for t in self.taps if t.get("ok"))
        return f"{total} cú bấm đã nhớ, trúng {hits} ({100 * hits / total:.0f}%), {learned} cú dùng được để dò độ trễ"
