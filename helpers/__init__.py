"""Hàm dùng chung cho mọi chức năng của tool.

Import từ gốc repo: thêm thư mục gốc vào sys.path rồi `from helpers import detect_screen, Screen`.
"""

from helpers.screen_detector import Detection, Screen, detect_screen, detect_screen_info

__all__ = ["Detection", "Screen", "detect_screen", "detect_screen_info"]
