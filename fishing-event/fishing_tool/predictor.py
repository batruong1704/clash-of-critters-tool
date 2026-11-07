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
# Vùng game 147 và 110. Ảnh đọc lệch vài px (109 vẫn là thanh 110) nên lấy từ 100.
# Thanh 73 và 36 ở dưới mức này, giữ 40% giữa.
WIDE_ZONE = 100.0
# Chừa từng này px mỗi mép vùng rộng. 20px ở 230px/s là khoảng 0,09s, đủ cho giờ chụp lệch.
EDGE_MARGIN = 20.0
# Sai số mẫu cho phép (px) để coi là khớp. Giờ chụp lệch khoảng 0.1 giây là đã lệch 25–50px.
FIT_TOLERANCE = 40.0
OUTLIER_CAP = 120.0


def aim_radius(width: float, measured: float | None = None) -> float:
    """Bán kính quanh tâm (px) mà cú bấm được phép rơi vào.

    Vùng rộng nhắm 55% nửa vùng: game ăn khoảng 60% nửa vùng, chừa phần còn lại cho sai số dự đoán.
    Trần chừa 20px mỗi mép siết thêm khi thanh không quá rộng. Bán kính học từ vùng hẹp không kéo
    cửa sổ này hẹp lại, vì số đó đo lúc tool chỉ nhắm 40% giữa.
    Vùng hẹp giữ 40% giữa, và không nhắm rộng hơn bán kính đã đo nếu có.
    """
    half = width / 2
    if width >= WIDE_ZONE:
        return min(half - EDGE_MARGIN, half * 0.55)
    visual = half * 0.40
    if measured is None:
        return visual
    return min(visual, measured)


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

    def velocity(self, when: float) -> float | None:
        """Tốc độ có dấu (px/s) của mô hình tại thời điểm này. Dương là chạy sang phải."""
        before = self.position(when)
        after = self.position(when + 0.02)
        if before is None or after is None:
            return None
        return (after - before) / 0.02

    def straight(self, n: int = 3) -> tuple[float, float] | None:
        """(tốc độ có dấu px/s, sai số px) nếu n mẫu cuối đi một chiều, không nảy và không đứng yên."""
        if len(self.samples) < n:
            return None
        pts = self.samples[-n:]
        dts = [pts[i][0] - pts[i - 1][0] for i in range(1, n)]
        dxs = [pts[i][1] - pts[i - 1][1] for i in range(1, n)]
        if any(dt < 0.12 or dt > 0.80 for dt in dts):
            return None
        if abs(sum(dxs)) < 40 or any(dx * sum(dxs) <= 0 for dx in dxs):
            return None
        speeds = [dx / dt for dx, dt in zip(dxs, dts)]
        mean = sum(speeds) / len(speeds)
        if abs(mean) < 80 or any(abs(speed - mean) > max(40.0, abs(mean) * 0.25) for speed in speeds):
            return None
        x0, t0 = pts[0][1], pts[0][0]
        err = [abs(x0 + mean * (t - t0) - x) for t, x in pts]
        rms = (sum(item * item for item in err) / len(err)) ** 0.5
        if rms > 18:
            return None
        return mean, rms

    def plan(self, now: float, latency: float, zone: tuple[float, float], horizon: float = 2.4, eat: float | None = None):
        """Giờ phát lệnh bấm (time.time) để mồi vào gần tâm vùng này. None khi chưa có mô hình.

        Trong cửa sổ ăn, vẫn chọn lúc mồi gần tâm nhất. Vùng rộng mở cửa sổ tới 55% nửa vùng
        (game ăn khoảng 60%), nên lượt mồi đi gần giữa cũng bấm được, không phải đợi vòng sau.
        Vùng hẹp giữ 40% giữa. `eat` là bán kính đo được từ các cú đã chấm (px quanh tâm).
        """
        if self.fit() is None:
            return None
        center = (zone[0] + zone[1]) / 2
        width = zone[1] - zone[0]
        steps = np.arange(0.02, horizon, 0.01)
        eat = aim_radius(width, eat)
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
