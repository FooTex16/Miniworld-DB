#!/usr/bin/env node
/**
 * build-index.mjs
 * ---------------
 * Menggabungkan (a) daftar file ikon di folder icons_cache tiap kategori data/,
 * (b) tabel ID resmi dari tools/sources/* menjadi satu berkas
 * data/index.json yang dibaca index.html.
 *
 * Pemakaian:  node tools/build-index.mjs
 * Jalankan lagi setiap kali ikon atau sumber data bertambah.
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.join(__dirname, '..');
const SOURCES = path.join(__dirname, 'sources');
const DATA = path.join(ROOT, 'data');

/** Folder ikon yang tersedia di repo. */
const ICON_FOLDERS = ['blocks', 'creature', 'gameplay', 'items'];

/** Kategori tampilan, sesuai menu di index.html. */
const CATEGORIES = [
  { key: 'blocks', label: 'Blocks' },
  { key: 'gameplay', label: 'Gameplay' },
  { key: 'creature', label: 'Creature' },
  { key: 'items', label: 'Items' },
];

/**
 * Pemetaan nama bagian (dari tabel resmi) -> kategori + label sub-kategori.
 * Nama asli disimpan agar bisa ditampilkan apa adanya.
 */
const SECTION_MAP = {
  '植物方块': { cat: 'blocks', label: 'Plant Block' },
  '液体方块': { cat: 'blocks', label: 'Liquid Block' },
  '自然方块': { cat: 'blocks', label: 'Natural Block' },
  '装饰方块': { cat: 'blocks', label: 'Decoration Block' },
  '功能方块': { cat: 'gameplay', label: 'Function Block' },
  '消耗品': { cat: 'items', label: 'Consumable' },
  '材料': { cat: 'items', label: 'Material' },
  '武器': { cat: 'items', label: 'Weapon' },
  '装备': { cat: 'items', label: 'Equipment' },
  '工具': { cat: 'items', label: 'Tool' },
  '生物蛋': { cat: 'items', label: 'Spawn Egg', catIfCreatureIcon: 'creature' },
  '投掷物': { cat: 'items', label: 'Throwable' },
  '动物': { cat: 'creature', label: 'Animal' },
  '怪物': { cat: 'creature', label: 'Monster' },
  '坐骑': { cat: 'creature', label: 'Mount' },
  '村民': { cat: 'creature', label: 'Villager' },
  '载具': { cat: 'creature', label: 'Vehicle' },
};

function readJson(file, fallback = null) {
  const p = path.join(SOURCES, file);
  if (!fs.existsSync(p)) {
    if (fallback !== null) return fallback;
    throw new Error(`Kurang berkas ${path.relative(ROOT, p)} — jalankan: node tools/fetch-sources.mjs`);
  }
  return JSON.parse(fs.readFileSync(p, 'utf8'));
}

/** Kumpulkan ikon: id -> path relatif. File non-numerik (item_0.webp dkk) dilewati. */
function scanIcons() {
  const byId = new Map();
  const skipped = [];
  for (const folder of ICON_FOLDERS) {
    const dir = path.join(DATA, folder, 'icons_cache');
    if (!fs.existsSync(dir)) continue;
    for (const file of fs.readdirSync(dir)) {
      if (!file.endsWith('.webp')) continue;
      const base = file.slice(0, -5);
      if (!/^\d+$/.test(base)) {
        skipped.push(`${folder}/${file}`);
        continue;
      }
      const id = Number(base);
      const rel = `data/${folder}/icons_cache/${file}`;
      if (!byId.has(id)) byId.set(id, { path: rel, folders: [folder] });
      else byId.get(id).folders.push(folder);
    }
  }
  return { byId, skipped };
}

function indexSections(sections) {
  const map = new Map();
  for (const sec of sections) for (const row of sec.rows) if (!map.has(row.id)) map.set(row.id, sec.section);
  return map;
}

