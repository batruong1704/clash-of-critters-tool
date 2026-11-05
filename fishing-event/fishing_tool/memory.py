"""Bộ nhớ học qua các phiên: ghi từng cú bấm thanh trượt, rút ra độ trễ thật của cú bấm.

Cú bấm đi từ lệnh ADB tới game mất một khoảng L (chừng 0.3 giây, hơi dao động). Sau mỗi cú bấm, tool biết kết quả
(trúng hay trượt) và biết đường đi của mồi nhờ các mẫu của cả thanh. Với mỗi L thử, tool kiểm tra: "nếu cú bấm tới game
sau L giây thì mồi có nằm trong vùng vàng không", rồi so với kết quả thật. Các L cho ra kết quả khớp được lưu lại
cùng cú bấm. Độ trễ tốt nhất là L khớp với nhiều cú bấm nhất, tính trên các cú bấm gần đây.

Cách này học được cả từ cú trượt và biết lệch về phía nào, không cần thử mò từng mức độ lệch.
"""

from __future__ import annotations

import json
import os
import time

import numpy as np

from fishing_tool.paths import DATA

MEMORY_FILE = DATA / "hoc.json"
KEEP_TAPS = 400  # số cú bấm giữ lại trong file
WINDOW = 120  # chỉ xét chừng này cú bấm có dữ liệu đường mồi gần nhất khi tính độ trễ
MIN_TAPS = 8  # ít hơn thì chưa tin, dùng độ trễ mặc định
LATENCY_GRID = tuple(round(float(x), 2) for x in np.arange(-0.30, 0.91, 0.02))
FIT_RMS_MAX = 40.0  # đường mồi khớp tệ hơn mức này (px) thì không dùng để học
MIN_SAMPLES = 6
# Vùng ăn thật chỉ nhỏ hơn vùng vàng nhìn thấy: khớp 95% khi chỉ tính 50-80% nửa vùng, còn 90% khi tính cả vùng.
ZONE_TRUST = 0.7  # số mẫu tối thiểu của thanh để học từ cú bấm đó


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
        if enabled:
            self._load()

    def _load(self) -> None:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            taps = data.get("taps", [])
            self.taps = [t for t in taps if isinstance(t, dict) and "hit" in t]
        except (OSError, ValueError, AttributeError):
            self.taps = []

    def _save(self) -> None:
        if not self.enabled:
            return
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps({"version": 2, "taps": self.taps[-KEEP_TAPS:]}, ensure_ascii=False), encoding="utf-8")
            os.replace(tmp, self.path)
        except OSError:
            pass  # không ghi được thì vẫn câu bình thường, chỉ mất phần nhớ

    @property
    def hits(self) -> list[dict]:
        return [t for t in self.taps if t["hit"]]

    def latency(self) -> tuple[float, int] | None:
        """(độ trễ tốt nhất, số cú bấm đã dùng). None khi chưa đủ dữ liệu."""
        usable = [t["ok"] for t in self.taps if t.get("ok")][-WINDOW:]
        if len(usable) < MIN_TAPS:
            return None
        votes = np.zeros(len(LATENCY_GRID))
        index = {value: i for i, value in enumerate(LATENCY_GRID)}
        for good in usable:
            for value in good:
                votes[index[value]] += 1
        best = votes.max()
        # Vùng phẳng quanh đỉnh: lấy điểm giữa, vì dao động nên đỉnh đơn lẻ dễ lệch.
        plateau = np.array(LATENCY_GRID)[votes >= best - max(1.0, 0.03 * len(usable))]
        return float(np.median(plateau)), len(usable)

    def record(
        self,
        total: float,
        hit: bool,
        width: int | None = None,
        speed: float | None = None,
        first: bool = False,
        ok: list[float] | None = None,
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
