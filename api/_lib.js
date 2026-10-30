'use strict';
/* =========================================================================
   api/_lib.js — util bersama untuk fungsi serverless Vercel.

   Peran: membuat situs LIVE bisa disunting admin (ubah nama, no urut, hapus
   entri, urut sub kategori) supaya perubahan tersimpan di repo GitHub dan
   terlihat oleh semua pengunjung, tanpa server sendiri.

   Penyimpanan = berkas `data/db.json` di repo. Setiap perubahan menjadi
   SATU commit lewat Contents API GitHub, sehingga riwayatnya bisa dilihat
   dan dibatalkan (revert) langsung di GitHub. Berkas lain (data/index.json,
   data/lang/*) tidak disentuh di sini — `tools/local-db/export_live.py`
   menyinkronkannya pada ekspor berikutnya sambil MEMPERTAHANKAN suntingan
   dari situs (lihat kolom editNama / no0 / situsHapus / situsUrut).

   Variabel lingkungan (dashboard Vercel -> Settings -> Environment
   Variables, lalu Redeploy):

     GH_TOKEN    token GitHub berizinkan "Contents: Read and write" untuk
                 repo ini saja (fine-grained personal access token)
     GH_REPO     nama repo, mis. "FooTex16/Miniworld-DB"
     GH_BRANCH   cabang tujuan (opsional, default "main")

   Keamanan
   --------
   Setiap endpoint tulis MEMERIKSA ULANG kunci admin di server (hash SHA-256
   yang sama dengan auth.js). Menyembunyikan tombol di klien tidak cukup:
   tanpa kunci yang benar, GitHub tidak pernah disentuh sama sekali.
   ========================================================================= */

const crypto = require('crypto');

/* Hash kunci — HARUS sama dengan H_ADMIN/H_GUEST di auth.js.
   Kalau kunci diganti, perbarui keduanya sekaligus. */
const H_ADMIN = 'f48e574e72f19008465c977bf00d5d129c09bfdbb3480471e2c07225fec03a43';
const H_GUEST = 'bded0732a2d8a76bc1a0cfd512ad1d6b86fcb9b59dbe7ba01427d174a0ccd7e1';

const PATH_DB = 'data/db.json';
const API_GH = 'https://api.github.com';
const MAKS_BADAN = 1024 * 1024;        // tolak permintaan lebih dari 1 MB
const MAKS_NAMA = 120;
const MAKS_HAPUS = 500;                // sekali hapus paling banyak 500 entri

/* ---------------------------------------------------------------- env --- */

function env() {
  const token = process.env.GH_TOKEN;
  const repo = process.env.GH_REPO;
  const cabang = process.env.GH_BRANCH || 'main';
  if (!token || !repo || String(repo).indexOf('/') < 0) return null;
  const i = String(repo).indexOf('/');
  return {
    token: String(token),
    owner: String(repo).slice(0, i),
    nama: String(repo).slice(i + 1),
    cabang: String(cabang),
  };
}

function konfigOk() { return env() !== null; }

/* --------------------------------------------------------------- kunci -- */

/* Persis seperti normalisasi() di auth.js: huruf besar, buang selain
   alfanumerik, sisipkan tanda hubung tiap 5 huruf. */
function normalisasi(raw) {
  const a = String(raw == null ? '' : raw).toUpperCase().replace(/[^A-Z0-9]/g, '');
  if (!a) return '';
  return (a.match(/.{1,5}/g) || []).join('-');
}

function hashKunci(raw) {
  const n = normalisasi(raw);
  if (!n) return '';
  return crypto.createHash('sha256').update(n, 'utf8').digest('hex');
}

function sama(a, b) {
  const ba = Buffer.from(String(a), 'utf8');
  const bb = Buffer.from(String(b), 'utf8');
  return ba.length === bb.length && crypto.timingSafeEqual(ba, bb);
}

function peran(kunci) {
  const h = hashKunci(kunci);
  if (!h) return null;
  if (sama(h, H_ADMIN)) return 'admin';
  if (sama(h, H_GUEST)) return 'guest';
  return null;
}

