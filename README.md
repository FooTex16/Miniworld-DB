# MiniWorld DB

Katalog ID block, item, gameplay, dan creature Mini World — cari nama (English / 中文 /
Bahasa Indonesia / bahasa lain), lihat ikon, dan klik satu entri untuk menyalin ID-nya.

## Dua mode, satu berkas

`index.html`, `app.js`, `auth.js`, `i18n.js`, dan `i18n-more.js` dipakai bersama oleh dua tempat:

| | Alamat | Sumber data | Aksi tulis |
|---|---|---|---|
| **LIVE** | <https://miniworlddb.vercel.app> | `data/db.json` + `data/icons/` (hasil ekspor) | diblokir → pesan baca-saja |
| **LOCAL** | <http://127.0.0.1:8777/> | `/api/db` yang membaca folder `DATA\` | hapus, ubah nama, ubah no urut aktif |

Mode dibaca dari hostname (`127.0.0.1` / `localhost` / `file://` → LOCAL), lalu
dikonfirmasi lagi waktu data dimuat — kalau tebakan salah, URL dicoba dua-duanya dan
mode dikoreksi. Badge di pojok kiri atas menampilkan **LIVE** (biru) atau **LOCAL**
(hijau); keterangan footer dan pesan galat pun ikut berganti.

Menjalankan berkas LIVE secara lokal (tanpa Vercel):

```bash
python -m http.server 8080     # dijalankan di root repo
# lalu buka http://127.0.0.1:8080/
```

## Halaman login — kunci tamu & admin

Sebelum database dibuka, situs meminta **kunci akses** (`auth.js`). Ada dua kunci:

| Peran | Boleh |
|---|---|
| **Tamu** | menelusuri kategori, mencari, urut **ID / Nama / Game**, ganti bahasa & tampilan, sembunyikan navigasi, **klik entri = salin ID** |
| **Admin** | semua fitur tamu **+** filter (ikon/nama/duplikat/unik), rentang no urut, pilih-banyak & **HAPUS**, **Ubah no urut**, **Urutkan sub kategori**, **UBAH** nama |

Peran diturunkan ulang dari kunci setiap kali halaman dimuat — mengubah variabel
peran lewat devtools tidak berguna. Untuk tamu, semua kontrol admin disembunyikan
lewat atribut `data-req="admin"` (CSS `body:not(.admin) …` — dipilih dari sisi
positif supaya kontrol admin ikut tersembunyi saat layar login, ketika body belum
punya kelas peran) **dan** fungsi-fungsinya dijaga `blokirAdmin()`; tombol
**Keluar** di pojok kanan atas menghapus kunci lalu memuat ulang halaman.

Yang tersimpan di repo hanyalah **hash SHA-256** kedua kunci (`H_GUEST` / `H_ADMIN`
di `auth.js`), bukan kuncinya. Kunci plaintext ditulis di berkas di **luar** repo
(`..\KUNCI-AKSES.txt`) — bagikan hanya kunci tamu.

> Situs ini statis: pembatasan ini mengatur **tampilan & aksi di UI**. Data `data/db.json`
> tetap bisa dibaca siapa pun yang membuka URL-nya langsung, jadi jangan pernah simpan
> rahasia di sana. Bila kunci admin bocor, ganti kedua kunci + kedua hash lalu push.

## Isi repo

```
index.html            # markup + CSS — dipakai LIVE & LOCAL
app.js                # logika UI, saringan, mode urut, i18n, deteksi mode, peran akses
auth.js               # gerbang login: hash SHA-256 kunci tamu + admin
i18n.js               # kamus en + id (171 kunci)
i18n-more.js          # kamus zh, es, pt, fr, ja, ru (171 kunci per bahasa)

data/db.json          # payload {meta, entries}: 1.678 entri, hasil ekspor DATA\
data/index.json       # format situs (id, nama EN/中文, grup, path ikon) — sumber
                      #   nama untuk pipeline translate + pemetaan id -> posisi
data/lang/*.json      # nama per bahasa (id, es, pt, fr, ja, ru), selaras urutan
                      #   data/index.json dan data/db.json (urutannya sama persis)
data/icons/<indu>/<kategori>/<id>.webp   # 1.678 ikon

data_old/             # CADANGAN data situs sebelumnya: 3.063 entri + ikon + lang

tools/local-db/       # server localhost, skrip ekspor ke data/, validasi i18n
tools/icon-scanner/   # pemindai ikon (scan.py -> Miniworld-Scanner.exe)
tools/*.mjs           # pipeline build data LAMA — kini menulis ke data_old/
tools/sources/        # tabel ID resmi hasil unduh + cache terjemahan
```

## Sumber data nama

Nama entri diambil dari sumber resmi:

