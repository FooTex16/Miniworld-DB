import json

recs = [json.loads(l) for l in open("output/scan.jsonl", encoding="utf-8") if l.strip()]
print("total record:", len(recs))
gagal = [r for r in recs if not r.get("pick_ok")]
for r in gagal:
    print("  p%d (%d,%d): tooltip=%s ocr=%r icon_clean=%s" % (
        r["page"], r["row"], r["col"], r.get("tooltip_found"),
        r.get("name_ocr"), r.get("icon_clean")))
print("pick_ok:", sum(1 for r in recs if r.get("pick_ok")), "| pick_gagal:", len(gagal))
