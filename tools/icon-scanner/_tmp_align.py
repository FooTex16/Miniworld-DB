import numpy as np
from scan import load_config, grab, detect_grid

cfg = load_config()
g = cfg["grid"]
cw, ch = g["w"] / g["cols"], g["h"] / g["rows"]
rgb = np.array(grab())
cols, rows, err = detect_grid(rgb, cfg)
print("err:", err)
if cols:
    exp_c = [g["x"] + (i + 0.5) * cw for i in range(g["cols"])]
    print("pusat kolom terdeteksi:", [round(v, 1) for v in np.mean(cols, axis=0)])
    print("pusat kolom config    :", [round(v, 1) for v in exp_c])
    exp_r = [g["y"] + (i + 0.5) * ch for i in range(g["rows"])]
    print("pusat baris terdeteksi:", [round(v, 1) for v in np.mean(rows, axis=0)])
    print("pusat baris config    :", [round(v, 1) for v in exp_r])
    # berapa baris yg terbaca kalau tanpa batas 4?
    print("(baris terdeteksi kolom 0, semua):", [round(v, 1) for v in rows[0]])
grab().save("output/debug/align_now.png")
print("screenshot: output/debug/align_now.png")
