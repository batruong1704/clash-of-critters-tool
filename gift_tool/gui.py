"""Cửa sổ dán UID, bấm Bắt đầu / Dừng, xem log tổng quan và log từng bước."""

from __future__ import annotations

import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, ttk

from gift_tool.adb_client import AdbClient
from gift_tool.flow import LABELS, MAX_GIFTS, Runner
from gift_tool.paths import LOGS
from gift_tool.vision import Finder, draw_hits, imwrite

WINDOW_WIDTH = 680
COMPACT_HEIGHT = 520
DETAIL_HEIGHT = 820
OVERVIEW_LOG_LINES = 5
DETAIL_LOG_LINES = 16
HINT_WRAP = 640


def parse_ids(text: str) -> tuple[list[str], list[str], int]:
    """Trả UID hợp lệ, dòng lỗi, và số ID trùng đã bỏ. Giữ thứ tự lần gặp đầu."""
    good, bad = [], []
    seen: set[str] = set()
    duplicated = 0
    chunks = text.replace(",", "\n").replace(";", "\n").splitlines()
    for chunk in chunks:
        # Dấu cách dính khi dán từ game hoặc bảng tính làm ADB gõ sai UID.
        token = "".join(chunk.split())
        if not token:
            continue
        if not (token.isdigit() and 4 <= len(token) <= 15):
            bad.append(token)
            continue
        if token in seen:
            duplicated += 1
            continue
        seen.add(token)
        good.append(token)
    return good, bad, duplicated


