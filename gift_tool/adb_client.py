"""Chụp màn hình và bấm vào LDPlayer qua ADB. Không đụng chuột Windows."""

from __future__ import annotations

import os
import re
import subprocess
import sys
import time
from pathlib import Path
from shutil import which

import cv2
import numpy as np

NO_WINDOW = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
_DRIVE_FIXED = 3
CONNECT_PORTS = (5555, 5557, 5554, 5556, 5558, 5559, 5561)

# Mã phím Android. Về cuối dòng rồi xóa lùi. Ô UID dài tối đa 15 chữ số, cộng một nhịp dự phòng.
KEY_MOVE_END = "123"
KEY_DELETE = "67"
CLEAR_COUNT = 16


def _unique_dirs(paths: list[Path]) -> list[Path]:
    seen: set[str] = set()
    result = []
    for path in paths:
        key = str(path).lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(path)
    return result


def _dir_from_registry_value(value: str) -> Path | None:
    text = str(value).strip()
    if not text:
        return None
    if text.startswith('"'):
        end = text.find('"', 1)
        text = text[1:end] if end > 1 else text.strip('"')
    else:
        exe_at = text.lower().find(".exe")
        text = text[: exe_at + 4] if exe_at != -1 else text.split()[0]
    text = text.strip().strip('"')
    if text.lower().endswith(",0"):
        text = text[:-2].strip().strip('"')
    if not text:
        return None
    path = Path(text)
    return path.parent if path.suffix.lower() == ".exe" else path


