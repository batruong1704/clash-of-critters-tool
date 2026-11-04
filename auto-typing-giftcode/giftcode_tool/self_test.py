"""Khớp mẫu gift code lên ảnh từng bước. Không cần emulator."""

from __future__ import annotations

import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
for _path in (_REPO / "checking-mvp", _REPO / "auto-typing-giftcode"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from gift_tool.paths import RESOURCE
from gift_tool.vision import Finder, imread

from giftcode_tool.codes import LIST_FILE, load_codes, parse_codes
from giftcode_tool.flow import Runner
from giftcode_tool.vision import Icons, field_point, reward_bar

ROOT = Path(__file__).resolve().parent.parent / "resource"


class _Stop:
    def is_set(self) -> bool:
        return False


class _Tape:
    """Đổi ảnh khi bấm đúng nút của màn hiện tại."""

    def __init__(self, shots: dict, centers: dict, start: str):
        self.shots = shots
        self.centers = centers
        self.name = start
        self.taps: list[tuple[str, str]] = []
        self.typed: list[str] = []
        self.swipes = 0
        self.backs = 0

    def screenshot(self):
        return self.shots[self.name]

    def tap(self, x: int, y: int) -> None:
        button = self._which(x, y)
        self.taps.append((self.name, button))
        nxt = {
            ("goldrush", "close"): "camp",
            ("camp", "friends"): "profile",
            ("profile", "gear"): "settings",
            ("list", "redemption"): "dialog",
            ("dialog", "confirm"): "reward" if self.name == "dialog" else "dialog",
        }.get((self.name, button))
        if self.name == "dialog" and button == "confirm" and self.typed == ["SAI"]:
            nxt = "stuck"
        if nxt:
            self.name = nxt

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration_ms: int = 350) -> None:
        self.swipes += 1
        if self.name == "settings":
            self.name = "list"

    def clear_text(self, count: int = 16) -> None:
        return None

    def input_code(self, text: str) -> None:
        self.typed.append(text)

    def back(self) -> None:
        self.backs += 1
        if self.name == "reward":
            self.name = "dialog"

    def _which(self, x: int, y: int) -> str:
        best, dist = "khac", 80
        for name, (cx, cy) in self.centers[self.name].items():
            gap = abs(x - cx) + abs(y - cy)
            if gap < dist:
                best, dist = name, gap
        return best


def _shots():
    files = sorted(ROOT.glob("*.png"))
    camp, profile, settings, listed, dialog, reward, stuck = [imread(path) for path in files]
    goldrush = imread(next(RESOURCE.glob("0. màn hình chế độ goldrush.png")))
    return {
        "goldrush": goldrush,
        "camp": camp,
        "profile": profile,
        "settings": settings,
        "list": listed,
        "dialog": dialog,
        "reward": reward,
        "stuck": stuck,
    }


def _centers(icons: Icons, finder: Finder, shots: dict) -> dict:
    centers = {}
    for name, shot in shots.items():
        points = {}
        for icon in ("gear", "redemption", "settings", "confirm"):
            hit = icons.find(shot, icon)
            if hit is not None:
                points[icon] = (hit.x, hit.y)
        friends = finder.find(shot, "friends")
        if friends is not None:
            points["friends"] = (friends.x, friends.y)
        close = finder.locate(shot, "close")
        if close is not None and close.w and close.score >= 0.80:
            points["close"] = (close.x, close.y)
        if "confirm" in points:
            points["field"] = field_point(shot, type("C", (), {"x": points["confirm"][0], "y": points["confirm"][1]})())
        centers[name] = points
    return centers


def test_screens(icons: Icons, finder: Finder, shots: dict) -> None:
    # close có ở panel hồ sơ và Settings. Luồng bấm bánh răng hoặc kéo trước, không bấm X đó.
    need = {
        "camp": {"friends"},
        "profile": {"gear"},
        "settings": {"settings"},
        "list": {"settings", "redemption"},
        "dialog": {"confirm"},
        "stuck": {"confirm"},
        "goldrush": {"close"},
    }
    forbid = {
        "camp": {"gear", "settings", "redemption", "confirm", "close"},
        "profile": {"friends", "settings", "redemption", "confirm"},
        "settings": {"gear", "redemption", "confirm", "friends"},
        "list": {"confirm", "friends", "gear"},
        "dialog": {"redemption", "reward"},
        "reward": {"confirm", "redemption", "settings", "gear", "friends"},
        "stuck": {"redemption"},
        "goldrush": {"friends", "gear", "settings", "redemption", "confirm"},
    }
    for name in forbid:
        got = set(_centers(icons, finder, {name: shots[name]})[name])
        got.discard("field")
        missing = need.get(name, set()) - got
        extra = forbid[name] & got
        if missing or extra:
            raise SystemExit(f"Màn {name} nhận {sorted(got)}, thiếu {sorted(missing)}, thừa {sorted(extra)}")
        bar = reward_bar(shots[name])
        if (name == "reward") != (bar is not None):
            raise SystemExit(f"Màn {name} thanh quà {'không thấy' if bar is None else 'nhận nhầm'}")
    print("ảnh từng bước: đúng màn")