/* Kunci dikirim lewat header x-mwdb-key (bukan query string — query bisa
   tersimpan di log). */
function kunciDari(req) {
  const h = req.headers || {};
  return h['x-mwdb-key'] || h['X-MWDB-KEY'] || '';
}

function butuhAdmin(req) {
  if (peran(kunciDari(req)) !== 'admin') {
    throw new Http(401, 'kunci admin tidak sah');
  }
}

/* ------------------------------------------------------------- respon --- */

class Http extends Error {
  constructor(status, pesan) {
    super(pesan);
    this.status = status;
  }
}

function json(res, status, obj, tambahan) {
  const hdr = Object.assign({
    'Content-Type': 'application/json; charset=utf-8',
    'Cache-Control': 'no-store',
    'x-mwdb-mode': 'live',            // dipakai app.js untuk mengenali mode
  }, tambahan || {});
  for (const k of Object.keys(hdr)) res.setHeader(k, hdr[k]);
  res.statusCode = status;
  res.end(JSON.stringify(obj));
}

function gagal(res, err) {
  const status = (err && err.status) || 400;
  const pesan = (err && err.message) || String(err);
  if (status >= 500) console.error('[mwdb] galat:', err);
  json(res, status, { ok: false, error: pesan });
}

function bacaBody(req) {
  return new Promise((resolve, reject) => {
    let n = 0;
    const potongan = [];
    req.on('data', c => {
      n += c.length;
      if (n > MAKS_BADAN) {
        reject(new Http(413, 'permintaan terlalu besar'));
        req.destroy();
        return;
      }
      potongan.push(c);
    });
    req.on('end', () => {
      const teks = Buffer.concat(potongan).toString('utf8');
      if (!teks) return resolve({});
      try { resolve(JSON.parse(teks)); }
      catch (_) { reject(new Http(400, 'body bukan JSON yang sah')); }
    });
    req.on('error', () => reject(new Http(400, 'gagal membaca body')));
  });
}

/* -------------------------------------------------------------- github -- */

async function gh(path, opt) {
  const e = env();
  if (!e) throw new Http(503, 'backend GitHub belum dikonfigurasi (GH_TOKEN / GH_REPO)');
  const res = await fetch(API_GH + path, Object.assign({
    headers: {
      'Authorization': 'Bearer ' + e.token,
      'Accept': 'application/vnd.github+json',
      'X-GitHub-Api-Version': '2022-11-28',
      'User-Agent': 'miniworld-db-api',
    },
  }, opt || {}));
  const teks = await res.text();
  let body = null;
  try { body = teks ? JSON.parse(teks) : null; } catch (_) { body = null; }
  if (!res.ok) {
    const pesan = (body && (body.message || body.error)) || ('HTTP ' + res.status);
    throw new Http(pesanDari(res.status, res.headers.get('x-ratelimit-remaining')), pesan);
  }
  return body;
}

/* Kuota GitHub habis -> beri tahu user, jangan menyamar sebagai galat biasa. */
function pesanDari(status, sisa) {
  return (status === 403 && sisa === '0') ? 429 : status;
}

const jalurRepo = () => {
  const e = env();
  return '/repos/' + e.owner + '/' + e.nama;
};

/* Baca isi sebuah berkas dari repo, lengkap dengan sha blob-nya. */
async function bacaIsi(path) {
  const e = env();
  const r = await gh(jalurRepo() + '/contents/' + path +
                     '?ref=' + encodeURIComponent(e.cabang));
  if (!r || r.type !== 'file' || !r.sha) {
    throw new Http(404, path + ' tidak ditemukan di repo');
  }
  if (r.content && r.encoding === 'base64') {
    return { sha: r.sha, teks: Buffer.from(r.content, 'base64').toString('utf8') };
  }
  // berkas 1-100 MB: Contents API tidak mengembalikan isi di objek,
  // jadi ambil ulang sebagai berkas mentah.
  const res = await fetch(API_GH + jalurRepo() + '/contents/' + path +
                          '?ref=' + encodeURIComponent(e.cabang), {
    headers: {
      'Authorization': 'Bearer ' + e.token,
      'Accept': 'application/vnd.github.raw+json',
      'X-GitHub-Api-Version': '2022-11-28',
      'User-Agent': 'miniworld-db-api',
    },
  });
  if (!res.ok) throw new Http(res.status, 'gagal membaca ' + path);
  return { sha: r.sha, teks: await res.text() };
}

