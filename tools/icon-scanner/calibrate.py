#!/usr/bin/env python3
"""
Fase 1 - KALIBRASI grid 10 x 4 + titik aman (clear).

Mode:
  1) --gui            tandai titik dengan klik pada screenshot layar (butuh tkinter)
  2) --grid ... --safe ...   tulis config langsung dari koordinat yang sudah diketahui
  3) --preview        gambar overlay 10x4 di atas screenshot TERBARU -> output/calib/preview.png
                      (dipakai untuk verifikasi visual sebelum mulai scan)

Contoh:
  python calibrate.py --capture
  python calibrate.py --gui
  python calibrate.py --grid 355,220,1310,550 --safe 1000,160
  python calibrate.py --preview
"""
from __future__ import annotations

import argparse
import ctypes
import ctypes.wintypes as wt
import json
import os
import sys
import time

# DPI-aware SEBELUM capture, supaya pixel = pixel fisik
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

from PIL import Image, ImageDraw, ImageFont  # noqa: E402

CALIB_DIR = "output/calib"
CONFIG = "config.json"
COLS, ROWS = 10, 4

# zona larangan: jangan sampai jadi titik aman / di dalam grid
FORBIDDEN = {
    "close_X": (1740, 50, 90, 90),      # perkiraan tombol X tutup (x,y,w,h)
    "add_btn": (1080, 120, 260, 70),    # perkiraan tombol + Add / Minature
}


def focus_window(substr: str = "miniworld") -> bool:
    """Angkat jendela game ke depan (restore bila minimized)."""
    user32 = ctypes.windll.user32
    found: list[int] = []

    @ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
    def _cb(hwnd, _):
        if not user32.IsWindowVisible(hwnd):
            return True
        n = user32.GetWindowTextLengthW(hwnd)
        if n == 0:
            return True
        buf = ctypes.create_unicode_buffer(n + 1)
        user32.GetWindowTextW(hwnd, buf, n + 1)
        if substr.lower() in buf.value.lower():
            found.append(hwnd)
        return True

    user32.EnumWindows(_cb, 0)
    if not found:
        print(f"[!] jendela berisi '{substr}' tidak ditemukan")
        return False
    hwnd = found[0]
    SW_RESTORE = 9
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, SW_RESTORE)
    # trik agar SetForegroundWindow diizinkan
    ALT, KEYUP = 0x0001, 0x0002
    user32.keybd_event(ALT, 0, ALT, 0)
    user32.SetForegroundWindow(hwnd)
    user32.keybd_event(ALT, 0, KEYUP, 0)
    user32.SetForegroundWindow(hwnd)
    user32.BringWindowToTop(hwnd)
    time.sleep(0.6)
    title = ctypes.create_unicode_buffer(256)
    user32.GetWindowTextW(hwnd, title, 256)
    print(f"[focus] {title.value}")
    return True


def grab() -> Image.Image:
    from PIL import ImageGrab
    return ImageGrab.grab()


def save(img: Image.Image, name: str) -> str:
    os.makedirs(CALIB_DIR, exist_ok=True)
    p = os.path.join(CALIB_DIR, name)
    img.save(p)
    return p


