#!/usr/bin/env python3
"""check_figure.py: six-checkpoint audit for source-bound schematics. Stdlib only.
Usage: check_figure.py figure.svg elements.json source_file [source_file ...]
Writes trace_report.json AND figure_map.md next to figure.svg.
Exit 0 = no fail (warnings allowed); 1 = needs_confirmation (>=1 fail).
Criteria EXTERNAL (assets/edge_rules.json, assets/palette.json). Checkpoints:
  ENTITY      every node/edge label + numeric+unit token hits sources VERBATIM
              (normalization: whitespace collapse, hyphen-newline read both ways,
              case-insensitive); misses get difflib top-3 suggestions
  SPATIAL     node-rect overlap, out-of-canvas rects, required layers present
  ENCODING    edge marker-end == edge_rules for its type (kills inhibit-as-activate);
              marked end at spec 'to' node (kills upstream/downstream flip);
              node colors must come from palette.json
  ANNOTATION  legend data-keys == exactly the node kinds + edge types used
  SOURCE      every element group has non-empty data-source; REQUIRED COVERAGE:
              spec["required"] items (task-named must-haves) all present --
              missing items or undeclared 'required' key => fail +
              status_ceiling=partial (no silent skipping);
              QUOTE DUAL-CHANNEL ANCHORING: dict source {locator, quote} --
              (1) normalized quote must exist in the material (else
              'quote_not_found' = suspected fabrication, FAIL); (2) quote must
              fall inside the claimed locator interval (found elsewhere =
              'locator_mismatch', FAIL; invalid range = FAIL). Legacy string
              sources are WARN (upgrade advised), never silently trusted.
  EXPORT      SVG well-formed XML, editable <text> present, canvas parsed.

figure.score (0-100) = 100 - weighted, category-capped deductions - warn cap.
  Weights (sum 100): ENTITY 25 / SPATIAL 10 / ENCODING 20 / ANNOTATION 10 /
                     SOURCE 25 / EXPORT 10.
    ENTITY     unmatched text -6 each, unmatched numeric -4, missing node label -8
    SPATIAL    overlap -5, out-of-bounds -5, missing layer -5
    ENCODING   glyph mismatch -10, direction flip -10, palette violation -4
    ANNOTATION legend missing/unused -5 each
    SOURCE     element w/o source -6, quote_not_found -10, locator_mismatch -8,
               locator_invalid -8, required missing -10 each, required undeclared -25
    EXPORT     malformed SVG -10, no editable text -10
  Warnings     -1 each, capped -5 (legacy string locator, quote>30 chars,
               interval unverified, unreadable source file).
Stop rule (mirrors SKILL.md): fix FAILS first, then WARNs; stop when
score>=90 or every remaining warn is explainable. Any fail =>
verdict=needs_confirmation, status_ceiling="partial": result.json MUST use
status "partial" and list the missing/failed items.
"""
import difflib, json, os, re, sys
import xml.etree.ElementTree as ET

CHROME_INNER = re.compile(r'<g id="legend-\d+".*?</g>', re.S)
CHROME_LAYER = re.compile(r'<g id="layer-(?:title|legend|note-\d+)".*?</g>', re.S)
NUM_UNIT = re.compile(r"\d+(?:\.\d+)?\s?(?:µ|u|m|M|n|k)?(?:g|L|s|min|h|Hz|M|V|A|K|°C|%|bp|kDa|nM|mM|µM|μM)\b")
TEXT_RE = re.compile(r"<text[^>]*>(.*?)</text>", re.S)
TAG_RE = re.compile(r"<[^>]+>")
SRC_RE = re.compile(r'<g id="((?:node|edge|group)-[^"]+)"[^>]*data-source="([^"]*)"')
EDGE_G = re.compile(r'<g id="edge-(\d+)" data-type="([^"]*)"[^>]*>(.*?)</g>', re.S)
LINE_RE = re.compile(r'<line x1="([\d.]+)" y1="([\d.]+)" x2="([\d.]+)" y2="([\d.]+)"([^>]*)>')
NODE_G = re.compile(r'<g id="node-([^"]+)"[^>]*>\s*<rect x="([-\d.]+)" y="([-\d.]+)" '
                    r'width="([\d.]+)" height="([\d.]+)"[^>]*fill="(#[0-9A-Fa-f]{6})"')
