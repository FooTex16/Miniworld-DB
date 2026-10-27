#!/usr/bin/env python3
"""
Fase 0 - PROBE (read-only, tanpa injeksi, tanpa tulis memori).

Tujuan:
  1. menemukan proses game,
  2. membaca alamat 0x2C00EA08 (uint32 LE) dan memastikan isinya masuk akal,
  3. MENJAWAB DUA PERTANYAAN SEBELUM OTOMASI DIBANGUN:
       a. apakah ID berubah saat HOVER saja, atau harus KLIK (pick)?
       b. apakah harus KLIK TITIK AMAN dulu (clear) sebelum pick cell berikutnya,
          atau klik langsung ke cell berikutnya otomatis melepas pick lama?

Mode:
  --list                 daftar kandidat proses game
  --pid N                MODE MANUAL: sampling 10 Hz, cetak tiap nilai berubah
                         (Anda yang hover/klik sendiri di game, lalu Ctrl+C)
  --pid N --auto ...     MODE OTOMATIS: probe hover -> klik -> clear -> klik cell lain

Contoh:
  python probe.py --list
  python probe.py --pid 12345
  python probe.py --pid 12345 --auto --cell 745,288 --cell2 875,288 --safe 1000,160
  python probe.py --pid 12345 --auto --cell 745,288 --cell2 875,288 --safe 1000,160 --shots
"""
from __future__ import annotations

import argparse
import ctypes
import ctypes.wintypes as wt
import json
import os
import struct
import sys
import time

# ---------------------------------------------------------------- platform ---
k32 = ctypes.WinDLL("kernel32", use_last_error=True)
PROCESS_VM_READ = 0x0010
PROCESS_QUERY_INFORMATION = 0x0400
MEM_RELEASE = 0x8000

# prototipe wajib di-set agar tidak terpotong 32-bit di proses 64-bit
k32.OpenProcess.argtypes = [wt.DWORD, wt.BOOL, wt.DWORD]
k32.OpenProcess.restype = wt.HANDLE
k32.ReadProcessMemory.argtypes = [wt.HANDLE, ctypes.c_void_p, ctypes.c_void_p,
                                  ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]
k32.ReadProcessMemory.restype = wt.BOOL
k32.CloseHandle.argtypes = [wt.HANDLE]
k32.CloseHandle.restype = wt.BOOL
k32.CreateToolhelp32Snapshot.argtypes = [wt.DWORD, wt.DWORD]
k32.CreateToolhelp32Snapshot.restype = wt.HANDLE

INPUT_MOUSE = 0
MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_ABSOLUTE = 0x8000
MOUSEEVENTF_VIRTUALDESK = 0x4000

DEFAULT_ADDR = 0x2C00EA08
ID_MIN, ID_MAX = 0, 400000


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wt.LONG),
        ("dy", wt.LONG),
        ("mouseData", wt.DWORD),
        ("dwFlags", wt.DWORD),
        ("time", wt.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


class INPUT(ctypes.Structure):
    class _U(ctypes.Union):
        _fields_ = [("mi", MOUSEINPUT)]
    _anonymous_ = ("u",)
    _fields_ = [("type", wt.DWORD), ("u", _U)]


def _screen_size() -> tuple[int, int]:
    user32 = ctypes.windll.user32
    return user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)


def move_to(x: int, y: int) -> None:
    """Pindahkan kursor ke (x,y) dalam koordinat pixel virtual-desktop."""
    w, h = _screen_size()
    nx = int(round(x * 65535 / max(w - 1, 1)))
    ny = int(round(y * 65535 / max(h - 1, 1)))
    inp = INPUT(type=INPUT_MOUSE)
    inp.mi = MOUSEINPUT(nx, ny, 0, MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_VIRTUALDESK, 0, None)
    ctypes.windll.user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(inp))


def click(x: int, y: int, hold_s: float = 0.045) -> None:
    move_to(x, y)
    time.sleep(0.06)
    for flag in (MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP):
        inp = INPUT(type=INPUT_MOUSE)
        inp.mi = MOUSEINPUT(0, 0, 0, flag, 0, None)
        ctypes.windll.user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(inp))
        time.sleep(hold_s)


MOUSEEVENTF_WHEEL = 0x0800


