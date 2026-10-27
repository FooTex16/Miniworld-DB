import numpy as np
from PIL import Image
import pytesseract

pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

TIPS = [
    ("cell_0_0", (568, 147, 723, 642), "Grassy Soil Block"),
    ("cell_0_9", (1018, 408, 723, 289), "Horas pit"),
    ("cell_3_0", (554, 368, 724, 442), "???"),
    ("cell_3_9", (1018, 344, 723, 490), "Ordinary Crystal Core Ore"),
]

best = {}
for label, (x, y, w, h), expect in TIPS:
    img = Image.open(f"output/debug/hover_{label}.png" if label != "cell_0_0"
                     else "output/debug/hover_full.png")
    results = []
    for dx in (104, 112, 120, 128):
        for dy in (4, 8, 12):
            crop = img.crop((x + dx, y + dy, x + dx + 440, y + dy + 44))
            im = crop.convert("L")
            im = im.resize((im.width * 3, im.height * 3), Image.LANCZOS)
            im = Image.eval(im, lambda p: 255 - p)      # teks terang -> gelap
            for psm in ("7", "6"):
                t = " ".join(pytesseract.image_to_string(
                    im, lang="eng", config=f"--psm {psm} --oem 1").split())
                if t:
                    results.append((dx, dy, psm, t))
    print(f"--- {label} (harusnya: {expect!r})")
    seen = set()
    for dx, dy, psm, t in results:
        if t.lower() in seen:
            continue
        seen.add(t.lower())
        print(f"    dx={dx} dy={dy} psm={psm}: {t!r}")
