#!/usr/bin/env python3
"""Ekspor database lokal (folder DATA\\) menjadi situs statis di <repo>\\data\\.

Dipakai untuk menyalin isi database yang berjalan di localhost (server.py)
kepada situs LIVE di Vercel. Hasilnya:

    data/db.json         payload yang dibaca index.html  ({meta, entries})
    data/index.json      format situs — sumber nama untuk pipeline translate
                         dan pemetaan id -> posisi (dipakai server.py)
    data/lang/*.json     nama per bahasa, selaras urutan data/index.json
                         dan data/db.json (keduanya sengaja diurutkan sama)
    data/icons/<indu>/<kategori>/<id>.webp

Catatan:
  * data/ LAMA (situs Vercel sebelumnya) sudah dipindah ke data_old/ dan tetap
    dipertahankan sebagai cadangan sekaligus sumber terjemahan awal.
  * Tidak perlu server berjalan — script ini membaca folder DATA\\ langsung.
  * Jalankan ulang setiap kali database berubah, lalu commit:

        python tools/local-db/export_live.py

Seluruh artefak tetap di drive D: (tidak ada yang menulis ke C:).
"""

from __future__ import annotations

import json
import os
import re
import shutil
import sys
from datetime import date
from pathlib import Path
from urllib.parse import quote, unquote

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]                       # root repo Miniworld-DB
sys.path.insert(0, str(HERE))

import server  # noqa: E402  — aman: modul tidak menjalankan server saat import

OUT = REPO / "data"          # tujuan ekspor (situs LIVE)
OLD = REPO / "data_old"       # cadangan data situs lama
API_ICON = "/api/icon/"


