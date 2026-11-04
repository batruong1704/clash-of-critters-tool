"""Cửa sổ dán UID, bấm Bắt đầu / Dừng, xem log tổng quan và log từng bước."""

from __future__ import annotations

import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, ttk

from gift_tool.adb_client import AdbClient
from gift_tool.flow import LABELS, LOG_INDENT, MAX_GIFTS, Runner
from gift_tool.paths import LOGS
from gift_tool.vision import Finder, draw_hits, imwrite

_CODE_ROOT = Path(__file__).resolve().parents[2] / "auto-typing-giftcode"
if str(_CODE_ROOT) not in sys.path:
    sys.path.insert(0, str(_CODE_ROOT))

from giftcode_tool.codes import load_codes
from giftcode_tool.flow import Runner as CodeRunner
from rally_tool.flow import Runner as RallyRunner

WINDOW_WIDTH = 840
COMPACT_HEIGHT = 760
DETAIL_PANEL = 420
OPEN_WIDTH = WINDOW_WIDTH + DETAIL_PANEL
OVERVIEW_LOG_LINES = 10
DETAIL_LOG_LINES = 16
HINT_WRAP = 460
UID_BOX_LINES = 7
APP_BG = "#f3f4f6"
CARD_BG = "#ffffff"
BORDER = "#e4e7ec"
ACCENT = "#1d4ed8"
ACCENT_HOVER = "#1e40af"
ACCENT_PRESS = "#1e3a8a"
UI_FONT = ("Segoe UI", 10)
UI_FONT_BOLD = ("Segoe UI", 10, "bold")
TITLE_FONT = ("Segoe UI", 18, "bold")
HINT_FONT = ("Segoe UI", 9)
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
OK_MARKS = ("đã nhận quà", "đã nhận mã", "đã bấm select và ok", "quà, dừng", "xin vào")
GIFT_HINT = "Màn hình dọc. Tool tự mở tab Add New nếu đang ở sân hoặc Goldrush. Lần đầu chỉ chạy 1–2 UID."
RALLY_HINT = "Màn dọc. Đang ở sân hoặc trong Goldrush đều được. Ra khỏi mode thì bấm lại nút Goldrush. Chỉ bấm nút xanh, bỏ nút xám, không tạo rally."
CODE_HINT = "Gõ một mã rồi bấm Nhập mã, hoặc bấm Chạy mã mặc định. Danh sách nằm ở auto-typing-giftcode/giftcode_tool/ma-mac-dinh.txt."
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
)
WARN_MARKS = (
    "không thấy người chơi",
    "không có quà",
    "sân đứng yên",
    "id sai",
    "không được nhận",
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


def log_tone(line: str) -> str:
    """Kết quả tô màu. Dòng UID và tổng kết giữ đen đậm. Bước làm chuyển xám."""
    text = line.strip().lower()
    if not text:
        return "muted"
    if text.startswith("tổng kết"):
        return "strong"
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
    """Clam cho phép tô nút. Vista thì nút chính không khác nút phụ."""
    style = ttk.Style(root)
    style.theme_use("clam")
    style.configure(".", background=APP_BG, foreground=LOG_FG, font=UI_FONT)
    style.configure("TFrame", background=APP_BG)
    style.configure("Card.TFrame", background=CARD_BG)
    style.configure("TLabel", background=APP_BG, foreground=LOG_FG, font=UI_FONT)
    style.configure("Title.TLabel", background=APP_BG, foreground=LOG_FG, font=TITLE_FONT)
    style.configure("Hint.TLabel", background=APP_BG, foreground=LOG_MUTED, font=HINT_FONT)
    style.configure("Section.TLabel", background=APP_BG, foreground=LOG_MUTED, font=UI_FONT_BOLD)
    style.configure("CardSection.TLabel", background=CARD_BG, foreground=LOG_MUTED, font=UI_FONT_BOLD)
    style.configure("Card.TLabel", background=CARD_BG, foreground=LOG_FG, font=UI_FONT)
    style.configure("CardHint.TLabel", background=CARD_BG, foreground=LOG_MUTED, font=HINT_FONT)
    style.configure("Status.TLabel", background=APP_BG, foreground=LOG_MUTED, font=HINT_FONT)
    style.configure("StatusOn.TLabel", background=APP_BG, foreground=LOG_OK, font=UI_FONT_BOLD)
    style.configure(
        "Segment.TButton",
        background=APP_BG,
        foreground=LOG_MUTED,
        borderwidth=1,
        bordercolor=BORDER,
        lightcolor=BORDER,
        darkcolor=BORDER,
        focusthickness=0,
        focuscolor=APP_BG,
        padding=(14, 8),
        font=UI_FONT,
    )
    style.map("Segment.TButton", background=[("active", "#e5e7eb")])
    style.configure(
        "SegmentOn.TButton",
        background=CARD_BG,
        foreground=LOG_FG,
        borderwidth=1,
        bordercolor=BORDER,
        lightcolor=BORDER,
        darkcolor=BORDER,
        focusthickness=0,
        focuscolor=CARD_BG,
        padding=(14, 8),
        font=UI_FONT_BOLD,
    )
    style.map("SegmentOn.TButton", background=[("active", CARD_BG)])
    style.configure(
        "TEntry",
        fieldbackground=CARD_BG,
        foreground=LOG_FG,
        bordercolor=BORDER,
        lightcolor=BORDER,
        darkcolor=BORDER,
        padding=8,
        font=ID_FONT,
    )
    style.configure(
        "TSpinbox",
        fieldbackground=CARD_BG,
        foreground=LOG_FG,
        bordercolor=BORDER,
        arrowcolor=LOG_FG,
        padding=6,
        font=ID_FONT,
    )
    style.configure(
        "Primary.TButton",
        background=ACCENT,
        foreground="#ffffff",
        borderwidth=1,
        bordercolor=ACCENT_PRESS,
        lightcolor=ACCENT_PRESS,
        darkcolor=ACCENT_PRESS,
        focusthickness=0,
        focuscolor=ACCENT,
        padding=(18, 8),
        font=UI_FONT_BOLD,
    )
    style.map(
        "Primary.TButton",
        background=[
            ("disabled", "#e5e7eb"),
            ("pressed", ACCENT_PRESS),
            ("active", ACCENT_HOVER),
        ],
        foreground=[("disabled", "#6b7280")],
    )
    style.configure(
        "Stop.TButton",
        background=APP_BG,
        foreground=LOG_MUTED,
        borderwidth=1,
        bordercolor=BORDER,
        lightcolor=BORDER,
        darkcolor=BORDER,
        focusthickness=0,
        focuscolor=APP_BG,
        padding=(14, 8),
        font=UI_FONT_BOLD,
    )
    style.map(
        "Stop.TButton",
        background=[("disabled", APP_BG), ("active", "#fde8e8"), ("!disabled", "#fde8e8")],
        foreground=[("disabled", "#9ca3af"), ("!disabled", LOG_BAD)],
    )
    style.configure(
        "Ghost.TButton",
        background=APP_BG,
        foreground=LOG_FG,
        borderwidth=1,
        bordercolor=BORDER,
        lightcolor=BORDER,
        darkcolor=BORDER,
        focusthickness=0,
        focuscolor=APP_BG,
        padding=(10, 8),
        font=UI_FONT,
    )
    style.map("Ghost.TButton", background=[("active", "#e5e7eb"), ("pressed", "#d1d5db")])
    style.configure(
        "CardGhost.TButton",
        background=CARD_BG,
        foreground=LOG_FG,
        borderwidth=1,
        bordercolor=BORDER,
        lightcolor=BORDER,
        darkcolor=BORDER,
        focusthickness=0,
        focuscolor=CARD_BG,
        padding=(10, 6),
        font=UI_FONT,
    )
    style.map("CardGhost.TButton", background=[("active", "#f3f4f6"), ("pressed", "#e5e7eb")])


def bordered(parent: tk.Misc) -> tuple[tk.Frame, ttk.Frame]:
    """Viền 1 px. ttk.Frame không vẽ cạnh khi chỉ đổi màu nền."""
    shell = tk.Frame(
        parent,
        bg=BORDER,
        highlightthickness=1,
        highlightbackground=BORDER,
        highlightcolor=BORDER,
        bd=0,
    )
    inner = ttk.Frame(shell, style="Card.TFrame", padding=14)
    inner.pack(fill="both", expand=True)
    return shell, inner


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
        self.list_seg = ttk.Button(
            switch, text="Nhập danh sách", style="SegmentOn.TButton", command=self.show_list
        )
        self.list_seg.pack(side="left")
        self.scan_seg = ttk.Button(switch, text="Quét ID", style="Segment.TButton", command=self.show_scan)
        self.scan_seg.pack(side="left", padx=(4, 0))
        self.rally_seg = ttk.Button(
            switch, text="Auto join rally", style="Segment.TButton", command=self.show_rally
        )
        self.rally_seg.pack(side="left", padx=(4, 0))
        self.code_seg = ttk.Button(
            switch, text="Gift code", style="Segment.TButton", command=self.show_code
        )
        self.code_seg.pack(side="left", padx=(4, 0))

        card_shell, self.card = bordered(frame)
        card_shell.pack(fill="x", pady=(8, 0))
        list_tab = ttk.Frame(self.card, style="Card.TFrame")
        scan_tab = ttk.Frame(self.card, style="Card.TFrame")
        rally_tab = ttk.Frame(self.card, style="Card.TFrame")
        code_tab = ttk.Frame(self.card, style="Card.TFrame")
        self.list_page = list_tab
        self.scan_page = scan_tab
        self.rally_page = rally_tab
        self.code_page = code_tab

        ttk.Label(list_tab, text="Mỗi dòng một UID", style="Card.TLabel").pack(anchor="w")
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
        ttk.Button(list_tab, text="Nạp file txt", style="CardGhost.TButton", command=self.load_file).pack(
            anchor="w", pady=(8, 0)
        )

        scan_tab.columnconfigure(0, weight=1)
        ttk.Label(scan_tab, text="ID đầu", style="CardHint.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(scan_tab, text="Số lần", style="CardHint.TLabel").grid(row=0, column=1, sticky="w", padx=(12, 0))
        self.scan_start = ttk.Entry(scan_tab, width=18, font=ID_FONT)
        self.scan_start.grid(row=1, column=0, sticky="ew", pady=(4, 0))
        self.scan_count = ttk.Spinbox(scan_tab, from_=1, to=SCAN_COUNT_MAX, width=8, font=ID_FONT)
        self.scan_count.set(str(SCAN_COUNT_DEFAULT))
        self.scan_count.grid(row=1, column=1, sticky="ew", padx=(12, 0), pady=(4, 0))
        ttk.Label(
            scan_tab,
            text="ID đầu là lượt 1. Mỗi lần sau cộng thêm 1.",
            style="CardHint.TLabel",
        ).grid(row=2, column=0, columnspan=2, sticky="w", pady=(12, 0))

        ttk.Label(rally_tab, text="Trong Goldrush, mở chat Frostnip League.", style="Card.TLabel").pack(anchor="w")
        ttk.Label(
            rally_tab,
            text="Thấy nút Join xanh trong chat thì bấm ngay. Không thấy thì mới kéo khoảng 10 tin gần nhất. Nhiều người cùng một ô thì bấm hết, rồi kéo xuống nếu danh sách còn dài.",
            style="CardHint.TLabel",
            wraplength=520,
        ).pack(anchor="w", pady=(8, 0))
        ttk.Label(
            rally_tab,
            text="Không thấy nút xanh thì kéo tới tin mới nhất. Tìm ở tin cũ xong thì bấm mũi tên tím bên phải để xuống. Hộp hoàn thành rally thì bấm Confirm để đóng. Chạy đến khi bấm Dừng.",
            style="CardHint.TLabel",
            wraplength=520,
        ).pack(anchor="w", pady=(8, 0))

        ttk.Label(code_tab, text="Một mã, chữ và số", style="Card.TLabel").pack(anchor="w")
        self.code = ttk.Entry(code_tab, font=ID_FONT)
        self.code.pack(fill="x", pady=(8, 0))
        self.code_default_btn = ttk.Button(
            code_tab, text="Chạy mã mặc định", style="CardGhost.TButton", command=self.start_default_codes
        )
        self.code_default_btn.pack(anchor="w", pady=(8, 0))
        ttk.Label(
            code_tab,
            text="Ô trống thì bấm Nhập mã không chạy. Mã mặc định đọc từ file ma-mac-dinh.txt, sửa file đó để thêm mã. Mã nhận được thì rời màn quà và sang mã sau, không bấm Open Another.",
            style="CardHint.TLabel",
            wraplength=520,
        ).pack(anchor="w", pady=(8, 0))

        list_tab.pack(fill="x")
        self.root.update_idletasks()
        page_height = max(page.winfo_reqheight() for page in (list_tab, scan_tab, rally_tab, code_tab))
        self.card.pack_propagate(False)
        self.card.configure(height=page_height + 28)

        bar = ttk.Frame(frame)
        bar.pack(fill="x", pady=(14, 0))
        self.primary_btn = ttk.Button(bar, text="Bắt đầu", style="Primary.TButton", command=self.run_current)
        self.primary_btn.pack(side="left")
        self.stop_btn = ttk.Button(
            bar, text="Dừng", style="Stop.TButton", command=self.request_stop, state="disabled"
        )
        self.stop_btn.pack(side="left", padx=(8, 0))
        self.detail_btn = ttk.Button(bar, text="Xem chi tiết log", style="Ghost.TButton", command=self.toggle_detail)
        self.detail_btn.pack(side="right")
        ttk.Button(bar, text="Kiểm tra nút", style="Ghost.TButton", command=self.preview).pack(side="right")
        ttk.Button(bar, text="Chụp thử", style="Ghost.TButton", command=self.capture_only).pack(side="right")

        self.progress = tk.StringVar(value=f"Sẵn sàng · dừng sau {MAX_GIFTS} quà")
        ttk.Label(frame, textvariable=self.progress).pack(anchor="w", pady=(12, 0))

        log_shell, log_card = bordered(frame)
        log_shell.pack(fill="x", pady=(14, 0))
        ttk.Label(log_card, text="TỔNG QUAN", style="CardSection.TLabel").pack(anchor="w", pady=(0, 8))
        self.log_box = tk.Text(
            log_card, height=OVERVIEW_LOG_LINES, state="disabled", font=LOG_FONT, wrap="word"
        )
        self.log_box.pack(fill="x")
        self._paint_log(self.log_box)

        self.detail_frame, detail_card = bordered(self.body)
        ttk.Label(detail_card, text="CHI TIẾT", style="CardSection.TLabel").pack(anchor="w", pady=(0, 8))
        self.detail_box = tk.Text(
            detail_card, height=DETAIL_LOG_LINES, state="disabled", font=LOG_FONT, wrap="word"
        )
        self.detail_box.pack(fill="both", expand=True)
        self._paint_log(self.detail_box)

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
        if self.mode == "rally":
            self.start_rally()
        elif self.mode == "code":
            self.start_code()
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

    def show_code(self):
        self._select("code")

    def _select(self, mode: str):
        if self.running:
            return
        self.mode = mode
        self.list_page.pack_forget()
        self.scan_page.pack_forget()
        self.rally_page.pack_forget()
        self.code_page.pack_forget()
        self.list_seg.configure(style="Segment.TButton")
        self.scan_seg.configure(style="Segment.TButton")
        self.rally_seg.configure(style="Segment.TButton")
        self.code_seg.configure(style="Segment.TButton")
        if mode == "scan":
            self.scan_page.pack(fill="x")
            self.scan_seg.configure(style="SegmentOn.TButton")
            self.primary_btn.configure(text="Quét")
            self.title_var.set("Nhận quà MVP")
            self.hint_var.set(GIFT_HINT)
            self.root.title("Nhận quà MVP")
            self.progress.set(f"Sẵn sàng · dừng sau {MAX_GIFTS} quà")
            return
        if mode == "rally":
            self.rally_page.pack(fill="both", expand=True)
            self.rally_seg.configure(style="SegmentOn.TButton")
            self.primary_btn.configure(text="Bắt đầu")
            self.title_var.set("Auto join rally")
            self.hint_var.set(RALLY_HINT)
            self.root.title("Auto join rally")
            self.progress.set("Sẵn sàng · join rally đến khi dừng")
            return
        if mode == "code":
            self.code_page.pack(fill="x")
            self.code_seg.configure(style="SegmentOn.TButton")
            self.primary_btn.configure(text="Nhập mã")
            self.title_var.set("Nhập gift code")
            self.hint_var.set(CODE_HINT)
            self.root.title("Nhập gift code")
            self.progress.set("Sẵn sàng · một mã hoặc danh sách mặc định")
            return
        self.list_page.pack(fill="x")
        self.list_seg.configure(style="SegmentOn.TButton")
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

    def start_code(self):
        if self.worker and self.worker.is_alive():
            return
        code = "".join(self.code.get().split())
        if not code or any(ch not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789" for ch in code):
            self.write("Gõ một mã chữ và số, hoặc bấm Chạy mã mặc định.")
            return
        self.stop.clear()
        self._clear(self.detail_box)
        self._lock()
        self.progress.set("Đang nhập mã")
        self.worker = threading.Thread(target=self._run_code, args=(code,), daemon=True)
        self.worker.start()

    def start_default_codes(self):
        if self.worker and self.worker.is_alive():
            return
        codes = load_codes()
        if not codes:
            self.write("File mã mặc định đang trống.")
            return
        self.stop.clear()
        self._clear(self.detail_box)
        self._lock()
        self.progress.set(f"Đang nhập 0/{len(codes)} mã")
        self.worker = threading.Thread(target=self._run_codes, args=(codes,), daemon=True)
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
        self.code_default_btn.configure(state="disabled")
        self.stop_btn.configure(state="normal")
        for button in (self.list_seg, self.scan_seg, self.rally_seg, self.code_seg):
            button.configure(state="disabled")

    def _unlock(self):
        self.running = False
        self.primary_btn.configure(state="normal")
        self.code_default_btn.configure(state="normal")
        self.stop_btn.configure(state="disabled")
        for button in (self.list_seg, self.scan_seg, self.rally_seg, self.code_seg):
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

    def _run_code(self, code: str):
        try:
            adb = AdbClient()
            serial = adb.ensure_device()
            self.write(f"Đã nối {serial}")
            self.root.after(0, lambda s=serial: self._set_device(s))
            status = CodeRunner(adb, self.write, self.stop, self.finder).run(code)
            summary = {
                "nhan": "Xong. Đã nhận mã, không bấm tiếp.",
                "khong_nhan": "Xong. Mã không được nhận.",
                "khong_mo": "Xong. Không mở được ô nhập mã.",
                "dung": "Đã dừng.",
            }.get(status, "Đã dừng.")
            self.root.after(0, lambda text=summary: self.progress.set(text))
        except Exception as exc:
            self.write(f"Lỗi: {exc}")
            self.root.after(0, lambda: self.progress.set("Dừng vì lỗi"))
        finally:
            self.root.after(0, self._unlock)

    def _run_codes(self, codes: list[str]):
        try:
            adb = AdbClient()
            serial = adb.ensure_device()
            self.write(f"Đã nối {serial}")
            self.root.after(0, lambda s=serial: self._set_device(s))

            def log(message: str):
                self.write(message)
                if message.startswith("[") and "Nhập mã" in message:
                    self.root.after(0, lambda m=message: self.progress.set(m))

            counts = CodeRunner(adb, log, self.stop, self.finder).run_many(codes)
            summary = f"Xong. Nhận {counts['nhan']}, không nhận {counts['khong_nhan']}."
            self.root.after(0, lambda text=summary: self.progress.set(text))
        except Exception as exc:
            self.write(f"Lỗi: {exc}")
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
            for name in ("search", "add", "apply", "visit", "gift", "select", "ok", "close", "missing_id", "claim_limit", "friends", "community"):
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
