#!/usr/bin/env python3
"""
Fase 2 - SCANNER (10 x 4 sel per halaman).

Alur per sel:
    1. kursor ke titik aman + baseline (layar bersih tanpa tooltip)
    2. crop isi cell         -> IKON transparan 128px (SEBELUM hover!
                                tooltip bisa menutupi cell -> overlay gelap)
    3. hover cell            -> poll sampai tooltip terdeteksi (diff vs baseline)
    4. crop baris nama       -> OCR (Eng) -> fuzzy-match ke nama resmi index.json
    5. klik cell (pick)      -> baca 0x2C00EA08 (uint32) -> ID block
    6. klik titik aman       -> clear, verifikasi ID kembali 0
    7. append JSONL

Nama akhir:
    name_index  = nama resmi dari data/index.json (lookup lewat ID) -> sumber utama
    name_ocr    = nama yang dibaca dari tooltip game -> validasi silang
    name_final  = name_index bila ada, else name_ocr
    mismatch    = true kalau keduanya ada tetapi berbeda (perlu review)

Mode:
  python scan.py --max-cells 3        # uji 3 sel
  python scan.py --page 1             # satu halaman penuh
  python scan.py --dry-run            # tanpa klik & tanpa memori
  python scan.py --no-ocr             # lewati hover/OCR (cepat, nama dari index saja)
"""
from __future__ import annotations

import argparse
import ctypes
import difflib
import json
import os
import random
import re
import sys
import tempfile
import time
from datetime import datetime

# --- Lokasi aplikasi TETAP di folder ini, walau sudah di-build jadi .exe ---
# Semua path relatif (config.json, output/, ../../data/index.json) di-resolve
# dari sini, jadi EXE yang dijalankan dari folder mana pun tetap memakai data
# yang sama: config, output/scan.jsonl, dan data/index.json tidak berpindah.
_APP_DIR_FIXED = r"D:\WORK\MINI WORLD DB\Miniworld-DB\tools\icon-scanner"
if os.path.isdir(_APP_DIR_FIXED):
    _BASE = _APP_DIR_FIXED
elif getattr(sys, "frozen", False):          # folder asli hilang -> ikut exe
    _BASE = os.path.dirname(os.path.abspath(sys.executable))
else:
    _BASE = os.path.dirname(os.path.abspath(__file__))
os.chdir(_BASE)                              # config.json / output/ relatif

# --- SEMUA file sementara (pytesseract / PIL / anak proses tesseract) ke D: ---
# Drive C: tinggal sedikit kosong -> tempfile gagal dengan
# "[Errno 28] No space left on device" dan OCR mati. Proyek ada di D:, jadi
# simpan sementara di folder ini juga (di D:).
TEMP_DIR = os.path.join(_BASE, "temp")
os.makedirs(TEMP_DIR, exist_ok=True)
tempfile.tempdir = TEMP_DIR
os.environ["TEMP"] = TEMP_DIR
os.environ["TMP"] = TEMP_DIR

# WAJIB sebelum capture: pixel = pixel fisik (koordinat kalibrasi = koordinat klik)
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

import cv2
import numpy as np
from PIL import Image, ImageDraw

from probe import (MemReader, click, get_cursor, move_to, module_of,
                   process_name, wheel)
from export import DATA_ROOT, Exporter
from overlay import (ACCENT as HUD_OK, BAD as HUD_BAD, MUTED as HUD_MUTED,
                     Ctrl, Overlay)

CTRL = Ctrl()                       # tombol HUD (LANJUT / JEDA / STOP)

CONFIG = os.path.join(_BASE, "config.json")
TESSERACT = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
INDEX = os.path.abspath(os.path.join(_BASE, "..", "..", "data", "index.json"))

# panel game (untuk membatasi area deteksi tooltip) - x, y, w, h
PANEL = (210, 110, 1600, 770)
TIP_NAME_BOX = (104, 12, 440, 44)  # dx, dy, w, h relatif ke pojok kiri-atas tooltip


# ------------------------------------------------------------------ config --
def load_config() -> dict:
    if not os.path.exists(CONFIG):
        sys.exit("[!] config.json belum ada. Jalankan dulu:  python calibrate.py --gui")
    with open(CONFIG, encoding="utf-8") as f:
        return json.load(f)


def save_config(cfg: dict) -> None:
    """Tulis config.json (kunci bantu yang diawari "_" tidak ikut ditulis)."""
    data = {k: v for k, v in cfg.items() if not str(k).startswith("_")}
    tmp = CONFIG + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, CONFIG)


# ----------------------------------------------- alamat pick-id (kolom HUD) --
def apply_mem_addr(cfg: dict, raw: str, reader, ov=None,
                   dry_run: bool = False) -> bool:
    """Terapkan alamat pick-id baru yang diketik user di HUD.

    Alamat hanya dipakai bila benar-benar BISA DIBACA dari memori game, jadi
    tombol SET langsung membuktikan "id bisa terbaca". Hasilnya ditulis ke
    config.json supaya run berikutnya (EXE) memakai alamat yang sama.
    -> True bila permintaan diproses (diterima maupun ditolak)."""
    txt = str(raw).strip()
    val, bad = None, None
    try:
        val = int(txt, 0)
        if not 0 < val < (1 << 64):
            raise ValueError("di luar rentang alamat 64-bit")
    except Exception as e:
        bad = f"alamat tidak sah: {e}"

    nilai = None
    if bad is None and reader is not None and not dry_run:
        try:
            nilai = reader.u32(val)          # ReadProcessMemory, 4 byte LE
        except Exception as e:
            bad = f"tidak terbaca: {e}"

    if bad:
        print(f"[mem] {txt!r} DITOLAK - {bad}")
        print(f"      alamat aktif tetap {cfg['mem']['addr']}")
        if ov:
            ov.set(mem_msg=f"DITOLAK: {bad}",
                   mem_fg=HUD_BAD,
                   mem_val=f"alamat aktif: {cfg['mem']['addr']}",
                   mem_vfg=HUD_MUTED)
        return True

    if val != cfg.get("_addr"):
        cfg["_addr"] = val
        cfg["mem"]["addr"] = hex(val)
        try:
            save_config(cfg)
        except Exception as e:
            print(f"[mem] peringatan: config.json tidak tersimpan ({e})")
        print(f"[mem] alamat pick-id -> {hex(val)}")

    # kolom isian sempat mengambil foreground -> kembalikan ke jendela game
    if reader is not None and not dry_run:
        try:
            from calibrate import focus_window
            focus_window("miniworld")
        except Exception:
            pass

    if ov:
        if nilai is None:
            ov.set(mem_addr=hex(val), mem_msg="alamat dipakai (tanpa verifikasi)",
                   mem_fg=HUD_MUTED, mem_val="nilai = -", mem_vfg=HUD_MUTED)
        else:
            ov.set(mem_addr=hex(val),
                   mem_msg=f"OK terbaca -> {hex(val)}", mem_fg=HUD_OK,
                   mem_val=f"nilai = {nilai} (u32)",
                   mem_vfg=HUD_OK if nilai else HUD_MUTED)
    return True


def drain_mem_req(cfg: dict, reader, ov=None, dry_run: bool = False) -> bool:
    """Ambil (kalau ada) permintaan alamat dari HUD lalu terapkan.
    -> True bila ada permintaan yang diproses."""
    raw = CTRL.take_mem()
    if raw is None:
        return False
    return apply_mem_addr(cfg, raw, reader, ov, dry_run)


def push_mem(cfg: dict, reader, ov) -> None:
    """Baca nilai terkini di alamat pick -> kolom pembaca di HUD."""
    if reader is None or ov is None:
        return
    try:
        v = reader.u32(cfg["_addr"])
        ov.set(mem_val=f"nilai = {v} (u32)",
               mem_vfg=HUD_OK if v else HUD_MUTED)
    except Exception as e:
        ov.set(mem_val=f"GAGAL BACA: {e}", mem_vfg=HUD_BAD)


def find_pid(hint: dict) -> int:
    import psutil
    if hint and hint.get("pid"):
        return int(hint["pid"])
    name = (hint or {}).get("name")
    if name:
        for p in psutil.process_iter(["pid", "name"]):
            if (p.info["name"] or "").lower() == name.lower():
                return int(p.info["pid"])
    for p in psutil.process_iter(["pid", "name"]):
        if "mini" in (p.info["name"] or "").lower():
            return int(p.info["pid"])
    sys.exit("[!] proses game tidak ditemukan (lihat: python probe.py --list)")


