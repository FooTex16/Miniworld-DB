"""Ukur geometri sel sesungguhnya dari piksel (tanpa asumsi config)."""
import numpy as np

from scan import _segments, _park_cursor, grab, load_config, PANEL

cfg = load_config()
_park_cursor(cfg)
rgb = np.array(grab())
bg = np.array([250, 250, 242])

g = cfg["grid"]
cw = g["w"] / g["cols"]

print("== potongan vertikal (baris sel) ==")
for c in (0, 5, 9):
    x = int(g["x"] + (c + 0.5) * cw)
    line = rgb[PANEL[1]:PANEL[1] + PANEL[3], x]
    segs = [s for s in _segments(np.abs(line - bg).sum(axis=1) > 6)
            if s[1] - s[0] > 25]
    out = [(s[0] + PANEL[1], s[1] + PANEL[1], s[1] - s[0] + 1) for s in segs]
    print(f"  kolom {c}: y0..y1 (tinggi) -> {out}")

print("== potongan horizontal (kolom sel) ==")
y_guess = [260, 400, 540, 680, 820]
for y in y_guess:
    line = rgb[y, g["x"] - 80:g["x"] + g["w"] + 80]
    segs = [s for s in _segments(np.abs(line - bg).sum(axis=1) > 6)
            if s[1] - s[0] > 60]
    print(f"  y={y}: {len(segs)} kolom, lebar={[s[1]-s[0]+1 for s in segs][:10]}")
