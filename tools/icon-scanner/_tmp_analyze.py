"""Analisis scan.jsonl: jumlah per page, apakah ada fp, dan pasangan fp mirip."""
import itertools
import json

p = "output/scan.jsonl"
recs = [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]
print("total record:", len(recs))

from collections import Counter
print("per page:", dict(sorted(Counter(r.get("page") for r in recs).items())))
print("punya fp :", sum(1 for r in recs if isinstance(r.get("fp"), list)))

done = [r for r in recs if r.get("pick_ok", True) or r.get("locked")]
keys = [(r["page"], r["row"], r["col"]) for r in done]
dup = [k for k, n in Counter(keys).items() if n > 1]
print("kunci (page,row,col) dobel:", len(dup))

# id dobel?
ids = [r["id"] for r in recs if r.get("id")]
dc = [i for i, n in Counter(ids).items() if n > 1]
print("id dobel:", len(dc), dc[:20])

# pasangan fp berbeda id yang terlalu mirip (risiko salah lewati)
withfp = [r for r in recs if isinstance(r.get("fp"), list)]
risk = []
for a, b in itertools.combinations(withfp, 2):
    if a.get("id") == b.get("id"):
        continue
    d = sum(abs(x - y) for x, y in zip(a["fp"], b["fp"])) / 64.0
    if d <= 6.0:
        risk.append((round(d, 2), a.get("id"), a.get("name_final"),
                     b.get("id"), b.get("name_final")))
risk.sort()
print("pasangan fp beda id d <= 6:", len(risk))
for r in risk[:10]:
    print("   ", r)
