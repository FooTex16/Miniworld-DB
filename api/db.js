'use strict';
/* GET /api/db — sumber data situs LIVE (baca dari repo GitHub).

   Klien mencoba endpoint ini lebih dulu; bila gagal (mis. GH_TOKEN belum
   diisi) ia jatuh ke data/db.json statis sehingga situs tetap tampil
   sekaligus memblokir tombol tulis. Jawaban disimpan CDN sebentar supaya
   tidak setiap kunjungan memanggil GitHub. */

const L = require('./_lib');

module.exports = async function (req, res) {
  if (req.method !== 'GET') {
    return L.json(res, 405, { ok: false, error: 'hanya GET yang diterima' });
  }
  if (!L.konfigOk()) {
    return L.json(res, 503, {
      ok: false,
      error: 'backend belum dikonfigurasi — isi GH_TOKEN & GH_REPO di Vercel',
    });
  }
  try {
    const { db } = await L.bacaDb();
    L.json(res, 200, db, {
      'Cache-Control': 'public, s-maxage=15, stale-while-revalidate=60',
    });
  } catch (err) {
    L.gagal(res, err);
  }
};
