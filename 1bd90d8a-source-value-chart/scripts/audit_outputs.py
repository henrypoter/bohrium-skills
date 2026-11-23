#!/usr/bin/env python3
# audit_outputs.py v5: required-figure coverage gate (anti-omission hard check) +
# verify_map triple deterministic re-check (value domain / geometry / legend) +
# export_spec artifact re-check. Derive the required figure list from
# task.md -> required_outputs.json, then audit /app/output:
#   * every required figure_id must exist with SVG+PNG + editable plot_source +
#     matching chart_type + zero validation errors;
#   * every produced figure's mapping_report.json is independently re-read and
#     re-verified: glyph value == source cell value, pixel geometry proportional to
#     value, legend labels 1:1 with glyph series and verbatim in the source column;
#   * export_spec (dpi / sRGB / size / embedded font) is confirmed in the artifacts.
# Missing/degraded/verify-failed items force status=partial and exit 3.
# Exit 0 = all required outputs present and clean AND verify_map/export pass.
import argparse, csv, difflib, glob, hashlib, json, os, re, sys, zlib

FINAL_OK = ("answered", "complete", "ok", "done", "success")

def to_float(x):
  if x is None:
    return None
  s = str(x).strip().replace(",", "")
  if s in ("", "-", "NA", "N/A", "NaN", "nan", "null", "--"):
    return None
  try:
    v = float(s)
    return v if v == v and abs(v) != float("inf") else None
  except ValueError:
    return None

def read_table(path):
  if not os.path.exists(path):
    return None, None
  if path.lower().endswith((".tsv", ".tab")):
    delim = "\t"
  else:
    with open(path, encoding="utf-8-sig", errors="replace") as f:
      l1 = f.readline()
    delim = "\t" if l1.count("\t") > l1.count(",") else ","
  try:
    with open(path, encoding="utf-8-sig", newline="") as f:
      rows = list(csv.DictReader(f, delimiter=delim))
  except Exception:
    return None, None
  return rows, (list(rows[0].keys()) if rows else [])

def row_field_hash(row, cols):
  h = hashlib.sha256()
  for c in cols:
    h.update((str(c) or "").encode("utf-8"))
    h.update(b"\x00")
    h.update(str(row.get(c, "")).encode("utf-8"))
    h.update(b"\x1f")
  return h.hexdigest()[:16]

def find_figures(outdir):
  figs = {}
  for vj in sorted(glob.glob(os.path.join(outdir, "**", "validation.json"), recursive=True)):
    try:
      v = json.load(open(vj, encoding="utf-8"))
    except Exception:
      continue
    s = v.get("summary") or {}
    fid = s.get("figure_id")
    if not fid:
      continue
    d = os.path.dirname(vj)
    figs[fid] = {"dir": d,
                 "artifacts": {e: os.path.exists(os.path.join(d, fid + e)) and os.path.getsize(os.path.join(d, fid + e)) > 1000
                               for e in (".svg", ".png", ".pdf")},
                 "editable_source": os.path.exists(os.path.join(d, s.get("editable_source", "_"))) if s.get("editable_source") else False,
                 "mapping_report": s.get("mapping_report"), "figure_map": s.get("figure_map"),
                 "score": (s.get("figure") or v.get("figure") or {}).get("score"),
                 "coverage": s.get("coverage") or {},
                 "status": s.get("status"), "panels": s.get("panels") or {},
                 "six_checkpoints": s.get("six_checkpoints") or v.get("six_checkpoints") or {},
                 "errors": [c.get("code") for c in v.get("checks", []) if c.get("level") == "error"]}
  return figs

def png_chunks(b):
  out = []
  if b[:8] != b"\x89PNG\r\n\x1a\n":
    return out
  off = 8
  while off + 8 <= len(b):
    ln = int.from_bytes(b[off:off + 4], "big")
    typ = b[off + 4:off + 8]
    data = b[off + 8:off + 8 + ln]
    out.append((typ, data))
    off += 12 + ln
  return out

def png_dpi(b):
  for typ, data in png_chunks(b):
    if typ == b"pHYs" and len(data) >= 9:
      return int.from_bytes(data[0:4], "big") * 0.0254 if data[8] == 1 else None
  return None

