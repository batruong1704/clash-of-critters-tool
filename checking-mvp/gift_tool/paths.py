from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPO = ROOT.parent
TEMPLATES = REPO / "templates"
LOGS = ROOT / "logs"
RESOURCE = ROOT / "resource"
USAGE_LOG = LOGS / "danh-gia-su-dung.log"


def note_use(step: str) -> None:
    """Ghi một dòng khi bước đọc resource/ thực sự chạy. Dùng để đánh giá sau có còn cần ảnh đó không."""
    LOGS.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with USAGE_LOG.open("a", encoding="utf-8") as handle:
        handle.write(f"{stamp} {step}\n")