async function bacaJson(path) {
  const f = await bacaIsi(path);
  try { return { sha: f.sha, obj: JSON.parse(f.teks) }; }
  catch (_) { throw new Http(500, path + ' bukan JSON yang sah'); }
}

async function bacaDb() {
  const f = await bacaJson(PATH_DB);
  const db = f.obj;
  if (!db || !Array.isArray(db.entries) || typeof db.meta !== 'object') {
    throw new Http(500, PATH_DB + ' tidak berbentuk {meta, entries}');
  }
  return { sha: f.sha, db };
}

/* Daftar berkas di sebuah folder (dipakai untuk memuat semua data/lang/*.json). */
async function daftarBerkas(path) {
  const e = env();
  const r = await gh(jalurRepo() + '/contents/' + path +
                     '?ref=' + encodeURIComponent(e.cabang));
  if (!Array.isArray(r)) return [];
  return r.filter(x => x.type === 'file' && /\.json$/i.test(x.name))
          .map(x => x.path);
}

/* Catat perubahan sebagai satu commit (satu berkas). */
async function tulisDb(db, pesan) {
  return tulisBerkas([{ path: PATH_DB, teks: teksDb(db) }], pesan);
}

function teksDb(db) {
  const teks = JSON.stringify(db, null, 2) + '\n';
  const ukuran = Buffer.byteLength(teks, 'utf8');
  /* tulisBerkas mengirim isi sebagai BLOB base64 (x 4/3), bukan lewat
     Contents API — 3 MB teks menjadi ~4 MB permintaan. Dipasang sebagai margin
     supaya ada jarak tumbuh: data/db.json kini ~540 KB, jadi batas ini baru
     tercapai setelah database berkembang hampir 6x lipat. Bila suatu hari kena,
     perbesar konstanta ini, jangan menonaktifkan pemeriksaannya. */
  const MAKS_TEKS = 3 * 1024 * 1024;
  if (ukuran > MAKS_TEKS) {
    throw new Http(507, PATH_DB + ' terlalu besar untuk dikirim sebagai blob (' +
      Math.round(ukuran / 1024) + ' KB, batas aman ' + Math.round(MAKS_TEKS / 1024) +
      ' KB — ada di api/_lib.js)');
  }
  return teks;
}

/* Commit beberapa berkas SEKALIGUS lewat Git Data API.

   Dibutuhkan supaya perubahan bersifat atomik: menghapus satu entri harus
   ikut membuang barisnya dari data/index.json dan data/lang/*.json, atau
   urutan nama terjemahan bergeser dan sig dianggap basi — akibatnya semua
   bahasa non-Inggris mendadak jatuh ke English untuk semua entri. */
async function tulisBerkas(daftar, pesan) {
  const e = env();
  const base = jalurRepo();

  const ref = await gh(base + '/git/ref/heads/' + encodeURIComponent(e.cabang));
  const kepala = ref && ref.object && ref.object.sha;
  if (!kepala) throw new Http(500, 'tidak bisa membaca cabang ' + e.cabang);
  const info = await gh(base + '/git/commits/' + kepala);

  const pohon = [];
  for (const f of daftar) {
    const b = await gh(base + '/git/blobs', {
      method: 'POST',
      body: JSON.stringify({
        content: Buffer.from(String(f.teks), 'utf8').toString('base64'),
        encoding: 'base64',
      }),
    });
    pohon.push({ path: f.path, mode: '100644', type: 'blob', sha: b.sha });
  }

  const tree = await gh(base + '/git/trees', {
    method: 'POST',
    body: JSON.stringify({ base_tree: info.tree.sha, tree: pohon }),
  });
  const baru = await gh(base + '/git/commits', {
    method: 'POST',
    body: JSON.stringify({ message: pesan, tree: tree.sha, parents: [kepala] }),
  });
  await gh(base + '/git/refs/heads/' + encodeURIComponent(e.cabang), {
    method: 'PATCH',
    body: JSON.stringify({ sha: baru.sha }),
  });
  return baru.sha;
}

