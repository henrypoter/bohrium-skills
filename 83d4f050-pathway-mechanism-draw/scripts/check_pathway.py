"""check_pathway.py: six-checkpoint audit of pathway spec + rendered SVG.

Usage: check_pathway.py spec.json svg.svg report.json src1 [src2...] [--png=p] [--pdf=q] [--map=m]

Side effect: a human-readable figure_map.md (element -> what is drawn on canvas
+ {locator, quote} source anchor + per-element checkpoint pass record).

figure.score (0-100) deduction scheme (stop rule lives in SKILL.md):
  hard:  layout-structure -40 | entity-label -25 | entity-evidence -30 |
         entity-coverage -10 per missing required item (cap -30) |
         export not well-formed -30
  advisory: -2 each (cap -15)

Six checkpoints (hard => exit 1; advisory => recorded, never block):
  entity    (hard) every node label verbatim in sources (misses get difflib
             top-3); evidence {locator,quote} dual-channel (quote must exist
             and fall inside the locator span: not_found / location_mismatch
             both hard); spec.required items all on canvas
             (advisory) compartment label verbatim, SVG/spec label drift,
             non-empty data-source per element
  relation  (advisory) marker-end == edge_rules (bar=inhibits, arrow=activates),
             badge letters match, marked end on `to` side, mod stem supported
  direction (advisory) downstream flow; upstream edge needs feedback:true
  legend    (advisory) legend == used node types U relations (exact set)
  layout    (hard: duplicate ids, dangling edges; advisory: node overlap,
             transmembrane span, node inside its compartment band)
  export    (hard: SVG well-formed; advisory: layers+font stack, --png/--pdf
             magic, PNG readback dims, SVG/spec element-count consistency)
"""
import difflib, json, os, re, sys
import xml.etree.ElementTree as ET

BASE = os.path.dirname(os.path.abspath(__file__))
sys.dont_write_bytecode = True
NUM = re.compile(r"-?\d+\.?\d*")
MARK = re.compile(r"url\(#m-(\w+)\)")
TOK = re.compile(r"[A-Za-z][A-Za-z0-9.\-]{1,}")
MOD = {"phosphorylates": ("phospho",), "ubiquitinates": ("ubiquitin",),
       "methylates": ("methyl",), "acetylates": ("acetyl",),
       "degrades": ("degrad", "destabil")}
PNG_M, PDF_M = b"\x89PNG", b"%PDF"


def norm(s):
    s = re.sub(r"-\s*\n\s*", "", str(s))
    return re.sub(r"\s+", " ", s).strip().lower()


def compact(s):
    return re.sub(r"[^a-z0-9]", "", norm(s))


def verbatim_in(q, text):
    n = norm(q)
    if not n:
        return False
    c = norm(text)
    return n in c or compact(q) in re.sub(r"[^a-z0-9]", "", c)


def ev_parts(ev):
    if isinstance(ev, dict):
        return str(ev.get("quote", "") or ""), str(ev.get("locator", "") or "")
    return str(ev or ""), ""


LOC = re.compile(r"^(?P<f>.*?):L(?P<a>\d+)(?:-L?(?P<b>\d+))?$")


def rules():
    try:
        return json.load(open(os.path.join(BASE, "..", "assets", "edge_rules.json"), encoding="utf-8"))
    except Exception:
        return {"relations": {"activates": {"marker": "arrow"}, "inhibits": {"marker": "bar"},
                              "binds": {"marker": "dot"}, "unknown": {"marker": None}}}


REL = rules().get("relations", {})


def file_ok(path, magic):
    try:
        if os.path.getsize(path) == 0:
            return False
        with open(path, "rb") as f:
            return f.read(len(magic)) == magic
    except OSError:
        return False


