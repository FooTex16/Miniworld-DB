'use strict';
/* POST /api/rename — ubah nama block (hanya field e / z).

   Kunci admin diverifikasi ulang di server; tanpa kunci yang benar GitHub
   tidak pernah disentuh. Hasilnya berisi db segar supaya klien tidak perlu
   memuat ulang (dan tidak terkena jawaban CDN yang basi). */

const L = require('./_lib');

module.exports = async function (req, res) {
  if (req.method !== 'POST') {
    return L.json(res, 405, { ok: false, error: 'hanya POST yang diterima' });
  }
  await L.tulis(req, res, async body => {
    const out = await L.jalankan(
      [{ t: 'rename', cat: body.cat, i: body.i, e: body.e, z: body.z }],
      'Sunting nama ' + String(body.cat) + ' #' + String(body.i));
    const h = out.hasil[0] || {};
    return { db: out.db, changed: h.changed || [], cat: body.cat, i: body.i };
  });
};
