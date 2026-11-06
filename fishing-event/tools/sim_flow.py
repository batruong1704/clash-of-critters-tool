"""Chạy vòng câu trên game giả dựng từ ảnh video thật. Kiểm tra thứ tự bước và bộ chọn giờ bấm mà không đụng game.

Mồi trên thanh trượt được vẽ lại theo sóng tam giác. Trúng khi mồi nằm trong vùng vàng lúc cú bấm tới game.

Chạy từ thư mục fishing-event: py -3 tools/sim_flow.py [tốc_độ_px_mỗi_giây] [số_thanh_trượt]
"""

import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cv2  # noqa: E402
import numpy as np  # noqa: E402

from fishing_tool.flow import Runner  # noqa: E402
from fishing_tool.paths import VIDEO  # noqa: E402
from fishing_tool.vision import POINTER_HI, POINTER_LO, normalize  # noqa: E402

SHOT_TIME = 0.45
SHOT_AT = 0.30
TAP_DELAY = 0.25


class FakeGame:
    def __init__(self, speed: float, sliders: int):
        video = cv2.VideoCapture(str(VIDEO))

        def frame(index):
            video.set(cv2.CAP_PROP_POS_FRAMES, index)
            return normalize(video.read()[1])

        self.idle, self.wait, self.reel = frame(290), frame(480), frame(612)
        self.cool, self.result = frame(672), frame(722)
        base = frame(640)
        self.sprite = base[812:902, 505:550].copy()
        clean = base.copy()
        clean[812:902, 500:556] = base[812:902, 440:496]
        self.clean = clean
        self.speed = speed
        self.sliders = sliders
        self.zones = [(290, 437), (230, 330), (400, 480), (300, 380)]
        self.state = "idle"
        self.since = time.time()
        self.shown = 0
        self.slider_at = 0.0
        self.taps = 0
        self.hits = 0
        self.log = []

    def pointer(self, when):
        span = POINTER_HI - POINTER_LO
        phase = (self.speed * (when - self.slider_at) + span / 2) % (2 * span)
        return POINTER_LO + (phase if phase <= span else 2 * span - phase)

    def advance(self, now):
        age = now - self.since
        if self.state == "wait" and age > 2.0:
            self.set("reel", now)
        elif self.state == "cool" and age > 0.6:
            if self.shown >= self.sliders:
                self.set("result", now)
            else:
                self.set("slider", now)
                self.slider_at = now
        elif self.state == "slider" and now - self.slider_at > 30:
            self.set("idle", now)

    def set(self, state, now):
        self.state, self.since = state, now
        if state == "slider":
            self.slider_at = now

    def image(self, now):
        self.advance(now)
        if self.state == "idle":
            return self.idle
        if self.state == "wait":
            return self.wait
        if self.state == "reel":
            return self.reel
        if self.state == "cool":
            return self.cool
        if self.state == "result":
            return self.result
        zone = self.zones[(self.shown) % len(self.zones)]
        img = self.clean.copy()
        # Vẽ lại vùng vàng theo zone hiện tại: tô thanh bằng màu vàng/xanh của video.
        strip = img[851:877, 175:556].copy()
        track = self.clean[851:877, 470:490].mean(axis=(0, 1))
        yellow = self.clean[851:877, 330:340].mean(axis=(0, 1))
        strip[:, :] = track
        strip[:, zone[0] - 175 : zone[1] - 175] = yellow
        img[851:877, 175:556] = strip
        x = int(self.pointer(now))
        h, w = self.sprite.shape[:2]
        img[812 : 812 + h, x - w // 2 : x - w // 2 + w] = self.sprite
        return img

    def tap_at(self, x, y, when):
        near_button = abs(x - 360) < 130 and abs(y - 1050) < 130
        if self.state == "idle" and near_button:
            self.set("wait", when)
            self.shown = 0
        elif self.state == "reel" and near_button:
            self.set("slider", when)
        elif self.state == "slider" and near_button:
            self.taps += 1
            zone = self.zones[self.shown % len(self.zones)]
            at = self.pointer(when)
            ok = zone[0] <= at <= zone[1]
            self.log.append((round(at), zone, ok))
            if ok:
                self.hits += 1
                self.shown += 1
                self.set("cool", when)
        elif self.state == "result":
            self.set("idle", when)


class FakeAdb:
    def __init__(self, game: FakeGame):
        self.game = game
        self.serial = "fake"
        self.pending = []

    def _flush(self, now):
        due = [item for item in self.pending if item[2] <= now]
        self.pending = [item for item in self.pending if item[2] > now]
        for x, y, when in sorted(due, key=lambda item: item[2]):
            self.game.tap_at(x, y, when)

    def timed_screenshot(self):
        started = time.time()
        time.sleep(SHOT_AT)
        self._flush(time.time())
        img = self.game.image(time.time())
        time.sleep(SHOT_TIME - SHOT_AT)
        return img, started, time.time()

    def screenshot(self):
        return self.timed_screenshot()[0]

    def tap(self, x, y):
        self.pending.append((x, y, time.time() + TAP_DELAY))

    tap_fast = tap

    def close(self):
        pass


def main() -> None:
    speed = float(sys.argv[1]) if len(sys.argv) > 1 else 240.0
    sliders = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    game = FakeGame(speed, sliders)
    messages = []

    def log(text):
        messages.append(text)
        print(f"[{time.time() - t0:5.1f}s] {text}")

    t0 = time.time()
    runner = Runner(FakeAdb(game), log, threading.Event(), casts=2, multiplier=1, learn=False)
    # Game giả có độ trễ riêng, không phải độ lệch đo trên máy thật.
    runner._latency = 0.22  # game giả nhận lệnh ngay
    stats = runner.run()
    print(f"bấm {game.taps} lần, trúng {game.hits}/{sliders * 2}; chi tiết (mồi, vùng, trúng): {game.log}")
    print(f"thống kê: {stats.casts} lượt, {stats.caught} thành công, {stats.gold} Gold")


if __name__ == "__main__":
    main()
