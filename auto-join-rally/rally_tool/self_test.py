"""Khớp màu nút và icon lên ảnh từng bước. Không cần emulator."""

from __future__ import annotations

import threading
from pathlib import Path

import tkinter as tk

from gift_tool.paths import RESOURCE
from gift_tool.vision import Finder, draw_hits, imread, imwrite
from rally_tool.paths import LOGS

from gift_tool.gui import App

from rally_tool.flow import Runner
from rally_tool.vision import (
    card_joins,
    chat_join_buttons,
    home_goldrush,
    jump_down,
    list_joins,
    load_icons,
    read_screen,
    reward_button,
    send_button,
    topmost,
)

RALLY = Path(__file__).resolve().parent.parent / "resource"

EXPECTED = {
    "Step 1": ("map", 0),
    "Step 2": ("chat", 1),
    "Step 3.1": ("multi", 3),
    "Step 3": ("single", 1),
    "Step 4.1": ("multi", 0),
    "Step 4": ("single", 0),
    "Step 5": ("map", 0),
    "Step 6": ("chat", 0),
}


def _key(path: Path) -> str:
    name = path.name
    for prefix in ("Step 3.1", "Step 4.1", "Step 1", "Step 2", "Step 3", "Step 4", "Step 5", "Step 6", "Step 7"):
        if name.startswith(prefix):
            return prefix
    raise SystemExit(f"Không đặt tên được ảnh {name}")


def _load() -> dict[str, object]:
    shots = {}
    for path in sorted(RALLY.iterdir()):
        if not path.name.startswith("Step "):
            continue
        shots[_key(path)] = imread(path)
    missing = [key for key in EXPECTED if key not in shots]
    if missing:
        raise SystemExit(f"Thiếu ảnh {missing}")
    return shots


def _finder() -> Finder:
    finder = Finder()
    load_icons(finder)
    return finder


def test_scenes() -> None:
    finder = _finder()
    shots = _load()
    out = LOGS / "self-test-rally"
    for key, (scene, join_count) in EXPECTED.items():
        shot = shots[key]
        reading = read_screen(finder, shot)
        if reading.scene != scene or len(reading.joins) != join_count:
            raise SystemExit(
                f"{key}: ra {reading.scene}, {len(reading.joins)} nút xanh; "
                f"cần {scene}, {join_count}"
            )
        send = send_button(shot)
        if send is not None and any(abs(hit.x - send.x) < 20 and abs(hit.y - send.y) < 20 for hit in reading.joins):
            raise SystemExit(f"{key}: nút gửi tin bị nhận thành Join")
        if scene == "map":
            if reading.chat is None or reading.chat.score < 0.9:
                raise SystemExit(f"{key}: không thấy icon chat")
            if reading.close is None:
                raise SystemExit(f"{key}: bản đồ phải thấy nút X nhưng không được bấm")
            if abs(reading.chat.x - reading.close.x) < 40 and abs(reading.chat.y - reading.close.y) < 40:
                raise SystemExit(f"{key}: icon chat trùng nút X")
        if scene == "chat" and send is None and key == "Step 6":
            raise SystemExit("Chat chờ rally phải thấy nút gửi để không bấm nhầm nút X")
        if scene == "single" and reading.back is None:
            raise SystemExit(f"{key}: thiếu nút back")
        if scene == "multi" and reading.close is None:
            raise SystemExit(f"{key}: thiếu nút X")
        if key == "Step 3.1" and len(list_joins(reading)) != 3:
            raise SystemExit("Danh sách nhiều người phải có 3 nút xanh")
        if key == "Step 2" and len(card_joins(reading)) != 1:
            raise SystemExit("Chat phải có đúng 1 nút Join trên thẻ")
        buttons = chat_join_buttons(finder, shot) if key in ("Step 2", "Step 6") else []
        if key == "Step 2":
            if len(buttons) != 1:
                raise SystemExit(f"Mẫu nút Join phải thấy 1 nút, ra {len(buttons)}")
            color = card_joins(reading)[0]
            if abs(buttons[0].x - color.x) > 15 or abs(buttons[0].y - color.y) > 15:
                raise SystemExit("Tâm mẫu Join lệch khỏi nút xanh")
        if key == "Step 6" and buttons:
            raise SystemExit("Thanh xám trong chat bị nhận thành nút Join")
        hits = list(buttons) if key == "Step 2" else list(reading.joins)
        if reading.chat is not None and scene == "map":
            hits.append(reading.chat)
        if reading.back is not None and scene == "single":
            hits.append(reading.back)
        imwrite(out / f"{key}.png", draw_hits(shot, hits))
        print(f"{key}: {scene}, {len(reading.joins)} nút xanh")


