#!/usr/bin/env python3
# build_figure.py v4: chart_spec.json -> SVG/PNG/PDF + plot_source.py + mapping_report.json
# (glyph<->row + coverage) + figure_map.md (human-readable map) + validation.json with SIX
# checkpoint categories and figure.score (0-100). Exit 0 ok / 2 fatal.
# Entity literal verification: every column ref / series value must match the source table
# verbatim; a typo is FATAL (exit 2) with difflib top-3 suggestions (e.g. temprature->temperature).
# Quote dual-channel anchoring: any mapping may carry "quote" (verbatim fragment of the data
# file header/first line); the script checks the NORMALIZED quote exists in the file head AND
# contains the referenced column name -- column present but quote absent/mismatched = FATAL.
import argparse, csv, difflib, hashlib, json, math, os, shutil, sys, traceback, zlib

CT = ("bar", "line", "scatter", "box", "heatmap")
EK = ("sd", "se", "sem", "ci", "ci90", "ci95", "ci99")
BAD_CM = {"jet", "rainbow", "hsv", "turbo", "gist_rainbow", "nipy_spectral"}
OKABE = {"#0072B2", "#E69F00", "#009E73", "#D55E00", "#CC79A7", "#56B4E9", "#F0E442", "#000000"}
OUT = ""
BASE = {"font_size": 8, "title_size": 9, "line_width": 1.0, "dpi": 300,
        "figure_width_in": 3.5, "figure_height_in": 2.6,
        "palette": ["#0072B2", "#E69F00", "#009E73", "#D55E00", "#CC79A7", "#56B4E9", "#F0E442", "#000000"],
        "font_family": "sans-serif", "svg_fonttype": "none", "errorbar_capsize": 2.5, "transparent": False,
        "color_space": "sRGB"}

# six checkpoint categories: entity / spatial / encoding / annotation / source / export
SIX = ("entity", "spatial", "encoding", "annotation", "source", "export")
CAT = {"missing_columns": "entity", "series_value_unknown": "entity", "entity_literal": "entity",
       "quote_anchor": "entity", "quote_mismatch": "entity",
       "tick_overlap": "spatial", "tick_bounds": "spatial", "tick_layout": "spatial", "magnitude": "spatial",
       "bar_zero_baseline": "encoding", "colormap_misleading": "encoding", "palette_colorblind": "encoding",
       "unknown_chart_type": "encoding",
       "unit_appended": "annotation", "unit_missing": "annotation", "n_unreported": "annotation",
       "caption_errorbar_unexplained": "annotation", "significance_method_missing": "annotation",
       "cjk_font": "annotation", "cjk_font_missing": "annotation",
       "source_read": "source", "original_kept": "source", "original_missing": "source",
       "empty_cells": "source", "empty_series": "source", "series_filtered": "source",
       "unrendered_rows": "source", "heatmap_gaps": "source", "source_traceable": "source",
       "svg_export": "export", "png_export": "export", "pdf_export": "export", "value_map": "encoding", "geometry_proportional": "spatial",
        "legend_series": "annotation", "source_hash": "source", "png_srgb": "export",
        "export_spec": "export"}

