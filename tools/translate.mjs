#!/usr/bin/env node
/**
 * translate.mjs
 * -------------
 * Menerjemahkan nama entri di data_old/index.json ke beberapa bahasa
 * lalu menyimpannya di data_old/lang/<kode>.json (perata dengan indeks entri).
 *
 * Catatan: terjemahan untuk data LIVE (<repo>/data/lang) dibuat ulang oleh
 * tools/local-db/export_live.py dengan memetakan id dari arsip ini.
 *
 * Sumber teks: nama Inggris bila ada, kalau tidak nama Mandarin.
 * Hasil mentah di-cache di tools/sources/translations.cache.json supaya
 * pengulangan tidak memanggil layanan terjemahan lagi.
 *
 * Pemakaian:
 *   node tools/translate.mjs            -> semua bahasa
 *   node tools/translate.mjs id es      -> bahasa tertentu
 *
 * Catatan: hasilnya terjemahan mesin (bukan resmi Mini World).
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.join(__dirname, '..');
const CACHE_FILE = path.join(__dirname, 'sources', 'translations.cache.json');
const INDEX_FILE = path.join(ROOT, 'data_old', 'index.json');
const LANG_DIR = path.join(ROOT, 'data_old', 'lang');

const LANGUAGES = [
  { code: 'id', label: 'Bahasa Indonesia', sl: 'auto' },
  { code: 'es', label: 'Español', sl: 'auto' },
  { code: 'pt', label: 'Português', sl: 'auto' },
  { code: 'fr', label: 'Français', sl: 'auto' },
  { code: 'ja', label: '日本語', sl: 'auto' },
  { code: 'ru', label: 'Русский', sl: 'auto' },
];

const BATCH_CHARS = 900; // batas panjang teks per request
const CONCURRENCY = 6;

const index = JSON.parse(fs.readFileSync(INDEX_FILE, 'utf8'));
const cache = fs.existsSync(CACHE_FILE)
  ? JSON.parse(fs.readFileSync(CACHE_FILE, 'utf8'))
  : {};

/** Kunci stabil untuk cache. */
function hash(s) {
  let h = 5381;
  for (let i = 0; i < s.length; i++) h = ((h << 5) + h + s.charCodeAt(i)) >>> 0;
  return h.toString(36);
}

async function translateBatch(strings, lang) {
  const url =
    'https://translate.googleapis.com/translate_a/single?client=gtx' +
    `&sl=${lang.sl}&tl=${lang.code}&dt=t&q=${encodeURIComponent(strings.join('\n'))}`;
  const res = await fetch(url, { headers: { 'user-agent': 'MiniWorld-DB build script' } });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  const json = await res.json();
  const text = (json[0] || []).map(seg => seg[0]).join('');
  const parts = text.split('\n');
  if (parts.length !== strings.length) throw new Error(`jumlah baris ${parts.length} != ${strings.length}`);
  return parts.map(s => s.trim());
}

/** Terjemahkan sejumlah string; kalau gagal, pecah sampai berhasil. */
async function translateChunk(strings, lang) {
  if (!strings.length) return [];
  const cached = [];
  const pending = [];
  strings.forEach((s, i) => {
    const hit = cache[`${lang.code}|${hash(s)}`];
    if (hit !== undefined) cached[i] = hit;
    else pending.push({ s, i });
  });
  if (pending.length) {
    const outMap = new Map();
    const chunks = [];
    let cur = [];
    let len = 0;
    for (const item of pending) {
      if (cur.length && (len + item.s.length > BATCH_CHARS || cur.length >= 24)) {
        chunks.push(cur);
        cur = [];
        len = 0;
      }
      cur.push(item);
      len += item.s.length + 1;
    }
    if (cur.length) chunks.push(cur);

    let next = 0;
    async function worker() {
      while (next < chunks.length) {
        const chunk = chunks[next++];
        try {
          const out = await translateBatch(chunk.map(c => c.s), lang);
          chunk.forEach((c, k) => outMap.set(c.i, out[k]));
        } catch (err) {
          if (chunk.length === 1) {
            console.warn(`    ! gagal "${chunk[0].s}": ${err.message}`);
            outMap.set(chunk[0].i, null);
          } else {
            // pecah dua lalu coba lagi
            const half = Math.ceil(chunk.length / 2);
            const first = chunk.slice(0, half);
            const second = chunk.slice(half);
            const a = await translateChunk(first.map(c => c.s), lang);
            const b = await translateChunk(second.map(c => c.s), lang);
            first.forEach((c, k) => outMap.set(c.i, a[k]));
            second.forEach((c, k) => outMap.set(c.i, b[k]));
          }
        }
      }
    }
    await Promise.all(Array.from({ length: CONCURRENCY }, worker));

    pending.forEach(c => {
      const val = outMap.has(c.i) ? outMap.get(c.i) : null;
      cache[`${lang.code}|${hash(c.s)}`] = val;
      cached[c.i] = val;
    });
  }
  return cached;
}

/** Kunci identitas isi index (kalau berubah, file terjemahan dianggap basi). */
function signature(entries) {
  return hash(entries.map(e => e.i).join(','));
}

const wanted = process.argv.slice(2);
const langs = wanted.length ? LANGUAGES.filter(l => wanted.includes(l.code)) : LANGUAGES;
if (!langs.length) {
  console.error('Bahasa tidak dikenal. Tersedia:', LANGUAGES.map(l => l.code).join(', '));
  process.exit(1);
}

fs.mkdirSync(LANG_DIR, { recursive: true });
const sig = signature(index.entries);

for (const lang of langs) {
  // kumpulkan sumber teks yang unik agar request minimal
  const sources = index.entries.map(e => (e.e || e.z || '').trim()).filter(Boolean);
  const unique = [...new Set(sources)];
  process.stdout.write(`${lang.code}: menerjemahkan ${unique.length} nama unik ... `);
  const t0 = Date.now();
  const uniqueOut = await translateChunk(unique, lang);
  const map = new Map(unique.map((s, i) => [s, uniqueOut[i]]));
  const n = index.entries.map(e => {
    const src = (e.e || e.z || '').trim();
    if (!src) return null;
    const out = map.get(src);
    return out || null;
  });
  const filled = n.filter(Boolean).length;
  const out = path.join(LANG_DIR, `${lang.code}.json`);
  fs.writeFileSync(out, JSON.stringify({ code: lang.code, label: lang.label, sig, n }), 'utf8');
  console.log(`ok (${filled}/${n.length}, ${((Date.now() - t0) / 1000).toFixed(1)}s)`);
}

fs.writeFileSync(CACHE_FILE, JSON.stringify(cache), 'utf8');
console.log(`cache: ${(fs.statSync(CACHE_FILE).size / 1024).toFixed(1)} KB di tools/sources/translations.cache.json`);
