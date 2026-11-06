"""Nhận loài trên màn kết quả.

Mẫu từng con nằm ở data/loai-ca, chia thư mục do, vang, tim, xanh, tên file là tên tiếng Việt.
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from fishing_tool.paths import DATA
from fishing_tool.vision import REF_H, REF_W, _read_digits, normalize

SPECIES = DATA / "loai-ca"

# Cỡ thô trước, rồi dò sát quanh cỡ ăn điểm nhất. Đỉnh khớp rất hẹp:
# lệch 0,05 là Cá Dẹt từ 0,67 rơi xuống dưới 0,50 và thua một mảng nhỏ của loài khác.
COARSE = (0.9, 1.25, 1.6, 1.95, 2.3)
REFINE = (-0.10, -0.05, 0.05, 0.10)
# So trên ảnh thu nhỏ. Icon và màn kết quả cùng thu, điểm khớp vẫn đủ để phân biệt loài.
MATCH_ZOOM = 0.34
MIN_SCORE = 0.42
MIN_MARGIN = 0.035
# Số kẹo / pinball trên thẻ là số ngắn (x3, x767). Bảng điểm hai bên là hàng triệu,
# đọc cụt thành x9.721 thì bỏ, chỉ giữ tên vật phẩm.
MAX_ITEM_COUNT = 999
# Khung nhỏ hơn mức này chỉ ăn một mảng nền hoặc một mảnh trên mình cá.
MIN_BOX = 32
# Vùng giữa màn, chỗ con cá hoặc vật phẩm hiện.
SEARCH = (0.16, 0.26, 0.84, 0.64)


@dataclass(frozen=True)
class Sprite:
    name: str
    kind: str  # ca, keo, pinball
    rarity: str  # do, xanh, tim, vang, trang
    image: np.ndarray
    mask: np.ndarray


@dataclass(frozen=True)
class Catch:
    name: str
    kind: str
    rarity: str
    count: int | None
    score: float

    @property
    def label(self) -> str:
        if self.kind == "ca" or not self.count:
            return self.name
        return f"x{_thousands(self.count)} {self.name}"

    @property
    def tone(self) -> str:
        return self.rarity or "ok"


def _thousands(value: int) -> str:
    """3.125 viết thành 3,125 như số trên màn game."""
    return f"{value:,}"


def tone_for(label: str) -> str:
    """Màu chữ của một dòng kết quả. Không rõ thì giữ màu thành công."""
    text = label.strip()
    name = text.split(" ", 1)[1] if text.startswith("x") and " " in text else text
    for sprite in _book():
        if sprite.name == name:
            return sprite.rarity or "ok"
    return "ok"


def classify(img) -> Catch | None:
    """Loài khớp nhất trên ảnh kết quả đã về 720x1280. Không đủ chắc thì None."""
    frame = normalize(img)
    y0, y1 = int(SEARCH[1] * REF_H), int(SEARCH[3] * REF_H)
    x0, x1 = int(SEARCH[0] * REF_W), int(SEARCH[2] * REF_W)
    view = frame[y0:y1, x0:x1]
    view = cv2.resize(view, None, fx=MATCH_ZOOM, fy=MATCH_ZOOM, interpolation=cv2.INTER_AREA)
    ranked: list[tuple[float, Sprite, int, int, int, int]] = []
    rough: list[tuple[float, float, Sprite, tuple]] = []
    for sprite in _book():
        hit, scale = _coarse(view, sprite)
        if hit is None or scale is None:
            continue
        rough.append((hit[0], scale, sprite, hit))
    rough.sort(key=lambda item: item[0], reverse=True)
    for score, scale, sprite, hit in rough[:8]:
        best = hit
        if score >= 0.28:
            for delta in REFINE:
                nxt = _match_at(view, sprite, scale + delta)
                if nxt is not None and nxt[0] > best[0]:
                    best = nxt
        ox, oy, tw, th = best[1], best[2], best[3], best[4]
        ranked.append((best[0], sprite, round(ox / MATCH_ZOOM), round(oy / MATCH_ZOOM), round(tw / MATCH_ZOOM), round(th / MATCH_ZOOM)))
    for score, _scale, sprite, hit in rough[8:]:
        ox, oy, tw, th = hit[1], hit[2], hit[3], hit[4]
        ranked.append((score, sprite, round(ox / MATCH_ZOOM), round(oy / MATCH_ZOOM), round(tw / MATCH_ZOOM), round(th / MATCH_ZOOM)))
    if not ranked:
        return None
    ranked.sort(key=lambda item: item[0], reverse=True)
    score, sprite, ox, oy, tw, th = ranked[0]
    rival = next((item[0] for item in ranked[1:] if item[1].name != sprite.name), 0.0)
    if score < MIN_SCORE or score - rival < MIN_MARGIN:
        return None
    count = None
    if sprite.kind != "ca":
        count = _count_below(frame, x0 + ox, y0 + oy, tw, th)
    return Catch(sprite.name, sprite.kind, sprite.rarity, count, score)


def _coarse(view, sprite: Sprite):
    best = None
    chosen = None
    for scale in COARSE:
        hit = _match_at(view, sprite, scale)
        if hit is not None and (best is None or hit[0] > best[0]):
            best = hit
            chosen = scale
    return best, chosen


def _match_at(view, sprite: Sprite, scale: float):
    height, width = view.shape[:2]
    tw = int(round(sprite.image.shape[1] * scale * MATCH_ZOOM))
    th = int(round(sprite.image.shape[0] * scale * MATCH_ZOOM))
    if tw >= width or th >= height or tw < MIN_BOX or th < MIN_BOX:
        return None
    templ = cv2.resize(sprite.image, (tw, th), interpolation=cv2.INTER_AREA)
    mask = cv2.resize(sprite.mask, (tw, th), interpolation=cv2.INTER_NEAREST)
    if int(mask.sum()) < 255 * 40:
        return None
    result = cv2.matchTemplate(view, templ, cv2.TM_CCOEFF_NORMED, mask=mask)
    _, peak, _, loc = cv2.minMaxLoc(np.nan_to_num(result, nan=-1.0))
    if not np.isfinite(peak) or peak > 1.0 or peak < -1.0:
        return None
    return float(peak), int(loc[0]), int(loc[1]), tw, th


def _count_below(img, x: int, y: int, width: int, height: int) -> int | None:
    """Số trắng dưới icon. Khung mẫu thường phủ cả quầng sáng nên số nằm đè mép dưới."""
    cx = x + width / 2
    top = y + height * 0.55
    box = (
        max(0.0, (cx - 110) / REF_W),
        max(0.0, top / REF_H),
        min(1.0, (cx + 110) / REF_W),
        min(1.0, (y + height + 56) / REF_H),
    )
    count = _read_digits(img, box, (0.022, 0.042), "white")
    if count is None or count > MAX_ITEM_COUNT:
        return None
    return count


def _book() -> tuple[Sprite, ...]:
    global _SPRITES
    if _SPRITES is None:
        _SPRITES = tuple(_load_sprites())
    return _SPRITES


_SPRITES: tuple[Sprite, ...] | None = None


def _load_sprites() -> list[Sprite]:
    """Đọc từng con đã cắt trong data/loai-ca."""
    import json

    catalog = json.loads((SPECIES / "loai.json").read_text(encoding="utf-8"))
    found = []
    for row in catalog:
        bgra = cv2.imdecode(np.fromfile(SPECIES / row["file"], dtype=np.uint8), cv2.IMREAD_UNCHANGED)
        if bgra is None or bgra.ndim != 3 or bgra.shape[2] < 4:
            raise RuntimeError(f"Thiếu ảnh loài {row['file']}")
        found.append(Sprite(row["name"], row["kind"], row["rarity"], bgra[:, :, :3], bgra[:, :, 3]))
    return found
