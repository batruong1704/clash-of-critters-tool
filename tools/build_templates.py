"""Cắt ảnh mẫu từ screenshot người dùng chụp. Chạy lại nếu đổi ảnh mẫu."""

from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "templates"

# (tên file screenshot bắt đầu bằng, y0, y1, x0, x1, tên mẫu)
CROPS = [
    ("2.", 488, 536, 492, 540, "search"),
    ("3.", 614, 682, 408, 522, "add"),
    # visit.png cắt từ ảnh emulator 720x1280 (logs/cap.png), không cắt lại từ ảnh 4.
    ("5.", 473, 535, 258, 313, "gift"),
    ("5.", 932, 988, 256, 316, "close"),
    ("6.", 848, 908, 74, 238, "select"),
    ("7.", 850, 924, 165, 405, "ok"),
]


def imread(path: Path):
    data = np.fromfile(str(path), dtype=np.uint8)
    return cv2.imdecode(data, cv2.IMREAD_COLOR)


def main():
    OUT.mkdir(exist_ok=True)
    shots = list(ROOT.glob("*.png"))
    for prefix, y0, y1, x0, x1, name in CROPS:
        src = next(p for p in shots if p.name.startswith(prefix))
        img = imread(src)
        crop = img[y0:y1, x0:x1]
        if crop.size == 0:
            raise SystemExit(f"Crop rỗng: {name}")
        cv2.imencode(".png", crop)[1].tofile(str(OUT / f"{name}.png"))
        print(f"{name}.png {crop.shape[1]}x{crop.shape[0]} từ {src.name} ({img.shape[1]}x{img.shape[0]})")


if __name__ == "__main__":
    main()
