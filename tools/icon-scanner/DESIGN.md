# Desain Otomasi: Scanner Ikon & ID Block dari Library Backpack (Mini World)

Status: **DRAF v2 — disesuaikan dengan screenshot UI asli** · belum ada kode build.

---

## 0. Referensi screenshot

| # | Isi screenshot |
|---|----------------|
| S1 | Panel library terbuka: `Blocks > Terrian`, tombol `+ Add` / `Minature` / search `Please enter`, rail kategori kiri (ikon gunung aktif hijau), grid 10 kolom × 4 baris penuh + baris ke-5 **terpotong**, hotbar `Pack` + 3 titik halaman di bawah, tombol `X` tutup di kanan-atas |
| S2 | Hover satu cell → muncul **tooltip gelap**: ikon kecil (±64 px) + nama tebal putih (`Grassy Soil Block`) + chip kategori hijau (`Terrian`) + deskripsi/resep + `Press Alt key to show more` |
| S3 | Setelah **klik**: cell ter-pick, ditandai **border kuning/kuning-emas** pada cell, tooltip masih terbuka, ikon terlihat "siap di-drag" |
| S4 | Hasil yang diinginkan: **ikon block bersih** (crop dari cell, tanpa latar cell) |

---

## 1. Tujuan

```
untuk tiap cell di grid 10 x 4 (baris penuh saja, baris terpotong di-skip):
    hover  → tooltip muncul
    crop nama dari tooltip → OCR (English) → simpan nama
    crop ikon cell        → simpan gambar (opsi: buang latar)
    klik cell             → block ter-pick, border kuning muncul
    baca memori 0x2C00EA08 (uint32) → ID block
    klik titik aman (di dalam panel) → pick hilang
setelah cell ke-40:
    bunyi + overlay "geser layar, lalu tekan F9" → lanjut halaman berikutnya
```

Keluaran per entri (`output/scan.jsonl`):

```json
{"page": 1, "row": 0, "col": 3, "cx": 745, "cy": 288,
 "name": "Grassy Soil Block", "category": "Terrian",
 "id": 3, "icon": "icons/p001_r00c03_3.png",
 "ocr_conf": 0.96, "pick_ok": true, "id_stable": true, "ts": 1793020800}
```

---

## 2. Gambaran UI & pembagian region (hasil kalibrasi)

Semua koordinat di bawah adalah **estimasi dari screenshot 1919×1079** dan wajib
diukur ulang lewat kalibrasi di layar asli (resolusi/window mode bisa beda).

```
┌──────────────────────────── panel (≈ x215..1710, y115..870) ───────────────────────────┐
│  [avatar] Blocks > Terrian            [+ Add] [Minature] [🔍 Please enter]        (X) │
│ ┌──────┐ ┌──────────────────── GRID: 10 x 4 baris penuh ────────────────────┐  ┌─────┐ │
│ │ rail │ │ c(0,0) c(1,0) … c(9,0)   pitch ≈ 130px, cell ≈ 115px            │  │sbr  │ │
│ │ kate-│ │ c(0,1) …                ┌─────────────────────────┐             │  │ol   │ │
│ │ gori │ │ c(0,2) …                │ TOOLTIP (muncul saat    │             │  │     │ │
│ │      │ │ c(0,3) …                │  hover) ikon+nama+chip  │             │  │     │ │
│ │      │ │ ▓▓ baris ke-5 TERPOTONG ▓│ +deskripsi (jangan      │             │  │     │ │
│ └──────┘ └─────────────────────────┘  dijadikan target scan) ┘             │  └─────┘ │
│  [Pack] [▶][hotbar 8 slot][▶]        • • •  (3 titik halaman)                            │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

| Region | Fungsi | Ditandai dengan |
|--------|--------|-----------------|
| `grid_rect` | area 10 × 4 yang discan | 4 **baris penuh** saja; baris terpotong di bawah di luar rect |
| `rail` | rail kategori kiri — **tidak pernah diklik** | di luar `grid_rect` |
| `header` | `+ Add`, `Minature`, search | area kandidat **titik aman** untuk klik clear |
| `tooltip` | panel info hover | dideteksi dinamis (template match), bukan offset tetap |
| `safe_clear` | titik klik untuk melepas pick | wajib **di dalam panel** (jangan di dunia di luar panel!) |
| `close(X)` | tombol tutup | **zona larangan** — jangan sampai tersentuh |
| `scrollbar` | scrollbar grid di kanan | dipakai untuk scroll halaman (wheel di atas grid) |

---

## 3. Alur per cell (revisi: ada siklus pick → clear)

```
0 ms    mouse → pusat cell (jitter ±3 px supaya natural)
150ms   tunggu tooltip render (default 400ms)
400ms   DETEKSI tooltip (template match ikon kecil / panel gelap)
        ├─ gagal → retry 2× (hover ulang + 400ms) → gagal lagi: name=null, tetap lanjut
        └─ ok  → crop baris NAMA  → preprocess → OCR eng → "Grassy Soil Block"
