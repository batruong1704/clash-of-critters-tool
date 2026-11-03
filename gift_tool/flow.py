"""Luồng một UID: tìm, vào nhà, nhận hộp quà nếu có, rồi quay ra."""

from __future__ import annotations

import csv
import random
import time
from datetime import datetime

from gift_tool.adb_client import AdbClient
from gift_tool.paths import LOGS
from gift_tool.vision import (
    Finder,
    avatar_point,
    field_point,
    result_signature,
    scene_signature,
    signature_diff,
)

MAX_GIFTS = 20

LABELS = {
    "da_nhan_qua": "đã nhận quà",
    "khong_co_qua": "không có quà",
    "id_sai": "ID sai",
    "loi_timeout": "lỗi / timeout",
}

BUTTON_NAMES = {
    "select": "Select",
    "ok": "OK",
}

RESULT_DIFF = 12.0
TAP_DELAY = (0.22, 0.45)
BETWEEN_IDS = (0.3, 0.6)
FOCUS_PAUSE = (0.35, 0.55)
POLL_PAUSE = (0.2, 0.35)
AFTER_VISIT = (0.6, 0.9)
SEARCH_TIMEOUT = 5.0
SEARCH_GIVE_UP = 1.2
RESULT_STABLE = 0.25
VISIT_TIMEOUT = 3.0
HOUSE_ENTER_TIMEOUT = 4.0
HOUSE_CLOSE_SCORE = 0.80
NO_GIFT_PAUSE = (0.45, 0.6)
PAN_DIFF = 15.0
PAN_FOLLOW = 2.0
GIFT_SCALES = (1.0, 1.05)
UI_SCALES = (1.0,)
EXIT_GAP = 0.9
BACK_TIMEOUT = 6.0


class Stopped(Exception):
    pass