def test_other_screens() -> None:
    """Sân chính phải vào Goldrush. Ảnh Goldrush có sẵn của tool quà không được bấm X."""
    finder = _finder()
    yard = imread(next(RESOURCE.glob("0. màn hình ở sản.png")))
    reading = read_screen(finder, yard)
    if reading.scene != "camp" or reading.goldrush is None:
        raise SystemExit(f"Sân chính phải là camp, ra {reading.scene}")
    goldrush = imread(next(RESOURCE.glob("0. màn hình chế độ goldrush.png")))
    reading = read_screen(finder, goldrush)
    if reading.scene != "map":
        raise SystemExit(f"Goldrush có sẵn phải là bản đồ, ra {reading.scene}")
    if reading.chat is None or reading.close is None:
        raise SystemExit("Goldrush có sẵn phải thấy cả icon chat và nút X")
    if abs(reading.chat.y - reading.close.y) < 80:
        raise SystemExit("Điểm mở chat quá gần nút X")
    print("sân và goldrush có sẵn: đúng")


def test_returns_home() -> None:
    """Ra khỏi Goldrush mà thanh mode còn nút thì bấm để vào lại. Trong bản đồ thì không."""
    finder = _finder()
    yard = imread(next(RESOURCE.glob("0. màn hình ở sản.png")))
    if home_goldrush(finder, yard) is None:
        raise SystemExit("Sân phải thấy nút Goldrush")
    inside = imread(next(RESOURCE.glob("0. màn hình chế độ goldrush.png")))
    if home_goldrush(finder, inside) is not None:
        raise SystemExit("Đang trong Goldrush không được bấm lại nút mode")
    shots = _load()
    if home_goldrush(finder, shots["Step 1"]) is not None or home_goldrush(finder, shots["Step 2"]) is not None:
        raise SystemExit("Bản đồ rally hoặc chat không được nhận nút Goldrush")
    pinball = imread(next(RESOURCE.glob("1. giao diện chính tab pinball.png")))
    reading = read_screen(finder, pinball)
    hit = home_goldrush(finder, pinball)
    if reading.scene in ("map", "chat", "single", "multi", "reward"):
        raise SystemExit(f"Màn ngoài mode bị nhận là đang chơi, ra {reading.scene}")
    if hit is None or hit.y < pinball.shape[0] * 0.80:
        raise SystemExit(f"Không thấy nút Goldrush ở thanh dưới, ra {hit}")
    stop = threading.Event()
    tape = _HomeTape(stop, pinball)
    runner = Runner(tape, tape.log, stop, finder)
    runner.quick = True
    runner.run()
    if tape.taps != [(hit.x, hit.y)]:
        raise SystemExit(f"Phải bấm đúng nút Goldrush {hit.x, hit.y}, ra {tape.taps}")
    print("ra khỏi mode: bấm lại Goldrush")


