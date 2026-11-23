#!/usr/bin/env python3
"""selftest.py: fixture proof for the whole pipeline. Stdlib only.

Runs the real scripts via subprocess in a temp dir:
  POSITIVE  build -> check must be exit 0 (zero false positives), score==100,
            zero warnings; figure_map.md emitted; make_result.py assembles a
            standardized result.json; render evidence verified when a backend
            exists, honestly skipped otherwise. The fixture source deliberately
            hyphenates 'cyto-/plasm' across L4/L5 and the cytoplasm quote uses
            locator L4-L5 -- proves the normalization channel (whitespace
            collapse / hyphen-newline / case) is exercised on the PASS path.
  MUTANTS   each deliberate error must be caught (exit 1) in its checkpoint:
            1 typo entity (difflib suggestion), 2 missing required item,
            3 undeclared 'required', 4 node overlap, 5 out-of-bounds,
            6 glyph (inhibit-as-arrow), 7 direction flip, 8 legend drift,
            9 empty data-source, 10 malformed SVG,
            11 fabricated quote (not in material) -> quote_not_found,
            12 real quote at wrong locator -> locator_mismatch.
  WARN      13 legacy string source -> exit 0, warning recorded, score 99.
Exit 0 iff every expectation holds; prints one line per case plus a summary.
"""
import json, os, re, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
BUILD = os.path.join(HERE, "build_svg.py")
CHECK = os.path.join(HERE, "check_figure.py")
RENDER = os.path.join(HERE, "render_preview.py")
RESULT = os.path.join(HERE, "make_result.py")

# Multi-line on purpose: L4/L5 hyphenate 'cyto-plasm'; quote normalization must
# bridge it (locator L4-L5 + de-hyphenation). Case channel: 'Insulin Receptor IR'.
SRC = ("Insulin activates the insulin receptor IR.\n"
       "IR activates PFK-1.\n"
       "PFK-1 drives glycolysis, converting glucose to pyruvate at 37 °C.\n"
       "ATP inhibits PFK-1 in the cyto-\n"
       "plasm. Pyruvate is converted to lactate.\n")


def q(loc, quote):
    return {"locator": loc, "quote": quote}


SPEC = {
    "title": "Fixture: insulin regulation of glycolysis",
    "canvas": {"width": 900, "height": 560},
    "nodes": [
        {"id": "Insulin", "label": "Insulin", "kind": "hormone",
         "source": q("src.txt:L1", "Insulin activates")},
        {"id": "IR", "label": "IR", "kind": "receptor",
         "source": q("src.txt:L1", "Insulin Receptor IR")},
        {"id": "PFK1", "label": "PFK-1", "kind": "enzyme",
         "source": q("src.txt:L2", "IR activates PFK-1")},
        {"id": "glycolysis", "label": "glycolysis", "kind": "process",
         "source": q("src.txt:L3", "drives glycolysis")},
        {"id": "pyruvate", "label": "pyruvate", "kind": "metabolite",
         "source": q("src.txt:L3", "glucose to pyruvate")},
        {"id": "lactate", "label": "lactate", "kind": "metabolite",
         "source": q("src.txt:L5", "converted to lactate")},
        {"id": "ATP", "label": "ATP", "kind": "metabolite",
         "source": q("src.txt:L4", "ATP inhibits PFK-1")},
    ],
    "edges": [
        {"from": "Insulin", "to": "IR", "type": "activates", "label": "activates",
         "source": q("src.txt:L1", "Insulin activates")},
        {"from": "IR", "to": "PFK1", "type": "activates", "label": "activates",
         "source": q("src.txt:L2", "IR activates PFK-1")},
        {"from": "PFK1", "to": "glycolysis", "type": "activates", "label": "drives",
         "source": q("src.txt:L3", "PFK-1 drives glycolysis")},
        {"from": "glycolysis", "to": "pyruvate", "type": "flows",
         "label": "converting glucose to pyruvate",
         "source": q("src.txt:L3", "glucose to pyruvate")},
        {"from": "pyruvate", "to": "lactate", "type": "flows", "label": "is converted to",
         "source": q("src.txt:L5", "is converted to")},
        {"from": "ATP", "to": "PFK1", "type": "inhibits", "label": "inhibits",
         "source": q("src.txt:L4", "ATP inhibits PFK-1")},
    ],
    "groups": [
        {"id": "cytoplasm", "label": "cytoplasm",
         "members": ["PFK1", "glycolysis", "pyruvate", "lactate"],
         "source": q("src.txt:L4-L5", "in the cytoplasm")},
    ],
    "legend": "auto",
    "required": ["Insulin", "PFK-1", "glycolysis", "lactate", "cytoplasm"],
    "units_notes": ["incubation at 37 °C (from source)"],
    "uncertainties": [],
    "change_log": [{"item": "legend", "decision": "kept legend:auto (derived)",
                    "confirmed_by": "selftest-fixture"}],
}