def wheel(x: int, y: int, delta: int) -> None:
    """Scroll mouse-wheel di (x,y). delta>0 = ke atas, <0 = ke bawah (120 = 1 notch)."""
    move_to(x, y)
    time.sleep(0.05)
    inp = INPUT(type=INPUT_MOUSE)
    inp.mi = MOUSEINPUT(0, 0, delta & 0xFFFFFFFF, MOUSEEVENTF_WHEEL, 0, None)
    ctypes.windll.user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(inp))


def get_cursor() -> tuple[int, int]:
    pt = ctypes.wintypes.POINT()
    ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
    return pt.x, pt.y


# ------------------------------------------------------------------ memory ---
class MemReader:
    """ReadProcessMemory read-only. Tidak pernah menulis."""

    def __init__(self, pid: int):
        self.pid = pid
        self.handle = k32.OpenProcess(PROCESS_VM_READ | PROCESS_QUERY_INFORMATION, False, pid)
        if not self.handle:
            raise OSError(ctypes.get_last_error(),
                          f"OpenProcess gagal untuk pid={pid} (coba jalankan terminal sebagai Admin)")

    def read(self, addr: int, size: int = 4) -> bytes:
        buf = (ctypes.c_ubyte * size)()
        n = ctypes.c_size_t(0)
        ok = k32.ReadProcessMemory(self.handle, ctypes.c_void_p(addr), buf, size, ctypes.byref(n))
        if not ok:
            raise OSError(ctypes.get_last_error(), f"ReadProcessMemory gagal @0x{addr:X}")
        return bytes(buf[: n.value])

    def u32(self, addr: int) -> int:
        b = self.read(addr, 4)
        return struct.unpack("<I", b)[0]

    def close(self) -> None:
        if self.handle:
            k32.CloseHandle(self.handle)
            self.handle = None


def process_name(pid: int) -> str:
    import psutil
    try:
        return psutil.Process(pid).name()
    except Exception:
        return "?"


class MODULEENTRY32(ctypes.Structure):
    _fields_ = [
        ("dwSize", wt.DWORD),
        ("th32ModuleID", wt.DWORD),
        ("th32ProcessID", wt.DWORD),
        ("GlblcntUsage", wt.DWORD),
        ("ProccntUsage", wt.DWORD),
        ("modBaseAddr", ctypes.POINTER(ctypes.c_byte)),
        ("modBaseSize", wt.DWORD),
        ("hModule", wt.HMODULE),
        ("szModule", ctypes.c_char * 256),
        ("szExePath", ctypes.c_char * 260),
    ]


TH32CS_SNAPMODULE = 0x00000008
TH32CS_SNAPMODULE32 = 0x00000010
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value

k32.Module32First.argtypes = [wt.HANDLE, ctypes.POINTER(MODULEENTRY32)]
k32.Module32First.restype = wt.BOOL
k32.Module32Next.argtypes = [wt.HANDLE, ctypes.POINTER(MODULEENTRY32)]
k32.Module32Next.restype = wt.BOOL


def modules_of(pid: int) -> list[tuple[int, int, str]]:
    """[(base, size, path)] modul proses. Pada 64-bit hanya modul 64-bit yang valid
    untuk dibaca; kegagalan ERROR_PARTIAL_COPY berarti beda arsitektur."""
    snap = k32.CreateToolhelp32Snapshot(TH32CS_SNAPMODULE | TH32CS_SNAPMODULE32, pid)
    if snap in (INVALID_HANDLE_VALUE, None):
        raise OSError(ctypes.get_last_error(), "CreateToolhelp32Snapshot gagal")
    out: list[tuple[int, int, str]] = []
    try:
        me = MODULEENTRY32()
        me.dwSize = ctypes.sizeof(MODULEENTRY32)
        ok = k32.Module32First(snap, ctypes.byref(me))
        if not ok:
            raise OSError(ctypes.get_last_error(), "Module32First gagal")
        while ok:
            base = ctypes.cast(me.modBaseAddr, ctypes.c_void_p).value or 0
            out.append((base, me.modBaseSize, me.szExePath.decode("utf-8", "replace")))
            ok = k32.Module32Next(snap, ctypes.byref(me))
    finally:
        k32.CloseHandle(snap)
    return out


