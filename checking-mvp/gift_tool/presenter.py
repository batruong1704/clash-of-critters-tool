"""Presenter: nhận thao tác trên cửa sổ, kiểm tra ô nhập, gọi model, đẩy chữ lên view."""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path

from gift_tool.flow import LABELS, LOG_INDENT, MAX_GIFTS
from gift_tool.paths import LOGS
from gift_tool.model import (
    FISHING_CASTS_DEFAULT,
    FISHING_CASTS_MAX,
    FISHING_MULTIPLIERS,
    SCAN_COUNT_DEFAULT,
    SCAN_COUNT_MAX,
    UID_MAX_LEN,
    UID_MIN_LEN,
    ToolModel,
    parse_ids,
    scan_ids,
)
from gift_tool.view import MainView, fish_level


def fish_step(message: str) -> str | None:
    """Bước đang làm, hiện dưới các con số. Rỗng khi dòng chỉ là kết quả."""
    if "quăng cần" in message or message.startswith("Chưa thấy cần"):
        return "Đang quăng cần"
    rules = (
        ("Đang ở sân", "Đang vào Pinball"),
        ("Ở Pinball", "Đang tìm Fishing Contest"),
        ("Vào Fishing Contest", "Đang vào câu cá"),
        ("Chờ cá", "Đang chờ cá cắn"),
        ("Cá cắn", "Đang bấm Reel it in"),
        ("Hệ số đang", "Đang đổi hệ số"),
        ("Không đọc được hệ số", "Đang đổi hệ số"),
        ("Trượt", "Đang chỉnh cú bấm"),
        ("Trúng vùng", "Đã trúng vùng vàng"),
        ("Thất bại", "Thất bại"),
        ("Câu được cá", "Đã câu được cá"),
        ("Không thấy màn kết quả", "Đang đọc kết quả"),
        ("Có popup", "Có popup chen vào"),
        ("Chưa nhận ra", "Chưa nhận ra màn hình"),
        ("Đang câu dở", "Câu nốt lượt này rồi dừng"),
        ("Tự câu cá", "Đang chuẩn bị"),
    )
    for prefix, step in rules:
        if message.startswith(prefix):
            return step
    return None


