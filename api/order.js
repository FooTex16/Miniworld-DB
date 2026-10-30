'use strict';
/* POST /api/order — susun no urut satu kategori.

   body = {cat, map:{id: no}} untuk menyusun, atau {cat, reset:true} untuk
   mengembalikan ke nomor asli (nomor asli disimpan di entri sebagai no0). */

const L = require('./_lib');

module.exports = async function (req, res) {
  if (req.method !== 'POST') {
    return L.json(res, 405, { ok: false, error: 'hanya POST yang diterima' });
  }
  await L.tulis(req, res, async body => {
    const cat = String(body.cat || '');
    const op = body.reset ? { t: 'order', cat: cat, reset: true }
                          : { t: 'order', cat: cat, map: body.map || {} };
    const out = await L.jalankan([op], 'No urut ' + cat + (body.reset ? ' (reset)' : ''));
    return { db: out.db, cat: cat, n: (out.hasil[0] || {}).n || 0, reset: !!body.reset };
  });
};