def test_goldrush_waits_out_the_animation() -> None:
    """Sau cú bấm Goldrush phải chờ hết 2 giây hoạt cảnh rồi mới chụp tiếp."""
    from rally_tool.flow import GOLDRUSH_ANIM

    stop = threading.Event()
    shot = _load()["Step 6"]
    tape = _HomeTape(stop, shot)
    runner = Runner(tape, tape.log, stop, _finder())
    waits = []
    runner._pause = lambda low, high: waits.append((low, high))
    runner._enter_goldrush(None, type("Hit", (), {"x": 3, "y": 4})())
    if tape.taps != [(3, 4)] or waits != [(GOLDRUSH_ANIM, GOLDRUSH_ANIM)] or GOLDRUSH_ANIM < 2:
        raise SystemExit(f"Phải bấm Goldrush rồi chờ hết hoạt cảnh, ra {tape.taps} {waits}")
    print("vào Goldrush: chờ hết hoạt cảnh rồi mới xem tiếp")


class _HomeTape:
    def __init__(self, stop, shot):
        self.stop = stop
        self.shot = shot
        self.taps = []
        self.n = 0

    def screenshot(self):
        self.n += 1
        if self.n > 4:
            self.stop.set()
        return self.shot

    def tap(self, x: int, y: int) -> None:
        self.taps.append((int(x), int(y)))
        self.stop.set()

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration_ms: int = 350) -> None:
        raise SystemExit("Màn ngoài mode không được kéo")

    def log(self, message: str) -> None:
        return None


def test_loop() -> None:
    shots = _load()
    stop = threading.Event()
    tape = _Tape(stop, shots)
    runner = Runner(tape, tape.log, stop, _finder())
    runner.quick = True
    runner.poll = 0
    counts = runner.run()
    names = [item[0] for item in tape.taps if item[1] != "swipe"]
    if names[:5] != ["Step 1", "Step 2", "Step 3", "Step 4", "Step 5"]:
        raise SystemExit(f"Sai thứ tự bấm: {names}")
    _away_from_close(shots["Step 1"], tape, "Step 1")
    _away_from_close(shots["Step 5"], tape, "Step 5")
    step4 = [item for item in tape.taps if item[0] == "Step 4" and item[1] != "swipe"]
    back = read_screen(_finder(), shots["Step 4"]).back
    if len(step4) != 1 or abs(step4[0][1] - back.x) > 25 or abs(step4[0][2] - back.y) > 25:
        raise SystemExit(f"Màn đã xin phải bấm back, ra {step4}")
    if not any("cuối chat" in line for line in tape.lines):
        raise SystemExit("Hết Join phải đứng cuối chat")
    step2 = [item for item in tape.taps if item[0] == "Step 2"]
    if any(item[1] == "swipe" for item in step2):
        raise SystemExit("Chat đang có Join mà vẫn kéo, cú bấm sẽ trượt")
    button = chat_join_buttons(_finder(), shots["Step 2"])[0]
    if len(step2) != 1 or abs(step2[0][1] - button.x) > 15 or abs(step2[0][2] - button.y) > 15:
        raise SystemExit(f"Phải bấm đúng tâm nút Join, ra {step2}")
    if counts["xin"] < 1 or counts["mo"] < 1:
        raise SystemExit(f"Chưa tính lượt xin: {counts}")
    print(f"vòng lặp: xin {counts['xin']}, mở {counts['mo']}")


def _roll_chat(img, dy: int):
    import numpy as np

    out = img.copy()
    height = img.shape[0]
    y0, y1 = int(height * 0.22), int(height * 0.70)
    out[y0:y1] = np.roll(out[y0:y1], dy, axis=0)
    return out


def test_first_chat_does_not_tap_around() -> None:
    """Chat vừa mở và đã ở tin mới thì không bấm bốn cú mặc định."""
    shots = _load()
    stop = threading.Event()
    tape = _ScrollTape(stop, [shots["Step 6"]])
    runner = Runner(tape, tape.log, stop, _finder())
    runner.quick = True
    runner.poll = 0
    runner.run()
    newer = 0
    for y1, y2 in tape.swipes:
        if y2 > y1:
            break
        newer += 1
    if newer != 1:
        raise SystemExit(f"Vào chat đã ở tin mới mà vẫn kéo {newer} lần: {tape.swipes}")
    print("vào chat: một lần kéo kiểm tra, không bấm thừa")


