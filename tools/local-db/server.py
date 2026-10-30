#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Server localhost: database block/item MiniWorld.

Sumber data (TIDAK disalin, dibaca & ditulis langsung di tempat):
    D:\\WORK\\MINI WORLD DB\\DATA\\Blocks\\<kategori>\\
        icon_webp\\<id>.webp        ikon per entri
        data_id\\entries.json       daftar entri per kategori

Kategori = subfolder di dalam Blocks  ->  ikut struktur folder apa adanya.
Tampilan = dipinjam dari index.html situs Miniworld-DB (yang di Vercel),
           hanya sumber datanya yang berbeda.

Jalankan:
    python server.py            ->  http://127.0.0.1:8777/
    python server.py --port 9000

Endpoint:
    GET  /                      aplikasi (app/index.html)
    GET  /api/db                {meta, entries}
    GET  /api/lang/<kode>.json  nama terjemahan (selaras urutan entries)
    GET  /api/icon/<kat>/<id>.webp
    POST /api/delete            {"items":[{"cat":"Blocks/Terrain","i":123}, ...]}
    POST /api/order             {"cat":"Blocks/Terrain","map":{"100":1,...}}
                                atau {"cat":"Blocks/Terrain","reset":true}
    POST /api/rename            {"cat":"Blocks/Natural","i":133,"e":"...","z":"..."}
    POST /api/cat_order         {"parent":"Blocks","order":["Natural","Terrain",...]}
                                atau {"parent":"Blocks","reset":true}

Kategori memakai kunci <indu>/<nama> (mis. Blocks/Natural, items/Food) karena
nama folder boleh kembar antar cabang DATA. Hasil edit nama disinkronkan ke
`Miniworld-DB/data/index.json` + `data/lang/*.json` dan dicatat ke
`DATA/nama_sync.json` (antrian langkah translate berikutnya).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import quote, unquote, urlparse

HERE = Path(__file__).resolve().parent

DATA = Path(r"D:\WORK\MINI WORLD DB\DATA")
# kategori = subfolder DUA tingkat di bawah DATA, contoh:
#   DATA\Blocks\Natural   DATA\Creature\Animals   DATA\items\Food
# (folder induk dibutuhkan karena ada nama kembar: Blocks/Function dan
#  items/Function -> kunci kategori jadi "InduK/Nama")
ROOT = DATA                             # dipakai untuk merakit path kategori
TRASH = DATA / "_trash"                 # hasil hapus dipindah ke sini (bisa dikembalikan)
MANIFEST = DATA / "manifest.json"
ORDER = DATA / "no_urut.json"               # hasil edit "no urut" oleh user
SUB_ORDER = DATA / "sub_urut.json"          # urutan sub kategori per induk
SYNC = DATA / "nama_sync.json"              # antrian nama hasil edit -> translate
SKIP_TOP = {"_trash"}                        # folder induk yang bukan kategori

# sumber terjemahan + tampilan
SITE = Path(r"D:\WORK\MINI WORLD DB\Miniworld-DB")
SITE_INDEX = SITE / "data" / "index.json"
SITE_LANG = SITE / "data" / "lang"

# berkas statis (index.html, app.js, i18n*.js) ada di ROOT repo — dipakai
# bersama oleh server lokal dan situs LIVE, jadi tampilannya selalu sama.
APP = SITE

# urutan block di game = urutan saat scanner membaca grid
# (halaman -> baris -> kolom). export.py mengurutkan entries.json berdasarkan ID,
# jadi satu-satunya sumber urutan aslinya ada di log scan ini.
SCAN_LOG = SITE / "tools" / "icon-scanner" / "output" / "scan.jsonl"

DB_LOCK = __import__("threading").Lock()


# ---------------------------------------------------------------- util json --

