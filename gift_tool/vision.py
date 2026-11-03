"""Tìm nút trên ảnh chụp màn hình bằng ảnh mẫu."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from gift_tool.paths import TEMPLATES

# Ngưỡng và bề rộng ảnh gốc lúc cắt mẫu. Điểm khớp từ 0 đến 1.
SPECS = {
    "search": {"threshold": 0.72, "screen_w": 559, "color": False},
    "results": {"threshold": 0.80, "screen_w": 560, "color": False},
    "add": {"threshold": 0.78, "screen_w": 560, "color": False},
    "visit": {"threshold": 0.80, "screen_w": 720, "color": True},
    "gift": {"threshold": 0.78, "screen_w": 567, "color": True},
    "close": {"threshold": 0.93, "screen_w": 567, "color": False},
    "select": {"threshold": 0.75, "screen_w": 580, "color": False},
    "ok": {"threshold": 0.75, "screen_w": 584, "color": False},
    "missing_id": {"threshold": 0.70, "screen_w": 553, "color": False, "text": True},
    "goldrush": {"threshold": 0.78, "screen_w": 560, "color": True},
    "friends": {"threshold": 0.80, "screen_w": 560, "color": True},
    "community": {"threshold": 0.80, "screen_w": 559, "color": True},
}

SCALES = (0.86, 0.95, 1.0, 1.05, 1.14)
WORK_WIDTH = 640
# Tab Add New nằm dưới nút Community, lệch trái. Đo trên ảnh 559x1004.
ADD_NEW_TAB_X = 0.18
ADD_NEW_TAB_BELOW_COMMUNITY = 0.093
BADGE_DARK = 60
BADGE_MIN_W = 36
# Độ rộng viên Lvl tính theo bề rộng nút Add: nền cộng thêm một khoảng cho mỗi chữ số.
# Đo trên 720x1280: 1 chữ 89-93px, 2 chữ 103-107px, 3 chữ 117px, nút Add rộng 146px.
BADGE_BASE_RATIO = 0.51
BADGE_DIGIT_RATIO = 0.096
# Chữ 1 hẹp hơn chữ khác, nên làm tròn nghiêng về ít chữ hơn để khỏi bắt lỗi oan.
BADGE_ROUND_BIAS = 0.35
DIGIT_SCORE = 0.64
DIGIT_MARGIN = 0.08
DIGIT_BOX = (16, 22)
# Tâm chữ "l" khoảng 2.8–3.0 lần chiều cao nét; tâm chữ số đầu khoảng 3.7–3.9.
# Cắt theo bề rộng viên thì viên 1–2 chữ số ngắn lại, chữ l lọt vào phần số và cả cấp thành rỗng.
LVL_GLYPH_CUT = 3.25
# Arial Bold đọc hụt chữ 1. Cấp dưới 150 gần như luôn có chữ 1, cả số thành rỗng và tool vẫn bấm Visit.
FONT_FILES = ("malgunbd.ttf", "arialbd.ttf")
FONT_PX = 28
FONT_CANVAS = 64


def letter_mask(image):
    """Chữ trắng có viền đen. Dùng để nhận câu báo không tìm thấy ID."""
    gray = image if image.ndim == 2 else cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    bright = (gray >= 188).astype(np.uint8) * 255
    dark = (gray <= 70).astype(np.uint8) * 255
    near_dark = cv2.dilate(dark, np.ones((3, 3), np.uint8))
    return cv2.bitwise_and(bright, near_dark)


def imread(path: Path):
    data = np.fromfile(str(path), dtype=np.uint8)
    img = cv2.imdecode(data, cv2.IMREAD_COLOR)
    if img is None:
        raise FileNotFoundError(path)
    return img


def imwrite(path: Path, img) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imencode(".png", img)[1].tofile(str(path))


@dataclass(frozen=True)
class Hit:
    name: str
    x: int
    y: int
    score: float
    w: int
    h: int


class Finder:
    def __init__(self, template_dir: Path = TEMPLATES):
        self.templates = {}
        for name, spec in SPECS.items():
            path = template_dir / f"{name}.png"
            image = imread(path)
            self.templates[name] = (image, spec)

    def locate(self, screen, name: str, scales=None) -> Hit | None:
        """Điểm khớp cao nhất, kể cả khi dưới ngưỡng. Dùng cho bước kiểm tra."""
        image, spec = self.templates[name]
        score, hit = self._match(screen, name, image, spec, scales)
        if hit is None:
            return Hit(name, 0, 0, score, 0, 0)
        return hit

    def find(self, screen, name: str, scales=None) -> Hit | None:
        hit = self.locate(screen, name, scales)
        if hit is None or hit.w == 0:
            return None
        if hit.score < self.templates[name][1]["threshold"]:
            return None
        return hit

    def find_below(self, screen, name: str, y0: int, y1: int, scales=None) -> Hit | None:
        """Tìm nút trong một dải ngang của ảnh, rồi trả tọa độ trên ảnh gốc."""
        height = screen.shape[0]
        top = min(max(0, y0), height - 2)
        bottom = min(max(top + 2, y1), height)
        hit = self.find(screen[top:bottom], name, scales)
        if hit is None:
            return None
        return Hit(hit.name, hit.x, hit.y + top, hit.score, hit.w, hit.h)

    def _match(self, screen, name: str, templ, spec, scales=None) -> tuple[float, Hit | None]:
        screen_h, screen_w = screen.shape[:2]
        work_w = min(screen_w, WORK_WIDTH)
        ratio = work_w / screen_w
        if ratio < 0.999:
            work = cv2.resize(screen, (work_w, max(1, int(screen_h * ratio))), interpolation=cv2.INTER_AREA)
        else:
            work = screen
        base = work.shape[1] / spec["screen_w"]
        if spec.get("text"):
            src = letter_mask(templ)
            hay = letter_mask(work)
        elif spec["color"]:
            src = templ
            hay = work
        else:
            src = cv2.cvtColor(templ, cv2.COLOR_BGR2GRAY)
            hay = cv2.cvtColor(work, cv2.COLOR_BGR2GRAY)
        best_score = -1.0
        best: Hit | None = None
        for scale in (SCALES if scales is None else scales):
            tw = int(src.shape[1] * base * scale)
            th = int(src.shape[0] * base * scale)
            if tw < 8 or th < 8 or tw >= hay.shape[1] or th >= hay.shape[0]:
                continue
            sized = cv2.resize(src, (tw, th), interpolation=cv2.INTER_AREA if scale * base < 1 else cv2.INTER_LINEAR)
            result = cv2.matchTemplate(hay, sized, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, max_loc = cv2.minMaxLoc(result)
            if max_val > best_score:
                best_score = float(max_val)
                cx = int(round((max_loc[0] + tw / 2) / ratio))
                cy = int(round((max_loc[1] + th / 2) / ratio))
                best = Hit(name, cx, cy, best_score, int(round(tw / ratio)), int(round(th / ratio)))
        return best_score, best


def field_point(screen, search: Hit) -> tuple[int, int]:
    """Ô nhập UID, nằm bên trái icon kính lúp."""
    width = screen.shape[1]
    x = int(search.x - 0.40 * width)
    return max(10, x), int(search.y)


def add_new_tab_point(screen, community: Hit) -> tuple[int, int]:
    """Tab Add New. Tab đang chọn và tab chưa chọn khác màu, nên không so mẫu mà tính từ nút Community."""
    height, width = screen.shape[:2]
    return int(ADD_NEW_TAB_X * width), int(community.y + ADD_NEW_TAB_BELOW_COMMUNITY * height)


def avatar_point(screen, add: Hit) -> tuple[int, int]:
    """Avatar hàng kết quả, nằm bên trái nút Add."""
    width = screen.shape[1]
    x = int(add.x - 0.68 * width)
    return max(10, x), int(add.y)


def scene_signature(screen):
    """Thu nhỏ vùng sân, bỏ mép trên và nút X. Dùng để xem camera có trượt tới hộp quà không."""
    height, width = screen.shape[:2]
    y0 = int(0.16 * height)
    y1 = int(0.80 * height)
    x0 = int(0.10 * width)
    x1 = int(0.90 * width)
    y0 = min(max(0, y0), height - 2)
    y1 = min(max(y0 + 2, y1), height)
    x0 = min(max(0, x0), width - 2)
    x1 = min(max(x0 + 2, x1), width)
    gray = cv2.cvtColor(screen[y0:y1, x0:x1], cv2.COLOR_BGR2GRAY)
    small = cv2.resize(gray, (32, 48), interpolation=cv2.INTER_AREA)
    return cv2.GaussianBlur(small, (3, 3), 0)


def result_signature(screen, search: Hit):
    """Ảnh xám vùng hàng kết quả, để so trước và sau khi tìm."""
    height, width = screen.shape[:2]
    y0 = int(search.y + 0.08 * height)
    y1 = int(search.y + 0.28 * height)
    x0 = int(0.04 * width)
    x1 = int(0.96 * width)
    y0 = min(max(0, y0), height - 2)
    y1 = min(max(y0 + 2, y1), height)
    x0 = min(max(0, x0), width - 2)
    x1 = min(max(x0 + 2, x1), width)
    gray = cv2.cvtColor(screen[y0:y1, x0:x1], cv2.COLOR_BGR2GRAY)
    return cv2.resize(gray, (180, 90), interpolation=cv2.INTER_AREA)


def signature_diff(before, after) -> float:
    return float(np.mean(cv2.absdiff(before, after)))


def player_level(screen, add: Hit) -> int | None:
    """Cấp trên nhãn Lvl của hàng Results. Không đọc cấp thú ở phía trên màn hình."""
    badge = _level_badge(screen, add)
    if badge is None:
        return None
    glyphs = _badge_digits(badge)
    if not glyphs:
        return None
    digits = []
    for glyph in glyphs:
        digit = _read_digit(glyph)
        if digit is None:
            return None
        digits.append(digit)
    if len(digits) > 4:
        return None
    # Viên rộng hơn số chữ đọc được nghĩa là rớt chữ. Trả rỗng để chụp lại, đừng ghi cấp thấp oan.
    if _expected_digits(badge.shape[1], add.w) > len(digits):
        return None
    return int("".join(digits))


def _expected_digits(badge_width: int, add_width: int) -> int:
    ratio = badge_width / max(1, add_width)
    return int((ratio - BADGE_BASE_RATIO) / BADGE_DIGIT_RATIO + BADGE_ROUND_BIAS)


def _level_badge(screen, add: Hit):
    """Nhãn đen ngay bên trái nút Add, dưới tên người chơi."""
    height, width = screen.shape[:2]
    x0 = int(add.x - 0.62 * width)
    x1 = int(add.x - add.w * 0.70)
    y0 = int(add.y - add.h * 0.05)
    y1 = int(add.y + add.h * 0.55)
    x0 = min(max(0, x0), width - 2)
    x1 = min(max(x0 + 2, x1), width)
    y0 = min(max(0, y0), height - 2)
    y1 = min(max(y0 + 2, y1), height)
    crop = screen[y0:y1, x0:x1]
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    dark = (gray < BADGE_DARK).astype(np.uint8) * 255
    dark = cv2.morphologyEx(dark, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    contours, _ = cv2.findContours(dark, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    best = None
    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        if w < BADGE_MIN_W or w < h * 1.6 or h < 12:
            continue
        if best is None or w * h > best[2] * best[3]:
            best = (x, y, w, h)
    if best is None:
        return None
    x, y, w, h = best
    return gray[y : y + h, x : x + w]


def _badge_digits(badge):
    """Chữ số nằm sau chữ Lvl. Mốc cắt theo chiều cao nét, không theo bề rộng viên."""
    white = (badge > 170).astype(np.uint8) * 255
    white[:2, :] = 0
    white[-2:, :] = 0
    white[:, :2] = 0
    white[:, -2:] = 0
    count, _, stats, _ = cv2.connectedComponentsWithStats(white, 8)
    glyphs = []
    for index in range(1, count):
        x, y, w, h, area = stats[index]
        if h < 8 or area < 8:
            continue
        glyphs.append((int(x), int(y), int(w), int(h)))
    if not glyphs:
        return []
    tallest = max(item[3] for item in glyphs)
    glyphs = [item for item in glyphs if item[3] >= tallest * 0.55]
    cut = tallest * LVL_GLYPH_CUT
    digits = []
    for x, y, w, h in sorted(glyphs):
        if x + w / 2 <= cut:
            continue
        digits.append(white[y : y + h, x : x + w])
    return digits


@lru_cache(maxsize=1)
def _digit_bank() -> dict[str, np.ndarray]:
    windir = Path(os.environ.get("WINDIR", r"C:\Windows"))
    font_path = next((windir / "Fonts" / name for name in FONT_FILES if (windir / "Fonts" / name).exists()), None)
    if font_path is None:
        return {}
    font = ImageFont.truetype(str(font_path), FONT_PX)
    bank = {}
    for digit in "0123456789":
        image = Image.new("L", (FONT_CANVAS, FONT_CANVAS), 0)
        ImageDraw.Draw(image).text((4, 4), digit, fill=255, font=font)
        arr = np.array(image)
        ys, xs = np.where(arr > 40)
        if len(xs) == 0:
            continue
        crop = arr[ys.min() : ys.max() + 1, xs.min() : xs.max() + 1]
        bank[digit] = cv2.resize(crop, DIGIT_BOX, interpolation=cv2.INTER_AREA)
    return bank


def _read_digit(glyph) -> str | None:
    bank = _digit_bank()
    if not bank:
        return None
    sample = cv2.resize(glyph, DIGIT_BOX, interpolation=cv2.INTER_AREA).astype(np.float32)
    scores = {digit: _corr(sample, template.astype(np.float32)) for digit, template in bank.items()}
    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    best, score = ranked[0]
    second = ranked[1][1] if len(ranked) > 1 else -1.0
    if score < DIGIT_SCORE or score - second < DIGIT_MARGIN:
        return None
    return best


def _corr(sample, template) -> float:
    left = sample - sample.mean()
    right = template - template.mean()
    scale = float(np.linalg.norm(left) * np.linalg.norm(right))
    if scale == 0:
        return -1.0
    return float((left * right).sum() / scale)


def draw_hits(screen, hits: list[Hit]):
    canvas = screen.copy()
    for hit in hits:
        if hit.w <= 0:
            continue
        x0 = int(hit.x - hit.w / 2)
        y0 = int(hit.y - hit.h / 2)
        cv2.rectangle(canvas, (x0, y0), (x0 + hit.w, y0 + hit.h), (40, 40, 220), 2)
        cv2.putText(
            canvas,
            f"{hit.name} {hit.score:.2f}",
            (x0, max(16, y0 - 6)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (40, 40, 220),
            1,
            cv2.LINE_AA,
        )
    return canvas