def test_scrolls_until_newest() -> None:
    """Chat còn trôi thì kéo tiếp, mỗi lần một cú, và dừng khi ảnh đứng yên."""
    shots = _load()
    base = shots["Step 6"]
    frames = [base, _roll_chat(base, 80), _roll_chat(base, 160), _roll_chat(base, 240), _roll_chat(base, 320)]
    frames.append(frames[-1])
    stop = threading.Event()
    tape = _ScrollTape(stop, frames)
    runner = Runner(tape, tape.log, stop, _finder())
    runner.quick = True
    runner.poll = 0
    runner.run()
    newer = 0
    for y1, y2 in tape.swipes:
        if y2 > y1:
            break
        newer += 1
    if newer < 5:
        raise SystemExit(f"Dừng kéo khi chat vẫn trôi, mới {newer} lần: {tape.swipes}")
    print(f"kéo tới tin mới nhất: {newer} lần")


class _ScrollTape:
    def __init__(self, stop, frames):
        self.stop = stop
        self.frames = frames
        self.i = 0
        self.swipes = []
        self.n = 0

    def screenshot(self):
        self.n += 1
        if self.n > 40:
            self.stop.set()
        return self.frames[min(self.i, len(self.frames) - 1)]

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration_ms: int = 350) -> None:
        self.swipes.append((int(y1), int(y2)))
        if y2 < y1:
            self.i += 1
        else:
            self.stop.set()

    def tap(self, x: int, y: int) -> None:
        raise SystemExit(f"Đang kéo xuống tin mới thì không bấm {(x, y)}")

    def log(self, message: str) -> None:
        return None


def test_jump_down() -> None:
    """Sau khi xem tin cũ, bấm mũi tên tím để về tin mới, không kéo dần."""
    finder = _finder()
    shots = _load()
    if "Step 7" not in shots:
        raise SystemExit("Thiếu ảnh nút mũi tên tím")
    top = shots["Step 7"]
    bottom = shots["Step 6"]
    hit = jump_down(finder, top)
    if hit is None:
        raise SystemExit("Không thấy nút mũi tên tím khi đang xem tin cũ")
    if jump_down(finder, bottom) is not None or jump_down(finder, shots["Step 2"]) is not None:
        raise SystemExit("Tin mới nhất không được có nút mũi tên tím")
    reading = read_screen(finder, top)
    if reading.scene != "chat":
        raise SystemExit(f"Màn có nút mũi tên phải là chat, ra {reading.scene}")
    out = LOGS / "self-test-rally"
    imwrite(out / "Step 7.png", draw_hits(top, [hit]))
    stop = threading.Event()
    tape = _DownTape(stop, top, bottom)
    runner = Runner(tape, tape.log, stop, finder)
    runner.quick = True
    runner.poll = 0
    runner._ready = True
    runner._returning = True
    runner.run()
    if len(tape.taps) != 1:
        raise SystemExit(f"Phải bấm đúng một lần mũi tên tím, ra {tape.taps}")
    x, y = tape.taps[0]
    if abs(x - hit.x) > 20 or abs(y - hit.y) > 20:
        raise SystemExit(f"Bấm lệch mũi tên {(x, y)} so với {(hit.x, hit.y)}")
    if tape.swipes:
        raise SystemExit(f"Có nút mũi tên mà vẫn kéo: {tape.swipes}")
    print("xuống tin mới: bấm mũi tên tím")


class _DownTape:
    def __init__(self, stop, top, bottom):
        self.stop = stop
        self.top = top
        self.bottom = bottom
        self.taps = []
        self.swipes = []
        self.n = 0

    def screenshot(self):
        self.n += 1
        if self.n > 8:
            self.stop.set()
        if self.taps:
            return self.bottom
        return self.top

    def tap(self, x: int, y: int) -> None:
        self.taps.append((int(x), int(y)))

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration_ms: int = 350) -> None:
        self.swipes.append((int(y1), int(y2)))

    def log(self, message: str) -> None:
        return None