def cells_of(cfg: dict):
    g = cfg["grid"]
    cw, ch = g["w"] / g["cols"], g["h"] / g["rows"]
    out = []
    for r in range(g["rows"]):
        for c in range(g["cols"]):
            x = g["x"] + c * cw
            y = g["y"] + r * ch
            out.append({"r": r, "c": c, "x": x, "y": y, "w": cw, "h": ch,
                        "cx": x + cw / 2, "cy": y + ch / 2})
    return out


def jitter(v: float, amt: int = 3) -> int:
    return int(round(v + random.uniform(-amt, amt)))


def load_index(path: str) -> tuple[dict, dict]:
    """-> (ID -> {name, zh}, nama_lower -> ID) dari data/index.json resmi."""
    if not os.path.exists(path):
        print(f"[!] index tidak ditemukan ({path}) -> nama hanya dari OCR")
        return {}, {}
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    by_id = {e["i"]: {"name": e.get("e") or "", "zh": e.get("z") or "",
                      "s": e.get("s") or "", "l": e.get("l") or ""}
             for e in data["entries"]}
    by_name = {v["name"].lower(): k for k, v in by_id.items() if v["name"]}
    return by_id, by_name


# ------------------------------------------------------------------ capture -
def grab(bbox=None) -> Image.Image:
    from PIL import ImageGrab
    return ImageGrab.grab(bbox=bbox) if bbox else ImageGrab.grab()


def to_bgr(img: Image.Image) -> np.ndarray:
    return cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)


def find_tooltip(base_bgr: np.ndarray, img_bgr: np.ndarray):
    """Area yang berubah besar setelah hover -> kotak tooltip (x,y,w,h) atau None."""
    d = cv2.absdiff(base_bgr, img_bgr).sum(axis=2)
    mask = (d > 45).astype(np.uint8)
    keep = np.zeros(mask.shape, np.uint8)
    x, y, w, h = PANEL
    keep[y:y + h, x:x + w] = 1
    mask &= keep
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((31, 31), np.uint8))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((9, 9), np.uint8))
    n, _lab, stats, _cent = cv2.connectedComponentsWithStats(mask, 8)
    best, best_area = None, 0
    for i in range(1, n):
        bx, by, bw, bh, area = stats[i]
        if area > best_area and bw > 400 and bh > 150:
            best, best_area = (int(bx), int(by), int(bw), int(bh)), int(area)
    return best


def wait_tooltip(base_bgr, timeout_ms: int = 1500):
    """Polling capture sampai tooltip terdeteksi DAN posisinya stabil
    (2 deteksi berturut dalam 8px) supaya crop nama tidak kena animasi.
    -> (box, img_bgr) | (None, None)"""
    t0 = time.time()
    prev, img = None, None
    while (time.time() - t0) * 1000 < timeout_ms:
        img = to_bgr(grab())
        box = find_tooltip(base_bgr, img)
        if box and prev and abs(box[0] - prev[0]) <= 8 and abs(box[1] - prev[1]) <= 8:
            return box, img
        prev = box
        time.sleep(0.12)
    if prev and img is not None:
        return prev, img          # belum terkonfirmasi, tapi tetap dipakai
    return None, None


# --------------------------------------------------------------------- ocr --
_ocr = None


def _tess(img: Image.Image, cfg_str: str, langs: str) -> str:
    """OCR satu crop (grayscale, upscale 3x, teks terang -> gelap)."""
    im = img.convert("L")
    im = im.resize((im.width * 3, im.height * 3), Image.LANCZOS)
    im = Image.eval(im, lambda p: 255 - p)
    try:
        return _ocr.image_to_string(im, lang=langs, config=cfg_str)
    except Exception as e:
        print(f"    [!] OCR gagal: {e}")
        return ""


def ocr_name(tip_box, screen_img: Image.Image, cfg: dict) -> str:
    global _ocr
    if _ocr is None:
        try:
            import pytesseract
            if os.path.exists(TESSERACT):
                pytesseract.pytesseract.tesseract_cmd = TESSERACT
            _ocr = pytesseract
        except Exception:
            return ""
    langs = cfg.get("ocr", {}).get("langs", "eng")
    x, y, _tw, _th = tip_box
    dx, dy, w, h = TIP_NAME_BOX
    txt = _tess(screen_img.crop((x + dx, y + dy, x + dx + w, y + dy + h)),
                "--psm 7 --oem 1", langs)
    if len(clean(txt)) >= 3:
        return txt
    # fallback: crop lebih tinggi, ambil baris pertama (nama selalu di baris atas)
    txt = _tess(screen_img.crop((x + 100, y - 4, x + 100 + 470, y - 4 + 76)),
                "--psm 6 --oem 1", langs)
    lines = [ln for ln in txt.splitlines() if ln.strip()]
    return lines[0] if lines else txt


def clean(s: str) -> str:
    s = re.sub(r"^[^A-Za-z0-9(\[]+", "", s or "").strip()
    return s


# breadcrumb kategori di header panel - kiri, atas, kanan, bawah
CAT_BOX = (355, 134, 720, 184)


def read_category(cfg) -> str:
    """OCR breadcrumb kategori di header panel -> 'Blocks > Natural'."""
    global _ocr
    if _ocr is None:
        try:
            import pytesseract
            if os.path.exists(TESSERACT):
                pytesseract.pytesseract.tesseract_cmd = TESSERACT
            _ocr = pytesseract
        except Exception:
            return ""
    langs = cfg.get("ocr", {}).get("langs", "eng")
    try:
        im = grab(CAT_BOX).convert("L")
        im = im.resize((im.width * 3, im.height * 3), Image.LANCZOS)
        im = Image.eval(im, lambda p: 255 - p)
        txt = " ".join(_tess(im, "--psm 7 --oem 1", langs).split())
    except Exception:
        return ""
    return re.sub(r"\s*>\s*", " > ", txt).strip()


def match_official(ocr_text: str, names: list[str]) -> tuple[str, float]:
    """Fuzzy-match hasil OCR ke daftar nama resmi -> (nama_resmi, skor)."""
    t = clean(ocr_text)
    if not t:
        return "", 0.0
    hits = difflib.get_close_matches(t, names, n=1, cutoff=0.70)
    if not hits:
        return "", 0.0
    score = difflib.SequenceMatcher(None, t.lower(), hits[0].lower()).ratio()
    return (hits[0], score) if score >= 0.78 else ("", score)


def _ocr_quality(txt: str, names: list[str]) -> int:
    """Skor kualitas hasil OCR: 0 = sampah, 1 = ada kata, 2 = cocok nama resmi."""
    if not txt:
        return 0
    words = [w for w in re.split(r"[^A-Za-z]+", txt) if len(w) >= 3]
    if not words:
        return 0
    hit, _s = match_official(txt, names)
    return 2 if hit else 1


