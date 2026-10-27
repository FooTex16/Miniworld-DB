"""Debug: hover sel terkunci, simpan diff-box + crop nama agar bisa dilihat."""
import cv2
import numpy as np
from PIL import Image

from scan import (TIP_NAME_BOX, cells_of, clean, grab, load_config, ocr_name,
                  to_bgr, wait_tooltip, _park_cursor, find_tooltip)
from calibrate import focus_window

focus_window("miniworld")

cfg = load_config()
# tiru koreksi auto-realign terakhir
cfg["grid"]["x"] += 0
cfg["grid"]["y"] += 14
cells = cells_of(cfg)

from probe import move_to

for idx in (37, 38, 39):          # (3,7) (3,8) (3,9)
    c = cells[idx]
    _park_cursor(cfg)
    base = to_bgr(grab())
    move_to(int(c["cx"]), int(c["cy"]))
    box, img = wait_tooltip(base, 1800)
    print(f"cell ({c['r']},{c['c']}) center=({int(c['cx'])},{int(c['cy'])}) -> box={box}")
    if not box:
        continue
    pil = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
    dx, dy, w, h = TIP_NAME_BOX
    crop = pil.crop((box[0] + dx, box[1] + dy, box[0] + dx + w, box[1] + dy + h))
    crop.save(f"output/debug/lock_name_{c['r']}{c['c']}.png")
    pil.crop((max(0, box[0] - 60), max(0, box[1] - 60),
              min(1920, box[0] + 900), min(1080, box[1] + 500))).save(
        f"output/debug/lock_tip_{c['r']}{c['c']}.png")
    print("   OCR psm7 ->", repr(clean(ocr_name(box, pil, cfg))))
