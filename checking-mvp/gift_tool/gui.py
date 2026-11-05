"""Cửa sổ dán UID, bấm Bắt đầu / Dừng, xem log tổng quan và log từng bước."""

from __future__ import annotations

import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, ttk

import sv_ttk

from gift_tool.adb_client import AdbClient
from gift_tool.flow import LABELS, LOG_INDENT, MAX_GIFTS, Runner
from gift_tool.paths import LOGS
from gift_tool.vision import Finder, draw_hits, imwrite
from rally_tool.flow import Runner as RallyRunner

# Tool tự câu cá nằm ở fishing-event/ cạnh thư mục này. Chỉ nạp khi bấm chạy để thiếu thư mục đó không làm hỏng tab khác.
FISHING_DIR = Path(__file__).resolve().parent.parent.parent / "fishing-event"
FISHING_MULTIPLIERS = ("1", "2", "3", "5", "10", "20", "50", "100", "200")
FISHING_CASTS_DEFAULT = 10
FISHING_CASTS_MAX = 100000

WINDOW_WIDTH = 840
COMPACT_HEIGHT = 760
DETAIL_PANEL = 420
OPEN_WIDTH = WINDOW_WIDTH + DETAIL_PANEL
OVERVIEW_LOG_LINES = 10
DETAIL_LOG_LINES = 16
HINT_WRAP = 460
UID_BOX_LINES = 7
# Màu theo bảng của sv-ttk (Sun Valley, giao diện Windows 11) bản sáng.
APP_BG = "#fafafa"
CARD_BG = "#ffffff"
BORDER = "#e0e0e0"
ACCENT = "#005fb8"
# Font đặt tên sẵn trong sv-ttk. Riêng ô nhập UID và log dùng Consolas cho thẳng hàng.
FONT_TITLE = "SunValleySubtitleFont"
FONT_BODY_STRONG = "SunValleyBodyStrongFont"
FONT_CAPTION = "SunValleyCaptionFont"
ID_FONT = ("Consolas", 12)
UID_MIN_LEN = 4
UID_MAX_LEN = 15
SCAN_COUNT_DEFAULT = 100
SCAN_COUNT_MAX = 5000
# Nền trắng. Chữ đậm đủ tương phản ở cỡ 10. Xám chỉ dành cho bước phụ.
LOG_BG = "#ffffff"
LOG_FG = "#1f2328"
LOG_MUTED = "#5c6570"
LOG_OK = "#0e7a3d"
LOG_WARN = "#8a5a00"
LOG_BAD = "#b42318"
LOG_FONT = ("Consolas", 10)
OK_MARKS = ("đã nhận quà", "đã bấm select và ok", "quà, dừng", "xin vào", "câu được cá", "trúng", "thành công")
FISH_HINT = "Màn dọc. Đang ở sân, Pinball hay Fishing Contest đều được, tool tự đi tới màn câu. Không bấm vào emulator khi tool chạy."
GIFT_HINT = "Màn hình dọc. Tool tự mở tab Add New nếu đang ở sân hoặc Goldrush. Lần đầu chỉ chạy 1–2 UID."
RALLY_HINT = "Màn dọc. Đang ở sân hoặc trong Goldrush đều được. Ra khỏi mode thì bấm lại nút Goldrush. Chỉ bấm nút xanh, bỏ nút xám, không tạo rally."
BAD_MARKS = (
    "lỗi",
    "timeout",
    "không thấy ô",
    "không thấy nút",
    "không thấy lại",
    "chưa thấy lại",
    "chưa thấy ô",
    "chưa vào",
    "hết giờ",
    "hết nhịp",
    "emulator đang ngang",
    "chưa nhận ra",
    "không nhận ra",
    "hết rod",
    "không đổi được",
    "thất bại",
)
WARN_MARKS = (
    "trượt",
    "màn thưởng",
    "không thấy màn kết quả",
    "không rõ",
    "không thấy người chơi",
    "không có quà",
    "sân đứng yên",
    "id sai",
    "dưới ",
    "dừng",
    "bỏ ",
    "chỉ quét",
)


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
        if not (token.isdigit() and UID_MIN_LEN <= len(token) <= UID_MAX_LEN):
            bad.append(token)
            continue
        if token in seen:
            duplicated += 1
            continue
        seen.add(token)
        good.append(token)
    return good, bad, duplicated


