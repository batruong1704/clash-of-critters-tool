import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPO = ROOT.parent
LOGS = ROOT / "logs"
RESOURCE = ROOT / "resource"

# ADB và ảnh mẫu nút dùng chung với tool nhận quà.
_SHARED = REPO / "checking-mvp"
if str(_SHARED) not in sys.path:
    sys.path.insert(0, str(_SHARED))
