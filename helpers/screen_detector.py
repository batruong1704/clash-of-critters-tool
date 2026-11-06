"""Nhận biết đang đứng ở giao diện nào của game từ một ảnh chụp màn hình.

Bốn giao diện được nhận:

- LOBBY: sảnh chính (sân nhà). Thanh tab dưới đáy có nút "Pinball" ở ngoài cùng bên phải.
- PINBALL: màn roll pinball. Cũng là thanh tab đó, nhưng nút ngoài cùng bên phải đổi thành "Camp".
- GOLDRUSH: bản đồ Goldrush. Hàng nút dưới đáy có "Reports" và "League", phía dưới là nút X.
- FISHING: sự kiện câu cá. Tiêu đề "Fishing Contest" kèm nút "?" ở đỉnh màn.

Màn nào cũng có hai loại dấu hiệu: chữ trên nút (đúng với game tiếng Anh) và icon (không phụ thuộc ngôn
ngữ). Chỉ cần một dấu hiệu đạt ngưỡng là đủ. Popup phủ lên màn (kết quả câu cá, hộp thưởng, chat...)
che mất các dấu hiệu nên trả UNKNOWN: hàm chỉ trả lời "đang ở màn nào", không đoán màn nằm dưới popup.

Ảnh vào là BGR (OpenCV) hoặc đường dẫn file. Ảnh ADB của LDPlayer đã là 720x1280. Ảnh có kích cỡ
khác cùng tỉ lệ 9:16 vẫn dùng được vì ảnh được co về 720x1280 trước khi so mẫu.

Ảnh mẫu trong templates/ ở thư mục gốc repo đều ở tỉ lệ 720x1280:

| Mẫu                       | Lấy từ                                                        |
|---------------------------|---------------------------------------------------------------|
| tab_pinball.png           | Chữ "Pinball" của tab ngoài cùng bên phải ở sảnh               |
| tab_pinball_icon.png      | Icon máy pinball đỏ của tab đó (bỏ chấm đỏ thông báo)         |
| tab_camp.png              | Chữ "Camp" của tab ngoài cùng bên phải ở màn pinball           |
| tab_camp_icon.png         | Icon lều của tab đó (bỏ bong bóng chat nổi phía trên)         |
| goldrush_reports.png      | Chữ "Reports" dưới đáy bản đồ Goldrush                         |
| goldrush_reports_icon.png | Icon thanh biểu đồ xanh của nút Reports                       |
| goldrush_league.png       | Chữ "League" dưới đáy bản đồ Goldrush                          |
| goldrush_league_icon.png  | Icon huy hiệu vàng của nút League                             |
| fishing_title.png         | Chữ "Fishing Contest" ở đỉnh màn câu cá                        |
| fishing_help.png          | Nút tròn "?" cạnh tiêu đề màn câu cá (vị trí ngang đổi theo chữ) |
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np

TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates"
REF_W, REF_H = 720, 1280


class Screen(str, Enum):
    LOBBY = "lobby"
    PINBALL = "pinball"
    GOLDRUSH = "goldrush"
    FISHING = "fishing"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class Spec:
    """Một dấu hiệu: màn nó chứng tỏ, vùng tìm (x0, y0, x1, y1 trên ảnh 720x1280) và điểm khớp tối thiểu."""

    screen: Screen
    region: tuple[int, int, int, int]
    threshold: float


_TAB = (540, 1130, 720, 1280)
_GOLDRUSH_LEFT = (100, 1000, 320, 1180)
_GOLDRUSH_RIGHT = (540, 1000, 720, 1180)
_FISHING_TOP = (120, 0, 720, 110)

SPECS: dict[str, Spec] = {
    "tab_pinball": Spec(Screen.LOBBY, _TAB, 0.85),
    "tab_pinball_icon": Spec(Screen.LOBBY, _TAB, 0.80),
    "tab_camp": Spec(Screen.PINBALL, _TAB, 0.85),
    "tab_camp_icon": Spec(Screen.PINBALL, _TAB, 0.80),
    "goldrush_reports": Spec(Screen.GOLDRUSH, _GOLDRUSH_LEFT, 0.80),
    "goldrush_reports_icon": Spec(Screen.GOLDRUSH, _GOLDRUSH_LEFT, 0.80),
    "goldrush_league": Spec(Screen.GOLDRUSH, _GOLDRUSH_RIGHT, 0.80),
    "goldrush_league_icon": Spec(Screen.GOLDRUSH, _GOLDRUSH_RIGHT, 0.80),
    "fishing_title": Spec(Screen.FISHING, _FISHING_TOP, 0.80),
    "fishing_help": Spec(Screen.FISHING, _FISHING_TOP, 0.80),
}


@dataclass(frozen=True)
class Detection:
    screen: Screen
    # Điểm khớp từng ảnh mẫu (0 đến 1), để xem vì sao ra kết luận đó.
    scores: dict[str, float] = field(default_factory=dict)


def detect_screen(image) -> Screen:
    """Đang ở giao diện nào. Không nhận ra thì trả Screen.UNKNOWN."""
    return detect_screen_info(image).screen


def detect_screen_info(image) -> Detection:
    """Như detect_screen, kèm điểm khớp của từng dấu hiệu."""
    img = _prepare(image)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    templates = _templates()
    scores = {name: _match(gray, templates[name], spec.region) for name, spec in SPECS.items()}

    # Mỗi màn lấy dấu hiệu mạnh nhất, vượt ngưỡng bao nhiêu thì tính bấy nhiêu. Màn vượt nhiều nhất thắng.
    margin: dict[Screen, float] = {}
    for name, spec in SPECS.items():
        over = scores[name] - spec.threshold
        if over >= 0 and over > margin.get(spec.screen, -1.0):
            margin[spec.screen] = over
    if not margin:
        return Detection(Screen.UNKNOWN, scores)
    return Detection(max(margin, key=margin.get), scores)


def imread(path) -> np.ndarray:
    """Đọc ảnh theo đường dẫn có dấu tiếng Việt (cv2.imread trên Windows không đọc được)."""
    data = np.fromfile(str(path), dtype=np.uint8)
    img = cv2.imdecode(data, cv2.IMREAD_COLOR)
    if img is None:
        raise FileNotFoundError(path)
    return img


def _prepare(image) -> np.ndarray:
    if isinstance(image, (str, Path)):
        image = imread(image)
    if not isinstance(image, np.ndarray) or image.ndim < 2:
        raise ValueError("Cần ảnh BGR của OpenCV hoặc đường dẫn file ảnh.")
    if image.ndim == 2:
        image = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
    elif image.shape[2] == 4:
        image = cv2.cvtColor(image, cv2.COLOR_BGRA2BGR)
    height, width = image.shape[:2]
    if (width, height) == (REF_W, REF_H):
        return image
    interpolation = cv2.INTER_AREA if width >= REF_W else cv2.INTER_CUBIC
    return cv2.resize(image, (REF_W, REF_H), interpolation=interpolation)


@lru_cache(maxsize=1)
def _templates() -> dict[str, np.ndarray]:
    return {name: cv2.cvtColor(imread(TEMPLATE_DIR / f"{name}.png"), cv2.COLOR_BGR2GRAY) for name in SPECS}


def _match(gray, template, region: tuple[int, int, int, int]) -> float:
    x0, y0, x1, y1 = region
    view = gray[y0:y1, x0:x1]
    if view.shape[0] < template.shape[0] or view.shape[1] < template.shape[1]:
        return 0.0
    result = cv2.matchTemplate(view, template, cv2.TM_CCOEFF_NORMED)
    return float(cv2.minMaxLoc(result)[1])


# Nút mode Goldrush cắt từ ảnh rộng 560. Khi không được chọn, điểm khớp chỉ khoảng 0.48.
_MODE_ICON = Path(__file__).resolve().parent.parent / "templates" / "goldrush.png"
_MODE_SCREEN_W = 560
_MODE_SCORE = 0.45


def goldrush_entry(image) -> tuple[int, int] | None:
    """Điểm bấm để vào Goldrush khi đang ở sân hoặc pinball.

    Đã ở bản đồ Goldrush, đang câu cá, hoặc không nhận ra màn thì trả None.
    Icon nút đổi theo bản game. Khớp được thì bấm đúng icon. Không khớp thì bấm
    nút giữa thanh mode, chỗ Goldrush nằm giữa Battle và Pinball.
    """
    img = _bgr(image)
    if detect_screen(img) not in (Screen.LOBBY, Screen.PINBALL):
        return None
    found = _goldrush_tab(img)
    if found is not None:
        return found
    height, width = img.shape[:2]
    return int(round(width * 0.50)), int(round(height * 0.93))


def _bgr(image) -> np.ndarray:
    if isinstance(image, (str, Path)):
        image = imread(image)
    if not isinstance(image, np.ndarray) or image.ndim < 2:
        raise ValueError("Cần ảnh BGR của OpenCV hoặc đường dẫn file ảnh.")
    if image.ndim == 2:
        image = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
    elif image.shape[2] == 4:
        image = cv2.cvtColor(image, cv2.COLOR_BGRA2BGR)
    return image


@lru_cache(maxsize=1)
def _goldrush_icon() -> np.ndarray:
    return imread(_MODE_ICON)


def _goldrush_tab(img) -> tuple[int, int] | None:
    """Tâm icon Goldrush ở nửa dưới, giữa thanh mode. Bỏ nút Pinball sát mép phải."""
    height, width = img.shape[:2]
    templ = _goldrush_icon()
    y0, x0 = int(height * 0.78), int(width * 0.22)
    view = img[y0:, x0 : int(width * 0.78)]
    if view.size == 0:
        return None
    base = width / _MODE_SCREEN_W
    best = 0.0
    point = None
    for scale in (0.86, 0.95, 1.0, 1.05, 1.14):
        tw = int(templ.shape[1] * base * scale)
        th = int(templ.shape[0] * base * scale)
        if tw < 8 or th < 8 or tw >= view.shape[1] or th >= view.shape[0]:
            continue
        shrinking = tw <= templ.shape[1] and th <= templ.shape[0]
        sized = cv2.resize(templ, (tw, th), interpolation=cv2.INTER_AREA if shrinking else cv2.INTER_LINEAR)
        result = cv2.matchTemplate(view, sized, cv2.TM_CCOEFF_NORMED)
        score, _, _, loc = cv2.minMaxLoc(result)
        if score <= best:
            continue
        best = float(score)
        point = (x0 + int(round(loc[0] + tw / 2)), y0 + int(round(loc[1] + th / 2)))
    if point is None or best < _MODE_SCORE:
        return None
    return point
