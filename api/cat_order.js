'use strict';
/* POST /api/cat_order — susun urutan sub kategori satu cabang.

   body = {parent, order:[nama]} atau {parent, reset:true}. */

const L = require('./_lib');

module.exports = async function (req, res) {
  if (req.method !== 'POST') {
    return L.json(res, 405, { ok: false, error: 'hanya POST yang diterima' });
  }
  await L.tulis(req, res, async body => {
    const parent = String(body.parent || '');
    const op = body.reset ? { t: 'cat_order', parent: parent, reset: true }
                          : { t: 'cat_order', parent: parent, order: body.order || [] };
    const out = await L.jalankan([op],
      'Urut sub kategori ' + parent + (body.reset ? ' (reset)' : ''));
    return { db: out.db, parent: parent, n: (out.hasil[0] || {}).n || 0 };
  });
};