def module_of(pid: int, addr: int) -> str:
    """Modul yang membungkus alamat (untuk tahu apakah alamat stabil / ASLR)."""
    try:
        mods = modules_of(pid)
    except OSError as e:
        return f"<gagal enumerasi modul: {e}>"
    for base, size, path in mods:
        if base <= addr < base + size:
            return f"{os.path.basename(path)} (base=0x{base:X}, size=0x{size:X}) -> {path}"
    if not mods:
        return "<tidak ada modul terbaca>"
    return (f"<di luar semua modul; {len(mods)} modul, "
            f"base terendah=0x{min(m[0] for m in mods):X}>)")


def list_candidates() -> None:
    import psutil
    kw = ("mini", "world", "unity", "unreal", "weplay", "game")
    rows = []
    for p in psutil.process_iter(["pid", "name", "exe"]):
        try:
            name = (p.info["name"] or "").lower()
            exe = (p.info["exe"] or "")
        except Exception:
            continue
        if any(k in name for k in kw) or any(k in exe.lower() for k in kw):
            rows.append((p.info["pid"], p.info["name"], exe))
    print("== Kandidat proses (filter kata kunci: %s) ==" % ", ".join(kw))
    if not rows:
        print("  (tidak ada yang cocok - pastikan game sudah dibuka)")
    for pid, name, exe in sorted(rows, key=lambda r: r[1] or ""):
        print(f"  pid={pid:<8} {name:<28} {exe}")
    print("\n== Jendela yang terlihat (judul -> pid) ==")
    user32 = ctypes.windll.user32
    results: list[tuple[int, str, int]] = []

    @ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
    def _cb(hwnd, _):
        if not user32.IsWindowVisible(hwnd):
            return True
        n = user32.GetWindowTextLengthW(hwnd)
        if n == 0:
            return True
        buf = ctypes.create_unicode_buffer(n + 1)
        user32.GetWindowTextW(hwnd, buf, n + 1)
        pid = wt.DWORD(0)
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        results.append((pid.value, buf.value, hwnd))
        return True

    user32.EnumWindows(_cb, 0)
    if not results:
        print("  (tidak ada)")
    for pid, title, _hwnd in sorted(results, key=lambda r: r[1].lower()):
        print(f"  pid={pid:<8} {title[:70]}")


# ------------------------------------------------------------------ shots ---
def shot(path: str, crop: tuple[int, int, int, int] | None = None) -> bool:
    try:
        from PIL import ImageGrab
        img = ImageGrab.grab()
        if crop:
            x, y, w, h = crop
            img = img.crop((x, y, x + w, y + h))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        img.save(path)
        return True
    except Exception as e:
        print(f"  [!] screenshot gagal: {e}")
        return False


# ----------------------------------------------------------------- probing --
def sample(reader: MemReader, addr: int, times: int, interval: float, label: str) -> dict:
    """Baca `addr` sebanyak `times`. Kembalikan nilai awal/akhir + semua nilai unik."""
    vals = []
    errs = []
    for i in range(times):
        try:
            vals.append(reader.u32(addr))
        except OSError as e:
            errs.append(str(e))
        time.sleep(interval)
    uniq = sorted(set(vals))
    out = {
        "label": label,
        "n": times,
        "first": vals[0] if vals else None,
        "last": vals[-1] if vals else None,
        "unique": uniq,
        "changed": len(uniq) > 1,
        "errors": errs[:3],
    }
    print(f"  {label:<26} n={times:<3} first={out['first']} last={out['last']} "
          f"unik={uniq if len(uniq) <= 6 else str(uniq[:6]) + '...'}")
    return out


