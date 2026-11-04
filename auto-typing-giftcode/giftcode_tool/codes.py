"""Đọc danh sách mã mặc định. Sửa file ma-mac-dinh.txt, không sửa file này."""

from __future__ import annotations

from pathlib import Path

LIST_FILE = Path(__file__).resolve().parent / "ma-mac-dinh.txt"


def load_codes(path: Path | None = None) -> list[str]:
    """Mỗi dòng một mã. Bỏ dòng trống và ghi chú sau dấu #."""
    file = LIST_FILE if path is None else path
    codes = []
    for raw in file.read_text(encoding="utf-8").splitlines():
        body = raw.split("#", 1)[0].strip()
        if not body:
            continue
        token = "".join(body.split())
        if token and all(ch.isalnum() for ch in token):
            codes.append(token)
    return codes