def write_json(path: Path, obj) -> None:
    """Tulis atomik dengan format yang sama dengan server.py (indent=1)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, path)


# ------------------------------------------------------------------ ikon ---

def export_icons(entries: list[dict]) -> tuple[int, set]:
    """Salin ikon tiap entri ke data/icons/<indu>/<kategori>/<id>.webp.

    Path ikon pada entri ikut diganti menjadi path statis (relatif terhadap
    index.html di root repo) supaya bisa dipakai langsung oleh situs Vercel.
    """
    n = 0
    expected: set[Path] = set()
    for e in entries:
        p = e.get("p")
        if not p:
            continue
        rest = unquote(p[len(API_ICON):]) if p.startswith(API_ICON) else ""
        if "/" not in rest:
            e.pop("p", None)
            continue
        cat, fname = rest.rsplit("/", 1)
        folder = server.cat_dir(cat)
        src = (folder / "icon_webp" / fname) if folder else None
        if src is None or not src.is_file():
            e.pop("p", None)
            continue

        dst = OUT / "icons" / Path(*cat.split("/")) / fname
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        expected.add(dst.resolve())
        e["p"] = "data/icons/" + quote(cat, safe="/") + "/" + fname
        n += 1

    # buang ikon yatim (entri sudah dihapus dari DATA tapi filenya masih ada)
    buang = 0
    if (OUT / "icons").is_dir():
        for f in (OUT / "icons").rglob("*.webp"):
            if f.resolve() not in expected:
                f.unlink()
                buang += 1
                if not any(f.parent.iterdir()):
                    f.parent.rmdir()
    if buang:
        print(f"  ikon yatim dibuang : {buang}")
    return n, expected


# ------------------------------------------------------------ situs format --

def site_entry(e: dict) -> dict:
    """Entri gaya index.json situs: hanya field yang ada, tanpa None."""
    out = {}
    for k in ("i", "c", "s", "l", "z", "e", "p"):
        v = e.get(k)
        if v is not None and v != "":
            out[k] = v
    return out


def build_index(entries: list[dict], meta: dict) -> dict:
    sumber = []
    if (OLD / "index.json").is_file():
        try:
            sumber = json.loads((OLD / "index.json").read_text(encoding="utf-8")) \
                .get("meta", {}).get("sources") or []
        except Exception:                        # noqa: BLE001
            sumber = []
    return {
        "meta": {
            "generated": meta.get("generated") or date.today().isoformat(),
            "total": len(entries),
            "named": sum(1 for e in entries if e.get("e") or e.get("z")),
            "withIcon": sum(1 for e in entries if e.get("p")),
            "categories": [
                {"key": c["key"], "label": c["label"],
                 "count": c["count"], "withIcon": c["withIcon"]}
                for c in meta.get("categories") or []
            ],
            "parents": [
                {"key": p["key"], "count": p["count"], "withIcon": p["withIcon"]}
                for p in meta.get("parents") or []
            ],
            "sources": sumber,
        },
        "entries": [site_entry(e) for e in entries],
    }


# ------------------------------------------------------------- terjemahan ---

def export_langs(entries: list[dict]) -> list[str]:
    """Bangun ulang data/lang/*.json selaras urutan entries + sig baru.

    Sumber terjemahan: data/lang bila sudah ada (sudah termasuk hasil rename
    dari tombol UBAH), selain itu data_old/lang (cadangan data situs lama).
    Keduanya dipasangkan dengan index.json yang sepadan supaya posisi `n`
    bisa dipetakan lewat id.
    """
    src = None
    for base in (OUT, OLD):
        if (base / "index.json").is_file() and (base / "lang").is_dir():
            src = base
            break
    if src is None:
        print("  [!] sumber terjemahan tidak ditemukan — data/lang dilewati")
        return []

    src_idx = json.loads((src / "index.json").read_text(encoding="utf-8"))
    src_ids = [e["i"] for e in src_idx.get("entries") or []]
    sig = server.js_sig(entries)
    hasil: list[str] = []

    # buang berkas bahasa yang sudah tidak ada di sumber (mis. en/zh tak dipakai)
    punya = set()
    for f in sorted((src / "lang").glob("*.json")):
        try:
            raw = json.loads(f.read_text(encoding="utf-8"))
        except Exception as ex:                  # noqa: BLE001
            print(f"  [!] {f.name} gagal dibaca: {ex}")
            continue
        n_src = raw.get("n") or []
        by_id = {src_ids[k]: v for k, v in enumerate(n_src) if k < len(src_ids)}
        write_json(OUT / "lang" / f.name, {
            "code": raw.get("code") or f.stem,
            "label": raw.get("label") or f.stem,
            "n": [by_id.get(e["i"]) for e in entries],
            "sig": sig,
        })
        punya.add(f.name)
        hasil.append(f.stem)

    if (OUT / "lang").is_dir():
        for f in (OUT / "lang").glob("*.json"):
            if f.name not in punya:
                f.unlink()
    return hasil


# ------------------------------------------------------------ keterangan ----

def tanggal_live() -> str:
    """Tulis tanggal ekspor ke kunci `db.updated` di semua kamus i18n.

    Keterangan "database update terakhir ..." harus selalu mengikuti ekspor
    terakhir, jadi tanggalnya diperbarui di sini (hanya baris `db.updated`).
    """
    tgl = date.today().strftime("%d/%m/%Y")
    pat_tgl = re.compile(r"\d{2}/\d{2}/\d{4}")
    total = 0
    for nama in ("i18n.js", "i18n-more.js"):
        f = REPO / nama
        if not f.is_file():
            continue
        teks = f.read_bytes().decode("utf-8")
        nl = "\r\n" if "\r\n" in teks else "\n"       # hormati akhir baris asli
        baris = teks.split(nl)
        n = 0
        for i, b in enumerate(baris):
            if '"db.updated"' not in b:
                continue
            if not pat_tgl.search(b):
                print(f"  [!] {nama}: baris db.updated tanpa tanggal")
                continue
            baru = pat_tgl.sub(tgl, b)
            if baru != b:
                baris[i] = baru
                n += 1
        if n:
            f.write_bytes(nl.join(baris).encode("utf-8"))
        print(f"  keterangan {nama}: {n} kunci -> {tgl}")
        total += n
    return tgl


# ------------------------------------------------------------------- main ---

def main() -> int:
    print("=" * 62)
    print("  Ekspor database lokal -> situs LIVE")
    print(f"  sumber : {server.ROOT}")
    print(f"  tujuan : {OUT}")
    print("=" * 62)

    if not server.ROOT.is_dir():
        print(f"[!] folder database tidak ditemukan: {server.ROOT}")
        return 1

    db = server.load_db()
    entries = db["entries"]
    meta = dict(db["meta"])
    meta.pop("root", None)          # jangan bocorkan path lokal ke situs

    n_icon, _ = export_icons(entries)
    meta["withIcon"] = sum(1 for e in entries if e.get("p"))
    meta["total"] = len(entries)
    meta["named"] = sum(1 for e in entries if e.get("e") or e.get("z"))
    meta["sig"] = server.js_sig(entries)

    OUT.mkdir(parents=True, exist_ok=True)
    write_json(OUT / "db.json", {"meta": meta, "entries": entries})
    write_json(OUT / "index.json", build_index(entries, meta))
    bahasa = export_langs(entries)
    tanggal_live()

    print("-" * 62)
    print(f"  entri    : {meta['total']}")
    print(f"  berikon  : {n_icon}")
    print(f"  kategori : {len(meta.get('categories') or [])} "
          f"({len(meta.get('parents') or [])} cabang)")
    print(f"  bahasa   : {', '.join(bahasa) or '-'}")
    print(f"  sig      : {meta['sig']}")
    print(f"  ukuran   : "
          f"{sum(f.stat().st_size for f in OUT.rglob('*') if f.is_file()) / 1048576:.1f} MB")
    print("=" * 62)
    print("  Selesai. Selanjutnya: git add -A && git commit && git push")
    return 0


if __name__ == "__main__":
    sys.exit(main())
