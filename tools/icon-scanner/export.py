#!/usr/bin/env python3
"""Ekspor hasil scan ke struktur folder per kategori (siap import website).

    D:\\WORK\\MINI WORLD DB\\DATA\\Blocks\\Terrain\\
        icon_webp\\100.webp         ikon transparan (WebP, alpha)
        data_id\\entries.json       data ID siap merge ke data/index.json

Breadcrumb game "Blocks > Terrain" -> folder DATA\\Blocks\\Terrain.
Saat kategori berubah, file lama di-flush dulu, folder baru dibuat, lalu scan
dilanjutkan (dipanggil scan.py sebelum scroll lanjut).
"""
from __future__ import annotations

import difflib
import json
import os
import re
from datetime import datetime

from PIL import Image

DATA_ROOT = r"D:\WORK\MINI WORLD DB\DATA"
# kategori index website: blocks / creature / gameplay / items
CAT_KEY = {"blocks": "blocks", "items": "items", "creature": "creature",
           "gameplay": "gameplay"}


def safe_name(s: str) -> str:
    """Bersihkan nama folder dari karakter terlarang Windows."""
    s = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", s or "").strip(" .")
    return s or "Tanpa Nama"


def lev(a: str, b: str) -> int:
    """Jarak edit sederhana (Levenshtein) untuk normalisasi OCR."""
    a, b = a.lower(), b.lower()
    if a == b:
        return 0
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1,
                           prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


