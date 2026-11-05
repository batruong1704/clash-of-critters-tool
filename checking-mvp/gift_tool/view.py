"""View: cửa sổ hai cột theo mockup. Không đọc UID, không nối ADB."""

from __future__ import annotations

import gc
import threading
import tkinter as tk
import winreg
from tkinter import filedialog, messagebox, ttk

from gift_tool.paths import LOGS, REPO

WINDOW_WIDTH = 1040
WINDOW_HEIGHT = 700
SIDE_WIDTH = 290
UID_BOX_LINES = 6
HINT_WRAP = 250
ID_FONT = ("Consolas", 12)
LOG_FONT = ("Consolas", 10)
UI_FONT = ("Segoe UI", 10)
MULT_LIST_FONT = ("Segoe UI", 18)
TITLE_FONT = ("Segoe UI", 16, "bold")
TILE_FONT = ("Segoe UI", 16, "bold")
GO_FONT = ("Segoe UI", 12, "bold")
APP_VERSION = "1.2.0"
_CACHE_KEEP = {"cua-so.json"}
_CACHE_DIRS = (
    LOGS,
    REPO / "fishing-event" / "logs",
    REPO / "auto-join-rally" / "logs",
)


def _windows_dark() -> bool:
    """Windows đang để ứng dụng màu tối hay không."""
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
        ) as key:
            value, _kind = winreg.QueryValueEx(key, "AppsUseLightTheme")
        return int(value) == 0
    except OSError:
        return False


def _resolved_theme(mode: str) -> str:
    if mode == "dark":
        return "dark"
    if mode == "system":
        return "dark" if _windows_dark() else "light"
    return "light"


def _cache_bytes() -> int:
    total = 0
    for folder in _CACHE_DIRS:
        if not folder.is_dir():
            continue
        for path in folder.rglob("*"):
            if not path.is_file() or path.name in _CACHE_KEEP:
                continue
            try:
                total += path.stat().st_size
            except OSError:
                continue
    return total


def _delete_cache() -> None:
    for folder in _CACHE_DIRS:
        if not folder.is_dir():
            continue
        for path in folder.rglob("*"):
            if not path.is_file() or path.name in _CACHE_KEEP:
                continue
            try:
                path.unlink()
            except OSError:
                continue


def _format_size(size: int) -> str:
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        number, unit = size / 1024, "KB"
    else:
        number, unit = size / (1024 * 1024), "MB"
    return f"{number:.1f} {unit}".replace(".", ",")

LIGHT = {
    "bg": "#f3f4f6",
    "panel": "#ffffff",
    "line": "#e2e5ea",
    "text": "#1f2937",
    "mute": "#6b7280",
    "acc": "#0f766e",
    "acc_t": "#ffffff",
    "ok": "#15803d",
    "gold": "#ca8a04",
    "warn": "#b45309",
    "err": "#b91c1c",
    "dbg": "#9ca3af",
    "tile": "#f8fafc",
    "log": "#fbfbfc",
}
DARK = {
    "bg": "#1b1d21",
    "panel": "#25282d",
    "line": "#383c43",
    "text": "#e5e7eb",
    "mute": "#9ca3af",
    "acc": "#2dd4bf",
    "acc_t": "#06312d",
    "ok": "#4ade80",
    "gold": "#facc15",
    "warn": "#fbbf24",
    "err": "#f87171",
    "dbg": "#6b7280",
    "tile": "#2b2f35",
    "log": "#1f2226",
}

FISH_HINT = "Chạy được từ màn sân, Pinball hay Fishing Contest."
GIFT_HINT = "Nhập danh sách ID cần xử lý."
SCAN_HINT = "ID đầu là lượt 1. Mỗi lần sau cộng thêm 1."
RALLY_HINT = "Tự vào và tham gia rally. Chỉ bấm nút xanh, không tạo rally."
START_LABEL = "▶  Bắt đầu"
STOP_LABEL = "■  Dừng"
HOLD_LABEL = "■  Câu nốt"
OK_MARKS = ("đã nhận quà", "đã bấm select và ok", "quà, dừng", "xin vào", "câu được cá", "thành công")
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


def log_tone(line: str) -> str:
    """Kết quả tô màu. Dòng phụ chuyển xám."""
    text = line.strip().lower()
    if not text:
        return "dbg"
    if text.startswith("tổng kết") or text.startswith("lượt "):
        return "turn"
    if "không gold" in text:
        return "dbg"
    if " gold" in text or any(mark in text for mark in OK_MARKS):
        return "ok"
    if any(mark in text for mark in BAD_MARKS):
        return "err"
    if any(mark in text for mark in WARN_MARKS):
        return "warn"
    if line.startswith("  "):
        return "dbg"
    return "text"


def fish_level(message: str) -> str:
    """Mức dòng log câu cá. Chi tiết cú bấm để ẩn cho đến khi bật hiện."""
    if message.startswith("Lượt "):
        return "turn"
    if message.startswith("Câu được"):
        return "ok"
    if message.startswith(("Thất bại", "Lỗi", "Hết rod", "Không nhận ra")):
        return "err"
    if message.startswith("Trượt"):
        return "warn"
    if message.startswith(("Trúng vùng", "Bấm ")) or "Độ trễ" in message or message.startswith("  "):
        return "dbg"
    return "text"


