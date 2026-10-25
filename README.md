# MiniWorld DB

Katalog ID block, item, gameplay, dan creature Mini World — cari nama (English / 中文 /
Bahasa Indonesia / bahasa lain), lihat ikon, dan klik satu entri untuk menyalin ID-nya.

Halaman statis: buka `index.html` lewat server HTTP (bukan `file://`, karena data dimuat
dengan `fetch`):

```bash
python -m http.server 8777
# lalu buka http://127.0.0.1:8777/
```

## Isi repo

```
index.html                 # UI (HTML + CSS + JS dalam satu berkas)
data/index.json            # manifest: 3.063 entri (id, nama EN/ZH, kategori, path ikon)
data/lang/*.json           # nama terjemahan per bahasa (id, es, pt, fr, ja, ru)
data/<kategori>/icons_cache/  # ikon .webp dari repo ini (blocks, creature, gameplay, items)
tools/fetch-sources.mjs    # unduh + parse tabel ID resmi -> tools/sources/*.json
tools/build-index.mjs      # gabungkan ikon + sumber -> data/index.json
tools/translate.mjs        # terjemahkan nama -> data/lang/<kode>.json (dengan cache)
```

## Sumber data nama

Nama entri diambil dari sumber resmi:

- `https://developers.mini1.cn/wiki/data_files/blockdef.html` (block, 中文)
- `https://developers.mini1.cn/wiki/data_files/itemdef.html` (item, 中文)
- `https://developers.mini1.cn/wiki/data_files/monster.html` (monster, 中文)
- `https://wiki.miniworldgame.com/doku.php?id=developer_center:developer_editor:script:itemid`
  (English, 2071 nama)

Ikon berasal dari folder `data/<kategori>/icons_cache` yang sudah ada di repo.
Nama pada bahasa selain English dan 中文 adalah **terjemahan mesin** (dibuat saat build,
tersimpan di `data/lang/`, bukan hasil terjemahan resmi).

> 273 entri belum punya nama resmi (237 ID blok tinggi 150000–390022 dan 36 ikon
> creature 13165–13199). Entri tetap ditampilkan dengan label *belum ada nama*.

## Build ulang data

Jalankan berurutan setiap kali ikon atau sumber berubah:

```bash
node tools/fetch-sources.mjs     # unduh tabel ID resmi -> tools/sources/*.json
node tools/build-index.mjs       # -> data/index.json
node tools/translate.mjs         # -> data/lang/*.json (semua bahasa)
node tools/translate.mjs id ja   # atau hanya bahasa tertentu
```

`tools/translate.mjs` menyimpan cache di `tools/sources/translations.cache.json`, jadi
terjemahan yang sama tidak dikirim ulang. Bila `data/index.json` berubah, `sig` di dalam
`data/lang/*.json` tidak cocok lagi dan halaman otomatis kembali ke English untuk bahasa
tersebut — jalankan ulang `translate.mjs` untuk memperbaruinya.

## Bahasa

English, 中文, Bahasa Indonesia, Español, Português, Français, 日本語, Русский
(pilihan bahasa ada di pojok kanan atas; pilihan tersimpan di `localStorage`).
