"""selftest.py: fixture proof that the six-checkpoint audit intercepts real errors.

Positive fixtures (shipped example + MAPK template + normalized quote) must
pass with ZERO issues (no false kills) and figure.score 100. Each mutant
fixture must be detected by the named checkpoint — including the dual-channel
evidence anchors (fabricated quote => not_found; real quote pinned to the
wrong line span => location_mismatch) and the deterministic PNG readback
(IHDR dimensions). Stdlib only; runs everything in a temp dir; exit 0 iff all
pass.

Usage: python3 scripts/selftest.py
"""
import json, os, re, struct, subprocess, sys, tempfile, zlib

BASE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(BASE)
sys.dont_write_bytecode = True
RESULTS = []


def sh(args):
    r = subprocess.run([sys.executable] + args, capture_output=True, text=True, timeout=120)
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def record(name, ok, detail=""):
    RESULTS.append({"fixture": name, "result": "PASS" if ok else "FAIL", "detail": detail})
    return ok


def pipeline(tmp, spec_path, src_path, tag):
    svg = os.path.join(tmp, f"{tag}.svg")
    rep = os.path.join(tmp, f"{tag}.json")
    png = os.path.join(tmp, f"{tag}.png")
    pdf = os.path.join(tmp, f"{tag}.pdf")
    rc, out = sh([os.path.join(BASE, "build_pathway.py"), spec_path, svg])
    if rc != 0:
        return None, None, f"build failed: {out.strip()[:200]}"
    extra = []
    rrc, _ = sh([os.path.join(BASE, "render_preview.py"), svg, png, pdf])
    if rrc == 0 and os.path.exists(png):
        extra.append(f"--png={png}")
    rc, out = sh([os.path.join(BASE, "check_pathway.py"), spec_path, svg, rep, src_path] + extra)
    try:
        report = json.load(open(rep, encoding="utf-8"))
    except Exception as ex:
        return None, None, f"report unreadable: {ex}"
    return rc, report, ""