def test_list_does_not_stick() -> None:
    """Ảnh không đổi sau cú bấm thì không bấm mãi một nút. Hai lần trượt thì bấm X."""
    shots = _load()
    reading = read_screen(_finder(), shots["Step 3.1"])
    if reading.close is None:
        raise SystemExit("Danh sách thiếu nút X")
    stop = threading.Event()
    tape = _Tape(stop, shots, start="Step 3.1", freeze=True, close_at=(reading.close.x, reading.close.y))
    runner = Runner(tape, tape.log, stop, _finder())
    runner.quick = True
    runner.run()
    taps = [item for item in tape.taps if item[1] != "swipe"]
    if len(taps) != 3:
        raise SystemExit(f"Cần 2 lần xin rồi 1 lần X, ra {taps}")
    top = topmost(list_joins(reading))
    for item in taps[:2]:
        if abs(item[1] - top.x) > 30 or abs(item[2] - top.y) > 30:
            raise SystemExit(f"Không bấm nút xanh trên cùng: {item}")
    if abs(taps[2][1] - reading.close.x) > 30 or abs(taps[2][2] - reading.close.y) > 30:
        raise SystemExit(f"Lần cuối phải là nút X, ra {taps[2]}")
    print("danh sách: hai lần xin không ăn thì đóng")


def test_reward() -> None:
    """Hộp nhận điểm và hộp nhận năng lượng đều đóng bằng Confirm, không bấm nút X đáy màn."""
    finder = _finder()
    paths = sorted(RALLY.glob("Exception*.png"))
    if len(paths) != 2:
        raise SystemExit(f"Cần 2 ảnh hộp hoàn thành rally, thấy {len(paths)}")
    out = LOGS / "self-test-rally"
    for path in paths:
        shot = imread(path)
        reading = read_screen(finder, shot)
        button = reward_button(reading)
        if reading.scene != "reward" or button is None:
            raise SystemExit(f"{path.name}: ra {reading.scene}, cần hộp thưởng")
        if abs(button.x - reading.width / 2) > reading.width * 0.08:
            raise SystemExit(f"{path.name}: Confirm không nằm giữa")
        if button.y < reading.height * 0.75:
            raise SystemExit(f"{path.name}: Confirm quá cao")
        imwrite(out / f"{path.stem}.png", draw_hits(shot, [button]))
        stop = threading.Event()
        tape = _RewardTape(stop, shot)
        runner = Runner(tape, tape.log, stop, finder)
        runner.quick = True
        runner.run()
        if len(tape.taps) != 1:
            raise SystemExit(f"{path.name}: phải bấm đúng một lần, ra {tape.taps}")
        x, y = tape.taps[0]
        if abs(x - button.x) > 20 or abs(y - button.y) > 20:
            raise SystemExit(f"{path.name}: bấm lệch Confirm {(x, y)} so với {(button.x, button.y)}")
        if y > reading.height * 0.94:
            raise SystemExit(f"{path.name}: bấm quá thấp, dễ trúng nút X")
        if chat_join_buttons(finder, shot):
            raise SystemExit(f"{path.name}: hộp thưởng bị nhận thành nút Join trong chat")
        print(f"{path.stem}: đóng bằng Confirm")


class _RewardTape:
    def __init__(self, stop, shot):
        self.stop = stop
        self.shot = shot
        self.taps = []

    def screenshot(self):
        return self.shot

    def tap(self, x: int, y: int) -> None:
        self.taps.append((int(x), int(y)))
        self.stop.set()

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration_ms: int = 350) -> None:
        raise SystemExit("Hộp thưởng không được kéo")

    def log(self, message: str) -> None:
        if "hoàn thành" not in message and "Auto join" not in message and "Đã dừng" not in message:
            raise SystemExit(f"Log lạ trên hộp thưởng: {message}")


