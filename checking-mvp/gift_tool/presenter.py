"""Presenter: nhận thao tác trên cửa sổ, kiểm tra ô nhập, gọi model, đẩy chữ lên view."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import threading
from datetime import datetime
from pathlib import Path

from gift_tool.flow import LABELS, LOG_INDENT, MAX_GIFTS
from gift_tool.paths import LOGS, REPO
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
from gift_tool.view import APP_VERSION, MainView, fish_level


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """Gọi git không mở cửa sổ và không chờ hộp nhập mật khẩu."""
    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["GCM_INTERACTIVE"] = "Never"
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    return subprocess.run(
        [shutil.which("git") or "git", *args],
        cwd=repo,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=90,
        env=env,
        creationflags=flags,
    )


def _one_line(text: str) -> str:
    line = " ".join(text.strip().split())
    return line[:160] if line else "git không trả lời"


def _explain_failure(text: str) -> str:
    """Đổi lời kỹ thuật thành câu người dùng đọc được. Nguyên văn vẫn ghi vào log."""
    raw = text.lower()
    if "would be overwritten" in raw or "local changes" in raw or "please commit" in raw:
        return "Chưa tải được vì trong thư mục tool còn file đang sửa. Đóng tool, mở lại, rồi bấm Cập nhật."
    if "not possible to fast-forward" in raw or "diverging" in raw:
        return "Bản trên máy đã lệch với bản phát hành nên chưa tải đè được. Nhờ người cài tool xử lý."
    if "index.lock" in raw:
        return "Tool đang bận một việc khác. Đợi một lát rồi bấm Cập nhật lại."
    if any(mark in raw for mark in ("could not resolve", "unable to access", "failed to connect", "timed out", "connection refused", "hết giờ")):
        return "Không kết nối được. Kiểm tra mạng rồi bấm Cập nhật lại."
    if any(mark in raw for mark in ("authentication", "permission denied", "403", "401")):
        return "Máy này chưa được phép tải bản mới. Nhờ người cài tool kiểm tra lại."
    return "Chưa tải được bản mới. Kiểm tra mạng rồi thử lại."


_SHIPPED = re.compile(r"^Ship (\d+\.\d+\.\d+)\b")
_VERSION_FILE = re.compile(r"^versions/(\d+\.\d+\.\d+)\.md$")


def parse_shipped_versions(text: str) -> list[tuple[str, str]]:
    """Đọc log git thành (số phiên bản, hash), bản mới đứng trước. Trùng số thì giữ bản mới hơn."""
    found: list[tuple[str, str]] = []
    seen: set[str] = set()
    for line in text.splitlines():
        parts = line.split(" ", 1)
        if len(parts) != 2:
            continue
        sha, subject = parts[0].strip(), parts[1].strip()
        match = _SHIPPED.match(subject)
        if match is None or not sha:
            continue
        version = match.group(1)
        if version in seen:
            continue
        seen.add(version)
        found.append((version, sha))
    return found


def published_versions(tree_text: str) -> set[str]:
    """Số phiên bản còn file thông báo trên bản phát hành. File đã xóa thì không hiện trong danh sách."""
    found: set[str] = set()
    for line in tree_text.splitlines():
        match = _VERSION_FILE.match(line.strip().replace("\\", "/"))
        if match is not None:
            found.add(match.group(1))
    return found


def list_shipped_versions(repo: Path) -> tuple[list[tuple[str, str]], str]:
    """Các bản đã phát hành còn được giữ. Câu lỗi là tiếng Việt, rỗng khi đọc được."""
    if shutil.which("git") is None:
        return [], "Máy này chưa được cài đủ để đổi phiên bản."
    if not (repo / ".git").exists():
        return [], "Không tìm thấy dữ liệu bản cài nên chưa đổi phiên bản được."
    ref = "origin/main"
    if _git(repo, "rev-parse", "--verify", "--quiet", ref).returncode != 0:
        ref = "main"
    tree = _git(repo, "ls-tree", "-r", "--name-only", ref, "versions")
    listed = _git(repo, "log", ref, "--format=%h %s")
    if tree.returncode != 0 or listed.returncode != 0:
        message = "Chưa đọc được danh sách phiên bản."
        _log_update(message, tree.stderr or listed.stderr or listed.stdout)
        return [], message
    kept = published_versions(tree.stdout)
    found = [item for item in parse_shipped_versions(listed.stdout) if item[0] in kept]
    if not found:
        return [], "Chưa có phiên bản nào để chọn."
    return found, ""


def switch_to_version(repo: Path, sha: str) -> tuple[bool, str]:
    """Đưa thư mục tool về đúng bản đã phát hành. Không đẩy gì lên nơi phát hành."""
    known = _git(repo, "cat-file", "-e", f"{sha}^{{commit}}")
    if known.returncode != 0:
        fetched = _git(repo, "fetch", "--quiet", "origin", "main")
        if fetched.returncode != 0:
            message = _explain_failure(fetched.stderr or fetched.stdout)
            _log_update(message, fetched.stderr or fetched.stdout)
            return False, message
        known = _git(repo, "cat-file", "-e", f"{sha}^{{commit}}")
        if known.returncode != 0:
            message = "Không tìm thấy phiên bản này."
            _log_update(message, sha)
            return False, message
    switched = _git(repo, "switch", "--detach", sha)
    if switched.returncode != 0:
        raw = switched.stderr or switched.stdout
        if any(mark in raw.lower() for mark in ("would be overwritten", "local changes", "please commit")):
            message = "Chưa đổi được vì trong thư mục tool còn file đang sửa. Đóng tool, mở lại, rồi bấm Đổi phiên bản."
        else:
            message = "Chưa đổi được phiên bản. Đóng tool, mở lại, rồi thử một lần nữa."
        _log_update(message, raw)
        return False, message
    return True, ""


def _log_update(message: str, detail: str = "") -> None:
    """Ghi lần cập nhật. Dòng đầu là câu người dùng thấy, phần sau là lời kỹ thuật."""
    try:
        LOGS.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        body = message.rstrip()
        extra = detail.strip()
        if extra:
            body = f"{body}\n{extra}"
        with (LOGS / "cap-nhat.log").open("a", encoding="utf-8") as handle:
            handle.write(f"[{stamp}] {body}\n")
    except OSError:
        pass


_PROGRESS_LINE = re.compile(
    r"(counting|compressing|receiving|resolving|unpacking)\s+(?:objects|deltas):\s+(\d+)%",
    re.IGNORECASE,
)


def _read_progress(line: str) -> tuple[int, str] | None:
    """Đổi dòng tiến trình của git thành phần trăm và câu trạng thái."""
    match = _PROGRESS_LINE.search(line)
    if match is None:
        return None
    phase = match.group(1).lower()
    pct = int(match.group(2))
    if phase == "counting":
        return 5 + pct * 15 // 100, "Đang chuẩn bị…"
    if phase == "compressing":
        return 20 + pct * 10 // 100, "Đang chuẩn bị…"
    if phase == "receiving":
        return 30 + pct * 60 // 100, "Đang tải bản mới…"
    return 90 + pct * 10 // 100, "Đang cài bản mới…"


def _split_git_chunks(buf: bytes) -> tuple[bytes, list[str]]:
    pieces: list[str] = []
    while True:
        cut = None
        for sep in (b"\r", b"\n"):
            found = buf.find(sep)
            if found >= 0 and (cut is None or found < cut):
                cut = found
        if cut is None:
            break
        piece = buf[:cut]
        buf = buf[cut + 1 :]
        if piece.strip():
            pieces.append(piece.decode("utf-8", "replace"))
    return buf, pieces


def _git_stream(repo: Path, on_status, on_progress, *args: str) -> tuple[int, str]:
    """Chạy git và đọc tiến trình tải. Git ghi phần trăm bằng dấu về đầu dòng."""
    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["GCM_INTERACTIVE"] = "Never"
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    proc = subprocess.Popen(
        [shutil.which("git") or "git", *args],
        cwd=repo,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        env=env,
        creationflags=flags,
    )
    notes: list[str] = []

    def reader() -> None:
        assert proc.stdout is not None
        buf = b""
        while True:
            block = proc.stdout.read(256)
            if not block:
                break
            buf += block
            buf, pieces = _split_git_chunks(buf)
            for piece in pieces:
                step = _read_progress(piece)
                if step is None:
                    notes.append(piece.strip())
                    continue
                pct, label = step
                on_progress(pct)
                on_status(label)
        if buf.strip():
            notes.append(buf.decode("utf-8", "replace").strip())

    worker = threading.Thread(target=reader, daemon=True)
    worker.start()
    try:
        code = proc.wait(timeout=180)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()
        worker.join(timeout=2)
        return 1, "Hết giờ khi tải code."
    worker.join(timeout=5)
    return code, "\n".join(note for note in notes if note)


def _remote_sha(repo: Path, branch: str) -> tuple[str, str]:
    listed = _git(repo, "ls-remote", "origin", f"refs/heads/{branch}")
    if listed.returncode != 0:
        return "", _one_line(listed.stderr or listed.stdout)
    token = listed.stdout.split()
    if not token:
        return "", f"Không thấy bản phát hành trên nhánh {branch}."
    return token[0], ""


def _render_version(text: str) -> str:
    """Lấy tiêu đề và các mục Thêm, Sửa, Bỏ. Bỏ phần kiểm tra và lưu ý kỹ thuật."""
    title = ""
    sections: list[tuple[str, list[str]]] = []
    current: list[str] | None = None
    keep = {"thêm", "sửa", "bỏ"}
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("# "):
            title = line[2:].strip()
            continue
        if line.startswith("## "):
            name = line[3:].strip()
            current = None
            if name.lower() in keep:
                current = []
                sections.append((name, current))
            continue
        if current is not None and line.startswith("- "):
            current.append(line[2:].strip())
    parts: list[str] = []
    if title:
        parts.append(title)
    for name, items in sections:
        if not items or (len(items) == 1 and items[0].lower().rstrip(".") == "không có"):
            continue
        parts.append(name)
        parts.extend(f"• {item}" for item in items)
    return "\n".join(parts)


def _notes_between(repo: Path, old: str, new: str) -> str:
    """Những thay đổi vừa kéo về. Ưu tiên file phiên bản, không có thì lấy câu mô tả commit."""
    if not old or not new or old == new:
        return ""
    listed = _git(repo, "diff", "--name-only", "--diff-filter=AM", f"{old}..{new}", "--", "versions")
    paths = []
    for rel in listed.stdout.splitlines():
        path = repo / rel.strip()
        if path.suffix.lower() == ".md" and path.is_file():
            paths.append(path)
    paths.sort(key=lambda path: path.stem, reverse=True)
    blocks = []
    for path in paths:
        try:
            block = _render_version(path.read_text(encoding="utf-8"))
        except OSError:
            continue
        if block:
            blocks.append(block)
    if blocks:
        return "\n\n".join(blocks)
    return "Đã cài bản mới."


def _latest_message() -> str:
    return f"Bạn đang dùng bản {APP_VERSION}. Đây là bản mới nhất."


def pull_from_github(repo: Path, on_status, on_progress) -> tuple[str, str]:
    """Tải bản phát hành mới. Không đụng cấu hình git. Câu trả về là tiếng Việt cho người dùng."""
    on_status("Đang kiểm tra bản mới…")
    if shutil.which("git") is None:
        message = "Máy này chưa được cài đủ để cập nhật. Nhờ người thiết lập tool kiểm tra lại."
        _log_update(message)
        return message, ""
    if not (repo / ".git").exists():
        message = "Không tìm thấy dữ liệu bản cài nên chưa cập nhật được."
        _log_update(message)
        return message, ""
    url = _git(repo, "remote", "get-url", "origin")
    remote = url.stdout.strip().lower()
    if url.returncode != 0 or "github.com" not in remote:
        message = "Bản cài này chưa được nối tới nơi phát hành nên chưa cập nhật được."
        _log_update(message, url.stderr or url.stdout)
        return message, ""
    branch = _git(repo, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    if not branch or branch == "HEAD":
        on_status("Đang về bản phát hành…")
        back = _git(repo, "switch", "main")
        if back.returncode != 0:
            message = _explain_failure(back.stderr or back.stdout)
            _log_update(message, back.stderr or back.stdout)
            return message, ""
        branch = "main"
    local = _git(repo, "rev-parse", "HEAD").stdout.strip()
    sha, problem = _remote_sha(repo, branch)
    if not sha:
        message = "Không kết nối được để kiểm tra bản mới. Kiểm tra mạng rồi thử lại."
        _log_update(message, problem)
        return message, ""
    if sha == local:
        message = _latest_message()
        _log_update(message)
        return message, ""
    known = _git(repo, "cat-file", "-e", f"{sha}^{{commit}}")
    if known.returncode == 0 and _git(repo, "merge-base", "--is-ancestor", sha, "HEAD").returncode == 0:
        message = _latest_message()
        _log_update(message)
        return message, ""
    on_status("Có bản mới. Đang tải về…")
    on_progress(0)
    code, text = _git_stream(repo, on_status, on_progress, "pull", "--ff-only", "--progress", "origin", branch)
    if code != 0:
        message = _explain_failure(text)
        _log_update(message, text or "không có lời trả về")
        return message, ""
    on_progress(100)
    if "already up to date" in text.lower() or "already up-to-date" in text.lower():
        message = _latest_message()
        _log_update(message)
        return message, ""
    new = _git(repo, "rev-parse", "HEAD").stdout.strip()
    _log_update(f"Đã tải bản mới {APP_VERSION}.")
    return "Đã tải bản mới.", _notes_between(repo, local, new)


def _window_python() -> str:
    """Python không gắn cửa sổ đen. python.exe luôn mở terminal trên Windows."""
    exe = Path(sys.executable)
    if os.name == "nt":
        windowed = exe.with_name("pythonw.exe")
        if windowed.is_file():
            return str(windowed)
    return str(exe)


def relaunch_app() -> None:
    """Mở lại đúng tool đang chạy để nạp code mới. Tiến trình cũ thoát sau đó."""
    main_py = Path(sys.argv[0]).resolve()
    if main_py.name != "main.py":
        main_py = Path(__file__).resolve().parents[1] / "main.py"
    command = [_window_python(), str(main_py)]
    cwd = str(main_py.parent)
    quiet = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
    if os.name != "nt":
        subprocess.Popen(command, cwd=cwd, start_new_session=True, close_fds=True, **quiet)
        return
    flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
    try:
        subprocess.Popen(
            command,
            cwd=cwd,
            creationflags=flags | subprocess.CREATE_BREAKAWAY_FROM_JOB,
            close_fds=True,
            **quiet,
        )
    except OSError:
        subprocess.Popen(command, cwd=cwd, creationflags=flags, close_fds=True, **quiet)


def caught_fish(message: str) -> tuple[str, str] | None:
    """Tên hiện trên bảng và màu chữ. None khi dòng không phải kết quả câu."""
    if not message.startswith("Câu được"):
        return None
    label = message.split(", +", 1)[0][len("Câu được ") :].strip().rstrip(".")
    if label == "cá":
        return "Không rõ", "ok"
    from fishing_tool.catch import tone_for

    return label, tone_for(label)


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
        ("Đang tính toán kết quả", "Đang tính toán kết quả"),
        ("Câu được", "Đã câu được cá"),
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
        self._updating = False
        self._loading = False
        self.stop = threading.Event()
        self.worker: threading.Thread | None = None
        self.model = ToolModel()
        self._status_step = "Sẵn sàng"
        self._status_stats = [f"Dừng sau {MAX_GIFTS} quà"]
        self._fish_timing = False
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
        self.view.root.after(200, self._open_saved_notes)

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
        self._status("Đang nối máy", ["Đã tham gia 0"])
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
        self._fish_timing = False
        self.view.reset_cast_clock()
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
                if message.lower().startswith("đã tham gia"):
                    self._rally_asked += 1
                    self.view.add_result((str(self._rally_asked), "Đã tham gia"))
                step = message.split(".", 1)[0]
                self._status(step, [f"Đã tham gia {self._rally_asked}"])

            counts = self.model.run_rally(adb, log, self.stop)
            self._status(f"Xong. Đã tham gia {counts['xin']} rally.", [f"Đã tham gia {counts['xin']}"])
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
                caught = caught_fish(message)
                level = caught[1] if caught else fish_level(message)
                self.view.append_log(message, level)
                updated = self._note_fish_row(message, caught)
                # Tên cá có thể về sau khi lượt kế đã bắt đầu. Không kéo dòng trạng thái về lượt cũ.
                if caught is not None and updated != getattr(self, "_fish_iid", ""):
                    return
                step = fish_step(message)
                if step:
                    self._status(step)

            def show(stats) -> None:
                if stats.timing:
                    self._fish_timing = True
                elif self._fish_timing:
                    self._fish_timing = False
                    self.view.stop_cast_clock(stats.seconds, getattr(self, "_fish_iid", ""))
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
            self.view.halt_cast_clock()
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
            self._status("Sẵn sàng", ["Chạy đến khi bấm Dừng"])
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
            return "Tham gia đến khi dừng"
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

    def update_from_github(self) -> None:
        current = getattr(self.view, "_update_dialog", None)
        if self._updating:
            if current is not None and current.alive:
                current.lift()
            else:
                self.view.toast("Đang cập nhật…")
            return
        dialog = self.view.open_update_dialog()
        if self.running:
            dialog.set_status("Đang chạy, hãy dừng trước khi cập nhật.")
            return
        self._updating = True
        self.view.set_update_busy(True)
        dialog.set_status("Đang kiểm tra bản mới…")
        threading.Thread(target=self._update_from_github, args=(dialog,), daemon=True).start()

    def _update_from_github(self, dialog) -> None:
        def on_status(text: str) -> None:
            def apply(text: str = text) -> None:
                if dialog.alive:
                    dialog.set_status(text)

            self.view.invoke(apply)

        def on_progress(pct: int) -> None:
            def apply(pct: int = pct) -> None:
                if dialog.alive:
                    dialog.set_progress(pct)

            self.view.invoke(apply)

        try:
            message, notes = pull_from_github(REPO, on_status, on_progress)
        except Exception as exc:
            _log_update("Không cập nhật được.", str(exc))
            message, notes = "Không cập nhật được. Hãy tắt tool rồi mở lại.", ""

        def done() -> None:
            self._updating = False
            self.view.set_update_busy(False)
            if message.startswith("Đã tải"):
                self._restart_with_notes(dialog, notes)
                return
            if dialog.alive:
                dialog.set_status(message)
                if message == _latest_message():
                    dialog.offer_restart(self.restart_app)
            else:
                self.view.toast(message)

        self.view.invoke(done)

    def choose_version(self) -> None:
        if self._updating:
            self.view.toast("Đang cập nhật…")
            return
        dialog = self.view.open_version_dialog()
        if self.running:
            dialog.set_status("Đang chạy, hãy dừng trước khi đổi phiên bản.")
            return
        self._updating = True
        self.view.set_update_busy(True)
        dialog.set_status("Đang đọc danh sách phiên bản…")
        threading.Thread(target=self._load_versions, args=(dialog,), daemon=True).start()

    def _load_versions(self, dialog) -> None:
        try:
            versions, error = list_shipped_versions(REPO)
        except Exception as exc:
            _log_update("Không đọc được danh sách phiên bản.", str(exc))
            versions, error = [], "Không đọc được danh sách phiên bản."

        def done() -> None:
            self._updating = False
            self.view.set_update_busy(False)
            if not dialog.alive:
                return
            if error:
                dialog.set_status(error)
                return
            dialog.show_versions(versions, APP_VERSION, lambda version, sha: self._pick_version(dialog, version, sha))

        self.view.invoke(done)

    def _pick_version(self, dialog, version: str, sha: str) -> None:
        if self._updating:
            return
        if self.running:
            dialog.set_status("Đang chạy, hãy dừng trước khi đổi phiên bản.")
            return
        if version == APP_VERSION:
            dialog.set_status(f"Bạn đang dùng phiên bản {version}.")
            return
        self._updating = True
        self.view.set_update_busy(True)
        dialog.set_busy(True)
        dialog.set_status(f"Đang chuyển về phiên bản {version}…")
        threading.Thread(target=self._switch_version, args=(dialog, version, sha), daemon=True).start()

    def _switch_version(self, dialog, version: str, sha: str) -> None:
        try:
            ok, message = switch_to_version(REPO, sha)
        except Exception as exc:
            _log_update("Không đổi được phiên bản.", str(exc))
            ok, message = False, "Không đổi được phiên bản. Hãy tắt tool rồi mở lại."

        def done() -> None:
            if ok:
                _log_update(f"Đã chuyển về phiên bản {version}.")
                self._relaunch(dialog, f"Đã về phiên bản {version}. Đang mở lại tool…")
                return
            self._updating = False
            self.view.set_update_busy(False)
            if dialog.alive:
                dialog.set_busy(False)
                dialog.set_status(message)
            else:
                self.view.toast(message)

        self.view.invoke(done)

    def _relaunch(self, dialog, status: str) -> None:
        """Mở cửa sổ mới để nạp code vừa chuyển, rồi đóng cửa sổ đang giữ code cũ."""
        self._save_settings()
        if dialog.alive:
            dialog.set_status(status)
            self.view.root.update_idletasks()
        try:
            relaunch_app()
        except OSError as exc:
            self._updating = False
            self.view.set_update_busy(False)
            if dialog.alive:
                dialog.set_busy(False)
                dialog.set_status("Đã đổi phiên bản nhưng chưa mở lại được. Hãy tắt tool rồi mở lại.")
            else:
                self.view.toast("Đã đổi phiên bản nhưng chưa mở lại được. Hãy tắt tool rồi mở lại.")
            _log_update("Chưa mở lại được sau khi đổi phiên bản.", str(exc))
            return
        self.view.root.destroy()

    def _restart_with_notes(self, dialog, notes: str) -> None:
        """Ghi phần có gì mới, mở cửa sổ mới, rồi đóng cửa sổ đang giữ code cũ."""
        self._save_settings()
        path = LOGS / "ban-moi.txt"
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(notes.strip(), encoding="utf-8")
            if dialog.alive:
                dialog.set_status("Đã tải xong. Đang mở lại tool…")
                dialog.set_progress(100)
                self.view.root.update_idletasks()
            relaunch_app()
        except OSError as exc:
            try:
                path.unlink()
            except OSError:
                pass
            if dialog.alive:
                dialog.set_status("Đã tải bản mới nhưng chưa mở lại được. Hãy tắt tool rồi mở lại.")
            else:
                self.view.toast("Đã tải bản mới nhưng chưa mở lại được. Hãy tắt tool rồi mở lại.")
            _log_update("Chưa mở lại được sau khi tải.", str(exc))
            return
        self.view.root.destroy()

    def restart_app(self) -> None:
        """Mở lại cửa sổ để nạp code đang có trên máy. Không tải gì từ nơi phát hành."""
        if self._updating:
            self.view.toast("Đang cập nhật…")
            return
        if self.running:
            self.view.toast("Đang chạy, hãy dừng trước khi khởi động lại.")
            return
        self._save_settings()
        try:
            relaunch_app()
        except OSError as exc:
            _log_update("Chưa khởi động lại được.", str(exc))
            self.view.toast("Chưa mở lại được. Hãy tắt tool rồi mở lại.")
            return
        _log_update("Khởi động lại để nạp code trên máy.")
        self.view.root.destroy()

    def _open_saved_notes(self) -> None:
        path = LOGS / "ban-moi.txt"
        if not path.is_file():
            return
        try:
            notes = path.read_text(encoding="utf-8").strip()
        except OSError:
            return
        try:
            path.unlink()
        except OSError:
            pass
        if notes:
            self.view.open_notes_dialog(notes)

    def _note_fish_row(self, message: str, caught: tuple[str, str] | None = None) -> str:
        """Ghi dòng bảng. Trả về mã dòng vừa chạm, để tên cá muộn không đè lượt đang câu."""
        if message.startswith("Lượt ") and "quăng" in message:
            number = message.split(":", 1)[0].split()[1].split("/")[0]
            self._fish_turn = number
            self._fish_iid = self.view.add_result((number, "Đang chạy…", "", "", ""))
            self.view.start_cast_clock(self._fish_iid)
            return ""
        if message.startswith("Đang tính toán kết quả"):
            turn = getattr(self, "_fish_turn", "")
            iid = getattr(self, "_fish_iid", "")
            pending = getattr(self, "_fish_name_rows", None)
            if pending is None:
                pending = []
                self._fish_name_rows = pending
            pending.append((iid, turn))
            self.view.finish_result(iid, (turn, "Đang tính toán kết quả", "", "…", "…"), "run")
            return iid
        if caught is not None:
            gold = "–"
            if "+" in message and "Gold" in message:
                gold = "+" + message.split("+", 1)[1].split()[0].rstrip(".")
            label, tone = caught
            pending = getattr(self, "_fish_name_rows", None) or []
            if pending:
                iid, turn = pending.pop(0)
            else:
                iid, turn = getattr(self, "_fish_iid", ""), getattr(self, "_fish_turn", "")
            self.view.finish_result(iid, (turn, "Thành công", "", label, gold), tone)
            return iid
        elif message.startswith("Thất bại"):
            turn = getattr(self, "_fish_turn", "")
            self.view.finish_result(getattr(self, "_fish_iid", ""), (turn, "Thất bại", "", "–", "–"), "fail")
        elif message.startswith("Không thấy màn kết quả"):
            turn = getattr(self, "_fish_turn", "")
            self.view.finish_result(getattr(self, "_fish_iid", ""), (turn, "Không rõ", "", "–", "–"), "warn")
        return ""

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