def scan_ids(start: str, count: int) -> list[str]:
    """ID đầu, rồi cộng 1 cho mỗi lần quét. Giữ số chữ số ban đầu nếu có số 0 đứng trước."""
    width = len(start)
    first = int(start)
    ids = []
    for offset in range(count):
        uid = str(first + offset).zfill(width)
        if len(uid) > UID_MAX_LEN:
            break
        ids.append(uid)
    return ids


def fish_overview(message: str) -> list[str]:
    """Dòng hiện ở Tổng quan khi câu cá. Mỗi lượt một dòng, kết quả thụt vào. Rỗng khi dòng chỉ thuộc log chi tiết."""
    if message.startswith("Lượt "):
        number = message.split(":", 1)[0].split()[1].split("/")[0]
        return [f"Lượt {number}"]
    if message.startswith("Câu được cá"):
        if "+" in message and "Gold" in message:
            gold = message.split("+", 1)[1].split()[0].rstrip(".")
            return [f"{LOG_INDENT}Thành công", f"{LOG_INDENT}+{gold} Gold"]
        return [f"{LOG_INDENT}Thành công", f"{LOG_INDENT}không Gold"]
    if message.startswith("Hết giờ"):
        return [f"{LOG_INDENT}Thất bại, hết giờ", f"{LOG_INDENT}không Gold"]
    if message.startswith("Không thấy màn kết quả"):
        return [f"{LOG_INDENT}Không rõ kết quả"]
    if message.startswith(("Tổng kết", "Đã dừng", "Đã câu", "Hết rod", "Lỗi", "Không đổi", "Không nhận ra", "Bấm quăng")):
        return [message]
    return []


def log_tone(line: str) -> str:
    """Kết quả tô màu. Dòng UID và tổng kết giữ đen đậm. Bước làm chuyển xám."""
    text = line.strip().lower()
    if not text:
        return "muted"
    if text.startswith("tổng kết"):
        return "strong"
    if "không gold" in text:
        return "muted"
    if " gold" in text:
        return "ok"
    if any(mark in text for mark in OK_MARKS):
        return "ok"
    if any(mark in text for mark in BAD_MARKS):
        return "bad"
    if any(mark in text for mark in WARN_MARKS):
        return "warn"
    if line.startswith(LOG_INDENT):
        return "muted"
    return "strong"


def apply_theme(root: tk.Tk) -> None:
    """sv-ttk lo nút, ô nhập, thẻ và công tắc. Ở đây chỉ thêm chữ tiêu đề, chữ phụ và nút Dừng."""
    sv_ttk.set_theme("light", root)
    root.configure(bg=APP_BG)
    style = ttk.Style(root)
    style.configure("Title.TLabel", font=FONT_TITLE)
    style.configure("Hint.TLabel", foreground=LOG_MUTED, font=FONT_CAPTION)
    style.configure("Section.TLabel", foreground=LOG_MUTED, font=FONT_BODY_STRONG)
    style.configure("Status.TLabel", foreground=LOG_MUTED, font=FONT_CAPTION)
    style.configure("StatusOn.TLabel", foreground=LOG_OK, font=FONT_BODY_STRONG)
    style.configure("Stop.TButton", foreground=LOG_BAD)
    style.map("Stop.TButton", foreground=[("disabled", "#a0a0a0")])


def card(parent: tk.Misc, padding: int = 16) -> ttk.Frame:
    """Thẻ bo góc có viền của sv-ttk."""
    return ttk.Frame(parent, style="Card.TFrame", padding=padding)


