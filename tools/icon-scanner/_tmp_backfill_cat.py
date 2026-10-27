"""Lengkapi field `cat` (breadcrumb kategori) pada record yang belum punya.

Sebelum fitur breadcrumb ada, record tidak menyimpan kategori. Sumber:
  1. mayoritas `cat` record lain pada halaman yang sama, lalu
  2. riwayat scan (PAGE_CAT):
       halaman 1-3 -> Blocks > Terrain  (81 blok unik; baris akhir tinggal 1 sel)
       halaman 6-8 -> Blocks > Natural  (1 record hal.6 + seluruh hal.7-8)
"""
import collections
import json
import os

JSONL = "output/scan.jsonl"
PAGE_CAT = {
    1: "Blocks > Terrain", 2: "Blocks > Terrain", 3: "Blocks > Terrain",
    6: "Blocks > Natural", 7: "Blocks > Natural", 8: "Blocks > Natural",
}

recs = []
with open(JSONL, encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if line:
            recs.append(json.loads(line))

# mayoritas cat per halaman
per_page = collections.defaultdict(collections.Counter)
for r in recs:
    if r.get("cat"):
        per_page[r["page"]][r["cat"]] += 1

n = 0
for r in recs:
    if r.get("cat"):
        continue
    cat = (per_page.get(r["page"], collections.Counter()).most_common(1)
           or [(None, 0)])[0][0] or PAGE_CAT.get(r["page"], "")
    if not cat:
        print(f"  [!] page {r['page']} tanpa kategori -> dilewati")
        continue
    r["cat"] = cat
    n += 1

if n:
    tmp = JSONL + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        for r in recs:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    os.replace(tmp, JSONL)

print(f"backfill: {n} record dilengkapi kategori")
print("rekap kategori:",
      dict(collections.Counter(r.get("cat") for r in recs)))
