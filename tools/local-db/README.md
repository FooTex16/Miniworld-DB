# MiniWorld DB — versi localhost

Tampilannya **sama persis** dengan situs LIVE di Vercel
(<https://miniworlddb.vercel.app>) — keduanya memakai `index.html`, `app.js`, dan
`i18n*.js` yang sama di **root repo**. Bedanya hanya sumber datanya: versi ini
mengambil folder lokal:

```
D:\WORK\MINI WORLD DB\DATA\<indu>\<kategori>\
    data_id\entries.json     daftar entri (id, nama EN/中文, dst.)
    icon_webp\<id>.webp      ikon per entri
```

`<indu>` = folder cabang hasil export: `Blocks`, `Creature`, `items`.
Jadi kategorinya `Blocks\Natural`, `Creature\Animals`, `items\Food`, dst.

Kategori **mengikuti nama folder** — begitu folder baru muncul (hasil scan),
dia otomatis muncul di sidebar tanpa perlu ubah apa pun.

Karena nama kategori boleh kembar antar cabang (`Blocks\Function` dan
`items\Function`), **kunci internal kategori = `<indu>/<nama>`** — kunci inilah
yang dipakai untuk URL ikon, hapus, dan ubah no urut. Tampilan sidebar memakai
`<indu> / <nama>` supaya tidak tertukar. Folder diawali `_` (mis. `_trash`)
dianggap bukan kategori.

Situs Vercel memakai berkas UI yang sama; `server.py` menyajikannya dari root repo
lewat `APP = SITE`, jadi tidak ada salinan yang bisa menyimpang. Badge di topbar
menampilkan **LOCAL** di server ini dan **LIVE** di situs.

## Cara jalankan

Dua cara:

```
start.bat                     ← klik dua kali, server + browser terbuka
```

atau manual:

```
python -X utf8 server.py --port 8777
```

lalu buka **<http://127.0.0.1:8777/>**.

Server hanya mendengarkan di `127.0.0.1` (tidak bisa diakses dari luar).
Stop dengan `Ctrl+C`.

## Fitur

| Fitur | Keterangan |
|---|---|
| Kategori per folder | sidebar = subfolder `DATA\<indu>\<kategori>` |
| Pilih-banyak | centang kartu, atau **Pilih semua hasil** |
| Status duplikat | baris pilihan menampilkan `N dipilih · X duplikat · Y unik` |
| Filter duplikat | **Hanya yang duplikat** / **Hanya yang unik** (sidebar) |
| Tag DUP | border merah + tag `DUP` pada kartu yang kembar |
| **HAPUS** | buang entri terpilih dari `entries.json` + ikonnya |
| **No urut** | rentang nomor urut (`dari` … `s/d`) di sidebar |
| Urut **Game** | tombol sort baru: tampil persis seperti urutan block di game |
| **Ubah no urut** | klik chip `No.N` (satu block) atau mode **Ubah no urut** (banyak block) |
| **Urutan asli** | tombol muncul otomatis bila urutan sudah disunting — kembalikan ke hasil scan |
| **Ubah nama** | tombol `UBAH` pada kartu → jendela isi nama English / 中文 |
| Pencarian / sort / grid-list / 8 bahasa | sama seperti versi Vercel |

### Definisi duplikat

Sebuah entri ditandai **duplikat** bila:

1. **ID-nya muncul di lebih dari satu kategori** (scan ke-loop / ke-scroll), atau
2. **Nama EN/中文-nya sama** dengan entri lain tetapi ID-nya berbeda.

Alasan ini muncul saat hover kartu (tooltip) dan saat menandainya.

### No urut & urutan seperti di game

Tiap kartu memuat chip **`No.N`** — posisi block di dalam kategorinya,
diurutkan **persis seperti urutan aslinya di game**.

* Sumbernya `tools/icon-scanner/output/scan.jsonl`: tiap record menyimpan
  `page` / `row` / `col` saat ikon itu terbaca, jadi urutannya sama dengan yang
  tampil di grid game (`page` → `row` → `col`).
  (`export.py` mengurutkan `entries.json` berdasarkan **ID**, jadi urutan aslinya
  hanya ada di log scan.)
* Entri yang **tidak tercatat** di scan (mis. hasil backfill lama) mendapat nomor
  sisa di belakang, urut ID — supaya tidak ada entri tanpa nomor.
* Nomor **per kategori**; kalau nomornya bolong (entri sempat dihapus) nomor
  tetap dipertahankan, jadi posisinya tidak bergeser.
* Rentang `dari` … `s/d` menyaring nomor tsb. Kosongkan `s/d` untuk *sampai habis*.
  Mengisi rentang otomatis mengaktifkan sort **Game** (selama user belum memilih
  tombol urutnya sendiri); tombol **Semua** mengembalikan ke `1 … habis`.
* Tombol sort **`ID | Nama | Game`**: `Game` mengurutkan memakai nomor urut
  tersebut; pada tampilan **Semua**, kategori disusun per kategori (Natural,
  Terrain, …) — persis seperti tiap tab di game.

#### Mengubah no urut

Ada dua cara, hasilnya sama-sama disimpan ke **`DATA\no_urut.json`**
(menimpa hasil scan, bukan merubah `entries.json` / `scan.jsonl`):

| Cara | Langkah |
|---|---|
| **Satu block** | klik chip `No.N` pada kartu → ketik nomor baru → **Enter** (`Esc` batal). Kalau nomor itu sedang dipakai block lain, keduanya **bertukar** — jadi nomor tidak pernah kembar. |
| **Banyak block** | tekan **Ubah no urut** (wajib pilih satu kategori dulu) → klik kartu **berurutan**: pertama → `No.1`, kedua → `No.2`, … (muncul badge `urut N`) → tekan **Terapkan no urut**. Block yang tidak dipilih menyusul di belakangnya dengan urutan lama, lalu nomor dihitung ulang jadi `1…N` rapat. |

* Masuk mode otomatis memakai sort **Game** supaya urutan yang disusun langsung
  terlihat; badge `urut N` menempel di kartu sampai diterapkan.
* Tombol **Urutan asli** muncul sendiri di baris pilihan begitu kategori itu
  disunting — menekannya menghapus bagian kategori itu dari `no_urut.json`
  dan nomor kembali persis seperti hasil scan.
* Kategori yang sudah disunting ditandai `urutan disunting` pada petunjuk
  `No urut` di sidebar.
* Sisi server menolak nomor kembar, kategori tak dikenal, dan `map` kosong
  (HTTP 400), jadi file tidak pernah tersimpan dalam keadaan rusak.

#### Mengubah nama block

Tekan tombol **`UBAH`** pada kartu (tombol kecil di samping nama, terang saat
kursor di atas kartu) → isi **Nama (English)** dan/atau **Nama (中文)** →
**Simpan**. `Enter` = simpan, `Esc` = batal, klik area gelap juga membatalkan.

* Hasilnya ditulis atomik ke `data_id\entries.json` kategori entri itu;
  `generated` ikut diperbarui.
* Yang boleh diubah hanya `e` (English) dan `z` (中文) — **id, label grup, dan
  OCR tidak bisa diedit**, supaya data hasil scan tetap bisa dibedakan dari
  hasil koreksi manual.
* Nama baru langsung ikut pencarian, sort **Nama**, dan penanda **duplikat**
  (entri dengan nama sama otomatis ditandai kembar).
* Spasi berlebih otomatis dirapikan, batas 120 karakter. Nilai yang sama
  dengan isi lama tidak menulis berkas apa pun.
* Perubahan hanya berlaku di localhost; kalau kategori itu di-ekspor ulang
  oleh scanner, hasil ekspor bisa menimpa koreksinya.

## Endpoint

```
GET  /                        aplikasi
GET  /api/db                  {meta, entries}  dari seluruh cabang DATA\<indu>\
GET  /api/lang/<kode>.json    terjemahan (dipetakan lewat ID dari repo situs)
GET  /api/icon/<indu>%2F<kat>/<id>.webp   kunci kategori di-URL-encode
POST /api/delete              {"items":[{"cat":"Blocks/Terrain","i":123}, ...]}
POST /api/order               {"cat":"Blocks/Terrain","map":{"100":1,...}}  (seluruh kategori)
                              {"cat":"Blocks/Terrain","reset":true}         (urutan asli)
POST /api/rename              {"cat":"Blocks/Natural","i":133,"e":"...","z":"..."}
                              balas {ok, changed:["e","z"], entry, meta}
```

## Hapus & mengembalikan

Entri yang dihapus **tidak dibuang permanen**:

* baris entri dihapus dari `data_id\entries.json`
* ikonnya dipindah ke `DATA\_trash\<indu>\<kategori>\<waktu-stamp>\<id>.webp`
* `DATA\manifest.json` ikut diselaraskan

Mengembalikan: pindahkan lagi ikon ke `icon_webp\`, lalu sisipkan kembali
objek entri di `entries.json` (atau jalankan ulang scan untuk kategori itu).

Data entri yang hilang **selalu masih ada** di
`tools/icon-scanner/output/scan.jsonl` (id, nama EN/中文, OCR, kategori,
`page`/`row`/`col`) — jadi entri yang terlanjur dihapus bisa dipulihkan
100% dengan menggabungkan log scan + ikon di `_trash` + label grup `l`/`s`
dari `data/index.json`.

## Ekspor ke situs LIVE

Situs di Vercel adalah **situs statis** — tidak ada `server.py`, jadi datanya harus
dibawa sebagai berkas. `export_live.py` menyalin isi folder `DATA\` ke `<repo>\data\`:

```bash
python tools/local-db/export_live.py      # tidak perlu server berjalan
```

| Yang ditulis | Isi |
|---|---|
| `data/db.json` | `{meta, entries}` — persis balasan `GET /api/db`, path ikon diganti jadi `data/icons/…` |
| `data/index.json` | format situs (id, nama EN/中文, grup, path) — dipakai `sync_site()` dan `build_langs()` |
| `data/lang/*.json` | `n` dipetakan ulang lewat id dari arsip, `sig` dihitung ulang |
| `data/icons/<indu>/<kategori>/<id>.webp` | 1.678 ikon; ikon yatim dibuang |

`data/index.json` dan `data/db.json` sengaja diurutkan sama, sehingga satu file
`data/lang/*.json` bisa dipakai dua-duanya (posisi `n` untuk server lokal, `sig`
untuk halaman LIVE). Keterangan **Database update terakhir …** di footer ikut
diperbarui ke tanggal ekspor.

Cadangan data situs lama ada di `data_old/` — di situlah `tools/*.mjs` (pipeline
build & translate) menulis sekarang.

Alur memperbarui situs:

```bash
python tools/local-db/export_live.py
git add -A && git commit -m "Perbarui data LIVE" && git push
```

## Berkas di folder ini

```
server.py        # server HTTP + endpoint di atas (APP = root repo)
export_live.py   # ekspor DATA\ -> data/ untuk situs LIVE
check_i18n.js    # validasi 8 x 161 kunci i18n (kamus di root repo)
start.bat        # jalankan server + buka browser
README.md        # berkas ini
```

## Catatan teknis

* Murni Python 3 stdlib — tidak perlu `pip install`.
* Menulis atomik (`*.tmp` + `os.replace`) supaya `entries.json` tidak korup
  bila proses gagal di tengah.
* Nama kategori divalidasi terhadap daftar folder asli (tolak path traversal).
* `no_urut.json` lama memakai kunci telanjang (mis. `Natural`) dari waktu hanya
  `DATA\Blocks` yang dibaca. Saat dibaca kunci itu otomatis dipetakan ke
  `Blocks/Natural`; simpan berikutnya menuliskannya dengan kunci baru.
* Server menyelaraskan `manifest.json` setiap kali start dan setiap hapus.
