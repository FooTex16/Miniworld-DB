"""Backfill fp (thumbnail 16x16 ikon) untuk semua record di scan.jsonl."""
import itertools
import json
import os

from scan import FP_TOL, icon_fp_file

P = "output/scan.jsonl"
recs = [json.loads(l) for l in open(P, encoding="utf-8") if l.strip()]
n = 0
for r in recs:
    ip = r.get("icon")
    if not ip or not os.path.exists(ip):
        continue
    fp = icon_fp_file(ip)
    if fp:
        r["fp"] = fp
        n += 1
with open(P, "w", encoding="utf-8") as f:
    for r in recs:
        f.write(json.dumps(r, ensure_ascii=False) + "\n")
print(f"fp diisi: {n}/{len(recs)}")

# QC: pasangan beda-id yang terlalu mirip -> risiko salah lewat saat dedup
withfp = [r for r in recs if isinstance(r.get("fp"), list) and len(r["fp"]) == 256]
risk = []
for a, b in itertools.combinations(withfp, 2):
    if a.get("id") is not None and a.get("id") == b.get("id"):
        continue
    d = sum(abs(x - y) for x, y in zip(a["fp"], b["fp"])) / len(a["fp"])
    if d <= FP_TOL:
        risk.append((round(d, 2), a.get("id"), a.get("name_final"),
                     b.get("id"), b.get("name_final")))
risk.sort()
print(f"fp terdaftar: {len(withfp)} | pasangan beda-id d<=FP_TOL({FP_TOL}): {len(risk)}")
for r in risk[:15]:
    print("   ", r)
