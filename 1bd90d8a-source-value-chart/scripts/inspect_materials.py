#!/usr/bin/env python3
# inspect_materials.py: scan /input -> materials_report.json (headers, rows, numeric
# columns, unit hints, md pipe tables, CJK fonts). Zero model requests.
import json, os, re, subprocess, sys

NUM = re.compile(r"-?[\d,]*\.?\d+(e[-+]?\d+)?", re.I)
ROW = re.compile(r"^\s*\|?[\w\.\-\+/()% ]+(\|[\w\.\-\+/()% ]+)+\|?\s*$")

def cols_of(header, body):
  return [{"column": header[ci], "n_numeric": sum(1 for r in body if ci < len(r) and NUM.fullmatch(r[ci])),
           "n_total": sum(1 for r in body if ci < len(r))} for ci in range(len(header))]

def sniff(path):
  try:
    lines = open(path, encoding="utf-8-sig", errors="replace").read().splitlines()
  except Exception as e:
    return {"error": str(e)}
  if path.lower().endswith((".csv", ".tsv", ".tab")):
    d = "\t" if not path.lower().endswith(".csv") else ("\t" if lines and lines[0].count("\t") > lines[0].count(",") else ",")
    rows = [l.split(d) for l in lines if l.strip()]
    if not rows:
      return {"kind": "table", "rows": 0}
    h = [c.strip() for c in rows[0]]
    return {"kind": "table", "delimiter": d, "header": h, "n_rows": len(rows) - 1,
            "columns": cols_of(h, rows[1:]),
            "unit_hints": [x for x in h if re.search(r"\(.*?\)|（.*?）|log\d?|fold|%", x, re.I)]}
  tabs, cur = [], []
  for ln in lines:
    if "|" in ln and ROW.match(ln):
      cur.append([c.strip() for c in ln.strip().strip("|").split("|")])
    else:
      if len(cur) >= 2:
        tabs.append(cur)
      cur = []
  if len(cur) >= 2:
    tabs.append(cur)
  out = {"kind": "text", "n_lines": len(lines), "n_tables": len(tabs)}
  for ti, t in enumerate(tabs[:10]):
    out.setdefault("tables", []).append({"table_index": ti, "header": t[0],
                                         "n_rows": len(t) - 1, "columns": cols_of(t[0], t[1:])})
  return out

def main():
  root = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("-") else "/input"
  out = sys.argv[sys.argv.index("--out") + 1] if "--out" in sys.argv else "/app/work/materials_report.json"
  rep = {"root": root, "files": [], "cjk_fonts": [], "notes": []}
  if not os.path.isdir(root):
    rep["notes"].append("input dir missing: " + root)
  else:
    for dp, _, fns in os.walk(root):
      for fn in sorted(fns):
        p = os.path.join(dp, fn)
        e = {"path": p, "size": os.path.getsize(p), "ext": os.path.splitext(fn)[1].lower()}
        if e["ext"] in (".csv", ".tsv", ".tab", ".txt", ".md"):
          e.update(sniff(p))
        rep["files"].append(e)
  try:
    fc = subprocess.run(["fc-list", ":lang=zh", "family"], capture_output=True, text=True, timeout=15).stdout
    rep["cjk_fonts"] = sorted({x.strip() for ln in fc.splitlines() for x in ln.split(",")})[:12]
  except Exception:
    rep["notes"].append("fc-list unavailable")
  os.makedirs(os.path.dirname(out), exist_ok=True)
  json.dump(rep, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
  for e in rep["files"]:
    if e.get("kind") == "table":
      print("TABLE %s rows=%s hdr=%s units=%s" % (e["path"], e.get("n_rows"), e.get("header"), e.get("unit_hints")))
    elif e.get("n_tables"):
      print("TEXT %s tables=%d" % (e["path"], e["n_tables"]))
    else:
      print("FILE %s (%dB)" % (e["path"], e["size"]))
  print("CJK fonts:", ", ".join(rep["cjk_fonts"]) or "NONE")

if __name__ == "__main__":
  main()