/* --------------------------------------------------------- penyelaras --- */

/* Sama persis dengan sig() di app.js dan js_sig() di server.py: djb2 atas
   daftar id, base36, uint32. Kalau berubah, seluruh data/lang dianggap basi
   dan terjemahan dibuang. */
function sigId(idList) {
  let h = 5381;
  const s = idList.join(',');
  for (let i = 0; i < s.length; i++) h = ((h << 5) + h + s.charCodeAt(i)) >>> 0;
  return h.toString(36);
}

/* Bangun daftar berkas yang ikut berubah bila urutan entri bergeser
   (hapus entri). Mengembalikan [{path, teks}]. */
async function berkasSelaras(idLama, idBaru, db) {
  const posisi = [];
  for (const id of idBaru) posisi.push(idLama.indexOf(id));
  if (posisi.some(p => p < 0)) {
    // ada entri baru yang tidak ada di berkas lama — biarkan export lokal
    // yang menyelaraskannya, di sini hanya buang baris yang kebetulan ada.
    for (let k = posisi.length - 1; k >= 0; k--) {
      if (posisi[k] < 0) posisi.splice(k, 1);
    }
  }
  const daftar = [];

  const idx = await bacaJson('data/index.json').catch(() => null);
  if (idx && Array.isArray(idx.obj.entries)) {
    const lama = idx.obj.entries;
    idx.obj.entries = posisi.map(p => (p < lama.length ? lama[p] : null))
                            .filter(Boolean);
    idx.obj.meta = idx.obj.meta || {};
    idx.obj.meta.total = db.meta.total;
    idx.obj.meta.named = db.meta.named;
    idx.obj.meta.withIcon = db.meta.withIcon;
    idx.obj.meta.categories = (db.meta.categories || []).map(c => ({
      key: c.key, label: c.label, count: c.count, withIcon: c.withIcon,
    }));
    idx.obj.meta.parents = (db.meta.parents || []).map(p => ({
      key: p.key, count: p.count, withIcon: p.withIcon,
    }));
    daftar.push({ path: 'data/index.json', teks: JSON.stringify(idx.obj, null, 2) + '\n' });
  }

  const sig = sigId(idBaru);
  const nama = await daftarBerkas('data/lang').catch(() => []);
  for (const path of nama) {
    const f = await bacaJson(path).catch(() => null);
    if (!f || !Array.isArray(f.obj.n)) continue;
    const lama = f.obj.n;
    f.obj.n = posisi.map(p => (p < lama.length ? lama[p] : null));
    f.obj.sig = sig;
    daftar.push({ path: path, teks: JSON.stringify(f.obj, null, 2) + '\n' });
  }
  return daftar;
}

/* ---------------------------------------------------------------- data -- */

const angka = v => (Number.isFinite(+v) ? +v : 0);

function cariEntri(db, cat, i) {
  const iid = angka(i);
  return db.entries.find(e => e.c === cat && angka(e.i) === iid) || null;
}

function perKategori(db) {
  const per = new Map();
  for (const e of db.entries) {
    if (!per.has(e.c)) per.set(e.c, []);
    per.get(e.c).push(e);
  }
  return per;
}

/* Hitung ulang seluruh nilai turunan: jumlah, gno, noMax, noCustom, parents.
   Urutan kategori mengikuti meta.categories (sudah memperhitungkan urutan
   sub kategori buatan user), sama seperti load_db() di server.py. */
