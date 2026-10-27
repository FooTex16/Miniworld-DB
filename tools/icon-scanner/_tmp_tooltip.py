import numpy as np
import cv2
from PIL import Image

SHOTS = [
    ("output/debug/hover_full.png", "cell_0_0"),
    ("output/debug/hover_cell_0_9.png", "cell_0_9"),
    ("output/debug/hover_cell_3_0.png", "cell_3_0"),
    ("output/debug/hover_cell_3_9.png", "cell_3_9"),
]


def find_tooltip(path):
    img = cv2.imread(path)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    # area panel: di luar itu jangan disentuh (dunia gelap di bawah panel)
    region = np.zeros(gray.shape, np.uint8)
    region[120:865, 300:1800] = 1
    mask = ((gray < 175) & (region > 0)).astype(np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((25, 25), np.uint8))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((15, 15), np.uint8))
    n, _lab, stats, _cent = cv2.connectedComponentsWithStats(mask, 8)
    best, best_area = None, 0
    for i in range(1, n):
        x, y, w, h, area = stats[i]
        if area > best_area and w > 250 and h > 150:
            best, best_area = (x, y, w, h), area
    return best


for path, label in SHOTS:
    box = find_tooltip(path)
    print(f"{label:14} tooltip = {box}")
    if box:
        x, y, w, h = box
        # crop kira-kira baris nama: 12px dari atas, tinggi 44, mulai dari ikon+100
        crop = Image.open(path).crop((x + 100, y + 8, x + 100 + 420, y + 8 + 44))
        crop.save(f"output/debug/name_{label}.png")
        try:
            import pytesseract
            pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
            im = crop.convert("L").resize((crop.width * 2, crop.height * 2), Image.LANCZOS)
            im = Image.eval(im, lambda p: 255 - p)
            im = im.point(lambda p: 255 if p > 128 else 0)
            txt = pytesseract.image_to_string(im, lang="eng", config="--psm 7")
            print(f"{'':14} OCR -> {' '.join(txt.split())!r}")
        except Exception as e:
            print(f"{'':14} OCR gagal: {e}")