RECT_RE = re.compile(r'<rect x="([-\d.]+)" y="([-\d.]+)" width="([\d.]+)" height="([\d.]+)"')
LEG_RE = re.compile(r'<g id="legend-\d+" data-key="([^"]*)"')
SVG_WH = re.compile(r'<svg[^>]*width="([\d.]+)"[^>]*height="([\d.]+)"')
WORD_RE = re.compile(r"[A-Za-z0-9]+(?:[-.][A-Za-z0-9]+)*|[一-鿿]+")
LOC_RE = re.compile(r"^\s*(?P<file>[^:']+?)\s*"
                    r"(?::\s*(?P<kind>[LC])(?P<a>\d+)(?:\s*-\s*[LC]?(?P<b>\d+))?)?\s*$")
RULES_FALLBACK = {"activates": {"marker": "arrow"}, "flows": {"marker": "arrow"},
                  "inhibits": {"marker": "tbar"}, "contains": {"marker": ""},
                  "unknown": {"marker": ""}}
PAL_FALLBACK = ["#E69F00", "#56B4E9", "#009E73", "#F0E442", "#0072B2", "#D55E00", "#CC79A7"]
LAYERS_REQUIRED = ["layer-groups", "layer-edges", "layer-nodes"]
WEIGHTS = {"entity": 25, "spatial": 10, "encoding": 20, "annotation": 10,
           "source": 25, "export": 10}          # see docstring for per-item points
QUOTE_MAX = 30
QSTAT = {"ok": "✓ 区间内逐字命中", "quote_not_found": "✗ 未找到·疑似编造",
         "locator_mismatch": "✗ 位置错配(他处命中)", "locator_invalid": "✗ 定位区间无效",
         "legacy_locator": "⚠ 旧式字符串定位·未核验", "quote_missing": "⚠ 缺 quote",
         "interval_unverified": "⚠ 定位文件未提供·区间未核验", "no_source": "— 无来源"}


def norm(t):
    return re.sub(r"\s+", " ", t).strip().lower()


def norm_variants(raw):
    """Normalization channel: whitespace collapse + lowercase, hyphen-newline
    read BOTH ways ('glyco-\\nlysis' -> 'glycolysis' and 'glyco- lysis')."""
    keep = re.sub(r"-\s*\n\s*", "-", raw)
    drop = re.sub(r"-\s*\n\s*", "", raw)
    return [v for v in {norm(keep), norm(drop)} if v]


def hit(text_norm, lows):
    return any(text_norm in l for l in lows)


def asset(name):
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets", name)
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return {}


def build_vocab(corpus):
    """Verbatim vocabulary: words (hyphen-safe, incl. CJK runs) + 2/3-word phrases."""
    words = WORD_RE.findall(corpus)
    vocab = set(words)
    for n in (2, 3):
        for i in range(len(words) - n + 1):
            vocab.add(" ".join(words[i:i + n]))
            if len(vocab) > 60000:
                return vocab
    return vocab


def suggest(token, vocab):
    """Top-3 near matches, case-insensitive, returned in source casing."""
    lower2orig = {}
    for w in vocab:
        lower2orig.setdefault(w.lower(), w)
    hits = difflib.get_close_matches(token.lower(), list(lower2orig), n=3, cutoff=0.55)
    return [lower2orig[h] for h in hits]


def interval_text(locator, src_texts):
    """Slice the raw text a locator claims. Locator grammar:
    'file.txt' (whole file) | 'file.txt:L3' | 'file.txt:L2-L4' (1-based lines)
    | 'file.txt:C10-C50' (1-based chars, inclusive). -> (text|None, status)."""
    m = LOC_RE.match(locator or "")
    if not m:
        return None, "unparseable"
    base = os.path.basename(m.group("file").strip())
    if base not in src_texts:
        return None, "file_not_provided"
    raw = src_texts[base]
    if not m.group("kind"):
        return raw, "ok"
    a = int(m.group("a"))
    b = int(m.group("b") or m.group("a"))
    if m.group("kind") == "L":
        lines = raw.splitlines()
        if a < 1 or a > b or b > len(lines):
            return None, "range_invalid"
        return "\n".join(lines[a - 1:b]), "ok"
    if a < 1 or a > b or b > len(raw):
        return None, "range_invalid"
    return raw[a - 1:b], "ok"