class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Nhận quà MVP — Clash of Critters")
        self.root.minsize(WINDOW_WIDTH, COMPACT_HEIGHT)
        self.root.geometry(f"{WINDOW_WIDTH}x{COMPACT_HEIGHT}")
        self.stop = threading.Event()
        self.worker: threading.Thread | None = None
        self.finder = Finder()
        self.detail_open = False

        frame = ttk.Frame(root, padding=12)
        frame.pack(fill="both", expand=True)

        ttk.Label(
            frame,
            text="Mở sẵn tab Add New (ô nhập UID). Lần đầu chỉ dán 1–2 ID. Nếu ADB đang tắt, bấm Chụp thử sẽ bật ADB và khởi động lại emulator một lần, rồi bạn mở lại game.",
            wraplength=HINT_WRAP,
        ).pack(anchor="w")

        self.device_var = tk.StringVar(value="Chưa kết nối emulator")
        ttk.Label(frame, textvariable=self.device_var).pack(anchor="w", pady=(6, 6))

        buttons = ttk.Frame(frame)
        buttons.pack(anchor="w")
        ttk.Button(buttons, text="Chụp thử", command=self.capture_only).pack(side="left")
        ttk.Button(buttons, text="Kiểm tra nút", command=self.preview).pack(side="left", padx=6)

        ttk.Label(frame, text="Danh sách UID, mỗi dòng một ID").pack(anchor="w", pady=(10, 2))
        self.ids = tk.Text(frame, height=8, font=("Consolas", 11))
        self.ids.pack(fill="x")

        run_row = ttk.Frame(frame)
        run_row.pack(anchor="w", pady=(8, 0))
        ttk.Button(run_row, text="Nạp file txt", command=self.load_file).pack(side="left")
        self.start_btn = ttk.Button(run_row, text="Bắt đầu", command=self.start)
        self.start_btn.pack(side="left", padx=(12, 0))
        self.stop_btn = ttk.Button(run_row, text="Dừng", command=self.request_stop, state="disabled")
        self.stop_btn.pack(side="left", padx=6)
        self.detail_btn = ttk.Button(run_row, text="Xem chi tiết log", command=self.toggle_detail)
        self.detail_btn.pack(side="left", padx=6)

        self.progress = tk.StringVar(value="Sẵn sàng")
        ttk.Label(frame, textvariable=self.progress).pack(anchor="w", pady=(8, 2))

        overview = ttk.LabelFrame(frame, text="Log tổng quan", padding=4)
        overview.pack(fill="x", pady=(4, 0))
        self.log_box = tk.Text(
            overview, height=OVERVIEW_LOG_LINES, state="disabled", font=("Consolas", 10), wrap="word"
        )
        self.log_box.pack(fill="x")

        self.detail_frame = ttk.LabelFrame(frame, text="Log chi tiết", padding=4)
        self.detail_box = tk.Text(
            self.detail_frame, height=DETAIL_LOG_LINES, state="disabled", font=("Consolas", 10), wrap="word"
        )
        self.detail_box.pack(fill="both", expand=True)

    def load_file(self):
        path = filedialog.askopenfilename(filetypes=[("Text", "*.txt"), ("Tất cả", "*.*")])
        if not path:
            return
        content = Path(path).read_text(encoding="utf-8", errors="replace")
        self.ids.delete("1.0", "end")
        self.ids.insert("1.0", content)
        self.write(f"Đã nạp {path}")

    def start(self):
        if self.worker and self.worker.is_alive():
            return
        ids, bad, duplicated = parse_ids(self.ids.get("1.0", "end"))
        if bad:
            self.write("Bỏ qua dòng không phải UID: " + ", ".join(bad[:8]))
        if duplicated:
            self.write(f"Bỏ {duplicated} ID trùng.")
        if not ids:
            self.write("Chưa có UID hợp lệ.")
            return
        self.stop.clear()
        self._clear(self.detail_box)
        self.start_btn.configure(state="disabled")
        self.stop_btn.configure(state="normal")
        self.progress.set(f"Đang chạy 0/{MAX_GIFTS} quà")
        self.worker = threading.Thread(target=self._run, args=(ids,), daemon=True)
        self.worker.start()

    def toggle_detail(self):
        if self.detail_open:
            self.detail_frame.pack_forget()
            self.detail_open = False
            self.detail_btn.configure(text="Xem chi tiết log")
            self.root.minsize(WINDOW_WIDTH, COMPACT_HEIGHT)
            self.root.geometry(f"{self.root.winfo_width()}x{COMPACT_HEIGHT}")
            return
        self.detail_frame.pack(fill="both", expand=True, pady=(8, 0))
        self.detail_open = True
        self.detail_btn.configure(text="Ẩn chi tiết log")
        self.root.minsize(WINDOW_WIDTH, DETAIL_HEIGHT)
        width = max(self.root.winfo_width(), WINDOW_WIDTH)
        height = max(self.root.winfo_height(), DETAIL_HEIGHT)
        self.root.geometry(f"{width}x{height}")
        self.detail_box.see("end")

    def request_stop(self):
        self.stop.set()
        self.write("Sẽ dừng sau bước hiện tại.")

    def capture_only(self):
        threading.Thread(target=self._capture_only, daemon=True).start()

    def preview(self):
        threading.Thread(target=self._preview, daemon=True).start()

    def _run(self, ids: list[str]):
        try:
            adb = AdbClient()
            serial = adb.ensure_device()
            self.write(f"Đã nối {serial}")
            self.root.after(0, lambda s=serial: self.device_var.set(f"Đã nối {s}"))

            def log(message: str):
                self.write(message)
                if message.startswith("[") and "đã nhận" in message:
                    self.root.after(0, lambda m=message: self.progress.set(m))

            runner = Runner(adb, self.finder, log, self.stop, self.write_detail)
            counts = runner.run(ids)
            summary = (
                f"Xong. Quà {counts['da_nhan_qua']}/{MAX_GIFTS}. "
                + ", ".join(f"{LABELS[key]} {counts[key]}" for key in LABELS)
            )
            self.root.after(0, lambda text=summary: self.progress.set(text))
        except Exception as exc:
            self.write(f"Lỗi: {exc}")
            self.root.after(0, lambda: self.progress.set("Dừng vì lỗi"))
        finally:
            self.root.after(0, lambda: self.start_btn.configure(state="normal"))
            self.root.after(0, lambda: self.stop_btn.configure(state="disabled"))

    def _capture_only(self):
        try:
            adb = AdbClient()
            serial = adb.ensure_device()
            shot = adb.screenshot()
            path = LOGS / "chup-thu.png"
            imwrite(path, shot)
            height, width = shot.shape[:2]
            self.write(f"Đã chụp {serial}: {width}x{height} → {path}")
        except Exception as exc:
            self.write(f"Lỗi chụp thử: {exc}")

    def _preview(self):
        try:
            adb = AdbClient()
            serial = adb.ensure_device()
            shot = adb.screenshot()
            hits = []
            lines = [f"Kiểm tra trên {serial}, {shot.shape[1]}x{shot.shape[0]}"]
            for name in ("search", "add", "visit", "gift", "select", "ok", "close", "missing_id"):
                hit = self.finder.locate(shot, name)
                threshold = self.finder.templates[name][1]["threshold"]
                mark = "thấy" if hit.score >= threshold and hit.w else "không"
                lines.append(f"  {name}: {hit.score:.2f} ({mark})")
                if hit.w and hit.score >= threshold:
                    hits.append(hit)
            path = LOGS / "kiem-tra.png"
            imwrite(path, draw_hits(shot, hits))
            lines.append(f"Ảnh khoanh nút: {path}")
            self.write("\n".join(lines))
            self.root.after(0, lambda: __import__("os").startfile(path))
        except Exception as exc:
            self.write(f"Lỗi kiểm tra: {exc}")

    def write(self, message: str):
        self._append(self.log_box, message)

    def write_detail(self, message: str):
        self._append(self.detail_box, message)

    def _append(self, box: tk.Text, message: str):
        def append():
            box.configure(state="normal")
            box.insert("end", message + "\n")
            box.see("end")
            box.configure(state="disabled")

        self.root.after(0, append)

    def _clear(self, box: tk.Text):
        def clear():
            box.configure(state="normal")
            box.delete("1.0", "end")
            box.configure(state="disabled")

        self.root.after(0, clear)


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()