def test_window() -> None:
    settings = Path(__file__).resolve().parents[2] / "checking-mvp" / "logs" / "cua-so.json"
    saved = settings.read_text(encoding="utf-8") if settings.exists() else None
    root = tk.Tk()
    try:
        app = App(root)
        root.update()
        app.show_list()
        root.update()
        if not app.list_page.winfo_ismapped() or app.rally_page.winfo_ismapped():
            raise SystemExit("Danh sách UID không hiện")
        app.show_rally()
        root.update()
        if app.mode != "rally" or not app.rally_page.winfo_ismapped() or app.list_page.winfo_ismapped():
            raise SystemExit("Chế độ rally không hiện")
        if app.primary_btn.cget("text") != "▶  Bắt đầu":
            raise SystemExit("Nút chạy phải là Bắt đầu khi chưa chạy")
        if "nút xanh" not in app.hint_var.get():
            raise SystemExit("Thiếu hướng dẫn rally")
        called = []
        app.start_rally = lambda: called.append("rally")
        app.run_current()
        if called != ["rally"]:
            raise SystemExit("Bắt đầu ở chế độ rally không chạy join rally")
        app.show_list()
        root.update()
        if app.mode != "list" or not app.list_page.winfo_ismapped() or app.rally_page.winfo_ismapped():
            raise SystemExit("Quay lại danh sách UID bị kẹt ở rally")
        app.show_scan()
        root.update()
        if not app.scan_page.winfo_ismapped() or app.primary_btn.cget("text") != "▶  Bắt đầu":
            raise SystemExit("Chế độ quét ID bị mất")
        app.show_rally()
        app.running = True
        app.show_list()
        if app.mode != "rally":
            raise SystemExit("Đang chạy vẫn đổi được chế độ")
    finally:
        if "app" in locals():
            app.running = False
            app.show_list()
        root.destroy()
        if saved is None:
            settings.unlink(missing_ok=True)
        else:
            settings.write_text(saved, encoding="utf-8")
    print("cửa sổ: rally nằm cùng màn nhận quà")


def _away_from_close(shot, tape, name: str) -> None:
    close = read_screen(_finder(), shot).close
    for item in tape.taps:
        if item[0] != name or item[1] == "swipe":
            continue
        if abs(item[1] - close.x) < 40 and abs(item[2] - close.y) < 40:
            raise SystemExit(f"{name}: bấm trúng nút X, thoát khỏi Goldrush")


class _Tape:
    def __init__(self, stop, shots, start="Step 1", freeze=False, close_at=None):
        self.stop = stop
        self.shots = shots
        self.name = start
        self.freeze = freeze
        self.close_at = close_at
        self.taps = []
        self.lines = []
        self.n = 0

    def screenshot(self):
        self.n += 1
        if self.n > 24:
            self.stop.set()
        return self.shots[self.name]

    def tap(self, x: int, y: int) -> None:
        self.taps.append((self.name, int(x), int(y)))
        if self.freeze:
            if self.close_at and abs(x - self.close_at[0]) < 40 and abs(y - self.close_at[1]) < 40:
                self.stop.set()
            return
        nxt = {
            "Step 1": "Step 2",
            "Step 2": "Step 3",
            "Step 3": "Step 4",
            "Step 4": "Step 5",
            "Step 5": "Step 6",
            "Step 3.1": "Step 4.1",
        }.get(self.name)
        if nxt:
            self.name = nxt

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration_ms: int = 350) -> None:
        self.taps.append((self.name, "swipe", int(x1), int(y1), int(x2), int(y2)))

    def log(self, message: str) -> None:
        self.lines.append(message)


def main() -> None:
    test_scenes()
    test_other_screens()
    test_returns_home()
    test_goldrush_waits_out_the_animation()
    test_loop()
    test_first_chat_does_not_tap_around()
    test_scrolls_until_newest()
    test_jump_down()
    test_list_does_not_stick()
    test_reward()
    test_window()
    print("self-test rally ok")


if __name__ == "__main__":
    main()
