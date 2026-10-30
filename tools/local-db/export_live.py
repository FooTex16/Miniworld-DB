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
  * Ekspor MENGGABUNGKAN suntingan admin di situs LIVE (nama, no urut, entri
    terhapus, urutan sub kategori) supaya koreksi dari halaman tidak tertimpa.
    Lihat fungsi gabung_situs() untuk aturannya dan cara melepas kuncinya.
  * Jalankan ulang setiap kali database berubah, lalu commit:

        python tools/local-db/export_live.py

Seluruh artefak tetap di drive D: (tidak ada yang menulis ke C:).
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
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

def export_langs(entries: list[dict], id_lama: list | None = None) -> list[str]:
    """Bangun ulang data/lang/*.json selaras urutan entries + sig baru.

    Sumber terjemahan: data/lang bila sudah ada (sudah termasuk hasil rename
    dari tombol UBAH), selain itu data_old/lang (cadangan data situs lama).

    Pasangan `id -> nama` harus memakai URUTAN LAMA (`id_lama`), yaitu isi
    index.json sebelum ekspor ini menimpanya. Kalau dipakai index.json yang
    sudah baru, entri yang terhapus di tengah membuat seluruh nama di belakangnya
    bergeser satu per sepanjang 6 berkas bahasa — dan itu tidak terlihat sampai
    nama asing muncul pada block yang salah.
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
    src_ids = id_lama if (id_lama and src is OUT) else \
        [e["i"] for e in src_idx.get("entries") or []]
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


# ------------------------------------------------------- suntingan situs ---

def baca_situs(timeout: int = 40) -> dict | None:
    """Ambil `data/db.json` yang kini terpasang di situs (commit terakhir).

    Situs LIVE punya editor sendiri (lihat api/*.js): admin bisa mengubah nama,
    no urut, menghapus entri, dan menyusun sub kategori langsung di halaman.
    Semua perubahannya disimpan sebagai commit di repo ini, jadi sumbernya cukup
    diambil lewat git — tanpa jaringan pun tetap bisa selama ref terakhir sudah
    tersimpan di mesin.

    Bila gagal, ekspor tetap berjalan tanpa penggabungan (tampil seperti dulu). """
    try:
        subprocess.run(["git", "fetch", "origin", "main", "--quiet"],
                       cwd=str(REPO), timeout=timeout, check=False,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:                          # noqa: BLE001 — offline, dll.
        pass

    for ref in ("origin/main", "HEAD"):
        try:
            out = subprocess.run(
                ["git", "show", ref + ":data/db.json"],
                cwd=str(REPO), timeout=timeout, check=True,
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
            db = json.loads(out.stdout.decode("utf-8"))
        except Exception:                      # noqa: BLE001
            continue
        if isinstance(db, dict) and isinstance(db.get("meta"), dict) \
                and isinstance(db.get("entries"), list):
            return db

    # cadangan terakhir: berkas hasil ekspor sebelumnya di working tree.
    # Isinya sudah termasuk penggabungan sebelumnya, jadi menerapkannya ulang
    # bersifat idempoten — tetap lebih baik daripada membuang penanda
    # suntingan situs karena git tidak bisa dihubungi.
    f = REPO / "data" / "db.json"
    if f.is_file():
        try:
            db = json.loads(f.read_text(encoding="utf-8"))
        except Exception:                      # noqa: BLE001
            db = None
        if isinstance(db, dict) and isinstance(db.get("meta"), dict) \
                and isinstance(db.get("entries"), list):
            return db
    return None


def selaraskan_meta(meta: dict, entries: list[dict]) -> None:
    """Hitung ulang nilai turunan meta dari isi `entries`.

    load_db() sudah menghitungnya dari folder DATA\\; begitu entri terhapus atau
    no urutnya berubah oleh suntingan situs, angka-angka itu harus disegarkan
    supaya jumlah di sidebar, rentang filter, dan statistik tetap benar. """
    meta["total"] = len(entries)
    meta["withIcon"] = sum(1 for e in entries if e.get("p"))
    meta["named"] = sum(1 for e in entries if e.get("e") or e.get("z"))

    per: dict[str, list[dict]] = {}
    for e in entries:
        per.setdefault(e.get("c"), []).append(e)

    # gno = nomor global: kategori mengikuti urutan navigasi lalu ikut no,
    # sama persis dengan load_db() (sorted stabil by no)
    gno = 0
    cats: list[dict] = []
    for c in (meta.get("categories") or []):
        recs = per.pop(c.get("key"), None)
        if not recs:
            continue                           # seluruh entri kategori terhapus
        for r in sorted(recs, key=lambda r: r.get("no") or 0):
            gno += 1
            r["gno"] = gno
        c["count"] = len(recs)
        c["withIcon"] = sum(1 for r in recs if r.get("p"))
        c["noMax"] = max((r.get("no") or 0 for r in recs), default=0)
        c["noCustom"] = any(r.get("custom") for r in recs)
        cats.append(c)
    meta["categories"] = cats

    parents: list[dict] = []
    for c in cats:
        p = next((x for x in parents if x["key"] == c["parent"]), None)
        if p is None:
            p = {"key": c["parent"], "label": c["parent"],
                 "count": 0, "withIcon": 0, "children": []}
            parents.append(p)
        p["count"] += c["count"]
        p["withIcon"] += c["withIcon"]
        p["children"].append(c["key"])
    meta["parents"] = parents
    meta["noMaxAll"] = max((c["noMax"] for c in cats), default=0)
    meta["noCustom"] = [c["key"] for c in cats if c.get("noCustom")]


def gabung_situs(situs: dict, db: dict) -> dict:
    """Terapkan suntingan admin di situs LIVE ke hasil ekspor lokal.

    Aturannya cuma satu: APA YANG TELAH DISUNTING DI SITUS MENANG. Ekspor lokal
    tetap yang menambah entri baru dari hasil scan, sedangkan nama, no urut,
    entri terhapus, dan urutan sub kategori dari situs tidak ditimpa — supaya
    koreksi admin tidak lenyap setiap kali database discan ulang.

    Mengembalikan ringkasan: {"hapus": n, "nama": n, "urut": n, "sub": n}.

    Untuk membatalkan kunci situs, hapus field penandanya (editNama / no0)
    dari data/db.json, atau hapus barisnya dari meta.situsHapus. """
    smeta = situs.get("meta") or {}
    sents = situs.get("entries") or []

    def iid(x):
        try:
            return int(x)
        except (TypeError, ValueError):
            return None

    sby: dict[int, dict] = {}
    for e in sents:
        k = iid(e.get("i"))
        if k is not None:
            sby[k] = e

    ringkas = {"hapus": 0, "nama": 0, "urut": 0, "sub": 0}
    entries: list[dict] = db["entries"]

    # 1) entri yang dihapus lewat situs jangan dihidupkan lagi oleh scan
    hapus = set()
    for c, i in (smeta.get("situsHapus") or []):
        k = iid(i)
        if isinstance(c, str) and k is not None:
            hapus.add((c, k))
    if hapus:
        sebelum = len(entries)
        entries = [e for e in entries
                   if (e.get("c"), iid(e.get("i"))) not in hapus]
        ringkas["hapus"] = sebelum - len(entries)
    db["entries"] = entries

    # 2) nama yang diedit di situs (editNama menyimpan field mana yang terkunci)
    for e in entries:
        s = sby.get(iid(e.get("i")))
        if not s:
            continue
        fl = s.get("editNama")
        if fl == 1:
            fl = {"e": 1, "z": 1}
        if not isinstance(fl, dict) or not fl:
            continue
        for k in ("e", "z"):
            if k in fl and s.get(k) is not None and e.get(k) != s.get(k):
                e[k] = s[k]
                ringkas["nama"] += 1
        e["editNama"] = dict(fl)

    # 3) no urut: kategori yang pernah disunting situs -> seluruh urutan situs
    #    menang; entri baru (hasil scan, tidak ada di situs) menyusul di belakang
    #    nomor tertinggi supaya tidak pernah kembar
    peta: dict[str, dict[int, tuple[int, object]]] = {}
    for e in sents:
        if e.get("no0") is None:
            continue
        k, no = iid(e.get("i")), e.get("no")
        if isinstance(e.get("c"), str) and k is not None and no is not None:
            peta.setdefault(e["c"], {})[k] = (no, e.get("no0"))

    per_lokal: dict[str, list[dict]] = {}
    for e in entries:
        per_lokal.setdefault(e.get("c"), []).append(e)

    for cat, peta_cat in peta.items():
        recs = per_lokal.get(cat)
        if not recs:
            continue
        angka = [v[0] for v in peta_cat.values() if isinstance(v[0], int)]
        maks = max(angka) if angka else 0
        sisa: list[dict] = []
        for e in recs:
            k = iid(e.get("i"))
            if k in peta_cat:
                e["no"], e["no0"] = peta_cat[k]
            else:
                sisa.append(e)
            e["custom"] = True                # seluruh kategori = disunting
        sisa.sort(key=lambda e: iid(e.get("i")) or 0)
        for e in sisa:
            maks += 1
            e["no"] = maks
        ringkas["urut"] += 1

    # 4) urutan sub kategori yang disusun DI SITUS.
    #    Yang jadi patokan ialah meta.situsUrut (penanda), BUKAN meta.subOrder —
    #    field itu juga diisi ekspor lokal dari sub_urut.json. Kalau subOrder
    #    saja yang dipakai, urutan yang Anda susun di localhost akan tertimpa
    #    nilai situs yang lama setiap kali ikut diekspor.
    sub = db["meta"].get("subOrder") or {}
    situs_urut = db["meta"].get("situsUrut") or {}
    for induk, urut in (smeta.get("situsUrut") or {}).items():
        if not isinstance(urut, list) or not urut:
            continue
        if sub.get(induk) != list(urut):
            ringkas["sub"] += 1
        sub[induk] = list(urut)             # urutan situs menang
        situs_urut[induk] = list(urut)      # penanda ikut dibawa ke ekspor
    db["meta"]["subOrder"] = sub
    if situs_urut:
        db["meta"]["situsUrut"] = situs_urut

    # 5) bawa terus penanda suntingan situs. Kalau tidak, ekspor berikutnya
    #    tidak tahu lagi bahwa situs pernah menyunting dan koreksi admin lenyap
    #    pada ekspor kedua.
    if smeta.get("situsHapus"):
        db["meta"]["situsHapus"] = list(smeta["situsHapus"])

    return ringkas


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

    # Suntingan admin di situs diterapkan lebih dulu — supaya koreksi nama,
    # no urut, hapus, dan urutan sub kategori dari LIVE tidak tertimpa ekspor.
    situs = baca_situs()
    ringkas = None
    if situs is None:
        print("  [i] data situs tidak terbaca — ekspor tanpa penggabungan")
    else:
        ringkas = gabung_situs(situs, db)
        entries = db["entries"]

    n_icon, _ = export_icons(entries)

    meta = db["meta"]
    meta.pop("root", None)          # jangan bocorkan path lokal ke situs
    selaraskan_meta(meta, entries)   # hitung ulang: setelah merge + setelah ikon
    meta["sig"] = server.js_sig(entries)

    OUT.mkdir(parents=True, exist_ok=True)

    # urutan id SEBELUM index.json ditimpa — dipakai export_langs supaya nama
    # per bahasa tidak ikut bergeser ketika entri bertambah/berkurang
    id_lama = None
    if (OUT / "index.json").is_file():
        try:
            lama = json.loads((OUT / "index.json").read_text(encoding="utf-8"))
            id_lama = [e["i"] for e in lama.get("entries") or []]
        except Exception:                      # noqa: BLE001
            id_lama = None

    write_json(OUT / "db.json", {"meta": meta, "entries": entries})
    write_json(OUT / "index.json", build_index(entries, meta))
    bahasa = export_langs(entries, id_lama)
    tanggal_live()

    if ringkas is not None:
        print("-" * 62)
        print(f"  suntingan situs yang dipertahankan: "
              f"hapus {ringkas['hapus']} · nama {ringkas['nama']} · "
              f"no urut {ringkas['urut']} kategori · sub {ringkas['sub']}")

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
