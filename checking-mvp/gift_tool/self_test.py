"""Khớp ảnh mẫu lên đúng screenshot từng bước. Không cần emulator."""

from pathlib import Path

import cv2

from gift_tool.flow import Runner
from gift_tool.paths import RESOURCE, ROOT, note_use
import numpy as np

from gift_tool.vision import (
    Finder,
    _badge_digits,
    _level_badge,
    _read_digit,
    avatar_point,
    draw_hits,
    field_point,
    imread,
    imwrite,
    pinball_reward,
    player_level,
    result_signature,
    signature_diff,
)

NAMES = ("search", "add", "visit", "gift", "select", "ok", "close")


def _shrink_badge(badge, drop_right: int):
    """Bỏ chữ số bên phải và thu viên lại, giống nhãn ít chữ số hơn."""
    white = (badge > 170).astype(np.uint8) * 255
    count, labels, stats, _ = cv2.connectedComponentsWithStats(white, 8)
    boxes = []
    for index in range(1, count):
        x, y, w, h, area = [int(value) for value in stats[index]]
        if h < 8 or area < 8:
            continue
        boxes.append((x, y, w, h, index))
    boxes.sort()
    if len(boxes) <= drop_right:
        raise RuntimeError("không đủ nét để thu viên")
    kept_last = boxes[-(drop_right + 1)]
    out = badge.copy()
    for _, _, _, _, index in boxes[-drop_right:]:
        out[labels == index] = 0
    right_pad = badge.shape[1] - (boxes[-1][0] + boxes[-1][2])
    new_w = kept_last[0] + kept_last[2] + max(1, right_pad)
    return out[:, :new_w]


def _read_badge(badge) -> int | None:
    digits = []
    for glyph in _badge_digits(badge):
        digit = _read_digit(glyph)
        if digit is None:
            return None
        digits.append(digit)
    if not digits:
        return None
    return int("".join(digits))


def screenshots() -> list[Path]:
    return sorted(p for p in RESOURCE.glob("*.png") if p.name[:1].isdigit())


def main():
    note_use("self_test đọc resource/")
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
    badge = _level_badge(img3, add)
    level_two = _read_badge(_shrink_badge(badge, 1))
    level_one = _read_badge(_shrink_badge(badge, 2))
    print(f"cấp khi còn 2 chữ số = {level_two}, 1 chữ số = {level_one}")
    if level_two != 29 or level_one != 2:
        raise SystemExit("Viên Lvl một hoặc hai chữ số phải đọc được cấp, không được thành rỗng")

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

    # Hai mẫu dùng để tự mò về ô nhập UID. Mỗi mẫu chỉ được nhận ở đúng màn của nó.
    yard = imread(next(RESOURCE.glob("0. màn hình ở sản.png")))
    goldrush = imread(next(RESOURCE.glob("0. màn hình chế độ goldrush.png")))
    if finder.find(yard, "friends") is None:
        raise SystemExit("Ảnh sân phải thấy icon Bạn bè")
    for label, shot in (("goldrush", goldrush), ("nhập UID", img2), ("kết quả", img3)):
        if finder.find(shot, "friends") is not None:
            raise SystemExit(f"Màn {label} không được nhận nhầm là màn chính")
    if finder.find(img2, "community") is None:
        raise SystemExit("Panel hồ sơ phải thấy nút Community")
    for label, shot in (("sân", yard), ("goldrush", goldrush)):
        if finder.find(shot, "community") is not None:
            raise SystemExit(f"Màn {label} không được nhận nhầm là panel hồ sơ")
    if finder.find(goldrush, "close") is None:
        raise SystemExit("Màn goldrush phải thấy nút X")

    _assert_other_frames(finder, img3, imread(notice))

    gift5 = finder.find(by_prefix["5"][0], "gift")
    gift9 = finder.find(by_prefix["9"][0], "gift")
    if gift5 is None:
        raise SystemExit("Ảnh 5 phải thấy hộp quà")
    if gift9 is not None:
        raise SystemExit(f"Ảnh 9 không được nhận nhầm hộp quà, điểm {gift9.score:.2f}")
    print(f"gift ảnh 5 = {gift5.score:.2f} tại ({gift5.x},{gift5.y}); ảnh 9 không có quà")
    reward6 = pinball_reward(by_prefix["6"][0])
    reward7 = pinball_reward(by_prefix["7"][0])
    if reward6 != 80 or reward7 != 80:
        raise SystemExit(f"Hộp quà phải đọc 80 pinball, ra ảnh 6 = {reward6}, ảnh 7 = {reward7}")
    for key in ("2", "3", "5", "9"):
        got = pinball_reward(by_prefix[key][0])
        if got is not None:
            raise SystemExit(f"Ảnh {key} không có hộp quà, không được đọc pinball {got}")
    print("pinball ảnh 6 và 7 = 80")
    _assert_pinball_multi_digit(by_prefix["7"][0])
    _assert_leave_after_gift(finder, by_prefix["9"][0], by_prefix["2"][0])
    _assert_game_update_2026_11(finder, by_prefix["2"][0])
    print("self-test ok")


