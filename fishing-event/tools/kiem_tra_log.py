"""Đọc nhật ký một phiên câu cá (chỉ cần thư mục logs người dùng gửi, không cần video) và chấm xem tool chạy ra sao.

Trả lời bốn câu hỏi mà trước đây phải ghép video mới biết:
- Máy này ra sao: chụp một ảnh mất bao lâu, độ trễ cú bấm tool dò được là bao nhiêu, đã dò xong chưa.
- Cú bấm đáp ở đâu: lệch tâm bao nhiêu px theo từng độ rộng vùng (147/110/73/36), bao nhiêu cú trượt, bao nhiêu cú thừa.
- Nhanh hay chậm: mỗi thanh mất bao lâu từ lúc hiện tới lúc bấm, bao lâu thì xác nhận được trúng.
- Có gì bất thường: những điều cần sửa, viết thành câu để đọc là hiểu.

Chạy từ thư mục fishing-event:
    py -3 tools/kiem_tra_log.py                      phiên mới nhất trong logs/
    py -3 tools/kiem_tra_log.py <thư mục>            mọi phiên trong thư mục đó (vd. log người dùng gửi)
    py -3 tools/kiem_tra_log.py <file -vet.txt>      một phiên

Đọc được cả nhật ký bản cũ (1.2.x, 1.3.0): phần chữ nổ sẽ báo "bản cũ chưa ghi".
"""

from __future__ import annotations

import csv
import re
import statistics
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from fishing_tool.paths import LOGS  # noqa: E402

# Độ rộng vùng vàng của game, px trên ảnh 720. Vùng đọc được lệch vài px nên gom theo mốc gần nhất.
WIDTHS = (147, 110, 73, 36)
GAME_TIMER = 30.0

STAMP = re.compile(r"^\[\s*([\d.]+)\] (.*)$")
SCENE = re.compile(r"^màn (\w+) \(chụp ([\d.]+)-([\d.]+)s\)")
SAMPLE = re.compile(r"^mẫu t=([\d.]+) mồi=(\d+) vùng=(\d+)-(\d+) .*?cùng=(\w+).*?chụp ([\d.]+)-([\d.]+)")
TAP = re.compile(r"^BẤM lệnh t=([\d.]+) .*?trễ=([\d.]+) (?:máy|học)=([\d.]+)")
FLASH = re.compile(r"^chữ nổ ở \+([\d.]+)s \(trắng ([\d.]+), chữ (\d+)\): độ trễ trong ([\d.]+)-([\d.]+)s")
DELAY = re.compile(r"^độ trễ cú bấm của máy ([\d.]+) → ([\d.]+)s")
LATE = re.compile(r"^ảnh \+([\d.]+)s sau lệnh chưa nổ chữ mà vẫn trúng")
PROBE = re.compile(r"^trượt dù mồi ở giữa vùng lúc giả định: dò độ trễ máy ([+-][\d.]+)s")
BIAS_PROBE = re.compile(r"^trượt sát tâm dù độ trễ đã chắc theo chữ nổ: dò lệch nhắm ([+-][\d.]+)s")
PROBE_HIT = re.compile(r"^cú dò ([\d.]+)s trúng")
BIAS = re.compile(r"^lệch nhắm học được ([+-][\d.]+)s theo (\d+) cú")
TAP_BIAS = re.compile(r"lệch=([+-][\d.]+)")
CAST = re.compile(r"^lượt (\d+): (\d+) lần bấm thanh trượt")
SPECIES = re.compile(r"^loài=(.*)$")
UNMEASURED = re.compile(r"^err_px=không đo được(?: \((.*)\))?")


def _width_bin(width: float) -> int:
    return min(WIDTHS, key=lambda w: abs(w - width))


def _num(text: str) -> float | None:
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def _median(values) -> float | None:
    values = [v for v in values if v is not None]
    return statistics.median(values) if values else None


def _pct(values, q: float) -> float | None:
    values = sorted(v for v in values if v is not None)
    if not values:
        return None
    return values[min(len(values) - 1, int(round(q * (len(values) - 1))))]