failures = []


def run(script, *args):
    return subprocess.run([sys.executable, script, *args], capture_output=True, text=True)


def expect(name, cond, detail=""):
    print(f"{'PASS' if cond else 'FAIL'} {name}" + (f" | {detail}" if detail else ""))
    if not cond:
        failures.append(name)


def build_and_check(td, spec, svg_mut=None, spec_name="spec.json"):
    sp = os.path.join(td, spec_name)
    with open(sp, "w", encoding="utf-8") as f:
        json.dump(spec, f, ensure_ascii=False)
    svg = os.path.join(td, "fig.svg")
    b = run(BUILD, sp, svg)
    if b.returncode != 0:
        return None, None, b
    if svg_mut:
        with open(svg, encoding="utf-8") as f:
            s = f.read()
        with open(svg, "w", encoding="utf-8") as f:
            f.write(svg_mut(s))
    c = run(CHECK, svg, sp, os.path.join(td, "src.txt"))
    report = {}
    rp = os.path.join(td, "trace_report.json")
    if os.path.isfile(rp):
        report = json.load(open(rp, encoding="utf-8"))
    return svg, report, c


def main():
    with tempfile.TemporaryDirectory() as td:
        with open(os.path.join(td, "src.txt"), "w", encoding="utf-8") as f:
            f.write(SRC)

        # ---- POSITIVE: zero false positives across the whole pipeline ----
        svg, rep, c = build_and_check(td, SPEC)
        expect("positive_build_check_exit0", c.returncode == 0,
               (c.stdout or c.stderr).strip()[:400])
        expect("positive_verdict_pass", rep.get("verdict") == "pass")
        expect("positive_score_100", (rep.get("figure_score") or {}).get("score") == 100,
               json.dumps(rep.get("figure_score", {}).get("deductions", [])))
        expect("positive_zero_warnings", rep.get("warnings") == [],
               json.dumps(rep.get("warnings", []), ensure_ascii=False)[:300])
        fmap = os.path.join(td, "figure_map.md")
        map_txt = open(fmap, encoding="utf-8").read() if os.path.isfile(fmap) else ""
        expect("positive_figure_map", "区间内逐字命中" in map_txt and "cytoplasm" in map_txt
               and "| 图元 |" in map_txt, f"{len(map_txt)} bytes")

        r = run(RENDER, svg, os.path.join(td, "fig.png"), os.path.join(td, "fig.pdf"))
        render_ev = None
        if r.returncode == 0:
            render_ev = json.loads(r.stdout.strip())
            expect("positive_render_evidence", bool(render_ev.get("png") or render_ev.get("pdf")),
                   json.dumps(render_ev))
            with open(os.path.join(td, "render.json"), "w", encoding="utf-8") as f:
                json.dump(render_ev, f)
        else:
            print(f"SKIP positive_render (exit {r.returncode}: honest preview_unavailable)")

        # ---- POSITIVE: make_result.py standardized assembly ------------------
        case = {"case_id": "fixture-case",
                "output_contract": {"editable_figure": None, "export_files": None,
                                    "source_trace": None}}
        cp = os.path.join(td, "case.json")
        with open(cp, "w", encoding="utf-8") as f:
            json.dump(case, f)
        rp = os.path.join(td, "result.json")
        mr_args = [cp, os.path.join(td, "trace_report.json"), rp,
                   "--elements", os.path.join(td, "spec.json"), "--svg", svg]
        if render_ev:
            mr_args += ["--render", os.path.join(td, "render.json"),
                        "--png", os.path.join(td, "fig.png"),
                        "--pdf", os.path.join(td, "fig.pdf")]
        mr = run(RESULT, *mr_args)
        res = json.load(open(rp, encoding="utf-8")) if os.path.isfile(rp) else {}
        expect("result_assembly_exit0", mr.returncode == 0, (mr.stdout or mr.stderr)[:300])
        expect("result_contract_fields", res.get("case_id") == "fixture-case"
               and all(k in res for k in ("editable_figure", "export_files", "source_trace")))
        expect("result_contract_filled",
               res.get("editable_figure", {}).get("path") == "fig.svg"
               and res.get("export_files", {}).get("path") == "fig.pdf"
               and res.get("source_trace", {}).get("path") == "figure_map.md"
               and res.get("deliverables", {}).get("editable_source", {}).get("path") == "fig.svg"
               and res.get("change_log") == res.get("changes", {}).get("change_log"),
               json.dumps({k: res.get(k) for k in
                           ("editable_figure", "export_files", "source_trace", "deliverables")}))
        expect("result_role_outputs", all(k in res.get("outputs", {}) for k in
               ("editable_source", "preview", "mapping", "report")))
        expect("result_sources_summary",
               (res.get("sources", {}).get("entity_text_tokens", {}) or {}).get("total", 0) > 0
               and res.get("sources", {}).get("required_coverage", {}).get("status") == "ok")
        expect("result_changes_recorded", res.get("status") == "answered"
               and len(res.get("changes", {}).get("change_log", [])) == 1)

        # ---- MUTANT 1: typo entities -> ENTITY + difflib top-3 suggestions ----
        m = json.loads(json.dumps(SPEC))
        m["nodes"][2]["label"] = "PFK1"          # source says PFK-1
        m["nodes"][3]["label"] = "glycolisis"    # source says glycolysis
        _, rep, c = build_and_check(td, m)
        sugg = rep.get("checkpoints", {}).get("entity", {}).get("verbatim_suggestions_top3", {})
        expect("mutant_typo_exit1", c.returncode == 1)
        expect("mutant_typo_suggests", "PFK-1" in sugg.get("pfk1", [])
               and "glycolysis" in sugg.get("glycolisis", []), json.dumps(sugg))

        # ---- MUTANT 2: required item dropped -> COVERAGE fails, partial ceiling ----
        m = json.loads(json.dumps(SPEC))
        m["nodes"] = [n for n in m["nodes"] if n["id"] != "lactate"]
        m["edges"] = [e for e in m["edges"] if e["to"] != "lactate"]
        m["groups"][0]["members"] = [x for x in m["groups"][0]["members"] if x != "lactate"]
        _, rep, c = build_and_check(td, m)
        req = rep.get("checkpoints", {}).get("source", {}).get("required_coverage", {})
        expect("mutant_required_missing_exit1", c.returncode == 1)
        expect("mutant_required_missing_flagged", req.get("missing") == ["lactate"]
               and rep.get("status_ceiling") == "partial", json.dumps(req))

        # ---- MUTANT 3: 'required' key undeclared -> hard fail (no silent skip) ----
        m = json.loads(json.dumps(SPEC))
        del m["required"]
        _, rep, c = build_and_check(td, m)
        req = rep.get("checkpoints", {}).get("source", {}).get("required_coverage", {})
        expect("mutant_required_undeclared_exit1", c.returncode == 1
               and req.get("status") == "not_declared")

        # ---- MUTANT 4: node overlap -> SPATIAL ----
        def put_lactate_on_pyruvate(s):
            pyr = re.search(r'<g id="node-pyruvate"[^>]*>\s*<rect x="([\d.]+)" y="([\d.]+)"', s)
            return re.sub(r'(<g id="node-lactate"[^>]*>\s*<rect x=")[\d.]+(" y=")[\d.]+(")',
                          r"\g<1>" + pyr.group(1) + r"\g<2>" + pyr.group(2) + r"\g<3>", s)
        _, rep, c = build_and_check(td, SPEC, svg_mut=put_lactate_on_pyruvate)
        ov = rep.get("checkpoints", {}).get("spatial", {}).get("node_overlaps", [])
        expect("mutant_overlap_exit1", c.returncode == 1 and len(ov) >= 1, str(ov))

        # ---- MUTANT 5: rect outside canvas -> SPATIAL ----
        def push_off_canvas(s):
            g = re.search(r'(<g id="node-lactate"[^>]*>\s*<rect x=")[\d.]+(")', s)
            return s[:g.start()] + g.group(1) + "2000" + g.group(2) + s[g.end():]
        _, rep, c = build_and_check(td, SPEC, svg_mut=push_off_canvas)
        oob = rep.get("checkpoints", {}).get("spatial", {}).get("out_of_bounds", [])
        expect("mutant_out_of_bounds_exit1", c.returncode == 1 and len(oob) >= 1, str(oob))

        # ---- MUTANT 6: inhibit drawn as arrow -> ENCODING (glyph) ----
        def glyph_flip(s):
            g = re.search(r'(<g id="edge-5" data-type="inhibits".*?)marker-end="url\(#tbar\)"', s, re.S)
            return s[:g.start(1)] + g.group(1) + 'marker-end="url(#arrow)"' + s[g.end():]
        _, rep, c = build_and_check(td, SPEC, svg_mut=glyph_flip)
        gm = rep.get("checkpoints", {}).get("encoding", {}).get("edge_glyph_check", {})
        expect("mutant_glyph_exit1", c.returncode == 1 and len(gm.get("mismatches", [])) == 1)

        # ---- MUTANT 7: edge endpoints swapped -> ENCODING (direction) ----
        def dir_flip(s):
            g = re.search(r'(<g id="edge-5" data-type="inhibits".*?<line x1=")([\d.]+)(" y1=")([\d.]+)'
                          r'(" x2=")([\d.]+)(" y2=")([\d.]+)(")', s, re.S)
            return (s[:g.start()] + g.group(1) + g.group(6) + g.group(3) + g.group(8)
                    + g.group(5) + g.group(2) + g.group(7) + g.group(4) + g.group(9) + s[g.end():])
        _, rep, c = build_and_check(td, SPEC, svg_mut=dir_flip)
        dm = rep.get("checkpoints", {}).get("encoding", {}).get("edge_direction_check", {})
        expect("mutant_direction_exit1", c.returncode == 1 and len(dm.get("mismatches", [])) == 1)

        # ---- MUTANT 8: legend drift (extra key) -> ANNOTATION ----
        _, rep, c = build_and_check(td, SPEC, svg_mut=lambda s: s.replace(
            "</svg>", '<g id="legend-99" data-key="catalysis"><text>catalysis</text></g></svg>'))
        le = rep.get("checkpoints", {}).get("annotation", {}).get("legend_exactness", {})
        expect("mutant_legend_exit1", c.returncode == 1 and le.get("unused_in_legend") == ["catalysis"])

        # ---- MUTANT 9: element without data-source -> SOURCE ----
        _, rep, c = build_and_check(td, SPEC, svg_mut=lambda s: s.replace(
            '<g id="node-ATP" data-kind="metabolite" data-source="src.txt:L4: \'ATP inhibits PFK-1\'"',
            '<g id="node-ATP" data-kind="metabolite" data-source=""'))
        se = rep.get("checkpoints", {}).get("source", {}).get("elements_without_source", [])
        expect("mutant_no_source_exit1", c.returncode == 1 and "node-ATP" in se, str(se))

        # ---- MUTANT 10: malformed SVG -> EXPORT ----
        bad = os.path.join(td, "bad.svg")
        open(bad, "w", encoding="utf-8").write("<svg><g><text>oops")
        sp = os.path.join(td, "spec.json")
        c = run(CHECK, bad, sp, os.path.join(td, "src.txt"))
        rep = json.load(open(os.path.join(td, "trace_report.json"), encoding="utf-8"))
        expect("mutant_malformed_exit1", c.returncode == 1
               and rep["checkpoints"]["export"]["svg_well_formed"] is False)

        # ---- MUTANT 11: fabricated quote (absent from material) -> SOURCE ----
        m = json.loads(json.dumps(SPEC))
        m["nodes"][6]["source"] = q("src.txt:L4", "ATP activates PFK-1")  # fabricated
        _, rep, c = build_and_check(td, m)
        qc = rep.get("checkpoints", {}).get("source", {}).get("quote_check", {})
        sc = (rep.get("figure_score") or {}).get("score", 100)
        expect("mutant_quote_not_found_exit1", c.returncode == 1
               and qc.get("quote_not_found") == ["node-ATP"] and sc <= 90,
               f"{json.dumps(qc)} score={sc}")

        # ---- MUTANT 12: real quote, wrong locator interval -> SOURCE ----
        m = json.loads(json.dumps(SPEC))
        m["nodes"][0]["source"] = q("src.txt:L5", "Insulin activates")  # actually on L1
        _, rep, c = build_and_check(td, m)
        qc = rep.get("checkpoints", {}).get("source", {}).get("quote_check", {})
        map_txt = open(os.path.join(td, "figure_map.md"), encoding="utf-8").read()
        expect("mutant_locator_mismatch_exit1", c.returncode == 1
               and qc.get("locator_mismatch") == ["node-Insulin"]
               and "位置错配" in map_txt, json.dumps(qc))

        # ---- WARN 13: legacy string source -> warn only, exit 0, score 99 ----
        m = json.loads(json.dumps(SPEC))
        m["nodes"][6]["source"] = "src.txt: 'ATP inhibits PFK-1'"  # legacy locator string
        _, rep, c = build_and_check(td, m)
        expect("warn_legacy_source_exit0", c.returncode == 0
               and rep.get("verdict") == "pass_with_warnings"
               and any("node-ATP" in w for w in rep.get("warnings", []))
               and (rep.get("figure_score") or {}).get("score") == 99,
               f"warnings={rep.get('warnings')} score={rep.get('figure_score')}")

    print(f"\n{'SELFTEST OK' if not failures else 'SELFTEST FAILED'} "
          f"({len(failures)} failure(s){': ' + ', '.join(failures) if failures else ''})")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
