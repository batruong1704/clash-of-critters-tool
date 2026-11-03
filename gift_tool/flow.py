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
    signature_diff,
)

LABELS = {
    "da_nhan_qua": "đã nhận quà",
    "khong_co_qua": "không có quà",
    "id_sai": "ID sai",
    "loi_timeout": "lỗi / timeout",
}

RESULT_DIFF = 12.0
TAP_DELAY = (0.22, 0.45)
BETWEEN_IDS = (0.3, 0.6)
SEARCH_GIVE_UP = 2.0
HOUSE_GIFT_LOOK = 1.2


class Stopped(Exception):
    pass


class Runner:
    def __init__(self, adb: AdbClient, finder: Finder, log, stop, max_gifts: int = 20):
        self.adb = adb
        self.finder = finder
        self.log = log
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
            shot = self._shot()
            if shot.shape[1] > shot.shape[0]:
                self.log("Emulator đang ngang. Hãy xoay dọc, giống ảnh mẫu, rồi chạy lại.")
                return counts
            if not self._search_ready(shot):
                self.log("Chưa thấy ô nhập UID. Hãy mở tab Add New trong game rồi bấm Bắt đầu.")
                return counts
            for index, uid in enumerate(ids, start=1):
                self._check()
                if counts["da_nhan_qua"] >= self.max_gifts:
                    self.log(f"Đủ {self.max_gifts} quà, dừng.")
                    break
                self.log(f"[{index}/{len(ids)}] UID {uid} — đã nhận {counts['da_nhan_qua']}/{self.max_gifts}")
                started = time.time()
                try:
                    status, note, ready = self.process_one(uid)
                except Stopped:
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
        shot = self._shot()
        search = self.finder.find(shot, "search")
        if search is None:
            return "loi_timeout", "không thấy ô tìm UID", False

        field_x, field_y = field_point(shot, search)
        self.adb.tap(field_x, field_y)
        self.adb.clear_text()
        self.adb.input_text(uid)
        self.adb.tap(search.x, search.y)
        self._pause(0.4, 0.45)

        shot = self._shot()
        found = self._result_add(shot)
        if found is None:
            self.finder.find(shot, "missing_id")
            return "id_sai", "không thấy người chơi", self.finder.find(shot, "search") is not None

        self.adb.tap(*avatar_point(shot, found))
        self._pause(0.08, 0.12)
        shot = self._shot()
        visit = self.finder.find(shot, "visit", scales=(1.0, 1.05))
        if visit is None:
            return "loi_timeout", "không thấy nút Visit", self.finder.find(shot, "search") is not None
        self.adb.tap(visit.x, visit.y)
        self._pause(0.55, 0.65)

        shot = self._house_shot()
        if shot is None:
            return "loi_timeout", "không vào được nhà", True
        if self.finder.find(shot, "gift", scales=(1.0, 1.05)) is not None or self.finder.find(shot, "select") is not None:
            return self._collect_gift(shot)
        self._tap_close(shot)
        return "khong_co_qua", "vào nhà, không thấy hộp quà", True

    def _house_shot(self):
        """Một ảnh sau khi nhà load. Nếu vẫn còn nút Visit thì bấm lại một lần."""
        shot = self._shot()
        visit = self.finder.find(shot, "visit", scales=(1.0, 1.05))
        if visit is None:
            return shot
        self.adb.tap(visit.x, visit.y)
        self._pause(0.7, 0.8)
        shot = self._shot()
        if self.finder.find(shot, "visit", scales=(1.0, 1.05)) is not None:
            return None
        return shot

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
            self.adb.tap(gift.x, gift.y)
            self._pause(0.25, 0.35)
        if not self._wait_tap("select", timeout=3):
            gift = self.finder.find(self._shot(), "gift")
            if gift is not None:
                self.adb.tap(gift.x, gift.y)
            if not self._wait_tap("select", timeout=2):
                self._back_to_search()
                return "loi_timeout", "đã thấy hộp quà nhưng không thấy nút Select", self._search_ready(self._shot())
        if not self._wait_tap("ok", timeout=3):
            self._back_to_search()
            return "loi_timeout", "đã bấm Select nhưng không thấy nút OK", self._search_ready(self._shot())
        ready = self._back_to_search()
        return "da_nhan_qua", "đã bấm Select và OK", ready

    def _result_add(self, shot):
        """Nút Add của hàng Results, không phải gợi ý Players you may know."""
        header = self.finder.find(shot, "results")
        if header is None:
            return None
        height = shot.shape[0]
        return self.finder.find_below(shot, "add", int(header.y), int(header.y + 0.22 * height))

    def _wait_search(self, timeout: float):
        deadline = time.time() + timeout
        stable_since = None
        idle_since = None
        shot = self._shot()
        while time.time() < deadline:
            self._check()
            shot = self._shot()
            if self.finder.find(shot, "missing_id"):
                return shot
            if self._result_add(shot) is not None:
                idle_since = None
                if stable_since is None:
                    stable_since = time.time()
                elif time.time() - stable_since >= 0.25:
                    return shot
            else:
                stable_since = None
                if idle_since is None:
                    idle_since = time.time()
                elif time.time() - idle_since >= SEARCH_GIVE_UP:
                    return shot
            self._pause(0.12, 0.22)
        return shot

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

    def _wait_house(self, timeout: float) -> str:
        """Thấy nút đóng của nhà thì chỉ tìm hộp quà thêm `timeout` giây."""
        house_since = None
        hard_stop = time.time() + 8
        visit_taps = 0
        while time.time() < hard_stop:
            self._check()
            shot = self._shot()
            gift = self.finder.find(shot, "gift")
            if gift is not None:
                self.adb.tap(gift.x, gift.y)
                self._pause(*TAP_DELAY)
                return "gift"
            if self.finder.find(shot, "select"):
                return "gift"
            visit = self.finder.find(shot, "visit")
            if visit is not None and visit_taps < 2:
                self.adb.tap(visit.x, visit.y)
                visit_taps += 1
                house_since = None
                self._pause(0.2, 0.35)
                continue
            in_house = (
                self.finder.find(shot, "search") is None
                and self.finder.find(shot, "close") is not None
                and visit is None
            )
            if not in_house:
                house_since = None
                self._pause(0.15, 0.28)
                continue
            if house_since is None:
                house_since = time.time()
            elif time.time() - house_since >= timeout:
                return "no_gift"
            self._pause(0.15, 0.25)
        return "timeout"

    def _wait_tap(self, name: str, timeout: float) -> bool:
        deadline = time.time() + timeout
        taps = 0
        while time.time() < deadline:
            self._check()
            shot = self._shot()
            hit = self.finder.find(shot, name)
            if hit is not None and taps < 2:
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
        deadline = time.time() + 6
        taps = 0
        while time.time() < deadline and taps < 4:
            self._check()
            shot = self._shot()
            if self._search_ready(shot):
                return True
            select = self.finder.find(shot, "select")
            ok = self.finder.find(shot, "ok")
            visit = self.finder.find(shot, "visit")
            close = self.finder.find(shot, "close")
            search = self.finder.find(shot, "search")
            if select is not None:
                self.adb.tap(select.x, select.y)
            elif ok is not None:
                self.adb.tap(ok.x, ok.y)
            elif visit is not None:
                self._dismiss_visit_popup(shot)
            elif close is not None and search is None:
                self.adb.tap(close.x, close.y)
            taps += 1
            self._pause(0.2, 0.35)
        return self._search_ready(self._shot())

    def _dismiss_visit_popup(self, shot) -> None:
        # Nút Back của Android không đóng popup này. Bấm vùng tối bên phải.
        height, width = shot.shape[:2]
        self.adb.tap(int(width * 0.69), int(height * 0.70))

    def _leave_search_overlays(self) -> None:
        shot = self._shot()
        if self.finder.find(shot, "visit") is not None:
            self._dismiss_visit_popup(shot)
            self._pause(0.15, 0.3)

    def _search_ready(self, shot) -> bool:
        return (
            self.finder.find(shot, "search") is not None
            and self.finder.find(shot, "visit") is None
            and self.finder.find(shot, "select") is None
            and self.finder.find(shot, "ok") is None
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

    def _summary(self, counts: dict[str, int]) -> None:
        parts = [f"{LABELS[key]}: {counts[key]}" for key in LABELS]
        self.log("Tổng kết — " + ", ".join(parts))