def die(msg, chk=None):
  d = OUT or os.getcwd()
  os.makedirs(d, exist_ok=True)
  payload = {"fatal_error": msg, "six_checkpoints": six_of(chk.checks) if chk else {},
             "figure": {"score": figure_score(chk.checks) if chk else 0, "max": 100,
                        "stop_rule": "fix fatal first, then rerun"},
             "checks": chk.checks if chk else []}
  try:
    json.dump(payload, open(os.path.join(d, "validation.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
  except Exception:
    pass
  print("FATAL: " + msg, file=sys.stderr); sys.exit(2)

def six_of(checks):
  out = {}
  for cat in SIX:
    cs = [c for c in checks if c.get("category") == cat]
    out[cat] = ("not_checked" if not cs else
                "error" if any(c["level"] == "error" for c in cs) else
                "warn" if any(c["level"] == "warn" for c in cs) else "pass")
  return out

def figure_score(checks):
  # figure.score 扣分配比（满分 100；本注释即规范，改配比先改注释）:
  #   每条 error  -12  （实体/拼写错误多为 exit 2 前置拦截，走到此处的多为 unrendered_rows/导出失败）
  #   每条 warn    -3
  #   六类检查点中某一类含 error：该类失守，追加 -8/类
  # 停止条件（与 SKILL.md 写死一致）：先修 error(fail) 再修 warn；score>=90 或剩余 warn 均可解释即停。
  d = sum(12 if c["level"] == "error" else 3 if c["level"] == "warn" else 0 for c in checks)
  d += 8 * sum(1 for v in six_of(checks).values() if v == "error")
  return max(0, 100 - d)

def sug(name, cands):
  m = difflib.get_close_matches(str(name), [str(c) for c in cands], n=3, cutoff=0.35)
  return ("; did you mean %s?" % m) if m else ""

def load_styles(path, preset):
  P = json.load(open(path, encoding="utf-8")) if (path and os.path.exists(path)) else {}
  def res(name, seen):
    if not name or name not in P or name in seen:
      return {}
    seen.add(name); out = {}
    inh = P[name].get("inherits") or []
    if isinstance(inh, str):
      inh = [inh]
    for b in inh:
      out.update(res(b, seen))
    out.update({k: v for k, v in P[name].items() if k != "inherits" and not k.startswith("_")})
    return out
  prof = res(preset, set()) or res("default", set())
  BASE.update({k: v for k, v in prof.items() if not k.startswith("_")})
  return BASE

def pick_cjk_font():
  pref = ("Noto Sans CJK SC", "Noto Sans CJK JP", "Noto Sans CJK HK", "Source Han Sans SC",
          "WenQuanYi Micro Hei", "WenQuanYi Zen Hei", "Droid Sans Fallback", "AR PL UMing CN")
  try:
    from matplotlib import font_manager as fm
    have = {x.name for x in fm.fontManager.ttflist}
    return next((n for n in pref if n in have), None)
  except Exception:
    return None

def read_table(src):
  path = src["file"]; delim = src.get("delimiter")
  if not delim:
    if path.lower().endswith((".tsv", ".tab")):
      delim = "\t"
    else:
      with open(path, encoding="utf-8-sig", errors="replace") as f:
        l1, l2 = f.readline(), f.readline()
      delim = "\t" if l1.count("\t") > l1.count(",") else ","
  with open(path, encoding="utf-8-sig", newline="") as f:
    rows = list(csv.DictReader(f, delimiter=delim))
  return rows, (list(rows[0].keys()) if rows else [])

def to_float(x):
  if x is None:
    return None
  s = str(x).strip().replace(",", "")
  if s in ("", "-", "NA", "N/A", "NaN", "nan", "null", "--"):
    return None
  try:
    v = float(s)
    return v if math.isfinite(v) else None
  except ValueError:
    return None

_SHA = {}
META = {}

def file_sha256(path):
  if path not in _SHA:
    h = hashlib.sha256()
    with open(path, "rb") as f:
      for blk in iter(lambda: f.read(65536), b""):
        h.update(blk)
    _SHA[path] = h.hexdigest()
  return _SHA[path]

def dedup(xs):
  out = []
  for x in xs:
    if x not in out:
      out.append(x)
  return out

def row_field_hash(row, cols):
  # field-level hash: each rendered source field (name + value) -> deterministic digest.
  # a changed value in any rendered field changes this hash, so audit can prove the
  # exact row+columns were not edited after rendering.
  h = hashlib.sha256()
  for c in cols:
    h.update((str(c) or "").encode("utf-8"))
    h.update(b"\x00")
    h.update(str(row.get(c, "")).encode("utf-8"))
    h.update(b"\x1f")
  return h.hexdigest()[:16]

class Chk:
  def __init__(self):
    self.checks = []
  def add(self, lv, code, msg, p="*"):
    self.checks.append({"level": lv, "code": code, "category": CAT.get(code, "annotation"),
                        "message": msg, "panel": p})
  def ok(self, c, m, p="*"): self.add("pass", c, m, p)
  def warn(self, c, m, p="*"): self.add("warn", c, m, p)
  def err(self, c, m, p="*"): self.add("error", c, m, p)

def col_values(rows, col, chk, p):
  vals = [(to_float(r.get(col)), i) for i, r in enumerate(rows)]
  d = sum(1 for v, _ in vals if v is None)
  if d:
    chk.warn("empty_cells", "%s: %d/%d empty dropped" % (col, d, len(rows)), p)
  return vals

def ref(src, j, cols, multi=None):
  return {"file": os.path.abspath(src["file"]), "file_rel": src["file"],
          "columns": cols, "rows": multi or [j + 2]}

def validate_spec(spec, chk):
  errs = []
  if not isinstance(spec, dict):
    return ["spec must be an object"]
  panels = spec.get("panels")
  if not isinstance(panels, list) or not panels:
    errs.append("panels: non-empty list required")
  for i, p in enumerate(panels or []):
    pid = p.get("panel_id") or ("panel#%d" % i)
    ct = p.get("chart_type")
    if ct not in CT:
      errs.append("%s: bad chart_type" % pid)
    if not isinstance(p.get("source"), dict) or not p["source"].get("file"):
      errs.append("%s: source.file required" % pid)
    for k in ("x", "y", "series", "error", "significance", "value"):
      d = p.get(k)
      need = k in ("x", "y") or d is not None
      if need and k != "value" and (not isinstance(d, dict) or not d.get("column")):
        errs.append("%s: %s.column required" % (pid, k))
      if isinstance(d, dict) and d.get("quote") is not None and not isinstance(d["quote"], str):
        errs.append("%s: %s.quote must be a string (verbatim data-file fragment)" % (pid, k))
    if ct == "heatmap" and not isinstance(p.get("value"), dict):
      errs.append("%s: value.column required" % pid)
    if "y2" in p or "secondary_axis" in p:
      errs.append("%s: dual-axis not supported" % pid)
    e = p.get("error") or {}
    if e.get("column") and not e.get("kind"):
      errs.append("%s: error.kind required (sd/se/sem/ci95)" % pid)
    elif e.get("kind") and str(e["kind"]).lower() not in EK:
      errs.append("%s: bad error.kind" % pid)
    sv = (p.get("series") or {}).get("values")
    if sv is not None and not (isinstance(sv, list) and all(isinstance(v, str) for v in sv)):
      errs.append("%s: series.values must be a list of strings" % pid)
  lc = (spec.get("layout") or {}).get("ncols")
  if lc is not None and (not isinstance(lc, int) or lc < 1):
    errs.append("layout.ncols must be int>=1")
  return errs

def norm_text(s):
  # quote normalization channel: whitespace folding, hyphen line-break rejoin, micro-sign unify
  s = str(s).replace("µ", "μ").replace("-\n", "").replace("-\r\n", "")
  return " ".join(s.split())

def verify_quotes(spec, chk):
  # Dual-channel quote anchoring (v4): each mapping {column, quote} -- quote is a verbatim
  # fragment of the data-file header/first line. Channel 1: normalized quote must appear in
  # the normalized file head. Channel 2: the quote must contain the referenced column name
  # (anchors THIS mapping, not some other part of the file). Either channel failing while the
  # column itself exists = mismatch -> FATAL exit 2 (column+quote disagree; trust the file).
  fatal = []; n_checked = 0
  for p in spec["panels"]:
    pid = p.get("panel_id", "?"); src = p["source"]
    try:
      with open(src["file"], encoding="utf-8-sig", errors="replace") as f:
        head = norm_text(f.read(8192))
    except OSError:
      continue
    maps = [("x", p.get("x")), ("y", p.get("y"))]
    for k in ("series", "error", "significance", "value"):
      if p.get(k):
        maps.append((k, p[k]))
    for k, m in maps:
      col, q = m.get("column"), m.get("quote")
      if q is None:
        continue
      n_checked += 1
      nq, ncol = norm_text(q), norm_text(col or "")
      if ncol and ncol not in nq:
        msg = "%s: %s.quote does not contain its column '%s' (quote='%s')" % (pid, k, col, str(q)[:40])
        chk.err("quote_mismatch", msg, pid); fatal.append(msg); continue
      if not nq or nq not in head:
        sug_q = "; file head starts '%s'" % head[:60]
        msg = "%s: %s.quote not found verbatim in %s%s" % (pid, k, os.path.basename(src["file"]), sug_q)
        chk.err("quote_mismatch", msg, pid); fatal.append(msg)
  if n_checked and not fatal:
    chk.ok("quote_anchor", "all %d mapping quotes found verbatim in data-file heads and match their columns" % n_checked)
  return fatal

def verify_entities(spec, tabs, chk):
  # Entity literal verification: every column reference and every declared series
  # value must hit the source table verbatim. Typo -> FATAL exit 2 + difflib top-3.
  fatal = []
  for p in spec["panels"]:
    pid = p.get("panel_id", "?"); src = p["source"]
    rows, header = tabs[src["file"]]
    refs = [("x", p["x"]["column"]), ("y", p["y"]["column"])]
    for k in ("series", "error", "significance", "value"):
      if p.get(k) and p[k].get("column"):
        refs.append((k, p[k]["column"]))
    for k, c in refs:
      if c not in header:
        msg = "%s: %s.column '%s' not in %s%s" % (pid, k, c, os.path.basename(src["file"]), sug(c, header))
        chk.err("missing_columns", msg + " (header=%s)" % header, pid)
        fatal.append(msg)
    sc = p.get("series") or {}
    if sc.get("column") and sc["column"] in header and sc.get("values"):
      actual = []
      for r in rows:
        v = str(r.get(sc["column"], "")).strip()
        if v not in actual:
          actual.append(v)
      for v in sc["values"]:
        if v not in actual:
          msg = "%s: series value '%s' not in column '%s'%s" % (pid, v, sc["column"], sug(v, actual))
          chk.err("series_value_unknown", msg + " (values=%s)" % actual, pid)
          fatal.append(msg)
  if not fatal:
    chk.ok("entity_literal", "all column refs and series values match source verbatim")
  return fatal

def lint_panels(spec, tabs, chk):
  cap = (spec.get("caption") or "").lower()
  for p in spec["panels"]:
    pid, ct = p["panel_id"], p["chart_type"]
    e = p.get("error") or {}
    if e.get("column"):
      if not ((spec.get("statistics") or {}).get("n")):
        chk.warn("n_unreported", "sample size n missing", pid)
      if not any(w in cap for w in ("error bar", "sd", "se", "sem", "ci", "±")):
        chk.warn("caption_errorbar_unexplained", "caption lacks error-bar meaning", pid)
    if p.get("significance") and not (spec.get("statistics") or {}).get("test"):
      chk.warn("significance_method_missing", "no test method", pid)
    if ct == "heatmap" and str(p.get("colormap", "viridis")).lower() in BAD_CM:
      chk.warn("colormap_misleading", "%s forced to viridis" % p.get("colormap"), pid)
      p["colormap"] = "viridis"

def draw_panel(ax, p, tabs, st, chk, mp, meta):
  ct = p["chart_type"]; src = p["source"]
  rows, header = tabs[src["file"]]
  pid0 = p["panel_id"]
  meta[pid0] = {"chart_type": ct, "series_column": None, "legend_labels": []}
  xcol, ycol = p["x"]["column"], p["y"]["column"]
  cols = [xcol, ycol]
  for e in ("series", "error", "significance"):
    if p.get(e) and p[e].get("column"):
      cols.append(p[e]["column"])
  if ct == "heatmap":
    cols.append(p["value"]["column"])
  missing = [c for c in cols if c not in header]
  if missing:
    chk.err("missing_columns", "missing %s (hdr=%s)%s" % (missing, header, sug(missing[0], header)), p["panel_id"])
    return
  ys = [(None, i) for i in range(len(rows))] if ct == "heatmap" else col_values(rows, ycol, chk, p["panel_id"])
  xraw = [str(r.get(xcol, "")).strip() for r in rows]
  ylab, unit = p["y"].get("label", ycol), p["y"].get("unit", "")
  if ct != "heatmap":
    if unit and unit not in ylab:
      ylab += " (%s)" % unit
      chk.ok("unit_appended", "unit added: %s" % unit, p["panel_id"])
    elif not unit:
      chk.warn("unit_missing", "no unit for %s" % ycol, p["panel_id"])
  ax.set_ylabel(ylab, fontsize=st["font_size"])
  ax.set_xlabel(p["x"].get("label", xcol), fontsize=st["font_size"])
  if p.get("title"):
    ax.set_title(p["title"], fontsize=st["title_size"], loc="left")
  ax.tick_params(labelsize=st["font_size"] - 1)
  for s in ("top", "right"):
    ax.spines[s].set_visible(False)
  pal, lw, pid = st["palette"], st["line_width"], p["panel_id"]
  if ct == "bar":
    groups = []
    for xl in xraw:
      if xl not in groups:
        groups.append(xl)
    scol = (p.get("series") or {}).get("column")
    snames = []
    if scol:
      for r in rows:
        s = str(r.get(scol, "")).strip()
        if s not in snames:
          snames.append(s)
      want = (p.get("series") or {}).get("values")
      if want:
        omitted = [v for v in snames if v not in want]
        if omitted:
          chk.warn("series_filtered", "series values not plotted (absent from series.values): %s" % omitted, pid)
        snames = [v for v in want if v in snames]
    else:
      snames = [p["y"].get("label", ycol)]
    ns, width = len(snames), 0.8 / len(snames)
    xp = list(range(len(groups)))
    ecol = (p.get("error") or {}).get("column")
    sig = (p.get("significance") or {}).get("column")
    evd = dict((j, e) for (e, j) in col_values(rows, ecol, chk, pid)) if ecol else {}
    allbv = []
    for si, sn in enumerate(snames):
      bx, bv, be, bj = [], [], [], []
      for gi, g in enumerate(groups):
        for j, (r, (v, i)) in enumerate(zip(rows, ys)):
          if xraw[j] == g and v is not None and (not scol or str(r.get(scol, "")).strip() == sn):
            bx.append(xp[gi] + (si - (ns - 1) / 2) * width)
            bv.append(v); be.append(evd.get(j)); bj.append((gi, j)); break
      if not bx:
        chk.warn("empty_series", "series %s empty" % sn, pid); continue
      allbv += bv
      ax.bar(bx, bv, width=width * 0.9, color=pal[si % len(pal)], edgecolor="black",
             linewidth=0.4, label=sn, yerr=be if ecol else None,
             capsize=st["errorbar_capsize"] if ecol else 0,
             error_kw={"elinewidth": lw * 0.8})
      for k, (x0, v0, (gi, j0)) in enumerate(zip(bx, bv, bj)):
        cols_used = dedup([xcol, ycol] + ([scol] if scol else []) + ([ecol] if ecol else []) + ([sig] if sig else []))
        el = {"panel": pid, "glyph": "bar", "series": sn, "x": groups[gi], "y": v0,
              "value": v0, "dx": x0, "value_column": ycol,
              "error": be[k], "source": ref(src, j0, [xcol, ycol] + ([ecol] if ecol else [])),
              "source_sha256": file_sha256(src["file"]),
              "field_sha256": row_field_hash(rows[j0], cols_used),
              "hash_columns": cols_used}
        if sig:
          t = str(rows[j0].get(sig, "")).strip()
          if t:
            ax.text(x0, v0 + (be[k] or 0.0) + 0.03 * (ax.get_ylim()[1] or 1), t,
                    ha="center", fontsize=st["font_size"] - 2)
            el["significance"] = t
        mp.append(el)
    ax.set_xticks(xp); ax.set_xticklabels(groups)
    if allbv and min(allbv) >= 0:
      ax.set_ylim(bottom=0)
      chk.ok("bar_zero_baseline", "bar axis starts at 0", pid)
    if scol:
      ax.legend(fontsize=st["font_size"] - 1, frameon=False)
      meta[pid0]["series_column"] = scol
      meta[pid0]["legend_labels"] = list(snames)
  elif ct in ("line", "scatter"):
    scol = (p.get("series") or {}).get("column")
    xlabs = []
    for xl in xraw:
      if xl not in xlabs:
        xlabs.append(xl)
    groups = {}
    for j, ((v, i), xl) in enumerate(zip(ys, xraw)):
      if v is None:
        continue
      k = str(rows[j].get(scol, "")).strip() if scol else p["y"].get("label", ycol)
      groups.setdefault(k, []).append((xl, v, j))
    ecol = (p.get("error") or {}).get("column")
    evd = dict((j, e) for (e, j) in col_values(rows, ecol, chk, pid)) if ecol else {}
    for si, (gn, pts) in enumerate(groups.items()):
      xs = [xlabs.index(xl) for xl, v, j in pts]
      yv = [v for xl, v, j in pts]
      js = [j for xl, v, j in pts]
      c = pal[si % len(pal)]
      if ct == "line":
        ax.plot(xs, yv, marker="o", ms=3.5, lw=lw, color=c, label=gn if scol else None)
      else:
        ax.scatter(xs, yv, s=18, color=c, label=gn if scol else None)
      if ecol:
        ax.errorbar(xs, yv, yerr=[evd.get(j) or 0.0 for j in js], fmt="none",
                    ecolor=c, elinewidth=lw * 0.8, capsize=st["errorbar_capsize"])
      for k, j in enumerate(js):
        cols_used = dedup([xcol, ycol] + ([scol] if scol else []) + ([ecol] if ecol else []))
        mp.append({"panel": pid, "glyph": ct, "series": gn, "x": pts[k][0], "y": yv[k],
                   "value": yv[k], "dx": xs[k], "value_column": ycol,
                   "source": ref(src, j, [xcol, ycol] + ([ecol] if ecol else [])),
                   "source_sha256": file_sha256(src["file"]),
                   "field_sha256": row_field_hash(rows[j], cols_used),
                   "hash_columns": cols_used})
    ax.set_xticks(range(len(xlabs)))
    ax.set_xticklabels(xlabs, rotation=p["x"].get("rotation", 0))
    if scol:
      ax.legend(fontsize=st["font_size"] - 1, frameon=False)
      meta[pid0]["series_column"] = scol
      meta[pid0]["legend_labels"] = list(groups.keys())
  elif ct == "box":
    scol = (p.get("series") or {}).get("column")
    cats, data, rows_of = [], [], []
    for j, ((v, i), xl) in enumerate(zip(ys, xraw)):
      if v is None:
        continue
      cat = xl + "|" + str(rows[j].get(scol, "")).strip() if scol else xl
      if cat not in cats:
        cats.append(cat); data.append([]); rows_of.append([])
      idx = cats.index(cat)
      data[idx].append(v); rows_of[idx].append(j)
    bp = ax.boxplot(data, labels=[c.split("|")[0] for c in cats], widths=0.55,
                    patch_artist=True, medianprops={"color": "black", "linewidth": lw})
    for i, pt in enumerate(bp["boxes"]):
      pt.set_facecolor(pal[i % len(pal)]); pt.set_alpha(0.65)
      pt.set_edgecolor("black"); pt.set_linewidth(0.5)
    for ci, (vals, jj) in enumerate(zip(data, rows_of)):
      cols_used = dedup([xcol, ycol] + ([scol] if scol else []))
      mp.append({"panel": pid, "glyph": "box", "series": cats[ci], "n": len(vals),
                 "min": min(vals), "max": max(vals), "value_column": ycol,
                 "source": ref(src, jj[0], [xcol, ycol], multi=[j + 2 for j in jj]),
                 "source_sha256": file_sha256(src["file"]),
                 "field_sha256s": [row_field_hash(rows[j], cols_used) for j in jj],
                 "hash_columns": cols_used})
    if scol:
      meta[pid0]["series_column"] = scol
  elif ct == "heatmap":
    import numpy as np
    vcol, xcl, ycl = p["value"]["column"], p["x"]["column"], p["y"]["column"]
    xs, ysl, grid = [], [], {}
    for j, r in enumerate(rows):
      v = to_float(r.get(vcol))
      if v is None:
        continue
      a, b = str(r[xcl]).strip(), str(r[ycl]).strip()
      if a not in xs:
        xs.append(a)
      if b not in ysl:
        ysl.append(b)
      grid[(a, b)] = (v, j)
    M = np.full((len(ysl), len(xs)), np.nan)
    for (a, b), (v, j) in grid.items():
      M[ysl.index(b), xs.index(a)] = v
      cols_used = [xcl, ycl, vcol]
      mp.append({"panel": pid, "glyph": "heatmap_cell", "x": a, "y": b, "value": v,
                 "value_column": vcol,
                 "source": ref(src, j, [xcl, ycl, vcol]),
                 "source_sha256": file_sha256(src["file"]),
                 "field_sha256": row_field_hash(rows[j], cols_used),
                 "hash_columns": cols_used})
    im = ax.imshow(M, aspect="auto", cmap=p.get("colormap", "viridis"))
    ax.set_xticks(range(len(xs))); ax.set_xticklabels(xs, rotation=45, ha="right")
    ax.set_yticks(range(len(ysl))); ax.set_yticklabels(ysl)
    ax.figure.colorbar(im, ax=ax, shrink=0.85, label=p["value"].get("label", vcol))
    ng = int(np.isnan(M).sum())
    if ng:
      chk.warn("heatmap_gaps", "%d blank cells" % ng, pid)
  else:
    chk.err("unknown_chart_type", ct, pid)

def check_spatial(fig, axes, panels, nc, chk):
  # tick labels must neither overlap each other nor be clipped by the figure edge
  try:
    fig.canvas.draw()
    ren = fig.canvas.get_renderer()
  except Exception:
    return
  before = len(chk.checks)
  fb = fig.bbox
  tol = fig.dpi / 72.0 * 1.5  # 1.5 pt slack: sub-pixel rounding of the topmost tick is not clipping
  for k, p in enumerate(panels):
    ax = axes[k // nc][k % nc]; pid = p["panel_id"]
    for ori, axis, labels in (("x", ax.xaxis, ax.get_xticklabels()), ("y", ax.yaxis, ax.get_yticklabels())):
      locs = list(axis.get_majorticklocs())
      lo, hi = sorted(ax.get_xlim() if ori == "x" else ax.get_ylim())
      # skip ticks outside the view interval: matplotlib does not draw them and
      # their label artists carry stale bounding boxes (false positives)
      labs = [l for l, lc in zip(labels, locs) if l.get_text().strip() and lo - 1e-9 <= lc <= hi + 1e-9]
      boxes = [l.get_window_extent(ren) for l in labs]
      nov = sum(1 for i in range(len(boxes)) for j in range(i + 1, len(boxes)) if boxes[i].overlaps(boxes[j]))
      if nov:
        chk.warn("tick_overlap", "%s-axis: %d overlapping tick-label pair(s)" % (ori, nov), pid)
      outs = [l.get_text() for l, b in zip(labs, boxes)
              if not (fb.contains(b.x0 - tol, b.y0 - tol) and fb.contains(b.x1 + tol, b.y1 + tol))]
      if outs:
        chk.warn("tick_bounds", "%s-axis tick label(s) clipped by figure edge: %s" % (ori, outs[:3]), pid)
  if not any(c["code"] in ("tick_overlap", "tick_bounds") for c in chk.checks[before:]):
    chk.ok("tick_layout", "tick labels non-overlapping and within figure bounds")

def attach_pixel_geometry(axes, panels, nc, mp, meta):
  # v17 value->pixel map: after tight_layout/draw, transform each glyph's data
  # coordinate to figure-pixel coordinates and record pixel_h / pixel_y, plus the
  # panel's ylim + axes bbox so audit can independently recompute expected pixels.
  axmap = {}
  for k, p in enumerate(panels):
    axmap[p["panel_id"]] = axes[k // nc][k % nc]
  for el in mp:
    ax = axmap.get(el["panel"])
    if ax is None or "dx" not in el or el.get("value") is None:
      continue
    try:
      px, py = ax.transData.transform((el["dx"], el["value"]))
      el["pixel_x"] = round(float(px), 2)
      el["pixel_y"] = round(float(py), 2)
      if el["glyph"] == "bar":
        _, py0 = ax.transData.transform((el["dx"], 0.0))
        el["pixel_y0"] = round(float(py0), 2)
        el["pixel_h"] = round(abs(py - py0), 2)
    except Exception:
      continue
  for p in panels:
    ax = axmap[p["panel_id"]]
    xl = ax.get_xlim(); yl = ax.get_ylim()
    bb = ax.bbox.bounds
    d = meta.setdefault(p["panel_id"], {})
    d["chart_type"] = p["chart_type"]
    d["ylim"] = [float(yl[0]), float(yl[1])]
    d["xlim"] = [float(xl[0]), float(xl[1])]
    d["axes_bbox"] = [round(float(b), 2) for b in bb]
    d["value_column"] = p["value"]["column"] if p["chart_type"] == "heatmap" else p["y"]["column"]

def selfcheck_value_map(mp, chk):
  # build-time sanity: every bar/line/scatter glyph carries value + pixel geometry,
  # and recorded pixel position matches the value->pixel linear map of its panel
  # (bars: pixel_h / |value| constant; points: pixel_y linear in value). The
  # authoritative independent re-check lives in audit_outputs.py verify_map.
  from collections import defaultdict
  byp = defaultdict(list)
  for el in mp:
    if el.get("glyph") in ("bar", "line", "scatter"):
      byp[el["panel"]].append(el)
  n_ok = 0
  for pid, els in sorted(byp.items()):
    bars = [e for e in els if e["glyph"] == "bar" and e.get("pixel_h") is not None and e.get("value") != 0]
    pts = [e for e in els if e["glyph"] in ("line", "scatter") and e.get("pixel_y") is not None]
    bad = False
    if len(bars) >= 2:
      r0 = bars[0]["pixel_h"] / abs(bars[0]["value"])
      spread = max(abs(e["pixel_h"] / abs(e["value"]) - r0) for e in bars)
      if spread > r0 * 0.02 + 0.5:
        chk.err("geometry_proportional", "%s: bar pixel_h not proportional to value (max spread %.2f px)" % (pid, spread), pid)
        bad = True
    if len(pts) >= 3:
      vs = [e["value"] for e in pts]; pys = [e["pixel_y"] for e in pts]
      vmin, vmax = min(vs), max(vs)
      if vmax - vmin > 0:
        b = (max(pys) - min(pys)) / (vmax - vmin)
        a = min(pys) - b * vmin
        resid = max(abs(py - (a + b * v)) for py, v in zip(pys, vs))
        if resid > 0.5 + 0.02 * (max(pys) - min(pys)):
          chk.err("geometry_proportional", "%s: point pixel_y not linear in value (max resid %.2f px)" % (pid, resid), pid)
          bad = True
    if not bad:
      n_ok += 1
  mapped = [e for e in mp if e.get("glyph") in ("bar", "line", "scatter")]
  if n_ok and mapped:
    chk.ok("value_map", "value->pixel map recorded for %d glyphs across %d panel(s)" % (len(mapped), n_ok))
  elif mapped:
    chk.err("value_map", "value->pixel geometry missing for %d glyph(s)" % len(mapped))

def png_chunks(b):
  out = []
  if b[:8] != b"\x89PNG\r\n\x1a\n":
    return out
  off = 8
  while off + 8 <= len(b):
    ln = int.from_bytes(b[off:off + 4], "big")
    typ = b[off + 4:off + 8]
    data = b[off + 8:off + 8 + ln]
    out.append((typ, data, off))
    off += 12 + ln
  return out

def png_dpi(b):
  for typ, data, _ in png_chunks(b):
    if typ == b"pHYs" and len(data) >= 9:
      x = int.from_bytes(data[0:4], "big")
      return x * 0.0254 if data[8] == 1 else None
  return None

def inject_png_srgb(path):
  # declare color space in PNG metadata: insert an sRGB chunk (rendering intent 0)
  # right after IHDR. matplotlib PNGs are sRGB by convention but do not declare it.
  b = open(path, "rb").read()
  if b[:8] != b"\x89PNG\r\n\x1a\n":
    raise ValueError("not a PNG")
  for typ, data, off in png_chunks(b):
    if typ == b"IHDR":
      end = off + 12 + len(data)
      payload = b"sRGB" + b"\x00"
      chunk = len(b"\x00").to_bytes(4, "big") + payload + (zlib.crc32(payload) & 0xffffffff).to_bytes(4, "big")
      open(path, "wb").write(b[:end] + chunk + b[end:])
      return True
  raise ValueError("no IHDR chunk")

def check_exports(stem, st, chk, fig_w_in, fig_h_in):
  # export_spec verification: size / color space / font embedding / dpi must land
  # in the exported artifact metadata (or at least the SVG declaration).
  sp = stem + ".svg"
  wpt, hpt = fig_w_in * 72.0, fig_h_in * 72.0
  try:
    import xml.etree.ElementTree as ET
    root = ET.parse(sp).getroot()
    svgtxt = open(sp, encoding="utf-8").read()
    nt = svgtxt.count("<text")
    w = root.attrib.get("width", ""); h = root.attrib.get("height", "")
    vb = root.attrib.get("viewBox")
    def pts(s):
      s = str(s).strip().lower().replace("pt", "").replace("px", "")
      try:
        return float(s)
      except ValueError:
        return None
    wv, hv = pts(w), pts(h)
    size_ok = (wv is not None and hv is not None and abs(wv - wpt) < 2 and abs(hv - hpt) < 2 and vb is not None)
    fam_ok = "font-family" in svgtxt or "font_family" in svgtxt
    if nt and size_ok and fam_ok:
      chk.ok("svg_export", "SVG %.0fx%.0fpt viewBox=%s; %d <text> nodes; font-family declared (svg.fonttype=%s)" %
             (wv, hv, vb, nt, st["svg_fonttype"]))
    else:
      chk.warn("svg_export", "SVG present but size/declaration incomplete: size_ok=%s fam_ok=%s <text>=%d" % (size_ok, fam_ok, nt))
  except Exception as e:
    chk.err("svg_export", "SVG not well-formed: %s" % e)
  try:
    b = open(stem + ".png", "rb").read()
    chunks = png_chunks(b)
    d = png_dpi(b)
    ihdr = next((d0 for t, d0, _ in chunks if t == b"IHDR"), None)
    wpx = hpx = ctyp = None
    if ihdr and len(ihdr) >= 13:
      wpx = int.from_bytes(ihdr[0:4], "big"); hpx = int.from_bytes(ihdr[4:8], "big")
      ctyp = ihdr[9]
    has_srgb = any(t == b"sRGB" for t, _, _ in chunks)
    rgb = ctyp in (2, 6)
    size_ok = (wpx is not None and abs(wpx - round(fig_w_in * st["dpi"])) <= 1 and abs(hpx - round(fig_h_in * st["dpi"])) <= 1)
    dpi_ok = d is not None and abs(d - st["dpi"]) <= 1
    if b[:8] == b"\x89PNG\r\n\x1a\n" and len(b) > 1000:
      if dpi_ok and size_ok and rgb and has_srgb:
        chk.ok("png_export", "PNG %dx%d px dpi=%s RGB=%s sRGB=%s" % (wpx, hpx, round(d) if d else "n/a", rgb, has_srgb))
      else:
        chk.warn("png_export", "PNG spec mismatch: dpi_ok=%s size_ok=%s RGB=%s sRGB=%s (dpi=%s)" %
                 (dpi_ok, size_ok, rgb, has_srgb, round(d) if d else "n/a"))
    else:
      chk.err("png_export", "PNG missing or truncated (%d bytes)" % len(b))
  except Exception as e:
    chk.err("png_export", "PNG check failed: %s" % e)
  try:
    b = open(stem + ".pdf", "rb").read()
    if b[:5] == b"%PDF-" and len(b) > 1000:
      t42 = b"/FontFile2" in b or b"/TrueType" in b
      rgb = pdf_has_rgb(b)
      mb = re_mediabox(b)
      mok = mb is not None and abs(mb[2] - wpt) < 2 and abs(mb[3] - hpt) < 2
      if t42 and rgb and mok:
        chk.ok("pdf_export", "PDF %.0fx%.0fpt DeviceRGB=%s TrueType(type42)=%s" % (mb[2], mb[3], rgb, t42))
      else:
        chk.warn("pdf_export", "PDF spec mismatch: size_ok=%s DeviceRGB=%s type42=%s" % (mok, rgb, t42))
    else:
      chk.err("pdf_export", "PDF missing or truncated (%d bytes)" % len(b))
  except Exception as e:
    chk.err("pdf_export", "PDF check failed: %s" % e)
  # aggregate export_spec evidence into one check
  codes = ["svg_export", "png_export", "pdf_export"]
  lv = [c for c in chk.checks if c["code"] in codes]
  if lv and all(c["level"] == "ok" or c["level"] == "pass" for c in lv):
    chk.ok("export_spec", "export_spec dpi=%d colorspace=%s font=embedded size=%.2fx%.2fin verified" %
           (st["dpi"], st["color_space"], fig_w_in, fig_h_in))

def re_mediabox(b):
  import re
  m = re.search(rb"/MediaBox\s*\[\s*([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s*\]", b)
  if not m:
    return None
  return tuple(float(x) for x in m.groups())

def pdf_has_rgb(b):
  # matplotlib vector PDFs rely on the DeviceRGB default; the /DeviceRGB token is
  # usually absent and the rg/RG operators live inside FlateDecode streams, so
  # decompress every stream and look for RGB color operators (never CMYK/Gray).
  if b"/DeviceRGB" in b:
    return True
  if b"/DeviceCMYK" in b or b"/DeviceGray" in b:
    return False
  import re
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

def index_and_cover(tabs, panels, mp):
  by = {}
  for idx, el in enumerate(mp):
    for rr in (el.get("source", {}).get("rows") or []):
      by.setdefault(el["source"].get("file", "?"), {}).setdefault(rr, []).append(idx)
  byp = {}
  for el in mp:
    byp.setdefault(el["panel"], []).append(el)
  cov = {}
  for p in panels:
    pid = p["panel_id"]
    rows = tabs[p["source"]["file"]][0]
    yc = p["value"]["column"] if p["chart_type"] == "heatmap" else p["y"]["column"]
    valid = {i for i, r in enumerate(rows) if to_float(r.get(yc)) is not None}
    rendered = set()
    for el in byp.get(pid, []):
      for rr in (el.get("source", {}).get("rows") or []):
        rendered.add(int(rr) - 2)
    un = sorted(valid - rendered)
    cov[pid] = {"n_rows": len(rows), "n_valid": len(valid), "n_rendered": len(rendered & valid),
                "unrendered_rows": [i + 2 for i in un]}
  return cov, by

def write_figure_map(path, fid, panels, mp, cov, quotes_by_panel):
  # Human-readable mapping table (v4 deliverable C): series/glyph -> data columns + row
  # range + hit status, one row per (panel, glyph, series); plus per-panel coverage and
  # unrendered-row rows so a human can audit the figure without opening JSON.
  L = ["# figure_map — %s" % fid, "",
       "图元/系列 → 数据列 + 行区间（源文件行号，表头为第 1 行）+ 命中状态。", "",
       "| 面板 | 图元 | 系列 | 数据文件 | 数据列 | 行区间(命中行数) | 命中状态 |",
       "|---|---|---|---|---|---|---|"]
  for p in panels:
    pid = p["panel_id"]
    groups = {}
    for e in mp:
      if e["panel"] != pid:
        continue
      key = (e.get("glyph", "?"), str(e.get("series", "—")))
      g = groups.setdefault(key, {"file": e["source"].get("file", "?"), "cols": [], "rows": []})
      for c in e["source"].get("columns", []):
        if c not in g["cols"]:
          g["cols"].append(c)
      g["rows"] += e["source"].get("rows", [])
    for (glyph, series), g in groups.items():
      rr = sorted(set(g["rows"]))
      rng = ("%d–%d (%d)" % (rr[0], rr[-1], len(rr))) if rr else "—"
      L.append("| %s | %s | %s | %s | %s | %s | ✓ 已渲染可回溯 |" %
               (pid, glyph, series, os.path.basename(g["file"]), ", ".join(g["cols"]), rng))
    c = cov.get(pid, {})
    un = c.get("unrendered_rows") or []
    if un:
      L.append("| %s | — | — | %s | %s | %s | ✗ 未渲染行 %s |" %
               (pid, os.path.basename(p["source"]["file"]),
                p["value"]["column"] if p["chart_type"] == "heatmap" else p["y"]["column"],
                "—", un))
    L.append("| %s | **覆盖率** | — | — | — | %d/%d 有效行已渲染 | %s |" %
             (pid, c.get("n_rendered", 0), c.get("n_valid", 0),
              "✗ 有漏行" if un else "✓"))
    qp = quotes_by_panel.get(pid)
    if qp:
      L.append("| %s | **quote 锚定** | — | — | — | %d 条映射带逐字 quote | ✓ 双通道核验通过 |" % (pid, qp))
  L.append("")
  with open(path, "w", encoding="utf-8") as f:
    f.write("\n".join(L))

def main():
  global OUT
  ap = argparse.ArgumentParser()
  ap.add_argument("--spec", required=True)
  ap.add_argument("--outdir", required=True)
  ap.add_argument("--styles", default=None)
  a = ap.parse_args()
  OUT = a.outdir
  if not os.path.exists(a.spec):
    die("spec not found: " + a.spec)
  with open(a.spec, encoding="utf-8") as f:
    spec = json.load(f)
  os.makedirs(a.outdir, exist_ok=True)
  chk = Chk()
  errs = validate_spec(spec, chk)
  if errs:
    die("spec invalid: " + " | ".join(errs), chk)
  st = load_styles(a.styles or spec.get("styles"), spec.get("style", "default"))
  bad = [c for c in st.get("palette", []) if str(c).upper() not in OKABE]
  if bad:
    chk.warn("palette_colorblind", "palette colors outside Okabe-Ito colorblind-safe set: %s" % bad)
  else:
    chk.ok("palette_colorblind", "palette is Okabe-Ito colorblind-safe (Wong 2011)")
  fid = spec.get("figure_id", "figure")
  base = spec.get("source_figure")
  if base and os.path.exists(base):
    dst = os.path.join(a.outdir, "original_reference" + os.path.splitext(base)[1])
    shutil.copyfile(base, dst)
    chk.ok("original_kept", dst)
  elif base:
    chk.warn("original_missing", base)
  tabs = {}
  for p in spec["panels"]:
    f = p["source"]["file"]
    if f not in tabs:
      if not os.path.exists(f):
        die("source data not found: " + f, chk)
      tabs[f] = read_table(p["source"])
      chk.ok("source_read", "%s: %d rows" % (f, len(tabs[f][0])))
  fatal = verify_entities(spec, tabs, chk)
  fatal += verify_quotes(spec, chk)
  if fatal:
    die("entity verification failed: " + " | ".join(fatal), chk)
  lint_panels(spec, tabs, chk)
  import matplotlib
  matplotlib.use("Agg")
  import matplotlib.pyplot as plt
  if any("一" <= c <= "鿿" for c in json.dumps(spec, ensure_ascii=False)):
    cj = pick_cjk_font()
    if cj:
      fams = [cj, st["font_family"]]
      chk.ok("cjk_font", cj)
    else:
      fams = [st["font_family"]]
      chk.warn("cjk_font_missing", "CJK labels but no CJK font")
  else:
    fams = [st["font_family"]]
  plt.rcParams.update({"font.family": fams, "font.size": st["font_size"],
                       "svg.fonttype": st["svg_fonttype"], "axes.linewidth": st["line_width"],
                       "figure.dpi": 120, "savefig.dpi": st["dpi"],
                       "pdf.fonttype": 42, "ps.fonttype": 42,
                       "svg.hashsalt": "source-value-chart-v5"})
  panels = spec["panels"]; n = len(panels)
  nc = (spec.get("layout") or {}).get("ncols") or (1 if n == 1 else 2)
  nr = math.ceil(n / nc)
  fig, axes = plt.subplots(nr, nc, figsize=(st["figure_width_in"] * nc, st["figure_height_in"] * nr), squeeze=False)
  mp = []
  meta = {}
  for k, p in enumerate(panels):
    draw_panel(axes[k // nc][k % nc], p, tabs, st, chk, mp, meta)
  for k in range(n, nr * nc):
    axes[k // nc][k % nc].axis("off")
  for p in panels:
    yc = p["value"]["column"] if p["chart_type"] == "heatmap" else p["y"]["column"]
    vals = [v for v in (to_float(r.get(yc)) for r in tabs[p["source"]["file"]][0]) if v is not None]
    if vals:
      mx = max(abs(v) for v in vals)
      if mx >= 1e6 or 0 < mx < 1e-3:
        chk.warn("magnitude", "%s |max|=%.3g extreme" % (yc, mx), p["panel_id"])
  fig.tight_layout()
  check_spatial(fig, axes, panels, nc, chk)
  attach_pixel_geometry(axes, panels, nc, mp, meta)
  selfcheck_value_map(mp, chk)
  fig_w_in = st["figure_width_in"] * nc
  fig_h_in = st["figure_height_in"] * nr
  stem = os.path.join(a.outdir, fid)
  for ext in (".svg", ".png", ".pdf"):
    save_meta = {"Date": None, "Creator": None} if ext != ".pdf" else {"CreationDate": None, "Creator": None}
    fig.savefig(stem + ext, transparent=st["transparent"], metadata=save_meta)
  try:
    inject_png_srgb(stem + ".png")
    chk.ok("png_srgb", "PNG sRGB chunk injected (colorspace declared)")
  except Exception as e:
    chk.warn("png_srgb", "PNG sRGB inject failed: %s" % e)
  plt.close(fig)
  check_exports(stem, st, chk, fig_w_in, fig_h_in)
  cov, by = index_and_cover(tabs, panels, mp)
  for pid, c in cov.items():
    if c["unrendered_rows"]:
      chk.err("unrendered_rows", "%s: %d rows not rendered: %s" % (pid, len(c["unrendered_rows"]), c["unrendered_rows"]), pid)
  if mp and all((el.get("source") or {}).get("rows") for el in mp):
    chk.ok("source_traceable", "all %d glyphs linked to source file+columns+rows" % len(mp))
  src_out = stem + "_plot_source.py"
  with open(__file__, encoding="utf-8") as f:
    self_src = f.read()
  with open(src_out, "w", encoding="utf-8") as f:
    f.write("# Editable source: regenerates %s from data + spec %s\n\n%s" % (fid, os.path.abspath(a.spec), self_src))
  src_versions = {}
  for f in tabs:
    src_versions[os.path.abspath(f)] = {"sha256": file_sha256(f), "n_rows": len(tabs[f][0])}
  with open(stem + "_mapping_report.json", "w", encoding="utf-8") as f:
    json.dump({"figure_id": fid, "spec": os.path.abspath(a.spec), "n_elements": len(mp),
               "elements": mp, "by_row": by, "coverage": cov,
               "panels": meta, "source_versions": src_versions,
               "export_spec": {"dpi": st["dpi"], "color_space": st["color_space"],
                               "figure_width_in": fig_w_in, "figure_height_in": fig_h_in,
                               "font_family": st["font_family"], "pdf_fonttype": 42,
                               "svg_fonttype": st["svg_fonttype"]}},
              f, ensure_ascii=False, indent=1)
  qbp = {}
  for p in panels:
    nq = sum(1 for m in [p.get("x"), p.get("y"), p.get("series"), p.get("error"),
                         p.get("significance"), p.get("value")] if m and m.get("quote"))
    if nq:
      qbp[p["panel_id"]] = nq
  write_figure_map(stem + "_figure_map.md", fid, panels, mp, cov, qbp)
  with open(stem + "_caption.txt", "w", encoding="utf-8") as f:
    f.write(spec.get("caption", "") + "\n")
  errs = [c for c in chk.checks if c["level"] == "error"]
  fs = figure_score(chk.checks)
  score_blk = {"score": fs, "max": 100,
               "deductions": "error -12 each; warn -3 each; checkpoint category with error -8 extra (see figure_score comment)",
               "stop_rule": "fix error first, then warn; stop when score>=90 or every remaining warn is explainable"}
  summary = {"figure_id": fid, "status": "ok" if not errs else "degraded",
             "panels": {p["panel_id"]: p["chart_type"] for p in panels},
             "six_checkpoints": six_of(chk.checks),
             "figure": score_blk,
             "artifacts": {e: os.path.basename(stem + e) for e in (".svg", ".png", ".pdf")},
             "editable_source": os.path.basename(src_out),
             "mapping_report": os.path.basename(stem + "_mapping_report.json"),
             "figure_map": os.path.basename(stem + "_figure_map.md"),
             "n_elements_mapped": len(mp),
             "n_with_pixel": sum(1 for e in mp if e.get("pixel_y") is not None),
             "source_versions": src_versions,
             "export_spec": {"dpi": st["dpi"], "color_space": st["color_space"],
                             "figure_width_in": fig_w_in, "figure_height_in": fig_h_in},
             "coverage": cov,
             "warnings": [c for c in chk.checks if c["level"] == "warn"], "errors": errs}
  with open(os.path.join(a.outdir, "validation.json"), "w", encoding="utf-8") as f:
    json.dump({"summary": summary, "six_checkpoints": six_of(chk.checks),
               "figure": score_blk, "checks": chk.checks},
              f, ensure_ascii=False, indent=1)
  print(json.dumps(summary, ensure_ascii=False, indent=1))

if __name__ == "__main__":
  try:
    main()
  except SystemExit:
    raise
  except Exception:
    traceback.print_exc()
    die("unexpected exception")