# --------------------------------------------------------------- icon crop --
def extract_icon(cell_img: Image.Image, cfg: dict) -> Image.Image:
    """Crop isi cell -> buang latar (flood-fill) -> trim -> kotak keluaran."""
    ic = cfg.get("icon", {})
    out_size = int(ic.get("out_size", 128))
    img = cell_img.convert("RGB")

    if ic.get("remove_bg", True):
        work = img.copy()
        w, h = work.size
        marker = (255, 0, 255)
        thresh = int(ic.get("flood_thresh", 14))
        for pt in [(0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1),
                   (w // 2, 0), (w // 2, h - 1), (0, h // 2), (w - 1, h // 2)]:
            try:
                ImageDraw.floodfill(work, pt, marker, thresh=thresh)
            except Exception:
                pass
        arr = np.array(work)
        bg_mask = np.all(arr == np.array(marker, dtype=np.uint8), axis=-1)
        alpha = np.where(bg_mask, 0, 255).astype(np.uint8)
        # buang fringe anti-alias (1 px) supaya tidak ada garis abu di tepi ikon
        er = int(ic.get("erode", 1))
        if er:
            alpha = cv2.erode(alpha, np.ones((2 * er + 1, 2 * er + 1), np.uint8))
        rgba = np.dstack([np.array(img), alpha])
        out = Image.fromarray(rgba, "RGBA")
    else:
        out = img.convert("RGBA")

    if ic.get("trim", True):
        bbox = out.split()[-1].getbbox()
        if bbox:
            pad = 3
            bbox = (max(0, bbox[0] - pad), max(0, bbox[1] - pad),
                    min(out.width, bbox[2] + pad), min(out.height, bbox[3] + pad))
            out = out.crop(bbox)

    canvas = Image.new("RGBA", (out_size, out_size), (0, 0, 0, 0))
    scale = min(out_size / max(out.width, 1), out_size / max(out.height, 1))
    nw, nh = max(1, int(out.width * scale)), max(1, int(out.height * scale))
    out = out.resize((nw, nh), Image.LANCZOS)
    canvas.paste(out, ((out_size - nw) // 2, (out_size - nh) // 2), out)
    return canvas


# ----------------------------------------------------------------- logging --
class Log:
    def __init__(self, path: str):
        self.path = path
        self.done: set[tuple[int, int, int]] = set()
        self.failed: set[tuple[int, int, int]] = set()   # perlu diulang
        self.key_fp: dict[tuple[int, int, int], list[int]] = {}   # slot -> fp
        self.id_status: dict[int, bool] = {}                      # id -> ikon bersih?
        self.icon_paths: set[str] = set()                         # file ikon terpakai
        self.recs: list[dict] = []                                # record sah
        if os.path.exists(path):
            good: set = set()
            bad: set = set()
            with open(path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        r = json.loads(line)
                        key = (r.get("page"), r.get("row"), r.get("col"))
                        ok = bool(r.get("pick_ok", True)) or bool(r.get("locked"))
                        if not ok:
                            bad.add(key)        # sementara; bisa saja ada record
                            continue            # sukses lain utk slot yang sama
                        good.add(key)
                        self.recs.append(r)
                        fp = r.get("fp")
                        if isinstance(fp, list) and len(fp) == 256:
                            self.key_fp[key] = fp
                        bid = r.get("id") or r.get("id_guess")
                        if bid:
                            self.id_status[int(bid)] = self.id_status.get(
                                int(bid), False) or bool(r.get("icon_clean"))
                        if r.get("icon"):
                            self.icon_paths.add(r["icon"])
                    except Exception:
                        pass
            # slot hanya "gagal" bila TIDAK ADA record sukses untuk slot itu
            self.done = good
            self.failed = bad - good
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        self.f = open(path, "a", encoding="utf-8")

    def skip_same(self, key, fp, tol: float = None) -> bool:
        """Lewati hanya bila SLOT yang sama juga berisi IKON yang sama persis.
        Beda posisi atau beda isi -> tetap di-scan (tidak mungkin salah lewat).
        Sel yang gagal selalu diulang walau fp-nya tercatat."""
        if tol is None:
            tol = FP_TOL
        key = tuple(key)
        if key in self.failed:
            return False
        old = self.key_fp.get(key)
        if not old or not fp or len(old) != len(fp):
            return False
        d = np.abs(np.asarray(old, np.float32) - np.asarray(fp, np.float32)).mean()
        return bool(d <= tol)

    def id_done(self, bid, new_clean: bool) -> bool:
        """True bila ID ini sudah tercatat & tak perlu catatan kedua."""
        old = self.id_status.get(int(bid))
        if old is None:
            return False
        if old:                             # catatan lama ikonnya bersih
            return True
        return not new_clean                # dua-duanya kotor -> buang yang baru

    def write(self, rec: dict) -> None:
        rec["ts"] = datetime.now().isoformat(timespec="seconds")
        self.f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        self.f.flush()                      # WAJIB: tersimpan sebelum scroll
        key = (rec["page"], rec["row"], rec["col"])
        ok = bool(rec.get("pick_ok")) or bool(rec.get("locked"))
        if ok:
            self.done.add(key)
            self.failed.discard(key)
            self.recs.append(rec)
        else:
            self.failed.add(key)
            self.done.discard(key)
        if isinstance(rec.get("fp"), list) and len(rec["fp"]) == 256:
            self.key_fp[key] = rec["fp"]
        bid = rec.get("id") or rec.get("id_guess")
        if bid:
            self.id_status[int(bid)] = self.id_status.get(
                int(bid), False) or bool(rec.get("icon_clean"))
        if rec.get("icon"):
            self.icon_paths.add(rec["icon"])

    def close(self):
        self.f.close()


FP_BG = 200                                # abu-abu netral saat flatten alpha
FP_TOL = 1.5                               # rata-rata selisih 0..255


def icon_fp(img: Image.Image) -> list[int]:
    """Thumbnail 16x16 ikon (alpha di-flatten ke abu-abu) -> kunci dedup isi sel.
    Kunci ini yang bikin overlap antar-halaman tidak di-scan ulang."""
    im = img.convert("RGBA")
    flat = Image.new("RGBA", im.size, (FP_BG, FP_BG, FP_BG, 255))
    im = Image.alpha_composite(flat, im).convert("L")
    im = im.resize((16, 16), Image.BILINEAR)
    return list(im.tobytes())


def icon_fp_file(path: str):
    try:
        with Image.open(path) as im:
            return icon_fp(im)
    except Exception:
        return None


def icon_path(out_dir: str, page: int, r: int, c: int, bid: int) -> str:
    os.makedirs(out_dir, exist_ok=True)
    return os.path.join(out_dir, f"p{page:03d}_r{r}c{c:02d}_{bid}.png")


# -------------------------------------------------------------------- core --
def crop_icon(cell, cfg) -> tuple[Image.Image, bool]:
    """Crop isi cell. Wajib dipanggil saat tooltip TIDAK sedang tampil.
    -> (img, bersih?) - bersih=false berarti ada overlay gelap di crop."""
    inset = int(cfg.get("cell_inset", 8))
    bx, by = int(cell["x"] + inset), int(cell["y"] + inset)
    bw, bh = int(cell["w"] - 2 * inset), int(cell["h"] - 2 * inset)
    box = (bx, by, bx + bw, by + bh)

    def corners_ok(im) -> bool:
        a = np.array(im.convert("RGB")).astype(int)
        k = 6
        c = np.concatenate([a[:k, :k], a[:k, -k:], a[-k:, :k], a[-k:, -k:]])
        return bool(c.mean() >= 160)     # latar sel terang (~226)

    img = grab(box)
    clean = corners_ok(img)
    if not clean:                    # sisa tooltip -> tunggu hilang, ulangi
        time.sleep(0.45)
        img = grab(box)
        clean = corners_ok(img)
    return img, clean


def capture_baseline(cfg: dict) -> np.ndarray:
    """Baseline layar tanpa tooltip (kursor di titik aman)."""
    _park_cursor(cfg)
    return to_bgr(grab())


# --------------------------------------------------------- cek sejajar grid --
def _segments(mask, gap: int = 3):
    idx = np.where(mask)[0]
    if len(idx) == 0:
        return []
    segs, s, p = [], idx[0], idx[0]
    for x in idx[1:]:
        if x - p > gap:
            segs.append((int(s), int(p)))
            s = x
        p = x
    segs.append((int(s), int(p)))
    return segs


def detect_grid(rgb: np.ndarray, cfg: dict):
    """Deteksi ulang posisi sel dari piksel layar.
    -> (kolom, baris, err). kolom/baris = list pusat sel per sampel; None bila gagal."""
    g = cfg["grid"]
    cw, ch = g["w"] / g["cols"], g["h"] / g["rows"]
    bg = np.array([250, 250, 242])          # latar panel game
    tol = 6

    x0 = g["x"] - 80
    cols = []
    for r in (0, 2):                        # 2 garis horizontal di tengah sel
        y = int(g["y"] + (r + 0.5) * ch)
        line = rgb[y, x0:g["x"] + g["w"] + 80]
        segs = [s for s in _segments(np.abs(line - bg).sum(axis=1) > tol)
                if s[1] - s[0] > 80]        # lebar sel ~129px
        if len(segs) != g["cols"]:
            return None, None, (f"baris {r}: {len(segs)}/{g['cols']} kolom "
                                f"terdeteksi (sel kosong / panel berubah?)")
        cols.append([(s[0] + s[1]) / 2 + x0 for s in segs])

    y0 = g["y"] - 80
    rows = []
    for c in (0, 5):                        # 2 garis vertikal di tengah sel
        x = int(g["x"] + (c + 0.5) * cw)
        line = rgb[y0:g["y"] + g["h"] + 80, x]
        segs = [s for s in _segments(np.abs(line - bg).sum(axis=1) > tol)
                if s[1] - s[0] > 80]
        if len(segs) < g["rows"]:
            return None, None, (f"kolom {c}: cuma {len(segs)}/{g['rows']} baris "
                                f"terdeteksi (halaman belum rata?)")
        rows.append([(s[0] + s[1]) / 2 + y0 for s in segs[:g["rows"]]])
    return cols, rows, ""


def _screen_stable(a: np.ndarray, b: np.ndarray) -> bool:
    """True bila area panel tidak berubah (tooltip sudah hilang / tidak animasi)."""
    x, y, w, h = PANEL
    d = cv2.absdiff(a[y:y + h, x:x + w], b[y:y + h, x:x + w]).sum(axis=2)
    return float(d.mean()) < 1.5


def _park_cursor(cfg) -> None:
    """Pindahkan kursor ke titik aman sampai layar stabil (tooltip hilang)."""
    sc = cfg.get("safe_clear")
    if not sc:
        return
    for _ in range(4):
        move_to(sc["x"], sc["y"])
        time.sleep(0.30)
        a = to_bgr(grab())
        time.sleep(0.30)
        b = to_bgr(grab())
        if _screen_stable(a, b):
            return


def verify_grid(cfg: dict) -> tuple[str, str, float, float]:
    """-> (status, pesan, dx, dy)
       status: 'ok'    = sudah sejajar
               'auto'  = geser kecil -> caller boleh koreksi koordinat dgn dx,dy
               'fail'  = terlalu jauh / tidak terdeteksi -> harus digeser manual
    """
    _park_cursor(cfg)                     # buang tooltip dulu supaya tak menutup sel
    rgb = np.array(grab())
    cols, rows, err = detect_grid(rgb, cfg)
    if cols is None:
        return "fail", err or "grid tidak terdeteksi (game di depan layar?)", 0.0, 0.0
    g = cfg["grid"]
    cw, ch = g["w"] / g["cols"], g["h"] / g["rows"]
    exp_c = [g["x"] + (i + 0.5) * cw for i in range(g["cols"])]
    exp_r = [g["y"] + (i + 0.5) * ch for i in range(g["rows"])]
    dx = float(np.mean(np.mean(cols, axis=0) - np.array(exp_c)))
    dy = float(np.mean(np.mean(rows, axis=0) - np.array(exp_r)))
    tol = cfg["timing"].get("realign_tol_px", 8)
    max_drift = cfg["timing"].get("auto_realign_px", 45)   # 1/3 pitch cell
    msg = (f"geser dx={dx:+.1f}px dy={dy:+.1f}px "
           f"(toleransi {tol}px, batas auto {max_drift}px)")
    if abs(dx) <= tol and abs(dy) <= tol:
        return "ok", msg, dx, dy
    if abs(dx) <= max_drift and abs(dy) <= max_drift:
        return "auto", msg, dx, dy
    return "fail", msg + " -> terlalu jauh, geser ulang halaman sampai rata", dx, dy


# ------------------------------------------------ deteksi sel dari piksel --
def detect_cells(cfg: dict) -> tuple[list[dict], str]:
    """Bangun daftar sel langsung dari piksel layar (tanpa asumsi posisi config).
    Tahan terhadap sisa scroll apa pun: baris terpotong dibuang, kolom diambil
    dari baris paling penuh, sel kosong (slot akhir daftar) otomatis terlewat.
    -> (cells, pesan_gagal). cells=[] bila gagal."""
    g = cfg["grid"]
    _park_cursor(cfg)                       # tooltip harus hilang sebelum deteksi
    rgb = np.array(grab())
    bg = np.array([250, 250, 242])
    diff = np.abs(rgb.astype(np.int16) - bg).sum(axis=2) > 6

    pitch = g["h"] / g["rows"]
    # BATAS HARUS INTEGER: nilai float -> numpy melempar
    # "TypeError: slice must be integers or none or have an __index__ method"
    y_lo = int(max(0, g["y"] - 40))
    y_hi = int(min(rgb.shape[0], g["y"] + g["h"] + 130))
    x_lo = int(max(0, g["x"] - 60))
    x_hi = int(min(rgb.shape[1], g["x"] + g["w"] + 60))
    cw = g["w"] / g["cols"]

    # --- baris: sampling di SEMUA kolom (2 titik tiap sel, menghindari garis
    #     pemisah) -> satu baris tetap terbaca walau beberapa sel kosong atau
    #     satu kolom kena rail. Dulu cuma 3 kolom: bila satu baris kelewat,
    #     jarak antar baris jadi ~2x pitch dan validasi gagal terus.
    samples = sorted({int(g["x"] + (i + f) * cw)
                      for i in range(g["cols"]) for f in (0.35, 0.65)
                      if x_lo <= int(g["x"] + (i + f) * cw) < x_hi})
    if not samples:                              # grid di luar layar -> pakai tengah
        samples = [int((x_lo + x_hi) / 2)]
    min_h, max_h = pitch * 0.75, pitch * 1.06    # sebaris saja; kependekan =
                                                 # baris terpotong, kepanjangan =
                                                 # rail/garis pemisah (2 baris)
    found = []
    for x in samples:
        for s in _segments(diff[y_lo:y_hi, x]):
            h = s[1] - s[0] + 1
            if min_h <= h <= max_h:
                found.append((int(s[0]) + y_lo, int(s[1]) + y_lo))
    found.sort()
    rows, cur = [], None
    for s in found:                         # gabung yang berdekatan (toleransi 10px)
        if cur and abs(s[0] - cur[0]) <= 10:
            cur = (cur[0], max(cur[1], s[1]))
        else:
            if cur:
                rows.append(cur)
            cur = s
    if cur:
        rows.append(cur)
    rows = rows[: g["rows"]]
    if not rows:
        return [], "tidak ada baris sel terdeteksi (panel tutup / game tak di depan?)"

    # --- kolom: pakai baris yang paling banyak selnya sebagai referensi ---
    def hsegs(yc):
        segs = [(int(a) + x_lo, int(b) + x_lo)
                for a, b in _segments(diff[yc, x_lo:x_hi])]
        return [s for s in segs if s[1] - s[0] + 1 >= 100]

    ref = []
    for y0, y1 in rows:
        segs = hsegs((y0 + y1) // 2)
        if len(segs) > len(ref):
            ref = segs
    if not ref:
        return [], "kolom sel tidak terdeteksi"
    ref_c = [(a + b) / 2 for a, b in ref]

    # --- rakit sel (slot tanpa sel = akhir daftar -> dilewati) ---
    cells = []
    for ri, (y0, y1) in enumerate(rows):
        yc = (y0 + y1) // 2
        for xa, xb in hsegs(yc):
            cx = (xa + xb) / 2
            j = int(np.argmin([abs(cx - rc) for rc in ref_c]))
            if abs(cx - ref_c[j]) > 40:     # bukan sel grid -> abaikan
                continue
            cells.append({"r": ri, "c": j,
                          "x": float(xa), "y": float(y0),
                          "w": float(xb - xa + 1), "h": float(y1 - y0 + 1),
                          "cx": cx, "cy": float(yc)})
    if not cells:
        return [], "tidak ada sel terdeteksi"
    cells.sort(key=lambda c: (c["r"], c["c"]))
    nr = max(c["r"] for c in cells) + 1
    return cells, ""


# ------------------------------------------------------- validasi sel --
def validate_cells(cells: list[dict], cfg: dict, ref: tuple | None = None):
    """Tolak sel yang tidak sejajar SEBELUM hover/klik (cegah pick meleset).

    Cek: ukuran sel ~ pitch (bukan gabungan 2-4 baris), jarak baris & kolom
    ~ pitch, lalu cocokkan titik kiri-atas dengan patokan `ref` bila ada.

    -> (ok, pesan, rect_bbox)
       rect_bbox = (x, y, w, h) gabungan sel; jadi patokan penjajaran DAN
       dipakai untuk menyetel ulang asal kotak deteksi (snap).
    """
    if not cells:
        return False, "tidak ada sel terdeteksi", None
    g = cfg["grid"]
    pitch = g["h"] / g["rows"]

    bad = [c for c in cells
           if not (pitch * 0.72 <= c["h"] <= pitch * 1.06
                   and 90 <= c["w"] <= pitch * 1.06)]
    if bad:
        c = bad[0]
        return (False,
                f"ukuran sel tak wajar {c['w']:.0f}x{c['h']:.0f}px "
                f"(pitch {pitch:.0f}px) di {len(bad)} sel -> baris tercampur",
                None)

    x0 = int(min(c["x"] for c in cells))
    y0 = int(min(c["y"] for c in cells))
    x1 = int(max(c["x"] + c["w"] for c in cells))
    y1 = int(max(c["y"] + c["h"] for c in cells))
    rect = (x0 - 6, y0 - 6, (x1 - x0) + 12, (y1 - y0) + 12)

    ys = sorted({int(round(c["y"])) for c in cells})
    for a, b in zip(ys, ys[1:]):
        d = b - a
        if abs(d - pitch) > 14:
            k = round(d / pitch)
            if k >= 2 and abs(d - k * pitch) <= 14:
                return (False, f"{k - 1} baris tidak terdeteksi (baris terbaca "
                               f"di y={ys}, pitch {pitch:.0f}px) -> tekan "
                               "SESUAIKAN lalu LANJUT", rect)
            return (False, f"jarak baris {d}px (pitch {pitch:.0f}px, baris "
                           f"terbaca di y={ys}) -> grid belum rata", rect)
    xs = sorted({int(round(c["x"])) for c in cells})
    for a, b in zip(xs, xs[1:]):
        d = b - a
        if abs(d - pitch) > 14:
            return (False, f"jarak kolom {d}px (pitch {pitch:.0f}px) "
                           "-> grid belum rata", rect)

    # jumlah kolom/baris melebihi setting -> perbesar setting dari HUD
    if len(xs) > g["cols"]:
        return (False, f"terbaca {len(xs)} kolom, setting hanya {g['cols']} "
                       "-> tekan tombol KOL +", rect)
    if len(ys) > g["rows"]:
        return (False, f"terbaca {len(ys)} baris, setting hanya {g['rows']} "
                       "-> tekan tombol BARIS +", rect)

    if ref:
        # penjajaran dinilai MODULO pitch: konten yang bergeser tepat kelipatan
        # 1 baris tetap sah (lattice sel tidak berubah), yang ditolak hanya
        # geser pecahan baris (penyebab crop kepanjangan & pick meleset)
        dx, dy = x0 - ref[0], y0 - ref[1]
        mdx = dx - round(dx / pitch) * pitch
        mdy = dy - round(dy / pitch) * pitch
        if abs(mdx) > 14 or abs(mdy) > 14:
            return (False, f"belum sejajar kotak patokan "
                           f"({mdx:+.0f}px, {mdy:+.0f}px dari kelipatan "
                           f"{pitch:.0f}px) -> scroll lagi", rect)
    return True, "", rect


# ------------------------------------------------- setting grid (HUD) --
def grid_spec(g: dict) -> dict:
    """Setting grid -> dict yang diterima HUD untuk menggambar outline."""
    return {"x": int(g["x"]), "y": int(g["y"]), "w": float(g["w"]),
            "h": float(g["h"]), "cols": int(g["cols"]), "rows": int(g["rows"])}


def grid_base(g: dict) -> dict:
    """Cadangan setting ASLI (untuk tombol UKURAN NORMAL)."""
    return {"x": g["x"], "y": g["y"], "w": g["w"], "h": g["h"],
            "cols": g["cols"], "rows": g["rows"],
            "cw": g["w"] / max(1, g["cols"]), "pitch": g["h"] / max(1, g["rows"])}


def norm_grid(g: dict) -> dict:
    """Paksa tipe angka setting grid supaya aman dipakai sebagai index/slice.

    Sel hasil deteksi berbentuk float, jadi `cfg["grid"]["x"]` ikut menjadi
    float begitu kotak di-snap ke deteksi pertama. Nilai float itu lalu
    dipakai sebagai batas slicing numpy (`diff[y_lo:y_hi, x]`) dan PIL
    (`ImageGrab.grab(bbox=...)`) -> "TypeError: slice must be integers or
    none or have an __index__ method", dan karena pengecekan menangkap
    pengecualian itu, DETEKSI GAGAL TERUS walaupun grid sudah pas.

    Koordinat asal (x, y, w, h) disimpan bilangan bulat; pecahan hanya
    dipakai di tempat perhitungan (pitch/cw), bukan di indeks.
    """
    for k in ("x", "y", "w", "h"):
        if k in g:
            g[k] = int(round(float(g[k])))
    for k in ("cols", "rows"):
        if k in g:
            g[k] = max(1, int(g[k]))
    return g


def apply_grid_op(g: dict, op: dict, base: dict) -> None:
    """Terapkan permintaan tombol HUD (KOL±, BARIS±, SESUAIKAN, NORMAL).

    Pitch/cw dijaga tetap dari `base` supaya ukuran sel di layar tidak ikut
    berubah — yang berubah hanya asal kotak dan jumlah kolom/baris."""
    if op.get("normal"):
        for k in ("x", "y", "w", "h", "cols", "rows"):
            g[k] = base[k]
        norm_grid(g)
        return
    if "cols" in op:
        n = max(4, min(16, int(op["cols"])))
        g["cols"] = n
        g["w"] = round(n * base["cw"], 2)
    if "rows" in op:
        n = max(1, min(8, int(op["rows"])))
        g["rows"] = n
        g["h"] = round(n * base["pitch"], 2)
    norm_grid(g)                    # x/y/w/h wajib integer (indeks numpy/PIL)
    # op "fit" tidak mengubah angka: cukup memicu snap ulang di pemanggil


# ---------------------------------------------------- auto geser halaman --
def grid_strip(cfg) -> np.ndarray:
    """Abu-abu area grid (dikecilkan 4x) -> pembanding pergeseran konten."""
    g = cfg["grid"]
    box = (int(g["x"]), max(0, int(g["y"]) - 40),
           int(g["x"] + g["w"]), min(1080, int(g["y"] + g["h"]) + 130))
    im = grab(box).convert("L")
    im = im.resize((max(1, im.width // 4), max(1, im.height // 4)),
                   Image.BILINEAR)
    return np.asarray(im, dtype=np.float32)


def best_shift(old: np.ndarray, new: np.ndarray) -> float:
    """Estimasi pergeseran vertikal konten old->new dalam px layar (>0 = naik)."""
    h = min(old.shape[0], new.shape[0])
    old, new = old[:h], new[:h]
    limit = max(1, h - 40)
    best, bs = 1e18, 0
    for s in range(0, limit, 4):            # new[y] ~= old[y+s]
        d = float(np.abs(new[:h - s] - old[s:h]).mean())
        if d < best:
            best, bs = d, s
    return bs * 4.0                         # px layar asli


def scroll_step(cfg, notches: int = 2) -> None:
    """Kirim wheel di tengah grid -> konten naik, tunggu animasi selesai."""
    g = cfg["grid"]
    x = int(g["x"] + g["w"] / 2)
    y = int(g["y"] + g["h"] / 2)
    for _ in range(notches):
        wheel(x, y, -120)
        time.sleep(0.25)
    time.sleep(0.55)


def advance_page(cfg, min_px: float, max_steps: int = 16) -> tuple[bool, float]:
    """Geser konten sampai bergeser >= min_px (≈ 4 baris) atau daftar habis.
    -> (bergerak?, total_px). bergerak=False = konten tidak jalan -> sudah ujung."""
    prev = grid_strip(cfg)
    total = 0.0
    for _ in range(max_steps):
        if total >= min_px:
            break
        scroll_step(cfg)
        cur = grid_strip(cfg)
        s = best_shift(prev, cur)
        if s <= 8.0:                        # tidak bergerak -> ujung daftar
            return total > 0.0, total
        total += s
        prev = cur
    return total > 0.0, total


def scan_cell(cell, cfg, reader, args, page, names, official, name_to_id,
              skip_same=None, hook=None) -> dict:
    t = cfg["timing"]
    addr = cfg["_addr"]
    hook = hook or (lambda ev, d: None)
    rec = {"page": page, "row": cell["r"], "col": cell["c"],
           "cx": int(cell["cx"]), "cy": int(cell["cy"])}

    # 0) PASTIKAN TANPA TOOLTIP dulu -> baseline untuk deteksi diff
    baseline = capture_baseline(cfg)

    # 1) IKON diambil SEBELUM hover (tooltip bisa menutupi cell yang di-hover)
    icon_raw, icon_clean = crop_icon(cell, cfg)
    rec["icon_clean"] = icon_clean
    icon = extract_icon(icon_raw, cfg)
    rec["fp"] = icon_fp(icon)

    # 1b) slot ini sudah pernah ke-scan dengan isi ikon sama persis -> hemat
    if skip_same and skip_same((page, cell["r"], cell["c"]), rec["fp"]):
        rec["dup"] = True
        hook("track", {"cell": (cell["r"], cell["c"]), "icon": icon,
                       "phase": "slot ini sudah tersimpan"})
        return rec
    hook("track", {"cell": (cell["r"], cell["c"]), "icon": icon,
                   "phase": "melacak ikon block..."})

    # 1c) crop masih ketutup -> jangan diklik (cegah pick meleset)
    if not icon_clean:
        rec["pick_ok"] = False
        rec["skip_reason"] = "crop tidak bersih (sisa tooltip / sel tak sejajar)"
        hook("track", {"cell": (cell["r"], cell["c"]), "icon": icon,
                       "phase": "SEL TIDAK BERSIH -> TIDAK DIKLIK"})
        return rec

    # 2) HOVER -> tooltip -> OCR nama (ulangi sekali bila hasil OCR lemah)
    if not args.no_ocr:
        best_txt, best_raw = "", ""
        for attempt in range(2):
            move_to(jitter(cell["cx"]), jitter(cell["cy"]))
            tip_box, screen = wait_tooltip(baseline, t.get("tooltip_timeout_ms", 1500))
            if not tip_box:
                if attempt == 0:
                    rec["tooltip_found"] = False
                break
            rec["tooltip_found"] = True
            screen = Image.fromarray(cv2.cvtColor(screen, cv2.COLOR_BGR2RGB))
            dx, dy, w, h = TIP_NAME_BOX
            if args.save_crops:
                os.makedirs("output/debug", exist_ok=True)
                screen.crop((tip_box[0] + dx, tip_box[1] + dy,
                             tip_box[0] + dx + w, tip_box[1] + dy + h)).save(
                    "output/debug/name_p%dr%dc%d.png" % (page, cell["r"], cell["c"]))
            raw = ocr_name(tip_box, screen, cfg)
            txt = clean(raw)
            if _ocr_quality(txt, names) > _ocr_quality(best_txt, names):
                best_txt, best_raw = txt, raw
            if _ocr_quality(best_txt, names) >= 2:
                break                                   # sudah cocok nama resmi
            if attempt == 0:
                baseline = capture_baseline(cfg)        # parkir + baseline segar
        rec["name_ocr"] = best_txt
        rec["name_ocr_raw"] = best_raw
    hook("ocr", {"ocr": rec.get("name_ocr", ""),
                 "phase": "klik pick + baca ID di memori..."})

    if args.dry_run:
        rec["id"] = None
        rec["name_final"] = rec.get("name_ocr", "")
        return rec

    # 3) PICK + baca ID
    pick_id = None
    for _ in range(2):
        click(jitter(cell["cx"]), jitter(cell["cy"]))
        time.sleep(t["settle_ms"] / 1000)
        pick_id = reader.u32(addr)
        if pick_id:
            break
    rec["id"] = pick_id
    rec["pick_ok"] = bool(pick_id)

    # 4) CLEAR (kursor ke titik aman; baseline berikutnya diambil di awal sel)
    sc = cfg.get("safe_clear")
    if sc and pick_id:
        click(sc["x"], sc["y"])
        time.sleep(t["settle_ms"] / 1000)
        after = reader.u32(addr)
        rec["clear_ok"] = (after == 0)

    # 5) NAMA: index resmi > OCR
    ocr_clean = rec.get("name_ocr", "")
    matched, score = match_official(ocr_clean, names) if ocr_clean else ("", 0.0)
    rec["ocr_match"] = round(score, 3) if ocr_clean else None

    # sel terkunci: klik tidak mem-pick (id=0) -> tebak ID dari nama OCR
    if not pick_id:
        rec["locked"] = bool(rec.get("tooltip_found"))
        if matched:
            rec["id_guess"] = name_to_id.get(matched.lower())

    bid = pick_id or rec.get("id_guess") or -1
    off = official.get(bid, {}).get("name", "")
    rec["name_index"] = off
    rec["name_zh"] = official.get(bid, {}).get("zh", "")
    rec["name_final"] = off or matched or ocr_clean or ""
    if off and ocr_clean:
        rec["name_mismatch"] = (difflib.SequenceMatcher(
            None, off.lower(), clean(ocr_clean).lower()).ratio() < 0.78)

    # 6) simpan ikon dengan nama ber-ID
    p = icon_path(cfg["output"]["icons"], page, cell["r"], cell["c"], int(bid))
    icon.save(p)
    rec["icon"] = p
    hook("pick", {"bid": bid, "name": rec.get("name_final", ""),
                  "ocr": rec.get("name_ocr", ""),
                  "icon": icon,
                  "phase": ("ID terbaca" if pick_id else
                            "TERKUNCI - klik tidak bisa pick")})
    return rec


def scan_page(cfg, cells, page, reader, a, names, official, name_to_id,
              log, cat: str = "", ov=None, ex=None) -> tuple:
    """Scan satu set sel. -> (n_done, n_skip, n_fail, n_dirty, n_lock, n_dup)."""
    n_done = n_skip = n_fail = n_dirty = n_lock = n_dup = 0
    counts = {"done": 0, "dup": 0, "lock": 0, "fail": 0, "skip": 0,
              "page_done": 0, "page_total": len(cells)}
    recent: list[str] = []

    def hook(ev, d):
        if ov is None:
            return
        kw = dict(d)
        kw.update(page=page, cat=cat, counts=dict(counts),
                  recent=list(recent[-5:]))
        ov.set(**kw)

    def tally():
        counts["page_done"] = min(counts["page_total"],
                                  counts["page_done"] + 1)
        if ov is not None:
            ov.set(counts=dict(counts), recent=list(recent[-5:]))

    def note(rec):
        recent.append(f"{(rec.get('id') or rec.get('id_guess') or 0):<7} "
                      f"{(rec.get('name_final') or '')[:46]}")

    for i, cell in enumerate(cells, 1):
        if a.max_cells and n_done >= a.max_cells:
            break
        # alamat pick-id boleh diganti di tengah scan -> berlaku utk sel ini
        drain_mem_req(cfg, reader, ov, a.dry_run)
        if not CTRL.hold_if_paused():       # tombol JEDA / STOP dari HUD
            if ov is not None:
                ov.set(btn="stop", phase="STOP ditekan -> scan dihentikan")
            return n_done, n_skip, n_fail, n_dirty, n_lock, n_dup
        mark = f"[p{page} {cell['r']},{cell['c']}]"
        try:
            rec = scan_cell(cell, cfg, reader, a, page, names, official,
                            name_to_id, skip_same=log.skip_same, hook=hook)
        except Exception as e:                  # gangguan sesaat -> lanjut
            n_fail += 1
            counts["fail"] = n_fail
            print(f"{mark} ERROR {type(e).__name__}: {e}")
            tally()
            if n_fail >= 3:
                print("\n[!] 3 sel error berturut-turut -> berhenti (resume: "
                      "jalankan ulang)")
                return n_done, n_skip, n_fail, n_dirty, n_lock, n_dup
            continue
        if rec.get("dup"):                  # slot + isi ikon sama -> tidak ditulis
            n_skip += 1
            counts["skip"] = n_skip
            tally()
            continue
        if cat:
            rec["cat"] = cat
        bid = rec.get("id") or rec.get("id_guess")
        if not a.dry_run and bid and log.id_done(bid, rec.get("icon_clean")):
            # ID ini sudah tercatat -> buang catatan/icon ganda
            p = rec.get("icon")
            if p and p not in log.icon_paths and os.path.exists(p):
                os.remove(p)
            n_dup += 1
            counts["dup"] = n_dup
            note(rec)
            tally()
            continue
        log.write(rec)                      # FLUSH ke disk -> baru boleh scroll
        if ex and not a.dry_run:
            try:
                ex.add(rec)                 # ikon -> icon_webp/{id}.webp + entri
            except Exception as e:
                print(f"    [!] ekspor gagal: {e}")
        if a.dry_run:
            n_done += 1
            counts["done"] = n_done
            print(f"{mark} ocr={rec.get('name_ocr')!r}")
            tally()
            continue
        if not rec.get("pick_ok") and rec.get("locked"):
            n_lock += 1
            n_done += 1
            counts["lock"] = n_lock
            counts["done"] = n_done
            note(rec)
            print(f"{mark} TERKUNCI  id~{rec.get('id_guess', '?')} "
                  f"{rec['name_final']!r} (klik tidak bisa pick)")
            tally()
            continue
        if not rec.get("pick_ok"):
            n_fail += 1
            counts["fail"] = n_fail
            print(f"{mark} PICK GAGAL (id={rec.get('id')}) "
                  f"ocr={rec.get('name_ocr')!r}")
        else:
            n_done += 1
            counts["done"] = n_done
            note(rec)
            warn = "  [MISMATCH!]" if rec.get("name_mismatch") else ""
            if not rec.get("icon_clean"):
                n_dirty += 1
                warn += "  [IKON KOTOR]"
            print(f"{mark} id={rec['id']:<6} {rec['name_final']!r} "
                  f"clear={rec.get('clear_ok')} ocr={rec.get('name_ocr')!r}{warn}")
        tally()
        if n_fail >= 3:
            print("\n[!] 3 sel gagal berturut-turut -> JEDA, periksa layar "
                  "(LANJUT = lanjut, STOP = berhenti)")
            if ov is not None:
                ov.set(btn="pause",
                       phase="3 sel gagal berturut-turut — periksa layar dulu")
            CTRL.pause.set()
            if not CTRL.hold_if_paused():       # STOP ditekan
                if ov is not None:
                    ov.set(btn="stop", phase="STOP ditekan -> scan dihentikan")
                return n_done, n_skip, n_fail, n_dirty, n_lock, n_dup
            n_fail = 0
            counts["fail"] = 0
            capture_baseline(cfg)
    return n_done, n_skip, n_fail, n_dirty, n_lock, n_dup


def main() -> int:
    ap = argparse.ArgumentParser(description="Fase 2 scanner per halaman (10x4)")
    ap.add_argument("--page", type=int, default=1)
    ap.add_argument("--max-cells", type=int, default=0)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-ocr", action="store_true", help="lewati hover/OCR (cepat)")
    ap.add_argument("--save-crops", action="store_true")
    ap.add_argument("--index", default=INDEX)
    ap.add_argument("--no-focus", dest="focus", action="store_false", default=True)
    ap.add_argument("--verify", action="store_true",
                    help="hanya deteksi sel lalu keluar (pakai setelah geser halaman)")
    ap.add_argument("--auto", action="store_true", default=True,
                    help="(default) lanjut ke halaman berikutnya setelah tombol "
                         "LANJUT ditekan")
    ap.add_argument("--once", action="store_true",
                    help="berhenti setelah satu halaman (tanpa gerbang)")
    ap.add_argument("--auto-scroll", action="store_true",
                    help="geser halaman sendiri pakai roda mouse. DEFAULT MATI: "
                         "user scroll manual mengikuti outline lalu tekan LANJUT")
    ap.add_argument("--max-pages", type=int, default=0,
                    help="batas jumlah halaman (0 = tanpa batas)")
    ap.add_argument("--no-overlay", action="store_true",
                    help="matikan HUD, outline grid, dan tombol kontrol")
    ap.add_argument("--data", default=DATA_ROOT,
                    help=f"folder ekspor per kategori (default: {DATA_ROOT})")
    ap.add_argument("--export-only", action="store_true",
                    help="tidak scan: semua record log -> folder kategori "
                         "DATA (icon_webp + data_id)")
    ap.add_argument("--qc", action="store_true",
                    help="cek halaman saat ini: sel yang belum tercatat "
                         "(tanpa klik; pakai --page sesuai halaman tercatat)")
    ap.add_argument("--paths", action="store_true",
                    help="tampilkan semua lokasi data yang dipakai lalu keluar "
                         "(tanpa menyentuh game)")
    a = ap.parse_args()

    if a.paths:                       # diagnostik lokasi data (aman, tanpa game)
        try:
            jsonl = os.path.join(_BASE, load_config()["output"]["jsonl"])
        except Exception as e:
            jsonl = f"(config tidak terbaca: {e})"
        print("lokasi data yang dipakai aplikasi:")
        for label, p in (("_BASE (folder aplikasi)", _BASE),
                         ("config.json         ", CONFIG),
                         ("data/index.json     ", INDEX),
                         ("folder ekspor DATA  ", DATA_ROOT),
                         ("file log jsonl      ", jsonl),
                         ("folder sementara    ", TEMP_DIR),
                         ("tesseract.exe       ", TESSERACT)):
            mark = "ADA  " if (os.path.exists(p) and not str(p).startswith("(")) \
                else "TIDAK"
            print(f"  [{mark:>8}] {label}: {p}")
        print(f"  [   cwd  ] {os.getcwd()}")
        return 0

    if a.focus:
        from calibrate import focus_window
        focus_window("miniworld")

    cfg = load_config()
    norm_grid(cfg["grid"])          # config lama bisa berisi pecahan -> indeks
    cfg["_addr"] = int(cfg["mem"]["addr"], 0)
    official, name_to_id = load_index(a.index)
    names = [v["name"] for v in official.values() if v["name"]]

    # ---- mode 1: ekspor saja (tanpa sentuh game) ----
    if a.export_only:
        log = Log(cfg["output"]["jsonl"])
        ex = Exporter(a.data, index=official)
        n = ni = no_cat = 0
        for rec in log.recs:
            cat = rec.get("cat") or ""
            if not cat:
                no_cat += 1
                continue
            ex.set_category(cat)
            n += 1
            try:
                if ex.add(rec):
                    ni += 1
            except Exception as e:
                print(f"[!] ekspor id={rec.get('id')}: {e}")
        ex.flush()
        log.close()
        print(f"ekspor : {n} record -> {ni} ikon webp "
              f"({no_cat} dilewati: tanpa kategori)")
        print(f"root   : {ex.root}")
        return 0 if n else 2

    cells, err = detect_cells(cfg)
    if a.verify:
        if not cells:
            print(f"VERIFY GAGAL: {err}")
            return 2
        rows = sorted({c["r"] for c in cells})
        print(f"VERIFY OK: {len(cells)} sel di {len(rows)} baris, "
              f"kolom={sorted({c['c'] for c in cells})}")
        return 0

    # ---- mode 2: QC halaman (tanpa klik) -> apa masih ada sel bolong? ----
    if a.qc:
        if not cells:
            print(f"QC GAGAL: {err}")
            return 2
        log = Log(cfg["output"]["jsonl"])
        ok = errs = 0
        miss = []
        for cell in cells:
            try:
                raw, _clean = crop_icon(cell, cfg)
                fp = icon_fp(extract_icon(raw, cfg))
            except Exception as e:
                errs += 1
                print(f"  [!] r{cell['r']}c{cell['c']}: {e}")
                continue
            if log.skip_same((a.page, cell["r"], cell["c"]), fp):
                ok += 1
            else:
                miss.append((cell["r"], cell["c"]))
        log.close()
        print(f"QC halaman {a.page}: {ok}/{len(cells)} sel sudah tersimpan, "
              f"{len(miss)} BELUM, {errs} gagal baca")
        if miss:
            print(f"  sel bolong : {miss}")
            print(f"  -> scan dulu : python scan.py --page {a.page}")
            return 1
        print("  -> bersih, halaman ini aman di-scroll")
        return 0

    if not cells:
        sys.exit(f"[!] {err}")

    reader = None
    if not a.dry_run:
        pid = find_pid(cfg.get("process_hint"))
        reader = MemReader(pid)
        print(f"proses pid={pid} ({process_name(pid)}) addr={cfg['mem']['addr']} "
              f"-> {module_of(pid, cfg['_addr'])} | baseline memori = "
              f"{reader.u32(cfg['_addr'])}")

    log = Log(cfg["output"]["jsonl"])
    ov = Overlay(enabled=not a.no_overlay, ctrl=CTRL)
    ov.set(mem_addr=cfg["mem"]["addr"],
           mem_msg="alamat aktif - ketik lalu SET", mem_fg=HUD_MUTED)
    push_mem(cfg, reader, ov)
    ex = Exporter(a.data, index=official)
    T = tot_done = tot_skip = tot_fail = tot_dirty = tot_lock = tot_dup = 0
    page = a.page
    pitch = cfg["grid"]["h"] / cfg["grid"]["rows"]
    cat_prev = "Uncategorized"
    folder_prev: str | None = None
    ref_rect = None                    # kotak patokan penjajaran (bbox sel sah)
    base = grid_base(cfg["grid"])      # setting asli -> tombol UKURAN NORMAL
    ov.set_grid(grid_spec(cfg["grid"]))

    def push_grid() -> None:
        """Kirim setting grid terbaru ke HUD supaya outline ikut berubah."""
        ov.set_grid(grid_spec(cfg["grid"]))

    def grid_policy(scanning: bool) -> None:
        """Outline tampil terus selama WDA sukses; kalau gagal, hanya saat berhenti
        (supaya tidak pernah ikut terekam saat capture)."""
        if ov is not None:
            ov.show_grid((not scanning) or ov.excluded)

    def drain_grid() -> bool:
        """Terapkan permintaan setting grid (KOL/BARIS/SESUAIKAN/NORMAL) dari HUD.
        -> True bila ada permintaan yang diproses."""
        nonlocal ref_rect
        op = CTRL.take_grid()
        if not op:
            return False
        apply_grid_op(cfg["grid"], op, base)
        if op.get("fit") or op.get("normal"):
            ref_rect = None                     # boleh snap ulang ke grid baru
        return True

    def detect_and_check():
        """Deteksi sel + validasi. -> (cells, ok, pesan, rect)."""
        nonlocal ref_rect
        try:
            cs, er = detect_cells(cfg)
        except Exception as e:                  # layar tak terbaca
            cs, er = [], f"{type(e).__name__}: {e}"
        o, m, r = (False, er, None)
        if cs:
            o, m, r = validate_cells(cs, cfg, ref_rect)
            if o and ref_rect is None:
                ref_rect = r                    # patokan resmi = deteksi sah
                # sejajarkan asal kotak deteksi dengan grid yang benar ada
                # (r[] dari sel float -> wajib dibulatkan, kalau tidak deteksi
                #  berikutnya melempar TypeError di slicing numpy)
                cfg["grid"]["x"] = r[0] + 6
                cfg["grid"]["y"] = r[1] + 6
                norm_grid(cfg["grid"])
                push_grid()
        return cs, o, m, r

    def gate_tick() -> None:
        """Selagi menunggu tombol: proses permintaan dari HUD (alamat pick-id
        + setting grid) dan perbarui bacaan memori di kolom pembaca."""
        drain_mem_req(cfg, reader, ov, a.dry_run)
        push_mem(cfg, reader, ov)
        if not drain_grid():
            return
        cells2, ok2, msg2, _ = detect_and_check()
        push_grid()
        grid_policy(scanning=False)
        head = f"Setting grid {cfg['grid']['cols']}x{cfg['grid']['rows']}"
        if ok2:
            print(f"[grid] {head} -> {len(cells2)} sel valid")
            ov.set(phase=f"{head}: {len(cells2)} sel valid — scroll bila perlu, "
                         "lalu tekan LANJUT", btn="gate")
        else:
            print(f"[grid] {head} -> {msg2}")
            ov.set(phase=f"{head}: {msg2}", btn="gate")

    try:
        while not CTRL.stop.is_set():
            # ------------------------------------------------ deteksi sel --
            drain_mem_req(cfg, reader, ov, a.dry_run)   # alamat dari HUD
            if drain_grid():                 # setting grid diubah saat scanning
                push_grid()
            cells, ok, msg, rect = detect_and_check()
            grid_policy(scanning=False)

            # ---------------------------------- belum sejajar -> tunggu user --
            if not ok:
                pesan = f"GRID BELUM SEJAJAR: {msg}"
                print(f"[!] {pesan}")
                print("    geser isi list sampai baris masuk kotak outline, "
                      "lalu tekan LANJUT (tombol KOL/BARIS bila grid bukan 10x4)")
                ov.set(phase=pesan, btn="gate")
                if not CTRL.wait_gate(on_tick=gate_tick):
                    break
                continue                         # deteksi ulang, halaman sama

            # ------------------------------------------- kategori (breadcrumb) --
            cat_raw = read_category(cfg) or cat_prev
            berubah = ex.set_category(cat_raw)      # normalisasi + buat folder
            cat = ex.crumb or cat_raw
            if berubah:
                baru = folder_prev is not None and ex.folder != folder_prev
                folder_prev, cat_prev = ex.folder, cat
                if baru:
                    print(f"--- KATEGORI BARU: {cat}")
                    print(f"    icon_webp : {ex.icon_dir}")
                    print(f"    data_id   : {ex.data_dir}")
                    ov.set(cat=cat, phase=f"folder baru dibuat: {ex.folder}")
                    time.sleep(1.5)                 # berhenti sejenak
                else:
                    print(f"--- kategori: {cat}")
            ov.set(cat=cat)

            print(f"--- halaman {page}: {len(cells)} sel terdeteksi "
                  f"({max(c['r'] for c in cells) + 1} baris) | {cat}")

            # -------------------------------------------------- scan halaman --
            grid_policy(scanning=True)
            ov.set(btn="scanning", phase=f"scan halaman {page}…")
            f = 0
            for attempt in (1, 2):                  # retry bila ada yang gagal
                d, s, f, di, l, du = scan_page(
                    cfg, cells, page, reader, a, names, official, name_to_id,
                    log, cat, ov=ov, ex=ex)
                tot_done += d; tot_skip += s; tot_fail += f
                tot_dirty += di; tot_lock += l; tot_dup += du
                if not f or CTRL.stop.is_set():
                    break
                print(f"    [!] {f} sel belum tersimpan -> ulangi "
                      f"(percobaan {attempt}/2)")
            if CTRL.stop.is_set():
                break
            if f:
                # syarat: TIDAK boleh lanjut sebelum semua sel tersimpan
                print(f"\n[!] {f} sel belum tersimpan -> TIDAK lanjut. "
                      "Tekan LANJUT untuk mengulang halaman ini, STOP untuk keluar.")
                ov.set(btn="gate",
                       phase=f"{f} SEL BELUM TERSIMPAN — tekan LANJUT untuk "
                             "ulang, STOP untuk keluar")
                if not CTRL.wait_gate(on_tick=gate_tick):
                    break
                continue

            ex.flush()                              # data_id/entries.json ikut
            ov.set(counts={"done": tot_done, "dup": tot_dup, "lock": tot_lock,
                           "fail": tot_fail, "skip": tot_skip,
                           "page_done": len(cells), "page_total": len(cells)})
            if a.dry_run and a.max_cells and tot_done >= a.max_cells:
                break
            if a.once:
                print("--- --once: berhenti setelah 1 halaman ---")
                break
            T += 1
            if a.max_pages and T >= a.max_pages:
                print(f"--- batas --max-pages {a.max_pages} tercapai ---")
                break

            # -------------------------------------------- geser halaman --
            if a.auto_scroll:                       # mode lama (opsional)
                try:
                    moved, px = advance_page(cfg, pitch * 4)   # ≈ 4 baris baru
                except Exception as e:
                    print(f"[!] gagal geser halaman: {e}")
                    break
                if not moved:
                    print(">>> konten tidak bergerak -> daftar habis")
                    break
                print(f"    geser {px:.0f}px ({px / pitch:.1f} baris)")
                page += 1
                continue

            # ---- GERBANG MANUAL: outline + tombol, scroll dikerjakan user ----
            push_grid()
            grid_policy(scanning=False)
            ov.set(btn="gate",
                   phase=f"HALAMAN {page} SELESAI — scroll manual sampai baris "
                         f"baru masuk kotak, lalu tekan LANJUT (STOP = berhenti)")
            print(f"--- halaman {page} SELESAI. Scroll MANUAL sampai baris baru "
                  f"sejajar kotak outline, lalu tekan LANJUT (STOP = berhenti)")
            if not CTRL.wait_gate(on_tick=gate_tick):
                break
            page += 1
    except KeyboardInterrupt:
        print("\n[diinterupsi user]")
    finally:
        if reader:
            reader.close()
        log.close()
        try:
            ex.close()
        except Exception as e:
            print(f"[!] flush ekspor: {e}")
        ov.close()

    print(f"\nselesai: {tot_done} discan ({tot_lock} terkunci), {tot_skip} dilewati "
          f"(slot sama), {tot_dup} id sudah ada, {tot_fail} gagal, "
          f"{tot_dirty} ikon kotor")
    if ex.folder:
        print(f">>> ekspor : {ex.folder}")
        print(f"            icon_webp ({ex.n_icon} file) + data_id\\entries.json")
        print(f">>> manifest: {os.path.join(ex.root, 'manifest.json')}")
    if not a.auto_scroll:
        print(">>> scroll manual: geser library mengikuti kotak outline, "
              "lalu jalankan ulang bila perlu (resume otomatis)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
