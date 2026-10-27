"""Tes auto-scroll: kirim wheel, ukur geser baris + perubahan konten."""
import numpy as np
from PIL import Image

from calibrate import focus_window
from probe import wheel
from scan import _park_cursor, cells_of, detect_grid, grab, load_config

focus_window("miniworld")
cfg = load_config()
cfg["grid"]["y"] += 14                 # koreksi auto-realign terakhir
cells = cells_of(cfg)


def fingerprint(cs):
    fp = []
    for c in cs:
        box = (int(c["x"]) + 10, int(c["y"]) + 10,
               int(c["x"] + c["w"]) - 10, int(c["y"] + c["h"]) - 10)
        im = grab(box).convert("L").resize((12, 12), Image.BILINEAR)
        fp.append(np.asarray(im, dtype=float))
    return np.array(fp)


def row_centers():
    _park_cursor(cfg)
    rgb = np.array(grab())
    _c, rows, err = detect_grid(rgb, cfg)
    if rows is None:
        return None, err
    return [round(float(v), 1) for v in np.mean(rows, axis=0)], err


r0, err0 = row_centers()
fp1 = fingerprint(cells)
print("sebelum: baris =", r0, err0)

# --- kirim 1 notch ke bawah di tengah grid
cx, cy = int(cfg["grid"]["x"] + cfg["grid"]["w"] / 2), \
         int(cfg["grid"]["y"] + cfg["grid"]["h"] / 2)
wheel(cx, cy, -120)
import time
time.sleep(1.0)

r1, err1 = row_centers()
fp2 = fingerprint(cells)
print("sesudah: baris =", r1, err1)

if r1 and r0:
    print("dy =", round(np.mean(np.array(r1) - np.array(r0)), 1), "px")

print("matriks kemiripan baris baru -> baris lama (L1, makin kecil makin sama):")
for i in range(4):
    d = [round(float(np.abs(fp2[i] - fp1[j]).mean()), 1) for j in range(4)]
    print(f"  baris baru {i}: {d}")