function hitungMeta(db) {
  const per = perKategori(db);
  const lama = Array.isArray(db.meta.categories) ? db.meta.categories : [];
  const urut = lama.map(c => c.key);
  for (const k of per.keys()) if (urut.indexOf(k) < 0) urut.push(k);

  let g = 0;
  const cats = [];
  for (const k of urut) {
    const list = per.get(k);
    if (!list) continue;
    list.sort((a, b) => (angka(a.no) - angka(b.no)) || (angka(a.i) - angka(b.i)));
    for (const e of list) e.gno = ++g;

    const induk = k.indexOf('/') >= 0 ? k.split('/')[0] : k;
    const sub = k.indexOf('/') >= 0 ? k.slice(k.indexOf('/') + 1) : k;
    const asal = lama.find(c => c.key === k) || {};
    const noMax = list.length
      ? Math.max.apply(null, list.map(e => angka(e.no))) : 0;
    const noCustom = list.some(e => e.custom);
    cats.push(Object.assign({}, asal, {
      key: k,
      parent: asal.parent || induk,
      name: asal.name || sub,
      label: asal.label || k,
      count: list.length,
      withIcon: list.filter(e => e.p).length,
      noMax: noMax,
      noCustom: noCustom,
      breadcrumb: asal.breadcrumb || k.replace('/', ' > '),
    }));
  }
  db.meta.categories = cats;
  db.meta.total = db.entries.length;
  db.meta.withIcon = db.entries.filter(e => e.p).length;
  db.meta.named = db.entries.filter(e => e.e || e.z).length;
  db.meta.noMaxAll = cats.reduce((m, c) => Math.max(m, angka(c.noMax)), 0);
  db.meta.noCustom = cats.filter(c => c.noCustom).map(c => c.key);

  const parents = [];
  for (const c of cats) {
    let p = parents.find(x => x.key === c.parent);
    if (!p) {
      p = { key: c.parent, label: c.parent, count: 0, withIcon: 0, children: [] };
      parents.push(p);
    }
    p.count += c.count;
    p.withIcon += c.withIcon;
    p.children.push(c.key);
  }
  db.meta.parents = parents;
}

/* ------------------------------------------------------- operasi tulis --- */

/* Tiap operasi menandai suntingannya sendiri supaya export lokal bisa
   memutuskan nilai mana yang menang (lihat export_live.py):

     editNama  berkas {e: <nama lokal saat diganti>, z: <nama lokal saat
               diganti>} — bila data lokal berubah setelah itu, kunci dilepas
               dan data lokal kembali menang.
     no0       nomor asli entri sebelum no urut disunting di situs.
     situsHapus  daftar [kategori, id] yang dihapus lewat situs.
     situsUrut   urutan sub kategori per cabang yang disusun di situs.       */

function opRename(db, o) {
  const e = cariEntri(db, o.cat, o.i);
  if (!e) throw new Http(404, 'id ' + o.i + ' tidak ada di ' + o.cat);

  const ubah = {};
  for (const k of ['e', 'z']) {
    if (o[k] == null) continue;
    if (typeof o[k] !== 'string') throw new Http(400, k + ' harus teks');
    const s = o[k].replace(/\s+/g, ' ').trim();
    if (s.length > MAKS_NAMA) {
      throw new Http(400, k + ' terlalu panjang (maks ' + MAKS_NAMA + ' karakter)');
    }
    if (s !== (e[k] || '')) ubah[k] = s;
  }
  if (!Object.keys(ubah).length) return { changed: [] };

  // Tanda "field ini pernah diedit di situs": export lokal TIDAK boleh
  // menimpanya (kesepakatan: suntingan situs dipertahankan). Kuncinya per
  // field supaya menyalin z tidak ikut mengunci e. Untuk melepas dan kembali
  // ke hasil scan, hapus kunci itu dari data/db.json.
  const kunci = (e.editNama && typeof e.editNama === 'object') ? e.editNama : {};
  for (const k of Object.keys(ubah)) kunci[k] = 1;
  e.editNama = kunci;
  Object.assign(e, ubah);

  return { changed: Object.keys(ubah), cat: o.cat, i: angka(o.i) };
}