def test_from_goldrush(icons, finder, shots, centers) -> None:
    tape = _Tape(shots, centers, "goldrush")
    notes = []
    runner = Runner(tape, notes.append, _Stop(), finder)
    runner.icons = icons
    runner.quick = True
    status = runner.run("WelcomeGift")
    if status != "nhan":
        raise SystemExit(f"Từ Goldrush phải nhận mã, ra {status} {notes}")
    if tape.typed != ["WelcomeGift"]:
        raise SystemExit(f"Phải gõ đúng một mã, ra {tape.typed}")
    buttons = [button for _name, button in tape.taps]
    if "reward" in [name for name, _button in tape.taps]:
        raise SystemExit(f"Không được bấm trên màn quà, ra {tape.taps}")
    for earlier, later in (("close", "friends"), ("friends", "gear"), ("gear", "redemption"), ("redemption", "confirm")):
        if buttons.index(earlier) > buttons.index(later):
            raise SystemExit(f"Sai thứ tự {earlier} trước {later}: {buttons}")
    if tape.swipes < 1:
        raise SystemExit("Settings chưa hiện Redemption Code thì phải kéo")
    print("từ Goldrush: X, Bạn bè, bánh răng, kéo, gõ, dừng khi có quà")


def test_from_settings(icons, finder, shots, centers) -> None:
    tape = _Tape(shots, centers, "settings")
    notes = []
    runner = Runner(tape, notes.append, _Stop(), finder)
    runner.icons = icons
    runner.quick = True
    status = runner.run("abc")
    buttons = [button for _name, button in tape.taps]
    if status != "nhan" or "friends" in buttons or "gear" in buttons or "close" in buttons:
        raise SystemExit(f"Đang ở Settings thì không mò lại từ đầu, ra {status} {buttons} {notes}")
    print("đang ở Settings: chỉ kéo và nhập")


def test_rejected_code(icons, finder, shots, centers) -> None:
    tape = _Tape(shots, centers, "dialog")
    notes = []
    runner = Runner(tape, notes.append, _Stop(), finder)
    runner.icons = icons
    runner.quick = True
    status = runner.run("SAI")
    if status != "khong_nhan":
        raise SystemExit(f"Mã không nhận phải dừng, ra {status} {notes}")
    if any(name == "stuck" and button != "field" for name, button in tape.taps):
        raise SystemExit(f"Hộp thoại đứng yên thì không bấm thêm, ra {tape.taps}")
    if not any("không được nhận" in note for note in notes):
        raise SystemExit(f"Log phải báo mã không được nhận, ra {notes}")
    print("mã không nhận: hộp thoại đứng yên, không bấm tiếp")


def test_default_file() -> None:
    good, bad = parse_codes("welcomegift\n\n# ghi chú\nweeklygift  # pinball\nbad-code\ntata2026, TATAMOON")
    if good != ["welcomegift", "weeklygift", "tata2026", "TATAMOON"] or bad != ["bad-code"]:
        raise SystemExit(f"Tách nhiều mã sai, ra {good} {bad}")
    loaded = load_codes()
    again, _skipped = parse_codes(LIST_FILE.read_text(encoding="utf-8"))
    if not loaded or loaded != again:
        raise SystemExit(f"File mã mặc định không khớp parser, ra {loaded}")
    print(f"nhiều mã: file mặc định có {len(loaded)} mã, ô nhập nhận nhiều dòng")


def test_two_codes(icons, finder, shots, centers) -> None:
    tape = _Tape(shots, centers, "dialog")
    notes = []
    runner = Runner(tape, notes.append, _Stop(), finder)
    runner.icons = icons
    runner.quick = True
    counts = runner.run_many(["WelcomeGift", "weeklygift"])
    if counts["nhan"] != 2 or tape.typed != ["WelcomeGift", "weeklygift"]:
        raise SystemExit(f"Hai mã phải được gõ, ra {counts} {tape.typed} {notes}")
    if any(name == "reward" for name, _button in tape.taps):
        raise SystemExit(f"Không được bấm trên màn quà, ra {tape.taps}")
    if tape.backs < 1:
        raise SystemExit("Sau mã đầu phải rời màn quà bằng Back")
    print("hai mã: nhận xong thì rời màn quà, gõ mã sau")


def main() -> None:
    test_default_file()
    icons = Icons()
    finder = Finder()
    shots = _shots()
    test_screens(icons, finder, shots)
    centers = _centers(icons, finder, shots)
    test_from_goldrush(icons, finder, shots, centers)
    test_from_settings(icons, finder, shots, centers)
    test_rejected_code(icons, finder, shots, centers)
    test_two_codes(icons, finder, shots, centers)


if __name__ == "__main__":
    main()