def _assert_pinball_multi_digit(shot) -> None:
    """Ghép chữ số 8 và 0 thật từ ảnh 7 thành số nhiều chữ, chèn vệt sáng giống quả bóng lẫn giữa các chữ.

    Xếp theo x trước thì vệt sáng cắt đôi số và mất chữ số đuôi (808 ra 8, 80 ra rỗng).
    """
    import cv2
    import numpy as np

    height, width = shot.shape[:2]
    left = int(0.22 * width)
    top = int(0.42 * height)
    x8, x0, y = left + 127, left + 158, top + 47
    glyph8 = shot[y : y + 45, x8 : x8 + 33].copy()
    glyph0 = shot[y : y + 45, x0 : x0 + 33].copy()
    for text, expected in (("88", 88), ("808", 808), ("880", 880), ("80", 80)):
        start = x8 - (len(text) - 2) * 15
        for offset in (None, 10, 24, 40, 55):
            image = shot.copy()
            image[y : y + 45, left + 80 : left + 300] = np.tile(shot[y : y + 45, left + 60 : left + 61], (1, 220, 1))
            for index, char in enumerate(text):
                xx = start + index * 31
                image[y : y + 45, xx : xx + 33] = glyph8 if char == "8" else glyph0
            if offset is not None:
                cv2.circle(image, (start + offset, y - 28), 24, (120, 60, 60), -1)
                cv2.circle(image, (start + offset, y - 28), 19, (255, 255, 255), -1)
            got = pinball_reward(image)
            if got != expected:
                raise SystemExit(f"Số {expected} có vệt sáng lệch {offset} phải đọc {expected}, ra {got}")
    print("pinball nhiều chữ số 88, 808, 880, 80 đọc đủ, kể cả khi có vệt sáng lẫn giữa")


class _Stop:
    def is_set(self) -> bool:
        return False


class _Shots:
    def __init__(self, frames):
        self.frames = frames
        self.index = 0
        self.taps: list[tuple[int, int]] = []

    def screenshot(self):
        shot = self.frames[min(self.index, len(self.frames) - 1)]
        self.index += 1
        return shot

    def tap(self, x: int, y: int) -> None:
        self.taps.append((int(x), int(y)))


def _assert_leave_after_gift(finder, house, search) -> None:
    """Sau OK chỉ bấm X một lần trên ảnh nhà, rồi nhận kính lúp. Không bấm lần hai."""
    close = finder.locate(house, "close", scales=(1.0,))
    if close.w == 0 or close.score < 0.80:
        raise SystemExit("Ảnh nhà sau quà phải thấy nút X")
    if finder.find(search, "search") is None:
        raise SystemExit("Ảnh ô nhập phải thấy kính lúp")

    adb = _Shots([search])
    runner = Runner(adb, finder, lambda *_args: None, _Stop())
    if not runner._leave_after_gift(house):
        raise SystemExit("Bấm X xong phải thấy lại ô nhập")
    if len(adb.taps) != 1:
        raise SystemExit(f"Chỉ được bấm X một lần, đã bấm {len(adb.taps)}")
    x, y = adb.taps[0]
    if abs(x - close.x) > 8 or abs(y - close.y) > 8:
        raise SystemExit(f"Bấm X lệch ({x},{y}) so với ({close.x},{close.y})")

    adb = _Shots([house, search])
    runner = Runner(adb, finder, lambda *_args: None, _Stop())
    if not runner._leave_after_gift(house) or len(adb.taps) != 1:
        raise SystemExit("Nhà còn trên màn cũng chỉ được bấm X một lần")
    print("thoát nhà sau quà: một cú bấm X rồi về ô nhập")