class Exporter:
    def __init__(self, root: str = DATA_ROOT, index: dict | None = None):
        self.root = root
        self.index = index or {}          # id -> entri lama (untuk lengkapi CN)
        self.crumb = ""
        self.folder: str | None = None
        self.leaf = ""
        self.entries: list[dict] = []
        self._known: list[str] = []       # breadcrumb yang sudah pernah dipakai
        os.makedirs(self.root, exist_ok=True)
        self._scan_known()

    # ------------------------------------------------ normalisasi OCR ---
    def _scan_known(self) -> None:
        """Kumpulkan breadcrumb dari folder yang sudah ada di root."""
        for dirpath, _dirs, files in os.walk(self.root):
            if os.path.basename(dirpath) != "data_id":
                continue
            p = os.path.join(dirpath, "entries.json")
            if not os.path.exists(p):
                continue
            try:
                with open(p, encoding="utf-8") as f:
                    crumb = json.load(f).get("breadcrumb", "")
            except Exception:
                continue
            if crumb and crumb not in self._known:
                self._known.append(crumb)

    @staticmethod
    def _segs(crumb: str) -> list[str]:
        return [" ".join(s.split()) for s in (crumb or "").split(">") if s.strip()]

    def _normalize(self, crumb: str) -> str:
        """Samakan ejaan OCR dengan kategori yang sudah ada.

        Game menulis 'Blocks > Terrian' padahal data lama 'Blocks > Terrain'
        -> tanpa normalisasi folder jadi terpecah dua.
        """
        segs = self._segs(crumb)
        if not segs:
            return ""
        pool = {s for k in self._known for s in self._segs(k)}
        if not pool:
            return " > ".join(segs)
        out = []
        for s in segs:
            best, bd = s, 99
            for cand in pool:
                if len(cand) < 4:
                    continue
                d = lev(s, cand)
                if d < bd:
                    best, bd = cand, d
            # toleransi 2 typo utk nama >= 5 huruf, 1 utk sisanya
            tol = 2 if len(s) >= 5 else 1
            out.append(best if bd <= tol else s)
        return " > ".join(out)

    # -------------------------------------------------------- kategori --
    @property
    def icon_dir(self) -> str | None:
        return os.path.join(self.folder, "icon_webp") if self.folder else None

    @property
    def data_dir(self) -> str | None:
        return os.path.join(self.folder, "data_id") if self.folder else None

    def set_category(self, crumb: str) -> bool:
        """Ganti kategori dari breadcrumb 'Blocks > Terrain'.
        -> True = kategori berubah (folder baru dibuat, muat entri lama)."""
        crumb = self._normalize(" ".join((crumb or "").split()))
        if not crumb or crumb == self.crumb:
            return False
        self.flush()
        parts = [safe_name(p) for p in self._segs(crumb)]
        if not parts:
            return False
        self.folder = os.path.join(self.root, *parts)
        self.leaf = parts[-1]
        os.makedirs(self.icon_dir, exist_ok=True)
        os.makedirs(self.data_dir, exist_ok=True)
        self.entries = self._load()
        self.crumb = " > ".join(parts)
        if self.crumb not in self._known:
            self._known.append(self.crumb)
        return True

    @property
    def n_icon(self) -> int:
        return sum(1 for e in self.entries if e.get("p"))

    def _data_path(self) -> str:
        return os.path.join(self.data_dir, "entries.json")

    def _load(self) -> list[dict]:
        p = self._data_path()
        if not os.path.exists(p):
            return []
        try:
            with open(p, encoding="utf-8") as f:
                return list(json.load(f).get("entries", []))
        except Exception:
            return []

    # ----------------------------------------------------------- tambah --
    def add(self, rec: dict) -> str | None:
        """Simpan 1 blok: ikon -> icon_webp/{id}.webp + entri data.
        -> path webp (None bila tidak ada id / ikon)."""
        if not self.folder:
            return None
        bid = rec.get("id") or rec.get("id_guess")
        if not bid:
            return None
        bid = int(bid)
        src = rec.get("icon")
        out = None
        if src and os.path.exists(src):
            out = os.path.join(self.icon_dir, f"{bid}.webp")
            try:
                with Image.open(src) as im:
                    im.convert("RGBA").save(out, "WEBP", quality=92, method=6)
            except Exception as e:
                print(f"    [!] gagal tulis webp {bid}: {e}")
                out = None

        old = next((e for e in self.entries if e.get("i") == bid), None)
        entri = dict(old) if old else {}
        # nama resmi dari index website > nama hasil scan
        off = self.index.get(bid) or {}
        entri.update({
            "i": bid,
            "c": CAT_KEY.get(self.crumb.split(">")[0].strip().lower(), "blocks"),
            # l & s harus tetap berpasangan seperti index resmi (s = CN, l = EN)
            "l": off.get("l") or self.leaf,
            "s": off.get("s") or entri.get("s"),
            "cat": self.crumb,                 # kategori asli di library game
            "e": off.get("name") or rec.get("name_final") or "",
            "z": off.get("zh") or entri.get("z") or "",
            "ocr": rec.get("name_ocr") or entri.get("ocr") or "",
            "locked": bool(rec.get("locked")),
        })
        if out:
            entri["p"] = f"icon_webp/{bid}.webp"
            entri["wp"] = f"data/{entri['c']}/icons_cache/{bid}.webp"
            entri["_icon"] = True
        if old:
            old.clear()
            old.update(entri)
        else:
            self.entries.append(entri)
        return out

    # ------------------------------------------------------------ simpan --
    def flush(self) -> None:
        """Tulis data_id/entries.json + manifest (panggil sebelum ganti kategori)."""
        if not self.folder:
            return
        data = {
            "breadcrumb": self.crumb,
            "category": [p for p in self.crumb.split(">")],
            "generated": datetime.now().isoformat(timespec="seconds"),
            "total": len(self.entries),
            "withIcon": sum(1 for e in self.entries if e.get("p")),
            "entries": [{k: v for k, v in e.items() if not k.startswith("_")}
                        for e in sorted(self.entries, key=lambda x: x.get("i", 0))],
        }
        try:
            with open(self._data_path(), "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=1)
            self._manifest()
        except Exception as e:
            print(f"    [!] gagal tulis data_id: {e}")

    def _manifest(self) -> None:
        """Indeks semua kategori yang sudah diekspor (untuk import website)."""
        cats = []
        for dirpath, _dirnames, filenames in os.walk(self.root):
            if os.path.basename(dirpath) != "data_id":
                continue
            p = os.path.join(dirpath, "entries.json")
            if not os.path.exists(p):
                continue
            try:
                with open(p, encoding="utf-8") as f:
                    d = json.load(f)
            except Exception:
                continue
            rel = os.path.relpath(os.path.dirname(dirpath), self.root)
            cats.append({
                "path": rel.replace("\\", "/"),
                "breadcrumb": d.get("breadcrumb", ""),
                "total": d.get("total", 0),
                "withIcon": d.get("withIcon", 0),
                "generated": d.get("generated", ""),
            })
        cats.sort(key=lambda c: c["path"])
        man = {
            "root": self.root,
            "generated": datetime.now().isoformat(timespec="seconds"),
            "categories": cats,
            "totals": {
                "categories": len(cats),
                "entries": sum(c["total"] for c in cats),
                "icons": sum(c["withIcon"] for c in cats),
            },
        }
        with open(os.path.join(self.root, "manifest.json"), "w",
                  encoding="utf-8") as f:
            json.dump(man, f, ensure_ascii=False, indent=1)

    def close(self) -> None:
        self.flush()
