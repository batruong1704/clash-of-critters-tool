import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPO = ROOT.parent
DATA = ROOT / "data"
TEMPLATES = DATA / "templates"
LOGS = ROOT / "logs"
RESOURCE = ROOT / "resource"
VIDEO = RESOURCE / "demo-video.mp4"

# adb_client và hàm đọc chữ số dùng chung với tool nhận quà.
_SHARED = REPO / "checking-mvp"
if str(_SHARED) not in sys.path:
    sys.path.insert(0, str(_SHARED))
