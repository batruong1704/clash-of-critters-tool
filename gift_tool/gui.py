"""Cửa sổ dán UID, bấm Bắt đầu / Dừng, xem tiến độ."""

from __future__ import annotations

import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, ttk

from gift_tool.adb_client import AdbClient
from gift_tool.flow import LABELS, Runner
from gift_tool.paths import LOGS
from gift_tool.vision import Finder, draw_hits, imwrite


def parse_ids(text: str) -> tuple[list[str], list[str]]:
    good, bad = [], []
    chunks = text.replace(",", "\n").replace(";", "\n").splitlines()
    for chunk in chunks:
        token = chunk.strip()
        if not token:
            continue
        if token.isdigit() and 4 <= len(token) <= 15:
            good.append(token)
        else:
            bad.append(token)
    return good, bad


class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Nhận quà MVP — Clash of Critters")
        self.root.minsize(640, 560)
        self.stop = threading.Event()
        self.worker: threading.Thread | None = None
        self.finder = Finder()

        frame = ttk.Frame(root, padding=12)
        frame.pack(fill="both", expand=True)

        ttk.Label(
            frame,
            text="Mở sẵn tab Add New (ô nhập UID). Lần đầu chỉ dán 1–2 ID. Nếu ADB đang tắt, bấm Chụp thử sẽ bật ADB và khởi động lại emulator một lần, rồi bạn mở lại game.",
            wraplength=600,
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

        row = ttk.Frame(frame)
        row.pack(fill="x", pady=8)
        ttk.Button(row, text="Nạp file txt", command=self.load_file).pack(side="left")
        ttk.Label(row, text="Dừng sau số quà").pack(side="left", padx=(12, 4))
        self.max_gifts = tk.Spinbox(row, from_=1, to=20, width=5)
        self.max_gifts.delete(0, "end")
        self.max_gifts.insert(0, "20")
        self.max_gifts.pack(side="left")

        run_row = ttk.Frame(frame)
        run_row.pack(anchor="w")
        self.start_btn = ttk.Button(run_row, text="Bắt đầu", command=self.start)
        self.start_btn.pack(side="left")
        self.stop_btn = ttk.Button(run_row, text="Dừng", command=self.request_stop, state="disabled")
        self.stop_btn.pack(side="left", padx=6)

        self.progress = tk.StringVar(value="Sẵn sàng")
        ttk.Label(frame, textvariable=self.progress).pack(anchor="w", pady=(8, 2))

        self.log_box = tk.Text(frame, height=14, state="disabled", font=("Consolas", 10))
        self.log_box.pack(fill="both", expand=True)

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
        ids, bad = parse_ids(self.ids.get("1.0", "end"))
        if bad:
            self.write("Bỏ qua dòng không phải UID: " + ", ".join(bad[:8]))
        if not ids:
            self.write("Chưa có UID hợp lệ.")
            return
        try:
            max_gifts = int(self.max_gifts.get())
        except ValueError:
            max_gifts = 20
        max_gifts = min(20, max(1, max_gifts))
        self.stop.clear()
        self.start_btn.configure(state="disabled")
        self.stop_btn.configure(state="normal")
        self.progress.set(f"Đang chạy 0/{max_gifts} quà")
        self.worker = threading.Thread(target=self._run, args=(ids, max_gifts), daemon=True)
        self.worker.start()

    def request_stop(self):
        self.stop.set()
        self.write("Sẽ dừng sau bước hiện tại.")

    def capture_only(self):
        threading.Thread(target=self._capture_only, daemon=True).start()

    def preview(self):
        threading.Thread(target=self._preview, daemon=True).start()

    def _run(self, ids: list[str], max_gifts: int):
        try:
            adb = AdbClient()
            serial = adb.ensure_device()
            self.write(f"Đã nối {serial}")
            self.root.after(0, lambda s=serial: self.device_var.set(f"Đã nối {s}"))

            def log(message: str):
                self.write(message)
                if message.startswith("[") and "đã nhận" in message:
                    self.root.after(0, lambda m=message: self.progress.set(m))

            runner = Runner(adb, self.finder, log, self.stop, max_gifts=max_gifts)
            counts = runner.run(ids)
            summary = (
                f"Xong. Quà {counts['da_nhan_qua']}/{max_gifts}. "
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
        def append():
            self.log_box.configure(state="normal")
            self.log_box.insert("end", message + "\n")
            self.log_box.see("end")
            self.log_box.configure(state="disabled")

        self.root.after(0, append)


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()
