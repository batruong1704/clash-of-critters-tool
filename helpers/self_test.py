"""Kiểm tra hàm nhận màn hình bằng ảnh mẫu có sẵn trong repo.

    py -3 -m helpers.self_test                chạy bộ kiểm tra có sẵn
    py -3 -m helpers.self_test ảnh1.png ...   chỉ in kết quả nhận cho các ảnh đó
"""

from __future__ import annotations

import sys
from pathlib import Path

import cv2

from helpers.screen_detector import Screen, detect_screen_info, imread

REPO = Path(__file__).resolve().parent.parent
FISHING = REPO / "fishing-event"
MVP = REPO / "checking-mvp"
RALLY = REPO / "auto-join-rally" / "resource"


def _find(folder: Path, prefix: str) -> Path:
    """Tên file ảnh mẫu dài và có dấu tiếng Việt, tìm theo phần đầu cho gọn."""
    matches = sorted(folder.glob(f"{prefix}*"))
    if not matches:
        raise FileNotFoundError(f"{folder}\\{prefix}*")
    return matches[0]


def _cases() -> list[tuple[Path, Screen]]:
    cases = [
        (_find(FISHING / "resource", "1. "), Screen.LOBBY),
        (_find(MVP / "resource", "0. màn hình ở"), Screen.LOBBY),
        (_find(FISHING / "resource", "2. "), Screen.PINBALL),
        (_find(MVP / "resource", "1. "), Screen.PINBALL),
        (_find(MVP / "resource", "0. màn hình chế độ goldrush"), Screen.GOLDRUSH),
        (_find(RALLY, "Step 1."), Screen.GOLDRUSH),
        (_find(RALLY, "Step 5."), Screen.GOLDRUSH),
        # Ảnh thật 720x1280 chụp bằng ADB lúc tool câu cá đang chạy.
        (FISHING / "logs" / "cau-ca-busy-1.png", Screen.FISHING),
        (FISHING / "logs" / "cau-ca-busy-5.png", Screen.FISHING),
        (FISHING / "logs" / "cau-ca-khong-nhan-ra-man.png", Screen.FISHING),
    ]
    for prefix in ("3. ", "4. ", "5. ", "6. ", "9. "):
        cases.append((_find(FISHING / "resource", prefix), Screen.FISHING))
    # Màn khác của game, không được nhận nhầm thành một trong bốn màn.
    for prefix in ("2. ", "3. ", "5. ", "7. "):
        cases.append((_find(MVP / "resource", prefix), Screen.UNKNOWN))
    for prefix in ("Step 2.", "Step 3.", "Step 4.", "Exception. Hoàn thành rally, nhận điểm"):
        cases.append((_find(RALLY, prefix), Screen.UNKNOWN))
    # Popup kết quả câu cá phủ lên màn câu cá che mất mọi dấu hiệu.
    cases.append((FISHING / "logs" / "cau-ca-ketqua-1.png", Screen.UNKNOWN))
    return cases


def _variants(img):
    """Cùng một màn nhưng khác kích cỡ và bị nén JPEG, như khi chụp từ cửa sổ có độ phân giải khác."""
    height, width = img.shape[:2]
    yield "co 75%", cv2.resize(img, (int(width * 0.75), int(height * 0.75)), interpolation=cv2.INTER_AREA)
    yield "phóng 125%", cv2.resize(img, (int(width * 1.25), int(height * 1.25)), interpolation=cv2.INTER_CUBIC)
    ok, data = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 60])
    if ok:
        yield "jpeg 60", cv2.imdecode(data, cv2.IMREAD_COLOR)


def run() -> int:
    failed = 0
    for path, expected in _cases():
        # Thư mục logs/ không được commit, máy mới clone sẽ không có ảnh chụp thật.
        if not path.exists():
            print(f"bỏ qua (không có file) {path.name}")
            continue
        img = imread(path)
        checks = [("gốc", img), *(_variants(img) if expected != Screen.UNKNOWN else [])]
        for label, frame in checks:
            got = detect_screen_info(frame).screen
            ok = got == expected
            failed += not ok
            if not ok or label == "gốc":
                print(f"{'ok  ' if ok else 'SAI '} {expected.value:9s} -> {got.value:9s} [{label}] {path.name[:60]}")
    print("Tất cả đúng." if not failed else f"Sai {failed} ca.")
    return 1 if failed else 0


def show(paths: list[str]) -> int:
    for item in paths:
        info = detect_screen_info(item)
        best = sorted(info.scores.items(), key=lambda pair: pair[1], reverse=True)[:3]
        detail = ", ".join(f"{name} {score:.2f}" for name, score in best)
        print(f"{info.screen.value:9s} {item}  ({detail})")
    return 0


if __name__ == "__main__":
    sys.exit(show(sys.argv[1:]) if len(sys.argv) > 1 else run())