def auto_probe(args) -> dict:
    cx, cy = args.cell
    cx2, cy2 = args.cell2 or (args.cell[0], args.cell[1])  # cell kedua opsional
    sx, sy = args.safe
    reader = MemReader(args.pid)
    addr = args.addr
    out = {
        "pid": args.pid, "process": process_name(args.pid), "addr": hex(addr),
        "module": module_of(args.pid, addr), "steps": [], "ts": time.time(),
    }
    print(f"\n[probe] pid={args.pid} ({out['process']}) addr={hex(addr)} -> {out['module']}")

    try:
        v = reader.u32(addr)
        print(f"  baseline           value={v} (0x{v:X})")
        out["baseline"] = v
        if not (ID_MIN <= v <= ID_MAX):
            print(f"  [!] baseline di luar rentang ID {ID_MIN}..{ID_MAX} - kemungkinan alamat salah")
    except OSError as e:
        print(f"  [!] gagal baca baseline: {e}")
        out["baseline_error"] = str(e)
        return out

    step = 0
    if args.shots:
        step += 1
        shot(f"output/probe/{step:02d}_baseline.png", args.rect)

    # --- 1. HOVER ONLY -------------------------------------------------------
    print("\n[1] HOVER saja (tanpa klik) ke cell A")
    move_to(cx, cy)
    time.sleep(args.tooltip_ms / 1000)
    out["steps"].append(sample(reader, addr, args.times, 0.1, "hover_only"))
    if args.shots:
        step += 1
        shot(f"output/probe/{step:02d}_hover.png", args.rect)
    hover_changed = out["steps"][-1]["changed"]
    print(f"     -> {'ID BERUBAH saat hover (cukup hover tanpa klik!)' if hover_changed else 'ID tidak berubah saat hover'}")

    # --- 2. KLIK (pick) ------------------------------------------------------
    print("\n[2] KLIK cell A (pick)")
    click(cx, cy)
    time.sleep(args.settle_ms / 1000)
    out["steps"].append(sample(reader, addr, args.times, 0.1, "click_pick_A"))
    if args.shots:
        step += 1
        shot(f"output/probe/{step:02d}_picked.png", args.rect)
    after_pick = out["steps"][-1]["last"]
    print(f"     -> nilai setelah pick = {after_pick}")

    # --- 3. CLEAR (klik titik aman) -----------------------------------------
    print("\n[3] KLIK titik aman (clear pick)")
    click(sx, sy)
    time.sleep(args.settle_ms / 1000)
    out["steps"].append(sample(reader, addr, args.times, 0.1, "click_safe_clear"))
    after_clear = out["steps"][-1]["last"]
    if args.shots:
        step += 1
        shot(f"output/probe/{step:02d}_cleared.png", args.rect)
    clear_works = after_clear != after_pick
    print(f"     -> nilai setelah clear = {after_clear} "
          f"({'clear mengubah nilai' if clear_works else 'TIDAK berubah - clear tidak berefek/alamat bukan pick-state'})")

    # --- 4. KLIK LANGSUNG ke cell B (tanpa clear) ---------------------------
    print(f"\n[4] KLIK LANGSUNG cell B ({cx2},{cy2}) TANPA clear dulu")
    move_to(cx2, cy2)
    time.sleep(0.2)
    click(cx2, cy2)
    time.sleep(args.settle_ms / 1000)
    out["steps"].append(sample(reader, addr, args.times, 0.1, "direct_click_B"))
    after_b = out["steps"][-1]["last"]
    if args.shots:
        step += 1
        shot(f"output/probe/{step:02d}_direct_B.png", args.rect)
    direct_ok = after_b != after_clear
    print(f"     -> nilai setelah klik langsung = {after_b}")

    # --- 5. clear lagi, lalu hover cell B -----------------------------------
    print("\n[5] CLEAR lagi lalu HOVER cell B (uji hover-only sekali lagi)")
    click(sx, sy)
    time.sleep(args.settle_ms / 1000)
    pre = reader.u32(addr)
    move_to(cx2, cy2)
    time.sleep(args.tooltip_ms / 1000)
    out["steps"].append(sample(reader, addr, args.times, 0.1, "hover_B_after_clear"))
    if args.shots:
        step += 1
        shot(f"output/probe/{step:02d}_hover_B.png", args.rect)
    reader.close()

    # --- verdict -------------------------------------------------------------
    v = {
        "hover_suffices": bool(hover_changed),
        "pick_changes_id": after_pick != out["baseline"],
        "clear_required": bool(clear_works and not direct_ok),
        "direct_click_works": bool(direct_ok),
        "notes": [],
    }
    if not v["pick_changes_id"]:
        v["notes"].append("klik TIDAK mengubah nilai -> alamat 0x2C00EA08 mungkin bukan pick-state, perlu pointer scan")
    if v["hover_suffices"]:
        v["notes"].append("cukup HOVER -> optimasi: hilangkan klik/clear, kecepatan naik ~2x")
    if v["clear_required"]:
        v["notes"].append("WAJIB clear (klik titik aman) sebelum pick cell berikutnya")
    elif v["direct_click_works"]:
        v["notes"].append("klik langsung ke cell berikutnya sudah cukup -> hilangkan langkah clear, hemat ~400 ms/cell")
    out["verdict"] = v

    print("\n===== VERDICT =====")
    for k, val in v.items():
        if k != "notes":
            print(f"  {k:<20}: {val}")
    for n in v["notes"]:
        print(f"  - {n}")

    os.makedirs("output", exist_ok=True)
    path = "output/probe/report.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    print(f"\nLaporan: {path}")
    return out