def _fmt(value, spec: str = ".2f", unit: str = "") -> str:
    return "—" if value is None else f"{format(value, spec)}{unit}"


class Session:
    def __init__(self, vet: Path):
        self.vet = vet
        self.stem = vet.name[: -len("-vet.txt")]
        self.shots: list[float] = []  # thời gian chụp một ảnh
        self.delay_start: float | None = None
        self.delay_changes: list[tuple[float, float, float]] = []  # (giờ, từ, tới)
        self.flashes: list[dict] = []
        self.late_frames: list[float] = []
        self.probes: list[float] = []
        self.probe_hits: list[float] = []
        self.bias_start: float | None = None
        self.bias_changes: list[tuple[float, int]] = []  # (lệch nhắm, số cú dùng)
        self.bar_waits: list[tuple[int, float]] = []  # (độ rộng, giây từ lúc thanh hiện tới lệnh bấm)
        self.confirm: list[tuple[str, float]] = []  # (cách xác nhận, giây từ lệnh tới TRÚNG)
        self.unmeasured_reasons: list[str] = []
        self.taps: list[dict] = []
        self.casts: list[dict] = []
        self.species: list[str] = []
        self.old_format = True
        self.end_time = 0.0
        self.tap_count_trace = 0
        self._read_vet()
        self._read_taps()
        self._read_casts()

    # ----- đọc file -----

    def _read_vet(self) -> None:
        bar_since: float | None = None
        bar_width = 0
        last_tap_t: float | None = None
        last_tap_clock: float | None = None
        last_flash_clock: float | None = None
        for raw in self.vet.read_text(encoding="utf-8").splitlines():
            m = STAMP.match(raw)
            if not m:
                continue
            clock, text = float(m.group(1)), m.group(2)
            self.end_time = clock
            if (s := SCENE.match(text)):
                self.shots.append(float(s.group(3)) - float(s.group(2)))
                if s.group(1) != "slider":
                    bar_since = None
                continue
            if (s := SAMPLE.match(text)):
                self.shots.append(float(s.group(7)) - float(s.group(6)))
                if s.group(5) == "thanh_moi" or bar_since is None:
                    bar_since = float(s.group(1))
                    bar_width = int(s.group(4)) - int(s.group(3))
                continue
            if (s := TAP.match(text)):
                self.tap_count_trace += 1
                last_tap_t = float(s.group(1))
                last_tap_clock = clock
                if self.delay_start is None:
                    self.delay_start = float(s.group(3))
                if "máy=" in text:
                    self.old_format = False
                if self.bias_start is None and (b := TAP_BIAS.search(text)):
                    self.bias_start = float(b.group(1))
                if bar_since is not None:
                    self.bar_waits.append((_width_bin(bar_width), last_tap_t - bar_since))
                    bar_since = None
                continue
            if (s := FLASH.match(text)):
                self.old_format = False
                self.flashes.append(
                    {
                        "clock": clock,
                        "offset": float(s.group(1)),
                        "white": float(s.group(2)),
                        "text": int(s.group(3)),
                        "lo": float(s.group(4)),
                        "hi": float(s.group(5)),
                    }
                )
                last_flash_clock = clock
                continue
            if (s := DELAY.match(text)):
                self.old_format = False
                self.delay_changes.append((clock, float(s.group(1)), float(s.group(2))))
                continue
            if (s := LATE.match(text)):
                self.late_frames.append(float(s.group(1)))
                continue
            if (s := PROBE.match(text)) or (s := BIAS_PROBE.match(text)):
                self.probes.append(float(s.group(1)))
                continue
            if (s := PROBE_HIT.match(text)):
                self.probe_hits.append(float(s.group(1)))
                continue
            if (s := BIAS.match(text)):
                self.bias_changes.append((float(s.group(1)), int(s.group(2))))
                continue
            if text == "TRÚNG" and last_tap_t is not None:
                how = "chữ nổ" if last_flash_clock is not None and clock - last_flash_clock < 0.05 else "thanh đổi/kết quả"
                self.confirm.append((how, clock - last_tap_t))
                last_tap_t = None
                continue
            if (s := UNMEASURED.match(text)):
                self.unmeasured_reasons.append(s.group(1) or "không rõ")
                continue
            if (s := SPECIES.match(text)):
                self.species.append(s.group(1))
                continue

    def _read_taps(self) -> None:
        path = self.vet.with_name(self.stem + "-bam.csv")
        if not path.exists():
            return
        with path.open(encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                if not row.get("lan") or row["lan"] == "0":
                    continue
                width = _num(row.get("rong")) or 0
                self.taps.append(
                    {
                        "luot": int(row["luot"]),
                        "thanh": int(row["thanh"] or 0),
                        "lan_tren_thanh": int(row["lan_tren_thanh"] or 1),
                        "ket_qua": row.get("ket_qua_bam") or "",
                        "t": _num(row.get("t_lenh")),
                        "tre": _num(row.get("tre")),
                        "may": _num(row.get("hoc")),
                        "xe": _num(row.get("xe")),
                        "width": width,
                        "bin": _width_bin(width),
                        "err": _num(row.get("err_px")),
                        "so_mau": int(row.get("so_mau") or 0),
                        "cho": _num(row.get("cho")),
                        "van_toc": _num(row.get("van_toc")),
                    }
                )

    def _read_casts(self) -> None:
        path = self.vet.with_name(self.stem + ".csv")
        if not path.exists():
            return
        with path.open(encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                self.casts.append(
                    {
                        "luot": int(row["luot"]),
                        "ket_qua": row.get("ket_qua") or "",
                        "vang": _num(row.get("vang")) or 0,
                        "loai": row.get("loai") or "",
                        "pham": row.get("pham") or "",
                        "so_lan_bam": int(row.get("so_lan_bam") or 0),
                        "giay": _num(row.get("giay")),
                    }
                )

    # ----- kết luận -----

    @property
    def delay_end(self) -> float | None:
        if self.delay_changes:
            return self.delay_changes[-1][2]
        return self.delay_start

    def delay_estimate(self) -> tuple[float | None, float | None, str]:
        """(thấp nhất, cao nhất, cách tính) của độ trễ thật theo các lần thấy chữ nổ."""
        if not self.flashes:
            return None, None, "chưa thấy chữ nổ lần nào"
        lo = max(f["lo"] for f in self.flashes)
        hi = min(f["hi"] for f in self.flashes)
        if lo <= hi:
            return lo, hi, f"giao của {len(self.flashes)} khoảng chữ nổ"
        mids = sorted((f["lo"] + f["hi"]) / 2 for f in self.flashes)
        return _pct(mids, 0.25), _pct(mids, 0.75), f"các khoảng chữ nổ không giao nhau, lấy nửa giữa của {len(mids)} điểm giữa"

    def converged(self) -> tuple[bool, str]:
        if self.old_format:
            return False, "bản cũ, chưa có cơ chế dò độ trễ máy"
        hits = [t for t in self.taps if t["ket_qua"] == "trung"]
        if not hits:
            return False, "chưa có cú trúng nào"
        if not self.delay_changes:
            if self.delay_start is not None and abs(self.delay_start - 0.30) < 0.005 and not self.flashes:
                return False, "vẫn ở số mặc định 0,30s và chưa thấy chữ nổ, chưa học được gì"
            return True, "không đổi suốt phiên"
        last_change = self.delay_changes[-1][0]
        after = [t for t in hits if t["t"] is not None and t["t"] > last_change]
        if len(after) >= 3:
            return True, f"ổn định qua {len(after)} cú trúng cuối"
        return False, f"còn đổi ở gần cuối phiên (mới {len(after)} cú trúng sau lần đổi cuối)"

    # ----- in -----

    def report(self) -> list[str]:
        out: list[str] = []
        out.append(f"=== Phiên {self.stem}" + (" (nhật ký bản cũ)" if self.old_format else ""))

        # Lượt
        if self.casts:
            ok = sum(1 for c in self.casts if c["ket_qua"] == "thanh_cong")
            bad = sum(1 for c in self.casts if c["ket_qua"] == "that_bai")
            other = len(self.casts) - ok - bad
            secs = _median([c["giay"] for c in self.casts])
            longest = max((c["giay"] or 0) for c in self.casts)
            out.append(
                f"Lượt: {len(self.casts)} (thành công {ok}, thất bại {bad}, không rõ {other}); "
                f"mỗi lượt trung vị {_fmt(secs, '.1f', 's')}, lâu nhất {longest:.1f}s; "
                f"vàng {sum(c['vang'] for c in self.casts):.0f}."
            )
            kinds = defaultdict(int)
            for c in self.casts:
                kinds[(c["pham"] or "?", c["loai"] or "?")] += 1
            out.append("  Loài: " + ", ".join(f"{loai} ({pham}) ×{n}" for (pham, loai), n in sorted(kinds.items())))
        else:
            out.append(f"Lượt: không có file {self.stem}.csv; loài theo vết: {', '.join(self.species) or '—'}")

        # Máy
        out.append("Máy:")
        out.append(
            f"  Chụp một ảnh: trung vị {_fmt(_median(self.shots), '.2f', 's')}, "
            f"chậm nhất 10% từ {_fmt(_pct(self.shots, 0.9), '.2f', 's')} ({len(self.shots)} ảnh)."
        )
        if self.old_format:
            out.append(
                f"  Độ trễ cú bấm: bản cũ chưa dò (ghi {_fmt(self.delay_start)}s). Cập nhật tool rồi gửi lại nhật ký."
            )
        else:
            path = " → ".join(f"{c[2]:.2f}" for c in self.delay_changes)
            out.append(
                f"  Độ trễ cú bấm tool dùng: đầu phiên {_fmt(self.delay_start)}s, cuối phiên {_fmt(self.delay_end)}s"
                + (f" (đổi {len(self.delay_changes)} lần: {self.delay_start:.2f} → {path})" if self.delay_changes else " (không đổi)")
                + "."
            )
            lo, hi, how = self.delay_estimate()
            if lo is not None:
                out.append(f"  Độ trễ thật theo chữ nổ: {lo:.2f}–{hi:.2f}s ({how}).")
                if self.delay_end is not None and not (lo - 0.03 <= self.delay_end <= hi + 0.03):
                    out.append(f"  !! Số đang dùng {self.delay_end:.2f}s nằm ngoài khoảng chữ nổ. Phiên sau tool sẽ kéo tiếp.")
            else:
                out.append(f"  Độ trễ thật theo chữ nổ: {how}.")
            hits = sum(1 for t in self.taps if t["ket_qua"] == "trung")
            by_how = defaultdict(list)
            for how_, dt in self.confirm:
                by_how[how_].append(dt)
            out.append(
                f"  Thấy chữ nổ {len(self.flashes)} lần trên {hits} cú trúng"
                + (f"; vệt trắng {_fmt(_median([f['white'] for f in self.flashes]))}" if self.flashes else "")
                + f"; ảnh chưa nổ chữ mà vẫn trúng {len(self.late_frames)} lần"
                + f"; dò hai phía {len(self.probes)} lần (trúng {len(self.probe_hits)})."
            )
            for how_, dts in sorted(by_how.items()):
                out.append(f"  Xác nhận trúng qua {how_}: {len(dts)} cú, sau lệnh trung vị {_fmt(_median(dts), '.2f', 's')}.")
            done, why = self.converged()
            out.append(f"  Đã dò xong độ trễ máy: {'rồi' if done else 'chưa'} ({why}).")
            if self.bias_start is not None:
                end = self.bias_changes[-1] if self.bias_changes else None
                out.append(
                    f"  Lệch nhắm học từ mồi thật: đầu phiên {self.bias_start:+.2f}s"
                    + (f", cuối phiên {end[0]:+.2f}s theo {end[1]} cú dò trúng (đổi {len(self.bias_changes)} lần)" if end else ", không đổi")
                    + "."
                )

        # Cú bấm theo độ rộng
        if self.taps:
            total = len(self.taps)
            hits = sum(1 for t in self.taps if t["ket_qua"] == "trung")
            extra = sum(1 for t in self.taps if t["lan_tren_thanh"] > 1)
            out.append(f"Cú bấm: {total}, trúng {hits}, trượt {sum(1 for t in self.taps if t['ket_qua'] == 'truot')}, cú thêm trên cùng thanh {extra}.")
            out.append("  rộng   cú  trúng  lệch tâm (px)      |lệch|/nửa vùng   chưa đo   chờ từ khi thanh hiện")
            waits = defaultdict(list)
            for width, wait in self.bar_waits:
                waits[width].append(wait)
            for width in WIDTHS:
                rows = [t for t in self.taps if t["bin"] == width]
                if not rows:
                    continue
                errs = [t["err"] for t in rows if t["err"] is not None]
                half = width / 2
                rel = [abs(e) / half for e in errs]
                hit = sum(1 for t in rows if t["ket_qua"] == "trung")
                late = sum(1 for t, e in ((t, t["err"]) for t in rows) if e is not None and t["van_toc"] and e * t["van_toc"] > 0)
                out.append(
                    f"  {width:>4}px {len(rows):>3}  {hit:>3}    "
                    f"{_fmt(_median(errs), '+.0f'):>5} (xa nhất {_fmt(max(errs, key=abs) if errs else None, '+.0f'):>5})   "
                    f"{_fmt(_median(rel), '.2f'):>5} (p90 {_fmt(_pct(rel, 0.9), '.2f')})    "
                    f"{len(rows) - len(errs):>3}      "
                    f"{_fmt(_median(waits.get(width)), '.2f', 's')} (lâu nhất {_fmt(max(waits[width]) if waits.get(width) else None, '.2f', 's')})"
                    + (f"   {late}/{len(errs)} cú lệch theo chiều chạy (tới muộn)" if errs else "")
                )
            if self.unmeasured_reasons:
                reasons = defaultdict(int)
                for r in self.unmeasured_reasons:
                    reasons[re.sub(r"[\d.]+s", "…s", r)] += 1
                out.append("  Lý do chưa đo được lệch: " + "; ".join(f"{k} ×{n}" for k, n in reasons.items()))
        else:
            out.append(f"Cú bấm: không có file {self.stem}-bam.csv (vết ghi {self.tap_count_trace} lệnh bấm).")

        # Cảnh báo
        warns = self.warnings()
        out.append("Cần để ý:" if warns else "Cần để ý: không có gì bất thường.")
        out.extend(f"  - {w}" for w in warns)
        return out

    def warnings(self) -> list[str]:
        warns: list[str] = []
        shot = _median(self.shots)
        if shot is not None and shot > 0.55:
            warns.append(
                f"Máy chụp ảnh chậm ({shot:.2f}s/ảnh, máy chuẩn 0,36s). Mỗi thanh sẽ mất lâu hơn; cá đỏ 8 thanh sẽ sát giờ."
            )
        if self.old_format:
            warns.append("Nhật ký của bản cũ: chưa có dò độ trễ máy và chữ nổ. Cập nhật tool rồi gửi lại.")
        else:
            hits = [t for t in self.taps if t["ket_qua"] == "trung"]
            if hits and not self.flashes:
                warns.append(
                    f"Có {len(hits)} cú trúng mà không lần nào thấy chữ nổ: ảnh canh lúc chữ nổ đang rơi lệch hoặc ngưỡng "
                    "vệt trắng không hợp máy này. Gửi kèm các ảnh cau-ca-busy-*.png trong logs để chỉnh ngưỡng."
                )
            done, why = self.converged()
            if not done and hits:
                warns.append(f"Độ trễ máy chưa chốt xong ({why}). Cho chạy thêm một phiên nữa rồi xem lại.")
            if self.delay_end is not None and self.delay_end >= 0.69:
                warns.append("Độ trễ máy đã chạm trần 0,70s. Máy quá chậm so với mức tool cho phép, cần xem lại giả lập.")
            if self.delay_end is not None and self.delay_end <= 0.16:
                warns.append("Độ trễ máy đã chạm sàn 0,15s. Có gì đó đo sai, gửi nhật ký để xem.")
        if self.taps:
            # Cú chốt bằng chữ nổ thì ảnh sau lệnh là ảnh chữ nổ, không đọc được mồi: không đo được là bình thường.
            unmeasured = sum(1 for t in self.taps if t["err"] is None) - len(self.flashes)
            if unmeasured > 0.3 * len(self.taps):
                warns.append(
                    f"{unmeasured}/{len(self.taps)} cú không đo được mồi lúc cú bấm tới (ngoài các cú chốt bằng chữ nổ). "
                    "Ảnh quá thưa quanh lúc bấm."
                )
            for width in (73, 36):
                rows = [t for t in self.taps if t["bin"] == width]
                hit = sum(1 for t in rows if t["ket_qua"] == "trung")
                if len(rows) >= 3 and hit < 0.7 * len(rows):
                    warns.append(f"Vùng {width}px chỉ trúng {hit}/{len(rows)}. Xem cột lệch tâm: cùng dấu với chiều chạy là tới muộn, ngược dấu là tới sớm.")
            extra = sum(1 for t in self.taps if t["lan_tren_thanh"] > 1)
            if extra > 0.2 * len(self.taps):
                warns.append(f"{extra} cú là bấm thêm trên thanh đã bấm. Nếu phần lớn vẫn ghi TRÚNG thì tool gọi trượt nhầm, cần xem vết.")
            long_waits = [(w, s) for w, s in self.bar_waits if s > 3.0]
            if long_waits:
                warns.append(f"{len(long_waits)} thanh chờ hơn 3s mới bấm (lâu nhất {max(s for _, s in long_waits):.1f}s).")
        for c in self.casts:
            if c["ket_qua"] == "that_bai":
                warns.append(f"Lượt {c['luot']} hết giờ ({c['so_lan_bam']} cú bấm, {_fmt(c['giay'], '.1f', 's')}).")
        # Giờ của game đếm từ lúc thanh trượt hiện. Lấy cú bấm cuối của lượt so với cú đầu để biết còn dư bao nhiêu.
        by_cast = defaultdict(list)
        for t in self.taps:
            if t["t"] is not None:
                by_cast[t["luot"]].append(t["t"])
        for luot, times in sorted(by_cast.items()):
            span = max(times) - min(times)
            if span > GAME_TIMER - 6:
                warns.append(f"Lượt {luot}: từ cú bấm đầu tới cú cuối mất {span:.1f}s, sát mức {GAME_TIMER:.0f}s của game.")
        return warns


def find_sessions(arg: str | None) -> list[Path]:
    if arg is None:
        files = sorted(LOGS.glob("cau-ca-*-vet.txt"))
        return files[-1:]
    path = Path(arg)
    if path.is_dir():
        return sorted(path.glob("*-vet.txt"))
    if path.name.endswith("-vet.txt"):
        return [path]
    # Cho phép đưa file .csv hoặc -bam.csv cùng phiên.
    stem = re.sub(r"(-bam)?\.csv$", "", path.name)
    vet = path.with_name(stem + "-vet.txt")
    return [vet] if vet.exists() else []


def main() -> int:
    sessions = find_sessions(sys.argv[1] if len(sys.argv) > 1 else None)
    if not sessions:
        print("Không tìm thấy file -vet.txt nào.")
        return 1
    all_taps: list[dict] = []
    for vet in sessions:
        session = Session(vet)
        print("\n".join(session.report()))
        print()
        all_taps.extend(session.taps)
    if len(sessions) > 1 and all_taps:
        hits = sum(1 for t in all_taps if t["ket_qua"] == "trung")
        print(f"=== Gộp {len(sessions)} phiên: {len(all_taps)} cú bấm, trúng {hits} ({100 * hits / len(all_taps):.0f}%)")
        for width in WIDTHS:
            rows = [t for t in all_taps if t["bin"] == width]
            if rows:
                hit = sum(1 for t in rows if t["ket_qua"] == "trung")
                errs = [t["err"] for t in rows if t["err"] is not None]
                print(f"  {width:>4}px: {hit}/{len(rows)} trúng, lệch tâm trung vị {_fmt(_median(errs), '+.0f', 'px')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
