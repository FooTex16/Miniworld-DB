"""Hapus record identitas ganda (id/id_guess + nama) + file ikon yatim."""
import json
import os

P = "output/scan.jsonl"
recs = [json.loads(l) for l in open(P, encoding="utf-8") if l.strip()]

seen, keep, drop_paths = set(), [], []
for r in recs:
    bid = r.get("id") or r.get("id_guess")
    key = (bid, (r.get("name_final") or "").strip().lower()) if bid else None
    if key is not None and key in seen:
        if r.get("icon"):
            drop_paths.append(r["icon"])
        continue
    if key is not None:
        seen.add(key)
    keep.append(r)

kept = {r.get("icon") for r in keep if r.get("icon")}
n_del = 0
for p in set(drop_paths):
    if p not in kept and os.path.exists(p):
        os.remove(p)
        n_del += 1

with open(P, "w", encoding="utf-8") as f:
    for r in keep:
        f.write(json.dumps(r, ensure_ascii=False) + "\n")
print(f"{len(recs)} -> {len(keep)} record | {len(drop_paths)} ganda dibuang | "
      f"{n_del} file ikon yatim dihapus")

ids = sorted({r["id"] for r in keep if r.get("id")})
guess = sorted({r["id_guess"] for r in keep if r.get("id_guess")})
print(f"id unik: {len(ids)} | id_guess unik: {len(guess)} "
      f"({guess[0]}..{guess[-1]})")
