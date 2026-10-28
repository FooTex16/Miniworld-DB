// Validasi kamus i18n: semua bahasa harus punya kunci, placeholder, dan tag HTML
// yang identik dengan en, plus aturan kemurnian (tidak ada aksara CJK yang tidak
// disengaja di bahasa Latin).
//
//   node tools/local-db/check_i18n.js
//
// Exit 0 = lulus, exit 1 = ada masalah (dicetak satu per satu).
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const ROOT = path.join(__dirname, '..', '..');   // kamus ada di root repo
const ctx = { window: {} };
vm.createContext(ctx);
for (const f of ['i18n.js', 'i18n-more.js']) {
  vm.runInContext(fs.readFileSync(path.join(ROOT, f), 'utf8'), ctx, { filename: f });
}
const D = ctx.window.MWDB_I18N || {};

const LOKAL = ['en', 'id', 'zh', 'es', 'pt', 'fr', 'ja', 'ru'];
const en = Object.keys(D.en || {});
let bad = 0;
const fail = m => { console.log('  GAGAL ' + m); bad++; };

if (en.length !== 171) fail(`jumlah kunci en = ${en.length}, diharapkan 171`);

for (const L of LOKAL) {
  if (!D[L]) { fail(`${L} tidak ada`); continue; }
  const k = Object.keys(D[L]);
  const hilang = en.filter(x => !(x in D[L]));
  const lebih = k.filter(x => !en.includes(x));
  const kosong = k.filter(x => !String(D[L][x]).trim());
  const ph = s => (String(s).match(/\{(\w+)\}/g) || []).slice().sort().join(',');
  const bedaPh = en.filter(x => ph(D.en[x]) !== ph(D[L][x]));
  const tags = s => (String(s).match(/<\/?[a-z][^>]*>/gi) || []).join('|');
  const bedaTag = en.filter(x => tags(D.en[x]) !== tags(D[L][x]));
  const cjk = ['en', 'es', 'pt', 'fr', 'ru'].includes(L)
    ? k.filter(x => /[\u3040-\u30ff\u4e00-\u9fff]/.test(String(D[L][x]).replace(/中文/g, '')))
    : [];
  // teks rusak: karakter non-ASCII terganti '?' saat file ditulis (sejarahnya
  // lewat PowerShell yang meng-encode non-ASCII jadi tanda tanya).
  // '?' menempel huruf (tambi?n), beruntun (??????), atau terpisah spasi lalu
  // huruf (Mode tamu ? hanya...) tidak pernah sah. Tanda '?' yang sah selalu
  // diikuti akhir kalimat: kutip, newline, atau akhir string.
  const rusakQ = k.filter(x => /\?[\?0-9a-z]|\s\?\s[^\n]/i.test(String(D[L][x])));
  const pergantian = k.filter(x => String(D[L][x]).includes('\uFFFD'));
  const nonAscii = k.filter(x => /[\u0080-\uffff]/.test(String(D[L][x])));
  const rasio = k.length ? (nonAscii.length / k.length) : 0;
  // zh/ja/ru wajib mayoritas non-Latin; hampir nol berarti aksaranya hilang semua.
  const wajibNonAscii = ['zh', 'ja', 'ru'].includes(L);

  console.log(`[${L}] kunci=${k.length} hilang=${hilang.length} tambahan=${lebih.length} ` +
    `kosong=${kosong.length} placeholder=${bedaPh.length} tagHTML=${bedaTag.length} cjk=${cjk.length} ` +
    `rusakTandaTanya=${rusakQ.length} pergantian=${pergantian.length} nonLatin=${Math.round(rasio * 100)}%`);
  if (hilang.length) fail(`${L} hilang: ${hilang.join(', ')}`);
  if (lebih.length) fail(`${L} tambahan: ${lebih.join(', ')}`);
  if (kosong.length) fail(`${L} kosong: ${kosong.join(', ')}`);
  if (bedaPh.length) fail(`${L} placeholder beda: ${bedaPh.join(', ')}`);
  if (bedaTag.length) fail(`${L} tag HTML beda: ${bedaTag.join(', ')}`);
  if (cjk.length) fail(`${L} ada aksara CJK: ${cjk.join(', ')}`);
  if (rusakQ.length) fail(`${L} teks rusak ('?' menempel huruf/ganda): ${rusakQ.join(', ')}`);
  if (pergantian.length) fail(`${L} ada karakter pergantian U+FFFD: ${pergantian.join(', ')}`);
  if (wajibNonAscii && rasio < 0.2) {
    fail(`${L} hanya ${Math.round(rasio * 100)}% nilai non-Latin (aksara hilang semua?)`);
  }
}

console.log(bad ? `\nADA ${bad} MASALAH` : `\nSEMUA BAHASA LULUS (${LOKAL.length} x ${en.length} kunci)`);
process.exit(bad ? 1 : 0);
