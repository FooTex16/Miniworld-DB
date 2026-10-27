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
tools/local-db/            # server localhost (baca DATA\, lihat bagian berikut)
tools/icon-scanner/        # pemindai ikon (scan.py -> Miniworld-Scanner.exe)
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

## Database lokal (`tools/local-db`)

Versi localhost yang membaca **folder `DATA\` di luar repo** (bukan `data/index.json`),
dengan tampilan mengikuti halaman situs. Seluruh UI — tombol, judul, saran pencarian,
catatan, modal, toast, label kategori dan grup — diterjemahkan ke 8 bahasa di atas, dan
setiap bahasa murni (tidak ada campur 中文/lainnya kecuali istilah yang memang harus
tetap asli, mis. `English`, `中文`, nama path, kode berkas).

```bash
cd tools/local-db
python -X utf8 server.py --port 8777
# lalu buka http://127.0.0.1:8777/
```

### Struktur kategori

Kategori = folder: `DATA\<indu>\<kategori>`. Yang di bawah 4 folder induk (`Blocks`,
`Creature`, `Gameplay`, `items`) menjadi **sub kategori** — di sidebar sub hanya muncul
setelah induknya dipilih, selain itu disembunyikan.

Urutan sub kategori per induk disimpan di `DATA\sub_urut.json`: buka cabangnya, tekan
**Urutkan sub kategori**, klik sub satu per satu (yang pertama jadi No.1, kedua No.2, …),
lalu **Terapkan urutan**. Tombol **Urutan asli** mengembalikannya ke urutan folder.
Chips `No.N` tampil di sidebar hanya bila ada urutan custom.

### Endpoint

| Method | Path | Isi |
|---|---|---|
| GET  | `/api/db` | `{meta, entries}` — meta memuat `parents` (indu + anak), `categories`, `subOrder`, `noCustom`, `total` |
| GET  | `/api/lang/<kode>.json` | nama terjemahan, selaras urutan `entries` |
| GET  | `/api/icon/<kat>/<id>.webp` | ikon |
| POST | `/api/delete` | `{"items":[{"cat":"Blocks/Terrain","i":123}]}` → pindah ke `DATA\_trash` |
| POST | `/api/order` | `{"cat":"Blocks/Terrain","map":{"100":1}}` → `DATA\no_urut.json` (reset: `{"cat":…,"reset":true}`) |
| POST | `/api/rename` | `{"cat":"Blocks/Natural","i":133,"e":"…","z":"…"}` — hanya field `e`/`z` |
| POST | `/api/cat_order` | `{"parent":"Blocks","order":["Natural","Terrain",…]}` → `DATA\sub_urut.json` |

### Auto-reload

`GET /api/db` membandingkan sidik (`sha1` atas size+mtime tiap file `data_id/`,
`entries.json`, `icon_webp/`, `no_urut.json`, `sub_urut.json`, `nama_sync.json`,
`manifest.json`) dengan sidik terakhir. Bila `DATA\` di luar server (mis. hasil scanner
baru) mengalami perubahan, data di-reload otomatis — tidak perlu restart server.

### Hasil edit nama → antrian translate

`POST /api/rename` menulis `data_id\entries.json` kategori tsb, lalu menyalin nilai baru
ke `data/index.json` dan `data/lang/*.json` (hanya nilai kosong atau yang persis sama
dengan nama English lama, sehingga hasil terjemahan mesin tidak tertimpa). Jumlah bahasa
yang dianggap usang dikembalikan sebagai `res.stale`, dan antrian langkah berikutnya
dicatat ke `DATA\nama_sync.json`.

### Tampilan

Tiga mode di toolbar: **Kartu** (ikon + nama + label grup + No.N + ID), **Ikon** (hanya
ikon), **Daftar** (baris rapat). Tombol **Sembunyikan navigasi** (`.layout.nav-off`)
menyingkirkan sidebar agar daftar entri tampil lebar penuh. Centang multi untuk melihat
jumlah **duplikat** / **unik**, tombol **HAPUS**, mode **Ubah no urut** (per kartu atau
berurutan lalu **Terapkan no urut**), dan **Game** untuk urut persis seperti di game.

### Berkas di `tools/local-db`

```
server.py      # server HTTP + endpoint di atas
app/index.html # markup + CSS (diambil dari halaman situs)
app/app.js     # logika UI, saringan, mode urut, i18n
app/i18n.js    # kamus en + id (158 kunci)
app/i18n-more.js # kamus zh, es, pt, fr, ja, ru (158 kunci per bahasa)
```

Semua kunci di `i18n-more.js` identik dengan `i18n.js` (jumlah, urutan, placeholder, dan
urutan tag HTML), divalidasi oleh:

```bash
node tools/local-db/check_i18n.js
```

