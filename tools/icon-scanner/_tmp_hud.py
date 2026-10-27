"""Uji HUD overlay: render, zona aman, dan hasil screenshot."""
import glob
import time

from PIL import Image

from overlay import Overlay
from scan import grab

ov = Overlay()
ov.set(cat="Blocks > Terrain", page=3, cell=(0, 4),
       phase="melacak ikon block...", bid=100,
       name="Grassy Soil Block", ocr="Grassy Soil",
       counts={"done": 12, "skip": 3, "dup": 1, "lock": 2, "fail": 0,
               "page_done": 16, "page_total": 40},
       recent=["100     Grassy Soil Block", "101     Soil",
               "102     Farmland", "446     Purple Fluorite Ore",
               "960     U-Concrete (terkunci)"])
icons = sorted(glob.glob("output/icons/*.png"))
# pakai ikon yang benar-benar punya isi (bukan PNG kosong)
chosen = None
for p in icons:
    im = Image.open(p).convert("RGBA")
    if im.getbbox():
        chosen = (p, im)
        break
if chosen:
    print("ikon dipakai:", chosen[0], "bbox:", chosen[1].getbbox())
    ov.set(icon=chosen[1])
else:
    print("[!] tidak ada ikon berisi!")
time.sleep(1.5)

img = grab()
img.save("output/debug/hud.png")

# zona aman: area grid (x 370..1766, y 231..862) tidak boleh tersentuh HUD
import numpy as np
a = np.array(img)
grid = a[231:862, 370:1766]
print("rata-rata piksel area grid :", grid.reshape(-1, 3).mean(axis=0).round(1))
print("pita atas y=60  baris      :", a[60, 0], a[60, 960])
print("pita bawah y=1000          :", a[1000, 0], a[1000, 960])
print("kiri y=500 x=100 (harus game):", a[500, 100])
prev = a[920:1070, 16:166].reshape(-1, 3)
print("preview ikon: warna unik =", len(np.unique(prev, axis=0)),
      "| mean =", prev.mean(axis=0).round(1))
ov.close()
print("ok -> output/debug/hud.png")