def quote_status(src, lows, src_texts):
    """Dual-channel check of one element's source. -> (status, severity)."""
    if not isinstance(src, dict):
        return ("legacy_locator", "warn") if str(src or "").strip() else ("no_source", "none")
    loc, q = str(src.get("locator", "") or ""), str(src.get("quote", "") or "")
    if not q.strip():
        return "quote_missing", "warn"
    qv = norm_variants(q)
    # channel 1: quote must exist anywhere in the material (anti-fabrication)
    if not any(v in l for v in qv for l in lows):
        return "quote_not_found", "fail"
    # channel 2: quote must land inside the claimed locator interval
    itext, istat = interval_text(loc, src_texts)
    if istat == "ok":
        inside = any(v in t for v in qv for t in norm_variants(itext))
        return ("ok", "ok") if inside else ("locator_mismatch", "fail")
    if istat == "file_not_provided":
        return "interval_unverified", "warn"
    return "locator_invalid", "fail"


def write_figure_map(path, figure, rows, summary):
    """Human-readable mapping table (deliverable C): element/label -> material
    quote + locator + verbatim-hit status."""
    L = ["# figure_map · 图元 → 材料溯源映射表", "",
         f"- 图稿: `{figure}` ｜ 生成: `check_figure.py`（复核证据，非预制答案）",
         "- quote 归一化: 空白折叠 / 连字符换行两种解读 / 大小写不敏感；定位: "
         "`文件:L行[-L行]` 或 `文件:C起-C止`（1 基）", "",
         "| 图元 | 标签 | 定位 locator | 材料 quote | quote 核验 | 标签逐字 |",
         "|---|---|---|---|---|---|"]
    for r in rows:
        L.append("| " + " | ".join(str(c).replace("|", "\\|") for c in r) + " |")
    L += ["", "## 汇总", ""]
    L += [f"- {k}: {v}" for k, v in summary]
    L.append("")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(L))


