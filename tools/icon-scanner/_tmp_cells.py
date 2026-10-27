"""Debug: kenapa detect_cells kehilangan sel? Cetak segmen per baris."""
import numpy as np

from scan import _segments, _park_cursor, grab, load_config

cfg = load_config()
g = cfg["grid"]
_park_cursor(cfg)
rgb = np.array(grab())
bg = np.array([250, 250, 242])
diff = np.abs(rgb.astype(np.int16) - bg).sum(axis=2) > 6

pitch = g["h"] / g["rows"]
y_lo, y_hi = max(0, g["y"] - 40), min(rgb.shape[0], g["y"] + g["h"] + 130)
x_lo, x_hi = max(0, g["x"] - 60), min(rgb.shape[1], g["x"] + g["w"] + 60)
cw = g["w"] / g["cols"]
print(f"pitch={pitch:.1f} min_h={pitch-16:.1f} | y {y_lo}..{y_hi} | x {x_lo}..{x_hi}")

# baris (sama persis dgn detect_cells)
samples = [int(g["x"] + (i + 0.5) * cw) for i in (0, 4, 8)]
found = []
for x in samples:
    for s in _segments(diff[y_lo:y_hi, x]):
        h = s[1] - s[0] + 1
        if h >= pitch - 16:
            found.append((int(s[0]) + y_lo, int(s[1]) + y_lo))
found.sort()
rows, cur = [], None
for s in found:
    if cur and abs(s[0] - cur[0]) <= 10:
        cur = (cur[0], max(cur[1], s[1]))
    else:
        if cur:
            rows.append(cur)
        cur = s
if cur:
    rows.append(cur)
rows = rows[: g["rows"]]
print("baris:", rows)

for y0, y1 in rows:
    yc = (y0 + y1) // 2
    segs = [(int(a) + x_lo, int(b) + x_lo) for a, b in _segments(diff[yc, x_lo:x_hi])]
    print(f"  row {y0}..{y1} h={y1-y0+1} yc={yc}:")
    print(f"    x = {[(a, b) for a, b in segs]}")
    # sampel piksel di pita atas tiap kolom referensi (okupansi)
    probe = []
    for j in range(g["cols"]):
        cx = int(g["x"] + (j + 0.5) * cw)
        vals = [int(rgb[y0 + 4, cx].sum() // 3), int(rgb[y0 + 64, cx].sum() // 3)]
        probe.append(vals)
    print(f"    piksel (atas, tengah) per kolom config: {probe}")