function opOrder(db, o) {
  const cat = o.cat;
  if (!cat || typeof cat !== 'string') throw new Http(400, 'cat wajib diisi');
  const list = db.entries.filter(e => e.c === cat);
  if (!list.length) throw new Http(404, 'kategori tidak dikenal: ' + cat);

  if (o.reset) {
    for (const e of list) {
      if (e.no0 != null) { e.no = e.no0; delete e.no0; }
      e.custom = false;
    }
    const subs = db.meta.subOrder;
    if (subs && typeof subs === 'object') delete subs[cat.split('/')[0]];
    return { reset: true, cat: cat, n: list.length };
  }

  const map = o.map;
  if (!map || typeof map !== 'object') throw new Http(400, 'map wajib diisi');
  let n = 0;
  for (const e of list) {
    const v = map[e.i];
    if (v == null) continue;
    const no = angka(v);
    if (no < 1) throw new Http(400, 'no urut tidak sah: ' + v);
    if (e.no0 == null) e.no0 = e.no;        // simpan nomor asli sekali saja
    e.no = no;
    n++;
  }
  if (!n) throw new Http(400, 'tidak ada entri yang cocok di ' + cat);
  for (const e of list) e.custom = true;    // seluruh kategori = disunting
  return { cat: cat, n: n };
}

function opDelete(db, o) {
  const items = o.items;
  if (!Array.isArray(items) || !items.length) throw new Http(400, 'items kosong');
  if (items.length > MAKS_HAPUS) {
    throw new Http(400, 'terlalu banyak entri sekaligus (maks ' + MAKS_HAPUS + ')');
  }
  const r = {};
  for (const it of items) {
    const cat = String((it && it.cat) || '');
    const e = cariEntri(db, cat, it && it.i);
    if (!e) throw new Http(404, 'id ' + (it && it.i) + ' tidak ada di ' + cat);
    r[cat + '/' + angka(it.i)] = e;
  }
  const kunci = Object.keys(r);
  db.entries = db.entries.filter(e => kunci.indexOf(e.c + '/' + angka(e.i)) < 0);

  // catat sebagai "hapus dari situs" supaya export lokal tidak menghidupkan
  // lagi entri yang sama dari hasil scan
  if (!Array.isArray(db.meta.situsHapus)) db.meta.situsHapus = [];
  const ada = new Set(db.meta.situsHapus.map(x => x[0] + '/' + angka(x[1])));
  for (const k of kunci) {
    const p = k.lastIndexOf('/');
    if (!ada.has(k)) db.meta.situsHapus.push([k.slice(0, p), angka(k.slice(p + 1))]);
  }
  return { deleted: kunci.length };
}