def main():
    if len(sys.argv) < 4:
        sys.exit("usage: check_figure.py figure.svg elements.json source_file [...]")
    svg_path, elem_path = sys.argv[1], sys.argv[2]
    svg = open(svg_path, encoding="utf-8").read()
    spec = json.load(open(elem_path, encoding="utf-8"))
    rules = asset("edge_rules.json").get("rules", RULES_FALLBACK)
    pal = [c.lower() for c in asset("palette.json").get("node", PAL_FALLBACK)]
    warnings = []
    corpus, sources, src_texts = "", [], {}
    for p in sys.argv[3:]:
        try:
            raw = open(p, encoding="utf-8", errors="replace").read()
            corpus += "\n" + raw
            src_texts[os.path.basename(p)] = raw
            sources.append(os.path.basename(p))
        except OSError as e:
            warnings.append(f"unreadable source {p}: {e}")
            print(f"WARN: cannot read source {p}: {e}", file=sys.stderr)
    lows = norm_variants(corpus)
    vocab = build_vocab(corpus)

    # ---- EXPORT: well-formed XML, editable text, canvas ---------------------
    export_err = None
    try:
        ET.fromstring(svg)
    except ET.ParseError as e:
        export_err = f"SVG not well-formed: {e}"
    text_elems = len(TEXT_RE.findall(svg))
    wh = SVG_WH.search(svg)
    canvas = (float(wh.group(1)), float(wh.group(2))) if wh else None

    # ---- ENTITY: verbatim hit + difflib suggestions -------------------------
    core = CHROME_LAYER.sub("", CHROME_INNER.sub("", svg))  # drop title/legend/notes
    texts = [t for t in (norm(TAG_RE.sub("", m)) for m in TEXT_RE.findall(core)) if t]
    nums = sorted(set(m.strip() for m in NUM_UNIT.findall(svg)))
    unmatched = [t for t in texts if not hit(t, lows)]
    num_unmatched = [n for n in nums if not hit(norm(n), lows)]
    nodes_missing = [n.get("label", n["id"]) for n in spec.get("nodes", [])
                     if not hit(norm(n.get("label", n["id"])), lows)]
    sugg = {t: suggest(t, vocab) for t in unmatched[:20]}
    sugg.update({n: suggest(norm(n), vocab) for n in nodes_missing[:20]})

    # ---- SPATIAL: overlap, out-of-bounds, layers ----------------------------
    rects = {m.group(1): tuple(float(m.group(i)) for i in range(2, 6))
             for m in NODE_G.finditer(svg)}
    overlaps = []
    ids = sorted(rects)
    for i, a in enumerate(ids):
        xa, ya, wa, ha = rects[a]
        for b in ids[i + 1:]:
            xb, yb, wb, hb = rects[b]
            if min(xa + wa, xb + wb) - max(xa, xb) > 1 and min(ya + ha, yb + hb) - max(ya, yb) > 1:
                overlaps.append(f"node-{a} overlaps node-{b}")
    oob = []
    if canvas:
        W, H = canvas
        for m in RECT_RE.finditer(svg):
            x, y, w, h = (float(m.group(i)) for i in range(1, 5))
            if x < -1 or y < -1 or x + w > W + 1 or y + h > H + 1:
                oob.append(f"rect@({x:.0f},{y:.0f},{w:.0f}x{h:.0f}) outside {W:.0f}x{H:.0f}")
    layers_missing = [l for l in LAYERS_REQUIRED if f'id="{l}"' not in svg]

    # ---- ENCODING: glyph, direction, palette --------------------------------
    centers = {k: (v[0] + v[2] / 2, v[1] + v[3] / 2) for k, v in rects.items()}
    glyph_bad, dir_bad, pal_bad, n_edges = [], [], [], 0
    spec_edges = spec.get("edges", [])
    for m in EDGE_G.finditer(svg):
        n_edges += 1
        idx, dtype, body = int(m.group(1)), m.group(2), m.group(3)
        lm = LINE_RE.search(body)
        if not lm:
            continue
        mk = re.search(r'marker-end="url\(#(\w+)\)"', lm.group(5))
        want = rules.get(dtype, {}).get("marker", "")
        got = mk.group(1) if mk else "none"
        if got != want:
            glyph_bad.append(f"edge-{idx} type={dtype} rendered={got} want={want or 'none'}")
        if idx < len(spec_edges):
            f, t = spec_edges[idx].get("from"), spec_edges[idx].get("to")
            if f in centers and t in centers:
                xe, ye = float(lm.group(3)), float(lm.group(4))
                d_to = (xe - centers[t][0]) ** 2 + (ye - centers[t][1]) ** 2
                d_from = (xe - centers[f][0]) ** 2 + (ye - centers[f][1]) ** 2
                if d_from < d_to:
                    dir_bad.append(f"edge-{idx} {f}->{t}: marked end near '{f}' (flipped)")
    for m in NODE_G.finditer(svg):
        if m.group(6).lower() not in pal:
            pal_bad.append(f"node-{m.group(1)} fill={m.group(6)} not in palette.json")

    # ---- ANNOTATION: legend exactness ---------------------------------------
    kinds = {n.get("kind", "entity") for n in spec.get("nodes", [])}
    types = {e.get("type", "flows") for e in spec_edges}
    used = kinds | types
    leg_keys = LEG_RE.findall(svg)
    legend_check = {"legend_keys": leg_keys, "used_kinds_types": sorted(used),
                    "missing_from_legend": sorted(used - set(leg_keys)) if leg_keys else [],
                    "unused_in_legend": sorted(set(leg_keys) - used)}

    # ---- SOURCE: data-source + REQUIRED coverage + QUOTE dual-channel -------
    src_attrs = SRC_RE.findall(svg)
    src_empty = [eid for eid, v in src_attrs if not v.strip()]
    coverage = sum(1 for _, v in src_attrs if v.strip()) / max(len(src_attrs), 1)
    searchable = set(texts)
    for n in spec.get("nodes", []):
        searchable.add(norm(n["id"]))
        searchable.add(norm(n.get("label", n["id"])))
    for e in spec_edges:
        searchable.add(norm(e.get("label", "")))
    for g in spec.get("groups", []):
        searchable.add(norm(g.get("id", "")))
        searchable.add(norm(g.get("label", "")))
    searchable.discard("")
    if "required" not in spec:
        req_status, missing_req = "not_declared", []
    else:
        missing_req = [r for r in spec["required"] if norm(str(r)) not in searchable]
        req_status = "missing_items" if missing_req else "ok"

    elements_seq = ([(f"node-{n.get('id', i)}", n.get("label", n.get("id", "")), n.get("source"))
                     for i, n in enumerate(spec.get("nodes", []))]
                    + [(f"edge-{i}", e.get("label", ""), e.get("source"))
                       for i, e in enumerate(spec_edges)]
                    + [(f"group-{g.get('id', i)}", g.get("label", ""), g.get("source"))
                       for i, g in enumerate(spec.get("groups", []))])
    q_fail = {"quote_not_found": [], "locator_mismatch": [], "locator_invalid": []}
    q_warn = {"legacy_locator": [], "quote_missing": [], "interval_unverified": []}
    map_rows, q_ok, q_total = [], 0, 0
    for eid, label, src in elements_seq:
        status, sev = quote_status(src, lows, src_texts)
        if isinstance(src, dict):
            loc, q = str(src.get("locator", "") or ""), str(src.get("quote", "") or "")
            if q.strip():
                q_total += 1
                if status == "ok":
                    q_ok += 1
                if len(q.strip()) > QUOTE_MAX:
                    warnings.append(f"{eid}: quote {len(q.strip())} chars > {QUOTE_MAX} (trim)")
        else:
            loc, q = str(src or ""), ""
        if sev == "fail" and status in q_fail:
            q_fail[status].append(eid)
        elif sev == "warn" and status in q_warn:
            q_warn[status].append(eid)
            warnings.append(f"{eid}: {QSTAT[status]}")
        label_hit = ("✓" if hit(norm(label), lows) else "✗") if str(label).strip() else "—"
        map_rows.append((eid, str(label)[:24], loc[:40] or "—", q[:QUOTE_MAX + 3] or "—",
                         QSTAT[status], label_hit))

    # ---- figure.score: 100 - weighted category-capped deductions ------------
    ded = []

    def d(cat, label, points):
        if points > 0:
            ded.append({"checkpoint": cat, "item": label, "points": -min(points, WEIGHTS[cat])})
        return min(points, WEIGHTS[cat])

    loss = d("entity", "unmatched_texts", 6 * len(unmatched))
    loss += d("entity", "unmatched_numeric_unit", 4 * len(num_unmatched))
    loss += d("entity", "node_labels_missing", 8 * len(nodes_missing))
    loss += d("spatial", "overlaps+out_of_bounds+layers", 5 * (len(overlaps) + len(oob)
                                                                + len(layers_missing)))
    loss += d("encoding", "glyph", 10 * len(glyph_bad))
    loss += d("encoding", "direction", 10 * len(dir_bad))
    loss += d("encoding", "palette", 4 * len(pal_bad))
    loss += d("annotation", "legend_drift", 5 * (len(legend_check["missing_from_legend"])
                                                 + len(legend_check["unused_in_legend"])))
    loss += d("source", "elements_without_source", 6 * len(src_empty))
    loss += d("source", "quote_not_found", 10 * len(q_fail["quote_not_found"]))
    loss += d("source", "locator_mismatch+invalid",
              8 * (len(q_fail["locator_mismatch"]) + len(q_fail["locator_invalid"])))
    loss += d("source", "required", 25 if req_status == "not_declared"
              else 10 * len(missing_req))
    loss += d("export", "malformed_svg", 10 if export_err else 0)
    loss += d("export", "no_editable_text", 10 if text_elems == 0 else 0)
    warn_loss = min(len(warnings), 5)
    score = max(0, 100 - loss - warn_loss)
    figure_score = {"score": score, "max": 100, "weights": WEIGHTS, "deductions": ded,
                    "warn_count": len(warnings), "warn_deduction": -warn_loss,
                    "stop_rule": "fix fails first, then warns; stop when score>=90 "
                                 "or every remaining warn is explainable"}

    fails = (unmatched or num_unmatched or nodes_missing or overlaps or oob or layers_missing
             or glyph_bad or dir_bad or pal_bad or legend_check["missing_from_legend"]
             or legend_check["unused_in_legend"] or src_empty or export_err
             or text_elems == 0 or req_status != "ok" or any(q_fail.values()))
    report = {
        "figure": os.path.basename(svg_path),
        "sources_read": sources,
        "checkpoints": {
            "entity": {"text_tokens": {"total": len(texts), "matched": len(texts) - len(unmatched),
                                       "unmatched": unmatched},
                       "numeric_unit_tokens": {"total": len(nums), "unmatched": num_unmatched},
                       "node_labels_missing_from_sources": nodes_missing,
                       "verbatim_suggestions_top3": sugg},
            "spatial": {"node_overlaps": overlaps, "out_of_bounds": oob,
                        "layers_required": LAYERS_REQUIRED, "layers_missing": layers_missing},
            "encoding": {"edge_glyph_check": {"edges_checked": n_edges, "mismatches": glyph_bad,
                                              "criteria": "assets/edge_rules.json"},
                         "edge_direction_check": {"mismatches": dir_bad},
                         "palette_color_violations": pal_bad},
            "annotation": {"legend_exactness": legend_check,
                           "units_notes_in_spec": len(spec.get("units_notes", []))},
            "source": {"elements_with_source_attr": f"{coverage:.0%}",
                       "elements_without_source": src_empty,
                       "required_coverage": {"status": req_status, "missing": missing_req,
                                             "declared": len(spec.get("required", []))
                                             if "required" in spec else None},
                       "quote_check": {"verified_in_interval": q_ok, "total_with_quote": q_total,
                                       "quote_not_found": q_fail["quote_not_found"],
                                       "locator_mismatch": q_fail["locator_mismatch"],
                                       "locator_invalid": q_fail["locator_invalid"],
                                       "warns": {k: v for k, v in q_warn.items() if v}}},
            "export": {"svg_well_formed": export_err is None, "error": export_err,
                       "editable_text_elements": text_elems,
                       "canvas": list(canvas) if canvas else None,
                       "png_evidence": "see render_preview.py output"},
        },
        "figure_score": figure_score,
        "warnings": warnings,
        "verdict": "needs_confirmation" if fails else ("pass_with_warnings" if warnings else "pass"),
        "status_ceiling": "partial" if fails else "answered",
        "status_rule": "result.json status MUST be 'partial' (listing missing/failed items) "
                       "while verdict != pass; 'answered'/'complete' forbidden",
        "note": "string/glyph/geometry-level checks only; scientific judgement still needs review",
    }
    outdir = os.path.dirname(os.path.abspath(svg_path))
    out = os.path.join(outdir, "trace_report.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    map_path = os.path.join(outdir, "figure_map.md")
    write_figure_map(map_path, report["figure"], map_rows, [
        ("实体 quote 区间命中", f"{q_ok}/{q_total}"),
        ("标签逐字命中", f"{len(texts) - len(unmatched)}/{len(texts)}"),
        ("required 覆盖", f"{req_status} ({len(spec.get('required', [])) - len(missing_req)}"
                          f"/{len(spec.get('required', []))})" if "required" in spec else "not_declared"),
        ("figure.score", f"{score}/100"),
        ("停止条件", figure_score["stop_rule"]),
    ])
    print(json.dumps({"verdict": report["verdict"], "status_ceiling": report["status_ceiling"],
                      "score": score, "warnings": len(warnings),
                      "unmatched_texts": len(unmatched), "unmatched_numbers": len(num_unmatched),
                      "nodes_missing": len(nodes_missing), "suggestions": sugg,
                      "overlaps": len(overlaps), "out_of_bounds": len(oob),
                      "layers_missing": layers_missing,
                      "glyph_mismatches": len(glyph_bad), "direction_mismatches": len(dir_bad),
                      "palette_violations": len(pal_bad),
                      "legend_missing": len(legend_check["missing_from_legend"]),
                      "legend_unused": len(legend_check["unused_in_legend"]),
                      "elements_without_source": len(src_empty),
                      "required_coverage": req_status, "required_missing": missing_req,
                      "quote_verified": f"{q_ok}/{q_total}",
                      "quote_not_found": len(q_fail["quote_not_found"]),
                      "locator_mismatch": len(q_fail["locator_mismatch"]),
                      "svg_well_formed": export_err is None,
                      "report": out, "figure_map": map_path}, ensure_ascii=False))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
