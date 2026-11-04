"""Đọc danh sách mã mặc định. Sửa file ma-mac-dinh.txt, không sửa file này."""

from __future__ import annotations

from pathlib import Path

LIST_FILE = Path(__file__).resolve().parent / "ma-mac-dinh.txt"


def parse_codes(text: str) -> tuple[list[str], list[str]]:
    """Tách nhiều mã. Nhận xuống dòng, dấu phẩy hoặc chấm phẩy. Ghi chú sau # bị bỏ."""
    good, bad = [], []
    chunks = text.replace(",", "\n").replace(";", "\n").splitlines()
    for chunk in chunks:
        body = chunk.split("#", 1)[0].strip()
        if not body:
            continue
        token = "".join(body.split())
        if token and all(ch.isalnum() for ch in token):
            good.append(token)
        elif token:
            bad.append(token)
    return good, bad


def load_codes(path: Path | None = None) -> list[str]:
    """Mỗi dòng một mã trong file mặc định. Bỏ dòng trống và ghi chú sau dấu #."""
    file = LIST_FILE if path is None else path
    codes, _bad = parse_codes(file.read_text(encoding="utf-8"))
    return codes
