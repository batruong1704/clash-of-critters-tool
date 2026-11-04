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
    add_new_tab_point,
    avatar_point,
    field_point,
    imwrite,
    player_level,
    result_signature,
    scene_signature,
    signature_diff,
)

MAX_GIFTS = 20
MIN_LEVEL = 150

LABELS = {
    "da_nhan_qua": "đã nhận quà",
    "khong_co_qua": "không có quà",
    "id_sai": "ID sai",
    "cap_thap": "false",
    "loi_timeout": "lỗi / timeout",
}

BUTTON_NAMES = {
    "select": "Select",
    "ok": "OK",
}

LOG_INDENT = "  "

RESULT_DIFF = 12.0
TAP_DELAY = (0.22, 0.45)
BETWEEN_IDS = (0.3, 0.6)
FOCUS_PAUSE = (0.35, 0.55)
POLL_PAUSE = (0.2, 0.35)
AFTER_VISIT = (0.6, 0.9)
SEARCH_TIMEOUT = 5.0
SEARCH_GIVE_UP = 1.2
RESULT_STABLE = 0.25
# Cấp đọc rỗng (nhãn chưa vẽ xong, hoặc rớt chữ số) thì chụp lại vài lần trước khi bỏ cuộc.
LEVEL_READS = 4
LEVEL_RETRY_PAUSE = (0.25, 0.4)
LEVEL_FAIL_FILE = "khong-doc-duoc-cap.png"
VISIT_TIMEOUT = 3.0
# Tải nhà mất khoảng 3,8s. Hạn này chỉ để chờ nút X, không tính lúc đã đứng trong nhà.
HOUSE_ENTER_TIMEOUT = 5.0
HOUSE_CLOSE_SCORE = 0.80
# Sau khi thấy nút X vẫn nhìn sân. Một nhịp 0,5s dễ bấm X trước khi camera chạy tới hộp.
HOUSE_LOOK = 2.5
PAN_DIFF = 15.0
PAN_FOLLOW = 3.5
GIFT_SCALES = (1.0, 1.05)
UI_SCALES = (1.0,)
SEARCH_MIN_X = 0.55
BACK_TIMEOUT = 6.0
# Tự tìm đường về ô nhập UID. Mỗi vòng chỉ làm một việc rồi chụp lại.
NAV_TIMEOUT = 30.0
NAV_MAX_ACTIONS = 8
NAV_OPEN_PAUSE = (0.8, 1.1)
NAV_TAB_PAUSE = (0.5, 0.7)
# Bấm X lần hai khi màn cũ chưa kịp đổi sẽ rơi trúng nút Goldrush giữa đáy sân.
NAV_CLOSE_SETTLE = 4.0
NAV_AFTER_CLOSE = (0.6, 0.9)
LOST_SCREEN_FILE = "khong-nhan-ra-man.png"


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
        self._clock = time.time()

    def run(self, ids: list[str]) -> dict[str, int]:
        counts = {key: 0 for key in LABELS}
        LOGS.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        csv_path = LOGS / f"ket-qua-{stamp}.csv"
        self._log_note(f"Ghi log: {csv_path}")
        with csv_path.open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.writer(handle)
            writer.writerow(["id", "trang_thai", "giay", "ghi_chu"])
            self._step("Kiểm tra hướng màn hình")
            shot = self._shot()
            if shot.shape[1] > shot.shape[0]:
                self._step("Emulator đang ngang", headline=True)
                self.log("Emulator đang ngang. Hãy xoay dọc, giống ảnh mẫu, rồi chạy lại.")
                return counts
            self._step("Kiểm tra ô nhập UID")
            if not self._open_uid_field(shot):
                self._step("Không tìm được đường tới ô nhập UID", headline=True)
                self.log(
                    "Không tự mở được ô nhập UID. Hãy mở tab Add New trong game rồi bấm Bắt đầu. "
                    f"Ảnh màn hình lúc đó: {LOGS / LOST_SCREEN_FILE}"
                )
                return counts
            for index, uid in enumerate(ids, start=1):
                self._check()
                if counts["da_nhan_qua"] >= self.max_gifts:
                    self._step(f"Đủ {self.max_gifts} quà, dừng", headline=True)
                    self.log(f"Đủ {self.max_gifts} quà, dừng.")
                    break
                self.log(f"[{index}/{len(ids)}] UID {uid} — đã nhận {counts['da_nhan_qua']}/{self.max_gifts}")
                self._step(f"UID {uid} ({index}/{len(ids)})", headline=True)
                started = time.time()
                self._clock = started
                try:
                    status, note, ready = self.process_one(uid)
                except Stopped:
                    self._step("Dừng theo lệnh", headline=True)
                    self.log("Đã dừng.")
                    break
                except Exception as exc:
                    status, note, ready = "loi_timeout", str(exc), False
                seconds = time.time() - started
                counts[status] += 1
                writer.writerow([uid, LABELS[status], f"{seconds:.1f}", note])
                handle.flush()
                self._log_note(f"{LABELS[status]} ({seconds:.1f}s). {note}")
                if not ready:
                    self._step("Mất ô nhập UID, tự mở lại")
                    ready = self._open_uid_field()
                if not ready:
                    self.log("Không tự mở lại được ô nhập UID. Dừng để khỏi bấm nhầm. Mở lại tab Add New rồi chạy tiếp các ID còn lại.")
                    break
                self._pause(*BETWEEN_IDS)
        self._summary(counts)
        return counts

    def process_one(self, uid: str) -> tuple[str, str, bool]:
        self._step("Tìm ô nhập UID")
        shot = self._shot()
        search = self._uid_search(shot)
        if search is None:
            # Đang ở sân, Goldrush hoặc panel hồ sơ sai tab thì tự mò về, không báo lỗi ngay.
            if self._open_uid_field(shot):
                shot = self._shot()
                search = self._uid_search(shot)
        if search is None:
            self._step("Không thấy ô nhập UID", headline=True)
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
            self._step("Không thấy người chơi", headline=True)
            return "id_sai", "không thấy người chơi", self._uid_search(shot, UI_SCALES) is not None

        shot, found, level = self._read_level(shot, found)
        if level is not None and level < MIN_LEVEL:
            self._step(f"Cấp {level}, dưới {MIN_LEVEL}", headline=True)
            ready = self._uid_search(shot, UI_SCALES) is not None
            return "cap_thap", f"cấp {level}, dưới {MIN_LEVEL}", ready
        if level is None:
            self._step("Không đọc được cấp, vẫn vào nhà")
        else:
            self._step(f"Cấp {level}")

        self._step("Bấm avatar")
        self.adb.tap(*avatar_point(shot, found))
        self._step("Chờ nút Visit")
        shot, visit = self._wait_visit()
        if visit is None:
            self._step("Không thấy nút Visit", headline=True)
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

    def _read_level(self, shot, found):
        """Trả (ảnh, nút Add, cấp). Cấp rỗng sau vài lần chụp thì lưu ảnh để soi lại."""
        for attempt in range(LEVEL_READS):
            level = player_level(shot, found)
            if level is not None:
                return shot, found, level
            if attempt == LEVEL_READS - 1:
                break
            self._step("Chưa đọc được cấp, chụp lại")
            self._pause(*LEVEL_RETRY_PAUSE)
            again = self._shot()
            add = self._result_add(again, UI_SCALES)
            if add is None:
                break
            shot, found = again, add
        imwrite(LOGS / LEVEL_FAIL_FILE, shot)
        return shot, found, None

    def _tap_close(self, shot) -> None:
        close = self.finder.find(shot, "close")
        if close is not None:
            self.adb.tap(close.x, close.y)

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
                self._step("Không thấy nút Select", headline=True)
                ready = self._back_to_search()
                return "loi_timeout", "đã thấy hộp quà nhưng không thấy nút Select", ready
        self._step("Chờ nút OK")
        if not self._wait_tap("ok", timeout=3):
            self._step("Không thấy nút OK", headline=True)
            ready = self._back_to_search()
            return "loi_timeout", "đã bấm Select nhưng không thấy nút OK", ready
        self._step("Đã bấm Select và OK", headline=True)
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
        """Vào nhà xong vẫn nhìn sân. Hết giờ tải nhà không được cắt ngắn lúc đang tìm hộp."""
        enter_deadline = time.time() + HOUSE_ENTER_TIMEOUT
        look_deadline = None
        visit_taps = 0
        anchor = None
        while True:
            self._check()
            now = time.time()
            if look_deadline is None and now >= enter_deadline:
                self._step("Chưa vào được nhà", headline=True)
                return "timeout"
            if look_deadline is not None and now >= look_deadline:
                self._step("Sân đứng yên, không có quà", headline=True)
                return "no_gift"
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
                look_deadline = time.time() + HOUSE_LOOK
                self._pause(*POLL_PAUSE)
                continue
            # Camera không trượt suốt lúc nhìn sân thì không có hộp. Critter nhấp không đủ độ lệch này.
            if signature_diff(anchor, scene_signature(shot)) >= PAN_DIFF:
                return self._follow_gift()
            self._pause(*POLL_PAUSE)

    def _seen_gift(self, shot) -> bool:
        gift = self.finder.find(shot, "gift", scales=GIFT_SCALES)
        if gift is not None:
            self._step("Bấm hộp quà")
            self.adb.tap(gift.x, gift.y)
            self._pause(*TAP_DELAY)
            return True
        return self.finder.find(shot, "select", scales=UI_SCALES) is not None

    def _in_house(self, shot, visit) -> bool:
        if visit is not None or self._uid_search(shot, UI_SCALES) is not None:
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
        self._step("Hết nhịp đuổi, không thấy hộp", headline=True)
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
        """Chỉ bấm đóng một lần. Cú thứ hai rơi trúng nút Goldrush giữa đáy sân."""
        self._step("Thoát về ô nhập UID")
        deadline = time.time() + BACK_TIMEOUT
        tapped = False
        while time.time() < deadline:
            self._check()
            shot = self._shot()
            if self._on_yard(shot):
                # Không bấm thêm ở đây. Vòng ngoài sẽ mở lại panel Bạn bè bằng _open_uid_field.
                self._step("Đang ở sân, không bấm Goldrush", headline=True)
                return False
            if self._search_ready(shot, UI_SCALES):
                self._step("Đã về ô nhập UID")
                return True
            if tapped:
                self._pause(*POLL_PAUSE)
                continue
            select = self.finder.find(shot, "select", scales=UI_SCALES)
            ok = self.finder.find(shot, "ok", scales=UI_SCALES)
            visit = self.finder.find(shot, "visit", scales=UI_SCALES)
            close = self.finder.locate(shot, "close", scales=UI_SCALES)
            if select is not None:
                self._step("Bấm Select để thoát")
                self.adb.tap(select.x, select.y)
                tapped = True
            elif ok is not None:
                self._step("Bấm OK để thoát")
                self.adb.tap(ok.x, ok.y)
                tapped = True
            elif visit is not None:
                self._step("Đóng popup Visit")
                self._dismiss_visit_popup(shot)
                tapped = True
            elif close.w > 0 and close.score >= HOUSE_CLOSE_SCORE:
                self._step("Bấm nút đóng")
                self.adb.tap(close.x, close.y)
                tapped = True
            self._pause(*POLL_PAUSE)
        ready = self._search_ready(self._shot(), UI_SCALES)
        if ready:
            self._step("Đã về ô nhập UID")
        else:
            self._step("Chưa thấy lại ô nhập UID", headline=True)
        return ready

    def _open_uid_field(self, shot=None) -> bool:
        """Từ màn quen nào cũng mò về tab Add New: Goldrush, sân chính, panel hồ sơ sai tab, popup còn sót."""
        deadline = time.time() + NAV_TIMEOUT
        actions = 0
        scales = None
        while time.time() < deadline and actions < NAV_MAX_ACTIONS:
            self._check()
            if shot is None:
                shot = self._shot()
            if self._search_ready(shot, scales):
                return True
            scales = UI_SCALES
            if self._nav_step(shot):
                actions += 1
            else:
                self._pause(*POLL_PAUSE)
            shot = None
        shot = self._shot()
        if self._search_ready(shot, UI_SCALES):
            return True
        imwrite(LOGS / LOST_SCREEN_FILE, shot)
        return False

    def _nav_step(self, shot) -> bool:
        """Một việc cho màn hiện tại. False nghĩa là chưa nhận ra màn, chờ rồi chụp lại."""
        visit = self.finder.find(shot, "visit", scales=UI_SCALES)
        if visit is not None:
            self._step("Còn popup Visit, đóng lại")
            self._dismiss_visit_popup(shot)
            self._pause(*NAV_TAB_PAUSE)
            return True
        for name in ("select", "ok"):
            hit = self.finder.find(shot, name, scales=UI_SCALES)
            if hit is not None:
                self._step(f"Còn nút {BUTTON_NAMES[name]}, bấm để dọn")
                self.adb.tap(hit.x, hit.y)
                self._pause(*NAV_TAB_PAUSE)
                return True

        community = self.finder.find(shot, "community", scales=UI_SCALES)
        if community is not None:
            self._step("Đang ở panel hồ sơ, chuyển sang tab Add New")
            self.adb.tap(*add_new_tab_point(shot, community))
            self._pause(*NAV_TAB_PAUSE)
            return True

        friends = self.finder.find(shot, "friends", scales=UI_SCALES)
        if friends is not None:
            self._step("Đang ở màn chính, mở panel Bạn bè")
            self.adb.tap(friends.x, friends.y)
            self._pause(*NAV_OPEN_PAUSE)
            return True

        close = self.finder.locate(shot, "close", scales=UI_SCALES)
        if close.w > 0 and close.score >= HOUSE_CLOSE_SCORE:
            self._step("Đang ở Goldrush hoặc trong nhà, bấm X để ra màn chính")
            self.adb.tap(close.x, close.y)
            self._wait_close_gone()
            return True
        return False

    def _wait_close_gone(self) -> None:
        """Chờ nút X biến mất hẳn rồi mới cho bấm tiếp."""
        deadline = time.time() + NAV_CLOSE_SETTLE
        while time.time() < deadline:
            self._pause(*POLL_PAUSE)
            close = self.finder.locate(self._shot(), "close", scales=UI_SCALES)
            if close.w == 0 or close.score < HOUSE_CLOSE_SCORE:
                break
        self._pause(*NAV_AFTER_CLOSE)

    def _uid_search(self, shot, scales=None):
        """Kính lúp ô UID nằm bên phải. Kính lúp Goldrush nằm bên trái."""
        hit = self.finder.find(shot, "search", scales=scales)
        if hit is None or hit.x < shot.shape[1] * SEARCH_MIN_X:
            return None
        return hit

    def _on_yard(self, shot) -> bool:
        return self.finder.find(shot, "goldrush", scales=UI_SCALES) is not None

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
            self._uid_search(shot, scales) is not None
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

    def _step(self, message: str, *, headline: bool = False) -> None:
        # Kết luận sát lề. Bước làm thụt vào để khỏi lẫn với kết quả.
        if self.detail is None:
            return
        # Mốc giờ tính từ đầu UID, để thấy bước nào ngốn thời gian.
        # Dấu ngoặc ở đầu dòng để GUI không nhầm dòng kết luận thành bước phụ (bước phụ bắt đầu bằng khoảng trắng).
        stamp = f"[{time.time() - self._clock:5.1f}s]"
        if headline:
            self.detail(f"{stamp} {message}")
        else:
            self.detail(f"{LOG_INDENT}{stamp} {message}")

    def _log_note(self, message: str) -> None:
        self.log(f"{LOG_INDENT}{message}")

    def _summary(self, counts: dict[str, int]) -> None:
        parts = [f"{LABELS[key]}: {counts[key]}" for key in LABELS]
        self.log("Tổng kết — " + ", ".join(parts))