def main():
    tmp = tempfile.mkdtemp(prefix="pw_selftest_")
    ex_spec = os.path.join(ROOT, "examples", "pathway.example.json")
    ex_src = os.path.join(ROOT, "examples", "demo_source.txt")
    tp_spec = os.path.join(ROOT, "templates", "mapk.template.json")
    tp_src = os.path.join(ROOT, "templates", "mapk_demo_source.txt")

    # ---- positive 1: shipped example, zero false kills, score 100, map written ----
    rc, rep, err = pipeline(tmp, ex_spec, ex_src, "pos_example")
    fmap = os.path.join(tmp, "figure_map.md")
    ok = (rep is not None and rc == 0 and rep["status"] == "pass"
          and rep.get("score") == 100 and os.path.exists(fmap)
          and "quote" in open(fmap, encoding="utf-8").read())
    record("positive/example (zero false-kill, score=100, figure_map)", ok,
           err or f"rc={rc} status={rep and rep['status']} score={rep and rep.get('score')}")

    # ---- positive 2: filled MAPK template, zero false kills ----
    rc, rep, err = pipeline(tmp, tp_spec, tp_src, "pos_template")
    ok = rep is not None and rc == 0 and rep["status"] == "pass" and rep.get("score") == 100
    record("positive/mapk_template (zero false-kill)", ok,
           err or f"rc={rc} status={rep and rep['status']} score={rep and rep.get('score')}")

    # ---- positive 3: messy case/whitespace quote still anchors (normalization) ----
    spec0 = json.load(open(tp_spec, encoding="utf-8"))
    s = json.loads(json.dumps(spec0))
    for n in s["nodes"]:
        if n["id"] == "egf":
            n["evidence"] = {"locator": "mapk_demo_source.txt:L2",
                             "quote": "egf  BINDS   the receptor egfr"}
    p3 = os.path.join(tmp, "pos_norm.json")
    json.dump(s, open(p3, "w", encoding="utf-8"))
    rc, rep, err = pipeline(tmp, p3, tp_src, "pos_norm")
    ok = rep is not None and rc == 0 and rep["status"] == "pass"
    record("positive/normalized-quote (case/whitespace robust)", ok,
           err or f"rc={rc} status={rep and rep['status']} score={rep and rep.get('score')}")

    spec = json.load(open(tp_spec, encoding="utf-8"))
    svg0 = open(os.path.join(tmp, "pos_template.svg"), encoding="utf-8").read()

    def mut_spec(name, mutate):
        s = json.loads(json.dumps(spec))
        mutate(s)
        p = os.path.join(tmp, f"{name}.json")
        json.dump(s, open(p, "w", encoding="utf-8"))
        return p

    def mut_svg(name, old, new):
        assert old in svg0, f"mutant {name}: anchor missing in SVG"
        p = os.path.join(tmp, f"{name}.svg")
        open(p, "w", encoding="utf-8").write(svg0.replace(old, new, 1))
        return p

    def check_only(name, spec_p, svg_p, extra=()):
        rep_p = os.path.join(tmp, f"{name}.report.json")
        rc, out = sh([os.path.join(BASE, "check_pathway.py"), spec_p, svg_p, rep_p, tp_src] + list(extra))
        rep = json.load(open(rep_p, encoding="utf-8"))
        return rc, rep

    # ---- mutant 1: misspelled entity (EGRF) -> entity hard fail + top-3 hints ----
    p = mut_spec("m_entity", lambda s: [n.update(label="EGRF") for n in s["nodes"] if n["id"] == "egfr"])
    rc, rep, err = pipeline(tmp, p, tp_src, "m_entity")
    ent = next(c for c in rep["checks"] if c["name"] == "entity") if rep else {}
    hints = ent.get("unmatched_labels", [{}])[0].get("suggestions", []) if ent else []
    record("mutant/misspelled-entity EGRF", rep is not None and rc == 1
           and ent.get("result") == "fail" and "EGFR" in hints,
           err or f"rc={rc} entity={ent.get('result')} hints={hints}")

    # ---- mutant 2: required item dropped from canvas -> entity coverage hard fail ----
    p = mut_spec("m_coverage", lambda s: s.update(nodes=[n for n in s["nodes"] if n["id"] != "ras"],
                                                  edges=[e for e in s["edges"]
                                                         if "ras" not in (e["from"], e["to"])]))
    rc, rep, err = pipeline(tmp, p, tp_src, "m_coverage")
    ent = next(c for c in rep["checks"] if c["name"] == "entity") if rep else {}
    record("mutant/missing-required RAS", rep is not None and rc == 1
           and ent.get("result") == "fail" and "RAS" in ent.get("missing_required", []),
           err or f"rc={rc} missing={ent.get('missing_required')}")

    # ---- mutant 3: inhibits T-bar hand-changed to arrow -> relation catches ----
    p = mut_svg("m_glyph", 'data-relation="inhibits"', 'data-relation="inhibits"')
    svg_m = open(p, encoding="utf-8").read().replace("url(#m-bar)", "url(#m-arrow)", 1)
    open(p, "w", encoding="utf-8").write(svg_m)
    rc, rep = check_only("m_glyph", tp_spec, p)
    rel = next(c for c in rep["checks"] if c["name"] == "relation")
    record("mutant/inhibits-drawn-as-arrow", any("marker=arrow" in i for i in rel["issues"]),
           f"rc={rc} relation={rel['issues'][:1]}")

    # ---- mutant 4: badge P -> Ub -> relation catches ----
    p = mut_svg("m_badge", ">P</text>", ">Ub</text>")
    rc, rep = check_only("m_badge", tp_spec, p)
    rel = next(c for c in rep["checks"] if c["name"] == "relation")
    record("mutant/badge-P-to-Ub", any("badge=" in i for i in rel["issues"]),
           f"rc={rc} relation={rel['issues'][:1]}")

    # ---- mutant 5: receptor shrunk off membrane -> layout catches ----
    m = re.search(r'(<g id="node-egfr"[^>]*data-bbox=")([^"]+)', svg0)
    x, y, w, h = [float(v) for v in m.group(2).split(",")]
    p = mut_svg("m_topology", m.group(2), f"{x},{y},{w},20")
    rc, rep = check_only("m_topology", tp_spec, p)
    lay = next(c for c in rep["checks"] if c["name"] == "layout")
    record("mutant/receptor-not-spanning", any("not spanning" in i for i in lay["issues"]),
           f"rc={rc} layout={lay['issues'][:1]}")

    # ---- mutant 6: two nodes moved onto each other -> layout overlap ----
    m2 = re.search(r'(<g id="node-ras"[^>]*data-bbox=")([^"]+)', svg0)
    p = mut_svg("m_overlap", m.group(2), m.group(2))
    svg_m = open(p, encoding="utf-8").read()
    m3 = re.search(r'(<g id="node-raf"[^>]*data-bbox=")([^"]+)', svg_m)
    svg_m = svg_m.replace(m3.group(2), m2.group(2), 1)
    open(p, "w", encoding="utf-8").write(svg_m)
    rc, rep = check_only("m_overlap", tp_spec, p)
    lay = next(c for c in rep["checks"] if c["name"] == "layout")
    record("mutant/node-overlap", any("overlap" in i for i in lay["issues"]),
           f"rc={rc} layout={lay['issues'][:1]}")

    # ---- mutant 7: dangling edge -> layout structure hard fail ----
    p = mut_spec("m_dangling", lambda s: s["edges"].append(
        {"from": "erk", "to": "ghost", "relation": "activates", "evidence": "MEK phosphorylates ERK"}))
    rc, rep, err = pipeline(tmp, p, tp_src, "m_dangling")
    lay = next(c for c in rep["checks"] if c["name"] == "layout") if rep else {}
    record("mutant/dangling-edge", rep is not None and rc == 1 and lay.get("result") == "fail",
           err or f"rc={rc} layout={lay.get('detail')}")

    # ---- mutant 8: fabricated evidence quote -> not_found, entity hard fail ----
    p = mut_spec("m_fabricated", lambda s: s["edges"][0].update(
        evidence={"locator": "mapk_demo_source.txt:L2",
                  "quote": "EGF binds the receptor ERBB4"}))
    rc, rep, err = pipeline(tmp, p, tp_src, "m_fabricated")
    ent = next(c for c in rep["checks"] if c["name"] == "entity") if rep else {}
    reasons = [m.get("reason") for m in ent.get("evidence_issues", [])] if ent else []
    record("mutant/fabricated-evidence not_found", rep is not None and rc == 1
           and ent.get("result") == "fail" and "not_found" in reasons,
           err or f"rc={rc} entity={ent.get('result')} reasons={reasons}")

    # ---- mutant 11: real quote pinned to WRONG locator -> location_mismatch fail ----
    p = mut_spec("m_mislocated", lambda s: [n.update(
        evidence={"locator": "mapk_demo_source.txt:L6",
                  "quote": "EGF binds the receptor EGFR"})
        for n in s["nodes"] if n["id"] == "egf"])
    rc, rep, err = pipeline(tmp, p, tp_src, "m_mislocated")
    ent = next(c for c in rep["checks"] if c["name"] == "entity") if rep else {}
    reasons = [m.get("reason") for m in ent.get("evidence_issues", [])] if ent else []
    fmap = open(os.path.join(tmp, "figure_map.md"), encoding="utf-8").read() if rep else ""
    record("mutant/quote-location-mismatch", rep is not None and rc == 1
           and ent.get("result") == "fail" and "location_mismatch" in reasons
           and "location_mismatch" in fmap,
           err or f"rc={rc} reasons={reasons}")

    # ---- mutant 9: legend extra entry -> legend catches ----
    p = mut_svg("m_legend", '<g data-kind="rel" data-key="binds">',
                '<g data-kind="rel" data-key="degrades"><line x1="1" y1="1" x2="2" y2="1"/></g>'
                '<g data-kind="rel" data-key="binds">')
    rc, rep = check_only("m_legend", tp_spec, p)
    leg = next(c for c in rep["checks"] if c["name"] == "legend")
    record("mutant/legend-extra-entry", "degrades" in leg["legend"]["unused"],
           f"rc={rc} legend={leg['legend']}")

    # ---- mutant 10: truncated SVG -> export hard fail (well-formed) ----
    p = os.path.join(tmp, "m_broken.svg")
    open(p, "w", encoding="utf-8").write(svg0[:len(svg0) // 2])
    rc, rep = check_only("m_broken", tp_spec, p)
    ex = next(c for c in rep["checks"] if c["name"] == "export")
    record("mutant/truncated-svg", rc == 1 and ex["result"] == "fail",
           f"rc={rc} export={ex['result']}")

    # ---- readback fixture: synthetic valid PNG => export reads IHDR dims ----
    def make_png(path, w, h):
        sig = b"\x89PNG\r\n\x1a\n"

        def chunk(typ, data):
            c = typ + data
            return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)
        open(path, "wb").write(sig + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
                               + chunk(b"IEND", b""))
    rp = os.path.join(tmp, "m_readback.png")
    make_png(rp, 2, 3)
    rc, rep = check_only("m_readback", tp_spec, os.path.join(tmp, "pos_template.svg"),
                         extra=[f"--png={rp}"])
    ex = next(c for c in rep["checks"] if c["name"] == "export")
    record("readback/synthetic-png IHDR dims", rc == 0 and ex["detail"].get("png") == "ok"
           and ex["detail"].get("png_dims") == [2, 3],
           f"rc={rc} png={ex['detail'].get('png')} dims={ex['detail'].get('png_dims')}")

    nfail = sum(1 for r in RESULTS if r["result"] == "FAIL")
    print(json.dumps({"fixtures": RESULTS,
                      "summary": f"{len(RESULTS) - nfail}/{len(RESULTS)} passed"},
                     ensure_ascii=False, indent=2))
    sys.exit(1 if nfail else 0)


if __name__ == "__main__":
    main()
