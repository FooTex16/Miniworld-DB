import time
import cv2
import numpy as np
from scan import cells_of, load_config, grab
from probe import move_to

cfg = load_config()
cells = cells_of(cfg)
c = cells[1]  # cell (0,1)

base = cv2.cvtColor(np.array(grab()), cv2.COLOR_RGB2BGR)
move_to(int(c["cx"]), int(c["cy"]))
t0 = time.time()
for i in range(16):
    time.sleep(0.15)
    img = cv2.cvtColor(np.array(grab()), cv2.COLOR_RGB2BGR)
    d = cv2.absdiff(base, img).sum(axis=2)
    mask = (d > 45).astype(np.uint8)
    keep = np.zeros(mask.shape, np.uint8)
    keep[110:880, 210:1810] = 1
    mask &= keep
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((31, 31), np.uint8))
    n, _l, stats, _c = cv2.connectedComponentsWithStats(mask, 8)
    big = [(stats[i][0], stats[i][1], stats[i][2], stats[i][3], stats[i][4])
           for i in range(1, n) if stats[i][4] > 30000 and stats[i][2] > 200]
    print(f"t={time.time()-t0:5.2f}s  blob besar: {big}")
    if big:
        break
