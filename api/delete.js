'use strict';
/* POST /api/delete — hapus entri terpilih.

   Penting: menghapus entri menggeser urutan baris di data/index.json dan
   data/lang/*.json. Bila keduanya tidak ikut diselaraskan, sig terjemahan
   dianggap basi dan SEMUA bahasa non-Inggris mendadak jatuh ke English
   untuk seluruh entri. Karena itu hapus memakai commit atomik multi-berkas
   (lihat _lib.berkasSelaras) — data/icon sengaja dibiarkan; berkasnya
   yatim dan akan dibuang oleh export_live.py pada ekspor berikutnya. */

const L = require('./_lib');

module.exports = async function (req, res) {
  if (req.method !== 'POST') {
    return L.json(res, 405, { ok: false, error: 'hanya POST yang diterima' });
  }
  await L.tulis(req, res, async body => {
    const items = Array.isArray(body.items) ? body.items : [];
    const kunci = items.map(x => String((x && x.cat) || '') + '#' + String((x && x.i) || ''));
    const out = await L.jalankan(
      [{ t: 'delete', items: items }],
      'Hapus ' + items.length + ' entri (' + kunci.slice(0, 8).join(', ') +
        (kunci.length > 8 ? ', …' : '') + ')',
      { selaraskanUrutan: true });
    return { db: out.db, deleted: (out.hasil[0] || {}).deleted || 0, files: out.files };
  });
};
