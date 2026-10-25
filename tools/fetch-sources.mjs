#!/usr/bin/env node
/**
 * fetch-sources.mjs
 * -----------------
 * Mengunduh tabel ID resmi Mini World (developer wiki) lalu menyimpannya
 * sebagai JSON yang sudah bersih di tools/sources/.
 *
 * Sumber:
 *   - developers.mini1.cn  -> tabel resmi berbahasa Mandarin (block/item/creature)
 *   - wiki.miniworldgame.com -> terjemahan resmi berbahasa Inggris (flat list)
 *
 * Pemakaian:  node tools/fetch-sources.mjs
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const OUT = path.join(__dirname, 'sources');
fs.mkdirSync(OUT, { recursive: true });

const SOURCES = {
  blocksZh: 'https://developers.mini1.cn/wiki/data_files/blockdef.html',
  itemsZh: 'https://developers.mini1.cn/wiki/data_files/itemdef.html',
  creaturesZh: 'https://developers.mini1.cn/wiki/data_files/monster.html',
  namesEn: 'https://wiki.miniworldgame.com/doku.php?id=developer_center%3Adeveloper_editor%3Ascript%3Aitemid',
};

/** Nama yang dipakai sumber hanya placeholder / penanda "tidak tersedia". */
const JUNK = /^(unavailable in this version|game version is too low|version outdated|not available|unknown|n\/a|\?+|[\d\-]+\?+|\?+[\d\-]+|[-–—.\s]*)$/i;

function clean(s) {
  const t = s
    .replace(/<[^>]+>/g, '')
    .replace(/&nbsp;/g, ' ').replace(/&amp;/g, '&').replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>').replace(/&#0?39;/g, "'").replace(/&quot;/g, '"')
    .replace(/\s+/g, ' ')
    .trim();
  if (!t || JUNK.test(t)) return '';
  return t;
}

async function download(url) {
  const res = await fetch(url, { headers: { 'user-agent': 'MiniWorld-DB build script' } });
  if (!res.ok) throw new Error(`${res.status} ${url}`);
  return await res.text();
}

/** Halaman CN: <h3> judul bagian </h3> lalu tabel 4 pasang ID/nama per baris. */
function parseSectionedTable(html) {
  const sections = [];
  for (const part of html.split(/<h3[^>]*>/).slice(1)) {
    const end = part.indexOf('</h3>');
    if (end < 0) continue;
    const title = clean(part.slice(0, end)).replace(/^#+\s*/, '');
    const tableEnd = part.indexOf('</table>');
    if (tableEnd < 0) continue;
    const rows = [];
    for (const tr of part.slice(0, tableEnd).matchAll(/<tr>([\s\S]*?)<\/tr>/g)) {
      const cells = [...tr[1].matchAll(/<td[^>]*>([\s\S]*?)<\/td>/g)].map(m => clean(m[1]));
      for (let i = 0; i + 1 < cells.length; i += 2) {
        if (!/^\d+$/.test(cells[i]) || !cells[i + 1]) continue;
        rows.push({ id: Number(cells[i]), name: cells[i + 1] });
      }
    }
    if (rows.length) sections.push({ section: title, rows });
  }
  return sections;
}

/** Halaman EN: satu tabel datar "col0 = ID, col1 = nama". */
function parseFlatTable(html) {
  const out = [];
  const seen = new Set();
  const re = /<td class="col0 centeralign">\s*(\d+)\s*<\/td><td class="col1 centeralign">\s*([\s\S]*?)\s*<\/td>/g;
  for (const m of html.matchAll(re)) {
    const id = Number(m[1]);
    const name = clean(m[2]);
    if (seen.has(id) || !name) continue;
    seen.add(id);
    out.push({ id, name });
  }
  return out;
}

function writeJson(file, data) {
  const p = path.join(OUT, file);
  fs.writeFileSync(p, JSON.stringify(data, null, 1) + '\n', 'utf8');
  console.log(`  -> tools/sources/${file} (${(fs.statSync(p).size / 1024).toFixed(1)} KB)`);
}

const raw = {};
for (const [key, url] of Object.entries(SOURCES)) {
  process.stdout.write(`mengunduh ${key} ... `);
  raw[key] = await download(url);
  console.log('ok');
}

const blocksZh = parseSectionedTable(raw.blocksZh);
const itemsZh = parseSectionedTable(raw.itemsZh);
const creaturesZh = parseSectionedTable(raw.creaturesZh);
const namesEn = parseFlatTable(raw.namesEn);

writeJson('blocks.zh.json', blocksZh);
writeJson('items.zh.json', itemsZh);
writeJson('creatures.zh.json', creaturesZh);
writeJson('names.en.json', namesEn);

const count = list => list.reduce((n, s) => n + s.rows.length, 0);
console.log(
  `\nselesai: ${count(blocksZh)} blok, ${count(itemsZh)} item, ` +
    `${count(creaturesZh)} makhluk, ${namesEn.length} nama EN`
);