class MainView:
    def __init__(
        self,
        root: tk.Tk,
        presenter,
        *,
        max_gifts: int,
        scan_default: int,
        scan_max: int,
        fish_default: int,
        fish_max: int,
        fish_multipliers: tuple[str, ...],
    ):
        self.root = root
        self.presenter = presenter
        self.max_gifts = max_gifts
        self.theme_mode = "light"
        self.theme_name = "light"
        self.colors = dict(LIGHT)
        self._ids_guard = False
        self._tools_open = False
        self._settings_open = False
        self._row_seq = 0
        self._bar_current = 0
        self._bar_total = 0
        self._toast_after = None
        self._show_debug = False
        self._auto_scroll = True
        self._view_name = "result"
        self._fish_hold = False

        self.root.title("Auto fishing")
        self.root.minsize(860, 640)
        self.root.geometry(f"{WINDOW_WIDTH}x{WINDOW_HEIGHT}")
        self.style = ttk.Style(self.root)
        self.style.theme_use("clam")

        self.title_var = tk.StringVar(value="Tự câu cá")
        self.hint_var = tk.StringVar(value=FISH_HINT)
        self.device_var = tk.StringVar(value="Chưa nối")
        self.id_summary = tk.StringVar(value="Chưa có UID hợp lệ")
        self.step_var = tk.StringVar(value="Sẵn sàng")
        self.progress_var = tk.StringVar(value="Sẵn sàng")
        self.percent_var = tk.StringVar(value="0%")
        self.toast_var = tk.StringVar(value="")
        self.mode_var = tk.StringVar(value="fish")
        self.scan_start_var = tk.StringVar()
        self.scan_count_var = tk.StringVar(value=str(scan_default))
        self.fish_casts_var = tk.StringVar(value=str(fish_default))
        self.fish_mult_var = tk.StringVar(value=f"x{fish_multipliers[0]}")

        self._build(scan_max, fish_max, fish_multipliers)
        self._paint()
        self.show_mode("fish")
        self.root.bind("<Escape>", lambda _event: presenter.on_escape())
        self.root.bind("<Button-1>", self._dismiss_tools, add="+")
        self.root.bind("<FocusIn>", self._follow_system_theme, add="+")

    def _build(self, scan_max: int, fish_max: int, fish_multipliers: tuple[str, ...]) -> None:
        self.debug_var = tk.BooleanVar(value=False)
        self.auto_var = tk.BooleanVar(value=True)
        self.body = tk.Frame(self.root)
        self.body.pack(fill="both", expand=True, padx=12, pady=12)
        self.body.columnconfigure(0, minsize=SIDE_WIDTH)
        self.body.columnconfigure(1, weight=1)
        self.body.rowconfigure(1, weight=1)

        self.header = tk.Frame(self.body)
        self.header.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 12))
        header = self.header
        self.title_label = tk.Label(header, textvariable=self.title_var, font=TITLE_FONT, anchor="w")
        self.title_label.pack(side="left")
        self._build_settings(header)
        self.conn = tk.Frame(header, cursor="hand2")
        self.conn.pack(side="right", padx=(0, 8))
        self.conn_dot = tk.Label(self.conn, text="●", font=("Segoe UI", 8))
        self.conn_dot.pack(side="left", padx=(8, 4))
        self.conn_label = tk.Label(self.conn, textvariable=self.device_var, font=UI_FONT)
        self.conn_label.pack(side="left", padx=(0, 10))
        for widget in (self.conn, self.conn_dot, self.conn_label):
            widget.bind("<Button-1>", lambda _event: self.presenter.check_connection())

        self.side = tk.Frame(self.body, highlightthickness=1)
        self.side.grid(row=1, column=0, sticky="nsew", padx=(0, 12))
        self.side.columnconfigure(0, weight=1)

        self.mode_tabs = tk.Frame(self.side, highlightthickness=0, bd=0)
        self.mode_tabs.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 0))
        tabs = self.mode_tabs
        self._mode_buttons = {}
        self._mode_lines = {}
        for label, mode in (("Câu cá", "fish"), ("Rally", "rally"), ("Quét ID", "scan"), ("Danh sách", "list")):
            self._mode_buttons[mode], self._mode_lines[mode] = self._mode_tab(tabs, label, mode)
        self.list_seg = self._mode_buttons["list"]
        self.scan_seg = self._mode_buttons["scan"]
        self.rally_seg = self._mode_buttons["rally"]
        self.fish_seg = self._mode_buttons["fish"]
        self._segments = (self.fish_seg, self.rally_seg, self.scan_seg, self.list_seg)

        self.hint_label = tk.Label(self.side, textvariable=self.hint_var, font=("Segoe UI", 9), wraplength=HINT_WRAP, justify="left", anchor="w")
        self.hint_label.grid(row=1, column=0, sticky="ew", padx=14, pady=(10, 0))

        self.card = tk.Frame(self.side)
        self.card.grid(row=2, column=0, sticky="ew", padx=14, pady=(12, 0))
        self.fish_page = self._fish_form(self.card, fish_max, fish_multipliers)
        self.rally_page = self._rally_form(self.card)
        self.scan_page = self._scan_form(self.card, scan_max)
        self.list_page = self._list_form(self.card)

        self.warn_label = tk.Label(self.side, text="Đang chạy: đừng bấm vào emulator.", font=("Segoe UI", 9), anchor="w", justify="left", wraplength=HINT_WRAP)
        self.warn_label.grid(row=3, column=0, sticky="ew", padx=14, pady=(12, 0))
        self.warn_label.grid_remove()

        self.primary_btn = tk.Button(
            self.side, text=START_LABEL, font=GO_FONT, relief="flat", bd=0, command=self._on_go, cursor="hand2"
        )
        self.primary_btn.grid(row=4, column=0, sticky="ew", padx=14, pady=(12, 0), ipady=6)

        self.tools_btn = tk.Button(self.side, text="Công cụ ▾", font=UI_FONT, relief="flat", bd=0, anchor="w", command=self._toggle_tools, cursor="hand2")
        self.tools_btn.grid(row=5, column=0, sticky="ew", padx=14, pady=(8, 0), ipady=4)
        self.tool_menu = tk.Frame(self.side, highlightthickness=1)
        self.capture_btn = tk.Button(self.tool_menu, text="Chụp thử", font=UI_FONT, relief="flat", bd=0, anchor="w", command=lambda: self._tool(self.presenter.capture_only))
        self.preview_btn = tk.Button(self.tool_menu, text="Kiểm tra nút", font=UI_FONT, relief="flat", bd=0, anchor="w", command=lambda: self._tool(self.presenter.preview))
        self.logs_btn = tk.Button(self.tool_menu, text="Mở thư mục log", font=UI_FONT, relief="flat", bd=0, anchor="w", command=lambda: self._tool(self.presenter.open_logs))
        for button in (self.capture_btn, self.preview_btn, self.logs_btn):
            button.pack(fill="x", ipady=4)

        self.toast_label = tk.Label(self.side, textvariable=self.toast_var, font=("Segoe UI", 9), anchor="w", justify="left", wraplength=HINT_WRAP)
        self.toast_label.grid(row=6, column=0, sticky="ew", padx=14, pady=(8, 12))

        self.main = tk.Frame(self.body, highlightthickness=1)
        self.main.grid(row=1, column=1, sticky="nsew")
        self.main.columnconfigure(0, weight=1)
        self.main.rowconfigure(4, weight=1)

        self.progress = tk.Frame(self.main)
        self.progress.grid(row=0, column=0, sticky="ew", padx=14, pady=(14, 0))
        progress = self.progress
        progress.columnconfigure(1, weight=1)
        self.progress_label = tk.Label(progress, textvariable=self.progress_var, font=("Segoe UI", 10, "bold"), anchor="w")
        self.progress_label.grid(row=0, column=0, sticky="w")
        self.bar = tk.Canvas(progress, height=8, highlightthickness=0, bd=0)
        self.bar.grid(row=0, column=1, sticky="ew", padx=10)
        self.bar.bind("<Configure>", lambda _event: self._draw_bar())
        self.percent_label = tk.Label(progress, textvariable=self.percent_var, font=UI_FONT)
        self.percent_label.grid(row=0, column=2, sticky="e")
        self.step_label = tk.Label(self.main, textvariable=self.step_var, font=("Segoe UI", 9), anchor="w")
        self.step_label.grid(row=1, column=0, sticky="ew", padx=14, pady=(4, 0))
        self.hold_banner = tk.Label(
            self.main,
            text="Đã dừng. Đang câu nốt con cá này.",
            font=("Segoe UI", 10, "bold"),
            anchor="w",
        )
        self.hold_banner.grid(row=2, column=0, sticky="ew", padx=14, pady=(8, 0), ipady=6, ipadx=8)
        self.hold_banner.grid_remove()

        self.tiles_row = tk.Frame(self.main)
        self.tiles_row.grid(row=3, column=0, sticky="ew", padx=14, pady=(10, 0))
        self.tile_order = ("Lượt", "Thành công", "Thất bại", "Gold", "Rod còn", "Đã xin", "Quà", "UID", "Pinball")
        self.tiles = {}
        for index, name in enumerate(self.tile_order):
            self.tiles_row.columnconfigure(index, weight=1)
            box = tk.Frame(self.tiles_row, highlightthickness=1)
            box.grid(row=0, column=index, sticky="ew", padx=(0 if index == 0 else 8, 0))
            value = tk.Label(box, text="0", font=TILE_FONT, anchor="w")
            value.pack(anchor="w", padx=10, pady=(8, 0))
            caption = tk.Label(box, text=name, font=("Segoe UI", 9), anchor="w")
            caption.pack(anchor="w", padx=10, pady=(0, 8))
            self.tiles[name] = (box, value, caption)
        self._tile_tones = {name: "gold" if name == "Gold" else "text" for name in self.tile_order}

        self.views = tk.Frame(self.main)
        self.views.grid(row=4, column=0, sticky="nsew", padx=14, pady=(12, 14))
        views = self.views
        views.columnconfigure(0, weight=1)
        views.rowconfigure(1, weight=1)
        self.view_switch = tk.Frame(views)
        self.view_switch.grid(row=0, column=0, sticky="ew")
        switch = self.view_switch
        self.result_tab, self.result_line = self._view_tab(switch, "Kết quả", "result")
        self.log_tab, self.log_line = self._view_tab(switch, "Log chi tiết", "log")

        self.result_pane = tk.Frame(views, highlightthickness=1)
        self.result_pane.grid(row=1, column=0, sticky="nsew", pady=(8, 0))
        self.result_pane.columnconfigure(0, weight=1)
        self.result_pane.rowconfigure(0, weight=1)
        self.results = ttk.Treeview(self.result_pane, columns=("a", "b", "c"), show="headings", style="App.Treeview")
        self.results.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(self.result_pane, command=self.results.yview)
        self.results.configure(yscrollcommand=scroll.set)
        scroll.grid(row=0, column=1, sticky="ns")
        self.set_columns(("Lượt", "Kết quả", "Gold"))

        self.log_pane = tk.Frame(views, highlightthickness=1)
        self.log_pane.columnconfigure(0, weight=1)
        self.log_pane.rowconfigure(0, weight=1)
        self.log_scroll = ttk.Scrollbar(self.log_pane)
        self._new_log_box()
        self.log_scroll.grid(row=0, column=1, sticky="ns")

        tools = tk.Frame(views)
        self.log_tools = tools
        self.copy_btn = tk.Button(tools, text="Copy", font=UI_FONT, relief="flat", bd=0, command=self.copy_log, cursor="hand2")
        self.copy_btn.pack(side="right")
        self.clear_btn = tk.Button(tools, text="Xóa", font=UI_FONT, relief="flat", bd=0, command=self.clear_log, cursor="hand2")
        self.clear_btn.pack(side="right", padx=(0, 6))
        self._view_name = "result"
        self._show_view("result")

    def _build_settings(self, header: tk.Frame) -> None:
        icon_font, icon = self._settings_icon()
        self.settings_btn = tk.Button(
            header,
            text=icon,
            font=icon_font,
            relief="flat",
            bd=0,
            command=self._toggle_settings,
            cursor="hand2",
            padx=10,
            pady=2,
        )
        self.settings_btn.pack(side="right")

        menu = tk.Frame(self.body, highlightthickness=1)
        self.settings_menu = menu
        self.settings_title = tk.Label(menu, text="Cài đặt", font=("Segoe UI", 12, "bold"), anchor="w")
        self.settings_title.pack(fill="x", padx=14, pady=(12, 10))
        self.settings_rule = self._settings_rule(menu)

        body = tk.Frame(menu)
        self.settings_body = body
        body.pack(fill="x", padx=14, pady=(12, 4))

        self.theme_caption = tk.Label(body, text="Giao diện", font=("Segoe UI", 9), anchor="w")
        self.theme_caption.pack(anchor="w")
        choice = tk.Frame(body)
        choice.pack(fill="x", pady=(6, 14))
        choice.columnconfigure((0, 1, 2), weight=1, uniform="theme")
        self._theme_choice = choice
        self.theme_light_btn = self._theme_button(choice, "Sáng", "light")
        self.theme_dark_btn = self._theme_button(choice, "Tối", "dark")
        self.theme_system_btn = self._theme_button(choice, "Theo máy", "system")
        self.theme_light_btn.grid(row=0, column=0, sticky="nsew")
        self.theme_dark_btn.grid(row=0, column=1, sticky="nsew", padx=6)
        self.theme_system_btn.grid(row=0, column=2, sticky="nsew")

        self.log_caption = tk.Label(body, text="Log", font=("Segoe UI", 9), anchor="w")
        self.log_caption.pack(anchor="w")
        self.auto_row, self.auto_label, self.auto_check = self._setting_switch(
            body, "Tự cuộn xuống cuối", self.auto_var, self._toggle_auto,
        )
        self.debug_row, self.debug_label, self.debug_check = self._setting_switch(
            body, "Hiện chi tiết bấm", self.debug_var, self._toggle_debug,
        )

        self.data_caption = tk.Label(body, text="Dữ liệu", font=("Segoe UI", 9), anchor="w")
        self.data_caption.pack(anchor="w", pady=(12, 0))
        self.open_log_btn = self._settings_action(body, "Mở thư mục log", self._open_log_folder)
        self.purge_btn = self._settings_action(body, "Xóa cache", self.purge_log)
        self._refresh_cache_label()

        self.settings_rule_bottom = self._settings_rule(menu)
        self.version_label = tk.Label(menu, text=f"Phiên bản {APP_VERSION}", font=("Segoe UI", 9), anchor="w")
        self.version_label.pack(fill="x", padx=14, pady=(8, 12))

    def _settings_rule(self, parent: tk.Frame) -> tk.Frame:
        rule = tk.Frame(parent, height=1, bd=0, highlightthickness=0)
        rule.pack(fill="x")
        rule.pack_propagate(False)
        return rule

    def _theme_button(self, parent: tk.Frame, text: str, mode: str) -> tk.Button:
        return tk.Button(
            parent, text=text, font=UI_FONT, relief="flat", bd=0, padx=4, pady=4, cursor="hand2",
            command=lambda: self._pick_theme(mode),
        )

    def _setting_switch(self, parent: tk.Frame, text: str, variable: tk.BooleanVar, command):
        row = tk.Frame(parent)
        row.pack(fill="x", pady=(6, 0))
        label = tk.Label(row, text=text, font=UI_FONT, anchor="w")
        label.pack(side="left")
        check = tk.Checkbutton(
            row, text="", variable=variable, command=command,
            bd=0, highlightthickness=0, padx=0, pady=0, cursor="hand2",
        )
        check.pack(side="right")
        return row, label, check

    def _settings_action(self, parent: tk.Frame, text: str, command) -> tk.Button:
        button = tk.Button(
            parent, text=text, font=UI_FONT, relief="flat", bd=0, anchor="w",
            cursor="hand2", highlightthickness=1, padx=10, command=command,
        )
        button.pack(fill="x", pady=(6, 0), ipady=4)
        return button

    def _settings_icon(self) -> tuple[tuple[str, int], str]:
        import tkinter.font as tkfont

        if "Segoe MDL2 Assets" in set(tkfont.families()):
            return ("Segoe MDL2 Assets", 14), "\uE713"
        return ("Segoe UI Symbol", 14), "\u2699"

    def _new_log_box(self) -> None:
        """Tạo lại ô log. Hủy ô cũ để Tcl trả bộ nhớ của toàn bộ dòng đã ghi."""
        old = getattr(self, "log_box", None)
        if old is not None and old.winfo_exists():
            old.destroy()
        self.log_box = tk.Text(self.log_pane, font=LOG_FONT, wrap="word", relief="flat", bd=0, state="disabled")
        self.log_scroll.configure(command=self.log_box.yview)
        self.log_box.configure(yscrollcommand=self.log_scroll.set)
        self.log_box.grid(row=0, column=0, sticky="nsew")
        self.detail_box = self.log_box

    def _mode_tab(self, parent, text: str, mode: str):
        cell = tk.Frame(parent)
        cell.pack(side="left", padx=(0, 2))
        button = tk.Button(
            cell, text=text, font=UI_FONT, relief="flat", bd=0, cursor="hand2", padx=8, pady=4,
            command=lambda: self.presenter.select(mode),
        )
        button.pack(fill="x")
        line = tk.Frame(cell, height=2, bd=0, highlightthickness=0)
        line.pack(fill="x")
        line.pack_propagate(False)
        return button, line

    def _view_tab(self, parent, text: str, name: str):
        cell = tk.Frame(parent)
        cell.pack(side="left", padx=(0, 8))
        button = tk.Button(
            cell, text=text, font=UI_FONT, relief="flat", bd=0, cursor="hand2", padx=8, pady=4,
            command=lambda: self._show_view(name),
        )
        button.pack(fill="x")
        line = tk.Frame(cell, height=2, bd=0, highlightthickness=0)
        line.pack(fill="x")
        line.pack_propagate(False)
        return button, line

    def _fish_form(self, parent, fish_max: int, multipliers: tuple[str, ...]) -> tk.Frame:
        page = tk.Frame(parent)
        tk.Label(page, text="Số lượt câu", font=("Segoe UI", 9)).pack(anchor="w")
        self.fish_casts = ttk.Spinbox(page, from_=1, to=fish_max, font=ID_FONT, textvariable=self.fish_casts_var, style="App.TSpinbox")
        self.fish_casts.pack(fill="x", pady=(4, 10))
        row = tk.Frame(page)
        row.pack(fill="x")
        row.columnconfigure(0, weight=1)
        tk.Label(row, text="Hệ số", font=("Segoe UI", 9)).grid(row=0, column=0, sticky="w")
        self.fish_mult = ttk.Combobox(
            row,
            values=tuple(f"x{item}" for item in multipliers),
            font=ID_FONT,
            textvariable=self.fish_mult_var,
            state="readonly",
            style="App.TCombobox",
        )
        self.fish_mult.grid(row=1, column=0, sticky="ew", pady=(4, 0))
        self.help_btn = tk.Button(row, text="?", font=UI_FONT, width=3, relief="flat", bd=0, cursor="hand2")
        self.help_btn.grid(row=1, column=1, padx=(8, 0), pady=(4, 0))
        self.help_tip = tk.Label(
            page,
            text="Hệ số xN tốn N rod mỗi lần quăng. Bấm Dừng khi đang câu thì câu nốt lượt đó rồi mới dừng. Hết lượt hoặc hết rod cũng dừng. Game hiện có đến x100.",
            font=("Segoe UI", 9),
            wraplength=240,
            justify="left",
        )
        self.help_btn.bind("<Enter>", lambda _event: self.help_tip.pack(anchor="w", pady=(8, 0)))
        self.help_btn.bind("<Leave>", lambda _event: self.help_tip.pack_forget())
        return page

    def _rally_form(self, parent) -> tk.Frame:
        page = tk.Frame(parent)
        for text in (
            "Bấm Join xanh trong chat Frostnip League.",
            "Không tạo rally và không bấm nút xám.",
            "Chạy đến khi bấm Dừng.",
        ):
            tk.Label(page, text=text, font=UI_FONT, anchor="w", justify="left", wraplength=HINT_WRAP).pack(anchor="w", pady=(0, 6))
        return page

    def _scan_form(self, parent, scan_max: int) -> tk.Frame:
        page = tk.Frame(parent)
        page.columnconfigure(0, weight=1)
        tk.Label(page, text="ID đầu", font=("Segoe UI", 9)).grid(row=0, column=0, sticky="w")
        tk.Label(page, text="Số lần", font=("Segoe UI", 9)).grid(row=0, column=1, sticky="w", padx=(8, 0))
        self.scan_start = ttk.Entry(page, font=ID_FONT, textvariable=self.scan_start_var, style="App.TEntry")
        self.scan_start.grid(row=1, column=0, sticky="ew", pady=(4, 0))
        self.scan_count = ttk.Spinbox(page, from_=1, to=scan_max, font=ID_FONT, width=8, textvariable=self.scan_count_var, style="App.TSpinbox")
        self.scan_count.grid(row=1, column=1, sticky="ew", padx=(8, 0), pady=(4, 0))
        return page

    def _list_form(self, parent) -> tk.Frame:
        page = tk.Frame(parent)
        tk.Label(page, text="Mỗi dòng một UID", font=("Segoe UI", 9)).pack(anchor="w")
        self.ids = tk.Text(page, height=UID_BOX_LINES, font=ID_FONT, relief="flat", bd=0, wrap="none")
        self.ids.pack(fill="x", pady=(4, 0))
        self.ids.bind("<<Modified>>", self._ids_changed)
        tk.Label(page, textvariable=self.id_summary, font=("Segoe UI", 9), anchor="w").pack(anchor="w", pady=(6, 0))
        self.load_btn = tk.Button(page, text="Nạp file txt", font=UI_FONT, relief="flat", bd=0, command=lambda: self.presenter.load_file(), cursor="hand2")
        self.load_btn.pack(anchor="w", pady=(8, 0))
        return page

    def show_mode(self, mode: str) -> None:
        """Đổi tab và form bên trái. Presenter quyết định có được đổi hay không."""
        self.mode_var.set(mode)
        for page in (self.fish_page, self.rally_page, self.scan_page, self.list_page):
            page.pack_forget()
        titles = {"fish": "Tự câu cá", "rally": "Auto join rally", "scan": "Quét ID", "list": "Nhận quà"}
        hints = {"fish": FISH_HINT, "rally": RALLY_HINT, "scan": SCAN_HINT, "list": GIFT_HINT}
        columns = {
            "fish": ("Lượt", "Kết quả", "Gold"),
            "rally": ("Lần", "Việc", ""),
            "scan": ("UID", "Kết quả", "Ghi chú"),
            "list": ("UID", "Kết quả", "Ghi chú"),
        }
        tiles = {
            "fish": ("Lượt", "Thành công", "Thất bại", "Gold", "Rod còn"),
            "rally": ("Đã xin",),
            "scan": ("Quà", "UID", "Pinball"),
            "list": ("Quà", "UID", "Pinball"),
        }
        page = {"fish": self.fish_page, "rally": self.rally_page, "scan": self.scan_page, "list": self.list_page}[mode]
        page.pack(fill="x")
        self.title_var.set(titles[mode])
        self.hint_var.set(hints[mode])
        self.root.title(titles[mode])
        self.set_columns(columns[mode])
        self._show_tiles(tiles[mode])
        self.clear_results()
        self._mark_mode(mode)

    def _mark_mode(self, mode: str) -> None:
        colors = self.colors
        for name, button in self._mode_buttons.items():
            selected = name == mode
            button.configure(
                fg=colors["text"] if selected else colors["mute"],
                bg=colors["panel"],
                activebackground=colors["panel"],
                font=("Segoe UI", 10, "bold") if selected else UI_FONT,
            )
            line = self._mode_lines[name]
            line.configure(bg=colors["acc"] if selected else colors["panel"])
            line.master.configure(bg=colors["panel"])

    def _show_tiles(self, names: tuple[str, ...]) -> None:
        column = 0
        for name in self.tile_order:
            box, value, _caption = self.tiles[name]
            if name in names:
                box.grid(row=0, column=column, sticky="ew", padx=(0 if column == 0 else 8, 0))
                tone = "gold" if name == "Gold" else "text"
                self._tile_tones[name] = tone
                value.configure(
                    text="—" if name == "Rod còn" else "0",
                    fg=self.colors[tone],
                )
                column += 1
            else:
                box.grid_remove()
        for index in range(len(self.tile_order)):
            self.tiles_row.columnconfigure(index, weight=1 if index < max(column, 1) else 0)

    def set_columns(self, headers: tuple[str, str, str]) -> None:
        widths = (80, 160, 120)
        for key, title, width in zip(("a", "b", "c"), headers, widths):
            self.results.heading(key, text=title)
            self.results.column(key, width=width, anchor="w", stretch=key == "b")

    def set_action(self, _text: str) -> None:
        """Nút chạy luôn là Bắt đầu hoặc Dừng, không đổi theo số lượt."""
        if not self.presenter.running:
            self.primary_btn.configure(text=START_LABEL)

    def set_id_summary(self, text: str) -> None:
        self.id_summary.set(text)

    def set_locked(self, locked: bool) -> None:
        state = "disabled" if locked else "normal"
        for widget in (self.load_btn, self.capture_btn, self.preview_btn):
            widget.configure(state=state)
        # Không tắt ô nhập bằng state disabled: theme clam sẽ tô nền be và sọc xám.
        self._inputs_locked = locked
        for widget in (self.scan_start, self.scan_count, self.fish_casts, self.fish_mult):
            if locked:
                widget.bind("<Button-1>", self._block_input)
                widget.bind("<Key>", self._block_input)
                widget.bind("<MouseWheel>", self._block_input)
            else:
                widget.unbind("<Button-1>")
                widget.unbind("<Key>")
                widget.unbind("<MouseWheel>")
        self.ids.configure(state=state)
        for button in self._segments:
            button.configure(state=state)
        if not locked:
            self._fish_hold = False
            self.hold_banner.grid_remove()
        self.primary_btn.configure(
            text=HOLD_LABEL if self._fish_hold else (STOP_LABEL if locked else START_LABEL),
            cursor="arrow" if self._fish_hold else "hand2",
        )
        if locked:
            self.warn_label.grid()
        else:
            self.warn_label.grid_remove()
        self._paint()

    def set_status(self, step: str, stats: list[str]) -> None:
        stats = list(stats)

        def apply(step: str = step, stats: list[str] = stats) -> None:
            self.step_var.set(step)
            progress = None
            for item in stats:
                if item.startswith("Lượt ") and "/" in item:
                    current, total = item.split(" ", 1)[1].split("/", 1)
                    self._tile("Lượt", current)
                    progress = (self._number(current), self._number(total), f"Lượt {current}/{total}")
                elif item.startswith("Được "):
                    self._tile("Thành công", item.split(" ", 1)[1], "ok")
                elif item.startswith("Thất bại "):
                    self._tile("Thất bại", item.removeprefix("Thất bại "), "err")
                elif item.startswith("Gold "):
                    self._tile("Gold", item.split(" ", 1)[1], "gold")
                elif item.startswith("Rod "):
                    self._tile("Rod còn", item.split(" ", 1)[1])
                elif item.startswith("Quà "):
                    value = item.split(" ", 1)[1]
                    self._tile("Quà", value, "ok")
                    if "/" in value:
                        current, total = value.split("/", 1)
                        progress = (self._number(current), self._number(total), f"Quà {value}")
                elif item.startswith("UID "):
                    value = item.split(" ", 1)[1]
                    self._tile("UID", value)
                    if "/" in value:
                        current, total = value.split("/", 1)
                        progress = (self._number(current), self._number(total), f"UID {value}")
                elif item.startswith("Pinball "):
                    self._tile("Pinball", item.split(" ", 1)[1])
                elif item.startswith("Đã xin "):
                    value = item.split(" ", 1)[1]
                    self._tile("Đã xin", value, "ok")
                    progress = (self._number(value), 0, f"Đã xin {value}")
            if progress is None:
                self._set_bar(step, 0, 0)
            else:
                self._set_bar(progress[2], progress[0], progress[1])

        self.invoke(apply)

    def set_fish_hold(self, holding: bool) -> None:
        """Dải và nút giữ nguyên khi đã bấm Dừng nhưng lượt câu đang dở chưa xong."""

        def apply() -> None:
            self._fish_hold = holding
            if holding:
                self.hold_banner.grid()
                self.primary_btn.configure(text=HOLD_LABEL, cursor="arrow")
            else:
                self.hold_banner.grid_remove()
                self.primary_btn.configure(
                    text=STOP_LABEL if self.presenter.running else START_LABEL,
                    cursor="hand2",
                )
            self._paint()

        self.invoke(apply)

    def set_device(self, serial: str) -> None:
        def apply() -> None:
            self.device_var.set(serial)
            self.conn_dot.configure(fg=self.colors["ok"])

        self.invoke(apply)

    def set_offline(self) -> None:
        def apply() -> None:
            self.device_var.set("Chưa nối")
            self.conn_dot.configure(fg=self.colors["err"])

        self.invoke(apply)

    def toast(self, text: str) -> None:
        def apply() -> None:
            self.toast_var.set(text)
            if self._toast_after is not None:
                self.root.after_cancel(self._toast_after)
            self._toast_after = self.root.after(2500, lambda: self.toast_var.set(""))

        self.invoke(apply)

    def append_overview(self, message: str) -> None:
        self.append_log(message)

    def append_detail(self, message: str) -> None:
        level = "dbg" if message.startswith(" ") else "text"
        self.append_log(message.strip(), level)

    def _insert_message(self, message: str, chosen: str) -> None:
        """Số Gold trong log tô vàng, phần còn lại giữ màu của dòng."""
        import re

        cursor = 0
        for match in re.finditer(r"\+?\d[\d.]*\s*Gold", message):
            if match.start() > cursor:
                self.log_box.insert("end", message[cursor:match.start()], chosen)
            self.log_box.insert("end", match.group(), "gold")
            cursor = match.end()
        if cursor < len(message):
            self.log_box.insert("end", message[cursor:], chosen)

    def append_log(self, message: str, level: str | None = None) -> None:
        chosen = level or log_tone(message)

        def apply(message: str = message, chosen: str = chosen) -> None:
            stamp = self._clock()
            self.log_box.configure(state="normal")
            start = self.log_box.index("end-1c")
            if chosen == "turn" and message.startswith("Lượt "):
                head, sep, tail = message.partition(":")
                self.log_box.insert("end", head.strip() + "\n", ("turn", "mid"))
                if sep and tail.strip():
                    self.log_box.insert("end", f"[{stamp}] ", "time")
                    self._insert_message(tail.strip(), "text")
                    self.log_box.insert("end", "\n")
            else:
                self.log_box.insert("end", f"[{stamp}] ", "time")
                self._insert_message(message, chosen)
                self.log_box.insert("end", "\n")
            if chosen == "dbg" and not self._show_debug:
                self.log_box.tag_add("hidden", start, "end-1c")
            if self._auto_scroll:
                self.log_box.see("end")
            self.log_box.configure(state="disabled")

        self.invoke(apply)

    def clear_overview(self) -> None:
        self.clear_results()

    def clear_detail(self) -> None:
        self.clear_log()

    def clear_log(self) -> None:
        def apply() -> None:
            self.log_box.configure(state="normal")
            self.log_box.delete("1.0", "end")
            self.log_box.configure(state="disabled")

        self.invoke(apply)

    def purge_log(self) -> None:
        """Xóa file log đã sinh và log đang hiện. Giữ file cài đặt."""
        self._close_settings()
        if self.presenter.running:
            self.toast("Đang chạy, hãy dừng trước khi xóa cache.")
            return
        size = _format_size(_cache_bytes())
        agreed = messagebox.askyesno(
            "Xóa cache",
            f"Xóa cache ({size})? Ảnh chụp và file log sẽ bị xóa. Cài đặt giữ nguyên.",
            parent=self.root,
        )
        if not agreed:
            return
        _delete_cache()
        self._release_log_memory()

    def _release_log_memory(self) -> None:
        def apply() -> None:
            self._new_log_box()
            children = self.results.get_children()
            for start in range(0, len(children), 400):
                self.results.delete(*children[start : start + 400])
            self._row_seq = 0
            self._paint()
            gc.collect()
            self.toast("Đã xóa cache.")
            self._refresh_cache_label()

        self.invoke(apply)

    def clear_results(self) -> None:
        def apply() -> None:
            children = self.results.get_children()
            if children:
                self.results.delete(*children)

        self.invoke(apply)

    def add_result(self, values: tuple[str, str, str]) -> str:
        self._row_seq += 1
        iid = f"r{self._row_seq}"
        vals = tuple(values)

        def apply(iid: str = iid, vals: tuple[str, str, str] = vals) -> None:
            self.results.insert("", 0, iid=iid, values=vals, tags=("run",))

        self.invoke(apply)
        return iid

    def finish_result(self, iid: str, values: tuple[str, str, str], tone: str) -> None:
        if not iid:
            return
        vals = tuple(values)

        def apply(iid: str = iid, vals: tuple[str, str, str] = vals, tone: str = tone) -> None:
            if self.results.exists(iid):
                self.results.item(iid, values=vals, tags=(tone,))

        self.invoke(apply)

    def copy_log(self) -> None:
        text = self.log_box.get("1.0", "end").strip()
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.toast("Đã copy log.")

    def gift_ids_text(self) -> str:
        return self.ids.get("1.0", "end")

    def set_ids(self, content: str) -> None:
        self.ids.delete("1.0", "end")
        self.ids.insert("1.0", content)

    def scan_start_text(self) -> str:
        return self.scan_start_var.get()

    def scan_count_text(self) -> str:
        return self.scan_count_var.get()

    def fish_casts_text(self) -> str:
        return self.fish_casts_var.get()

    def fish_multiplier_text(self) -> str:
        return self.fish_mult_var.get()

    def set_fish_casts(self, text: str) -> None:
        self.fish_casts_var.set(text)

    def set_fish_multiplier(self, text: str) -> None:
        raw = text.strip().lower().lstrip("x") or "1"
        self.fish_mult_var.set(f"x{raw}")

    def choose_text_file(self) -> str:
        return filedialog.askopenfilename(filetypes=[("Text", "*.txt"), ("Tất cả", "*.*")])

    def bind_close(self, callback) -> None:
        def close() -> None:
            callback()
            self.root.destroy()

        self.root.protocol("WM_DELETE_WINDOW", close)

    def watch_form(self, callback) -> None:
        for var in (self.scan_start_var, self.scan_count_var, self.fish_casts_var, self.fish_mult_var):
            var.trace_add("write", lambda *_args: callback())

    def toggle_theme(self) -> None:
        self._pick_theme("dark" if self.theme_name == "light" else "light")

    def _pick_theme(self, name: str) -> None:
        if name == self.theme_mode:
            return
        self.set_theme(name)
        self.presenter.on_theme()

    def set_theme(self, name: str) -> None:
        self.theme_mode = name if name in ("light", "dark", "system") else "light"
        self.theme_name = _resolved_theme(self.theme_mode)
        self.colors = dict(DARK if self.theme_name == "dark" else LIGHT)
        self._paint()

    def _follow_system_theme(self, _event=None) -> None:
        if self.theme_mode != "system":
            return
        applied = _resolved_theme("system")
        if applied == self.theme_name:
            return
        self.theme_name = applied
        self.colors = dict(DARK if applied == "dark" else LIGHT)
        self._paint()

    def _open_log_folder(self) -> None:
        self._close_settings()
        self.presenter.open_logs()

    def _refresh_cache_label(self) -> None:
        self.purge_btn.configure(text=f"Xóa cache ({_format_size(_cache_bytes())})")

    def invoke(self, fn) -> None:
        """Việc đụng widget từ luồng chạy phải xếp hàng về luồng cửa sổ."""
        if threading.current_thread() is threading.main_thread():
            fn()
        else:
            self.root.after(0, fn)

    def _block_input(self, _event=None) -> str:
        return "break"

    def _on_go(self) -> None:
        if self.presenter.running:
            self.presenter.request_stop()
        else:
            self.presenter.run_current()

    def _tool(self, action) -> None:
        self._close_tools()
        action()

    def _toggle_tools(self) -> None:
        if self._tools_open:
            self._close_tools()
            return
        self._close_settings()
        self.tool_menu.place(in_=self.tools_btn, relx=0, rely=0, anchor="sw", relwidth=1.0)
        self.tool_menu.lift()
        self._tools_open = True

    def _close_tools(self) -> None:
        self.tool_menu.place_forget()
        self._tools_open = False

    def _toggle_settings(self) -> None:
        if self._settings_open:
            self._close_settings()
            return
        self._close_tools()
        self._refresh_cache_label()
        self.settings_menu.place(in_=self.settings_btn, relx=1.0, rely=1.0, anchor="ne", y=6, width=320)
        self.settings_menu.lift()
        self._settings_open = True

    def _close_settings(self) -> None:
        self.settings_menu.place_forget()
        self._settings_open = False

    def _dismiss_tools(self, event) -> None:
        widget = event.widget
        inside_tools = False
        inside_settings = False
        while widget is not None:
            if widget in (self.tool_menu, self.tools_btn):
                inside_tools = True
            if widget in (self.settings_menu, self.settings_btn):
                inside_settings = True
            widget = getattr(widget, "master", None)
        if self._tools_open and not inside_tools:
            self._close_tools()
        if self._settings_open and not inside_settings:
            self._close_settings()

    def _show_view(self, name: str) -> None:
        colors = self.colors
        self._view_name = name
        selected = name == "result"
        self.result_tab.configure(
            fg=colors["text"] if selected else colors["mute"],
            bg=colors["panel"],
            activebackground=colors["panel"],
            font=("Segoe UI", 10, "bold" if selected else "normal"),
        )
        self.log_tab.configure(
            fg=colors["mute"] if selected else colors["text"],
            bg=colors["panel"],
            activebackground=colors["panel"],
            font=("Segoe UI", 10, "bold" if not selected else "normal"),
        )
        self.result_line.configure(bg=colors["acc"] if selected else colors["panel"])
        self.log_line.configure(bg=colors["panel"] if selected else colors["acc"])
        self.result_line.master.configure(bg=colors["panel"])
        self.log_line.master.configure(bg=colors["panel"])
        if selected:
            self.log_pane.grid_remove()
            self.log_tools.grid_remove()
            self.result_pane.grid(row=1, column=0, sticky="nsew", pady=(8, 0))
        else:
            self.result_pane.grid_remove()
            self.log_pane.grid(row=1, column=0, sticky="nsew", pady=(8, 0))
            self.log_tools.grid(row=2, column=0, sticky="ew", pady=(8, 0))

    def _toggle_debug(self) -> None:
        self._show_debug = bool(self.debug_var.get())
        self.log_box.tag_configure("hidden", elide=not self._show_debug)
        self.presenter.on_option_changed()

    def _toggle_auto(self) -> None:
        self._auto_scroll = bool(self.auto_var.get())
        self.presenter.on_option_changed()

    def _ids_changed(self, _event=None) -> None:
        if self._ids_guard:
            return
        self._ids_guard = True
        try:
            if self.ids.edit_modified():
                self.ids.edit_modified(False)
            self.presenter.on_form_changed()
        finally:
            self._ids_guard = False

    def _tile(self, name: str, value: str, tone: str = "text") -> None:
        if name not in self.tiles:
            return
        _box, label, _caption = self.tiles[name]
        self._tile_tones[name] = tone
        label.configure(text=value, fg=self.colors.get(tone, self.colors["text"]))

    def _set_bar(self, label: str, current: int, total: int) -> None:
        self._bar_current = current
        self._bar_total = total
        self.progress_var.set(label)
        if total <= 0:
            self.percent_var.set("0%")
        else:
            self.percent_var.set(f"{round(current / total * 100)}%")
        self._draw_bar()

    def _draw_bar(self) -> None:
        width = max(self.bar.winfo_width(), 1)
        height = 8
        colors = self.colors
        self.bar.delete("all")
        self.bar.configure(bg=colors["tile"])
        self.bar.create_rectangle(0, 0, width, height, fill=colors["tile"], outline=colors["line"])
        if self._bar_total > 0 and self._bar_current > 0:
            filled = max(2, int(width * min(self._bar_current, self._bar_total) / self._bar_total))
            fill = colors["warn"] if self._fish_hold else colors["acc"]
            self.bar.create_rectangle(0, 0, filled, height, fill=fill, outline="")

    def _number(self, text: str) -> int:
        digits = "".join(char for char in text if char.isdigit())
        return int(digits) if digits else 0

    def _clock(self) -> str:
        import datetime

        now = datetime.datetime.now()
        return f"{now:%H:%M:%S}"

    def _paint_settings(self, colors: dict[str, str]) -> None:
        self.settings_btn.configure(
            bg=colors["panel"],
            fg=colors["text"],
            activebackground=colors["tile"],
            activeforeground=colors["text"],
            highlightbackground=colors["line"],
            highlightthickness=1,
        )
        self.settings_menu.configure(bg=colors["panel"], highlightbackground=colors["line"])
        self.settings_body.configure(bg=colors["panel"])
        self.settings_title.configure(bg=colors["panel"], fg=colors["text"])
        self.version_label.configure(bg=colors["panel"], fg=colors["mute"])
        for rule in (self.settings_rule, self.settings_rule_bottom):
            rule.configure(bg=colors["line"])
        for caption in (self.theme_caption, self.log_caption, self.data_caption):
            caption.configure(bg=colors["panel"], fg=colors["mute"])
        self._theme_choice.configure(bg=colors["panel"])
        for name, button in (
            ("light", self.theme_light_btn),
            ("dark", self.theme_dark_btn),
            ("system", self.theme_system_btn),
        ):
            on = self.theme_mode == name
            button.configure(
                bg=colors["acc"] if on else colors["tile"],
                fg=colors["acc_t"] if on else colors["text"],
                activebackground=colors["acc"] if on else colors["tile"],
                activeforeground=colors["acc_t"] if on else colors["text"],
                highlightthickness=0,
            )
        for row, label, check in (
            (self.auto_row, self.auto_label, self.auto_check),
            (self.debug_row, self.debug_label, self.debug_check),
        ):
            row.configure(bg=colors["panel"])
            label.configure(bg=colors["panel"], fg=colors["text"])
            check.configure(
                bg=colors["panel"],
                fg=colors["text"],
                activebackground=colors["panel"],
                activeforeground=colors["text"],
                selectcolor=colors["panel"],
                highlightthickness=0,
            )
        for button in (self.open_log_btn, self.purge_btn):
            button.configure(
                bg=colors["panel"],
                fg=colors["text"],
                activebackground=colors["tile"],
                activeforeground=colors["text"],
                highlightbackground=colors["line"],
                highlightthickness=1,
                highlightcolor=colors["line"],
            )

    def _paint(self) -> None:
        colors = self.colors
        running = self.presenter.running
        self.root.configure(bg=colors["bg"])
        self.body.configure(bg=colors["bg"])
        self.header.configure(bg=colors["bg"])
        self.title_label.configure(bg=colors["bg"], fg=colors["text"])
        self.mode_tabs.configure(bg=colors["panel"])
        self.view_switch.configure(bg=colors["panel"])
        self._paint_settings(colors)
        self.conn.configure(bg=colors["panel"], highlightbackground=colors["line"], highlightthickness=1)
        self.conn_label.configure(bg=colors["panel"], fg=colors["text"])
        self.conn_dot.configure(bg=colors["panel"], fg=colors["err"] if self.device_var.get() == "Chưa nối" else colors["ok"])
        self.side.configure(bg=colors["panel"], highlightbackground=colors["line"])
        self.main.configure(bg=colors["panel"], highlightbackground=colors["line"])
        self.card.configure(bg=colors["panel"])
        self.hint_label.configure(bg=colors["panel"], fg=colors["mute"])
        self.step_label.configure(bg=colors["panel"], fg=colors["mute"])
        hold_bg = "#f8efe4" if self.theme_name == "light" else "#3d3218"
        self.hold_banner.configure(bg=hold_bg, fg=colors["warn"])
        self.progress_label.configure(bg=colors["panel"], fg=colors["text"])
        self.percent_label.configure(bg=colors["panel"], fg=colors["mute"])
        self.toast_label.configure(bg=colors["panel"], fg=colors["mute"])
        warn_bg = "#f8efe4" if self.theme_name == "light" else "#3d3218"
        self.warn_label.configure(bg=warn_bg, fg=colors["warn"])
        if self._fish_hold:
            button_bg = colors["warn"]
            button_fg = "#1b1d21" if self.theme_name == "dark" else "#ffffff"
        elif running:
            button_bg = colors["err"]
            button_fg = "#ffffff"
        else:
            button_bg = colors["acc"]
            button_fg = "#ffffff" if self.theme_name == "light" else colors["acc_t"]
        self.primary_btn.configure(
            bg=button_bg,
            fg=button_fg,
            activebackground=button_bg,
            activeforeground=button_fg,
        )
        self.tools_btn.configure(bg=colors["panel"], fg=colors["text"], highlightbackground=colors["line"], highlightthickness=1)
        self.tool_menu.configure(bg=colors["panel"], highlightbackground=colors["line"])
        for button in (self.capture_btn, self.preview_btn, self.logs_btn):
            button.configure(bg=colors["panel"], fg=colors["text"], activebackground=colors["tile"])
        self.progress.configure(bg=colors["panel"])
        self.views.configure(bg=colors["panel"])
        self.tiles_row.configure(bg=colors["panel"])
        for name, (box, value, caption) in self.tiles.items():
            box.configure(bg=colors["tile"], highlightbackground=colors["line"])
            tone = self._tile_tones.get(name, "text")
            value.configure(bg=colors["tile"], fg=colors.get(tone, colors["text"]))
            caption.configure(bg=colors["tile"], fg=colors["mute"])
        self._mark_mode(self.mode_var.get())
        for button in self._mode_buttons.values():
            button.configure(bg=colors["panel"], activebackground=colors["panel"])
        self.result_pane.configure(bg=colors["log"], highlightbackground=colors["line"])
        self.log_pane.configure(bg=colors["log"], highlightbackground=colors["line"])
        self.log_box.configure(bg=colors["log"], fg=colors["text"], insertbackground=colors["text"])
        self.log_box.tag_configure("time", foreground=colors["dbg"])
        self.log_box.tag_configure("text", foreground=colors["text"])
        self.log_box.tag_configure("turn", foreground=colors["text"], font=(LOG_FONT[0], LOG_FONT[1], "bold"))
        self.log_box.tag_configure("mid", justify="center")
        self.log_box.tag_configure("ok", foreground=colors["ok"])
        self.log_box.tag_configure("gold", foreground=colors["gold"])
        self.log_box.tag_raise("gold")
        self.log_box.tag_configure("warn", foreground=colors["warn"])
        self.log_box.tag_configure("err", foreground=colors["err"])
        self.log_box.tag_configure("dbg", foreground=colors["dbg"])
        self.log_box.tag_configure("hidden", elide=not self._show_debug)
        self.ids.configure(bg=colors["panel"], fg=colors["text"], insertbackground=colors["text"], highlightthickness=1, highlightbackground=colors["line"], highlightcolor=colors["acc"])
        self.help_btn.configure(bg=colors["panel"], fg=colors["mute"], highlightbackground=colors["line"], highlightthickness=1)
        self.help_tip.configure(bg=colors["text"], fg=colors["bg"])
        self.load_btn.configure(bg=colors["panel"], fg=colors["text"], highlightbackground=colors["line"], highlightthickness=1)
        self.clear_btn.configure(bg=colors["panel"], fg=colors["text"], highlightbackground=colors["line"], highlightthickness=1)
        self.copy_btn.configure(bg=colors["panel"], fg=colors["text"], highlightbackground=colors["line"], highlightthickness=1)
        self.log_tools.configure(bg=colors["panel"])
        # Khung form không tô sẽ giữ nền xám của Windows. Nền đó lộ thành ô trắng cạnh nhãn ngắn, nhất là khi đổi tối.
        for page in (self.fish_page, self.rally_page, self.scan_page, self.list_page):
            page.configure(bg=colors["panel"])
            self._paint_children(page, colors)
        self._paint_inputs()
        self.style.configure(
            "App.Treeview",
            background=colors["log"],
            fieldbackground=colors["log"],
            foreground=colors["text"],
            borderwidth=0,
            rowheight=28,
            font=UI_FONT,
        )
        self.style.configure("App.Treeview.Heading", background=colors["tile"], foreground=colors["mute"], relief="flat", font=("Segoe UI", 9, "bold"))
        self.style.map("App.Treeview", background=[("selected", colors["tile"])], foreground=[("selected", colors["text"])])
        self.results.tag_configure("run", foreground=colors["mute"])
        self.results.tag_configure("ok", foreground=colors["ok"])
        self.results.tag_configure("fail", foreground=colors["err"])
        self._show_view(self._view_name)
        self._draw_bar()

    def _paint_inputs(self) -> None:
        """Ô nhập theo màu giao diện. Theme clam mặc định nền be và tô xanh khi ô hệ số được chọn."""
        colors = self.colors
        panel = colors["panel"]
        text = colors["text"]
        line = colors["line"]
        tile = colors["tile"]
        mute = colors["mute"]
        shared = {
            "fieldbackground": panel,
            "background": panel,
            "foreground": text,
            "bordercolor": line,
            "lightcolor": panel,
            "darkcolor": panel,
            "arrowcolor": mute,
            "insertcolor": text,
            "padding": 4,
        }
        self.style.configure("App.TSpinbox", **shared)
        self.style.configure("App.TCombobox", **shared)
        self.style.configure("App.TEntry", **shared)
        self.style.map(
            "App.TSpinbox",
            fieldbackground=[("disabled", tile), ("readonly", panel), ("focus", panel)],
            foreground=[("disabled", mute)],
            background=[("disabled", tile), ("active", tile), ("pressed", line), ("readonly", panel)],
            arrowcolor=[("disabled", colors["dbg"]), ("active", text)],
            bordercolor=[("focus", colors["acc"])],
            selectbackground=[("focus", panel)],
            selectforeground=[("focus", text)],
        )
        self.style.map(
            "App.TCombobox",
            fieldbackground=[
                ("disabled", tile),
                ("readonly", "focus", panel),
                ("readonly", panel),
                ("focus", panel),
            ],
            foreground=[
                ("disabled", mute),
                ("readonly", "focus", text),
                ("readonly", text),
            ],
            selectbackground=[("readonly", "focus", panel), ("readonly", panel), ("focus", panel)],
            selectforeground=[("readonly", "focus", text), ("readonly", text), ("focus", text)],
            background=[("disabled", tile), ("active", tile), ("pressed", line), ("readonly", panel)],
            arrowcolor=[("disabled", colors["dbg"]), ("active", text)],
            bordercolor=[("readonly", "focus", colors["acc"]), ("focus", colors["acc"])],
        )
        self.style.map(
            "App.TEntry",
            fieldbackground=[("disabled", tile), ("readonly", panel)],
            foreground=[("disabled", mute)],
            bordercolor=[("focus", colors["acc"])],
        )
        picked = "#ffffff" if self.theme_name == "light" else colors["acc_t"]
        self.root.option_add("*TCombobox*Listbox.font", "{Segoe UI} 18")
        self.root.option_add("*TCombobox*Listbox.background", panel)
        self.root.option_add("*TCombobox*Listbox.foreground", text)
        self.root.option_add("*TCombobox*Listbox.selectBackground", colors["acc"])
        self.root.option_add("*TCombobox*Listbox.selectForeground", picked)
        self._style_multiplier_list(panel, text, colors["acc"], picked)

    def _style_multiplier_list(self, panel: str, text: str, accent: str, picked: str) -> None:
        """Danh sách hệ số mặc định chỉ cao khoảng 15px mỗi dòng, khó bấm."""
        combo = self.fish_mult
        pop = combo.tk.call("ttk::combobox::PopdownWindow", combo)
        combo.tk.call(
            f"{pop}.f.l",
            "configure",
            "-font", MULT_LIST_FONT,
            "-background", panel,
            "-foreground", text,
            "-selectbackground", accent,
            "-selectforeground", picked,
            "-activestyle", "none",
            "-borderwidth", 0,
            "-highlightthickness", 0,
        )

    def _paint_children(self, widget: tk.Misc, colors: dict[str, str]) -> None:
        for child in widget.winfo_children():
            if isinstance(child, (tk.Frame, tk.Label)):
                child.configure(bg=colors["panel"])
                if isinstance(child, tk.Label):
                    child.configure(fg=colors["mute"] if child.cget("font") != str(UI_FONT) else colors["text"])
            self._paint_children(child, colors)
