import time
import cv2
import numpy as np
from scan import cells_of, load_config, grab, to_bgr, find_tooltip, PANEL
from probe import move_to, get_cursor

cfg = load_config()
cells = cells_of(cfg)
sc = cfg["safe_clear"]

move_to(sc["x"], sc["y"])
time.sleep(0.4)
base = to_bgr(grab())
print("baseline diambil, cursor =", get_cursor())

c = cells[3]
move_to(int(c["cx"]), int(c["cy"]))
print("hover ke", int(c["cx"]), int(c["cy"]), "cursor =", get_cursor())
for i in range(12):
    time.sleep(0.15)
    img = to_bgr(grab())
    box = find_tooltip(base, img)
    d = cv2.absdiff(base, img).sum(axis=2)
    mask = (d > 45).astype(np.uint8)
    keep = np.zeros(mask.shape, np.uint8)
    x, y, w, h = PANEL
    keep[y:y + h, x:x + w] = 1
    mask &= keep
    n_px = int(mask.sum())
    m2 = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((31, 31), np.uint8))
    n, _l, stats, _c = cv2.connectedComponentsWithStats(m2, 8)
    big = sorted([tuple(int(v) for v in stats[i][:5]) for i in range(1, n)],
                 key=lambda s: -s[4])[:3]
    print(f"  t={i*0.15:.2f}px={n_px:7d} box={box} komponen={big}")
    if box:
        img_out = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        cv2.imwrite("output/debug/dbg_found.png", img)
        print("  -> TOOLTIP TERDETEKSI")
        break
else:
    cv2.imwrite("output/debug/dbg_notfound.png", to_bgr(grab()))
    print("  -> gagal; screenshot disimpan output/debug/dbg_notfound.png")
