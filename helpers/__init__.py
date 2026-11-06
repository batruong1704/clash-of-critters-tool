"""Hàm dùng chung cho mọi chức năng của tool.

Import từ gốc repo: thêm thư mục gốc vào sys.path rồi `from helpers import detect_screen, Screen`.
Màn rally (bản đồ, chat, hộp thưởng, hộp thoại) nằm ở `helpers.rally_screen`.
"""

from helpers.rally_screen import Reading, read_screen
from helpers.screen_detector import Detection, Screen, detect_screen, detect_screen_info, goldrush_entry

__all__ = [
    "Detection",
    "Reading",
    "Screen",
    "detect_screen",
    "detect_screen_info",
    "goldrush_entry",
    "read_screen",
]
