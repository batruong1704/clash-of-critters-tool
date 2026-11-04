"""Gõ một mã gift code rồi dừng khi quà hiện.

Sảnh hoặc Goldrush đều là điểm vào. Sảnh bấm Bạn bè, Goldrush bấm X về sảnh.
Rồi bánh răng, kéo Settings tới Redemption Code, gõ mã, bấm Confirm.
Thấy thanh Open Another hoặc Continue thì dừng, không bấm tiếp.
"""

from __future__ import annotations

import time

from gift_tool.paths import LOGS
from gift_tool.vision import Finder, imwrite

from giftcode_tool.vision import Icons, field_point, reward_bar

CLOSE_SCORE = 0.80
NAV_STEPS = 14
NAV_PAUSE = 0.45
RESULT_TIMEOUT = 25.0
# Hộp thoại còn nguyên sau khoảng này thì mã không được nhận. Quà thật mất vài giây để hiện thanh xanh.
FAIL_AFTER = 8.0
LOST_FILE = "khong-mo-duoc-giftcode.png"


class Stopped(Exception):
    pass


class Runner:
    def __init__(self, adb, log, stop, finder: Finder | None = None):
        self.adb = adb
        self.log = log
        self.stop = stop
        self.finder = finder or Finder()
        self.icons = Icons()
        self.quick = False

    def run(self, code: str) -> str:
        LOGS.mkdir(parents=True, exist_ok=True)
        self.log(f"Nhập mã {code}.")
        try:
            status = self._one(code)
        except Stopped:
            self.log("Đã dừng.")
            return "dung"
        if status == "dang_qua":
            self.log("Đã nhận mã. Đang ở màn quà, không bấm tiếp.")
            return "nhan"
        return status

    def run_many(self, codes: list[str]) -> dict[str, int]:
        """Gõ lần lượt. Mã không nhận thì sang mã sau. Mã nhận được thì rời màn quà, không bấm Open Another."""
        LOGS.mkdir(parents=True, exist_ok=True)
        counts = {"nhan": 0, "khong_nhan": 0, "khong_mo": 0}
        try:
            for index, code in enumerate(codes, start=1):
                self.log(f"[{index}/{len(codes)}] Nhập mã {code}.")
                status = self._one(code)
                if status == "dang_qua":
                    if not self._leave_reward():
                        break
                    status = self._one(code)
                if status == "nhan" and index < len(codes):
                    counts["nhan"] += 1
                    if not self._leave_reward():
                        break
                    continue
                if status == "nhan":
                    counts["nhan"] += 1
                elif status == "khong_mo" or status == "dang_qua":
                    counts["khong_mo"] += 1
                    break
                else:
                    counts["khong_nhan"] += 1
            self.log(f"Tổng kết mã — nhận {counts['nhan']}, không nhận {counts['khong_nhan']}.")
        except Stopped:
            self.log("Đã dừng.")
        return counts

    def _one(self, code: str) -> str:
        shot = self._open_dialog()
        if shot is None:
            return "khong_mo"
        if reward_bar(shot) is not None:
            return "dang_qua"
        self._submit(shot, code)
        return self._wait_result()

    def _leave_reward(self) -> bool:
        """Back đóng lớp quà. Không bấm thanh Open Another hay Continue."""
        self.log("Rời màn quà, không bấm Open Another.")
        self.adb.back()
        self._pause(0.6)
        if reward_bar(self._shot()) is not None:
            self.log("Vẫn ở màn quà, dừng các mã còn lại.")
            return False
        return True

    def _open_dialog(self):
        """Về hộp Redeem Rewards. Trả ảnh lúc thấy Confirm, hoặc ảnh thanh quà nếu quà đang mở."""
        shot = None
        for _ in range(NAV_STEPS):
            self._check()
            shot = self._shot()
            if reward_bar(shot) is not None or self.icons.find(shot, "confirm") is not None:
                return shot
            if not self._nav_step(shot):
                self._pause(NAV_PAUSE)
        imwrite(LOGS / LOST_FILE, shot if shot is not None else self._shot())
        self.log(f"Không mở được ô nhập mã. Ảnh: {LOGS / LOST_FILE}")
        return None

    def _nav_step(self, shot) -> bool:
        """Một việc. False nghĩa là chưa nhận ra màn."""
        redemption = self.icons.find(shot, "redemption")
        if redemption is not None:
            self.log("Bấm Redemption Code.")
            self.adb.tap(redemption.x, redemption.y)
            self._pause(NAV_PAUSE)
            return True
        if self.icons.find(shot, "settings") is not None:
            self.log("Kéo danh sách Cài đặt.")
            height, width = shot.shape[:2]
            x = int(width * 0.50)
            self.adb.swipe(x, int(height * 0.72), x, int(height * 0.42), 450)
            self._pause(NAV_PAUSE)
            return True
        gear = self.icons.find(shot, "gear")
        if gear is not None:
            self.log("Bấm bánh răng Cài đặt.")
            self.adb.tap(gear.x, gear.y)
            self._pause(NAV_PAUSE)
            return True
        friends = self.finder.find(shot, "friends")
        if friends is not None:
            self.log("Đang ở sảnh, bấm Bạn bè.")
            self.adb.tap(friends.x, friends.y)
            self._pause(NAV_PAUSE)
            return True
        close = self.finder.locate(shot, "close")
        if close is not None and close.w and close.score >= CLOSE_SCORE:
            self.log("Bấm X để về sảnh.")
            self.adb.tap(close.x, close.y)
            self._wait_left_goldrush()
            return True
        return False

    def _wait_left_goldrush(self) -> None:
        """X còn trên vài khung hình. Bấm lần hai rơi trúng nút Goldrush ở sảnh."""
        deadline = time.time() + (0.2 if self.quick else 6)
        while time.time() < deadline:
            self._check()
            shot = self._shot()
            if self.finder.find(shot, "friends") is not None:
                return
            close = self.finder.locate(shot, "close")
            if close is None or close.w == 0 or close.score < CLOSE_SCORE:
                return
            self._pause(0.3)

    def _submit(self, shot, code: str) -> None:
        confirm = self.icons.find(shot, "confirm")
        self.log("Gõ mã, bấm Confirm.")
        self.adb.tap(*field_point(shot, confirm))
        self._pause(0.3)
        self.adb.clear_text(40)
        self.adb.input_code(code)
        self._pause(0.4)
        again = self.icons.find(self._shot(), "confirm")
        if again is None:
            # Bàn phím che nút. Một lần Back đóng bàn phím, chưa đóng hộp thoại.
            self.adb.back()
            self._pause(0.3)
            again = self.icons.find(self._shot(), "confirm")
        if again is not None:
            self.adb.tap(again.x, again.y)
        else:
            self.adb.tap(confirm.x, confirm.y)
        self._pause(0.4)

    def _wait_result(self) -> str:
        fail_at = None
        deadline = time.time() + (0.25 if self.quick else RESULT_TIMEOUT)
        fail_after = 0.05 if self.quick else FAIL_AFTER
        while time.time() < deadline:
            self._check()
            shot = self._shot()
            if reward_bar(shot) is not None:
                self.log("Đã nhận mã. Dừng, không bấm tiếp.")
                return "nhan"
            if self.icons.find(shot, "confirm") is not None:
                if fail_at is None:
                    fail_at = time.time()
                elif time.time() - fail_at >= fail_after:
                    self.log("Mã không được nhận.")
                    return "khong_nhan"
            else:
                fail_at = None
            self._pause(0.35)
        imwrite(LOGS / LOST_FILE, self._shot())
        self.log(f"Hết giờ chờ quà. Ảnh: {LOGS / LOST_FILE}")
        return "khong_nhan"

    def _shot(self):
        self._check()
        return self.adb.screenshot()

    def _pause(self, seconds: float) -> None:
        if self.quick:
            self._check()
            return
        end = time.time() + seconds
        while time.time() < end:
            self._check()
            time.sleep(0.05)

    def _check(self) -> None:
        if self.stop.is_set():
            raise Stopped()