def png_dims(b):
  for typ, data in png_chunks(b):
    if typ == b"IHDR" and len(data) >= 13:
      return int.from_bytes(data[0:4], "big"), int.from_bytes(data[4:8], "big"), data[9]
  return None, None, None

def svg_size(path):
  try:
    import xml.etree.ElementTree as ET
    root = ET.parse(path).getroot()
    def pts(s):
      try:
        return float(str(s).strip().lower().replace("pt", "").replace("px", ""))
      except Exception:
        return None
    return pts(root.attrib.get("width")), pts(root.attrib.get("height")), root.attrib.get("viewBox")
  except Exception:
    return None, None, None

def pdf_mediabox(b):
  m = re.search(rb"/MediaBox\s*\[\s*([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s*\]", b)
  return tuple(float(x) for x in m.groups()) if m else None

def pdf_has_rgb(b):
  if b"/DeviceRGB" in b:
    return True
  if b"/DeviceCMYK" in b or b"/DeviceGray" in b:
    return False
  i = 0
  while True:
    s = b.find(b"stream", i)
    if s == -1:
      break
    e = b.find(b"endstream", s)
    if e == -1:
      break
    raw = b[s + 6:e]
    if raw[:2] == b"\r\n":
      raw = raw[2:]
    elif raw[:1] in (b"\n", b"\r"):
      raw = raw[1:]
    try:
      dec = zlib.decompress(raw)
    except Exception:
      dec = b""
    if re.search(rb"\brg\b|\bRG\b", dec):
      return True
    i = e + 9
  return False

