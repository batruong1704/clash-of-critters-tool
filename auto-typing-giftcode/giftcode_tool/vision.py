"""Nhận màn nhập gift code. So trên cả khung, không cắt viền đen.

Hộp Settings và hộp Redeem Rewards có nền tối hai bên. Cắt viền của tool nhận quà
co khung này lại và làm mẫu lệch tỉ lệ.
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from gift_tool.vision import Hit, imread

HERE = Path(__file__).resolve().parent
TEMPLATES = HERE / "templates"
WORK_WIDTH = 640
THRESHOLD = 0.80
# Bề rộng ảnh lúc cắt mẫu. Cùng tỉ lệ 9:16 thì ảnh 720 và ảnh 1392 dùng chung một mẫu.
SPECS = {
    "gear": 1392,
    "redemption": 1392,
    "settings": 720,
    "confirm": 720,
}
SCALES = (0.86, 0.95, 1.0, 1.05, 1.14)


class Icons:
    def __init__(self):
        self.templates = {}
        for name, screen_w in SPECS.items():
            self.templates[name] = (imread(TEMPLATES / f"{name}.png"), screen_w)

    def find(self, screen, name: str) -> Hit | None:
        templ, screen_w = self.templates[name]
        hit = _locate(screen, name, templ, screen_w)
        if hit is None or hit.w == 0 or hit.score < THRESHOLD:
            return None
        return hit


def field_point(screen, confirm: Hit) -> tuple[int, int]:
    """Ô nhập mã, phía trên nút Confirm, giữa hộp thoại."""
    height, width = screen.shape[:2]
    x = int(confirm.x - 0.23 * width)
    y = int(confirm.y - 0.18 * height)
    return max(10, x), max(10, y)


def reward_bar(screen) -> Hit | None:
    """Thanh xanh đáy màn. Open Another và Continue cùng một dạng. Không bấm."""
    height, width = screen.shape[:2]
    hsv = cv2.cvtColor(screen, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, (40, 90, 120), (85, 255, 255))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8))
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    best: Hit | None = None
    for contour in contours:
        x, y, bw, bh = cv2.boundingRect(contour)
        if bw < 0.65 * width or bh < 0.03 * height or bh > 0.16 * height:
            continue
        if y < 0.75 * height or bw / max(bh, 1) < 3:
            continue
        hit = Hit("reward", int(x + bw / 2), int(y + bh / 2), 1.0, bw, bh)
        if best is None or hit.w > best.w:
            best = hit
    return best


def _locate(screen, name: str, templ, screen_w: int) -> Hit | None:
    height, width = screen.shape[:2]
    work_w = min(width, WORK_WIDTH)
    ratio = work_w / width
    if ratio < 0.999:
        work = cv2.resize(screen, (work_w, max(1, int(height * ratio))), interpolation=cv2.INTER_AREA)
    else:
        work = screen
    base = work.shape[1] / screen_w
    best_score = -1.0
    best: Hit | None = None
    for scale in SCALES:
        tw = int(templ.shape[1] * base * scale)
        th = int(templ.shape[0] * base * scale)
        if tw < 8 or th < 8 or tw >= work.shape[1] or th >= work.shape[0]:
            continue
        shrinking = tw <= templ.shape[1] and th <= templ.shape[0]
        sized = cv2.resize(templ, (tw, th), interpolation=cv2.INTER_AREA if shrinking else cv2.INTER_LINEAR)
        result = cv2.matchTemplate(work, sized, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(result)
        if max_val <= best_score:
            continue
        best_score = float(max_val)
        cx = int(round((max_loc[0] + tw / 2) / ratio))
        cy = int(round((max_loc[1] + th / 2) / ratio))
        best = Hit(name, cx, cy, best_score, int(round(tw / ratio)), int(round(th / ratio)))
    return best
