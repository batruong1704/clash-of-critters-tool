"""Đoán vị trí mồi và chọn lúc bấm.

Mồi chạy với tốc độ không đổi và nảy lại ở hai đầu thanh, nên vị trí là sóng tam giác theo thời gian.
Mỗi ảnh chụp mất gần nửa giây, nên không thể bấm theo ảnh vừa chụp. Tool ghi lại vài mẫu (giờ, vị trí),
dò tốc độ và pha khớp nhất, rồi tính giờ bấm sao cho lúc cú bấm tới game thì mồi nằm giữa vùng vàng.
"""

from __future__ import annotations

import numpy as np

from fishing_tool.vision import POINTER_HI, POINTER_LO

SPEED_MIN = 80.0
SPEED_MAX = 900.0
SPEED_STEP = 3.0
PHASE_STEP = 3.0
# Sai số mẫu cho phép (px) để coi là khớp. Giờ chụp lệch khoảng 0.1 giây là đã lệch 25–50px.
FIT_TOLERANCE = 40.0
OUTLIER_CAP = 120.0


def _triangle(unfolded: np.ndarray, span: float, lo: float) -> np.ndarray:
    phase = np.mod(unfolded, 2 * span)
    return lo + np.where(phase <= span, phase, 2 * span - phase)


class Tracker:
    def __init__(self, lo: float = POINTER_LO, hi: float = POINTER_HI, speed_range: tuple[float, float] | None = None):
        self.speed_min, self.speed_max = speed_range or (SPEED_MIN, SPEED_MAX)
        self.lo = lo
        self.span = hi - lo
        self.samples: list[tuple[float, float]] = []
        self._fit: tuple[float, float, float] | None = None

    def reset(self) -> None:
        self.samples.clear()
        self._fit = None

    def add(self, when: float, x: float) -> None:
        self.samples.append((when, float(min(max(x, self.lo), self.lo + self.span))))
        del self.samples[:-10]
        self._fit = None

    @property
    def count(self) -> int:
        return len(self.samples)

    def fit(self) -> tuple[float, float, float] | None:
        """(tốc độ px/s, pha lúc t=0, sai số trung bình px). None khi chưa đủ hai mẫu."""
        if self._fit is not None:
            return self._fit
        if len(self.samples) < 2:
            return None
        times = np.array([item[0] for item in self.samples])
        xs = np.array([item[1] for item in self.samples])
        base = times[0]
        rel = times - base
        speeds = np.arange(self.speed_min, self.speed_max, SPEED_STEP)
        phases = np.arange(0.0, 2 * self.span, PHASE_STEP)
        unfolded = phases[None, :, None] + speeds[:, None, None] * rel[None, None, :]
        predicted = _triangle(unfolded, self.span, self.lo)
        error = np.minimum(np.abs(predicted - xs[None, None, :]), OUTLIER_CAP)
        score = (error**2).mean(axis=2)
        best_rms = float(np.sqrt(score.min()))
        # Mẫu thưa khớp được cả một tốc độ rất cao (răng cưa). Trong các nghiệm khớp ngang nhau lấy tốc độ chậm nhất.
        good = score <= (best_rms + 2.0) ** 2
        v_index = int(np.where(good.any(axis=1))[0][0])
        p_index = int(np.argmin(np.where(good[v_index], score[v_index], np.inf)))
        speed = float(speeds[v_index])
        phase = float(phases[p_index]) - speed * base
        self._fit = (speed, phase, float(np.sqrt(score[v_index, p_index])))
        return self._fit

    def confident(self) -> bool:
        fit = self.fit()
        return fit is not None and len(self.samples) >= 3 and fit[2] <= FIT_TOLERANCE

    def position(self, when: float) -> float | None:
        fit = self.fit()
        if fit is None:
            return None
        speed, phase, _ = fit
        return float(_triangle(np.array([phase + speed * when]), self.span, self.lo)[0])

    def plan(self, now: float, latency: float, zone: tuple[float, float], horizon: float = 2.4):
        """Giờ phát lệnh bấm (time.time) để mồi vào giữa vùng. None khi chưa có mô hình."""
        if self.fit() is None:
            return None
        center = (zone[0] + zone[1]) / 2
        half = max(8.0, (zone[1] - zone[0]) * 0.15)
        steps = np.arange(0.02, horizon, 0.01)
        # Vùng ăn thật hẹp hơn vùng vàng nhìn thấy (memory.ZONE_TRUST). Mồi phải nằm trong phần này, không phải cả vùng.
        from fishing_tool.memory import ZONE_TRUST

        eat = (zone[1] - zone[0]) / 2 * ZONE_TRUST
        xs = np.array([self.position(now + step + latency) for step in steps])
        dist = np.abs(xs - center)
        inside = dist <= eat
        if inside.any():
            first = int(np.argmax(inside))
            end = first
            while end + 1 < len(inside) and inside[end + 1]:
                end += 1
            best = first + int(np.argmin(dist[first : end + 1]))
        else:
            return None
        return now + float(steps[best])