class Runner:
    def __init__(self, adb: AdbClient, finder: Finder, log, stop, detail=None, max_gifts: int = MAX_GIFTS):
        self.adb = adb
        self.finder = finder
        self.log = log
        self.detail = detail
        self.stop = stop
        self.max_gifts = max_gifts

    def run(self, ids: list[str]) -> dict[str, int]:
        counts = {key: 0 for key in LABELS}
        LOGS.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        csv_path = LOGS / f"ket-qua-{stamp}.csv"
        self.log(f"Ghi log: {csv_path}")
        with csv_path.open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.writer(handle)
            writer.writerow(["id", "trang_thai", "giay", "ghi_chu"])
            self._step("Kiểm tra hướng màn hình")
            shot = self._shot()
            if shot.shape[1] > shot.shape[0]:
                self._step("Emulator đang ngang")
                self.log("Emulator đang ngang. Hãy xoay dọc, giống ảnh mẫu, rồi chạy lại.")
                return counts
            self._step("Kiểm tra ô nhập UID")
            if not self._search_ready(shot):
                self._step("Chưa thấy ô nhập UID")
                self.log("Chưa thấy ô nhập UID. Hãy mở tab Add New trong game rồi bấm Bắt đầu.")
                return counts
            for index, uid in enumerate(ids, start=1):
                self._check()
                if counts["da_nhan_qua"] >= self.max_gifts:
                    self._step(f"Đủ {self.max_gifts} quà, dừng")
                    self.log(f"Đủ {self.max_gifts} quà, dừng.")
                    break
                self.log(f"[{index}/{len(ids)}] UID {uid} — đã nhận {counts['da_nhan_qua']}/{self.max_gifts}")
                self._step(f"UID {uid} ({index}/{len(ids)})")
                started = time.time()
                try:
                    status, note, ready = self.process_one(uid)
                except Stopped:
                    self._step("Dừng theo lệnh")
                    self.log("Đã dừng.")
                    break
                except Exception as exc:
                    status, note, ready = "loi_timeout", str(exc), False
                seconds = time.time() - started
                counts[status] += 1
                writer.writerow([uid, LABELS[status], f"{seconds:.1f}", note])
                handle.flush()
                self.log(f"  {LABELS[status]} ({seconds:.1f}s). {note}")
                if not ready:
                    self.log("Không thấy lại ô nhập UID. Dừng để khỏi bấm nhầm. Mở lại tab Add New rồi chạy tiếp các ID còn lại.")
                    break
                self._pause(*BETWEEN_IDS)
        self._summary(counts)
        return counts

    def process_one(self, uid: str) -> tuple[str, str, bool]:
        self._step("Tìm ô nhập UID")
        shot = self._shot()
        search = self.finder.find(shot, "search")
        if search is None:
            self._step("Không thấy ô nhập UID")
            return "loi_timeout", "không thấy ô tìm UID", False

        field_x, field_y = field_point(shot, search)
        self._step("Bấm vào ô nhập")
        self.adb.tap(field_x, field_y)
        self._pause(*FOCUS_PAUSE)
        self._step("Xóa UID cũ")
        self.adb.clear_text()
        self._step(f"Gõ UID {uid}")
        self.adb.input_text(uid)
        self._step("Bấm tìm")
        self.adb.tap(search.x, search.y)

        self._step("Chờ kết quả tìm")
        shot, found = self._wait_search(SEARCH_TIMEOUT)
        if found is None:
            self._step("Không thấy người chơi")
            return "id_sai", "không thấy người chơi", self.finder.find(shot, "search", scales=UI_SCALES) is not None

        self._step("Bấm avatar")
        self.adb.tap(*avatar_point(shot, found))
        self._step("Chờ nút Visit")
        shot, visit = self._wait_visit()
        if visit is None:
            self._step("Không thấy nút Visit")
            return "loi_timeout", "không thấy nút Visit", self._search_ready(shot)
        self._step("Bấm Visit")
        self.adb.tap(visit.x, visit.y)

        self._step("Vào nhà, tìm hộp quà")
        outcome = self._wait_house()
        if outcome == "gift":
            return self._collect_gift(self._shot())
        # Còn đứng trong nhà khi kết luận không có quà. Phải thấy lại ô tìm rồi mới sang UID sau.
        ready = self._back_to_search()
        if outcome == "no_gift":
            return "khong_co_qua", "vào nhà, không thấy hộp quà", ready
        return "loi_timeout", "không vào được nhà", ready

    def _tap_close(self, shot) -> None:
        close = self.finder.find(shot, "close")
        if close is not None:
            self.adb.tap(close.x, close.y)
            return
        height, width = shot.shape[:2]
        self.adb.tap(int(width * 0.50), int(height * 0.96))

    def _collect_gift(self, shot) -> tuple[str, str, bool]:
        gift = self.finder.find(shot, "gift")
        if gift is not None:
            self._step("Bấm hộp quà")
            self.adb.tap(gift.x, gift.y)
            self._pause(0.25, 0.35)
        self._step("Chờ nút Select")
        if not self._wait_tap("select", timeout=3):
            gift = self.finder.find(self._shot(), "gift")
            if gift is not None:
                self._step("Chưa thấy Select, bấm lại hộp quà")
                self.adb.tap(gift.x, gift.y)
            self._step("Chờ nút Select lần nữa")
            if not self._wait_tap("select", timeout=2):
                self._step("Không thấy nút Select")
                ready = self._back_to_search()
                return "loi_timeout", "đã thấy hộp quà nhưng không thấy nút Select", ready
        self._step("Chờ nút OK")
        if not self._wait_tap("ok", timeout=3):
            self._step("Không thấy nút OK")
            ready = self._back_to_search()
            return "loi_timeout", "đã bấm Select nhưng không thấy nút OK", ready
        self._step("Đã bấm Select và OK")
        ready = self._back_to_search()
        return "da_nhan_qua", "đã bấm Select và OK", ready

    def _result_add(self, shot, scales=None):
        """Nút Add của hàng Results, không phải gợi ý Players you may know."""
        header = self.finder.find(shot, "results", scales=scales)
        if header is None:
            return None
        height = shot.shape[0]
        return self.finder.find_below(
            shot, "add", int(header.y), int(header.y + 0.22 * height), scales
        )

    def _wait_search(self, timeout: float):
        """Câu báo ID sai hiện ngay thì trả về, không ngồi hết hạn tìm người chơi."""
        deadline = time.time() + timeout
        stable_since = None
        idle_since = None
        shot = None
        while time.time() < deadline:
            self._check()
            shot = self._shot()
            if self.finder.find(shot, "missing_id", scales=UI_SCALES):
                return shot, None
            found = self._result_add(shot, UI_SCALES)
            if found is not None:
                idle_since = None
                if stable_since is None:
                    stable_since = time.time()
                elif time.time() - stable_since >= RESULT_STABLE:
                    return shot, found
            else:
                stable_since = None
                if idle_since is None:
                    idle_since = time.time()
                elif time.time() - idle_since >= SEARCH_GIVE_UP:
                    return shot, None
            self._pause(*POLL_PAUSE)
        if shot is None:
            shot = self._shot()
        return shot, None

    def _wait_result(self, before, timeout: float) -> tuple[bool, object]:
        deadline = time.time() + timeout
        last = None
        stable_since = None
        shot = self._shot()
        while time.time() < deadline:
            self._check()
            shot = self._shot()
            search = self.finder.find(shot, "search")
            if search is None:
                self._pause(0.3, 0.45)
                continue
            current = result_signature(shot, search)
            if last is not None and signature_diff(current, last) < 3:
                if stable_since is None:
                    stable_since = time.time()
                elif time.time() - stable_since >= 0.8:
                    return signature_diff(current, before) >= RESULT_DIFF, shot
            else:
                stable_since = None
            last = current
            self._pause(0.3, 0.45)
        search = self.finder.find(shot, "search")
        if search is None:
            return False, shot
        return signature_diff(result_signature(shot, search), before) >= RESULT_DIFF, shot

    def _wait_visit(self):
        """Popup Visit không hiện ngay sau cú bấm avatar."""
        deadline = time.time() + VISIT_TIMEOUT
        shot = None
        while time.time() < deadline:
            self._check()
            shot = self._shot()
            visit = self.finder.find(shot, "visit", scales=(1.0, 1.05))
            if visit is not None:
                return shot, visit
            self._pause(*POLL_PAUSE)
        return shot if shot is not None else self._shot(), None

    def _wait_house(self) -> str:
        """Không có quà thì sân đứng yên: nhìn thêm một nhịp rồi thoát, không chờ hết hạn vào nhà."""
        deadline = time.time() + HOUSE_ENTER_TIMEOUT
        visit_taps = 0
        anchor = None
        while time.time() < deadline:
            self._check()
            shot = self._shot()
            if self._seen_gift(shot):
                return "gift"
            if anchor is None:
                visit = self.finder.find(shot, "visit", scales=UI_SCALES)
                if visit is not None and visit_taps < 2:
                    self._step("Popup Visit còn, bấm lại")
                    self.adb.tap(visit.x, visit.y)
                    visit_taps += 1
                    self._pause(*AFTER_VISIT)
                    continue
                if not self._in_house(shot, visit):
                    self._pause(*POLL_PAUSE)
                    continue
                self._step("Đã vào nhà, nhìn sân")
                anchor = scene_signature(shot)
                self._pause(*NO_GIFT_PAUSE)
                continue
            # Camera không trượt sau nhịp ngắn thì không có hộp. Critter nhấp không đủ độ lệch này.
            if signature_diff(anchor, scene_signature(shot)) >= PAN_DIFF:
                return self._follow_gift()
            self._step("Sân đứng yên, không có quà")
            return "no_gift"
        if anchor is None:
            self._step("Chưa vào được nhà")
            return "timeout"
        self._step("Hết giờ trong nhà, không thấy hộp")
        return "no_gift"

    def _seen_gift(self, shot) -> bool:
        gift = self.finder.find(shot, "gift", scales=GIFT_SCALES)
        if gift is not None:
            self._step("Bấm hộp quà")
            self.adb.tap(gift.x, gift.y)
            self._pause(*TAP_DELAY)
            return True
        return self.finder.find(shot, "select", scales=UI_SCALES) is not None

    def _in_house(self, shot, visit) -> bool:
        if visit is not None or self.finder.find(shot, "search", scales=UI_SCALES) is not None:
            return False
        close = self.finder.locate(shot, "close", scales=UI_SCALES)
        return close.w > 0 and close.score >= HOUSE_CLOSE_SCORE

    def _follow_gift(self) -> str:
        """Camera đã rời chỗ đứng, nên hộp có thể chưa vào giữa khung."""
        self._step("Camera trượt, đuổi hộp quà")
        deadline = time.time() + PAN_FOLLOW
        while time.time() < deadline:
            self._check()
            if self._seen_gift(self._shot()):
                return "gift"
            self._pause(*POLL_PAUSE)
        self._step("Hết nhịp đuổi, không thấy hộp")
        return "no_gift"

    def _wait_tap(self, name: str, timeout: float) -> bool:
        deadline = time.time() + timeout
        taps = 0
        while time.time() < deadline:
            self._check()
            shot = self._shot()
            hit = self.finder.find(shot, name)
            if hit is not None and taps < 2:
                self._step(f"Bấm nút {BUTTON_NAMES.get(name, name)}")
                self.adb.tap(hit.x, hit.y)
                taps += 1
                self._pause(0.28, 0.5)
                if self.finder.find(self._shot(), name) is None:
                    return True
                continue
            if hit is None and taps > 0:
                return True
            self._pause(0.15, 0.28)
        return False

    def _back_to_search(self) -> bool:
        """Bấm thoát một lần rồi chỉ chờ kính lúp. Không bấm X liền tay kẻo đóng tab Add New."""
        self._step("Thoát về ô nhập UID")
        deadline = time.time() + BACK_TIMEOUT
        tapped_at = 0.0
        while time.time() < deadline:
            self._check()
            shot = self._shot()
            search = self.finder.find(shot, "search", scales=UI_SCALES)
            visit = self.finder.find(shot, "visit", scales=UI_SCALES)
            select = self.finder.find(shot, "select", scales=UI_SCALES)
            ok = self.finder.find(shot, "ok", scales=UI_SCALES)
            if search is not None and visit is None and select is None and ok is None:
                self._step("Đã về ô nhập UID")
                return True
            if tapped_at and time.time() - tapped_at < EXIT_GAP:
                self._pause(*POLL_PAUSE)
                continue
            if select is not None:
                self._step("Bấm Select để thoát")
                self.adb.tap(select.x, select.y)
            elif ok is not None:
                self._step("Bấm OK để thoát")
                self.adb.tap(ok.x, ok.y)
            elif visit is not None:
                self._step("Đóng popup Visit")
                self._dismiss_visit_popup(shot)
            else:
                close = self.finder.locate(shot, "close", scales=UI_SCALES)
                if close.w > 0 and close.score >= HOUSE_CLOSE_SCORE:
                    self._step("Bấm nút đóng")
                    self.adb.tap(close.x, close.y)
                else:
                    self._step("Bấm mép dưới để thoát")
                    height, width = shot.shape[:2]
                    self.adb.tap(int(width * 0.50), int(height * 0.96))
            tapped_at = time.time()
            self._pause(*POLL_PAUSE)
        ready = self._search_ready(self._shot(), UI_SCALES)
        if ready:
            self._step("Đã về ô nhập UID")
        else:
            self._step("Chưa thấy lại ô nhập UID")
        return ready

    def _dismiss_visit_popup(self, shot) -> None:
        # Nút Back của Android không đóng popup này. Bấm vùng tối bên phải.
        height, width = shot.shape[:2]
        self.adb.tap(int(width * 0.69), int(height * 0.70))

    def _leave_search_overlays(self) -> None:
        shot = self._shot()
        if self.finder.find(shot, "visit") is not None:
            self._dismiss_visit_popup(shot)
            self._pause(0.15, 0.3)

    def _search_ready(self, shot, scales=None) -> bool:
        return (
            self.finder.find(shot, "search", scales=scales) is not None
            and self.finder.find(shot, "visit", scales=scales) is None
            and self.finder.find(shot, "select", scales=scales) is None
            and self.finder.find(shot, "ok", scales=scales) is None
        )

    def _shot(self):
        self._check()
        return self.adb.screenshot()

    def _pause(self, low: float, high: float) -> None:
        end = time.time() + random.uniform(low, high)
        while time.time() < end:
            self._check()
            time.sleep(0.05)

    def _check(self) -> None:
        if self.stop.is_set():
            raise Stopped()

    def _step(self, message: str) -> None:
        if self.detail is not None:
            self.detail(message)

    def _summary(self, counts: dict[str, int]) -> None:
        parts = [f"{LABELS[key]}: {counts[key]}" for key in LABELS]
        self.log("Tổng kết — " + ", ".join(parts))

