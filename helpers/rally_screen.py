"""Nhận màn rally bằng màu và icon, không đọc chữ.

Dùng chung cho mọi tool. Ảnh mẫu nút chat, back, join, mũi tên nằm trong templates/ ở thư mục gốc repo.
Mẫu kính lúp, nút X và nút Goldrush dùng chung với tool nhận quà.

Join tiếng Anh và Tham gia tiếng Việt là cùng một thanh xanh. Pending, Đang chờ và
Expired là thanh xám. Sự kiện không có mặt thường xuyên nên không chờ đủ ảnh cho
mọi ngôn ngữ: nút xin vào nhận bằng màu, nút thoát nhận bằng icon không chữ.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

_REPO = Path(__file__).resolve().parent.parent
_GIFT = _REPO / "checking-mvp"
if str(_GIFT) not in sys.path:
    sys.path.insert(0, str(_GIFT))

from gift_tool.vision import Finder, Hit, imread

ICON_DIR = _REPO / "templates"
# Mẫu cắt từ ảnh cửa sổ rộng 560, cùng kiểu ảnh resource của tool nhận quà.
ICON_SCREEN_W = 560
CHAT_THRESHOLD = 0.78
BACK_THRESHOLD = 0.78
# Nút Join cắt từ chat rộng 550. Thanh xám Expired trên cùng màn chỉ khớp khoảng 0.56.
JOIN_THRESHOLD = 0.72
JOIN_SCREEN_W = 550
# Nút mũi tên tím cắt từ chat rộng 556. Màn đang ở đáy chỉ khớp khoảng 0.46.
DOWN_THRESHOLD = 0.78
DOWN_SCREEN_W = 556
# Nền khung chat gần như trắng. Bản đồ, danh sách rally và màn một người đều tối hơn.
CHAT_LIGHT = 0.50
# Kính lúp Goldrush nằm bên trái. Kính lúp ô UID nằm bên phải.
MAP_SEARCH_SCORE = 0.72
MAP_SEARCH_X = 0.40
# Nút mode khi không được chọn khớp thấp hơn lúc đang đứng ở sân. Bản đồ Goldrush chỉ khoảng 0.32.
HOME_SCORE = 0.45

# Thanh Join đo được khoảng hue 44–49. Vòng tròn gửi tin khoảng hue 59, loại bằng hình.
JOIN_HUE = (38, 56)
JOIN_SAT = 140
JOIN_VAL = 165
JOIN_ASPECT = 2.5
# Nút Confirm của hộp hoàn thành rally. Cùng màu Join, hẹp hơn nút Join cả màn và nằm giữa hộp tím.
CONFIRM_W = (0.28, 0.62)
CONFIRM_X = (0.40, 0.60)
CONFIRM_Y = (0.70, 0.92)
CONFIRM_PURPLE = 0.55
# Hộp thoại kem, ví dụ Rally Incomplete. Nút Confirm cao hơn hộp thưởng tím.
DIALOG_Y = (0.42, 0.78)
DIALOG_CREAM = 0.75
# Confirm lúc hộp thưởng đang mờ. Màu loãng hơn thanh Join nên ngưỡng thấp hơn.
FAINT_Y = (0.74, 0.93)
FAINT_W = (0.28, 0.62)


@dataclass(frozen=True)
class Reading:
    scene: str
    joins: tuple[Hit, ...]
    greys: tuple[Hit, ...]
    chat: Hit | None
    back: Hit | None
    close: Hit | None
    goldrush: Hit | None
    width: int
    height: int


def load_icons(finder: Finder) -> None:
    finder.add_template(
        "chat",
        imread(ICON_DIR / "chat.png"),
        {"threshold": CHAT_THRESHOLD, "screen_w": ICON_SCREEN_W, "color": True},
    )
    finder.add_template(
        "back",
        imread(ICON_DIR / "back.png"),
        {"threshold": BACK_THRESHOLD, "screen_w": ICON_SCREEN_W, "color": True},
    )
    finder.add_template(
        "join",
        imread(ICON_DIR / "join.png"),
        {"threshold": JOIN_THRESHOLD, "screen_w": JOIN_SCREEN_W, "color": True},
    )
    finder.add_template(
        "down",
        imread(ICON_DIR / "down.png"),
        {"threshold": DOWN_THRESHOLD, "screen_w": DOWN_SCREEN_W, "color": True},
    )


def read_screen(finder: Finder, screen) -> Reading:
    height, width = screen.shape[:2]
    joins = tuple(_join_bars(screen))
    greys = tuple(_grey_bars(screen))
    chat = finder.find(screen, "chat")
    back = finder.find(screen, "back")
    close = finder.find(screen, "close")
    goldrush = finder.find(screen, "goldrush")
    scene = _scene(screen, finder, joins, greys, chat, back, close, goldrush)
    if scene == "map" and chat is None:
        chat = Hit("chat", int(0.92 * width), int(0.77 * height), 0.0, 0, 0)
    return Reading(scene, joins, greys, chat, back, close, goldrush, width, height)


def chat_join_buttons(finder: Finder, screen) -> list[Hit]:
    """Mọi nút Join xanh trong chat, theo đúng hình nút. Bấm tâm mẫu, không bấm vùng xanh bị loãng."""
    view = screen.copy()
    height, width = view.shape[:2]
    hits: list[Hit] = []
    for _ in range(5):
        hit = finder.find(view, "join")
        if hit is None:
            break
        if hit.x > width * 0.80 and hit.y > height * 0.80:
            break
        hits.append(hit)
        x0 = max(0, int(hit.x - hit.w * 0.5))
        y0 = max(0, int(hit.y - hit.h))
        x1 = min(width, int(hit.x + hit.w * 0.5))
        y1 = min(height, int(hit.y + hit.h))
        view[y0:y1, x0:x1] = (244, 240, 236)
    hits.sort(key=lambda item: item.y)
    return hits


def jump_down(finder: Finder, screen) -> Hit | None:
    """Nút mũi tên tím bên phải. Chỉ hiện khi đang xem tin cũ, bấm để về tin mới nhất."""
    hit = finder.find(screen, "down")
    if hit is None:
        return None
    height, width = screen.shape[:2]
    if hit.x < width * 0.75:
        return None
    if not (0.62 * height <= hit.y <= 0.86 * height):
        return None
    return hit


def card_joins(reading: Reading) -> list[Hit]:
    """Nút Join trên thẻ chat. Hẹp hơn nút Join cả màn, rộng hơn nút trong danh sách."""
    low = 0.35 * reading.width
    high = 0.70 * reading.width
    return [hit for hit in reading.joins if low <= hit.w <= high]


def list_joins(reading: Reading) -> list[Hit]:
    """Nút xanh trong danh sách nhiều rally. Bỏ nút gửi tin và nút Join cả màn."""
    high = 0.50 * reading.width
    low = 0.18 * reading.width
    return [hit for hit in reading.joins if low <= hit.w <= high]


def dialog_button(screen, joins=None) -> Hit | None:
    """Nút Confirm trên hộp thoại nền kem. Không phải hộp thưởng tím, không phải Join trong chat."""
    if joins is None:
        joins = _join_bars(screen)
    height, width = screen.shape[:2]
    found = [
        hit
        for hit in joins
        if CONFIRM_W[0] * width <= hit.w <= CONFIRM_W[1] * width
        and CONFIRM_X[0] * width <= hit.x <= CONFIRM_X[1] * width
        and DIALOG_Y[0] * height <= hit.y <= DIALOG_Y[1] * height
        and _cream_card(screen, hit)
    ]
    if not found:
        return None
    return max(found, key=lambda hit: hit.y)


def faint_confirm(screen) -> Hit | None:
    """Nút Confirm còn nhìn thấy khi hộp thưởng đang mờ. Không phải nút Join sắc trên chat."""
    height, width = screen.shape[:2]
    hsv = cv2.cvtColor(screen, cv2.COLOR_BGR2HSV)
    y0, y1 = int(height * FAINT_Y[0]), int(height * FAINT_Y[1])
    x0, x1 = int(width * 0.18), int(width * 0.82)
    roi = hsv[y0:y1, x0:x1]
    mask = cv2.inRange(roi, (35, 45, 35), (85, 255, 255))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((11, 25), np.uint8))
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    best: Hit | None = None
    for contour in contours:
        x, y, bw, bh = cv2.boundingRect(contour)
        if bh < 16 or not (FAINT_W[0] * width <= bw <= FAINT_W[1] * width):
            continue
        if bw / bh < 2.2:
            continue
        cx = x0 + x + bw / 2
        cy = y0 + y + bh / 2
        if not (CONFIRM_X[0] * width <= cx <= CONFIRM_X[1] * width):
            continue
        area = cv2.contourArea(contour)
        if area < 0.35 * bw * bh:
            continue
        hit = Hit("confirm", int(cx), int(cy), 1.0, bw, bh)
        if best is None or hit.w * hit.h > best.w * best.h:
            best = hit
    return best


def reward_button(reading: Reading) -> Hit | None:
    """Nút Confirm giữa hộp. Chưa xét nền tím; phần đó nằm trong phân loại màn."""
    found = [
        hit
        for hit in reading.joins
        if CONFIRM_W[0] * reading.width <= hit.w <= CONFIRM_W[1] * reading.width
        and CONFIRM_X[0] * reading.width <= hit.x <= CONFIRM_X[1] * reading.width
        and CONFIRM_Y[0] * reading.height <= hit.y <= CONFIRM_Y[1] * reading.height
    ]
    if not found:
        return None
    return max(found, key=lambda hit: hit.y)


def bottom_join(reading: Reading) -> Hit | None:
    """Nút Join rộng dưới cùng màn một người."""
    found = [
        hit
        for hit in reading.joins
        if hit.w >= 0.60 * reading.width and hit.y >= 0.80 * reading.height
    ]
    if not found:
        return None
    return min(found, key=lambda hit: hit.y)


def home_goldrush(finder: Finder, screen) -> Hit | None:
    """Nút Goldrush trên thanh mode. Có thì bấm để vào lại, trừ khi đang ở trong bản đồ."""
    hit = finder.locate(screen, "goldrush")
    if hit is None or hit.w == 0:
        return None
    height = screen.shape[0]
    close = finder.find(screen, "close")
    if close is not None and close.y > height * 0.85:
        return None
    threshold = finder.templates["goldrush"][1]["threshold"]
    if hit.score >= threshold:
        return hit
    if hit.score >= HOME_SCORE and hit.y > height * 0.80:
        return hit
    return None


def topmost(hits: list[Hit]) -> Hit:
    return min(hits, key=lambda hit: hit.y)


def panel_light(screen) -> float:
    height, width = screen.shape[:2]
    roi = screen[int(height * 0.22) : int(height * 0.72), int(width * 0.22) : int(width * 0.88)]
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    mask = (hsv[:, :, 1] < 45) & (hsv[:, :, 2] > 190)
    return float(mask.mean())


def send_button(screen) -> Hit | None:
    """Vòng tròn xanh góc phải dưới. Không được bấm: đó là nút gửi, tool không tạo rally."""
    height, width = screen.shape[:2]
    hsv = cv2.cvtColor(screen, cv2.COLOR_BGR2HSV)
    # Máy bay giấy trắng làm mặt nút bị thủng. Đóng mask thì vòng xanh thành một hình tròn.
    mask = cv2.inRange(hsv, (40, 100, 120), (80, 255, 255))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8))
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    best: Hit | None = None
    for contour in contours:
        x, y, bw, bh = cv2.boundingRect(contour)
        if bh < 8:
            continue
        aspect = bw / bh
        cx = x + bw / 2
        cy = y + bh / 2
        if not (0.75 <= aspect <= 1.35):
            continue
        if cx < width * 0.75 or cy < height * 0.75:
            continue
        if not (0.06 * width <= bw <= 0.20 * width):
            continue
        area = cv2.contourArea(contour)
        if area < 0.55 * bw * bh:
            continue
        hit = Hit("send", int(cx), int(cy), 1.0, bw, bh)
        if best is None or hit.w * hit.h > best.w * best.h:
            best = hit
    return best


def _scene(screen, finder, joins, greys, chat, back, close, goldrush) -> str:
    height, width = screen.shape[:2]
    light = panel_light(screen)
    cards = [hit for hit in (*joins, *greys) if 0.35 * width <= hit.w <= 0.70 * width]
    # Hộp thưởng phủ lên màn đang đứng. Phải đóng trước khi xét chat, bản đồ hay nút Join.
    confirm = reward_button(
        Reading("unknown", joins, greys, chat, back, close, goldrush, width, height)
    )
    if confirm is not None and _purple_card(screen, confirm):
        return "reward"
    # Hộp thưởng lúc vừa bấm Confirm còn mờ. Thanh xanh loãng, không đủ ngưỡng nút Join.
    faint = faint_confirm(screen)
    if faint is not None and _purple_card(screen, faint, vmin=30):
        return "reward"
    # Hộp thoại kem phủ lên màn đang đứng. Đóng trước khi xét chat, bản đồ hay nút Join.
    if dialog_button(screen, joins) is not None:
        return "dialog"
    # Back là icon, không phụ thuộc chữ trên nút Join hay Pending.
    if back is not None:
        return "single"
    if light >= CHAT_LIGHT and (send_button(screen) is not None or cards):
        return "chat"
    # Nút Goldrush nằm đáy sân. Icon chat ở sân cũng là bong bóng trắng, dễ khớp nhầm.
    # Trong bản đồ chỗ đó là nút X, mẫu Goldrush không khớp.
    if goldrush is not None and goldrush.y > height * 0.75 and not _bottom_close(close, height):
        return "camp"
    if _bottom_close(close, height) and (chat is not None or _goldrush_map(screen, finder, close)):
        return "map"
    # Danh sách nhiều người phủ lên bản đồ và có nút X. Không có icon chat.
    if close is not None and chat is None and light < 0.20:
        return "multi"
    return "unknown"


def _cream_card(screen, button: Hit) -> bool:
    """Dải ngay trên nút là nền kem của hộp thoại. Chat trắng loãng hơn, không đạt ngưỡng."""
    width = screen.shape[1]
    y1 = int(button.y - button.h * 0.55)
    y0 = int(button.y - button.h * 2.2)
    x0, x1 = int(width * 0.22), int(width * 0.78)
    if y0 < 0 or y1 - y0 < 24 or x1 <= x0:
        return False
    hsv = cv2.cvtColor(screen[y0:y1, x0:x1], cv2.COLOR_BGR2HSV)
    cream = (hsv[:, :, 1] < 50) & (hsv[:, :, 2] > 185)
    return float(cream.mean()) >= DIALOG_CREAM


def _purple_card(screen, button: Hit, vmin: int = 50) -> bool:
    """Phần hộp phía trên nút Confirm là nền tím. Chat trắng và danh sách không có nút giữa."""
    height, width = screen.shape[:2]
    y1 = int(button.y - button.h / 2)
    y0 = int(height * 0.18)
    x0, x1 = int(width * 0.18), int(width * 0.82)
    if y1 - y0 < 40:
        return False
    hsv = cv2.cvtColor(screen[y0:y1, x0:x1], cv2.COLOR_BGR2HSV)
    purple = (hsv[:, :, 0] >= 120) & (hsv[:, :, 0] <= 165) & (hsv[:, :, 1] >= 40) & (hsv[:, :, 2] >= vmin)
    return float(purple.mean()) >= CONFIRM_PURPLE


def _bottom_close(close: Hit | None, height: int) -> bool:
    return close is not None and close.y > height * 0.85


def _goldrush_map(screen, finder: Finder, close: Hit | None) -> bool:
    if not _bottom_close(close, screen.shape[0]):
        return False
    search = finder.locate(screen, "search")
    return bool(search.w) and search.score >= MAP_SEARCH_SCORE and search.x < MAP_SEARCH_X * screen.shape[1]


def _join_bars(screen) -> list[Hit]:
    height, width = screen.shape[:2]
    hsv = cv2.cvtColor(screen, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, (JOIN_HUE[0], JOIN_SAT, JOIN_VAL), (JOIN_HUE[1], 255, 255))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((11, 5), np.uint8))
    return _bars(mask, width, height, "join", corner_guard=True)


def _grey_bars(screen) -> list[Hit]:
    height, width = screen.shape[:2]
    hsv = cv2.cvtColor(screen, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, (0, 0, 90), (180, 45, 175))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((9, 5), np.uint8))
    return _bars(mask, width, height, "grey", corner_guard=False)


def _bars(mask, width: int, height: int, name: str, corner_guard: bool) -> list[Hit]:
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    hits: list[Hit] = []
    for contour in contours:
        x, y, bw, bh = cv2.boundingRect(contour)
        if bh < 16 or bw < width * 0.18:
            continue
        aspect = bw / bh
        if aspect < JOIN_ASPECT:
            continue
        if bw > width * 0.95:
            continue
        cx = x + bw / 2
        cy = y + bh / 2
        if cy < height * 0.18 or cy > height * 0.97:
            continue
        # Vòng gửi tin cũng xanh và nằm đúng góc này. Tool không được chạm vào.
        if corner_guard and cx > width * 0.80 and cy > height * 0.80:
            continue
        area = cv2.contourArea(contour)
        if area < 0.45 * bw * bh:
            continue
        hits.append(Hit(name, int(cx), int(cy), 1.0, bw, bh))
    return _suppress(hits)


def _suppress(hits: list[Hit]) -> list[Hit]:
    ordered = sorted(hits, key=lambda hit: hit.w * hit.h, reverse=True)
    kept: list[Hit] = []
    for hit in ordered:
        if any(_iou(hit, other) > 0.4 for other in kept):
            continue
        kept.append(hit)
    kept.sort(key=lambda hit: hit.y)
    return kept


def _iou(left: Hit, right: Hit) -> float:
    ax0, ay0 = left.x - left.w / 2, left.y - left.h / 2
    ax1, ay1 = ax0 + left.w, ay0 + left.h
    bx0, by0 = right.x - right.w / 2, right.y - right.h / 2
    bx1, by1 = bx0 + right.w, by0 + right.h
    ix0, iy0 = max(ax0, bx0), max(ay0, by0)
    ix1, iy1 = min(ax1, bx1), min(ay1, by1)
    if ix1 <= ix0 or iy1 <= iy0:
        return 0.0
    inter = (ix1 - ix0) * (iy1 - iy0)
    union = left.w * left.h + right.w * right.h - inter
    if union <= 0:
        return 0.0
    return inter / union