def png_dims(path):
    try:
        with open(path, "rb") as f:
            if f.read(8) != b"\x89PNG\r\n\x1a\n" or f.read(8) != b"\x00\x00\x00\rIHDR":
                return None
            w, h = int.from_bytes(f.read(4), "big"), int.from_bytes(f.read(4), "big")
            return (w, h) if w > 0 and h > 0 else None
    except OSError:
        return None


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    opts = dict(a[2:].split("=", 1) for a in sys.argv[1:]
                if a.startswith("--") and "=" in a[2:])
    if len(args) < 3:
        sys.exit(__doc__)
    spec = json.load(open(args[0], encoding="utf-8"))
    svg_path, report_path = args[1], args[2]
    raw = ""
    srcs = []
    for p in args[3:]:
        try:
            t = open(p, encoding="utf-8", errors="replace").read()
            raw += "\n" + t
            srcs.append((os.path.basename(p), t))
        except OSError:
            pass
    corpus = norm(raw)
    vocab = sorted(set(TOK.findall(raw)))
    have_src = bool(corpus.strip())

    def verbatim(s):
        return verbatim_in(s, raw)

    def locate_quote(quote, locator):
        if not norm(quote):
            return "empty"
        if not verbatim(quote):
            return "not_found"
        if not locator:
            return "ok_no_locator"
        m = LOC.match(locator.strip())
        if not m:
            return "ok_bad_locator"
        fname = os.path.basename(m.group("f").strip())
        a, b = int(m.group("a")), int(m.group("b") or m.group("a"))
        text = next((t for bn, t in srcs if bn == fname or bn.endswith(fname) or fname.endswith(bn)), None)
        if text is None:
            return "ok_src_missing"
        span = "\n".join(text.splitlines()[max(a - 1, 0):max(b, a)])
        return "ok" if verbatim_in(quote, span) else "location_mismatch"

    def suggest(s):
        return difflib.get_close_matches(str(s), vocab, n=3, cutoff=0.6)

    nodes, edges = spec.get("nodes", []), spec.get("edges", [])
    comps = {c["id"]: c for c in spec.get("compartments", [])}
    ids = [n.get("id") for n in nodes]
    by_id = {n["id"]: n for n in nodes}
    # six-checkpoint collectors
    st_err, ent_err, ev_miss, cov_missing = [], [], [], []
    ent_adv, rel_iss, dir_iss, lay_iss = [], [], [], []
    leg_iss = {"missing": [], "unused": []}
    export = {"well_formed": None, "layers_missing": [], "font_stack_ok": None,
              "png": "not_provided", "pdf": "not_provided", "png_dims": None,
              "elements": {}, "data_source_missing": []}

    # --- layout (hard): duplicate ids / dangling edges ---
    if len(ids) != len(set(ids)):
        st_err.append("duplicate node ids")
    bad = [f"{e.get('from')}->{e.get('to')}" for e in edges
           if e.get("from") not in ids or e.get("to") not in ids]
    if bad:
        st_err.append("dangling edges: " + "; ".join(bad))

    # --- entity (hard): label verbatim + evidence dual-channel + coverage ---
    if not have_src:
        ent_adv.append("no sources; entity/traceability unverified")
    else:
        for n in nodes:
            lab = n.get("label") or n.get("id")
            if lab and not verbatim(lab):
                ent_err.append({"element": n.get("id"), "label": lab,
                                "suggestions": suggest(lab)})
        for c in spec.get("compartments", []):
            lab = c.get("label", "")
            if lab and not verbatim(lab):
                ent_adv.append({"compartment": c.get("id"), "label": lab,
                                "suggestions": suggest(lab)})

    qrows = []
    for kind, el_id, sub, ev in (
            [("node", n.get("id"), n.get("type", "?"), n.get("evidence")) for n in nodes] +
            [("edge", f"{e.get('from')}->{e.get('to')}", e.get("relation", "?"),
              e.get("evidence")) for e in edges]):
        q, loc = ev_parts(ev)
        st = locate_quote(q, loc) if have_src else ("empty" if not norm(q) else "unverified")
        qrows.append({"element": el_id, "kind": kind, "sub": sub, "quote": q,
                      "locator": loc, "quote_hit": st})
        if st in ("not_found", "location_mismatch"):
            ev_miss.append({"element": el_id, "kind": kind, "quote": q[:60],
                            "locator": loc, "reason": st})
        elif st in ("ok_no_locator", "ok_bad_locator", "ok_src_missing"):
            ent_adv.append(f"{kind} {el_id}: evidence '{st.replace('ok_', '')}' — pin as 'file:Lx'")
        elif st == "empty" and kind == "edge":
            ent_adv.append(f"edge {el_id}: no evidence")
        if len(q) > 30:
            ent_adv.append(f"{kind} {el_id}: quote {len(q)} chars >30")

    req = spec.get("required") or []
    if req:
        hay = []
        for n in nodes:
            hay += [n.get("label", ""), n.get("id", "")]
        hay += [e.get("relation", "") for e in edges]
        hay += [c.get("label", "") for c in spec.get("compartments", [])]
        hay.append(spec.get("title", ""))
        H = [norm(h) for h in hay if h]
        for r in req:
            nr = norm(r)
            if not nr:
                continue
            hit = any(nr in h for h in H) if " " in nr else \
                any(nr == h or nr in h.split() or compact(r) == compact(h) for h in H)
            if not hit:
                cov_missing.append(r)
    else:
        ent_adv.append("spec.required empty; coverage unverified")

    # --- relation / direction (advisory, from spec) ---
    order = list(comps)
    rank = {cid: i for i, cid in enumerate(order)}
    for e in edges:
        r, tag = e.get("relation", "unknown"), f"{e.get('from')}->{e.get('to')}"
        if r not in REL:
            rel_iss.append(f"{tag}: relation '{r}' not in vocab")
        if r == "unknown":
            rel_iss.append(f"{tag}: unresolved relation")
        if have_src and r in MOD and not any(s in corpus for s in MOD[r]):
            rel_iss.append(f"{tag}: '{r}' unsupported by source wording")
        ra = rank.get(by_id.get(e.get("from"), {}).get("compartment"), 0)
        rb = rank.get(by_id.get(e.get("to"), {}).get("compartment"), 0)
        if rb < ra and not e.get("feedback") and r not in ("translocates", "transports", "unknown"):
            dir_iss.append(f"{tag}: upstream; set feedback:true if loop")

    # --- SVG-level checks (six classes) ---
    svg = ""
    centers, edge_els = {}, []
    rel_bad, dir_bad, lay_bad = set(), set(), set()
    try:
        svg = open(svg_path, encoding="utf-8").read()
    except OSError:
        export["well_formed"] = "unreadable"
    root = None
    if svg:
        try:
            root = ET.fromstring(svg)
            export["well_formed"] = True
        except ET.ParseError as ex:
            export["well_formed"] = False
            st_err.append(f"SVG not well-formed: {ex}")
    if root is not None:
        cmap, centers, boxes, edge_els = {}, {}, {}, []
        used_typ, used_rel, leg_typ, leg_rel, layers = set(), set(), set(), set(), set()
        rel_bad, dir_bad, lay_bad = set(), set(), set()
        for el in root.iter():
            a = el.attrib
            if a.get("id", "").startswith("layer-"):
                layers.add(a["id"])
            if "data-relation" in a:
                path = next((ch for ch in el.iter() if ch.tag.endswith("path")), None)
                badge = next((ch.text for ch in el.iter() if ch.tag.endswith("text")), None)
                edge_els.append((a.get("data-relation"), a.get("data-from"),
                                 a.get("data-to"), path, badge))
                used_rel.add(a.get("data-relation"))
            if "data-type" in a:
                try:
                    x, y, w, h = (float(v) for v in a["data-bbox"].split(","))
                except (ValueError, KeyError):
                    continue
                nid = a.get("id", "")[5:]
                centers[nid] = (a.get("data-type"), a.get("data-compartment"), x, y, w, h)
                boxes[nid] = (x, y, w, h)
                used_typ.add(a.get("data-type"))
                slab = a.get("data-label", "")
                slab_spec = str(by_id.get(nid, {}).get("label", slab))
                if slab and slab_spec and slab != slab_spec:
                    ent_adv.append({"element": nid, "svg_label": slab,
                                    "spec_label": slab_spec, "note": "SVG/spec label drift"})
                    if have_src and not verbatim(slab):
                        ent_err.append({"element": nid, "label": slab,
                                        "note": "SVG label not in sources",
                                        "suggestions": suggest(slab)})
            if "data-key" in a:
                (leg_typ if a.get("data-kind") == "typ" else leg_rel).add(a.get("data-key"))
            if "data-kind" in a and "data-key" not in a and a.get("id", "").startswith("comp-"):
                try:
                    cmap[a["id"][5:]] = (a.get("data-kind"), float(a["data-y0"]), float(a["data-y1"]))
                except (ValueError, TypeError):
                    pass
            if "data-source" in a and not a.get("data-source"):
                export["data_source_missing"].append(a.get("id", "?"))

        # layout: out-of-band + transmembrane + overlap
        for nid, (t, c, x, y, w, h) in centers.items():
            if c and c in cmap:
                _, y0, y1 = cmap[c]
                if not (y0 <= y + h / 2 <= y1):
                    lay_iss.append(f"node {nid}: center outside '{c}'"); lay_bad.add(nid)
            elif c:
                lay_iss.append(f"node {nid}: undeclared compartment '{c}'"); lay_bad.add(nid)
            if t == "receptor":
                ckind = cmap.get(c, (None,))[0]
                if ckind != "membrane":
                    lay_iss.append(f"receptor {nid}: not in membrane"); lay_bad.add(nid)
                elif c in cmap:
                    _, y0, y1 = cmap[c]
                    if not (y < y0 and y + h > y1):
                        lay_iss.append(f"receptor {nid}: not spanning membrane"); lay_bad.add(nid)
        bids = sorted(boxes)
        for i in range(len(bids)):
            for j in range(i + 1, len(bids)):
                A, B = boxes[bids[i]], boxes[bids[j]]
                ox = min(A[0] + A[2], B[0] + B[2]) - max(A[0], B[0])
                oy = min(A[1] + A[3], B[1] + B[3]) - max(A[1], B[1])
                if ox > 2 and oy > 2:
                    lay_iss.append(f"nodes {bids[i]}~{bids[j]}: overlap {int(ox)}x{int(oy)}px")
                    lay_bad.update((bids[i], bids[j]))

        # relation: marker/badge/marked-end
        for rel, f, t, path, badge in edge_els:
            want = REL.get(rel, {}).get("marker")
            if path is None:
                rel_iss.append(f"{f}->{t}: no <path>"); rel_bad.add(f"{f}->{t}")
                continue
            got = MARK.search(path.get("marker-end") or "")
            got = got.group(1) if got else "none"
            if (want or "none") != got:
                rel_iss.append(f"{f}->{t}: marker={got} want={want or 'none'}"); rel_bad.add(f"{f}->{t}")
            want_b = REL.get(rel, {}).get("badge")
            if (want_b or None) != (badge or None):
                rel_iss.append(f"{f}->{t}: badge={badge!r} want={want_b!r}"); rel_bad.add(f"{f}->{t}")
            nums = NUM.findall(path.get("d") or "")
            if len(nums) >= 4 and f in centers and t in centers and f != t:
                xe, ye = float(nums[-2]), float(nums[-1])
                cx, cy, w, h = centers[f][2:6]
                tx, ty, tw, th = centers[t][2:6]
                if (xe - cx - w / 2) ** 2 + (ye - cy - h / 2) ** 2 < \
                   (xe - tx - tw / 2) ** 2 + (ye - ty - th / 2) ** 2:
                    rel_iss.append(f"{f}->{t}: marked end near '{f}'"); rel_bad.add(f"{f}->{t}")

        # legend: exact set equality
        leg_iss["missing"] = sorted((used_typ - leg_typ) | (used_rel - leg_rel))
        leg_iss["unused"] = sorted((leg_typ - used_typ) | (leg_rel - used_rel))

        # export: layers + font stack + element-count consistency
        need = {"layer-compartments", "layer-edges", "layer-nodes", "layer-legend"}
        export["layers_missing"] = sorted(need - layers)
        ff = root.get("font-family") or ""
        export["font_stack_ok"] = "," in ff and "sans-serif" in ff
        export["elements"] = {"svg_nodes": len(centers), "spec_nodes": len(nodes),
                              "svg_edges": len(edge_els), "spec_edges": len(edges)}

    if "png" in opts:
        export["png"] = "ok" if file_ok(opts["png"], PNG_M) else "invalid"
        export["png_dims"] = png_dims(opts["png"]) if export["png"] == "ok" else None
        if export["png"] == "ok" and not export["png_dims"]:
            export["png"] = "invalid"
    if "pdf" in opts:
        export["pdf"] = "ok" if file_ok(opts["pdf"], PDF_M) else "invalid"

    # --- verdicts + figure.score ---
    hard = bool(st_err or ent_err or ev_miss or cov_missing or export["well_formed"] is False)
    adv_n = (len(ent_adv) + len(rel_iss) + len(dir_iss) + len(leg_iss["missing"])
             + len(leg_iss["unused"]) + len(lay_iss) + len(export["layers_missing"])
             + (export["font_stack_ok"] is False) + (export["png"] == "invalid")
             + (export["pdf"] == "invalid") + len(export["data_source_missing"]))
    status = "fail" if hard else ("warn" if adv_n else "pass")
    ded = (40 * bool(st_err) + 25 * bool(ent_err) + 30 * bool(ev_miss)
           + min(10 * len(cov_missing), 30) + 30 * (export["well_formed"] is False)
           + min(2 * adv_n, 15))
    score = max(0, 100 - ded)

    ent_bad = {e.get("element") for e in ent_err}
    for r in qrows:
        if r["kind"] == "node":
            r["name_hit"] = "miss" if r["element"] in ent_bad else "ok"
    q_ok = sum(1 for r in qrows if r["quote_hit"] == "ok")
    summary = {
        "entities": {"hit": len(nodes) - len({n.get("id") for n in nodes} & ent_bad),
                     "total": len(nodes)},
        "required": {"covered": len(req) - len(cov_missing), "total": len(req)},
        "quotes": {"ok": q_ok, "total": len(qrows),
                   "location_mismatch": sum(1 for r in qrows if r["quote_hit"] == "location_mismatch"),
                   "not_found": sum(1 for r in qrows if r["quote_hit"] == "not_found")},
    }

    # per-element checkpoint pass record (for figure_map.md)
    def node_pass(nid, typ):
        bits = []
        bits.append(f"entity={'✗' if nid in ent_bad else '✓'}")
        bits.append(f"layout={'⚠' if nid in lay_bad else '✓'}")
        bits.append(f"legend={'⚠' if typ in leg_iss['missing'] else '✓'}")
        return " ".join(bits)

    def edge_pass(tag, rel):
        bits = []
        bits.append(f"relation={'⚠' if tag in rel_bad else '✓'}")
        bits.append(f"direction={'⚠' if tag in dir_bad else '✓'}")
        bits.append(f"legend={'⚠' if rel in leg_iss['missing'] else '✓'}")
        return " ".join(bits)

    drawn = {("node", nid): (f"{typ} · {comp}" if comp else str(typ))
             for nid, (typ, comp, *_rest) in centers.items()}
    for rel, f, t, path, badge in edge_els:
        mk = MARK.search(path.get("marker-end") or "") if path is not None else None
        drawn[("edge", f"{f}->{t}")] = f"{rel} · {mk.group(1) if mk else '—'}"

    map_path = opts.get("map") or os.path.join(
        os.path.dirname(os.path.abspath(report_path)), "figure_map.md")
    try:
        md = [f"# figure_map — {spec.get('title', args[0])}", "",
              f"- status: **{status}** · figure.score: **{score}/100**",
              f"- 实体命中: {summary['entities']['hit']}/{summary['entities']['total']}"
              f" · required 覆盖: {summary['required']['covered']}/{summary['required']['total']}"
              f" · quote 锚定: {q_ok}/{len(qrows)}", "",
              "| 元素 | 类型/关系 | 图上画了什么 | 材料 quote | locator | quote 命中 | 名称命中 | 检查点通过 |",
              "|---|---|---|---|---|---|---|---|"]
        for r in qrows:
            qq = (r["quote"][:48] + "…" if len(r["quote"]) > 48 else r["quote"]).replace("|", "\\|")
            key = (r["kind"], r["element"])
            sub = r["sub"]
            if r["kind"] == "node":
                p = node_pass(r["element"], sub)
            else:
                p = edge_pass(r["element"], sub)
            md.append(f"| {r['kind']} `{r['element']}` | {sub} | {drawn.get(key, '—')} | “{qq}” "
                      f"| {r['locator'] or '—'} | {r['quote_hit']} | {r.get('name_hit', '—')} | {p} |")
        with open(map_path, "w", encoding="utf-8") as f:
            f.write("\n".join(md) + "\n")
    except OSError:
        map_path = None

    report = {
        "status": status,
        "score": score,
        "summary": summary,
        "figure_map": map_path,
        "rule": "hard fail => fix or deliver status:partial listing missing; advisory => human/Judge review",
        "checks": [
            {"name": "entity", "level": "hard",
             "result": "fail" if (ent_err or ev_miss or cov_missing) else ("warn" if ent_adv else "pass"),
             "unmatched_labels": ent_err, "evidence_issues": ev_miss,
             "missing_required": cov_missing, "required": req, "advisory": ent_adv},
            {"name": "relation", "level": "advisory",
             "result": "warn" if rel_iss else "pass",
             "criteria": "assets/edge_rules.json", "issues": rel_iss},
            {"name": "direction", "level": "advisory",
             "result": "warn" if dir_iss else "pass", "issues": dir_iss},
            {"name": "legend", "level": "advisory",
             "result": "warn" if (leg_iss["missing"] or leg_iss["unused"]) else "pass",
             "legend": leg_iss},
            {"name": "layout", "level": "hard",
             "result": "fail" if st_err else ("warn" if lay_iss else "pass"),
             "detail": st_err, "issues": lay_iss},
            {"name": "export", "level": "mixed",
             "result": "fail" if export["well_formed"] is False else "pass",
             "detail": export},
        ],
    }
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(json.dumps({"status": status, "score": score, "layout_structure": len(st_err),
                      "entity_labels": len(ent_err), "entity_evidence": len(ev_miss),
                      "entity_coverage_missing": cov_missing, "quotes_ok": f"{q_ok}/{len(qrows)}",
                      "relation": len(rel_iss), "direction": len(dir_iss),
                      "legend_missing": len(leg_iss["missing"]), "legend_unused": len(leg_iss["unused"]),
                      "layout": len(lay_iss), "png": export["png"],
                      "png_dims": export["png_dims"], "elements": export["elements"]},
                     ensure_ascii=False))
    sys.exit(1 if status == "fail" else 0)


if __name__ == "__main__":
    main()