class Presenter:
    def __init__(self, root):
        self.mode = "fish"
        self.running = False
        self._loading = False
        self.stop = threading.Event()
        self.worker: threading.Thread | None = None
        self.model = ToolModel()
        self._status_step = "Sẵn sàng"
        self._status_stats = [f"Dừng sau {MAX_GIFTS} quà"]
        self._settings_path = LOGS / "cua-so.json"
        self._loading = True
        self.view = MainView(
            root,
            self,
            max_gifts=MAX_GIFTS,
            scan_default=SCAN_COUNT_DEFAULT,
            scan_max=SCAN_COUNT_MAX,
            fish_default=FISHING_CASTS_DEFAULT,
            fish_max=FISHING_CASTS_MAX,
            fish_multipliers=FISHING_MULTIPLIERS,
        )
        self._load_settings()
        self._loading = False
        self.view.watch_form(self.on_option_changed)
        self.view.bind_close(self._save_settings)
        self._ready_status()
        self.refresh_action()

    def __getattr__(self, name: str):
        """Self-test vẫn đọc nút và trang trên cửa sổ qua App."""
        view = self.__dict__.get("view")
        if view is not None and hasattr(view, name):
            return getattr(view, name)
        raise AttributeError(name)

    def select(self, mode: str) -> None:
        if self.running:
            return
        self.mode = mode
        self.view.show_mode(mode)
        self._ready_status()
        self.refresh_action()
        if not self._loading:
            self._save_settings()

    def on_form_changed(self) -> None:
        if self.running or self._loading:
            return
        self.refresh_action()

    def on_option_changed(self) -> None:
        self.on_form_changed()
        if not self.running and not self._loading:
            self._save_settings()

    def on_theme(self) -> None:
        if not self._loading:
            self._save_settings()

    def on_escape(self) -> None:
        if self.running:
            self.request_stop()

    def refresh_action(self) -> None:
        if self.running:
            return
        self.view.set_action(self._action_label())
        if self.mode == "list":
            _ids, summary = self._id_summary(self.view.gift_ids_text())
            self.view.set_id_summary(summary)

    def show_list(self) -> None:
        self.select("list")

    def show_scan(self) -> None:
        self.select("scan")

    def show_rally(self) -> None:
        self.select("rally")

    def load_file(self) -> None:
        path = self.view.choose_text_file()
        if not path:
            return
        content = Path(path).read_text(encoding="utf-8", errors="replace")
        self.view.set_ids(content)
        self.on_form_changed()
        self.write(f"Đã nạp {path}")

    def start(self) -> None:
        if self.worker and self.worker.is_alive():
            return
        ids, bad, duplicated = parse_ids(self.view.gift_ids_text())
        if bad:
            self.write("Bỏ qua dòng không phải UID: " + ", ".join(bad[:8]), note=True)
        if duplicated:
            self.write(f"Bỏ {duplicated} ID trùng.", note=True)
        if not ids:
            self.write("Chưa có UID hợp lệ.")
            return
        self._begin(ids)

    def run_current(self) -> None:
        if self.mode == "fish":
            self.start_fishing()
        elif self.mode == "rally":
            self.start_rally()
        elif self.mode == "scan":
            self.start_scan()
        else:
            self.start()

    def start_scan(self) -> None:
        if self.worker and self.worker.is_alive():
            return
        raw = "".join(self.view.scan_start_text().split())
        if not (raw.isdigit() and UID_MIN_LEN <= len(raw) <= UID_MAX_LEN):
            self.write("ID đầu phải là số, dài 4 đến 15 chữ số.")
            return
        try:
            count = int(self.view.scan_count_text())
        except ValueError:
            self.write("Số lần quét không hợp lệ.")
            return
        count = min(SCAN_COUNT_MAX, max(1, count))
        ids = scan_ids(raw, count)
        if not ids:
            self.write("Không tạo được UID để quét.")
            return
        if len(ids) < count:
            self.write(f"Chỉ quét tới {ids[-1]} vì UID dài quá 15 chữ số.", note=True)
        self.write(f"Quét nối tiếp {len(ids)} ID, từ {ids[0]} đến {ids[-1]}.")
        self._begin(ids)

    def start_rally(self) -> None:
        if self.worker and self.worker.is_alive():
            return
        self.stop.clear()
        self.view.clear_detail()
        self.view.clear_results()
        self._lock()
        self._rally_asked = 0
        self._status("Đang nối máy", ["Đã xin 0"])
        self.worker = threading.Thread(target=self._run_rally, daemon=True)
        self.worker.start()

    def start_fishing(self) -> None:
        if self.worker and self.worker.is_alive():
            return
        try:
            casts = int(self.view.fish_casts_text())
        except ValueError:
            self.write("Số lượt câu phải là số nguyên dương.")
            return
        if not 1 <= casts <= FISHING_CASTS_MAX:
            self.write(f"Số lượt câu từ 1 đến {FISHING_CASTS_MAX}.")
            return
        text = self.view.fish_multiplier_text().strip().lower().lstrip("x") or "1"
        if text not in FISHING_MULTIPLIERS:
            self.write(f"Hệ số chỉ nhận một trong: {', '.join(FISHING_MULTIPLIERS)}.")
            return
        self.view.set_fish_multiplier(text)
        self._save_settings()
        self.stop.clear()
        self.view.clear_overview()
        self.view.clear_detail()
        self._lock()
        self._status("Đang nối máy", [f"Lượt 0/{casts}", "Được 0", "Thất bại 0", "Gold 0", "Rod ?"])
        self.worker = threading.Thread(target=self._run_fishing, args=(casts, int(text)), daemon=True)
        self.worker.start()

    def request_stop(self) -> None:
        if not self.running or self.stop.is_set():
            return
        self.stop.set()
        if self.mode == "fish":
            self.write("Nếu đang câu dở thì câu nốt lượt này rồi dừng.")
            self.view.set_fish_hold(True)
        else:
            self.write("Sẽ dừng sau bước hiện tại.")
            self._status("Sẽ dừng sau bước hiện tại.")

    def capture_only(self) -> None:
        threading.Thread(target=self._capture_only, daemon=True).start()

    def preview(self) -> None:
        threading.Thread(target=self._preview, daemon=True).start()

    def write(self, message: str, *, note: bool = False) -> None:
        if note:
            message = f"{LOG_INDENT}{message}"
        self.view.append_log(message)
        self._note_gift_row(message)

    def write_detail(self, message: str) -> None:
        self.view.append_detail(message)

    def _begin(self, ids: list[str]) -> None:
        self.stop.clear()
        self.view.clear_detail()
        self.view.clear_results()
        self._lock()
        self._gift_got = f"0/{MAX_GIFTS}"
        self._gift_index = "0"
        self._gift_total = str(len(ids))
        self._gift_pinball = "0"
        self._status("Đang nối máy", self._gift_stats())
        self.worker = threading.Thread(target=self._run, args=(ids,), daemon=True)
        self.worker.start()

    def _lock(self) -> None:
        self.running = True
        self.view.set_locked(True)

    def _unlock(self) -> None:
        finished = not self.stop.is_set()

        def apply() -> None:
            self.running = False
            self.view.set_locked(False)
            self.refresh_action()
            if finished:
                self.view.play_done()

        self.view.invoke(apply)

    def _run(self, ids: list[str]) -> None:
        try:
            adb, serial = self.model.open_adb()
            self.write(f"Đã nối {serial}")
            self.view.set_device(serial)

            def log(message: str) -> None:
                self.write(message)
                self._note_gift_line(message)

            counts = self.model.run_gifts(adb, ids, log, self.stop, self._gift_detail)
            summary = (
                f"Xong. Quà {counts['da_nhan_qua']}/{MAX_GIFTS}, pinball {counts.get('pinball', 0)}. "
                + ", ".join(f"{LABELS[key]} {counts[key]}" for key in LABELS)
            )
            self._status(summary, [f"Quà {counts['da_nhan_qua']}/{MAX_GIFTS}", f"Pinball {counts.get('pinball', 0)}"])
            self.view.toast("Đã dừng." if self.stop.is_set() else "Hoàn tất.")
        except Exception as exc:
            self.write(f"Lỗi: {exc}")
            self._status("Dừng vì lỗi")
            self.view.toast("Dừng vì lỗi.")
        finally:
            self._unlock()

    def _run_rally(self) -> None:
        try:
            adb, serial = self.model.open_adb()
            self.write(f"Đã nối {serial}")
            self.view.set_device(serial)

            def log(message: str) -> None:
                self.view.append_log(message)
                if "xin vào" in message.lower():
                    self._rally_asked += 1
                    self.view.add_result((str(self._rally_asked), message.split(".", 1)[0], ""))
                step = message.split(".", 1)[0]
                self._status(step, [f"Đã xin {self._rally_asked}"])

            counts = self.model.run_rally(adb, log, self.stop)
            self._status(f"Xong. Đã xin {counts['xin']} rally.", [f"Đã xin {counts['xin']}"])
            self.view.toast("Đã dừng." if self.stop.is_set() else "Hoàn tất.")
        except Exception as exc:
            self.write(f"Lỗi: {exc}")
            self._status("Dừng vì lỗi")
            self.view.toast("Dừng vì lỗi.")
        finally:
            self._unlock()

    def _run_fishing(self, casts: int, multiplier: int) -> None:
        try:
            adb, serial, fish_runner = self.model.open_fishing()
            self.write_detail(f"Đã nối {serial}")
            self.view.set_device(serial)

            def log(message: str) -> None:
                self.view.append_log(message, fish_level(message))
                self._note_fish_row(message)
                step = fish_step(message)
                if step:
                    self._status(step)

            def show(stats) -> None:
                rods = "?" if stats.rods is None else stats.rods
                self._status(
                    self._status_step,
                    [
                        f"Lượt {stats.casts}/{casts}",
                        f"Được {stats.caught}",
                        f"Thất bại {stats.failed}",
                        f"Gold {stats.gold}",
                        f"Rod {rods}",
                    ],
                )

            stats = fish_runner(adb, log, self.stop, casts, multiplier, on_stats=show).run()
            show(stats)
            self.view.toast("Đã dừng." if self.stop.is_set() else "Hoàn tất.")
        except Exception as exc:
            self.write(f"Lỗi: {exc}")
            self._status("Dừng vì lỗi")
            self.view.toast("Dừng vì lỗi.")
        finally:
            self._unlock()

    def _capture_only(self) -> None:
        try:
            result = self.model.capture()
            self.view.set_device(result.serial)
            self.write(f"Đã chụp {result.serial}: {result.width}x{result.height} → {result.path}")
            self.view.toast("Chụp thử: đã lưu ảnh màn hình.")
        except Exception as exc:
            self.write(f"Lỗi chụp thử: {exc}")
            self.view.toast("Chụp thử không xong.")

    def _preview(self) -> None:
        try:
            result = self.model.preview()
            lines = [f"Kiểm tra trên {result.serial}, {result.width}x{result.height}"]
            for check in result.checks:
                mark = "thấy" if check.found else "không"
                lines.append(f"{LOG_INDENT}{check.name}: {check.score:.2f} ({mark})")
            lines.append(f"Ảnh khoanh nút: {result.path}")
            self.view.set_device(result.serial)
            self.write("\n".join(lines))
            self.view.toast("Kiểm tra nút: đã lưu ảnh khoanh.")
            self.view.invoke(lambda: os.startfile(result.path))
        except Exception as exc:
            self.write(f"Lỗi kiểm tra: {exc}")
            self.view.toast("Kiểm tra nút không xong.")

    def _status(self, step: str, stats: list[str] | None = None) -> None:
        self._status_step = step
        if stats is not None:
            self._status_stats = list(stats)
        self.view.set_status(self._status_step, self._status_stats)

    def _ready_status(self) -> None:
        if self.mode == "fish":
            self._status("Sẵn sàng", ["Dừng sau lượt đang câu, hoặc khi đủ lượt, hết rod"])
        elif self.mode == "rally":
            self._status("Sẵn sàng", ["Chạy đến khi dừng"])
        else:
            self._status("Sẵn sàng", [f"Dừng sau {MAX_GIFTS} quà"])

    def _action_label(self) -> str:
        if self.mode == "fish":
            casts = self.view.fish_casts_text().strip()
            mult = self.view.fish_multiplier_text().strip().lower().lstrip("x") or "1"
            if casts.isdigit() and 1 <= int(casts) <= FISHING_CASTS_MAX and mult in FISHING_MULTIPLIERS:
                return f"Câu {int(casts)} lượt · x{mult}"
            return "Câu cá"
        if self.mode == "rally":
            return "Join rally đến khi dừng"
        if self.mode == "scan":
            count = self.view.scan_count_text().strip()
            if count.isdigit() and int(count) >= 1:
                return f"Quét {min(int(count), SCAN_COUNT_MAX)} ID"
            return "Quét"
        ids, _summary = self._id_summary(self.view.gift_ids_text())
        if ids:
            return f"Nhận quà {len(ids)} UID"
        return "Nhận quà"

    def _id_summary(self, text: str) -> tuple[list[str], str]:
        ids, bad, duplicated = parse_ids(text)
        if not ids and not bad and not duplicated:
            return ids, "Chưa có UID hợp lệ"
        parts = [f"{len(ids)} UID hợp lệ" if ids else "Chưa có UID hợp lệ"]
        if bad:
            parts.append(f"bỏ {len(bad)} dòng")
        if duplicated:
            parts.append(f"{duplicated} trùng")
        return ids, " · ".join(parts)

    def _gift_stats(self) -> list[str]:
        return [
            f"Quà {self._gift_got}",
            f"UID {self._gift_index}/{self._gift_total}",
            f"Pinball {self._gift_pinball}",
        ]

    def _note_gift_line(self, message: str) -> None:
        if not (message.startswith("[") and "đã nhận" in message and "]" in message):
            return
        head = message.split("]", 1)[0][1:]
        if "/" in head:
            index, total = head.split("/", 1)
            self._gift_index = index.strip()
            self._gift_total = total.strip()
        got = message.split("đã nhận", 1)[1].split(",")[0].strip()
        self._gift_got = got
        if "pinball" in message:
            self._gift_pinball = message.split("pinball", 1)[1].strip()
        uid = ""
        if "UID" in message:
            uid = message.split("UID", 1)[1].split("—", 1)[0].strip()
        self._status(f"UID {uid}" if uid else self._status_step, self._gift_stats())

    def _gift_detail(self, message: str) -> None:
        self.write_detail(message)
        body = message.strip()
        if "]" in body:
            body = body.split("]", 1)[1].strip()
        if body:
            self._status(body, self._gift_stats())

    def check_connection(self) -> None:
        threading.Thread(target=self._check_connection, daemon=True).start()

    def _check_connection(self) -> None:
        try:
            _adb, serial = self.model.open_adb()
        except Exception as exc:
            self.view.set_offline()
            self.view.toast(f"Chưa nối: {exc}")
            return
        self.view.set_device(serial)
        self.view.toast(f"Đã nối {serial}")

    def open_logs(self) -> None:
        LOGS.mkdir(parents=True, exist_ok=True)
        os.startfile(LOGS)
        self.view.toast("Mở thư mục log.")

    def _note_fish_row(self, message: str) -> None:
        if message.startswith("Lượt ") and "quăng" in message:
            number = message.split(":", 1)[0].split()[1].split("/")[0]
            self._fish_turn = number
            self._fish_iid = self.view.add_result((number, "Đang chạy…", ""))
        elif message.startswith("Câu được cá"):
            gold = "–"
            if "+" in message and "Gold" in message:
                gold = "+" + message.split("+", 1)[1].split()[0].rstrip(".")
            self.view.finish_result(getattr(self, "_fish_iid", ""), (getattr(self, "_fish_turn", ""), "Thành công", gold), "ok")
        elif message.startswith("Thất bại"):
            self.view.finish_result(getattr(self, "_fish_iid", ""), (getattr(self, "_fish_turn", ""), "Thất bại", "–"), "fail")

    def _note_gift_row(self, message: str) -> None:
        if self.mode == "fish":
            return
        if message.startswith("[") and "UID" in message:
            uid = message.split("UID", 1)[1].split("—", 1)[0].strip()
            self._gift_uid = uid
            self._gift_iid = self.view.add_result((uid, "Đang chạy…", ""))
            return
        text = message.strip()
        for label in LABELS.values():
            if text.startswith(label):
                tone = "ok" if label == "đã nhận quà" else "fail"
                self.view.finish_result(getattr(self, "_gift_iid", ""), (getattr(self, "_gift_uid", ""), label, text), tone)
                return

    def _load_settings(self) -> None:
        if not self._settings_path.exists():
            return
        try:
            data = json.loads(self._settings_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        casts = str(data.get("casts", "")).strip()
        mult = str(data.get("multiplier", "")).strip().lower().lstrip("x")
        if casts.isdigit() and 1 <= int(casts) <= FISHING_CASTS_MAX:
            self.view.set_fish_casts(casts)
        if mult in FISHING_MULTIPLIERS:
            self.view.set_fish_multiplier(mult)
        mode = data.get("mode")
        if mode in ("list", "scan", "rally", "fish"):
            self.select(mode)
        if "autoscroll" in data:
            self.view.auto_var.set(bool(data["autoscroll"]))
            self.view._toggle_auto()
        if "debug" in data:
            self.view.debug_var.set(bool(data["debug"]))
            self.view._toggle_debug()
        theme = data.get("theme")
        if theme in ("light", "dark", "system"):
            self.view.set_theme(theme)

    def _save_settings(self) -> None:
        data = {
            "mode": self.mode,
            "casts": self.view.fish_casts_text().strip(),
            "multiplier": self.view.fish_multiplier_text().strip().lower().lstrip("x") or "1",
            "theme": self.view.theme_mode,
            "autoscroll": bool(self.view.auto_var.get()),
            "debug": bool(self.view.debug_var.get()),
        }
        try:
            self._settings_path.parent.mkdir(parents=True, exist_ok=True)
            self._settings_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        except OSError:
            return
