import numpy as np
import cv2
from PIL import Image
import pytesseract

pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

BASE = "output/calib/screen.png"
SHOTS = [
    ("output/debug/hover_full.png", "cell_0_0"),
    ("output/debug/hover_cell_0_9.png", "cell_0_9"),
    ("output/debug/hover_cell_3_0.png", "cell_3_0"),
    ("output/debug/hover_cell_3_9.png", "cell_3_9"),
]


def tooltip_box(base_path, shot_path):
    a = cv2.imread(base_path)
    b = cv2.imread(shot_path)
    diff = cv2.absdiff(a, b).sum(axis=2)
    mask = (diff > 45).astype(np.uint8)
    # batasi area panel agar FPS counter / dunia di luar tidak ikut
    keep = np.zeros(mask.shape, np.uint8)
    keep[110:880, 210:1810] = 1
    mask = mask & keep
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((31, 31), np.uint8))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((9, 9), np.uint8))
    n, _l, stats, _c = cv2.connectedComponentsWithStats(mask, 8)
    best, area = None, 0
    for i in range(1, n):
        x, y, w, h, ar = stats[i]
        if ar > area and w > 200 and h > 150:
            best, area = (x, y, w, h), ar
    return best


for path, label in SHOTS:
    box = tooltip_box(BASE, path)
    print(f"{label:12} tooltip={box}")
    if not box:
        continue
    x, y, w, h = box
    for dy, dh in ((6, 46), (10, 40)):
        crop = Image.open(path).crop((x + 96, y + dy, x + 96 + 430, y + dy + dh))
        im = crop.convert("L").resize((crop.width * 2, crop.height * 2), Image.LANCZOS)
        im = Image.eval(im, lambda p: 255 - p).point(lambda p: 255 if p > 128 else 0)
        txt = " ".join(pytesseract.image_to_string(im, lang="eng", config="--psm 7").split())
        print(f"    offset(+96,{dy},430,{dh}) -> {txt!r}")
    crop = Image.open(path).crop((x, y, x + w, y + h))
    crop.save(f"output/debug/tip_{label}.png")
