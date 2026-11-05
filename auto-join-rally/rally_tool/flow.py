"""Vòng auto join rally. Chạy đến khi bấm Dừng, không giới hạn số rally.

Từ Goldrush mở chat Frostnip League, xin mọi nút xanh trong khoảng 10 tin gần nhất,
rồi đứng ở cuối chat chờ đợt sau. Không gõ tin, không bấm gửi, không tự tạo rally.
"""

from __future__ import annotations

import time

from gift_tool.adb_client import AdbClient
from gift_tool.vision import Finder, scene_signature, signature_diff
from rally_tool.paths import LOGS

from rally_tool.vision import (
    Reading,
    bottom_join,
    card_joins,
    chat_join_buttons,
    home_goldrush,
    jump_down,
    list_joins,
    load_icons,
    read_screen,
    reward_button,
    topmost,
)

# Ba lần kéo từ cuối chat phủ khoảng 10 tin. Hết thì quay xuống chờ.
CHAT_SCROLLS = 3
BOTTOM_RECHECK = 6.0
LIST_SCROLLS = 6
SCROLL_DIFF = 6.0
# Ảnh thu nhỏ của hai khung chat khác nhau lệch khoảng 8. Ngưỡng này vẫn thấy một lần kéo thật.
BOTTOM_DIFF = 4.0
POLL = 2.5
GOLDRUSH_LOAD = 10.0
# Hoạt cảnh vào Goldrush khoảng 2 giây. Chụp trong lúc này sẽ thấy màn đang trượt.
GOLDRUSH_ANIM = 2.0
AFTER_TAP = (0.55, 0.85)
SCROLL_PAUSE = (0.45, 0.7)


class Stopped(Exception):
    pass