def verify_map(mapping):
  # triple deterministic re-check from mapping_report.json (independent of build code):
  # V1 value domain (glyph value == source cell value; no invented numbers),
  # V2 geometry (pixel position/height proportional to value via panel ylim+bbox),
  # V3 legend (legend labels 1:1 with glyph series and verbatim in source column).
  probs = []
  rep = {"value_domain": "pass", "geometry": "pass", "legend": "pass", "n_checked": 0, "details": []}
  elements = mapping.get("elements") or []
  panels = mapping.get("panels") or {}
  src_cache = {}

  def rows_of(path):
    if path not in src_cache:
      src_cache[path] = read_table(path)
    return src_cache[path]

  domains = {}
  for el in elements:
    src = el.get("source") or {}
    f = src.get("file")
    if not f:
      probs.append("element lacks source.file"); rep["value_domain"] = "fail"; continue
    rows, header = rows_of(f)
    if rows is None:
      probs.append("cannot re-read source %s" % f); rep["value_domain"] = "fail"; continue
    vc = el.get("value_column")
    if vc and vc not in (header or []):
      probs.append("value_column '%s' not in source header %s" % (vc, header)); rep["value_domain"] = "fail"; continue
    if el.get("source_sha256"):
      try:
        h = hashlib.sha256(open(f, "rb").read()).hexdigest()
        if h != el["source_sha256"]:
          probs.append("source version changed: %s" % f); rep["value_domain"] = "fail"
      except OSError:
        probs.append("cannot hash source %s" % f); rep["value_domain"] = "fail"
    rn = (src.get("rows") or [None])[0]
    if el.get("glyph") == "box":
      vals = []
      hc = el.get("hash_columns")
      fhs = el.get("field_sha256s") or []
      for k, rr in enumerate(src.get("rows") or []):
        ri = int(rr) - 2
        if 0 <= ri < len(rows):
          v = to_float(rows[ri].get(vc))
          if v is not None:
            vals.append(v)
          if hc and k < len(fhs) and row_field_hash(rows[ri], hc) != fhs[k]:
            probs.append("row fields changed for box glyph %s row %s" % (el.get("x"), rr))
            rep["value_domain"] = "fail"
      if vals:
        emin, emax = el.get("min"), el.get("max")
        if emin is None or emax is None or abs(emin - min(vals)) > 1e-9 or abs(emax - max(vals)) > 1e-9:
          probs.append("box min/max mismatch glyph %s: got (%s,%s) expected (%s,%s)" %
                       (el.get("x"), emin, emax, min(vals), max(vals)))
          rep["value_domain"] = "fail"
        rep["n_checked"] += 1
      continue
    if el.get("value") is None:
      continue
    if rn is None:
      probs.append("glyph lacks source row"); rep["value_domain"] = "fail"; continue
    ri = int(rn) - 2
    if not (0 <= ri < len(rows)):
      probs.append("source row %s out of range (file has %d rows)" % (rn, len(rows))); rep["value_domain"] = "fail"; continue
    sv = to_float(rows[ri].get(vc))
    ev = el["value"]
    if sv is None or abs(float(sv) - float(ev)) > 1e-6 * max(1.0, abs(float(sv))):
      probs.append("value mismatch: glyph '%s/%s' value=%s but source %s row %s col '%s'=%s" %
                   (el.get("glyph"), el.get("x"), ev, os.path.basename(f), rn, vc, sv))
      rep["value_domain"] = "fail"
    # value must be inside the source column value domain (no invented numbers)
    dom = domains.setdefault((f, vc), sorted({to_float(r.get(vc)) for r in rows if to_float(r.get(vc)) is not None}))
    if dom and not any(abs(float(ev) - d) <= 1e-6 * max(1.0, abs(d)) for d in dom):
      probs.append("value %s not in source domain of %s:%s" % (ev, os.path.basename(f), vc))
      rep["value_domain"] = "fail"
    hc = el.get("hash_columns")
    if hc and el.get("field_sha256") and row_field_hash(rows[ri], hc) != el["field_sha256"]:
      probs.append("row fields changed for glyph '%s/%s' row %s" % (el.get("glyph"), el.get("x"), rn))
      rep["value_domain"] = "fail"
    rep["n_checked"] += 1

  for pid, pm in panels.items():
    yl, bb = pm.get("ylim"), pm.get("axes_bbox")
    if not yl or not bb or yl[1] - yl[0] == 0:
      continue
    y0, h = bb[1], bb[3]
    lo, hi = float(yl[0]), float(yl[1])
    for e in elements:
      if e.get("panel") != pid or e.get("glyph") not in ("bar", "line", "scatter"):
        continue
      if e.get("value") is None or e.get("pixel_y") is None:
        probs.append("glyph missing value/pixel geometry: %s/%s" % (pid, e.get("x"))); rep["geometry"] = "fail"; continue
      v = float(e["value"])
      ey = y0 + (v - lo) / (hi - lo) * h
      tol = 2.0 + 0.01 * abs(h)
      if abs(float(e["pixel_y"]) - ey) > tol:
        probs.append("geometry mismatch panel %s glyph %s value=%s pixel_y=%s expected=%.2f" %
                     (pid, e.get("x"), v, e.get("pixel_y"), ey))
        rep["geometry"] = "fail"
      if e["glyph"] == "bar" and e.get("pixel_h") is not None:
        ey0 = y0 + (0.0 - lo) / (hi - lo) * h
        eh = abs(ey - ey0)
        if abs(float(e["pixel_h"]) - eh) > tol:
          probs.append("bar height mismatch panel %s glyph %s pixel_h=%s expected=%.2f" %
                       (pid, e.get("x"), e.get("pixel_h"), eh))
          rep["geometry"] = "fail"

  for pid, pm in panels.items():
    if pm.get("chart_type") not in ("bar", "line", "scatter"):
      continue
    scol = pm.get("series_column")
    if not scol:
      continue
    labels = pm.get("legend_labels") or []
    pel = [e for e in elements if e.get("panel") == pid and e.get("series")]
    glyph_series = sorted({str(e.get("series")) for e in pel})
    if sorted(str(x) for x in labels) != glyph_series:
      probs.append("legend mismatch panel %s: legend=%s glyph_series=%s" % (pid, labels, glyph_series))
      rep["legend"] = "fail"
    if pel:
      rows, header = rows_of(pel[0]["source"]["file"])
      if rows is not None and scol in (header or []):
        actual = sorted({str(r.get(scol, "")).strip() for r in rows})
        for lb in labels:
          if str(lb) not in actual:
            probs.append("legend label '%s' not verbatim in source column '%s' (values=%s)" % (lb, scol, actual))
            rep["legend"] = "fail"
  return probs, rep

