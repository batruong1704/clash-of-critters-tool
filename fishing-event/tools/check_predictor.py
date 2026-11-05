"""Thử bộ đoán mồi: dùng mẫu thưa (như lúc chụp ADB) của video, so với vị trí thật ở khung sau.

Chạy từ thư mục fishing-event: py -3 tools/check_predictor.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cv2  # noqa: E402

from fishing_tool.paths import VIDEO  # noqa: E402
from fishing_tool.predictor import Tracker  # noqa: E402
from fishing_tool.vision import normalize, read_slider  # noqa: E402

FPS = 30.0


def main() -> None:
    video = cv2.VideoCapture(str(VIDEO))
    truth = {}
    for index in range(618, 668):
        video.set(cv2.CAP_PROP_POS_FRAMES, index)
        ok, img = video.read()
        slider = read_slider(normalize(img))
        if ok and slider.pointer is not None:
            truth[index] = slider.pointer
    frames = sorted(truth)
    print("khung có mồi:", frames[0], "-", frames[-1])
    for gap in (14, 16, 18):
        tracker = Tracker()
        picks = [frames[0] + gap * i for i in range(3)]
        for index in picks:
            tracker.add(index / FPS, truth[index])
        fit = tracker.fit()
        print(f"cách {gap} khung: tốc độ {fit[0]:.0f}px/s, sai số mẫu {fit[2]:.0f}px, tin cậy {tracker.confident()}")
        errors = []
        for index in frames:
            if index > picks[-1] + 2:
                errors.append(abs(tracker.position(index / FPS) - truth[index]))
        print(f"  lệch trung bình {sum(errors) / len(errors):.0f}px, tối đa {max(errors):.0f}px trên {len(errors)} khung sau")


if __name__ == "__main__":
    main()