560ms   crop isi cell → icons/p{page}_r{r}c{c}_{id}.png  (+ opsi buang latar → transparan)
620ms   klik cell (pick)
780ms   VERIFIKASI pick: template border kuning harus muncul di cell itu
        └─ tidak muncul → klik ulang (maks 2×) → tetap gagal: PAUSE + screenshot debug
860ms   baca memori 0x2C00EA08 (uint32 LE), dibaca 2× harus identik
        └─ nilai di luar 0..400000 / tidak berubah / tetap sama dengan cell sebelumnya
            padahal nama beda → PAUSE
920ms   pindah mouse ke titik AMAN (di dalam panel) → klik → pick hilang
1100ms  VERIFIKASI clear: border kuning hilang dari semua cell
1200ms  append JSONL → cell berikutnya
```

**≈ 1,2–1,5 dtk per cell → 40 cell ≈ 50–60 detik per halaman.**

### Optimisasi yang diuji di Fase 0 (bila berhasil, hemat ±400 ms/cell)

1. **Klik langsung ke cell berikutnya** (tanpa titik clear) — kalau game otomatis melepas
   pick lama saat cell baru diklik. Rancangan awal Anda menyebut *perlu clear dulu*, jadi
   ini wajib diuji, bukan diasumsikan.
2. **Hover-only** untuk nama: kalau ID ternyata ikut berubah saat hover (tanpa klik),
   klik & clear bisa dihilangkan sama sekali.
3. Tooltip ternyata menutupi cell target → geser offset hover ke **sudut kiri-atas cell**
   (di luar area tooltip) — divalidasi dengan `pick_ok`.

### Aturan validasi

| Pemeriksaan | Aksi bila gagal |
|-------------|-----------------|
| Tooltip terdeteksi & OCR menghasilkan teks | retry 2× → `name=null`, tetap catat ikon + ID |
| Border kuning muncul setelah klik (pick_ok) | retry 1× → PAUSE + simpan screenshot debug |
| `id` uint32 wajar `0..400000` | PAUSE |
| `id` berubah antar cell (atau identik **dan** nama identik) | PAUSE — kemungkinan klik meleset / pick tidak terbaca |
| Pick hilang setelah klik titik aman (clear_ok) | retry 1× → PAUSE (risiko: pick nyangkut & menyebar ke sel berikutnya) |
| 3 cell gagal berturut-turut | PAUSE, minta intervensi manusia |

---

## 4. Deteksi grid 10 × 4 & pergantian halaman

### Kalibrasi sekali (F6)

1. User klik **kiri-atas** dan **kanan-bawah** area grid (4 baris penuh) → `grid_rect`.
2. Tool menghitung pitch dengan autocorrelation lalu **snap** ke 10 kolom × 4 baris:
   `cell_w = grid_w/10`, `cell_h = grid_h/4`, `center(r,c) = origin + ((c+.5)·cell_w, (r+.5)·cell_h)`.
3. Overlay 40 kotak + nomor `r,c` di layar 3 dtk → user tekan **F7** kalau meleset, F8 kalau pas.
4. Sekaligus kalibrasi: **titik aman clear**, **template border kuning**, **template tooltip**,
   dan **template sel kosong** (ambil dari cell yang jelas kosong).

### Ganti halaman (manual, sesuai pilihan Anda)

> "tidak selalu 10 × 4 block yang ada, tapi posisikan saja seperti itu"
> → `grid_rect` **tetap**; yang berubah hanya isi slot saat scroll.

1. Setelah cell (3,9) → buzzer + overlay: **"Geser layar (scroll halaman library) lalu tekan F9"**
   (scroll dilakukan **user**, paling aman).
2. Sebelum lanjut: **re-align check** — crop penanda tepi slot kiri-atas di-cocokkan ke
   template, geser maksimal 8 px diizinkan. Lebih dari itu → PAUSE, minta kalibrasi ulang.
3. Page counter +1 → ulangi loop.
4. Selesai: 2 halaman berturut-turut **semua cell kosong**, atau user tekan **F10**.

### Deteksi cell kosong (di-skip, tanpa hover/klik)

- `cv2.matchTemplate(cell_crop, template_sel_kosong)` → skor > 0.92 ⇒ kosong.
- Cadangan: variance piksel sangat rendah + tooltip tidak muncul setelah hover 500 ms.

### Aturan deteksi baris/kolom (jangan dilonggarkan sembarangan)

Baris dicari dengan sampling kolom vertikal `diff[y_lo:y_hi, x]`:

- **D sampel di SEMUA kolom** (2 titik tiap sel: 35% & 65% lebar sel, menghindari
  garis pemisah). Sampling cuma 3 kolom (0, 5, 9) dulu menyebabkan satu baris
  kelewat begitu selnya kosong/kontras rendah → jarak antar baris jadi ~2× pitch
  dan validasi gagal terus dengan pesan `jarak baris 270px (pitch 141px)`.
- Tinggi segmen wajib `0.75 × pitch … 1.06 × pitch`: terpendek = baris terpotong,
  terpanjang = rail/garis pemisah (≈2 baris) → keduanya dibuang.
- `min_h = pitch - 16` (dulu) terlalu ketat: margin cuma 4px, satu baris 120px
  padahal pitch 141px sudah gugur.

> **Peringatan tipe:** sel hasil deteksi berbentuk `float`, jadi `rect` dan
> `cfg["grid"]["x"/"y"]` ikut float. Nilai itu dipakai sebagai batas slicing
> numpy (`diff[y:y, x]`) dan `ImageGrab.grab(bbox=...)` →
> `TypeError: slice indices must be integers or None or have an __index__ method`.
> Karena `detect_and_check()` menangkap pengecualian itu, gejalanya bukan crash
> melainkan **deteksi gagal terus-menerus walaupun grid sudah pas**.
> Semua koordinat grid wajib lewat `norm_grid()` (dipanggil saat load config,
> di akhir `apply_grid_op()`, dan saat snap ke deteksi), plus `int()` defensif
> di setiap situs slicing.

---

## 5. Membaca memori

```python
addr = 0x2C00EA08
v1 = read_u32(pid, addr)     # ReadProcessMemory, 4 byte little-endian
v2 = read_u32(pid, addr)     # dibaca lagi, wajib v1 == v2
```

Bila `0x2C00EA08` tidak stabil (ASLR/build beda), urutan fallback:

1. `module_base + (0x2C00EA08 - base_awal)` — kalau ternyata offset tetap terhadap module.
2. Pointer/AOB scan pola di sekitar → simpan rantai `[[[module+o1]+o2]+o3]` di `config.json`.
3. Bila tetap gagal → opsi terakhir: **OCR ID dari layar** (hanya kalau ada panel yang
   menampilkan ID setelah pick — pada screenshot tidak terlihat, jadi memory tetap utama).

### Kolom **ALAMAT PICK ID** di HUD

Karena alamat bisa berbeda antar build/versi game, tersedia kolom isian di pita
bawah HUD (di antara daftar *TERAKHIR TERSIMPAN* dan tombol kontrol, x 1168–1390):

| Elemen | Fungsi |
|---|---|
| isian `0x…` | alamat pick-id; terisi otomatis dari `config.json` saat mulai |
| **SET ALAMAT** | kirim alamat ke thread scan untuk divalidasi |
| baris status | `OK terbaca -> 0x…` bila berhasil, `DITOLAK: <alasan>` bila gagal |
| baris `nilai = N` | pembacaan terkini di alamat itu, diperbarui terus selagi menunggu tombol |

* Alamat hanya **dipakai bila benar-benar bisa dibaca** (`ReadProcessMemory`
  harus berhasil) — jadi SET langsung membuktikan *id bisa terbaca*. Kalau gagal,
  alamat aktif tidak berubah dan alasannya tampil di baris status.
* Alamat yang diterima **ditulis ke `config.json`** (tulis ulang atomik, kunci
  bantu `_…` tidak ikut), jadi run berikutnya — termasuk versi EXE — memakai
  alamat yang sama.
* Boleh diganti kapan saja: antrean `Ctrl.mem_q` dikuras tiap sel scan, di
  gerbang halaman, dan di loop utama, sehingga perubahan berlaku untuk sel
  berikutnya.
* Saat kolom diklik, `WS_EX_NOACTIVATE` di pita bawah dilepas sebentar dan
  jendela diangkat ke foreground memakai `AttachThreadInput` — tanpa ini sistem
  membuang ketikan (pita atas/outline tetap click-through & tidak bisa diketik).
  Setelah SET berhasil, fokus dikembalikan ke jendela game.

**Fase 0 wajib:** probe 1 cell — hover, klik, baca nilai 20× selama 2 detik.
Nilai harus berubah mengikuti cell yang dipick. Belum lulus → jangan lanjut ke Fase 1.

---

## 6. Konfigurasi (`config.json`)

```jsonc
{
  "process": "",                         // kosong = cari otomatis / ditanya user
  "grid": { "x": 355, "y": 220, "w": 1310, "h": 550, "cols": 10, "rows": 4 },
  "cell_inset": 8,                       // padding crop ikon di dalam cell
  "icon": { "trim": true, "remove_bg": true, "out_size": 128 },
  "tooltip": { "template": "assets/tpl_tooltip.png", "name_box": [92, 14, 340, 34] },
  "safe_clear": { "x": 1000, "y": 160 }, // di dalam panel, di luar grid & tombol
  "mem": { "addr": "0x2C00EA08", "type": "u32", "ptr_chain": [] },
  "timing": { "hover_ms": 150, "tooltip_ms": 400, "settle_ms": 180,
              "jitter_ms": 80, "realign_tol_px": 8 },
  "ocr": { "engine": "tesseract", "langs": "eng", "scale": 2, "invert": true },
  "hotkey": { "calibrate": "F6", "grid_ok": "F7", "tooltip_ok": "F8",
              "next_page": "F9", "stop": "F10" },
  "output": { "dir": "output", "icons": "output/icons",
              "jsonl": "output/scan.jsonl", "shots": "output/debug" }
}
```

**Zona larangan (otomatis ditolak saat kalibrasi):** tombol `X` tutup, tombol `+ Add`,
rail kategori, area di luar panel (dunia).

---

## 7. Antarmuka pengawasan

- **Overlay layar** (transparan, selalu di atas): halaman `n`, cell `k/40`, nama hasil OCR
  terakhir, ID terakhir, status pick/clear, jumlah entri & jumlah PAUSE.
- **Hotkey:** F6 kalibrasi, F7 grid-OK, F8 tooltip-OK, F9 halaman berikut, F10 stop;
  failsafe: mouse ke pojok kiri-atas = abort.
- **Resume:** `scan.jsonl` di-append; run ulang otomatis melewati `(page,row,col)` yang sudah ada.
- **Laporan HTML** per halaman: thumbnail + nama + ID → cek cepat konsistensi.
- **`--dry-run`**: semua langkah kecuali klik & baca memori (uji koordinat/OCR).
- **`--max-cells N`**: uji 1–3 cell dulu sebelum full run.

---

## 8. Tahapan build & exit criteria

| Fase | Isi | Exit criteria (wajib lulus) |
|------|-----|-----------------------------|
| **0 Probe** | Cari proses, baca `0x2C00EA08`; uji hover-only vs klik-pick; uji klik-langsung vs clear-dulu | nilai berubah mengikuti cell yang dipick; mekanisme clear terkonfirmasi |
| **1 Kalibrasi** | `grid_rect` 10×4, pitch, titik aman, template (border kuning/tooltip/sel kosong), overlay 40 kotak | 40 overlay tepat di 40 slot (verifikasi user: F7) |
| **2 Satu halaman** | Loop 40 cell: hover→OCR→ikon→pick→baca→clear→log + laporan HTML | ≥38/40 cell tercatat, nama OCR ≥90%, semua ID wajar & unik |
| **3 Antarmuka** | Overlay, hotkey, resume, pause-reason | jalan 10 menit tanpa campur tangan selain F9 |
| **4 Full run** | Multi-halaman + re-align + deteksi selesai | 2 halaman berturut-turut tanpa PAUSE |
| **5 Integrasi** | Ikon → `.webp`, merge `name + id + ikon` ke `data/index.json` repo Miniworld-DB | PR ke repo |

**Prinsip:** satu fase = satu commit; fase berikutnya hanya dibangun kalau exit criteria
fase sebelumnya lulus.

---

## 9. Stack (sudah diputuskan)

- **Python 3.11** — `mss` (capture), `opencv-python` (template match/OCR prep),
  `pytesseract` + Tesseract-OCR **eng**, `numpy`, `ctypes`/`pymem` (ReadProcessMemory & SendInput),
  `keyboard` (hotkey global), `pillow` (icon export).
- Bahasa UI game: **English** → OCR `eng`.
- Ganti halaman: **manual (geser → F9)**.
- ID: **klik → pick → baca memori → klik titik aman untuk clear** (sesuai mekanisme yang
  Anda jelaskan), dengan pengujian di Fase 0 apakah clear bisa dilewati.

## 10. Risiko

- Baca memori proses game = **read-only, tanpa inject**, tapi tetap berpotensi melanggar
  ToS / kena anti-cheat → keputusan & risiko di tangan pengguna.
- Salah klik pada `X`/`+ Add`/rail bisa merusak sesi → mitigasi: zona larangan + titik aman
  yang sudah divalidasi + verifikasi pick/clear tiap cell.
- Tooltip menutupi cell target → mitigasi: deteksi rect tooltip tiap hover & offset sudut cell.
- Resolusi/posisi jendela berubah → re-align check tiap halaman.