def verify_export(mapping, figdir):
  probs = []
  es = mapping.get("export_spec") or {}
  fid = mapping.get("figure_id") or "figure"
  stem = os.path.join(figdir, fid)
  if not es:
    return ["mapping_report lacks export_spec"], None
  wpt = es.get("figure_width_in", 0) * 72.0
  hpt = es.get("figure_height_in", 0) * 72.0
  w, h, vb = svg_size(stem + ".svg")
  if w is None or abs(w - wpt) >= 2 or abs(h - hpt) >= 2 or not vb:
    probs.append("SVG size/declaration mismatch: width=%s height=%s viewBox=%s expected %.0fx%.0fpt" % (w, h, vb, wpt, hpt))
  try:
    svgtxt = open(stem + ".svg", encoding="utf-8").read()
    if svgtxt.count("<text") <= 0 or "font-family" not in svgtxt:
      probs.append("SVG text not editable: <text> count=%d, font-family declared=%s" %
                   (svgtxt.count("<text"), "font-family" in svgtxt))
  except Exception as e:
    probs.append("SVG text check failed: %s" % e)
  try:
    b = open(stem + ".png", "rb").read()
    dpi = png_dpi(b)
    wp, hp, ct = png_dims(b)
    has_srgb = any(t == b"sRGB" for t, _ in png_chunks(b))
    if dpi is None or abs(dpi - es.get("dpi", 300)) > 1 or ct not in (2, 6) or not has_srgb:
      probs.append("PNG export_spec mismatch: dpi=%s color_type=%s sRGB=%s" % (dpi, ct, has_srgb))
  except Exception as e:
    probs.append("PNG check failed: %s" % e)
  try:
    b = open(stem + ".pdf", "rb").read()
    mb = pdf_mediabox(b)
    rgb = pdf_has_rgb(b)
    t42 = b"/FontFile2" in b or b"/TrueType" in b
    if mb is None or abs(mb[2] - wpt) >= 2 or abs(mb[3] - hpt) >= 2 or not rgb or not t42:
      probs.append("PDF export_spec mismatch: mediabox=%s DeviceRGB=%s type42=%s" % (mb, rgb, t42))
  except Exception as e:
    probs.append("PDF check failed: %s" % e)
  return probs, es

def standard_result(case_id, figs, matched, missing, req, verify):
  outputs = []
  for fid in sorted(figs):
    h = figs[fid]; d = os.path.relpath(h["dir"])
    outputs.append({"figure_id": fid, "role_outputs": {
      "editable_source": [d + "/" + fid + "_plot_source.py"] if h["editable_source"] else [],
      "preview": sorted(d + "/" + fid + e for e, ok in h["artifacts"].items() if ok),
      "mapping": [d + "/" + m for m in (h.get("mapping_report"), h.get("figure_map")) if m],
      "report": [d + "/validation.json"]},
      "figure_score": h.get("score"), "status": h.get("status")})
  nv = sum(c.get("n_valid", 0) for h in figs.values() for c in h["coverage"].values())
  nr = sum(c.get("n_rendered", 0) for h in figs.values() for c in h["coverage"].values())
  sources = {"row_render_rate": (round(nr / nv, 4) if nv else None),
             "rows_rendered": nr, "rows_valid": nv,
             "required_coverage": "%d/%d" % (len(matched), len(req)) if req else "no required list given",
             "required_matched": matched, "required_missing": [m["figure_id"] for m in missing]}
  bad = missing or [fid for fid, p in verify.items() if p.get("problems")]
  return {"case_id": case_id,
          "status": "complete" if not bad else "partial",
          "status_reason": "all required outputs present and clean" if not bad
                           else "required/verify problems: %s" % ([m["figure_id"] for m in missing] + [fid for fid, p in verify.items() if p.get("problems")]),
          "answer": "not_determined_from_materials",
          "outputs": outputs, "sources": sources,
          "changes": [],
          "figures": sorted(figs),
          "validation": {"missing_required": missing, "verify_map": verify},
          "uncertainty": "fill after agent review; changes[] records tradeoffs and manual confirmations",
          "change_log": []}