def _registry_dirs() -> list[Path]:
    if sys.platform != "win32":
        return []
    import winreg

    found: list[Path] = []
    direct = (
        (winreg.HKEY_CURRENT_USER, r"Software\leidian\LDPlayer9"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\leidian\LDPlayer9"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\leidian\LDPlayer9"),
    )
    for hive, subkey in direct:
        try:
            with winreg.OpenKey(hive, subkey) as key:
                for name in ("InstallDir", "InstallPath", "Path"):
                    try:
                        value, _ = winreg.QueryValueEx(key, name)
                    except OSError:
                        continue
                    directory = _dir_from_registry_value(str(value))
                    if directory is not None:
                        found.append(directory)
        except OSError:
            continue

    uninstall_roots = (
        (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
    )
    for hive, subkey in uninstall_roots:
        try:
            root = winreg.OpenKey(hive, subkey)
        except OSError:
            continue
        try:
            count = winreg.QueryInfoKey(root)[0]
            for index in range(count):
                try:
                    name = winreg.EnumKey(root, index)
                    with winreg.OpenKey(root, name) as key:
                        display, _ = winreg.QueryValueEx(key, "DisplayName")
                        if "ldplayer" not in str(display).lower():
                            continue
                        for value_name in ("InstallLocation", "DisplayIcon", "UninstallString"):
                            try:
                                value, _ = winreg.QueryValueEx(key, value_name)
                            except OSError:
                                continue
                            directory = _dir_from_registry_value(str(value))
                            if directory is not None:
                                found.append(directory)
                                break
                except OSError:
                    continue
        finally:
            winreg.CloseKey(root)
    return found


def _fixed_drives() -> list[Path]:
    if sys.platform != "win32":
        return []
    import ctypes

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    mask = int(kernel.GetLogicalDrives())
    drives = []
    for index in range(26):
        if mask & (1 << index) == 0:
            continue
        root = f"{chr(65 + index)}:\\"
        if kernel.GetDriveTypeW(root) == _DRIVE_FIXED:
            drives.append(Path(root))
    return drives


def _install_dirs() -> list[Path]:
    dirs = _registry_dirs()
    for env_name in ("ProgramFiles", "ProgramFiles(x86)", "LocalAppData"):
        base = os.environ.get(env_name)
        if not base:
            continue
        root = Path(base)
        dirs.append(root / "ldplayer9box")
        dirs.append(root / "LDPlayer" / "LDPlayer9")
        dirs.append(root / "LDPlayer9")
    for drive in _fixed_drives():
        dirs.append(drive / "LDPlayer" / "LDPlayer9")
        dirs.append(drive / "LDPlayer9")
        dirs.append(drive / "ldplayer9box")
    return _unique_dirs(dirs)


def _ldplayer_home() -> Path | None:
    """Thư mục cài LDPlayer trên máy này. adb.exe và ldconsole.exe nằm cạnh nhau trong đó."""
    directories = _install_dirs()
    for directory in directories:
        if (directory / "adb.exe").is_file() and (directory / "ldconsole.exe").is_file():
            return directory
    on_path = which("adb")
    if on_path:
        directory = Path(on_path).resolve().parent
        if (directory / "ldconsole.exe").is_file():
            return directory
    for directory in directories:
        if (directory / "adb.exe").is_file():
            return directory
    return None


class AdbClient:
    def __init__(self):
        home = _ldplayer_home()
        if home is not None:
            self.adb = str(home / "adb.exe")
            console = home / "ldconsole.exe"
        else:
            on_path = which("adb")
            if not on_path:
                raise FileNotFoundError("Không thấy adb.exe. Hãy cài LDPlayer.")
            self.adb = on_path
            console = Path(on_path).resolve().with_name("ldconsole.exe")
        self.ldconsole = str(console) if console.is_file() else None
        self.serial = ""

    def ensure_device(self) -> str:
        serial = self._try_connect()
        if not serial:
            index = self._primary_index()
            if index is not None and self._adb_debug_value(index) == 0 and self.ldconsole:
                self._restart_with_adb(index)
                serial = self._wait_serial(90)
            else:
                serial = self._wait_serial(8)
        if not serial:
            raise RuntimeError(
                "Không nối được ADB. Trong LDPlayer mở Cài đặt, mục Khác, bật Gỡ lỗi ADB, "
                "khởi động lại giả lập, vào lại tab Add New rồi bấm Chụp thử."
            )
        self.serial = serial
        return self.serial

    def screenshot(self):
        if not self.serial:
            self.ensure_device()
        raw = self._run([self.adb, "-s", self.serial, "exec-out", "screencap", "-p"])
        # exec-out của adb LDPlayer 9 giữ nguyên byte. Thay \r\n ở đây làm hỏng mọi ảnh vì dữ liệu nén
        # có sẵn vài cặp 0D 0A, rồi mỗi lần chụp phải đi đường dự phòng chậm gấp đôi. Chỉ thay khi giải mã thẳng hỏng.
        img = self._decode_png(raw)
        if img is None:
            img = self._decode_png(raw.replace(b"\r\n", b"\n"))
        if img is None:
            remote = "/sdcard/coc_gift_cap.png"
            self._run([self.adb, "-s", self.serial, "shell", "screencap", "-p", remote])
            local = Path(__file__).resolve().parent.parent / "logs" / "cap.png"
            local.parent.mkdir(parents=True, exist_ok=True)
            self._run([self.adb, "-s", self.serial, "pull", remote, str(local)])
            data = np.fromfile(str(local), dtype=np.uint8)
            img = cv2.imdecode(data, cv2.IMREAD_COLOR)
        if img is None:
            raise RuntimeError("Không chụp được màn hình emulator.")
        return img

    @staticmethod
    def _decode_png(data: bytes):
        if not data:
            return None
        return cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)

    def tap(self, x: int, y: int) -> None:
        self._run([self.adb, "-s", self.serial, "shell", "input", "tap", str(int(x)), str(int(y))])

    def input_text(self, text: str) -> None:
        if not text.isdigit():
            raise ValueError("UID chỉ gồm chữ số.")
        self._run([self.adb, "-s", self.serial, "shell", "input", "text", text])

    def clear_text(self, count: int = CLEAR_COUNT) -> None:
        codes = [KEY_MOVE_END, *[KEY_DELETE] * count]
        self._run([self.adb, "-s", self.serial, "shell", "input", "keyevent", *codes])

    def back(self) -> None:
        self._run([self.adb, "-s", self.serial, "shell", "input", "keyevent", "4"])

    def _try_connect(self) -> str:
        serials = self._serials()
        if serials:
            return serials[0]
        rows = self._instances()
        running = [row for row in rows if row["running"]] or rows
        for row in running:
            if self.ldconsole:
                self._run(
                    [self.ldconsole, "adb", "--index", row["index"], "--command", "devices"],
                    check=False,
                )
        serials = self._serials()
        if serials:
            return serials[0]
        ports: list[int] = []
        for row in running:
            index = int(row["index"])
            ports.append(5555 + index * 2)
            ports.append(5555 + index)
        ports.extend(CONNECT_PORTS)
        ports.extend(self._ports_of([row["pid"] for row in running] + [row["vbox_pid"] for row in running]))
        seen: set[int] = set()
        for port in ports:
            if port in seen or port == 5037:
                continue
            seen.add(port)
            self._run([self.adb, "connect", f"127.0.0.1:{port}"], check=False)
        serials = self._serials()
        return serials[0] if serials else ""

    def _wait_serial(self, seconds: float) -> str:
        deadline = time.time() + seconds
        while time.time() < deadline:
            serial = self._try_connect()
            if serial:
                return serial
            time.sleep(2)
        return ""

    def _instances(self) -> list[dict[str, str | bool]]:
        if not self.ldconsole:
            return []
        raw = self._run([self.ldconsole, "list2"], check=False).decode("utf-8", "replace")
        rows = []
        for line in raw.splitlines():
            parts = [part.strip() for part in line.split(",")]
            if len(parts) < 7 or not parts[0].isdigit():
                continue
            rows.append(
                {
                    "index": parts[0],
                    "name": parts[1],
                    "running": parts[4] == "1",
                    "pid": parts[5],
                    "vbox_pid": parts[6],
                }
            )
        return rows

    def _primary_index(self) -> str | None:
        rows = self._instances()
        if not rows:
            config = Path(self.adb).parent / "vms" / "config" / "leidian0.config"
            return "0" if config.exists() else None
        running = [row for row in rows if row["running"]]
        return str((running or rows)[0]["index"])

    def _config_path(self, index: str) -> Path:
        return Path(self.adb).parent / "vms" / "config" / f"leidian{index}.config"

    def _adb_debug_value(self, index: str) -> int | None:
        path = self._config_path(index)
        if not path.exists():
            return None
        match = re.search(r'"basicSettings\.adbDebug"\s*:\s*(\d+)', path.read_text(encoding="utf-8"))
        return int(match.group(1)) if match else None

    def _set_adb_debug(self, index: str) -> None:
        path = self._config_path(index)
        text = path.read_text(encoding="utf-8")
        updated, count = re.subn(
            r'("basicSettings\.adbDebug"\s*:\s*)\d+',
            r"\g<1>1",
            text,
            count=1,
        )
        if count != 1:
            raise RuntimeError("Không sửa được cấu hình ADB của LDPlayer.")
        if updated != text:
            path.write_text(updated, encoding="utf-8")

    def _restart_with_adb(self, index: str) -> None:
        self._run([self.ldconsole, "quit", "--index", index], check=False)
        deadline = time.time() + 40
        while time.time() < deadline:
            rows = [row for row in self._instances() if row["index"] == index and row["running"]]
            if not rows:
                break
            time.sleep(1)
        self._set_adb_debug(index)
        self._run([self.ldconsole, "launch", "--index", index], check=False)

    def _ports_of(self, pids: list[str]) -> list[int]:
        wanted = {pid for pid in pids if pid.isdigit()}
        if not wanted:
            return []
        proc = subprocess.run(
            ["netstat", "-ano", "-p", "tcp"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=15,
            creationflags=NO_WINDOW,
            check=False,
        )
        ports = []
        for line in proc.stdout.decode("utf-8", "replace").splitlines():
            parts = line.split()
            if len(parts) < 5 or parts[0].upper() != "TCP" or parts[3].upper() != "LISTENING":
                continue
            if parts[4] not in wanted:
                continue
            address = parts[1]
            port_text = address.rsplit(":", 1)[-1]
            if port_text.isdigit():
                ports.append(int(port_text))
        return ports

    def _serials(self) -> list[str]:
        raw = self._run([self.adb, "devices"], check=False).decode("utf-8", "replace")
        found = []
        for line in raw.splitlines():
            parts = line.split()
            if len(parts) >= 2 and parts[1] == "device":
                found.append(parts[0])
        preferred = [item for item in found if item.startswith("emulator") or item.startswith("127.0.0.1")]
        return preferred or found

    def _run(self, cmd: list[str], check: bool = True) -> bytes:
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=30,
            creationflags=NO_WINDOW,
            check=False,
        )
        if check and proc.returncode != 0:
            err = proc.stderr.decode("utf-8", "replace").strip()
            raise RuntimeError(err or f"Lệnh adb thất bại ({proc.returncode})")
        return proc.stdout