function main() {
  const blocksZh = readJson('blocks.zh.json');
  const itemsZh = readJson('items.zh.json');
  const creaturesZh = readJson('creatures.zh.json');
  const namesEn = readJson('names.en.json');

  const { byId: icons, skipped } = scanIcons();

  // id -> nama asli (prioritas: blok > item > makhluk, sesuai sumber pertama)
  const sectionById = new Map();
  for (const [sections] of [[blocksZh], [itemsZh], [creaturesZh]]) {
    for (const [id, sec] of indexSections(sections)) if (!sectionById.has(id)) sectionById.set(id, sec);
  }
  const zhById = new Map();
  for (const sections of [blocksZh, itemsZh, creaturesZh]) {
    for (const sec of sections) for (const row of sec.rows) if (!zhById.has(row.id)) zhById.set(row.id, row.name);
  }
  const enById = new Map(namesEn.map(r => [r.id, r.name]));

  const allIds = new Set([...icons.keys(), ...zhById.keys(), ...enById.keys()]);
  const ids = [...allIds].sort((a, b) => a - b);

  // id tanpa bagian resmi: warisi dari tetangga terdekat (rentang ID sangat rapat)
  const idsWithSection = ids.filter(id => sectionById.has(id));
  function sectionOf(id) {
    if (sectionById.has(id)) return sectionById.get(id);
    let best = null;
    let bestDist = Infinity;
    for (const near of idsWithSection) {
      const d = Math.abs(near - id);
      if (d < bestDist) { bestDist = d; best = near; }
      if (near > id && d > 32) break;
    }
    return bestDist <= 8 ? sectionById.get(best) : null;
  }

  const entries = [];
  for (const id of ids) {
    const icon = icons.get(id);
    const section = sectionOf(id);
    const mapped = section ? SECTION_MAP[section] : null;

    let cat;
    if (mapped) {
      cat = mapped.catIfCreatureIcon && icon && icon.folders.length === 1 && icon.folders[0] === 'creature'
        ? mapped.catIfCreatureIcon
        : mapped.cat;
    } else if (icon) {
      cat = icon.folders[0];
    } else {
      cat = id >= 10000 ? 'items' : 'blocks';
    }

    const entry = { i: id, c: cat };
    if (section) entry.s = section;
    if (mapped) entry.l = mapped.label;
    if (icon) entry.p = icon.path;
    if (enById.has(id)) entry.e = enById.get(id);
    if (zhById.has(id)) entry.z = zhById.get(id);
    entries.push(entry);
  }

  const counts = Object.fromEntries(CATEGORIES.map(c => [c.key, 0]));
  const iconCounts = Object.fromEntries(CATEGORIES.map(c => [c.key, 0]));
  let withIcon = 0;
  let named = 0;
  for (const e of entries) {
    counts[e.c] = (counts[e.c] || 0) + 1;
    if (e.p) { withIcon++; iconCounts[e.c]++; }
    if (e.e || e.z) named++;
  }

  const index = {
    meta: {
      generated: new Date().toISOString().slice(0, 10),
      total: entries.length,
      withIcon,
      named,
      categories: CATEGORIES.map(c => ({ ...c, count: counts[c.key], withIcon: iconCounts[c.key] })),
      sources: [
        'https://developers.mini1.cn/wiki/data_files/blockdef.html',
        'https://developers.mini1.cn/wiki/data_files/itemdef.html',
        'https://developers.mini1.cn/wiki/data_files/monster.html',
        'https://wiki.miniworldgame.com/doku.php?id=developer_center:developer_editor:script:itemid',
      ],
    },
    entries,
  };

  fs.mkdirSync(DATA, { recursive: true });
  const out = path.join(DATA, 'index.json');
  fs.writeFileSync(out, JSON.stringify(index), 'utf8');

  const kb = (fs.statSync(out).size / 1024).toFixed(1);
  console.log(`data/index.json ditulis (${kb} KB)`);
  console.log(`  total entri : ${entries.length}`);
  console.log(`  punya ikon  : ${withIcon}`);
  console.log(`  punya nama  : ${named}`);
  for (const c of CATEGORIES) console.log(`  ${c.label.padEnd(9)}: ${counts[c.key]} (${iconCounts[c.key]} berikon)`);
  if (skipped.length) console.log(`  ikon dilewati (bukan angka): ${skipped.length} — ${skipped.slice(0, 5).join(', ')}…`);
}

main();
