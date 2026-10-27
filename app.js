/* MiniWorld DB — katalog ID block, item, dan creature.
   Satu berkas dipakai dua tempat; yang membedakan hanya sumber datanya:

     LOCAL  server lokal (server.py)  ->  /api/db + /api/lang/ + /api/icon/
                                          membaca folder DATA\<indu>\<kategori>
     LIVE   situs statis (Vercel)     ->  data/db.json + data/lang/ + data/icons/

   Mode dibaca dari hostname, lalu dikonfirmasi lagi waktu data dimuat (URL
   dicoba dua-duanya bila tebakan salah). Di mode LIVE semua tulisan diblokir:
   hapus, ubah no urut, urutkan sub kategori, dan ubah nama — tampilannya tetap
   sama, hanya aksi tulisnya yang diganti pesan baca-saja.

   Tambahan lokal: pilih-banyak, penanda duplikat, tombol hapus, ubah no urut,
   dan ubah nama block (/api/rename). */
(() => {
  'use strict';

  const PAGE = 120;
  const $ = id => document.getElementById(id);

  // URL data per mode. file:// dan server lokal -> LOCAL; lainnya -> LIVE.
  const URL_DB_STATIS = 'data/db.json';
  const URL_DB_API = '/api/db';
  let LIVE = !['127.0.0.1', 'localhost', '::1', ''].includes(location.hostname);
  const URL_LANG = code => LIVE
    ? 'data/lang/' + code + '.json'
    : '/api/lang/' + code + '.json';

  /* Badge di topbar, kunci footer, dan pesan baca-saja mengikuti mode. */
  function terapkanMode() {
    const badge = document.querySelector('.brand .mode');
    if (badge) {
      badge.textContent = LIVE ? 'LIVE' : 'LOCAL';
      badge.classList.toggle('live', LIVE);
    }
    const foot = document.querySelector('[data-i18n-html="footer"]');
    if (foot) foot.dataset.i18nHtml = LIVE ? 'footerLive' : 'footer';
  }

  /* True bila situs sedang LIVE (baca-saja): tampilkan pesan, jangan lanjut. */
  function blokirTulis() {
    if (!LIVE) return false;
    toastMsg(t('ro.msg'));
    return true;
  }

  // warna titik kategori — palet yang sama dengan situs, dipakai bergiliran
  const CAT_COLORS = ['#d9a441', '#58a6d8', '#77c178', '#b48ae0', '#e07a5f', '#6fc3b0', '#d06a8c'];

  const ui = {
    q: $('q'), lang: $('lang'), cats: $('cats'), onlyIcon: $('onlyIcon'), onlyName: $('onlyName'),
    onlyDup: $('onlyDup'), onlyUniq: $('onlyUniq'),
    noFrom: $('noFrom'), noTo: $('noTo'), noReset: $('noReset'), noHint: $('noHint'),
    modeNo: $('modeNo'), modeWrap: $('modeWrap'), pickStat: $('pickStat'),
    noApply: $('noApply'), noOrderReset: $('noOrderReset'), modeExit: $('modeExit'),
    title: $('title'), count: $('count'), dupStat: $('dupStat'),
    grid: $('grid'), more: $('more'), empty: $('empty'),
    loading: $('loading'), error: $('error'), toast: $('toast'), topStat: $('topStat'),
    selAll: $('selAll'), selStat: $('selStat'), selClear: $('selClear'), selDelete: $('selDelete'),
    edWrap: $('edwrap'), edCtx: $('edCtx'), edE: $('edE'), edZ: $('edZ'),
    edErr: $('edErr'), edCancel: $('edCancel'), edSave: $('edSave'),
    navToggle: $('navToggle'), catBar: $('catBar'), catSortOn: $('catSortOn'),
    catMode: $('catMode'), catApply: $('catApply'), catReset: $('catReset'),
    catExit: $('catExit'),
    layout: document.querySelector('.layout'),
  };

  const state = {
    entries: [],
    meta: null,
    cat: 'all',
    q: '',
    sort: 'id',
    sortTouched: false,     // user sudah memilih tombol urut sendiri
    noFrom: 1,              // batas bawah no urut (per kategori)
    noTo: null,             // batas atas; null = sampai habis
    modeNo: false,          // mode ubah no urut (klik kartu berurutan)
    picks: [],              // id terpilih pada mode urut, sesuai urutan klik
    modeCat: false,         // mode urutkan sub kategori (klik berurutan)
    catPicks: [],           // nama sub kategori terpilih pada mode tsb
    view: 'grid',
    nav: localStorage.getItem('mwdb.nav') !== '0',   // navigasi tampil
    onlyIcon: false,
    onlyName: false,
    onlyDup: false,
    onlyUniq: false,
    lang: localStorage.getItem('mwdb.lang') || 'en',
    translations: {},        // kode -> array nama selaras urutan entries
    filtered: [],
    shown: 0,
    haystack: null,
    sel: new Set(),          // kunci "kategori|id|indeks" yang tercentang
    byKey: new Map(),        // kunci -> entri
    dupTotal: 0,
  };

  /* ---------- i18n ---------- */

  const DICT = () => window.MWDB_I18N || {};

  // rantai fallback: bahasa aktif -> en -> id -> teks bawaan
  function tr(key, fb) {
    const d = DICT();
    const cur = d[state.lang];
    if (cur && cur[key] != null) return cur[key];
    if (d.en && d.en[key] != null) return d.en[key];
    if (d.id && d.id[key] != null) return d.id[key];
    return fb != null ? fb : key;
  }
  const t = key => tr(key);

  function applyLang() {
    document.documentElement.lang = state.lang;
    document.title = t('title');
    document.querySelectorAll('[data-i18n]').forEach(el => {
      el.textContent = tr(el.dataset.i18n, el.textContent);
    });
    document.querySelectorAll('[data-i18n-html]').forEach(el => {
      el.innerHTML = tr(el.dataset.i18nHtml, el.innerHTML);
    });
    document.querySelectorAll('[data-i18n-ph]').forEach(el => {
      el.placeholder = tr(el.dataset.i18nPh, el.placeholder);
    });
    document.querySelectorAll('[data-i18n-aria]').forEach(el => {
      el.setAttribute('aria-label',
        tr(el.dataset.i18nAria, el.getAttribute('aria-label') || ''));
    });
    document.querySelectorAll('[data-i18n-title]').forEach(el => {
      el.title = tr(el.dataset.i18nTitle, el.title);
    });
    if (ui.navToggle) {
      ui.navToggle.textContent = state.nav ? t('nav.hide') : t('nav.show');
    }
    if (state.meta) { renderCats(); rebuild(); }
  }

  /* ---------- helpers ---------- */

  const fold = s => s.toLowerCase().normalize('NFKD').replace(/[\u0300-\u036f]/g, '');
  // angka ikut format negara bahasa yang sedang dipilih (1.548 vs 1,548 vs 1 548)
  const LOCALE = {
    id: 'id-ID', en: 'en-US', zh: 'zh-CN', es: 'es-ES',
    pt: 'pt-BR', fr: 'fr-FR', ja: 'ja-JP', ru: 'ru-RU',
  };
  const fmt = n => Number(n).toLocaleString(LOCALE[state.lang] || 'en-US');
  // ganti placeholder {nama} di dalam teks terjemahan
  const fill = (s, map) => String(s).replace(/\{(\w+)\}/g,
    (m, k) => (k in map ? map[k] : m));

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  }

  // Nama utama selalu satu bahasa: en -> English, zh -> 中文, sisanya
  // terjemahan mesin (kalau belum ada, jatuh ke English karena tidak ada
  // padanan lain yang tersimpan secara lokal).
  function primary(e, i) {
    const tv = state.translations[state.lang];
    if (state.lang === 'zh') return e.z || e.e || '';
    if (state.lang === 'en') return e.e || e.z || '';
    return (tv && tv[i]) || e.e || e.z || '';
  }
  // Nama kedua sengaja tidak pernah ditampilkan: satu bahasa = satu nama,
  // supaya tampilan tidak tercampur (mis. English + 中Cina berdampingan).
  function secondary() { return ''; }

  // label grup (Decoration Block, Spawn Egg, ...) ikut bahasa aktif
  function grupLabel(e) {
    if (!e.l) return '';
    return tr('grp.' + e.l, state.lang === 'zh' ? (e.s || e.l) : e.l);
  }

  // nama kategori: kunci folder ("Blocks", "Natural") -> teks bahasa aktif
  function catNama(raw) { return tr('cat.' + raw, raw); }

  function judulCat() {
    if (state.cat === 'all') return t('cat.all');
    const p = state.cat.split('/');
    return p.length === 1 ? catNama(p[0]) : catNama(p[0]) + ' / ' + catNama(p[1]);
  }

  // filter kategori: 'all' | induk ('Blocks') | sub ('Blocks/Natural')
  function cocokCat(e) {
    if (state.cat === 'all') return true;
    if (state.cat.indexOf('/') < 0) return e.c.indexOf(state.cat + '/') === 0;
    return e.c === state.cat;
  }
  function haystackFor(e, i) {
    const parts = [String(e.i), e.l || '', e.s || '', e.c || ''];
    for (const src of [e.e, e.z]) if (src) parts.push(src);
    const t = state.translations[state.lang];
    if (t && t[i]) parts.push(t[i]);
    return fold(parts.filter(Boolean).join(' '));
  }
  function ensureHaystack() {
    if (!state.haystack) state.haystack = state.entries.map(haystackFor);
  }
  function dropHaystack() { state.haystack = null; }

  function toast(id, label) {
    ui.toast.innerHTML = 'ID <code>' + escapeHtml(id) + '</code> ' + (label || t('msg.copied'));
    show();
  }
  function toastMsg(html) {
    ui.toast.innerHTML = html;
    show();
  }
  function show() {
    ui.toast.classList.add('on');
    clearTimeout(toast._t);
    toast._t = setTimeout(() => ui.toast.classList.remove('on'), 2200);
  }

  async function copyText(text) {
    try {
      await navigator.clipboard.writeText(text);
      return true;
    } catch (_) {
      const ta = document.createElement('textarea');
      ta.value = text;
      ta.style.cssText = 'position:fixed;opacity:0';
      document.body.appendChild(ta);
      ta.select();
      let ok = false;
      try { ok = document.execCommand('copy'); } catch (_) {}
      ta.remove();
      return ok;
    }
  }

  async function copyId(id, node) {
    const ok = await copyText(String(id));
    if (ok) {
      node.classList.add('copied');
      setTimeout(() => node.classList.remove('copied'), 700);
      toast(id, t('msg.copied'));
    } else {
      toast(id, t('msg.copyFail'));
    }
  }

  /* ---------- duplikat & pilihan ---------- */

  function markDuplicates() {
    const byId = new Map(), byName = new Map();

    state.entries.forEach((e, idx) => {
      const idk = String(e.i);
      if (!byId.has(idk)) byId.set(idk, []);
      byId.get(idk).push(idx);

      const nm = fold((e.e || e.z || '').trim());
      if (nm) {
        if (!byName.has(nm)) byName.set(nm, []);
        byName.get(nm).push(idx);
      }
    });

    let dupTotal = 0;
    state.byKey = new Map();

    state.entries.forEach((e, idx) => {
      const idk = String(e.i);
      const nm = fold((e.e || e.z || '').trim());
      const ids = byId.get(idk) || [];
      const nms = nm ? (byName.get(nm) || []) : [];

      const dupId = ids.length > 1;
      const dupName = nms.length > 1;

      e._key = e.c + '|' + e.i + '|' + idx;
      e._dupId = dupId;
      e._dupName = dupName;
      e._dup = dupId || dupName;
      e._grp = dupId ? 'id:' + idk : (dupName ? 'nm:' + nm : '');

      const cats = [...new Set(ids.map(j => state.entries[j].c))];
      const others = [...new Set(nms.filter(j => j !== idx).map(j => '#' + state.entries[j].i))];
      e._dupWhy = [
        dupId ? t('dup.idIn') + ' ' + cats.join(', ') : '',
        dupName ? t('dup.sameName') + ' ' + others.join(', ') : '',
      ].filter(Boolean).join(' · ');

      state.byKey.set(e._key, e);
      if (e._dup) dupTotal++;
    });

    state.dupTotal = dupTotal;
  }

  function keyParts(k) {
    const p = k.split('|');
    return { cat: p[0], i: Number(p[1]) };
  }

  function updateSelUI() {
    if (!ui.selStat) return;

    let dup = 0;
    for (const k of state.sel) {
      const e = state.byKey.get(k);
      if (e && e._dup) dup++;
    }
    const n = state.sel.size;

    ui.selStat.innerHTML = '<b>' + fmt(n) + '</b> ' + t('sel.stat') + (n
      ? ' · <span class="d">' + fmt(dup) + ' ' + t('tag.dup') + '</span>' +
        ' · <span class="u">' + fmt(n - dup) + ' ' + t('tag.uniq') + '</span>'
      : '');
    ui.selClear.disabled = n === 0;
    ui.selDelete.disabled = n === 0;

    if (ui.selAll) {
      const f = state.filtered;
      const all = f.length > 0 && f.every(i => state.sel.has(state.entries[i]._key));
      const some = f.some(i => state.sel.has(state.entries[i]._key));
      ui.selAll.checked = all;
      ui.selAll.indeterminate = !all && some;
    }

    ui.grid.querySelectorAll('.card').forEach(c => {
      const e = state.byKey.get(c.dataset.key);
      const on = state.sel.has(c.dataset.key);
      c.classList.toggle('sel', on);
      const p = c.querySelector('.pick');
      if (p) p.checked = on;
      if (!e) return;
      let tag = c.querySelector('.tag');
      if (!tag && (on || e._dup)) {
        tag = document.createElement('span');
        c.appendChild(tag);
      }
      if (tag) {
        if (!on && !e._dup) { tag.remove(); return; }
        tag.className = 'tag ' + (e._dup ? 'dup' : 'uniq');
        tag.textContent = e._dup ? t('tag.dup') : t('tag.uniq');
        tag.title = e._dup ? e._dupWhy : t('tag.notDup');
      }
    });
  }

  function renderCats() {
    const meta = state.meta || {};
    const parents = meta.parents || [];
    const cats = meta.categories || [];
    const subUrut = meta.subOrder || {};
    const induk = state.cat === 'all' ? null : state.cat.split('/')[0];

    let html = '<li data-cat="all"' + (state.cat === 'all' ? ' on' : '') + '>' +
      '<span class="dot" style="background:var(--muted)"></span>' +
      escapeHtml(t('cat.all')) +
      '<span class="n" data-n="all">' + fmt(meta.total || 0) + '</span></li>';

    parents.forEach((p, k) => {
      const warna = CAT_COLORS[k % CAT_COLORS.length];
      html += '<li class="par' + (state.cat === p.key ? ' on' : '') +
        '" data-cat="' + escapeHtml(p.key) + '">' +
        '<span class="dot" style="background:' + warna + '"></span>' +
        escapeHtml(catNama(p.key)) +
        '<span class="n" data-n="' + escapeHtml(p.key) + '">' +
        fmt(p.count) + '</span></li>';

      // sub kategori hanya tampil kalau induknya sedang dipilih
      if (induk !== p.key) return;

      const daftar = subUrut[p.key] ||
        cats.filter(c => c.parent === p.key).map(c => c.name);
      daftar.forEach(nama => {
        const c = cats.find(x => x.parent === p.key && x.name === nama);
        if (!c) return;                 // folder hilang sejak pesanan disusun
        const dipilih = state.modeCat && state.catPicks.indexOf(nama) >= 0;
        let nomor = 0;
        if (state.modeCat) nomor = dipilih ? state.catPicks.indexOf(nama) + 1 : 0;
        else if (subUrut[p.key]) nomor = daftar.indexOf(nama) + 1;

        html += '<li class="sub' + (state.cat === c.key ? ' on' : '') +
          (dipilih ? ' pick' : '') +
          '" data-cat="' + escapeHtml(c.key) +
          '" data-name="' + escapeHtml(nama) + '">' +
          '<span class="dot" style="background:' + warna + '"></span>' +
          escapeHtml(catNama(nama)) +
          (nomor ? '<span class="urut">No.' + nomor + '</span>' : '') +
          '<span class="n" data-n="' + escapeHtml(c.key) + '">' +
          fmt(c.count) + '</span></li>';
      });
    });

    ui.cats.innerHTML = html;
    ui.cats.classList.toggle('mode', state.modeCat);

    ui.topStat.innerHTML = '<b>' + fmt(meta.total || 0) + '</b> ' + t('stat.entri') +
      ' · <b>' + fmt(meta.withIcon || 0) + '</b> ' + t('stat.icon') +
      (state.dupTotal
        ? ' · <b style="color:#e8734d">' + fmt(state.dupTotal) + '</b> ' + t('stat.dup')
        : '');

    // tombol urutkan sub kategori hanya muncul bila sub memang sedang tampil
    const adaSub = !!induk && cats.some(c => c.parent === induk);
    ui.catSortOn.hidden = state.modeCat || !adaSub;
    ui.catMode.hidden = !state.modeCat;
    ui.catReset.hidden = !(state.modeCat && subUrut[induk]);
    ui.catApply.disabled = state.catPicks.length === 0;
  }

  /* ---------- data ---------- */

  async function loadJson(url) {
    const res = await fetch(url, { cache: 'no-cache' });
    if (!res.ok) throw new Error(url + ' → HTTP ' + res.status);
    return res.json();
  }

  /* Coba URL berurutan sampai ada yang berhasil; kalau tebakan mode salah,
     mode LIVE dikoreksi supaya badge & keterangan ikut benar. */
  async function loadJsonMode(urut) {
    let err = null;
    for (const u of urut) {
      try {
        return [u, await loadJson(u)];
      } catch (e) {
        if (!err) err = e;
      }
    }
    throw err;
  }

  async function loadIndex() {
    const urut = LIVE ? [URL_DB_STATIS, URL_DB_API] : [URL_DB_API, URL_DB_STATIS];
    const [pakai, data] = await loadJsonMode(urut);
    LIVE = pakai === URL_DB_STATIS;
    terapkanMode();
    state.entries = data.entries;
    state.meta = data.meta;
    ui.lang.value = state.lang;
  }

  async function loadLang(code) {
    if (code === 'en' || code === 'zh' || state.translations[code]) return;
    try {
      const data = await loadJson(URL_LANG(code));
      if (data.sig === sig(state.entries)) state.translations[code] = data.n;
    } catch (_) {
      /* bahasa gagal dimuat → otomatis jatuh ke English */
    }
  }

  function sig(entries) {
    let h = 5381;
    const s = entries.map(e => e.i).join(',');
    for (let i = 0; i < s.length; i++) h = ((h << 5) + h + s.charCodeAt(i)) >>> 0;
    return h.toString(36);
  }

  /* ---------- filtering ---------- */

  function rangeActive() {
    return state.noFrom > 1 || state.noTo != null;
  }

  function maxNo() {
    let m = 0;
    for (const e of state.entries) {
      if (!cocokCat(e)) continue;
      if (e.no != null && e.no > m) m = e.no;
    }
    return m;
  }

  function kustom(cat) {
    return ((state.meta && state.meta.noCustom) || []).indexOf(cat) >= 0;
  }

  function updateRangeHint() {
    const habis = t('hint.end');
    ui.noTo.placeholder = maxNo() ? String(maxNo()) : habis;
    const edited = (state.cat !== 'all' && kustom(state.cat)) ? t('hint.edited') : '';
    const sort = state.sort === 'game' ? t('hint.sortGame') : t('hint.sortTip');
    ui.noHint.innerHTML = rangeActive()
      ? fill(t('hint.range'), {
        from: state.noFrom,
        to: state.noTo != null ? state.noTo : habis,
        sort: sort, edited: edited,
      })
      : fill(t('hint.full'), { to: habis, sortTip: t('hint.sortTip'), edited: edited });
    // tombol kembalikan hanya muncul bila kategori itu memang sudah disunting
    ui.noOrderReset.hidden = !(state.cat !== 'all' && kustom(state.cat));
  }

  function rebuild() {
    ensureHaystack();
    const term = fold(state.q.trim());
    const active = rangeActive();
    const out = [];
    for (let i = 0; i < state.entries.length; i++) {
      const e = state.entries[i];
      if (!cocokCat(e)) continue;
      if (state.onlyIcon && !e.p) continue;
      if (state.onlyName && !e.e && !e.z) continue;
      if (state.onlyDup && !e._dup) continue;
      if (state.onlyUniq && e._dup) continue;
      if (term && !state.haystack[i].includes(term)) continue;
      if (active) {
        const no = e.no;
        if (no == null) continue;                 // tanpa nomor -> di luar rentang
        if (no < state.noFrom) continue;
        if (state.noTo != null && no > state.noTo) continue;
      }
      out.push(i);
    }

    if (state.onlyDup) {
      // kelompokkan anggota duplikat supaya bersebelahan
      out.sort((a, b) =>
        state.entries[a]._grp.localeCompare(state.entries[b]._grp) ||
        state.entries[a].i - state.entries[b].i);
    } else if (state.sort === 'name') {
      out.sort((a, b) => {
        const na = primary(state.entries[a], a).toLowerCase();
        const nb = primary(state.entries[b], b).toLowerCase();
        return na.localeCompare(nb) || state.entries[a].i - state.entries[b].i;
      });
    } else if (state.sort === 'game') {
      // urutan seperti di game: halaman -> baris -> kolom (gno), nomor hilang di belakang
      out.sort((a, b) => {
        const na = state.entries[a].gno;
        const nb = state.entries[b].gno;
        if (na == null && nb == null) return state.entries[a].i - state.entries[b].i;
        if (na == null) return 1;
        if (nb == null) return -1;
        return na - nb || state.entries[a].i - state.entries[b].i;
      });
    } else {
      out.sort((a, b) => state.entries[a].i - state.entries[b].i);
    }

    state.filtered = out;
    state.shown = 0;
    ui.grid.innerHTML = '';
    ui.empty.hidden = true;
    renderChunk();

    ui.title.textContent = judulCat();

    const withIcon = out.filter(i => state.entries[i].p).length;
    const dups = out.filter(i => state.entries[i]._dup).length;
    ui.count.textContent = fmt(out.length) + ' ' + t('stat.entri') +
      (withIcon !== out.length ? ' · ' + fmt(withIcon) + ' ' + t('stat.withIcon') : '') +
      (active ? ' · No. ' + state.noFrom + '–' +
        (state.noTo != null ? state.noTo : t('hint.end')) : '');
    ui.dupStat.textContent = dups ? '· ' + fmt(dups) + ' ' + t('stat.dup') : '';

    updateRangeHint();
    updateSelUI();
  }

  /* ---------- rendering ---------- */

  function cardNode(i) {
    const e = state.entries[i];
    const main = primary(e, i);
    const named = !!main;
    const on = state.sel.has(e._key);
    const urutKe = state.modeNo ? state.picks.indexOf(e.i) : -1;

    const card = document.createElement('div');
    card.className = 'card' + (e._dup ? ' dup' : '') + (on ? ' sel' : '') +
      (urutKe >= 0 ? ' picked' : '');
    card.dataset.id = e.i;
    card.dataset.key = e._key;
    card.setAttribute('role', 'button');
    card.tabIndex = 0;
    // nama selalu ikut di tooltip — penting pada tampilan "ikon" yang
    // sengaja tidak menampilkan teks apa pun selain ikonnya
    card.title = (named ? main + ' · ' : '') +
      (e._dup ? t('tag.dup') + ' — ' + e._dupWhy + ' — ' : '') +
      t('card.copyTip') + ' ' + e.i;

    const pick = document.createElement('input');
    pick.type = 'checkbox';
    pick.className = 'pick';
    pick.checked = on;
    pick.setAttribute('aria-label', t('card.pick') + ' #' + e.i);
    pick.addEventListener('click', ev => ev.stopPropagation());
    pick.addEventListener('change', () => {
      if (state.modeNo) {                 // mode urut: kotak = tandai urutan
        togglePick(e);
        rebuild();
        updatePickUI();
        return;
      }
      if (pick.checked) state.sel.add(e._key); else state.sel.delete(e._key);
      updateSelUI();
    });
    card.appendChild(pick);

    const thumb = document.createElement('span');
    thumb.className = 'thumb';
    if (e.p) {
      const img = document.createElement('img');
      img.src = e.p;
      img.alt = '';
      img.loading = 'lazy';
      img.decoding = 'async';
      img.width = 46;
      img.height = 46;
      img.addEventListener('error', () => {
        thumb.innerHTML = '<span class="ph">#</span>';
      });
      thumb.appendChild(img);
    } else {
      thumb.innerHTML = '<span class="ph">' + (named ? main.charAt(0).toUpperCase() : '#') + '</span>';
    }

    const meta = document.createElement('span');
    meta.className = 'meta';
    const nm = document.createElement('span');
    nm.className = 'nm' + (named ? '' : ' empty');
    nm.textContent = named ? main : t('card.noname');
    meta.appendChild(nm);
    const grp = grupLabel(e);
    if (grp) {
      const sub = document.createElement('span');
      sub.className = 'sub';
      sub.textContent = grp;
      meta.appendChild(sub);
    }

    const id = document.createElement('span');
    id.className = 'id';
    id.textContent = '#' + e.i;

    const seq = document.createElement('span');
    seq.className = 'no';
    seq.textContent = e.no != null ? 'No.' + e.no : 'No.—';
    seq.title = state.modeNo
      ? t('no.tipMode')
      : e.no != null
        ? fill(t('no.tipOne'), { no: e.no, cat: catNama(String(e.c || '-').split('/').pop()) })
        : t('no.tipNone');

    card.append(thumb, meta);

    const ed = document.createElement('button');
    ed.type = 'button';
    ed.className = 'ed';
    ed.textContent = t('card.edit');
    ed.title = fill(t('card.editTip'), { id: e.i });
    ed.setAttribute('aria-label', fill(t('card.editTip'), { id: e.i }));
    ed.addEventListener('click', ev => {
      ev.stopPropagation();
      bukaEditNama(e);
    });
    card.appendChild(ed);

    if (e._dup || on) {
      const tag = document.createElement('span');
      tag.className = 'tag ' + (e._dup ? 'dup' : 'uniq');
      tag.textContent = e._dup ? t('tag.dup') : t('tag.uniq');
      tag.title = e._dup ? e._dupWhy : t('tag.notDup');
      card.appendChild(tag);
    }
    if (urutKe >= 0) {
      const pn = document.createElement('span');
      pn.className = 'pno';                // sengaja BUKAN kelas "tag" —
      pn.textContent = fill(t('card.ord'), { n: urutKe + 1 });
      pn.title = fill(t('card.ordTip'), { n: urutKe + 1 });
      card.appendChild(pn);
    }
    card.appendChild(seq);
    card.appendChild(id);

    card.addEventListener('click', ev => {
      if (ev.target.closest('.pick')) return;
      if (state.modeNo) {                 // mode urut: klik = tambah urutan
        togglePick(e);
        rebuild();
        updatePickUI();
        return;
      }
      if (ev.target.closest('.no')) {     // klik chip No. = ubah nomor ini
        startEditNo(card, e);
        return;
      }
      copyId(e.i, card);
    });
    card.addEventListener('keydown', ev => {
      if (ev.target !== card) return;
      if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); copyId(e.i, card); }
      if (ev.key === 'x' || ev.key === 'X') {
        pick.checked = !pick.checked;
        if (pick.checked) state.sel.add(e._key); else state.sel.delete(e._key);
        updateSelUI();
      }
    });

    return card;
  }

  function renderChunk() {
    const total = state.filtered.length;
    if (!total) {
      ui.empty.hidden = false;
      ui.empty.innerHTML = state.q
        ? '<h4>' + escapeHtml(fill(t('empty.qTitle'), { q: state.q })) + '</h4>' +
          '<p>' + t('empty.qBody') + '</p>' +
          '<button class="btn" id="reset">' + t('empty.qBtn') + '</button>'
        : '<h4>' + t('empty.catTitle') + '</h4><p>' + t('empty.catBody') + '</p>';
      const reset = $('reset');
      if (reset) reset.addEventListener('click', () => {
        ui.q.value = ''; state.q = ''; rebuild();
      });
      ui.more.hidden = true;
      return;
    }
    const end = Math.min(state.shown + PAGE, total);
    const frag = document.createDocumentFragment();
    for (let k = state.shown; k < end; k++) frag.appendChild(cardNode(state.filtered[k]));
    ui.grid.appendChild(frag);
    state.shown = end;
    const rest = total - state.shown;
    ui.more.hidden = rest <= 0;
    if (rest > 0) ui.more.textContent = fill(t('more.show'), {
      n: fmt(Math.min(PAGE, rest)), sisa: fmt(rest),
    });
    updateSelUI();
  }

  /* ---------- hapus ---------- */

  async function deleteSelected() {
    const keys = [...state.sel];
    if (!keys.length || blokirTulis()) return;

    const items = keys.map(k => { const p = keyParts(k); return { cat: p.cat, i: p.i }; });
    const nDup = keys.filter(k => { const e = state.byKey.get(k); return e && e._dup; }).length;

    const ok = confirm(fill(t('del.confirm'), {
      n: items.length, dup: nDup, unik: items.length - nDup,
    }));
    if (!ok) return;

    ui.selDelete.disabled = true;
    ui.selClear.disabled = true;
    try {
      const res = await fetch('/api/delete', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ items }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.error || ('HTTP ' + res.status));

      state.sel.clear();
      await muatUlang();                 // entries + meta baru dari server

      toastMsg(fill(t('del.done'), {
        n: fmt(data.deleted), icon: fmt(data.iconsMoved),
      }));
    } catch (err) {
      alert(t('del.fail') + ' ' + err.message);
      updateSelUI();
    }
  }

  /* ---------- ubah no urut ---------- */

  function renumberGlobal() {
    // gno = nomor global, kategori disusun mengikuti urutan navigasi
    // (sudah memperhitungkan urutan sub kategori buatan user) lalu ikut no
    const per = new Map();
    for (const e of state.entries) {
      if (!per.has(e.c)) per.set(e.c, []);
      per.get(e.c).push(e);
    }
    const urut = ((state.meta && state.meta.categories) || []).map(c => c.key);
    for (const k of per.keys()) if (urut.indexOf(k) < 0) urut.push(k);
    let g = 0;
    for (const k of urut) {
      const list = per.get(k);
      if (!list) continue;
      list.sort((a, b) =>
        ((a.no == null ? 1e9 : a.no) - (b.no == null ? 1e9 : b.no)) ||
        (a.i - b.i));
      for (const e of list) e.gno = ++g;
    }
  }

  function orderMap(cat) {
    const m = {};
    for (const e of state.entries) if (e.c === cat) m[e.i] = e.no;
    return m;
  }

  async function kirimUrut(body) {
    const res = await fetch('/api/order', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok || !data.ok) throw new Error(data.error || ('HTTP ' + res.status));
    return data;
  }

  async function muatUrutUlang() {
    await loadIndex();
    dropHaystack();
    markDuplicates();
    rebuild();
    updateSelUI();
    updatePickUI();
  }

  async function simpanUrut(cat, ket) {
    try {
      await kirimUrut({ cat: cat, map: orderMap(cat) });
      if (state.meta) {                   // tandai kategori sebagai "disunting"
        const arr = state.meta.noCustom || (state.meta.noCustom = []);
        if (arr.indexOf(cat) < 0) arr.push(cat);
      }
      toastMsg(fill(t('no.saved'), { ket: ket }));
    } catch (err) {
      alert(t('no.saveFail') + ' ' + err.message);
      await muatUrutUlang();              // samakan lagi dengan server
    }
  }

  function applySingle(e, noBaru) {
    // ubah satu block: kalau nomornya sedang dipakai block lain, keduanya
    // bertukar supaya nomor tidak pernah kembar.
    const penghuni = state.entries.find(
      x => x.c === e.c && x.no === noBaru && x.i !== e.i);
    const lama = e.no;
    if (penghuni) penghuni.no = lama;
    e.no = noBaru;
    renumberGlobal();
    return penghuni;
  }

  let sedangEdit = false;

  function startEditNo(card, e) {
    if (sedangEdit || state.modeNo || blokirTulis()) return;
    const chip = card.querySelector('.no');
    if (!chip) return;
    sedangEdit = true;

    const lama = e.no;
    chip.classList.add('editing');
    chip.textContent = '';
    const inp = document.createElement('input');
    inp.type = 'number';
    inp.className = 'no-in';
    inp.min = '1';
    inp.value = lama == null ? '' : String(lama);
    inp.setAttribute('aria-label', fill(t('no.newAria'), { id: e.i }));
    chip.appendChild(inp);
    inp.focus();
    inp.select();

    let tutup = false;
    const selesai = terapkan => {
      if (tutup) return;
      tutup = true;
      sedangEdit = false;
      const v = parseInt(inp.value, 10);
      chip.classList.remove('editing');
      if (!terapkan || !Number.isFinite(v) || v < 1 || v === lama) {
        rebuild();                       // tampilkan angka lama kembali
        return;
      }
      const bentrok = applySingle(e, v);
      rebuild();
      simpanUrut(e.c, 'No.' + lama + ' → No.' + v +
        (bentrok ? fill(t('no.swap'), { id: bentrok.i, no: lama }) : ''));
    };

    inp.addEventListener('keydown', ev => {
      ev.stopPropagation();
      if (ev.key === 'Enter') { ev.preventDefault(); selesai(true); }
      else if (ev.key === 'Escape') { ev.preventDefault(); selesai(false); }
    });
    inp.addEventListener('click', ev => ev.stopPropagation());
    inp.addEventListener('blur', () => selesai(false));
  }

  /* ---------- ubah nama block ---------- */

  let edEntry = null;                   // entri yang sedang dibuka di modal

  function bukaEditNama(e) {
    if (state.modeNo || sedangEdit) return;
    edEntry = e;
    ui.edErr.hidden = true;
    ui.edErr.textContent = '';
    const parts = String(e.c || '-').split('/');
    const kat = parts.length > 1
      ? catNama(parts[0]) + ' / ' + catNama(parts[1])
      : catNama(parts[0]);
    const grp = grupLabel(e);
    ui.edCtx.textContent = '#' + e.i + ' · ' + kat + (grp ? ' · ' + grp : '');
    ui.edE.value = e.e || '';
    ui.edZ.value = e.z || '';
    ui.edWrap.hidden = false;
    ui.edE.focus();
    ui.edE.select();
  }

  function tutupEditNama() {
    ui.edWrap.hidden = true;
    edEntry = null;
  }

  async function simpanEditNama() {
    const e = edEntry;
    if (!e || ui.edSave.disabled) return;
    if (LIVE) {                       // mode LIVE: tampilkan pesan di modal
      ui.edErr.textContent = t('ro.msg');
      ui.edErr.hidden = false;
      return;
    }
    const namaE = ui.edE.value.trim();
    const namaZ = ui.edZ.value.trim();
    if (namaE === (e.e || '') && namaZ === (e.z || '')) {
      tutupEditNama();
      return;
    }

    ui.edSave.disabled = true;
    ui.edErr.hidden = true;
    try {
      const res = await fetch('/api/rename', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ cat: e.c, i: e.i, e: namaE, z: namaZ }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok || !data.ok) throw new Error(data.error || ('HTTP ' + res.status));

      e.e = namaE;
      e.z = namaZ;
      tutupEditNama();
      dropHaystack();
      markDuplicates();                  // nama bisa membuat entri jadi duplikat
      const jml = state.shown, y = window.scrollY;
      rebuild();
      while (state.shown < jml && state.shown < state.filtered.length) renderChunk();
      window.scrollTo(0, y);

      // kabar sinkron translate: hasil edit ikut ditulis ke data situs
      const site = data.site || {};
      let pesan = fill(t('ed.saved'), { id: e.i });
      if (site.ok === false) pesan += ' · ' + t('ed.siteFail');
      else if (site.stale) pesan += ' · ' + fill(t('ed.siteStale'), { n: site.stale });
      else if (site.index) pesan += ' · ' + t('ed.siteOk');
      toastMsg(pesan);
    } catch (err) {
      ui.edErr.textContent = err.message;
      ui.edErr.hidden = false;
    } finally {
      ui.edSave.disabled = false;
    }
  }

  ui.edCancel.addEventListener('click', tutupEditNama);
  ui.edSave.addEventListener('click', simpanEditNama);
  ui.edWrap.addEventListener('click', ev => {
    if (ev.target === ui.edWrap) tutupEditNama();      // klik area gelap
  });
  ui.edWrap.addEventListener('keydown', ev => {
    if (ev.key === 'Escape') { ev.preventDefault(); tutupEditNama(); }
  });
  [ui.edE, ui.edZ].forEach(inp => {
    inp.addEventListener('keydown', ev => {
      ev.stopPropagation();
      if (ev.key === 'Enter') { ev.preventDefault(); simpanEditNama(); }
      else if (ev.key === 'Escape') { ev.preventDefault(); tutupEditNama(); }
    });
  });

  function togglePick(e) {
    const i = state.picks.indexOf(e.i);
    if (i >= 0) state.picks.splice(i, 1); else state.picks.push(e.i);
  }

  function updatePickUI() {
    ui.pickStat.innerHTML = '<b>' + fmt(state.picks.length) + '</b> ' + t('sel.stat');
    ui.noApply.disabled = state.picks.length === 0;
  }

  function setMode(on) {
    if (on && blokirTulis()) return;
    state.modeNo = on;
    if (!on) state.picks = [];
    ui.modeNo.hidden = on;
    ui.modeNo.classList.toggle('on', on);
    ui.modeWrap.hidden = !on;
    if (on) {
      setSort('game', false);            // urutan yang disusun langsung terlihat
      toastMsg(t('no.modeOn'));
    }
    updatePickUI();
    rebuild();
  }

  function applySequence() {
    const cat = state.cat;
    const picks = state.picks.slice();
    if (cat === 'all' || cat.indexOf('/') < 0 || !picks.length) return;

    const set = new Set(picks);
    const list = state.entries.filter(e => e.c === cat);
    const sisa = list.filter(e => !set.has(e.i)).sort((a, b) =>
      ((a.no == null ? 1e9 : a.no) - (b.no == null ? 1e9 : b.no)) ||
      (a.i - b.i));

    if (!window.confirm(fill(t('no.applyConfirm'), {
      n: picks.length, sisa: sisa.length,
    }))) return;

    let n = 0;
    for (const id of picks) {
      const e = list.find(x => x.i === id);
      if (e) e.no = ++n;
    }
    for (const e of sisa) e.no = ++n;
    renumberGlobal();

    state.picks = [];
    rebuild();
    updatePickUI();
    simpanUrut(cat, fill(t('no.seqKet'), { n: picks.length }));
  }

  /* ---------- urutkan sub kategori ---------- */

  async function muatUlang() {
    await loadIndex();
    state.translations = {};            // urutan entri berubah -> petakan ulang
    dropHaystack();
    await loadLang(state.lang);
    markDuplicates();
    renderCats();
    rebuild();
    updateSelUI();
  }

  function indukAktif() {
    return state.cat === 'all' ? null : state.cat.split('/')[0];
  }

  function masukModeCat() {
    if (blokirTulis()) return;
    const induk = indukAktif();
    if (!induk) { toastMsg(t('cat.needBranch')); return; }
    state.modeCat = true;
    state.catPicks = [];
    renderCats();
    toastMsg(t('cat.modeOn'));
  }

  function keluarModeCat() {
    state.modeCat = false;
    state.catPicks = [];
    renderCats();
  }

  async function kirimUrutSub(body) {
    const res = await fetch('/api/cat_order', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok || !data.ok) throw new Error(data.error || ('HTTP ' + res.status));
    return data;
  }

  async function simpanUrutSub() {
    const induk = indukAktif();
    const order = state.catPicks.slice();
    if (!induk || !order.length) return;
    if (!window.confirm(fill(t('cat.applyConfirm'),
      { n: order.length, branch: catNama(induk) }))) return;
    try {
      const data = await kirimUrutSub({ parent: induk, order });
      state.modeCat = false;
      state.catPicks = [];
      await muatUlang();
      toastMsg(fill(t('cat.applied'),
        { branch: catNama(induk), n: data.n != null ? data.n : order.length }));
    } catch (err) {
      alert(t('cat.applyFail') + ' ' + err.message);
    }
  }

  async function resetUrutSub() {
    const induk = indukAktif();
    if (!induk) return;
    if (!window.confirm(fill(t('cat.resetConfirm'), { branch: catNama(induk) }))) return;
    try {
      await kirimUrutSub({ parent: induk, reset: true });
      state.modeCat = false;
      state.catPicks = [];
      await muatUlang();
      toastMsg(fill(t('cat.resetDone'), { branch: catNama(induk) }));
    } catch (err) {
      alert(t('cat.resetFail') + ' ' + err.message);
    }
  }

  /* ---------- ui wiring ---------- */

  ui.cats.addEventListener('click', ev => {
    const li = ev.target.closest('li');
    if (!li) return;

    if (state.modeCat) {
      if (li.classList.contains('sub')) {       // klik sub = tandai urutan
        const nama = li.dataset.name;
        const i = state.catPicks.indexOf(nama);
        if (i >= 0) state.catPicks.splice(i, 1); else state.catPicks.push(nama);
        renderCats();
        return;
      }
      keluarModeCat();                          // klik induk = tutup mode
    }

    state.cat = li.dataset.cat;
    if (state.modeNo) {
      // no urut dihitung per sub kategori, bukan per induk
      if (state.cat.indexOf('/') < 0) setMode(false);
      else { state.picks = []; updatePickUI(); }
    }
    renderCats();
    rebuild();
    updateSelUI();
  });

  let debounce;
  ui.q.addEventListener('input', () => {
    clearTimeout(debounce);
    debounce = setTimeout(() => { state.q = ui.q.value; rebuild(); }, 110);
  });

  ui.onlyIcon.addEventListener('change', () => { state.onlyIcon = ui.onlyIcon.checked; rebuild(); });
  ui.onlyName.addEventListener('change', () => { state.onlyName = ui.onlyName.checked; rebuild(); });

  ui.onlyDup.addEventListener('change', () => {
    state.onlyDup = ui.onlyDup.checked;
    if (state.onlyDup) { state.onlyUniq = false; ui.onlyUniq.checked = false; }
    rebuild();
  });
  ui.onlyUniq.addEventListener('change', () => {
    state.onlyUniq = ui.onlyUniq.checked;
    if (state.onlyUniq) { state.onlyDup = false; ui.onlyDup.checked = false; }
    rebuild();
  });

  ui.selAll.addEventListener('change', () => {
    if (ui.selAll.checked) state.filtered.forEach(i => state.sel.add(state.entries[i]._key));
    else state.filtered.forEach(i => state.sel.delete(state.entries[i]._key));
    updateSelUI();
  });

  ui.selClear.addEventListener('click', () => {
    state.sel.clear();
    updateSelUI();
  });

  ui.selDelete.addEventListener('click', deleteSelected);

  // -- mode ubah no urut ------------------------------------------------
  ui.modeNo.addEventListener('click', () => {
    if (state.cat === 'all') {
      toastMsg(t('no.needCat'));
      return;
    }
    if (state.cat.indexOf('/') < 0) {
      toastMsg(t('no.needSub'));         // no urut dihitung per sub kategori
      return;
    }
    setMode(true);
  });
  ui.modeExit.addEventListener('click', () => setMode(false));
  ui.noApply.addEventListener('click', applySequence);

  ui.noOrderReset.addEventListener('click', async () => {
    const cat = state.cat;
    if (cat === 'all' || cat.indexOf('/') < 0 || blokirTulis()) return;
    if (!window.confirm(fill(t('no.resetConfirm'), { cat: judulCat() }))) return;
    try {
      await kirimUrut({ cat: cat, reset: true });
      state.picks = [];
      await muatUrutUlang();
      updatePickUI();
      toastMsg(fill(t('no.resetDone'), { cat: judulCat() }));
    } catch (err) {
      alert(t('no.resetFail') + ' ' + err.message);
    }
  });

  // -- mode urutkan sub kategori ---------------------------------------
  ui.catSortOn.addEventListener('click', masukModeCat);
  ui.catExit.addEventListener('click', keluarModeCat);
  ui.catApply.addEventListener('click', simpanUrutSub);
  ui.catReset.addEventListener('click', resetUrutSub);

  function setSort(name, touched) {
    state.sort = name;
    document.querySelectorAll('[data-sort]').forEach(b =>
      b.classList.toggle('on', b.dataset.sort === name));
    if (touched) state.sortTouched = true;
  }

  document.querySelectorAll('[data-sort]').forEach(btn => btn.addEventListener('click', () => {
    setSort(btn.dataset.sort, true);
    rebuild();
  }));

  // rentang no urut — dihitung ulang setelah jeda, seperti pencarian
  let rangeDebounce;
  function readRange() {
    clearTimeout(rangeDebounce);
    rangeDebounce = setTimeout(() => {
      const f = parseInt(ui.noFrom.value, 10);
      const t = parseInt(ui.noTo.value, 10);
      state.noFrom = Number.isFinite(f) && f > 0 ? f : 1;
      state.noTo = Number.isFinite(t) && t > 0 ? t : null;
      // rentang diisi -> tampilan otomatis mengikuti urutan game,
      // selama user belum memilih tombol urutnya sendiri
      if (!state.sortTouched && rangeActive()) setSort('game', false);
      rebuild();
    }, 120);
  }
  ui.noFrom.addEventListener('input', readRange);
  ui.noTo.addEventListener('input', readRange);
  ui.noFrom.addEventListener('change', readRange);
  ui.noTo.addEventListener('change', readRange);

  ui.noReset.addEventListener('click', () => {
    clearTimeout(rangeDebounce);
    ui.noFrom.value = '1';
    ui.noTo.value = '';
    state.noFrom = 1;
    state.noTo = null;
    rebuild();
  });

  // tampilan: Kartu (nama + ikon) · Ikon (hanya ikon) · Daftar
  function setView(v) {
    if (['grid', 'icon', 'list'].indexOf(v) < 0) v = 'grid';
    state.view = v;
    ui.grid.classList.toggle('list', v === 'list');
    ui.grid.classList.toggle('icon', v === 'icon');
    document.querySelectorAll('[data-view]').forEach(b =>
      b.classList.toggle('on', b.dataset.view === v));
    localStorage.setItem('mwdb.view', v);
  }

  document.querySelectorAll('[data-view]').forEach(btn =>
    btn.addEventListener('click', () => setView(btn.dataset.view)));

  // navigasi bisa disembunyikan supaya kartu dapat lebar penuh
  function setNav(on) {
    state.nav = !!on;
    ui.layout.classList.toggle('nav-off', !state.nav);
    ui.navToggle.textContent = state.nav ? t('nav.hide') : t('nav.show');
    localStorage.setItem('mwdb.nav', state.nav ? '1' : '0');
  }

  ui.navToggle.addEventListener('click', () => setNav(!state.nav));

  ui.more.addEventListener('click', renderChunk);

  ui.lang.addEventListener('change', async () => {
    state.lang = ui.lang.value;
    localStorage.setItem('mwdb.lang', state.lang);
    applyLang();                    // seluruh antarmuka ikut berbahasa
    await loadLang(state.lang);
    dropHaystack();
    rebuild();
  });

  document.addEventListener('keydown', ev => {
    if (!ui.edWrap.hidden) return;        // modal ubah nama sedang terbuka
    const typing = /^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement.tagName);
    if (ev.key === '/' && !typing) { ev.preventDefault(); ui.q.focus(); ui.q.select(); }
    if ((ev.key === 'k' || ev.key === 'K') && (ev.metaKey || ev.ctrlKey)) { ev.preventDefault(); ui.q.focus(); ui.q.select(); }
    if (ev.key === 'Escape' && document.activeElement === ui.q) { ui.q.value = ''; state.q = ''; rebuild(); ui.q.blur(); }
    if ((ev.key === 'Delete' || ev.key === 'Backspace') && !typing && state.sel.size) {
      ev.preventDefault();
      deleteSelected();
    }
  });

  /* ---------- boot ---------- */

  function showError(msg) {
    ui.loading.hidden = true;
    ui.error.hidden = false;
    ui.error.innerHTML =
      '<h4>' + t('err.title') + '</h4><p>' + escapeHtml(msg) + '</p>' +
      '<p style="margin-top:6px">' + t(LIVE ? 'err.bodyLive' : 'err.body') + '</p>' +
      '<button class="btn" onclick="location.reload()">' + t('err.btn') + '</button>';
  }

  async function boot() {
    terapkanMode();                    // badge & kunci footer sesuai tebakan mode
    applyLang();                       // teks statis -> bahasa yang dipilih
    try {
      await loadIndex();               // bisa mengoreksi mode LIVE/LOCAL
    } catch (err) {
      showError(err.message);
      return;
    }
    applyLang();                       // ulang — kunci footer bisa sudah berganti

    ui.loading.hidden = true;
    ui.grid.hidden = false;

    markDuplicates();
    renderCats();
    setView(localStorage.getItem('mwdb.view') || 'grid');
    setNav(state.nav);

    rebuild();
    updateSelUI();
    loadLang(state.lang).then(() => { dropHaystack(); rebuild(); });
  }

  boot();
})();
