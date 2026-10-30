/* MiniWorld DB — gerbang akses (kunci TAMU dan ADMIN).

   Sebelum data database dimuat, user dimasukkan kunci dulu:

     TAMU   telusuri, cari, ganti bahasa/tampilan, klik kartu = salin ID
     ADMIN  semua fitur tamu + filter, rentang no urut, urutkan sub kategori,
            hapus, ubah no urut, dan ubah nama block

   Kunci aslinya TIDAK ada di berkas ini — yang tersimpan hanya hash SHA-256
   (H_GUEST / H_ADMIN). Peran diturunkan ulang dari kunci setiap kali halaman
   dimuat, jadi mengubah variabel peran lewat devtools tidak berguna: tanpa
   kunci admin yang benar, peran tidak mungkin jadi "admin".

   Kunci plaintext disimpan terpisah (di luar repo) dan hanya kunci tamu yang
   dibagikan. Bila kunci admin bocor, ganti kedua kunci + kedua hash ini.   */
(() => {
  'use strict';

  const KUNCI_STORAGE = 'mwdb.key';        // localStorage

  /* ---------- SHA-256 (hanya input ASCII) ---------- */

  const K = [
      0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5,
      0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
      0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3,
      0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
      0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc,
      0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
      0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7,
      0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
      0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13,
      0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
      0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3,
      0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
      0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5,
      0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
      0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208,
      0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2,
  ];

  function sha256hex(msg) {
    const bytes = [];
    for (let i = 0; i < msg.length; i++) {
      const c = msg.charCodeAt(i);
      if (c > 0xff) return '';            // kunci harus ASCII
      bytes.push(c);
    }
    const bitLen = bytes.length * 8;
    bytes.push(0x80);
    while (bytes.length % 64 !== 56) bytes.push(0);
    bytes.push(0, 0, 0, 0,
      (bitLen >>> 24) & 0xff, (bitLen >>> 16) & 0xff,
      (bitLen >>> 8) & 0xff, bitLen & 0xff);

    const H = [0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a,
               0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19];
    const rr = (x, n) => (x >>> n) | (x << (32 - n));

    for (let off = 0; off < bytes.length; off += 64) {
      const w = new Array(64);
      for (let i = 0; i < 16; i++) {
        w[i] = (bytes[off + i * 4] << 24) | (bytes[off + i * 4 + 1] << 16) |
               (bytes[off + i * 4 + 2] << 8) | bytes[off + i * 4 + 3];
      }
      for (let i = 16; i < 64; i++) {
        const s0 = rr(w[i - 15], 7) ^ rr(w[i - 15], 18) ^ (w[i - 15] >>> 3);
        const s1 = rr(w[i - 2], 17) ^ rr(w[i - 2], 19) ^ (w[i - 2] >>> 10);
        w[i] = (w[i - 16] + s0 + w[i - 7] + s1) | 0;
      }
      let a = H[0], b = H[1], c = H[2], d = H[3];
      let e = H[4], f = H[5], g = H[6], h = H[7];
      for (let i = 0; i < 64; i++) {
        const S1 = rr(e, 6) ^ rr(e, 11) ^ rr(e, 25);
        const ch = (e & f) ^ (~e & g);
        const t1 = (h + S1 + ch + K[i] + w[i]) | 0;
        const S0 = rr(a, 2) ^ rr(a, 13) ^ rr(a, 22);
        const maj = (a & b) ^ (a & c) ^ (b & c);
        const t2 = (S0 + maj) | 0;
        h = g; g = f; f = e; e = (d + t1) | 0;
        d = c; c = b; b = a; a = (t1 + t2) | 0;
      }
      H[0] = (H[0] + a) | 0; H[1] = (H[1] + b) | 0;
      H[2] = (H[2] + c) | 0; H[3] = (H[3] + d) | 0;
      H[4] = (H[4] + e) | 0; H[5] = (H[5] + f) | 0;
      H[6] = (H[6] + g) | 0; H[7] = (H[7] + h) | 0;
    }
    return H.map(x => (x >>> 0).toString(16).padStart(8, '0')).join('');
  }

  /* ---------- kunci ---------- */

  const H_GUEST  = 'bded0732a2d8a76bc1a0cfd512ad1d6b86fcb9b59dbe7ba01427d174a0ccd7e1';
  const H_ADMIN  = 'f48e574e72f19008465c977bf00d5d129c09bfdbb3480471e2c07225fec03a43';

  /* kunci ditulis huruf besar, dipisah tanda hubung per 5 huruf;
     user boleh mengetiknya apa adanya (spasi, huruf kecil, tanpa hubung) */
  function normalisasi(raw) {
    const a = String(raw == null ? '' : raw).toUpperCase().replace(/[^A-Z0-9]/g, '');
    if (!a) return '';
    return (a.match(/.{1,5}/g) || []).join('-');
  }

  function peranDari(kunci) {
    if (!kunci) return null;
    const h = sha256hex(kunci);
    if (h === H_ADMIN) return 'admin';
    if (h === H_GUEST) return 'guest';
    return null;
  }

  function t(key) {
    const d = window.MWDB_I18N || {};
    const lang = (document.documentElement && document.documentElement.lang) ||
      (window.localStorage && localStorage.getItem('mwdb.lang')) || 'en';
    if (d[lang] && d[lang][key] != null) return d[lang][key];
    if (d.en && d.en[key] != null) return d.en[key];
    if (d.id && d.id[key] != null) return d.id[key];
    return key;
  }

  function bacaKunci() {
    try { return localStorage.getItem(KUNCI_STORAGE) || ''; } catch (_) { return ''; }
  }
  function simpanKunci(k) {
    try { localStorage.setItem(KUNCI_STORAGE, k); } catch (_) { /* mode privat */ }
  }
  function hapusKunci() {
    try { localStorage.removeItem(KUNCI_STORAGE); } catch (_) { /* mode privat */ }
  }

  /* ---------- layar login ---------- */

  let selesaikan = null;                 // resolver promise tentukan()

  function kunciScroll(on) {
    if (document.documentElement) document.documentElement.style.overflow = on ? 'hidden' : '';
  }

  function tampilLogin() {
    const w = document.getElementById('loginwrap');
    if (!w) return;
    w.hidden = false;
    kunciScroll(true);
    const inp = document.getElementById('loginKey');
    if (inp) { inp.value = ''; inp.focus(); }
  }

  function sembunyiLogin() {
    const w = document.getElementById('loginwrap');
    if (w) w.hidden = true;
    kunciScroll(false);
  }

  function salahPesan(pesan) {
    const err = document.getElementById('loginErr');
    if (err) { err.textContent = pesan; err.hidden = false; }
    const inp = document.getElementById('loginKey');
    if (inp) { inp.focus(); inp.select(); }
  }

  function cobaMasuk() {
    const inp = document.getElementById('loginKey');
    const kunci = normalisasi(inp ? inp.value : '');
    const peran = peranDari(kunci);
    if (!peran) { salahPesan(t('login.err')); return; }

    simpanKunci(kunci);
    const err = document.getElementById('loginErr');
    if (err) { err.hidden = true; err.textContent = ''; }
    sembunyiLogin();
    if (selesaikan) { const selesai = selesaikan; selesaikan = null; selesai(peran); }
  }

  function pasang() {
    const btn = document.getElementById('loginBtn');
    const inp = document.getElementById('loginKey');
    const err = document.getElementById('loginErr');
    if (err) err.hidden = true;
    if (btn) btn.addEventListener('click', cobaMasuk);
    if (inp) {
      inp.addEventListener('keydown', ev => {
        ev.stopPropagation();             // jangan kena jalan pintas app.js
        if (ev.key === 'Enter') { ev.preventDefault(); cobaMasuk(); }
      });
      inp.addEventListener('input', () => { if (err) err.hidden = true; });
    }
  }
  if (typeof document !== 'undefined' && document.getElementById) pasang();

  /* ---------- API untuk app.js ---------- */

  // Resolve begitu kunci valid diketahui (langsung dari penyimpanan,
  // atau setelah user menekan tombol Masuk). Tidak pernah resolve null.
  function tentukan() {
    const tersimpan = bacaKunci();
    const awal = peranDari(tersimpan);
    if (awal) { sembunyiLogin(); return Promise.resolve(awal); }
    if (tersimpan) hapusKunci();         // kunci sudah tidak berlaku
    tampilLogin();
    return new Promise(resolve => { selesaikan = resolve; });
  }

  function keluar() {
    hapusKunci();
    location.reload();
  }

  /* Kunci yang sedang dipakai, HANYA bila berperan admin. Disertai pada setiap
     permintaan tulis supaya server bisa memverifikasi ulang — menyembunyikan
     tombol di klien tidak cukup. Kunci tamu tidak pernah dikirim karena
     memang tidak akan diterima. */
  function kunciAdmin() {
    const kunci = bacaKunci();
    return peranDari(kunci) === 'admin' ? kunci : null;
  }

  window.MWDB_AUTH = { tentukan, keluar, kunciAdmin, sha256hex, normalisasi, peranDari };
})();