def manual_probe(args) -> None:
    reader = MemReader(args.pid)
    addr = args.addr
    print(f"[manual] pid={args.pid} ({process_name(args.pid)}) addr={hex(addr)} "
          f"-> {module_of(args.pid, addr)}")
    try:
        base = reader.u32(addr)
    except OSError as e:
        print(f"[!] gagal baca: {e}")
        return
    print(f"  baseline = {base} (0x{base:X})\n")
    print("  Sekarang lakukan di game: hover block -> klik (pick) -> klik titik aman (clear).")
    print("  Tiap kali nilai berubah akan tercetak. Ctrl+C untuk berhenti.\n")

    last = base
    t0 = time.time()
    counts: dict[int, int] = {}
    try:
        while True:
            if args.duration and (time.time() - t0) >= args.duration:
                print(f"\n[selesai {args.duration:.0f} dtk]")
                break
            try:
                v = reader.u32(addr)
            except OSError as e:
                print(f"[!] baca gagal (proses keluar?): {e}")
                break
            counts[v] = counts.get(v, 0) + 1
            if v != last:
                print(f"  [{time.time() - t0:8.3f}s]  {last} -> {v}   (0x{v:X})")
                last = v
            time.sleep(args.interval)
    except KeyboardInterrupt:
        pass
    finally:
        reader.close()

    print("\n===== RINGKASAN =====")
    print(f"  nilai unik terlihat: {sorted(counts)}")
    for val, n in sorted(counts.items(), key=lambda kv: -kv[1])[:10]:
        print(f"    {val:>10} (0x{val:X})  x{n}")
    if len(counts) == 1:
        print("  [!] nilai tidak pernah berubah -> alamat kemungkinan salah / butuh click dulu")


# --------------------------------------------------------------------- main --
def parse_pair(s: str) -> tuple[int, int]:
    x, y = s.split(",")
    return int(x), int(y)


def main() -> int:
    ap = argparse.ArgumentParser(description="Fase 0 probe (read-only) untuk otomasi scanner block")
    ap.add_argument("--list", action="store_true", help="daftar kandidat proses game")
    ap.add_argument("--pid", type=int, help="pid proses game")
    ap.add_argument("--addr", type=lambda s: int(s, 0), default=DEFAULT_ADDR,
                    help="alamat memori (default 0x2C00EA08)")
    ap.add_argument("--interval", type=float, default=0.1, help="interval sampling mode manual (dtk)")
    ap.add_argument("--duration", type=float, default=0, help="berhenti otomatis setelah N detik (0 = terus)")
    ap.add_argument("--auto", action="store_true", help="mode probe terotomasi (butuh --cell & --safe)")
    ap.add_argument("--cell", type=parse_pair, help="pusat cell A, contoh: 745,288")
    ap.add_argument("--cell2", type=parse_pair, help="pusat cell B (default = --cell)")
    ap.add_argument("--safe", type=parse_pair, help="titik aman untuk klik clear (di dalam panel)")
    ap.add_argument("--rect", type=lambda s: tuple(map(int, s.split(","))),
                    help="crop screenshot x,y,w,h (opsional)")
    ap.add_argument("--times", type=int, default=10, help="jumlah pembacaan per step (default 10)")
    ap.add_argument("--tooltip-ms", type=int, default=450, dest="tooltip_ms")
    ap.add_argument("--settle-ms", type=int, default=300, dest="settle_ms")
    ap.add_argument("--shots", action="store_true", help="simpan screenshot tiap step")
    args = ap.parse_args()

    if args.list:
        list_candidates()
        return 0
    if not args.pid:
        ap.error("--pid wajib (lihat daftar dengan --list)")
    if args.auto and (not args.cell or not args.safe):
        ap.error("--auto butuh --cell x,y dan --safe x,y")

    print("Fase 0 PROBE - read-only, tidak ada tulis/inject memori.")
    if args.auto:
        auto_probe(args)
    else:
        manual_probe(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
