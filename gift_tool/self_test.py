"""Khớp ảnh mẫu lên đúng screenshot từng bước. Không cần emulator."""

from pathlib import Path

import cv2

from gift_tool.paths import RESOURCE, ROOT
from gift_tool.vision import (
    Finder,
    avatar_point,
    draw_hits,
    field_point,
    imread,
    imwrite,
    player_level,
    result_signature,
    signature_diff,
)

NAMES = ("search", "add", "visit", "gift", "select", "ok", "close")


def screenshots() -> list[Path]:
    return sorted(p for p in RESOURCE.glob("*.png") if p.name[:1].isdigit())


def main():
    finder = Finder()
    shots = {path.name: imread(path) for path in screenshots()}
    print(f"{'file':<18} " + " ".join(f"{name:>7}" for name in NAMES))
    by_prefix = {}
    for name, img in shots.items():
        prefix = name.split(".", 1)[0]
        scores = []
        hits = []
        for key in NAMES:
            hit = finder.locate(img, key)
            scores.append(f"{hit.score:7.2f}")
            threshold = finder.templates[key][1]["threshold"]
            if hit.w and hit.score >= threshold:
                hits.append(hit)
        print(f"{prefix:<18} " + " ".join(scores))
        by_prefix[prefix] = (img, hits)

    out = ROOT / "logs" / "self-test"
    for prefix, (img, hits) in by_prefix.items():
        imwrite(out / f"{prefix}.png", draw_hits(img, hits))

    img3 = by_prefix["3"][0]
    add = finder.find(img3, "add")
    search = finder.find(img3, "search")
    if add is None or search is None:
        raise SystemExit("Ảnh 3 phải thấy nút Add và kính lúp")
    ax, ay = avatar_point(img3, add)
    fx, fy = field_point(img3, search)
    marked = img3.copy()
    cv2.circle(marked, (ax, ay), 14, (0, 0, 255), 2)
    cv2.circle(marked, (fx, fy), 10, (0, 180, 0), 2)
    imwrite(out / "3-diem-bam.png", marked)
    print(f"avatar=({ax},{ay}) o_nhap=({fx},{fy}) add=({add.x},{add.y}) search=({search.x},{search.y})")
    level = player_level(img3, add)
    print(f"cấp hàng kết quả = {level}")
    if level != 299:
        raise SystemExit("Ảnh 3 phải đọc cấp 299 trên hàng Results")

    img2 = by_prefix["2"][0]
    search2 = finder.find(img2, "search")
    if search2 is None:
        raise SystemExit("Ảnh 2 phải thấy kính lúp")
    diff = signature_diff(result_signature(img2, search2), result_signature(img3, search))
    same = signature_diff(result_signature(img3, search), result_signature(img3, search))
    print(f"diff friend-request vs result = {diff:.1f}, same = {same:.1f}")

    if finder.find(img3, "results") is None:
        raise SystemExit("Ảnh 3 phải thấy chữ Results")
    if finder.find(by_prefix["2"][0], "results") is not None:
        raise SystemExit("Ảnh nhập UID trống không được nhận là Results")

    notice = next(RESOURCE.glob("*thông báo*.png"))
    if finder.find(imread(notice), "missing_id") is None:
        raise SystemExit("Ảnh thông báo ID sai phải được nhận")
    if finder.find(img2, "missing_id") is not None:
        raise SystemExit("Màn nhập UID không được nhận nhầm là ID sai")

    gift5 = finder.find(by_prefix["5"][0], "gift")
    gift9 = finder.find(by_prefix["9"][0], "gift")
    if gift5 is None:
        raise SystemExit("Ảnh 5 phải thấy hộp quà")
    if gift9 is not None:
        raise SystemExit(f"Ảnh 9 không được nhận nhầm hộp quà, điểm {gift9.score:.2f}")
    print(f"gift ảnh 5 = {gift5.score:.2f} tại ({gift5.x},{gift5.y}); ảnh 9 không có quà")
    print("self-test ok")


if __name__ == "__main__":
    main()
