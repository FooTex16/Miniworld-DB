"""Bandingkan hasil extract_icon dengan parameter berbeda pada crop cell asli."""
from PIL import Image, ImageDraw

from scan import cells_of, load_config, grab, extract_icon

cfg = load_config()
cells = cells_of(cfg)
PICK = [1, 2, 4, 11, 21, 30]
VARIANTS = [
    ("mentah", None),
    ("t14 e1", {"remove_bg": True, "trim": True, "out_size": 128,
                "flood_thresh": 14, "erode": 1}),
    ("t28 e1", {"remove_bg": True, "trim": True, "out_size": 128,
                "flood_thresh": 28, "erode": 1}),
    ("t40 e0", {"remove_bg": True, "trim": True, "out_size": 128,
                "flood_thresh": 40, "erode": 0}),
]

inset = int(cfg.get("cell_inset", 8))
raws = []
for idx in PICK:
    c = cells[idx]
    bx, by = int(c["x"] + inset), int(c["y"] + inset)
    bw, bh = int(c["w"] - 2 * inset), int(c["h"] - 2 * inset)
    raws.append((f"{c['r']},{c['c']}", grab((bx, by, bx + bw, by + bh))))


def checker(n):
    im = Image.new("RGB", (n, n), (60, 60, 60))
    d = ImageDraw.Draw(im)
    for i in range(0, n, 10):
        for j in range(0, n, 10):
            if (i // 10 + j // 10) % 2 == 0:
                d.rectangle([i, j, i + 9, j + 9], fill=(95, 95, 95))
    return im


cell_w = 140
rows = len(VARIANTS)
sheet = Image.new("RGB", (len(PICK) * cell_w, rows * 140 + 8), (30, 30, 30))
for r, (label, var) in enumerate(VARIANTS):
    for c, (_pos, raw) in enumerate(raws):
        if var is None:
            tile = raw.convert("RGB").resize((128, 128))
        else:
            out = extract_icon(raw, {**cfg, "icon": var})
            tile = checker(128)
            tile.paste(out, (0, 0), out)
        sheet.paste(tile, (c * cell_w + 6, r * 140 + 6))

sheet.save("output/debug/icon_variants.png")
print("tersimpan output/debug/icon_variants.png  baris:", [v[0] for v in VARIANTS])
print("cell:", [p[0] for p in [(l, 0) for l, _ in raws]])
