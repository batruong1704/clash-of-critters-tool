"""Nhận màn hình câu cá từ ảnh chụp ADB 720x1280.

Mọi tọa độ tính theo tỉ lệ ảnh, đo trên ảnh 720x1280. Nút câu ở giữa đáy đổi màu theo bước:
xanh lá là chờ quăng, xám là chờ cá cắn, tím là đang kéo, tối là màn kết quả.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import cv2
import numpy as np

from fishing_tool import paths  # noqa: F401  (thêm checking-mvp vào sys.path)
from fishing_tool.paths import TEMPLATES
from gift_tool.vision import _corr, _digit_bank, imread

REF_W, REF_H = 720, 1280

# Nút câu và viên hệ số.
BUTTON = (0.5, 0.82)
RING_RADIUS = 0.125
BADGE = (488 / REF_W, 985 / REF_H)
# Vòng đổi hệ số của game: x1, x2, x3, x5, x10, x20, x50, x100 rồi về x1. x200 chưa thấy trong vòng đổi của tài khoản thử,
# chỉ dùng được khi có ảnh mẫu templates/mult_200.png.
MULTIPLIERS = (1, 2, 3, 5, 10, 20, 50, 100, 200)

# Thanh trượt. Vùng vàng nằm trong dải hàng này, mồi đỏ cao hơn thanh một chút.
SLIDER_ZONE_Y = (0.665, 0.685)
SLIDER_BOB_Y = (0.640, 0.700)
SLIDER_X = (0.22, 0.80)
SLIDER_MIN_YELLOW = 500

# Khoảng đi của tâm mồi trên ảnh 720 (đo trên video: tới 532 bên phải, thanh giữa 365).
POINTER_LO = 199.0
POINTER_HI = 532.0

DIGIT_SCORE = 0.50
DIGIT_MARGIN = 0.04

TEMPLATE_SPECS = {
    "pinball_btn": 0.85,
    "camp_btn": 0.85,
    "fish_tile": 0.80,
    **{f"mult_{value}": 0.80 for value in MULTIPLIERS},
}


@dataclass
class Scene:
    kind: str
    ring: str = ""
    detail: dict = field(default_factory=dict)


@dataclass
class Slider:
    lo: int | None
    hi: int | None
    pointer: float | None


def normalize(img):
    height, width = img.shape[:2]
    if (width, height) == (REF_W, REF_H):
        return img
    return cv2.resize(img, (REF_W, REF_H), interpolation=cv2.INTER_AREA)


class Templates:
    def __init__(self):
        # Ảnh hệ số nào chưa có file thì bỏ qua (x200), các ảnh khác thiếu là lỗi.
        self.images = {
            name: imread(TEMPLATES / f"{name}.png")
            for name in TEMPLATE_SPECS
            if not name.startswith("mult_") or (TEMPLATES / f"{name}.png").exists()
        }

    def has(self, name: str) -> bool:
        return name in self.images

    def match(self, img, name: str, region: tuple[int, int, int, int] | None = None):
        """Điểm khớp cao nhất và tâm của nó. region là (x0, y0, x1, y1) trên ảnh 720x1280."""
        templ = self.images[name]
        x0 = y0 = 0
        view = img
        if region is not None:
            x0, y0, x1, y1 = region
            view = img[y0:y1, x0:x1]
        if view.shape[0] < templ.shape[0] or view.shape[1] < templ.shape[1]:
            return 0.0, 0, 0
        result = cv2.matchTemplate(view, templ, cv2.TM_CCOEFF_NORMED)
        _, score, _, loc = cv2.minMaxLoc(result)
        return float(score), x0 + loc[0] + templ.shape[1] // 2, y0 + loc[1] + templ.shape[0] // 2

    def find(self, img, name: str, region=None):
        score, x, y = self.match(img, name, region)
        return (x, y) if score >= TEMPLATE_SPECS[name] else None


def ring_kind(img) -> str:
    """Màu vòng ngoài của nút câu: idle, wait, purple, dim hoặc other."""
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    samples = []
    for angle in range(0, 360, 30):
        a = np.deg2rad(angle)
        x = int(REF_W * BUTTON[0] + REF_W * RING_RADIUS * np.cos(a))
        y = int(REF_H * BUTTON[1] + REF_W * RING_RADIUS * np.sin(a))
        samples.append(hsv[y - 3 : y + 4, x - 3 : x + 4].reshape(-1, 3).mean(axis=0))
    h, s, v = np.median(np.array(samples), axis=0)
    if v < 90:
        return "dim"
    if 44 <= h <= 62 and s > 140 and v > 150:
        return "idle"
    if s < 45 and 60 <= v <= 170:
        return "wait"
    if 130 <= h <= 152 and v > 150:
        return "purple"
    return "other"


def _fraction(hsv, box, hue, smin, vmin) -> float:
    x0, y0, x1, y1 = box
    part = hsv[int(y0 * REF_H) : int(y1 * REF_H), int(x0 * REF_W) : int(x1 * REF_W)]
    mask = (part[..., 0] >= hue[0]) & (part[..., 0] <= hue[1]) & (part[..., 1] > smin) & (part[..., 2] > vmin)
    return float(mask.mean())


def read_slider(img) -> Slider:
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    x0 = int(SLIDER_X[0] * REF_W)
    x1 = int(SLIDER_X[1] * REF_W)
    strip = hsv[int(SLIDER_ZONE_Y[0] * REF_H) : int(SLIDER_ZONE_Y[1] * REF_H), x0:x1]
    yellow = (strip[..., 0] >= 18) & (strip[..., 0] <= 32) & (strip[..., 1] > 130) & (strip[..., 2] > 190)
    lo = hi = None
    if int(yellow.sum()) >= SLIDER_MIN_YELLOW:
        cols = np.where(yellow.sum(axis=0) >= 6)[0]
        if len(cols):
            lo, hi = int(cols.min()) + x0, int(cols.max()) + x0
    bob = hsv[int(SLIDER_BOB_Y[0] * REF_H) : int(SLIDER_BOB_Y[1] * REF_H), x0:x1]
    red = ((bob[..., 0] < 8) | (bob[..., 0] > 172)) & (bob[..., 1] > 140) & (bob[..., 2] > 150)
    pointer = None
    cols = np.where(red.sum(axis=0) >= 3)[0]
    if len(cols) >= 4:
        pointer = float(cols.mean()) + x0
    return Slider(lo, hi, pointer)


def read_scene(img, templates: Templates) -> Scene:
    """Đoán màn hình hiện tại. img đã ở 720x1280."""
    ring = ring_kind(img)
    if ring == "idle":
        return Scene("idle", ring)
    if ring == "wait":
        return Scene("wait", ring)
    if ring == "dim":
        return Scene("result", ring)
    if ring == "purple":
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        if _fraction(hsv, (0.0, 0.41, 1.0, 0.54), (5, 18), 150, 200) > 0.45:
            return Scene("timesup", ring)
        if _fraction(hsv, (0.24, 0.595, 0.78, 0.69), (125, 160), 90, 90) > 0.25:
            return Scene("reel", ring)
        slider = read_slider(img)
        if slider.lo is not None and slider.pointer is not None:
            return Scene("slider", ring, {"slider": slider})
        return Scene("busy", ring, {"slider": slider})
    if templates.find(img, "camp_btn", (560, 1200, 720, 1280)) is not None:
        return Scene("pinball", ring)
    if templates.find(img, "pinball_btn", (560, 1200, 720, 1280)) is not None:
        return Scene("yard", ring)
    return Scene("unknown", ring)


def read_multiplier(img, templates: Templates) -> int | None:
    x, y = int(BADGE[0] * REF_W), int(BADGE[1] * REF_H)
    region = (x - 50, y - 40, x + 50, y + 40)
    best = None
    for value in MULTIPLIERS:
        if not templates.has(f"mult_{value}"):
            continue
        score, _, _ = templates.match(img, f"mult_{value}", region)
        if score >= TEMPLATE_SPECS[f"mult_{value}"] and (best is None or score > best[0]):
            best = (score, value)
    return best[1] if best else None


def fish_tile_point(img, templates: Templates):
    """Tâm ô Fishing Contest bên phải màn Pinball. Ô nằm ngay dưới mắt cá nên cộng thêm chiều cao."""
    hit = templates.find(img, "fish_tile", (440, 200, 720, 1000))
    if hit is None:
        return None
    return hit[0], hit[1] + 60


def _glyph_bank():
    return _digit_bank()


def _read_glyph(glyph) -> str | None:
    bank = _glyph_bank()
    if not bank:
        return None
    sample = cv2.resize(glyph, (16, 22), interpolation=cv2.INTER_AREA).astype(np.float32)
    ranked = sorted(((_corr(sample, tpl.astype(np.float32)), key) for key, tpl in bank.items()), reverse=True)
    score, best = ranked[0]
    second = ranked[1][0] if len(ranked) > 1 else -1.0
    if score < DIGIT_SCORE or score - second < DIGIT_MARGIN:
        return None
    return best


def _read_digits(img, box, height_range, kind: str, rightmost: bool = False) -> int | None:
    """Đọc dãy chữ số trong box (tỉ lệ). Chữ trắng hoặc vàng, có viền đen quanh nét."""
    x0, y0, x1, y1 = box
    px0, px1 = int(x0 * REF_W), int(x1 * REF_W)
    py0, py1 = int(y0 * REF_H), int(y1 * REF_H)
    crop = img[py0:py1, px0:px1]
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    if kind == "gold":
        hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
        fill = (hsv[..., 0] >= 12) & (hsv[..., 0] <= 32) & (hsv[..., 1] >= 100) & (hsv[..., 2] >= 190)
    else:
        fill = gray >= 185
    dark = (gray <= 90).astype(np.uint8)
    near = cv2.dilate(dark, np.ones((9, 9), np.uint8)) > 0
    mask = (fill & near).astype(np.uint8) * 255
    count, _, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
    low, high = int(height_range[0] * REF_H), int(height_range[1] * REF_H)
    glyphs = []
    for index in range(1, count):
        x, y, w, h, area = [int(v) for v in stats[index]]
        if h < low or h > high or w > h * 1.1 or w < h * 0.2 or area < 40:
            continue
        glyphs.append((x, y, w, h))
    if not glyphs:
        return None
    glyphs.sort()
    # Giữ các chữ cùng hàng với chữ cao nhất. Viền đồng xu hay sao lấp lánh nằm lệch hàng.
    anchor = max(glyphs, key=lambda item: item[3])
    mid = anchor[1] + anchor[3] / 2
    row = [g for g in glyphs if abs(g[1] + g[3] / 2 - mid) <= anchor[3] * 0.25]
    chain = [row[0]]
    for item in row[1:]:
        prev = chain[-1]
        if item[0] - (prev[0] + prev[2]) <= prev[3] * 0.9:
            chain.append(item)
        else:
            chain = [item] if rightmost else chain
    digits = []
    for x, y, w, h in chain:
        glyph = mask[y : y + h, x : x + w]
        digit = _read_glyph(glyph)
        if digit is None:
            return None
        digits.append(digit)
    if not digits or len(digits) > 7:
        return None
    return int("".join(digits))


def read_rods(img) -> int | None:
    """Số rod dưới nút câu."""
    return _read_digits(img, (0.40, 0.87, 0.62, 0.925), (0.0125, 0.020), "white")


def read_gold(img) -> int | None:
    """Gold Coin hiện thoáng ở trên con cá khi phá kỷ lục."""
    return _read_digits(img, (0.60, 0.30, 0.95, 0.40), (0.017, 0.027), "gold")