def _assert_game_update_2026_11(finder, search) -> None:
    """Ảnh thật sau bản cập nhật game: nút Apply thay Add, màn Rewards sau OK, vệt sáng chạm chữ số."""
    folder = RESOURCE / "cap-nhat-2026-11"
    apply_shot = imread(folder / "ket-qua-nut-apply-lvl-409.png")
    select = imread(folder / "select-60-co-vet-sang.png")
    rewards = imread(folder / "rewards-sau-ok-x-bi-mo.png")
    house = imread(folder / "nha-sau-rewards-x-sang.png")

    runner = Runner(_Shots([apply_shot]), finder, lambda *_args: None, _Stop())
    found = runner._result_add(apply_shot, (1.0,))
    if found is None:
        raise SystemExit("Hàng kết quả ghi Apply phải thấy nút xanh")
    level = player_level(apply_shot, found)
    if level != 409:
        raise SystemExit(f"Cấp 409 sau khung avatar tối phải đọc 409, ra {level}")
    reward = pinball_reward(select)
    if reward != 60:
        raise SystemExit(f"Màn Select có vệt sáng chạm chữ số phải đọc 60, ra {reward}")

    # Màn Rewards làm mờ nút X. Bấm lúc đó bị nuốt, nên chỉ bấm khi X đã sáng.
    adb = _Shots([rewards, rewards, house, search])
    runner = Runner(adb, finder, lambda *_args: None, _Stop())
    if not runner._leave_after_gift(rewards):
        raise SystemExit("Qua màn Rewards rồi bấm X phải về lại ô nhập")
    close = finder.locate(house, "close", scales=(1.0,))
    if len(adb.taps) != 1 or abs(adb.taps[0][0] - close.x) > 8 or abs(adb.taps[0][1] - close.y) > 8:
        raise SystemExit(f"Chỉ được bấm X khi đã sáng, một lần. Các cú bấm: {adb.taps}")
    print("bản cập nhật 2026-11: nút Apply, cấp 409, pinball 60, chờ màn Rewards rồi mới bấm X")


def _letterbox(image, width: int, height: int, bar: int):
    """Đặt ảnh game vào khung lớn hơn, viền đen đều. Giống screencap có thanh đen."""
    canvas = np.zeros((height, width, 3), np.uint8)
    src_h, src_w = image.shape[:2]
    avail_w = width - 2 * bar
    avail_h = height - 2 * bar
    scale = min(avail_w / src_w, avail_h / src_h)
    tw, th = max(1, int(src_w * scale)), max(1, int(src_h * scale))
    resized = cv2.resize(image, (tw, th), interpolation=cv2.INTER_AREA)
    x0 = (width - tw) // 2
    y0 = (height - th) // 2
    canvas[y0 : y0 + th, x0 : x0 + tw] = resized
    return canvas


def _assert_other_frames(finder, found, notice) -> None:
    """ID có thật vẫn phải thấy hàng Results khi khung không còn đúng 9:16."""
    framed = _letterbox(found, 720, 1280, 24)
    search = finder.find(framed, "search", scales=(1.0,))
    results = finder.find(framed, "results", scales=(1.0,))
    add = finder.find(framed, "add", scales=(1.0,))
    if search is None or results is None or add is None:
        raise SystemExit("Khung có viền đen phải thấy kính lúp, Results và Add")
    if finder.find(framed, "missing_id", scales=(1.0,)) is not None:
        raise SystemExit("Hàng kết quả trong khung có viền không được nhận là ID sai")
    level = player_level(framed, add)
    if level != 299:
        raise SystemExit(f"Khung có viền đen phải đọc cấp 299, ra {level}")

    tall = cv2.resize(found, (720, 1600), interpolation=cv2.INTER_AREA)
    if finder.find(tall, "results", scales=(1.0,)) is None or finder.find(tall, "add", scales=(1.0,)) is None:
        raise SystemExit("Khung cao hơn 9:16 phải thấy Results và Add")
    if finder.find(tall, "missing_id", scales=(1.0,)) is not None:
        raise SystemExit("Khung cao không được nhận hàng kết quả là ID sai")
    level = player_level(tall, finder.find(tall, "add", scales=(1.0,)))
    if level != 299:
        raise SystemExit(f"Khung bị kéo dọc phải đọc cấp 299, ra {level}")

    missing = _letterbox(notice, 720, 1280, 24)
    if finder.find(missing, "results", scales=(1.0,)) is not None:
        raise SystemExit("Thông báo ID sai trong khung có viền không được nhận là Results")


if __name__ == "__main__":
    main()