- `https://developers.mini1.cn/wiki/data_files/blockdef.html` (block, 中文)
- `https://developers.mini1.cn/wiki/data_files/itemdef.html` (item, 中文)
- `https://developers.mini1.cn/wiki/data_files/monster.html` (monster, 中文)
- `https://wiki.miniworldgame.com/doku.php?id=developer_center:developer_editor:script:itemid`
  (English, 2071 nama)

Nama pada bahasa selain English dan 中文 adalah **terjemahan mesin** (tersimpan di
`data/lang/`, bukan hasil terjemahan resmi).

Ikon LIVE disalin dari `DATA\<indu>\<kategori>\icon_webp\` ke `data/icons/` waktu ekspor —
semua 1.678 entri punya nama maupun ikon. Data situs lama (3.063 entri, 894 berikon, 273
di antaranya belum punya nama resmi) tetap utuh di `data_old/`.

## Perbarui data LIVE

Database di `data/` adalah **cuplikan** dari folder `DATA\` yang dipakai server localhost.
Setiap kali database berubah (scan baru, hapus entri, ubah nama), ekspor ulang lalu commit:

```bash
python tools/local-db/export_live.py
git add -A
git commit -m "Perbarui data LIVE"
git push           # Vercel deploy otomatis
```

Skrip ini menyalin entri + ikon ke `data/`, membangun ulang `data/index.json` dan
`data/lang/*.json` (terjemahan lama dipetakan lewat id, jadi hasil rename tidak hilang),
membuang ikan yatim, dan memperbarui tanggal pada keterangan
*Database update terakhir …*. Tidak perlu server berjalan.

Pipeline lama (`tools/fetch-sources.mjs` → `tools/build-index.mjs` →
`tools/translate.mjs`) kini menulis ke `data_old/` dan hanya dipakai untuk merawat arsip —
**jangan** diarahkan ke `data/`, karena urutan `entries` di sana harus sama dengan
`data/db.json`.

```bash
node tools/fetch-sources.mjs     # unduh tabel ID resmi -> tools/sources/*.json
node tools/build-index.mjs       # -> data_old/index.json
node tools/translate.mjs         # -> data_old/lang/*.json
```

## Bahasa

English, 中文, Bahasa Indonesia, Español, Português, Français, 日本語, Русский
(pilihan bahasa ada di pojok kanan atas; pilihan tersimpan di `localStorage`).

**Bahasa otomatis mengikuti bahasa peramban** saat pertama dibuka: `navigator.languages[0]`
dicocokkan ke daftar di atas (subtag utama saja — `zh-CN`/`zh-TW` → `zh`, `pt-BR` → `pt`,
`in` → `id`). Kalau bahasa default di luar pilihan (`de`, `ar`, `ko`, …) atau peramban tidak
memberi tahu apa pun, halaman dibuka dalam **English**. Pilihan yang sudah dipilih user
selalu menang atas deteksi otomatis.

Seluruh UI diterjemahkan — tombol, judul, saran pencarian, catatan, modal, toast, label
kategori dan grup — dan setiap bahasa murni (tidak ada campur 中文/lainnya kecuali istilah
yang memang harus tetap asli, mis. `English`, `中文`, nama path, kode berkas).

## Database lokal (`tools/local-db`)

Versi localhost membaca **folder `DATA\` di luar repo** (bukan `data/`), dengan tampilan
mengikuti halaman situs. Selain fitur baca, versi lokal menambah pilih-banyak, penanda
duplikat, tombol hapus, ubah no urut, dan ubah nama block.

```bash
cd tools/local-db
python -X utf8 server.py --port 8777
# atau klik dua kali start.bat
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

### Berkas

```
tools/local-db/server.py       # server HTTP + endpoint di atas
tools/local-db/export_live.py  # ekspor DATA\ -> data/ untuk situs LIVE
tools/local-db/check_i18n.js   # validasi 8 x 171 kunci i18n + kemurnian teks
tools/local-db/start.bat       # jalankan server + buka browser
tools/local-db/README.md       # dokumentasi lengkap versi localhost
index.html, app.js, auth.js, i18n*.js   # UI — ada di root repo, dipakai LIVE & LOCAL
```

Seluruh kamus i18n (8 bahasa × 171 kunci) wajib identik jumlah, urutan, placeholder,
dan urutan tag HTML-nya — divalidasi oleh:

```bash
node tools/local-db/check_i18n.js
```

Validator juga memeriksa **kemurnian teks**: nilai yang berisi karakter pergantian
`U+FFFD`, atau `?` yang menempel huruf / beruntun / diapit spasi lalu huruf
(`tambi?n`, `??????`, `Mode tamu ? hanya`) dianggap rusak. Aturan ini pernah
menangkap 46 nilai terjemahan yang aksaranya hilang karena skrip sisip lama
menulis file lewat PowerShell (non-ASCII ter-encode jadi `?`).