def load_font(size: int = 14):
    for name in ("consola.ttf", "arialbd.ttf", "arial.ttf", "segoeui.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except Exception:
            continue
    return ImageFont.load_default()


def cell_rects(grid: tuple[int, int, int, int]):
    """-> (x, y, w, h) grid; hasilkan 40 rect cell + pusatnya."""
    gx, gy, gw, gh = grid
    cw, ch = gw / COLS, gh / ROWS
    out = []
    for r in range(ROWS):
        for c in range(COLS):
            x = gx + c * cw
            y = gy + r * ch
            out.append((r, c, x, y, cw, ch, (x + cw / 2, y + ch / 2)))
    return out


def draw_preview(grid, safe, cells=None, path="output/calib/preview.png",
                 note: str = "") -> str:
    img = grab()
    d = ImageDraw.Draw(img, "RGBA")
    f = load_font(15)
    fs = load_font(12)
    cells = cells or cell_rects(grid)

    # zona larangan
    for name, (x, y, w, h) in FORBIDDEN.items():
        d.rectangle([x, y, x + w, y + h], outline=(255, 60, 60, 255), width=3)
        d.text((x + 4, y - 16), f"JANGAN: {name}", fill=(255, 60, 60, 255), font=fs)

    # grid
    gx, gy, gw, gh = grid
    d.rectangle([gx, gy, gx + gw, gy + gh], outline=(0, 255, 120, 255), width=3)
    for r, c, x, y, cw, ch, (mx, my) in cells:
        d.rectangle([x, y, x + cw, y + ch], outline=(0, 255, 120, 160), width=1)
        d.ellipse([mx - 3, my - 3, mx + 3, my + 3], fill=(0, 255, 120, 255))
        d.text((x + 4, y + 3), f"{r},{c}", fill=(255, 230, 60, 255), font=fs)

    if safe:
        sx, sy = safe
        d.line([sx - 14, sy, sx + 14, sy], fill=(90, 170, 255, 255), width=3)
        d.line([sx, sy - 14, sx, sy + 14], fill=(90, 170, 255, 255), width=3)
        d.ellipse([sx - 12, sy - 12, sx + 12, sy + 12], outline=(90, 170, 255, 255), width=2)
        d.text((sx + 16, sy - 8), "TITIK AMAN (clear)", fill=(90, 170, 255, 255), font=f)

    cw, ch = gw / COLS, gh / ROWS
    hdr = (f"grid {gw}x{gh} @ {gx},{gy} | cell {cw:.1f}x{ch:.1f} | "
           f"{COLS}x{ROWS} = {COLS*ROWS} sel" + (f" | {note}" if note else ""))
    d.rectangle([0, 0, min(len(hdr) * 8 + 12, img.width), 26], fill=(0, 0, 0, 200))
    d.text((6, 5), hdr, fill=(0, 255, 120, 255), font=f)

    p = save(img, os.path.basename(path))
    print(f"preview: {p}")
    return p


def write_config(grid, safe, extra: dict | None = None) -> str:
    gx, gy, gw, gh = grid
    cfg = {
        "grid": {"x": int(gx), "y": int(gy), "w": int(gw), "h": int(gh),
                 "cols": COLS, "rows": ROWS},
        "safe_clear": {"x": int(safe[0]), "y": int(safe[1])} if safe else None,
        "cell_inset": 8,
        "icon": {"trim": True, "remove_bg": True, "out_size": 128,
                 "flood_thresh": 14, "erode": 1},
        "mem": {"addr": "0x2C00EA08", "type": "u32", "ptr_chain": []},
        "process_hint": {"pid": None, "name": "MiniGameApp.exe"},
        "timing": {"hover_ms": 150, "tooltip_ms": 400, "tooltip_timeout_ms": 1500,
                   "settle_ms": 180, "jitter_ms": 80, "realign_tol_px": 8,
                   "auto_realign_px": 45},
        "ocr": {"engine": "tesseract", "langs": "eng", "scale": 2, "invert": True},
        "hotkey": {"calibrate": "F6", "grid_ok": "F7", "next_page": "F9", "stop": "F10"},
        "output": {"dir": "output", "icons": "output/icons",
                   "jsonl": "output/scan.jsonl", "shots": "output/debug"},
    }
    if extra:
        cfg.update(extra)
    with open(CONFIG, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)
    print(f"config: {os.path.abspath(CONFIG)}")
    print(json.dumps({"grid": cfg["grid"], "safe_clear": cfg["safe_clear"]},
                     indent=2))
    return CONFIG


# ------------------------------------------------------------------- GUI ----
def gui() -> int:
    try:
        import tkinter as tk
        from PIL import ImageTk
    except Exception as e:
        print(f"[!] tkinter/Pillow tidak tersedia: {e}\n    pakai mode --grid/--safe")
        return 1

    img = grab()
    print(f"capture layar {img.size[0]}x{img.size[1]}")
    pts: list[tuple[int, int]] = []

    root = tk.Tk()
    root.overrideredirect(True)
    root.attributes("-topmost", True)
    root.geometry(f"{img.width}x{img.height}+0+0")
    cv = tk.Canvas(root, highlightthickness=0, bg="black")
    cv.pack(fill="both", expand=True)
    tk_img = ImageTk.PhotoImage(img)
    cv.create_image(0, 0, anchor="nw", image=tk_img)

    status = cv.create_text(10, 10, anchor="nw", fill="#00ff88",
                            font=("Consolas", 13, "bold"),
                            text="KLIK kiri-ATAS grid (4 baris penuh) -> lalu KANAN-BAWAH")

    def redraw():
        cv.delete("ov")
        if len(pts) >= 1:
            x, y = pts[0]
            cv.create_line(x - 20, y, x + 20, y, fill="#00ff88", width=2, tags="ov")
            cv.create_line(x, y - 20, x, y + 20, fill="#00ff88", width=2, tags="ov")
        if len(pts) >= 2:
            x1, y1 = pts[0]
            x2, y2 = pts[1]
            gx, gy = min(x1, x2), min(y1, y2)
            gw, gh = abs(x2 - x1), abs(y2 - y1)
            cw, ch = gw / COLS, gh / ROWS
            cv.create_rectangle(gx, gy, gx + gw, gy + gh, outline="#00ff88", width=3, tags="ov")
            for r in range(ROWS):
                for c in range(COLS):
                    x = gx + c * cw
                    y = gy + r * ch
                    cv.create_rectangle(x, y, x + cw, y + ch, outline="#00ff8855", tags="ov")
                    cv.create_text(x + 5, y + 4, anchor="nw", fill="#ffe63c",
                                   font=("Consolas", 9), text=f"{r},{c}", tags="ov")
                    cv.create_oval(x + cw / 2 - 3, y + ch / 2 - 3,
                                   x + cw / 2 + 3, y + ch / 2 + 3,
                                   fill="#00ff88", tags="ov")
            cv.itemconfigure(status, text=f"grid {gw}x{gh} @ {gx},{gy} - "
                                          f"cell {cw:.1f}x{ch:.1f}  |  "
                                          f"ENTER=simpan, R=ulang, ESC=batal")
        elif len(pts) == 1:
            cv.itemconfigure(status, text="KLIK KANAN-BAWAH grid (baris ke-5 yang "
                                          "terpotong JANGAN disertakan)")

    def on_click(ev):
        pts.append((ev.x, ev.y))
        redraw()

    def on_key(ev):
        k = ev.keysym.lower()
        if k == "r":
            pts.clear()
            redraw()
            cv.itemconfigure(status, text="RESET - klik kiri-ATAS grid")
        elif k == "escape":
            root.destroy()
        elif k == "return" and len(pts) >= 2:
            x1, y1 = pts[0]
            x2, y2 = pts[1]
            grid = (min(x1, x2), min(y1, y2), abs(x2 - x1), abs(y2 - y1))
            root.destroy()
            # titik aman: minta klik di layar penuh
            ask_safe(grid)

    def ask_safe(grid):
        r2 = tk.Tk()
        r2.overrideredirect(True)
        r2.attributes("-topmost", True)
        r2.geometry(f"{img.width}+0+0" if False else f"{img.width}x{img.height}+0+0")
        c2 = tk.Canvas(r2, highlightthickness=0, bg="black")
        c2.pack(fill="both", expand=True)
        im2 = ImageTk.PhotoImage(img)
        c2.image = im2
        c2.create_image(0, 0, anchor="nw", image=im2)
        draw_preview(grid, None)  # sementara, agar user lihat grid dulu
        st = c2.create_text(10, 10, anchor="nw", fill="#5aaeff",
                            font=("Consolas", 13, "bold"),
                            text="KLIK TITIK AMAN untuk klik CLEAR (di DALAM panel, "
                                 "di luar grid, bukan di tombol X/+Add) | ESC=batal")
        safe: list[tuple[int, int]] = []

        def ck(ev):
            safe.append((ev.x, ev.y))
            c2.create_oval(ev.x - 12, ev.y - 12, ev.x + 12, ev.y + 12,
                           outline="#5aaeff", width=2)
            c2.itemconfigure(st, text=f"titik aman = {ev.x},{ev.y} - ENTER=simpan, "
                                      f"KLIK ULANG=ubah, ESC=batal")

        def kk(ev):
            if ev.keysym == "Escape":
                r2.destroy()
            elif ev.keysym == "Return" and safe:
                pt = safe[-1]
                r2.destroy()
                write_config(grid, pt)
                draw_preview(grid, pt, note="CALIBRASI - verifikasi sebelum scan")

        c2.bind("<Button-1>", ck)
        r2.bind("<Key>", kk)
        r2.mainloop()

    cv.bind("<Button-1>", on_click)
    root.bind("<Key>", on_key)
    root.mainloop()
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Fase 1 kalibrasi grid 10x4")
    ap.add_argument("--capture", action="store_true", help="simpan screenshot layar")
    ap.add_argument("--focus", action="store_true",
                    help="angkat jendela game ke depan sebelum capture")
    ap.add_argument("--focus-title", default="miniworld",
                    help="potongan judul jendela yang dicari (default: miniworld)")
    ap.add_argument("--gui", action="store_true", help="kalibrasi interaktif dengan klik")
    ap.add_argument("--grid", type=str, help="x,y,w,h area grid (4 baris penuh)")
    ap.add_argument("--safe", type=str, help="x,y titik aman untuk klik clear")
    ap.add_argument("--preview", action="store_true",
                    help="gambar overlay di atas screenshot terbaru (verifikasi)")
    a = ap.parse_args()

    if a.focus:
        focus_window(a.focus_title)

    if a.capture:
        p = save(grab(), "screen.png")
        print(f"screenshot: {p} ({Image.open(p).size[0]}x{Image.open(p).size[1]})")
        return 0

    if a.gui:
        return gui()

    if a.grid:
        x, y, w, h = (int(v) for v in a.grid.split(","))
        grid = (x, y, w, h)
        safe = tuple(int(v) for v in a.safe.split(",")) if a.safe else None
        write_config(grid, safe)
        draw_preview(grid, safe, note="CALIBRASI - verifikasi sebelum scan")
        return 0

    if a.preview:
        if not os.path.exists(CONFIG):
            print("[!] config.json belum ada - jalankan --gui atau --grid dulu")
            return 1
        cfg = json.load(open(CONFIG, encoding="utf-8"))
        g = cfg["grid"]
        s = cfg.get("safe_clear")
        draw_preview((g["x"], g["y"], g["w"], g["h"]), (s["x"], s["y"]) if s else None,
                     note="PREVIEW terbaru")
        return 0

    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