class Runner:
    def __init__(self, adb: AdbClient, log, stop, finder: Finder | None = None):
        self.adb = adb
        self.log = log
        self.stop = stop
        self.finder = finder or Finder()
        load_icons(self.finder)
        self.poll = POLL
        self.quick = False
        self._parked = False
        self._snapped = False
        self._climbed = 0
        self._bottom_check = 0.0
        self._ready = False
        self._arm_sig = None
        self._returning = False
        self._jumped = False
        self._scroll_logged = False
        self._list_slides = 0
        self._goldrush_hold = 0.0
        self._chat_hold = 0.0
        self._single_tries = 0
        self._multi_stuck = 0
        self._unknown = 0
        self.asked = 0
        self.opened = 0

    def run(self) -> dict[str, int]:
        LOGS.mkdir(parents=True, exist_ok=True)
        self.log("Auto join rally. Không tạo rally. Chạy đến khi bấm Dừng.")
        try:
            while True:
                self._check()
                shot = self._shot()
                reading = read_screen(self.finder, shot)
                self._act(reading, shot)
        except Stopped:
            self.log(f"Đã dừng. Đã xin {self.asked} rally, mở {self.opened} thẻ từ chat.")
        return {"xin": self.asked, "mo": self.opened}

    def _act(self, reading: Reading, shot) -> None:
        scene = reading.scene
        if scene != "chat":
            self._parked = False
            self._snapped = False
            self._climbed = 0
            self._bottom_check = 0.0
            self._ready = False
            self._arm_sig = None
            self._returning = False
            self._jumped = False
            self._scroll_logged = False
        if scene != "multi":
            self._list_slides = 0
            self._multi_stuck = 0
        if scene != "single":
            self._single_tries = 0

        if scene == "camp":
            self._enter_goldrush(reading)
        elif scene == "map":
            self._open_chat(reading)
        elif scene == "chat":
            self._in_chat(reading, shot)
        elif scene == "single":
            self._one_rally(reading)
        elif scene == "multi":
            self._many_rallies(reading, shot)
        elif scene == "reward":
            self._close_reward(reading)
        else:
            self._unknown_screen(reading, shot)

    def _enter_goldrush(self, reading: Reading, hit=None) -> None:
        if time.time() < self._goldrush_hold:
            self._pause(0.4, 0.6)
            return
        target = hit if hit is not None else reading.goldrush
        if target is None:
            self._pause(0.4, 0.6)
            return
        self.log("Vào Goldrush.")
        self.adb.tap(target.x, target.y)
        # Bản đồ hiện chậm. Bấm lần hai trong lúc đang vào sẽ hủy hoặc bấm nhầm.
        self._goldrush_hold = time.time() + GOLDRUSH_LOAD
        self._pause(GOLDRUSH_ANIM, GOLDRUSH_ANIM)

    def _open_chat(self, reading: Reading) -> None:
        if reading.chat is None:
            return
        if time.time() < self._chat_hold:
            self._pause(0.3, 0.5)
            return
        self.log("Mở chat Frostnip League.")
        self.adb.tap(reading.chat.x, reading.chat.y)
        self._chat_hold = time.time() + 2.0
        self._pause(*AFTER_TAP)

    def _in_chat(self, reading: Reading, shot) -> None:
        # Nút đang hiện thì bấm ngay. Không kéo một loạt lúc chat vừa mở.
        if self._tap_join(shot, reading):
            return
        if not self._ready:
            sig = scene_signature(shot)
            # Khung chat còn trượt lúc mở. Kéo lúc này thành vài cú bấm thừa và làm chậm Join.
            if self._arm_sig is None or signature_diff(self._arm_sig, sig) >= BOTTOM_DIFF:
                self._arm_sig = sig
                return
            self._ready = True
        if self._returning:
            if self._jump_latest(shot):
                return
            if self._jumped or self._nudge_bottom(shot):
                self._arrive()
            return
        if not self._snapped:
            if self._nudge_bottom(shot):
                self._snapped = True
            return
        if not self._parked and self._climbed < CHAT_SCROLLS:
            self._climb(shot)
            return
        if not self._parked:
            self._park(shot)
            return
        if time.time() >= self._bottom_check and self._moved_newer(shot):
            self.log("Chưa ở tin mới nhất. Kéo xuống tiếp.")
            self._parked = False
            self._snapped = False
            self._climbed = 0
            self._returning = True
            return
        self._pause(self.poll, self.poll)

    def _tap_join(self, shot, reading: Reading) -> bool:
        cards = chat_join_buttons(self.finder, shot)
        if not cards:
            cards = card_joins(reading)
        if not cards:
            return False
        target = topmost(cards)
        self.opened += 1
        self.log(f"Mở rally từ chat ({self.opened}).")
        self._parked = False
        self._climbed = 0
        self._returning = False
        self.adb.tap(target.x, target.y)
        self._pause(*AFTER_TAP)
        return True

    def _climb(self, shot) -> None:
        before = scene_signature(shot)
        self._swipe_older(shot)
        self._pause(*SCROLL_PAUSE)
        after_shot = self._shot()
        self._climbed += 1
        moved = signature_diff(before, scene_signature(after_shot))
        if moved < SCROLL_DIFF or self._climbed >= CHAT_SCROLLS:
            self._park(after_shot)

    def _jump_latest(self, shot) -> bool:
        """Bấm mũi tên tím để về tin mới. Không có nút thì để nhánh kéo xử lý."""
        hit = jump_down(self.finder, shot)
        if hit is None:
            return False
        self.log("Xuống tin mới nhất.")
        self.adb.tap(hit.x, hit.y)
        self._pause(*AFTER_TAP)
        self._jumped = True
        return True

    def _arrive(self) -> None:
        self._jumped = False
        self._snapped = True
        self._returning = False
        self._parked = True
        self._climbed = 0
        self._bottom_check = time.time() + BOTTOM_RECHECK

    def _park(self, shot) -> None:
        self.log("Hết nút Join trong 10 tin. Đứng cuối chat chờ đợt sau.")
        self._returning = True
        self._snapped = False

    def _nudge_bottom(self, shot) -> bool:
        """Một cú kéo. True khi ảnh không đổi, tức là đang ở tin mới nhất."""
        before = scene_signature(shot)
        self._swipe_newer(shot)
        self._pause(0.4, 0.6)
        after_shot = self._shot()
        moved = signature_diff(before, scene_signature(after_shot)) >= BOTTOM_DIFF
        if not moved:
            return True
        if not self._scroll_logged:
            self.log("Kéo xuống tin mới nhất.")
            self._scroll_logged = True
        later = read_screen(self.finder, after_shot)
        if later.scene == "chat":
            self._tap_join(after_shot, later)
        return False

    def _moved_newer(self, shot) -> bool:
        before = scene_signature(shot)
        self._swipe_newer(shot)
        self._pause(0.35, 0.55)
        after = scene_signature(self._shot())
        self._bottom_check = time.time() + BOTTOM_RECHECK
        return signature_diff(before, after) >= BOTTOM_DIFF

    def _swipe_newer(self, shot) -> None:
        height, width = shot.shape[:2]
        x = int(width * 0.48)
        # Bắt đầu phía trên nút Join, tránh rê tay thành một cú bấm lên nút.
        self.adb.swipe(x, int(height * 0.50), x, int(height * 0.30), 280)

    def _one_rally(self, reading: Reading) -> None:
        target = bottom_join(reading)
        if target is not None and self._single_tries < 2:
            self._single_tries += 1
            self.asked += 1
            self.log(f"Xin vào rally ({self.asked}).")
            self.adb.tap(target.x, target.y)
            self._pause(*AFTER_TAP)
            return
        if reading.back is None:
            self.log("Màn một người không còn nút xanh và không thấy nút thoát.")
            self._pause(0.4, 0.6)
            return
        self.log("Rời màn rally.")
        self.adb.tap(reading.back.x, reading.back.y)
        self._single_tries = 0
        self._pause(*AFTER_TAP)

    def _many_rallies(self, reading: Reading, shot) -> None:
        targets = list_joins(reading)
        if targets and self._multi_stuck < 2:
            target = topmost(targets)
            self.asked += 1
            self.log(f"Xin vào rally trong danh sách ({self.asked}).")
            self.adb.tap(target.x, target.y)
            self._pause(*AFTER_TAP)
            # Nút vừa bấm còn xanh thì chưa ăn. Nút khác phía dưới vẫn được bấm ở vòng sau.
            later = read_screen(self.finder, self._shot())
            still_there = _same_bar(target, list_joins(later), reading.width, reading.height)
            self._multi_stuck = self._multi_stuck + 1 if still_there else 0
            return
        if self._list_slides < LIST_SCROLLS and self._multi_stuck < 2:
            before = scene_signature(shot)
            self._swipe_list(shot)
            self._list_slides += 1
            self._pause(*SCROLL_PAUSE)
            moved = signature_diff(before, scene_signature(self._shot()))
            if moved >= SCROLL_DIFF:
                self._multi_stuck = 0
                return
        if reading.close is None:
            self.log("Danh sách không còn nút xanh và không thấy nút X.")
            self._pause(0.4, 0.6)
            return
        self.log("Đóng danh sách rally.")
        self.adb.tap(reading.close.x, reading.close.y)
        self._list_slides = 0
        self._multi_stuck = 0
        self._pause(*AFTER_TAP)

    def _close_reward(self, reading: Reading) -> None:
        target = reward_button(reading)
        if target is None:
            self._pause(0.4, 0.6)
            return
        self.log("Đóng hộp hoàn thành rally.")
        self.adb.tap(target.x, target.y)
        self._pause(*AFTER_TAP)

    def _unknown_screen(self, reading: Reading, shot) -> None:
        # Ra khỏi mode quá xa: thanh dưới vẫn có nút Goldrush thì bấm để vào lại.
        hit = home_goldrush(self.finder, shot)
        if hit is not None:
            self._enter_goldrush(reading, hit)
            return
        self._unknown += 1
        if self._unknown == 1 or self._unknown % 8 == 0:
            from gift_tool.vision import imwrite

            path = LOGS / "rally-khong-nhan-ra-man.png"
            imwrite(path, shot)
            self.log(f"Chưa nhận ra màn hình, không bấm. Ảnh: {path}")
        self._pause(0.6, 0.9)

    def _swipe_older(self, shot) -> None:
        height, width = shot.shape[:2]
        x = int(width * 0.55)
        # Kéo tay xuống thì hiện tin cũ hơn phía trên.
        self.adb.swipe(x, int(height * 0.38), x, int(height * 0.70), 350)

    def _swipe_list(self, shot) -> None:
        height, width = shot.shape[:2]
        x = int(width * 0.50)
        self.adb.swipe(x, int(height * 0.72), x, int(height * 0.40), 350)

    def _shot(self):
        self._check()
        return self.adb.screenshot()

    def _pause(self, low: float, high: float) -> None:
        self._check()
        if self.quick or high <= 0:
            return
        end = time.time() + (low if low == high else _between(low, high))
        while time.time() < end:
            self._check()
            time.sleep(0.05)

    def _check(self) -> None:
        if self.stop.is_set():
            raise Stopped()


def _between(low: float, high: float) -> float:
    import random

    return random.uniform(low, high)


def _same_bar(target, hits, width: int, height: int) -> bool:
    dx = width * 0.05
    dy = height * 0.035
    return any(abs(hit.x - target.x) <= dx and abs(hit.y - target.y) <= dy for hit in hits)