def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, obj) -> None:
    """Tulis atomik: file lama tetap utuh bila proses gagal di tengah."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    os.replace(tmp, path)


def js_sig(entries) -> str:
    """Sama persis dengan sig() di frontend (djb2 -> base36, uint32)."""
    s = ",".join(str(e["i"]) for e in entries)
    h = 5381
    for ch in s:
        h = ((h << 5) + h + ord(ch)) & 0xFFFFFFFF
    if h == 0:
        return "0"
    digs = "0123456789abcdefghijklmnopqrstuvwxyz"
    out = ""
    n = h
    while n:
        out = digs[n % 36] + out
        n //= 36
    return out


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


# ------------------------------------------------------------------ memuat --

def load_sub_order() -> dict[str, list[str]]:
    """Urutan sub kategori buatan user -> {indu: [nama, ...]}."""
    if not SUB_ORDER.is_file():
        return {}
    try:
        raw = read_json(SUB_ORDER)
    except Exception:                          # noqa: BLE001  -> berkas rusak
        return {}
    if not isinstance(raw, dict):
        return {}
    out: dict[str, list[str]] = {}
    for k, v in raw.items():
        if isinstance(v, list):
            nama = [str(x) for x in v if isinstance(x, (str, int)) and str(x)]
            if nama:
                out[str(k)] = nama
    return out


def folders() -> list[Path]:
    """Semua kategori = DATA/<indu>/<nama> (folder induk diawali '_' dibuang).

    Urutan: kelompok induk (Blocks, Creature, items) lalu sub kategori sesuai
    urutan manual user di `sub_urut.json` — yang belum tercantum menyusul
    di belakang, alfabet.
    """
    if not DATA.is_dir():
        return []
    out: list[Path] = []
    for top in DATA.iterdir():
        if not top.is_dir() or top.name in SKIP_TOP or top.name.startswith("_"):
            continue
        out.extend(p for p in top.iterdir() if p.is_dir())
    urut = load_sub_order()

    def kunci(p: Path):
        daftar = urut.get(p.parent.name)
        if daftar and p.name in daftar:
            idx = daftar.index(p.name)
        else:
            idx = len(daftar) if daftar else 0     # belum diurutkan -> belakang
        return (p.parent.name.lower(), idx, p.name.lower())

    return sorted(out, key=kunci)


def cat_key(d: Path) -> str:
    """Kunci kategori = path relatif terhadap DATA, mis. "Blocks/Natural"."""
    return d.relative_to(DATA).as_posix()


def cat_dir(key: str) -> Path | None:
    """Kunci 'InduK/Nama' -> folder kategori; None bila tidak sah (traversal)."""
    if not key or key.startswith("/") or "\\" in key or ".." in key:
        return None
    d = DATA / key
    if not d.is_dir() or cat_key(d) != key:
        return None
    # jangan percaya semata pada kecocokan teks: Windows tidak membedakan
    # besar/kecil huruf, jadi "Items/Food" akan lolos walau foldernya "items".
    try:
        nyata = d.resolve()          # resolve() mengembalikan ejaan asli di disk
    except OSError:
        return None
    if cat_key(nyata) != key:
        return None
    return d


def cat_label(key: str) -> str:
    """Tampilan sidebar: 'Blocks / Natural' (induK / nama)."""
    return " / ".join(key.split("/"))


def data_sig() -> str:
    """Jejak murah isi DATA (ukuran + mtime entri, ikon, dan berkas urut).

    Dipakai di `GET /api/db` supaya folder yang muncul BELUM lama — mis. hasil
    scan yang ditulis langsung ke `DATA\\` — ikut terbaca tanpa restart server.
    Sebelum ada ini, server tetap menyajikan 15 kategori lama walau `Gameplay\\`
    sudah berisi 99 entri.
    """
    parts: list[str] = []
    for d in folders():
        for rel in ("data_id", "data_id/entries.json", "icon_webp"):
            f = d / rel
            try:
                st = f.stat()
                parts.append(f"{f}|{st.st_size}|{st.st_mtime_ns}")
            except OSError:
                parts.append(f"{f}|-")
    for f in (ORDER, SUB_ORDER, SYNC, MANIFEST):
        try:
            st = f.stat()
            parts.append(f"{f}|{st.st_size}|{st.st_mtime_ns}")
        except OSError:
            parts.append(f"{f}|-")
    return hashlib.sha1("\n".join(parts).encode("utf-8")).hexdigest()[:20]


def read_folders() -> list[tuple[Path, str, dict]]:
    """[(folder, kunci, isi entries.json)] untuk kategori yang punya data."""
    out: list[tuple[Path, str, dict]] = []
    for d in folders():
        ef = d / "data_id" / "entries.json"
        if not ef.is_file():
            continue
        try:
            raw = read_json(ef)
        except Exception:                        # noqa: BLE001  -> rusak, lewati
            continue
        out.append((d, cat_key(d), raw))
    return out


def game_order(crumb2key: dict[str, str]) -> tuple[dict, dict]:
    """Nomor urut per kategori = urutan seperti di game.

    Sumbernya `scan.jsonl` hasil scanner: tiap record menyimpan halaman, baris,
    dan kolom saat ikon itu terbaca, jadi urutannya sama dengan yang tampil di
    grid game. Kategori di log berupa breadcrumb ("items > Food"), dipetakan ke
    kunci folder ("items/Food").
    -> ({(kunci, id): nomor}, {kunci: jumlah nomor}).
    """
    rows = []
    try:
        text = SCAN_LOG.read_text(encoding="utf-8")
    except OSError:
        text = ""
    for n, line in enumerate(text.splitlines()):
        line = line.strip()
        if not line:
            continue
        try:
            d = json.loads(line)
        except Exception:                       # baris log rusak -> lewati
            continue
        if d.get("id") is None or not d.get("cat"):
            continue
        crumb = str(d["cat"])
        folder = crumb2key.get(crumb) or crumb.replace(" > ", "/")
        if folder not in crumb2key.values():
            continue                            # kategorinya sudah tidak ada
        rows.append((folder, int(d.get("page") or 0), int(d.get("row") or 0),
                     int(d.get("col") or 0), n, int(d["id"])))

    order: dict[tuple[str, int], int] = {}
    per: dict[str, int] = {}
    for folder, _p, _r, _c, _n, iid in sorted(rows):
        k = (folder, iid)
        if k in order:
            continue                            # scan ulang -> pakai yang pertama
        per[folder] = per.get(folder, 0) + 1
        order[k] = per[folder]
    return order, per


def load_order() -> dict:
    """Baca hasil edit "no urut" -> {kategori: {id: nomor}}.

    File ini menimpa hasil baca scan.jsonl. Kalau file tidak ada / korup,
    nomor urut kembali seperti hasil scan apa adanya.
    """
    if not ORDER.is_file():
        return {}
    try:
        raw = read_json(ORDER)
    except Exception:                            # noqa: BLE001
        return {}
    if not isinstance(raw, dict):
        return {}
    out: dict[str, dict[int, int]] = {}
    for cat, m in raw.items():
        if not isinstance(m, dict):
            continue
        d: dict[int, int] = {}
        for k, v in m.items():
            try:
                d[int(k)] = int(v)
            except (TypeError, ValueError):
                continue
        if d:
            out[str(cat)] = d

    # Kunci lama cuma nama folder (waktu itu hanya DATA\Blocks yang dibaca) ->
    # ganti jadi "InduK/Nama". Kalau nama itu dipakai lebih dari satu kategori
    # tidak bisa dipastikan maksudnya, jadi dibiarkan (tidak akan cocok).
    per_nama: dict[str, list[str]] = {}
    for p in folders():
        per_nama.setdefault(p.name, []).append(cat_key(p))
    pindah: dict[str, dict[int, int]] = {}
    for cat, m in out.items():
        if "/" in cat:
            pindah[cat] = m
            continue
        kunci = per_nama.get(cat) or []
        pindah[kunci[0] if len(kunci) == 1 else cat] = m
    return pindah


def save_order(cat: str, mapping=None, reset: bool = False) -> dict:
    """Simpan (atau kembalikan) nomor urut satu kategori.

    `mapping` harus memuat SEMUA id pada kategori itu -> nomor barunya,
    sehingga hasilnya selalu utuh. Nomor kembar langsung ditolak.
    """
    if cat_dir(cat) is None:
        raise ValueError("kategori tidak dikenal: " + repr(cat))

    data = load_order()
    n = 0
    if reset:
        data.pop(cat, None)
    else:
        if not isinstance(mapping, dict) or not mapping:
            raise ValueError("map kosong — kirim seluruh {id: no} kategori itu")
        new: dict[int, int] = {}
        for k, v in mapping.items():
            try:
                iid, no = int(k), int(v)
            except (TypeError, ValueError):
                raise ValueError("pasangan tidak sah: %r -> %r" % (k, v))
            if no < 1:
                raise ValueError("nomor urut harus >= 1")
            new[iid] = no
        seen: dict[int, list[int]] = {}
        for iid, no in new.items():
            seen.setdefault(no, []).append(iid)
        kembar = {no: ids for no, ids in seen.items() if len(ids) > 1}
        if kembar:
            raise ValueError("nomor urut kembar: " + "; ".join(
                "No.%d dipakai id %s" % (no, sorted(ids))
                for no, ids in sorted(kembar.items())))
        data[cat] = {str(k): v for k, v in sorted(new.items())}
        n = len(new)

    if data:
        write_json(ORDER, data)
    elif ORDER.is_file():                      # tidak ada override sama sekali
        ORDER.unlink()                         # biar folder DATA\ bersih
    return {"reset": bool(reset), "n": n, "file": str(ORDER)}


def load_db() -> dict:
    """Baca semua kategori -> {meta, entries} gaya index.json situs."""
    items = read_folders()
    crumb2key = {str(raw.get("breadcrumb") or f"{d.parent.name} > {d.name}"): k
                 for d, k, raw in items}
    order, per_no = game_order(crumb2key)
    ovr = load_order()                          # hasil edit "no urut" menang
    entries: list[dict] = []
    cats: list[dict] = []
    generated = ""
    gno = 0                                     # nomor urut global lintas kategori

    for d, key, raw in items:
        icon_dir = d / "icon_webp"
        crumb = str(raw.get("breadcrumb") or f"{d.parent.name} > {d.name}")
        punya_nomor = bool(ovr.get(key))
        override = ovr.get(key) or {}
        recs: list[dict] = []
        n_icon = 0
        for e in raw.get("entries") or []:
            rec = dict(e)
            rec["c"] = key                         # kunci kategori "InduK/Nama"
            rec.setdefault("cat", crumb)
            rec.pop("wp", None)                     # path situs Vercel tidak dipakai
            f = icon_dir / (str(rec["i"]) + ".webp")
            if f.is_file():
                rec["p"] = f"/api/icon/{quote(key, safe='')}/{rec['i']}.webp"
                n_icon += 1
            else:
                rec.pop("p", None)
            iid = int(rec["i"])
            # Kategori yang sudah disunting: nomor hasil scan tidak dipakai lagi
            # untuk entri yang TIDAK ada di override — bisa bentrok dengan nomor
            # hasil edit (entri ditambahkan setelah urutan disusun). Entri begitu
            # dihitung sebagai "sisa" di belakang, seperti entri tanpa nomor.
            rec["no"] = override.get(iid) if override else order.get((key, iid))
            rec["custom"] = punya_nomor            # urutan sudah disunting user
            recs.append(rec)

        # Entri yang tidak tercatat di scan.jsonl (mis. hasil backfill lama)
        # mendapat nomor sisa di belakang, urut ID — supaya tidak ada entri
        # yang kehilangan nomor dan rentang "1..habis" selalu utuh.
        # Mulai setelah nomor tertinggi yang sudah ada supaya tidak bentrok
        # dengan nomor hasil edit. Kalau kategori sudah disunting, batasnya
        # cukup dari override saja (rentang scan lama tidak relevan lagi).
        ada = [r["no"] for r in recs if r["no"] is not None]
        batas = max(max(ada or [0]), 0 if override else per_no.get(key, 0))
        for rec in sorted((r for r in recs if r["no"] is None),
                          key=lambda r: int(r["i"])):
            batas += 1
            rec["no"] = batas

        for rec in sorted(recs, key=lambda r: r["no"]):
            gno += 1
            rec["gno"] = gno
        entries.extend(recs)

        g = str(raw.get("generated") or "")
        if g > generated:
            generated = g
        induk, sub = key.split("/", 1)
        cats.append({
            "key": key,
            "parent": induk,                    # cabang: Blocks / Creature / items
            "name": sub,                        # sub kategori: Natural, Food, ...
            "label": cat_label(key),
            "count": len(recs),
            "withIcon": n_icon,
            "noMax": max(r["no"] for r in recs) if recs else 0,
            "noCustom": punya_nomor,
            "breadcrumb": crumb,
        })

    # navigasi dua tingkat: cabang (Blocks, Creature, items) -> sub kategori
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

    meta = {
        "generated": generated or now(),
        "total": len(entries),
        "withIcon": sum(1 for e in entries if e.get("p")),
        "named": sum(1 for e in entries if e.get("e") or e.get("z")),
        "categories": cats,
        "parents": parents,
        "subOrder": load_sub_order(),      # urutan sub kategori buatan user
        "root": str(ROOT),
        "noMaxAll": max((c["noMax"] for c in cats), default=0),
        "noCustom": [c["key"] for c in cats if c.get("noCustom")],
        "sig": js_sig(entries),
    }
    return {"meta": meta, "entries": entries}


def build_langs(entries: list[dict]) -> dict:
    """Terjemahan dari repo situs, dipetakan ulang lewat ID -> urutan entries."""
    out: dict[str, dict] = {}
    try:
        pos = {e["i"]: k for k, e in enumerate(read_json(SITE_INDEX)["entries"])}
    except Exception:
        return out
    if not SITE_LANG.is_dir():
        return out
    for f in sorted(SITE_LANG.glob("*.json")):
        try:
            raw = read_json(f)
        except Exception:
            continue
        src = raw.get("n") or []
        out[f.stem] = {
            "code": raw.get("code") or f.stem,
            "label": raw.get("label") or f.stem,
            "n": [src[pos[e["i"]]] if e["i"] in pos else None for e in entries],
            "sig": js_sig(entries),
        }
    return out


def refresh_db() -> dict:
    """Muat ulang cache db + terjemahan dari isi DATA terbaru.

    Satu-satunya tempat yang boleh mengisi `Handler.db` supaya jejak `data_sig()`
    selalu dihitung ulang setelah selesai — kalau tidak, `GET /api/db` akan
    reload berulang tiap kali dipanggil.
    """
    db = load_db()
    Handler.db = db
    Handler.langs = build_langs(db["entries"])
    Handler.db_sig = data_sig()
    return db


def update_manifest() -> dict:
    """Selaraskan manifest.json dengan isi folder (total per kategori)."""
    cats = []
    total = icons = 0
    for d, key, raw in read_folders():
        n = len(raw.get("entries") or [])
        ic = sum(1 for e in (raw.get("entries") or [])
                 if (d / "icon_webp" / (str(e["i"]) + ".webp")).is_file())
        cats.append({
            "path": key,
            "breadcrumb": raw.get("breadcrumb") or f"{d.parent.name} > {d.name}",
            "total": n,
            "withIcon": ic,
            "generated": raw.get("generated") or now(),
        })
        total += n
        icons += ic
    man = {
        "root": str(DATA),
        "generated": now(),
        "categories": cats,
        "totals": {"categories": len(cats), "entries": total, "icons": icons},
    }
    write_json(MANIFEST, man)
    return man


def delete_items(items: list[dict]) -> dict:
    """Hapus entri dari entries.json + pindahkan ikonnya ke DATA/_trash."""
    allowed = {cat_key(p) for p in folders()}
    by_cat: dict[str, set[int]] = {}
    for it in items:
        cat = str(it.get("cat") or "")
        if cat not in allowed:                       # tolak path traversal
            raise ValueError("kategori tidak dikenal: " + cat)
        try:
            iid = int(it.get("i"))
        except (TypeError, ValueError):
            raise ValueError("id tidak valid: " + repr(it.get("i")))
        by_cat.setdefault(cat, set()).add(iid)

    deleted, moved = 0, 0
    for cat, ids in by_cat.items():
        d = ROOT / cat
        ef = d / "data_id" / "entries.json"
        raw = read_json(ef)
        before = raw.get("entries") or []
        keep = [e for e in before if int(e["i"]) not in ids]
        if len(keep) == len(before):
            continue
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        for e in before:
            if int(e["i"]) not in ids:
                continue
            src = d / "icon_webp" / (str(e["i"]) + ".webp")
            if src.is_file():
                dst = TRASH / cat / stamp
                dst.mkdir(parents=True, exist_ok=True)
                shutil.move(str(src), str(dst / src.name))
                moved += 1
        deleted += len(before) - len(keep)
        raw["entries"] = keep
        raw["total"] = len(keep)
        raw["withIcon"] = sum(
            1 for e in keep if (d / "icon_webp" / (str(e["i"]) + ".webp")).is_file())
        raw["generated"] = now()
        write_json(ef, raw)

    update_manifest()
    return {"deleted": deleted, "iconsMoved": moved, "trash": str(TRASH)}


# field entri yang boleh diedit user lewat UI
BOLEH_UBAH = ("e", "z")                    # nama English / nama 中文
MAKS_NAMA = 120


def update_entry(cat: str, iid: int, fields: dict) -> dict:
    """Ubah nama satu entri di entries.json (tulis atomik).

    Hanya `e` (English) dan `z` (中文) yang boleh diubah — id, label grup,
    OCR, dan urutan disengaja tidak bisa diedit supaya data hasil scan tetap
    bisa dibedakan dari hasil koreksi manual.
    """
    if not isinstance(fields, dict):
        raise ValueError("fields bukan objek")
    folder = cat_dir(cat)
    if folder is None:                       # tolak path traversal
        raise ValueError("kategori tidak dikenal: " + repr(cat))

    ef = folder / "data_id" / "entries.json"
    raw = read_json(ef)
    rows = raw.get("entries") or []
    target = None
    for e in rows:
        try:
            if int(e.get("i")) == iid:
                target = e
                break
        except (TypeError, ValueError):
            continue
    if target is None:
        raise ValueError("id %s tidak ada di kategori %s" % (iid, cat))

    ubah: dict[str, str] = {}
    for k, v in fields.items():
        if k not in BOLEH_UBAH:
            raise ValueError("field tidak boleh diubah: " + str(k))
        if v is None:                        # tidak dikirim -> tidak diubah
            continue
        if not isinstance(v, str):
            raise ValueError("nilai %s harus teks" % k)
        s = " ".join(v.split())              # buang spasi/karakter tak terpakai
        if len(s) > MAKS_NAMA:
            raise ValueError("%s terlalu panjang (maks %d karakter)" % (k, MAKS_NAMA))
        if s != (target.get(k) or ""):
            ubah[k] = s

    if not ubah:                             # tidak ada perubahan -> tidak tulis
        return {"changed": [], "cat": cat, "i": iid}

    e_lama = str(target.get("e") or "")      # dipakai untuk sinkron translate
    target.update(ubah)
    raw["generated"] = now()
    write_json(ef, raw)

    # ikut disinkronkan ke data situs supaya hasil koreksi masuk ke langkah
    # translate berikutnya (index.json = sumber nama, lang/*.json = padanannya)
    sync = None
    if ubah:
        try:
            sync = sync_site(iid, cat, ubah, e_lama)
        except Exception as ex:                 # noqa: BLE001
            sync = {"ok": False, "error": str(ex)}

    res = {"changed": sorted(ubah), "cat": cat, "i": iid,
           "entry": {k: target.get(k) for k in ("i", "e", "z", "l", "s")}}
    if sync is not None:
        res["site"] = sync
    return res


def sync_site(iid: int, cat: str, ubah: dict, e_lama: str) -> dict:
    """Terapkan hasil edit nama ke data situs + antrian translate.

      * `data/index.json`       sumber nama (e / z) ikut diperbarui
      * `data/lang/*.json`      hanya terjemahan yang masih kosong / persis
                                nama English lama yang ikut diganti —
                                terjemahan lama tidak dibuang, hanya ditandai
                                `stale` supaya langkah `translate` berikutnya
                                memutakhirkan
      * `DATA\\nama_sync.json`  antrian: daftar id + nama baru + berapa banyak
                                bahasa yang masih menunggu translate ulang
    """
    res: dict = {"ok": True, "queue": False, "index": False, "langs": 0,
                 "stale": 0}

    # 1) data/index.json — sumber nama untuk pipeline translate
    idx = read_json(SITE_INDEX)
    rows = idx.get("entries") or []
    pos = None
    for k, r in enumerate(rows):
        if r.get("i") == iid:
            pos = k
            for f, v in ubah.items():
                r[f] = v
            break
    if pos is None:
        res["note"] = "id belum ada di data/index.json — masuk antrian translate"
    else:
        write_json(SITE_INDEX, idx)
        res["index"] = True

    # 3) data/lang/*.json — hanya nilai yang memang belum pernah diterjemahkan
    #    (kosong / persis nama English lama) yang ikut diganti nama barunya.
    #    Terjemahan lama TIDAK dibuang: ia tetap tampil sampai langkah translate
    #    berikutnya memutakhirkan, dan sudah ditandai `stale` di antrian.
    if "e" in ubah and pos is not None:
        for f in sorted(SITE_LANG.glob("*.json")):
            try:
                raw = read_json(f)
            except Exception:                   # noqa: BLE001
                continue
            n = raw.get("n")
            if not isinstance(n, list) or pos >= len(n):
                continue
            lama = n[pos]
            if lama is None or lama == "" or lama == e_lama:
                n[pos] = ubah["e"]              # belum terjemahan / cuma salinan EN
                write_json(f, raw)
                res["langs"] += 1
            else:
                res["stale"] += 1               # perlu translate ulang nanti

    # 4) antrian lokal — daftar id + nama baru yang menunggu translate ulang
    antri: dict = {}
    if SYNC.is_file():
        try:
            raw = read_json(SYNC)
            if isinstance(raw, dict):
                antri = raw
        except Exception:                       # noqa: BLE001
            antri = {}
    kunci = cat + "/" + str(iid)
    rec = dict(antri.get(kunci) or {})
    rec.update({"cat": cat, "i": iid, "updated": now(),
                "stale": res["stale"], "langs": res["langs"]})
    rec.update(ubah)
    antri[kunci] = rec
    write_json(SYNC, antri)
    res["queue"] = True
    if res["stale"]:
        res["pending"] = "translate ulang"
    return res


def save_cat_order(parent: str, order=None, reset: bool = False) -> dict:
    """Simpan urutan sub kategori satu cabang (mis. Blocks -> Natural dulu)."""
    if not parent or "/" in parent or "\\" in parent or ".." in parent:
        raise ValueError("induk tidak sah: " + repr(parent))
    # bandingkan nama folder apa adanya — sistem berkas Windows tidak
    # membedakan besar/kecil huruf, jadi "Items" akan cocok dengan "items"
    # dan menghasilkan kunci urutan yang tidak pernah terpakai.
    top = next((p for p in DATA.iterdir()
                if p.is_dir() and p.name == parent), None)
    if (top is None or parent in SKIP_TOP or parent.startswith("_")):
        raise ValueError("induk tidak dikenal: " + repr(parent))
    subs = sorted(p.name for p in top.iterdir()
                  if p.is_dir() and not p.name.startswith("_"))

    data: dict = {}
    if SUB_ORDER.is_file():
        try:
            raw = read_json(SUB_ORDER)
            if isinstance(raw, dict):
                data = raw
        except Exception:                       # noqa: BLE001
            data = {}

    if reset:
        data.pop(parent, None)
        n = 0
    else:
        if not isinstance(order, list) or not order:
            raise ValueError("urutan kosong")
        nama = [str(x) for x in order]
        if len(set(nama)) != len(nama):
            raise ValueError("ada nama sub kategori kembar di urutan")
        salah = [x for x in nama if x not in subs]
        if salah:
            raise ValueError("sub kategori tidak ada di " + parent
                             + ": " + ", ".join(salah))
        # yang belum diklik user menyusul di belakang (alfabet)
        nama += sorted(x for x in subs if x not in set(nama))
        data[parent] = nama
        n = len(nama)

    if data:
        write_json(SUB_ORDER, data)
    elif SUB_ORDER.is_file():                   # tidak ada urutan sama sekali
        SUB_ORDER.unlink()
    return {"parent": parent, "n": n, "reset": bool(reset),
            "order": data.get(parent) or [], "file": str(SUB_ORDER)}


# ------------------------------------------------------------- kunci admin ---
# Sumber kebenaran satu-satunya ialah auth.js di root repo: isinya HASH SHA-256,
# bukan kuncinya, dan hash itu diparse sekali waktu mulai supaya tidak pernah
# ada dua salinan yang bisa berbeda.
#
# Tanpa hash ini semua endpoint tulis MENOLAK permintaan (fail-safe) — bukan
# membiarkannya lolos. Ini penting: menyembunyikan tombol di klien memang perlu,
# tetapi tidak cukup sebagai pengaman, sebab siapa pun bisa memanggil
# /api/delete langsung dari konsol peramban, baik di localhost maupun di LIVE.

_H_ADMIN = ""


def muat_hash_admin() -> bool:
    """Baca H_ADMIN dari auth.js. False bila tidak terbaca (lalu tulis ditolak)."""
    global _H_ADMIN
    try:
        teks = (APP / "auth.js").read_text(encoding="utf-8")
    except OSError:
        return False
    m = re.search(r"H_ADMIN\s*=\s*'([0-9a-f]{64})'", teks)
    if not m:
        return False
    _H_ADMIN = m.group(1)
    return True


def normalisasi_kunci(raw) -> str:
    """Sama persis dengan normalisasi() di auth.js.

    auth.js memakai `.toUpperCase().replace(/[^A-Z0-9]/g, '')` lalu menyisipkan
    hubung per 5 — jadi di sini pun hanya A-Z dan 0-9 yang dipertahankan.
    isalnum() TIDAK dipakai karena ikut menerima huruf non-ASCII (mis. Ä)."""
    bersih = "".join(ch for ch in str(raw or "").upper()
                     if ("A" <= ch <= "Z") or ("0" <= ch <= "9"))
    return "-".join(bersih[i:i + 5] for i in range(0, len(bersih), 5))


def kunci_admin(dikirim) -> bool:
    """True bila `dikirim` (header x-mwdb-key) benar-benar kunci admin."""
    if not dikirim or not _H_ADMIN:
        return False
    h = hashlib.sha256(normalisasi_kunci(dikirim).encode("utf-8")).hexdigest()
    return h == _H_ADMIN


# ------------------------------------------------------------------ handler --

class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "MiniWorldLocalDB/1.0"

    db: dict = {"meta": {"categories": [], "total": 0, "withIcon": 0},
                "entries": []}
    langs: dict = {}
    db_sig: str = ""                   # jejak isi DATA saat db dimuat terakhir

    # -- helpers ----------------------------------------------------------
    def _send(self, body: bytes, ctype: str, status: int = 200) -> None:
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        # Penanda mode. Kini LIVE juga punya endpoint /api/* (fungsi
        # serverless), jadi app.js tidak lagi menebak mode dari hostname maupun
        # dari urutan URL yang berhasil — ia membaca header ini. Jawaban tanpa
        # header (berkas statis di Vercel) dianggap "live".
        self.send_header("x-mwdb-mode", "local")
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _json(self, obj, status: int = 200) -> None:
        self._send(json.dumps(obj, ensure_ascii=False).encode("utf-8"),
                   "application/json; charset=utf-8", status)

    def log_message(self, fmt, *args):            # ringkas, jangan banjir
        if self.path.startswith("/api/icon"):
            return
        sys.stderr.write("%s %s\n" % (self.address_string(),
                                      fmt % args if args else fmt))

    # -- GET --------------------------------------------------------------
    def do_GET(self) -> None:
        path = unquote(urlparse(self.path).path)

        if path in ("/", "/index.html"):
            f = APP / "index.html"
            if not f.is_file():
                return self._json({"error": "app/index.html tidak ada"}, 404)
            return self._send(f.read_bytes(), "text/html; charset=utf-8")

        if path == "/api/db":
            with DB_LOCK:
                # muat ulang kalau isi DATA berubah di luar API (mis. hasil scan
                # yang baru ditulis ke folder) — supaya tidak perlu restart
                if data_sig() != type(self).db_sig:
                    refresh_db()
                return self._json(self.db)

        if path.startswith("/api/lang/"):
            code = path[len("/api/lang/"):-len(".json")] if path.endswith(".json") \
                else path[len("/api/lang/"):]
            data = self.langs.get(code)
            if not data:
                return self._json({"error": "bahasa tidak ada: " + code}, 404)
            return self._json(data)

        if path.startswith("/api/icon/"):
            rest = path[len("/api/icon/"):]
            if "/" not in rest:
                return self._json({"error": "path ikon salah"}, 400)
            cat, fname = rest.rsplit("/", 1)     # kategori boleh "InduK/Nama"
            folder = cat_dir(cat)
            if folder is None:
                return self._json({"error": "kategori tidak dikenal"}, 404)
            if not fname.endswith(".webp") or "/" in fname or "\\" in fname \
                    or ".." in fname:
                return self._json({"error": "nama berkas tidak sah"}, 400)
            f = folder / "icon_webp" / fname
            if not f.is_file():
                return self._json({"error": "ikon tidak ada"}, 404)
            return self._send(f.read_bytes(), "image/webp")

        if path.startswith("/api/"):
            return self._json({"error": "endpoint tidak dikenal"}, 404)

        # berkas statis di folder app/ (app.js, css, ...) — hanya satu tingkat
        name = path.lstrip("/")
        if name and "/" not in name and "\\" not in name and ".." not in name:
            f = APP / name
            if f.is_file():
                ctype = ("text/javascript; charset=utf-8" if f.suffix == ".js"
                         else "text/css; charset=utf-8" if f.suffix == ".css"
                         else "application/octet-stream")
                return self._send(f.read_bytes(), ctype)
        return self._json({"error": "tidak ditemukan"}, 404)

    # -- POST -------------------------------------------------------------
    def do_POST(self) -> None:
        path = unquote(urlparse(self.path).path)
        try:
            n = int(self.headers.get("Content-Length") or 0)
            payload = json.loads(self.rfile.read(n).decode("utf-8") or "{}")
        except Exception:
            return self._json({"error": "body bukan JSON yang sah"}, 400)

        # Gerbang admin untuk SEMUA endpoint tulis. Badan tetap dibaca lebih dulu
        # (koneksinya keep-alive, HTTP/1.1) supaya jawaban galat tidak membuat
        # sisa body tertinggal dan merusak permintaan berikutnya.
        if not kunci_admin(self.headers.get("x-mwdb-key")):
            return self._json({"error": "kunci admin diperlukan"}, 401)

        if path == "/api/delete":
            items = payload.get("items")
            if not isinstance(items, list) or not items:
                return self._json({"error": "items kosong"}, 400)
            try:
                with DB_LOCK:
                    res = delete_items(items)
                    # tulis ke atribut KELAS — atribut instance tidak terbaca
                    # oleh koneksi berikutnya, jadi data akan tetap basi.
                    refresh_db()
            except Exception as e:                # noqa: BLE001
                return self._json({"error": str(e)}, 400)
            res["ok"] = True
            res["meta"] = self.db["meta"]
            return self._json(res)

        if path == "/api/order":
            cat = str(payload.get("cat") or "")
            reset = payload.get("reset") is True
            try:
                with DB_LOCK:
                    res = save_order(cat, payload.get("map"), reset=reset)
                    # isi entries.json tidak berubah, jadi urutan langkah
                    # terjemahan tetap valid — cukup muat ulang db saja.
                    refresh_db()
            except Exception as e:                # noqa: BLE001
                return self._json({"error": str(e)}, 400)
            res["ok"] = True
            res["meta"] = type(self).db["meta"]
            return self._json(res)

        if path == "/api/rename":
            cat = str(payload.get("cat") or "")
            try:
                iid = int(payload.get("i"))
            except (TypeError, ValueError):
                return self._json(
                    {"error": "id tidak valid: " + repr(payload.get("i"))}, 400)
            try:
                with DB_LOCK:
                    res = update_entry(cat, iid, {"e": payload.get("e"),
                                                  "z": payload.get("z")})
                    if res["changed"]:       # nama berubah -> muat ulang db
                        refresh_db()
            except Exception as e:                # noqa: BLE001
                return self._json({"error": str(e)}, 400)
            res["ok"] = True
            res["meta"] = type(self).db["meta"]
            return self._json(res)

        if path == "/api/cat_order":
            parent = str(payload.get("parent") or "")
            reset = payload.get("reset") is True
            try:
                with DB_LOCK:
                    res = save_cat_order(parent, payload.get("order"),
                                         reset=reset)
                    refresh_db()         # urutan navigasi ikut berubah
            except Exception as e:                # noqa: BLE001
                return self._json({"error": str(e)}, 400)
            res["ok"] = True
            res["meta"] = type(self).db["meta"]
            return self._json(res)

        return self._json({"error": "endpoint tidak dikenal"}, 404)


# -------------------------------------------------------------------- main --

def main() -> int:
    ap = argparse.ArgumentParser(
        description="Server localhost database MiniWorld (semua kategori di folder DATA\\)")
    ap.add_argument("--port", type=int, default=8777)
    ap.add_argument("--host", default="127.0.0.1",
                    help="default 127.0.0.1 (hanya bisa diakses dari komputer ini)")
    a = ap.parse_args()

    if not ROOT.is_dir():
        sys.exit(f"[!] folder database tidak ditemukan: {ROOT}")
    if not (APP / "index.html").is_file():
        sys.exit(f"[!] aplikasi tidak ditemukan: {APP / 'index.html'}")

    if not muat_hash_admin():
        print("[!] H_ADMIN tidak terbaca dari auth.js")
        print("    -> SEMUA permintaan tulis (/api/rename, /api/delete, dst.)")
        print("       akan DITOLAK 401. Baca tetap berjalan normal.")

    try:
        update_manifest()                    # manifest selalu ikut isi folder
    except Exception as e:                   # noqa: BLE001
        print(f"[!] manifest tidak bisa diperbarui: {e}")
    refresh_db()                             # setelah manifest, jejak ikut final

    m = Handler.db["meta"]
    print("=" * 62)
    print("  MiniWorld DB  (localhost)")
    print(f"  data      : {ROOT}")
    print(f"  kategori  : {', '.join(c['key'] for c in m['categories']) or '-'}")
    print(f"  entri     : {m['total']}  (berikon {m['withIcon']})")
    print(f"  hapus ->  : {TRASH}")
    print(f"  tulis     : butuh kunci admin"
          f"{' (hash ok)' if _H_ADMIN else ' (DITOLAK SEMUA)'}")
    print("=" * 62)
    print(f"  Buka:  http://{a.host}:{a.port}/")
    print("  Stop:  Ctrl+C")
    print("=" * 62, flush=True)

    srv = ThreadingHTTPServer((a.host, a.port), Handler)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n[·] server berhenti")
    finally:
        srv.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