function opCatOrder(db, o) {
  const parent = o.parent;
  if (!parent || /[\\/.]/.test(parent)) throw new Http(400, 'parent tidak sah');
  const subs = Array.isArray(db.meta.categories) ? db.meta.categories : [];
  const punya = subs.filter(c => c.parent === parent);
  if (!punya.length) throw new Http(404, 'cabang tidak dikenal: ' + parent);

  const semua = punya.map(c => c.name);
  let nama;
  if (o.reset) {
    nama = semua.slice().sort();
  } else {
    if (!Array.isArray(o.order) || !o.order.length) throw new Http(400, 'urutan kosong');
    nama = o.order.map(String);
    if (new Set(nama).size !== nama.length) throw new Http(400, 'ada nama kembar di urutan');
    const salah = nama.filter(x => semua.indexOf(x) < 0);
    if (salah.length) throw new Http(400, 'sub kategori tidak ada di ' + parent + ': ' + salah.join(', '));
    // yang tidak diklik user menyusul di belakang (alfabet) — sama dengan server.py
    nama = nama.concat(semua.filter(x => nama.indexOf(x) < 0).sort());
  }

  // Susun ulang: kelompokkan per cabang, pertahankan urutan cabang apa adanya,
  // hanya isi dalam cabang target yang dibalik.
  const grup = [];
  for (const c of subs) {
    let g = grup.find(x => x.parent === c.parent);
    if (!g) { g = { parent: c.parent, list: [] }; grup.push(g); }
    g.list.push(c);
  }
  const pos = new Map(nama.map((x, i) => [x, i]));
  for (const g of grup) {
    if (g.parent === parent) g.list.sort((a, b) => pos.get(a.name) - pos.get(b.name));
  }
  db.meta.categories = grup.reduce((acc, g) => acc.concat(g.list), []);

  if (!db.meta.subOrder || typeof db.meta.subOrder !== 'object') db.meta.subOrder = {};
  // Penanda: subOrder saja TIDAK cukup karena field itu juga diisi oleh
  // export_live.py dari sub_urut.json lokal. Tanpa penanda terpisah, ekspor
  // berikutnya tidak bisa membedakan urutan yang disusun di situs dari urutan
  // yang disusun di localhost — dan salah satu pasti akan tertimpa.
  if (!db.meta.situsUrut || typeof db.meta.situsUrut !== 'object') db.meta.situsUrut = {};
  if (o.reset) {
    delete db.meta.subOrder[parent];
    delete db.meta.situsUrut[parent];
  } else {
    db.meta.subOrder[parent] = nama;
    db.meta.situsUrut[parent] = nama;
  }

  return { parent: parent, n: nama.length, reset: !!o.reset };
}

const OPERASI = {
  rename: opRename,
  order: opOrder,
  delete: opDelete,
  cat_order: opCatOrder,
};

/* Terapkan satu operasi lalu tandai waktu suntingan situs. */
function terapkan(db, op) {
  const fn = OPERASI[op && op.t];
  if (!fn) throw new Http(400, 'operasi tidak dikenal: ' + (op && op.t));
  const hasil = fn(db, op) || {};
  hitungMeta(db);
  db.meta.situs = new Date().toISOString();
  return hasil;
}

/* Baca -> terapkan -> tulis ulang, dengan ulang coba bila ada yang commit
   di antaranya (Contents API menjawab 409, pembaruan ref menjawab 422). */
async function jalankan(ops, pesan, opsi) {
  const sinkronUrutan = !!(opsi && opsi.selaraskanUrutan);
  for (let upaya = 0; upaya < 3; upaya++) {
    const { sha, db } = await bacaDb();
    const idLama = db.entries.map(e => e.i);
    const hasil = [];
    for (const op of ops) hasil.push(terapkan(db, op));

    const daftar = [{ path: PATH_DB, teks: teksDb(db) }];
    const idBaru = db.entries.map(e => e.i);
    if (sinkronUrutan && idBaru.join(',') !== idLama.join(',')) {
      daftar.push.apply(daftar, await berkasSelaras(idLama, idBaru, db));
    }
    try {
      const baru = await tulisBerkas(daftar, pesan);
      return { db: db, sha: baru, hasil: hasil, files: daftar.length };
    } catch (err) {
      const bentrok = err.status === 409 || err.status === 422;
      if (!bentrok || upaya === 2) throw err;
    }
  }
  throw new Http(409, 'terlalu banyak penyunting bersamaan, coba lagi');
}

/* --------------------------------------------------------- penjaga umum -- */

/* Semua endpoint tulis melewati ini: konfigurasi + kunci admin + body. */
async function tulis(req, res, buat) {
  if (!konfigOk()) {
    return json(res, 503, {
      ok: false,
      error: 'backend belum dikonfigurasi — isi GH_TOKEN & GH_REPO di Vercel',
    });
  }
  try {
    butuhAdmin(req);
    const body = await bacaBody(req);
    const out = await buat(body);
    json(res, 200, Object.assign({ ok: true }, out));
  } catch (err) {
    gagal(res, err);
  }
}

module.exports = {
  Http, json, gagal, bacaBody, tulis,
  konfigOk, env, peran, normalisasi, hashKunci,
  bacaDb, tulisDb, terapkan, jalankan, hitungMeta,
  sigId, berkasSelaras, daftarBerkas,
};