def main():
  ap = argparse.ArgumentParser()
  ap.add_argument("--outdir", required=True, help="directory holding per-figure output subdirs")
  ap.add_argument("--require", default=None, help="required_outputs.json derived from task.md")
  ap.add_argument("--result", default=None, help="result.json to patch when required items missing")
  ap.add_argument("--out", default=None, help="audit report path (default <outdir>/output_audit.json)")
  a = ap.parse_args()
  figs = find_figures(a.outdir)
  req = []
  if a.require:
    if not os.path.exists(a.require):
      print("FATAL: require file not found: " + a.require, file=sys.stderr); sys.exit(2)
    req = (json.load(open(a.require, encoding="utf-8"))).get("required", [])

  # verify_map + export re-check on every produced figure
  verify = {}
  for fid, h in figs.items():
    probs = []
    mp_path = os.path.join(h["dir"], h.get("mapping_report") or (fid + "_mapping_report.json"))
    if os.path.exists(mp_path):
      try:
        mapping = json.load(open(mp_path, encoding="utf-8"))
        p1, rep = verify_map(mapping)
        p2, _ = verify_export(mapping, h["dir"])
        probs = p1 + p2
        verify[fid] = {"problems": probs, "verify_map": rep, "export_spec": mapping.get("export_spec") or {}}
      except Exception as e:
        probs = ["cannot parse mapping_report: %s" % e]
        verify[fid] = {"problems": probs, "verify_map": {"value_domain": "fail", "geometry": "fail", "legend": "fail"}, "export_spec": {}}
    else:
      probs = ["mapping_report missing: %s" % mp_path]
      verify[fid] = {"problems": probs, "verify_map": None, "export_spec": {}}
    h["verify_problems"] = probs

  matched, missing = [], []
  for r in req:
    fid = r.get("figure_id") or r.get("id")
    if not fid:
      continue
    hit = figs.get(fid)
    if not hit:
      sug = difflib.get_close_matches(fid, list(figs), n=3, cutoff=0.4)
      missing.append({"figure_id": fid, "reason": "not produced",
                      "suggestions": sug, "produced": sorted(figs)})
      continue
    prob = []
    for e in (".svg", ".png"):
      if not hit["artifacts"].get(e):
        prob.append("missing/empty " + fid + e)
    if not hit["editable_source"]:
      prob.append("missing editable plot_source.py")
    ct = r.get("chart_type")
    if ct and ct not in hit["panels"].values():
      prob.append("chart_type '%s' not in produced panels %s" % (ct, hit["panels"]))
    if hit["errors"]:
      prob.append("validation errors: %s" % hit["errors"])
    prob += hit.get("verify_problems") or []
    if prob:
      missing.append({"figure_id": fid, "reason": "; ".join(prob)})
    else:
      matched.append(fid)
  verify_bad = [fid for fid, v in verify.items() if v.get("problems")]
  ok = not missing and not verify_bad
  audit = {"outdir": a.outdir, "n_required": len(req), "n_produced": len(figs),
           "produced": sorted(figs), "matched": matched, "missing": missing,
           "verify_map": verify, "verify_failed": verify_bad,
           "status_gate": "complete" if ok else "partial",
           "rule": "result.json status must NOT be answered/complete while missing/verify problems are non-empty"}
  if not req:
    audit["note"] = "no required list given; completeness NOT proven (derive required_outputs.json from task.md)"
  out = a.out or os.path.join(a.outdir, "output_audit.json")
  os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
  patched = False; emitted = False
  if a.result and os.path.exists(a.result) and (missing or verify_bad):
    res = json.load(open(a.result, encoding="utf-8"))
    if res.get("status") in FINAL_OK:
      res["status"] = "partial"
      res["status_reason"] = "required/verify problems: %s" % ([m["figure_id"] for m in missing] + verify_bad)
      res["missing_required"] = missing
      res["verify_map"] = verify
      json.dump(res, open(a.result, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
      patched = True
  elif a.result and not os.path.exists(a.result):
    cid = "not_determined_from_materials"
    for cj in (os.path.join(os.path.dirname(a.result) or ".", "case.json"), "/input/case.json"):
      if os.path.exists(cj):
        try:
          cid = json.load(open(cj, encoding="utf-8")).get("case_id") or cid
          break
        except Exception:
          pass
    res = standard_result(cid, figs, matched, missing, req, verify)
    json.dump(res, open(a.result, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    emitted = True
  audit["result_patched"] = patched
  audit["result_emitted"] = emitted
  json.dump(audit, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
  print(json.dumps(audit, ensure_ascii=False, indent=1))
  sys.exit(0 if ok else 3)

if __name__ == "__main__":
  main()
