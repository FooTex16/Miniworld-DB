import numpy as np, cv2
from PIL import Image
from scan import cells_of, load_config

cfg = load_config()
cells = cells_of(cfg)


def test(idx, shot, label):
    c = cells[idx]
    full = np.array(Image.open(shot).convert("L"))
    inset = 14
    x = int(c["x"]) + inset
    y = int(c["y"]) + inset
    w = int(c["w"]) - 2 * inset
    h = int(c["h"]) - 2 * inset
    tpl = full[y:y + h, x:x + w]
    best = []
    for s in (0.70, 0.75, 0.80, 0.85, 0.90, 1.0):
        tw, th = max(8, int(tpl.shape[1] * s)), max(8, int(tpl.shape[0] * s))
        t = cv2.resize(tpl, (tw, th))
        res = cv2.matchTemplate(full, t, cv2.TM_CCOEFF_NORMED)
        res[max(0, y - 5):y + h + 5, max(0, x - 5):x + w + 5] = -1
        _mn, mx, _mnl, mxl = cv2.minMaxLoc(res)
        best.append((round(float(mx), 3), s, mxl))
    best.sort(reverse=True)
    print(label, "cell=(%d,%d)" % (int(c["x"]), int(c["y"])), "->", best[:3])


test(0, "output/debug/hover_full.png", "cell_0_0")
test(9, "output/debug/hover_cell_0_9.png", "cell_0_9")
test(30, "output/debug/hover_cell_3_0.png", "cell_3_0")
test(39, "output/debug/hover_cell_3_9.png", "cell_3_9")