class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Nhận quà MVP")
        self.root.minsize(WINDOW_WIDTH, COMPACT_HEIGHT)
        self.root.geometry(f"{WINDOW_WIDTH}x{COMPACT_HEIGHT}")
        self.root.configure(bg=APP_BG)
        apply_theme(root)
        self.stop = threading.Event()
        self.worker: threading.Thread | None = None
        self.finder = Finder()
        self.detail_open = False
        self.mode = "list"
        self.running = False

        self.body = ttk.Frame(root, padding=20)
        self.body.pack(fill="both", expand=True)
        self.body.columnconfigure(0, weight=1)
        self.body.rowconfigure(0, weight=1)

        frame = ttk.Frame(self.body)
        frame.grid(row=0, column=0, sticky="nsew")

        header = ttk.Frame(frame)
        header.pack(fill="x")
        titles = ttk.Frame(header)
        titles.pack(side="left", fill="x", expand=True)
        self.title_var = tk.StringVar(value="Nhận quà MVP")
        self.hint_var = tk.StringVar(value=GIFT_HINT)
        ttk.Label(titles, textvariable=self.title_var, style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            titles,
            textvariable=self.hint_var,
            style="Hint.TLabel",
            wraplength=HINT_WRAP,
        ).pack(anchor="w", pady=(2, 0))
        self.device_var = tk.StringVar(value="Chưa nối")
        self.device_label = ttk.Label(header, textvariable=self.device_var, style="Status.TLabel")
        self.device_label.pack(side="right", anchor="ne")

        switch = ttk.Frame(frame)
        switch.pack(anchor="w", pady=(16, 0))
        self.mode_var = tk.StringVar(value="list")
        self.list_seg = self._segment(switch, "Nhập danh sách", "list", first=True)
        self.scan_seg = self._segment(switch, "Quét ID", "scan")
        self.rally_seg = self._segment(switch, "Auto join rally", "rally")
        self.fish_seg = self._segment(switch, "Tự câu cá", "fish")

        self.card = card(frame)
        self.card.pack(fill="x", pady=(10, 0))
        list_tab = ttk.Frame(self.card)
        scan_tab = ttk.Frame(self.card)
        rally_tab = ttk.Frame(self.card)
        fish_tab = ttk.Frame(self.card)
        self.list_page = list_tab
        self.scan_page = scan_tab
        self.rally_page = rally_tab
        self.fish_page = fish_tab

        ttk.Label(list_tab, text="Mỗi dòng một UID").pack(anchor="w")
        self.ids = tk.Text(
            list_tab,
            height=UID_BOX_LINES,
            font=ID_FONT,
            bg=CARD_BG,
            fg=LOG_FG,
            relief="flat",
            highlightthickness=1,
            highlightbackground=BORDER,
            highlightcolor=ACCENT,
            padx=8,
            pady=6,
            borderwidth=0,
            insertbackground=LOG_FG,
        )
        self.ids.pack(fill="x", pady=(8, 0))
        ttk.Button(list_tab, text="Nạp file txt", command=self.load_file).pack(
            anchor="w", pady=(8, 0)
        )

        scan_tab.columnconfigure(0, weight=1)
        ttk.Label(scan_tab, text="ID đầu", style="Hint.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(scan_tab, text="Số lần", style="Hint.TLabel").grid(row=0, column=1, sticky="w", padx=(12, 0))
        self.scan_start = ttk.Entry(scan_tab, width=18, font=ID_FONT)
        self.scan_start.grid(row=1, column=0, sticky="ew", pady=(4, 0))
        self.scan_count = ttk.Spinbox(scan_tab, from_=1, to=SCAN_COUNT_MAX, width=8, font=ID_FONT)
        self.scan_count.set(str(SCAN_COUNT_DEFAULT))
        self.scan_count.grid(row=1, column=1, sticky="ew", padx=(12, 0), pady=(4, 0))
        ttk.Label(
            scan_tab,
            text="ID đầu là lượt 1. Mỗi lần sau cộng thêm 1.",
            style="Hint.TLabel",
        ).grid(row=2, column=0, columnspan=2, sticky="w", pady=(12, 0))

        ttk.Label(rally_tab, text="Trong Goldrush, mở chat Frostnip League.").pack(anchor="w")
        ttk.Label(
            rally_tab,
            text="Thấy nút Join xanh trong chat thì bấm ngay. Không thấy thì mới kéo khoảng 10 tin gần nhất. Nhiều người cùng một ô thì bấm hết, rồi kéo xuống nếu danh sách còn dài.",
            style="Hint.TLabel",
            wraplength=520,
        ).pack(anchor="w", pady=(8, 0))
        ttk.Label(
            rally_tab,
            text="Không thấy nút xanh thì kéo tới tin mới nhất. Tìm ở tin cũ xong thì bấm mũi tên tím bên phải để xuống. Hộp hoàn thành rally thì bấm Confirm để đóng. Chạy đến khi bấm Dừng.",
            style="Hint.TLabel",
            wraplength=520,
        ).pack(anchor="w", pady=(8, 0))

        fish_tab.columnconfigure(0, weight=1)
        ttk.Label(fish_tab, text="Số lượt câu", style="Hint.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(fish_tab, text="Hệ số", style="Hint.TLabel").grid(row=0, column=1, sticky="w", padx=(12, 0))
        self.fish_casts = ttk.Spinbox(fish_tab, from_=1, to=FISHING_CASTS_MAX, width=10, font=ID_FONT)
        self.fish_casts.set(str(FISHING_CASTS_DEFAULT))
        self.fish_casts.grid(row=1, column=0, sticky="ew", pady=(4, 0))
        self.fish_mult = ttk.Combobox(fish_tab, values=FISHING_MULTIPLIERS, width=6, font=ID_FONT)
        self.fish_mult.set("1")
        self.fish_mult.grid(row=1, column=1, sticky="ew", padx=(12, 0), pady=(4, 0))
        ttk.Label(
            fish_tab,
            text="Để trống hệ số là x1. Hệ số xN tốn N rod mỗi lần quăng. Tool dừng khi đủ lượt hoặc hết rod. Vòng đổi hệ số của game hiện có đến x100, chưa nhận ra x200.",
            style="Hint.TLabel",
            wraplength=520,
        ).grid(row=2, column=0, columnspan=2, sticky="w", pady=(12, 0))
        ttk.Label(
            fish_tab,
            text="Tổng quan chỉ hiện từng lượt, thụt vào là thành công hay thất bại và Gold. Bấm Xem chi tiết log để xem từng bước bấm.",
            style="Hint.TLabel",
            wraplength=520,
        ).grid(row=3, column=0, columnspan=2, sticky="w", pady=(8, 0))

        list_tab.pack(fill="x")
        self.root.update_idletasks()
        page_height = max(page.winfo_reqheight() for page in (list_tab, scan_tab, rally_tab, fish_tab))
        self.card.pack_propagate(False)
        self.card.configure(height=page_height + 44)

        bar = ttk.Frame(frame)
        bar.pack(fill="x", pady=(14, 0))
        self.primary_btn = ttk.Button(bar, text="Bắt đầu", style="Accent.TButton", command=self.run_current)
        self.primary_btn.pack(side="left")
        self.stop_btn = ttk.Button(
            bar, text="Dừng", style="Stop.TButton", command=self.request_stop, state="disabled"
        )
        self.stop_btn.pack(side="left", padx=(8, 0))
        self.detail_btn = ttk.Button(bar, text="Xem chi tiết log", command=self.toggle_detail)
        self.detail_btn.pack(side="right")
        ttk.Button(bar, text="Kiểm tra nút", command=self.preview).pack(side="right", padx=(0, 6))
        ttk.Button(bar, text="Chụp thử", command=self.capture_only).pack(side="right", padx=(0, 6))

        self.progress = tk.StringVar(value=f"Sẵn sàng · dừng sau {MAX_GIFTS} quà")
        ttk.Label(frame, textvariable=self.progress).pack(anchor="w", pady=(12, 0))

        log_card = card(frame)
        log_card.pack(fill="x", pady=(14, 0))
        ttk.Label(log_card, text="Tổng quan", style="Section.TLabel").pack(anchor="w", pady=(0, 8))
        log_wrap = ttk.Frame(log_card)
        log_wrap.pack(fill="x")
        self.log_box = tk.Text(
            log_wrap, height=OVERVIEW_LOG_LINES, state="disabled", font=LOG_FONT, wrap="word"
        )
        log_scroll = ttk.Scrollbar(log_wrap, command=self.log_box.yview)
        self.log_box.configure(yscrollcommand=log_scroll.set)
        self.log_box.pack(side="left", fill="both", expand=True)
        log_scroll.pack(side="right", fill="y")
        self._paint_log(self.log_box)

        self.detail_frame = card(self.body)
        detail_card = self.detail_frame
        ttk.Label(detail_card, text="Chi tiết", style="Section.TLabel").pack(anchor="w", pady=(0, 8))
        detail_wrap = ttk.Frame(detail_card)
        detail_wrap.pack(fill="both", expand=True)
        self.detail_box = tk.Text(
            detail_wrap, height=DETAIL_LOG_LINES, state="disabled", font=LOG_FONT, wrap="word"
        )
        detail_scroll = ttk.Scrollbar(detail_wrap, command=self.detail_box.yview)
        self.detail_box.configure(yscrollcommand=detail_scroll.set)
        self.detail_box.pack(side="left", fill="both", expand=True)
        detail_scroll.pack(side="right", fill="y")
        self._paint_log(self.detail_box)

    def _segment(self, parent, text: str, value: str, first: bool = False) -> ttk.Radiobutton:
        """Nút chuyển chế độ. Toggle.TButton của sv-ttk tô màu nhấn cho nút đang chọn."""
        button = ttk.Radiobutton(
            parent,
            text=text,
            value=value,
            variable=self.mode_var,
            style="Toggle.TButton",
            command=lambda: self._select(value),
        )
        button.pack(side="left", padx=(0 if first else 6, 0))
        return button

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
            self.write("Bỏ qua dòng không phải UID: " + ", ".join(bad[:8]), note=True)
        if duplicated:
            self.write(f"Bỏ {duplicated} ID trùng.", note=True)
        if not ids:
            self.write("Chưa có UID hợp lệ.")
            return
        self._begin(ids)

    def run_current(self):
        if self.mode == "fish":
            self.start_fishing()
        elif self.mode == "rally":
            self.start_rally()
        elif self.mode == "scan":
            self.start_scan()
        else:
            self.start()

    def show_list(self):
        self._select("list")

    def show_scan(self):
        self._select("scan")

    def show_rally(self):
        self._select("rally")

    def _select(self, mode: str):
        if self.running:
            return
        self.mode = mode
        self.list_page.pack_forget()
        self.scan_page.pack_forget()
        self.rally_page.pack_forget()
        self.fish_page.pack_forget()
        self.mode_var.set(mode)
        if mode == "fish":
            self.fish_page.pack(fill="x")
            self.primary_btn.configure(text="Bắt đầu")
            self.title_var.set("Tự câu cá")
            self.hint_var.set(FISH_HINT)
            self.root.title("Tự câu cá")
            self.progress.set("Sẵn sàng · câu đủ số lượt hoặc đến khi hết rod")
            return
        if mode == "scan":
            self.scan_page.pack(fill="x")
            self.primary_btn.configure(text="Quét")
            self.title_var.set("Nhận quà MVP")
            self.hint_var.set(GIFT_HINT)
            self.root.title("Nhận quà MVP")
            self.progress.set(f"Sẵn sàng · dừng sau {MAX_GIFTS} quà")
            return
        if mode == "rally":
            self.rally_page.pack(fill="both", expand=True)
            self.primary_btn.configure(text="Bắt đầu")
            self.title_var.set("Auto join rally")
            self.hint_var.set(RALLY_HINT)
            self.root.title("Auto join rally")
            self.progress.set("Sẵn sàng · join rally đến khi dừng")
            return
        self.list_page.pack(fill="x")
        self.primary_btn.configure(text="Bắt đầu")
        self.title_var.set("Nhận quà MVP")
        self.hint_var.set(GIFT_HINT)
        self.root.title("Nhận quà MVP")
        self.progress.set(f"Sẵn sàng · dừng sau {MAX_GIFTS} quà")

    def start_scan(self):
        if self.worker and self.worker.is_alive():
            return
        raw = "".join(self.scan_start.get().split())
        if not (raw.isdigit() and UID_MIN_LEN <= len(raw) <= UID_MAX_LEN):
            self.write("ID đầu phải là số, dài 4 đến 15 chữ số.")
            return
        try:
            count = int(self.scan_count.get())
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

    def start_rally(self):
        if self.worker and self.worker.is_alive():
            return
        self.stop.clear()
        self._clear(self.detail_box)
        self._lock()
        self.progress.set("Đang join rally")
        self.worker = threading.Thread(target=self._run_rally, daemon=True)
        self.worker.start()

    def start_fishing(self):
        if self.worker and self.worker.is_alive():
            return
        try:
            casts = int(self.fish_casts.get())
        except ValueError:
            self.write("Số lượt câu phải là số nguyên dương.")
            return
        if not 1 <= casts <= FISHING_CASTS_MAX:
            self.write(f"Số lượt câu từ 1 đến {FISHING_CASTS_MAX}.")
            return
        text = self.fish_mult.get().strip().lower().lstrip("x") or "1"
        if text not in FISHING_MULTIPLIERS:
            self.write(f"Hệ số chỉ nhận một trong: {', '.join(FISHING_MULTIPLIERS)}.")
            return
        self.fish_mult.set(text)
        self.stop.clear()
        self._clear(self.log_box)
        self._clear(self.detail_box)
        self._lock()
        self.progress.set(f"Đang câu 0/{casts} lượt")
        self.worker = threading.Thread(target=self._run_fishing, args=(casts, int(text)), daemon=True)
        self.worker.start()

    def _begin(self, ids: list[str]):
        self.stop.clear()
        self._clear(self.detail_box)
        self._lock()
        self.progress.set(f"Đang chạy 0/{MAX_GIFTS} quà")
        self.worker = threading.Thread(target=self._run, args=(ids,), daemon=True)
        self.worker.start()

    def _lock(self):
        self.running = True
        self.primary_btn.configure(state="disabled")
        self.stop_btn.configure(state="normal")
        for button in (self.list_seg, self.scan_seg, self.rally_seg, self.fish_seg):
            button.configure(state="disabled")

    def _unlock(self):
        self.running = False
        self.primary_btn.configure(state="normal")
        self.stop_btn.configure(state="disabled")
        for button in (self.list_seg, self.scan_seg, self.rally_seg, self.fish_seg):
            button.configure(state="normal")

    def toggle_detail(self):
        height = self.root.winfo_height()
        if self.detail_open:
            self.detail_frame.grid_remove()
            self.body.columnconfigure(1, weight=0, minsize=0)
            self.detail_open = False
            self.detail_btn.configure(text="Xem chi tiết log")
            self.root.minsize(WINDOW_WIDTH, COMPACT_HEIGHT)
            self.root.geometry(f"{WINDOW_WIDTH}x{height}")
            return
        self.body.columnconfigure(1, weight=1, minsize=DETAIL_PANEL)
        self.detail_frame.grid(row=0, column=1, sticky="nsew", padx=(12, 0))
        self.detail_open = True
        self.detail_btn.configure(text="Ẩn chi tiết log")
        self.root.minsize(OPEN_WIDTH, COMPACT_HEIGHT)
        self.root.geometry(f"{max(self.root.winfo_width(), OPEN_WIDTH)}x{height}")
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
            self.root.after(0, lambda s=serial: self._set_device(s))

            def log(message: str):
                self.write(message)
                if message.startswith("[") and "đã nhận" in message:
                    self.root.after(0, lambda m=message: self.progress.set(m))

            runner = Runner(adb, self.finder, log, self.stop, self.write_detail)
            counts = runner.run(ids)
            summary = (
                f"Xong. Quà {counts['da_nhan_qua']}/{MAX_GIFTS}, pinball {counts.get('pinball', 0)}. "
                + ", ".join(f"{LABELS[key]} {counts[key]}" for key in LABELS)
            )
            self.root.after(0, lambda text=summary: self.progress.set(text))
        except Exception as exc:
            self.write(f"Lỗi: {exc}")
            self.root.after(0, lambda: self.progress.set("Dừng vì lỗi"))
        finally:
            self.root.after(0, self._unlock)

    def _run_rally(self):
        try:
            adb = AdbClient()
            serial = adb.ensure_device()
            self.write(f"Đã nối {serial}")
            self.root.after(0, lambda s=serial: self._set_device(s))

            def log(message: str):
                self.write(message)
                if "xin vào" in message.lower() or message.startswith("Đã dừng"):
                    self.root.after(0, lambda m=message: self.progress.set(m))

            counts = RallyRunner(adb, log, self.stop, self.finder).run()
            summary = f"Xong. Đã xin {counts['xin']} rally."
            self.root.after(0, lambda text=summary: self.progress.set(text))
        except Exception as exc:
            self.write(f"Lỗi: {exc}")
            self.root.after(0, lambda: self.progress.set("Dừng vì lỗi"))
        finally:
            self.root.after(0, self._unlock)

    def _run_fishing(self, casts: int, multiplier: int):
        try:
            if str(FISHING_DIR) not in sys.path:
                sys.path.insert(0, str(FISHING_DIR))
            try:
                from fishing_tool.device import FishAdb
                from fishing_tool.flow import Runner as FishRunner
            except ImportError as exc:
                raise RuntimeError(f"Không nạp được tool câu cá ở {FISHING_DIR}: {exc}") from exc

            adb = FishAdb()
            serial = adb.ensure_device()
            self.write_detail(f"Đã nối {serial}")
            self.root.after(0, lambda s=serial: self._set_device(s))

            def log(message: str):
                self.write_detail(message)
                for line in fish_overview(message):
                    self.write(line)

            def show(stats):
                rods = "?" if stats.rods is None else stats.rods
                text = (
                    f"Câu {stats.casts}/{casts} · thành công {stats.caught} · hết giờ {stats.failed} · "
                    f"Gold {stats.gold} · rod còn {rods}"
                )
                self.root.after(0, lambda t=text: self.progress.set(t))

            runner = FishRunner(adb, log, self.stop, casts, multiplier, on_stats=show)
            stats = runner.run()
            show(stats)
        except Exception as exc:
            self.write(f"Lỗi: {exc}")
            self.write_detail(f"Lỗi: {exc}")
            self.root.after(0, lambda: self.progress.set("Dừng vì lỗi"))
        finally:
            self.root.after(0, self._unlock)

    def _capture_only(self):
        try:
            adb = AdbClient()
            serial = adb.ensure_device()
            shot = adb.screenshot()
            path = LOGS / "chup-thu.png"
            imwrite(path, shot)
            height, width = shot.shape[:2]
            self.root.after(0, lambda s=serial: self._set_device(s))
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
            for name in ("search", "add", "apply", "visit", "gift", "select", "ok", "close", "missing_id", "friends", "community"):
                hit = self.finder.locate(shot, name)
                threshold = self.finder.templates[name][1]["threshold"]
                mark = "thấy" if hit.score >= threshold and hit.w else "không"
                lines.append(f"{LOG_INDENT}{name}: {hit.score:.2f} ({mark})")
                if hit.w and hit.score >= threshold:
                    hits.append(hit)
            path = LOGS / "kiem-tra.png"
            imwrite(path, draw_hits(shot, hits))
            self.root.after(0, lambda s=serial: self._set_device(s))
            lines.append(f"Ảnh khoanh nút: {path}")
            self.write("\n".join(lines))
            self.root.after(0, lambda: __import__("os").startfile(path))
        except Exception as exc:
            self.write(f"Lỗi kiểm tra: {exc}")

    def _set_device(self, serial: str) -> None:
        self.device_var.set(f"Đã nối {serial}")
        self.device_label.configure(style="StatusOn.TLabel")

    def write(self, message: str, *, note: bool = False):
        if note:
            message = f"{LOG_INDENT}{message}"
        self._append(self.log_box, message)

    def write_detail(self, message: str):
        self._append(self.detail_box, message)

    def _paint_log(self, box: tk.Text) -> None:
        box.configure(
            bg=LOG_BG,
            fg=LOG_FG,
            relief="flat",
            highlightthickness=1,
            highlightbackground=BORDER,
            highlightcolor=BORDER,
            padx=8,
            pady=6,
            borderwidth=0,
            insertbackground=LOG_FG,
        )
        box.tag_configure("strong", foreground=LOG_FG, font=(*LOG_FONT, "bold"))
        box.tag_configure("muted", foreground=LOG_MUTED, font=LOG_FONT)
        box.tag_configure("ok", foreground=LOG_OK, font=(*LOG_FONT, "bold"))
        box.tag_configure("warn", foreground=LOG_WARN, font=(*LOG_FONT, "bold"))
        box.tag_configure("bad", foreground=LOG_BAD, font=(*LOG_FONT, "bold"))

    def _append(self, box: tk.Text, message: str):
        def append():
            box.configure(state="normal")
            lines = message.splitlines() or [""]
            for line in lines:
                box.insert("end", line + "\n", log_tone(line))
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
