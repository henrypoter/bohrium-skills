#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""relation_ir + data_legend + coverage_guard + make_result 正向/变异 bench。"""
import copy
import json
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = {name: os.path.join(ROOT, "scripts", name + ".py") for name in
          ("relation_ir", "data_legend", "coverage_guard", "build_svg", "check_figure", "make_result", "fig_tool")}
COUNT = 0
FAILURES = []


def expect(name, condition, detail=""):
    global COUNT
    COUNT += 1
    print(("PASS " if condition else "FAIL ") + name + (" | " + str(detail)[:260] if not condition and detail else ""))
    if not condition:
        FAILURES.append(name)


def run(name, *args):
    return subprocess.run([sys.executable, SCRIPT[name], *map(str, args)], capture_output=True, text=True)


def load(path):
    return json.load(open(path, encoding="utf-8"))


def dump(path, obj):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)


def out_json(proc):
    try:
        return json.loads(proc.stdout)
    except Exception:
        return {"raw": proc.stdout, "stderr": proc.stderr}


def main():
    with tempfile.TemporaryDirectory(prefix="schematic_innovation_bench_") as td:
        src = os.path.join(td, "src.txt")
        with open(src, "w", encoding="utf-8") as f:
            f.write("Insulin activates IR at 37 °C.\nATP inhibits PFK-1.\nPyruvate is converted to lactate.\n")
        csv_path = os.path.join(td, "data.csv")
        with open(csv_path, "w", encoding="utf-8") as f:
            f.write("entity,category\nInsulin,hormone\nIR,receptor\nATP,metabolite\nPFK-1,enzyme\nPyruvate,metabolite\nlactate,metabolite\n")
        draft = os.path.join(td, "draft.json")
        extract = run("relation_ir", "extract", src, draft, "--report", os.path.join(td, "extract_report.json"))
        expect("extract_positive_exit0", extract.returncode == 0 and os.path.isfile(draft), extract.stdout + extract.stderr)
        spec = load(draft)
        expect("extract_entities_relations", len(spec["nodes"]) == 6 and len(spec["edges"]) == 3
               and spec["status"] == "draft_requires_review" and spec["extraction"]["review_required"], spec)
        expect("extract_semantics_direction", [(e["from"], e["to"], e["type"]) for e in spec["edges"]]
               == [("Insulin", "IR", "activates"), ("ATP", "PFK-1", "inhibits"),
                   ("Pyruvate", "lactate", "flows")], spec["edges"])
        audit = run("relation_ir", "audit", src, draft)
        expect("relation_audit_positive_zero_false_positive", audit.returncode == 0 and out_json(audit).get("ok"), audit.stdout)

        synced_path = os.path.join(td, "synced.json")
        sync = run("data_legend", "sync", draft, csv_path, synced_path,
                   "--report", os.path.join(td, "binding.json"))
        expect("data_sync_positive_exit0", sync.returncode == 0 and os.path.isfile(synced_path), sync.stdout + sync.stderr)
        data_audit = run("data_legend", "audit", synced_path, csv_path)
        expect("data_audit_positive_zero_false_positive", data_audit.returncode == 0 and out_json(data_audit).get("ok"), data_audit.stdout)
        synced = load(synced_path)
        expect("data_binding_provenance", len(synced["data_mapping"]) == 6
               and len(synced["data_binding"]["sha256"]) == 64 and synced["legend"] == "auto")
        synced["required"] = ["Insulin"]
        synced["units_notes"] = ["37 °C"]
        task_path = os.path.join(td, "task.md")
        with open(task_path, "w", encoding="utf-8") as f:
            f.write("Draw Insulin with activates relation, a legend, 37 °C, and panel-a.")
        synced["required_elements"] = [
            {"id": "entity-insulin", "category": "entity", "svg_id": "node-Insulin", "task_quote": "Insulin"},
            {"id": "relation-0", "category": "relationship", "svg_id": "edge-0", "task_quote": "activates"},
            {"id": "legend", "category": "legend", "svg_id": "layer-legend", "task_quote": "legend"},
            {"id": "temperature", "category": "unit", "text": "37 °C", "task_quote": "37 °C"},
            {"id": "panel-a", "category": "panel", "svg_id": "panel-a", "task_quote": "panel-a"},
        ]
        dump(synced_path, synced)
        svg = os.path.join(td, "figure.svg")
        build = run("build_svg", synced_path, svg)
        expect("build_synced_positive", build.returncode == 0, build.stdout + build.stderr)
        with open(svg, encoding="utf-8") as f:
            text = f.read().replace("</svg>", '<g id="panel-a"></g></svg>')
        with open(svg, "w", encoding="utf-8") as f:
            f.write(text)
        check = run("check_figure", svg, synced_path, src, csv_path)
        trace = load(os.path.join(td, "trace_report.json"))
        expect("legacy_six_checks_zero_false_positive", check.returncode == 0
               and trace.get("figure_score", {}).get("score") == 100, check.stdout + check.stderr)
        coverage_path = os.path.join(td, "coverage.json")
        coverage_run = run("coverage_guard", "audit", synced_path, svg, "--task", task_path,
                           "--out", coverage_path)
        coverage = load(coverage_path)
        expect("coverage_positive_zero_false_positive", coverage_run.returncode == 0 and coverage["ok"]
               and coverage["coverage"]["percent"] == 100.0, coverage)

        # Data change -> sync -> audit -> redraw: legend keys must follow the table.
        changed_csv = os.path.join(td, "changed.csv")
        with open(csv_path, encoding="utf-8") as f:
            changed = f.read().replace("IR,receptor", "IR,channel")
        with open(changed_csv, "w", encoding="utf-8") as f:
            f.write(changed)
        changed_spec = os.path.join(td, "changed.json")
        changed_run = run("data_legend", "sync", draft, changed_csv, changed_spec)
        changed_audit = run("data_legend", "audit", changed_spec, changed_csv)
        changed_svg = os.path.join(td, "changed.svg")
        run("build_svg", changed_spec, changed_svg)
        changed_text = open(changed_svg, encoding="utf-8").read()
        expect("data_change_redraw_legend", changed_run.returncode == 0 and changed_audit.returncode == 0
               and 'data-key="channel"' in changed_text and 'data-key="receptor"' not in changed_text,
               changed_run.stdout + changed_audit.stdout)

        # make_result: contract, coverage, versions and replay identities.
        case_path = os.path.join(td, "case.json")
        dump(case_path, {"case_id": "innovation-bench", "output_contract": {
            "editable_figure": None, "source_trace": None, "coverage_report": None}})
        result_path = os.path.join(td, "result.json")
        made = run("make_result", case_path, os.path.join(td, "trace_report.json"), result_path,
                   "--elements", synced_path, "--svg", svg, "--coverage", coverage_path,
                   "--source", src, "--source", csv_path)
        result = load(result_path)
        expect("result_contract_coverage", made.returncode == 0 and result["case_id"] == "innovation-bench"
               and result["editable_figure"]["path"] == "figure.svg"
               and result["source_trace"]["path"] == "figure_map.md"
               and result["coverage_report"]["path"] == "coverage.json"
               and result["status"] == "answered", made.stdout + made.stderr)
        expect("result_versions_hashes_replay", result["result_schema_version"] == "sci-schematic-result/2.0"
               and len(result["source_manifest"]) == 4 and result["data_mapping"]
               and all(len(row["sha256"]) == 64 for row in result["source_manifest"])
               and result["reproduction"]["commands"], result.get("source_manifest"))
        schema_ok = run("fig_tool", "schema", result_path)
        expect("v2_fig_tool_schema_zero_false_positive", schema_ok.returncode == 0
               and out_json(schema_ok).get("schema_mode") == "v2", schema_ok.stdout + schema_ok.stderr)
        broken = copy.deepcopy(result)
        broken["artifact_manifest"][0]["sha256"] = "bogus"
        broken_path = os.path.join(td, "broken_result.json")
        dump(broken_path, broken)
        schema_bad = run("fig_tool", "schema", broken_path)
        expect("v2_bad_manifest_hash_hit", schema_bad.returncode == 1
               and any("sha256" in x for x in out_json(schema_bad).get("errors", [])), schema_bad.stdout)

        def relation_mutation(tag, change, code):
            mutant = copy.deepcopy(synced)
            change(mutant)
            path = os.path.join(td, tag + ".json")
            dump(path, mutant)
            proc = run("relation_ir", "audit", src, path)
            payload = out_json(proc)
            expect(tag + "_hit", proc.returncode == 1
                   and any(e.get("code") == code for e in payload.get("errors", [])), payload)

        relation_mutation("relation_type_flip", lambda s: s["edges"][1].update(type="activates"),
                          "relation_missing_or_direction_type_drift")
        relation_mutation("relation_direction_flip", lambda s: s["edges"][0].update(**{"from": "IR", "to": "Insulin"}),
                          "relation_missing_or_direction_type_drift")
        relation_mutation("fabricated_entity", lambda s: s["nodes"].append(
            {"id": "Ghost", "label": "Ghost", "kind": "entity", "source": {"locator": "src.txt:L1", "quote": "Insulin"}}),
            "entity_not_extracted_from_text")
        tampered_src = os.path.join(td, "tampered.txt")
        with open(tampered_src, "w", encoding="utf-8") as f:
            f.write(open(src, encoding="utf-8").read() + "Background sentence only.\n")
        proc = run("relation_ir", "audit", tampered_src, synced_path)
        expect("source_digest_drift_hit", proc.returncode == 1
               and any(e.get("code") == "source_digest_mismatch" for e in out_json(proc).get("errors", [])), proc.stdout)
        no_relation_src = os.path.join(td, "none.txt")
        with open(no_relation_src, "w", encoding="utf-8") as f:
            f.write("No explicit interaction is stated here.\n")
        no_relation_out = os.path.join(td, "none.json")
        proc = run("relation_ir", "extract", no_relation_src, no_relation_out)
        expect("no_pattern_no_fabricated_output", proc.returncode == 3 and not os.path.exists(no_relation_out), proc.stdout)

        def data_mutation(tag, change, code, table=csv_path):
            mutant = copy.deepcopy(synced)
            change(mutant)
            path = os.path.join(td, tag + ".json")
            dump(path, mutant)
            proc = run("data_legend", "audit", path, table)
            payload = out_json(proc)
            expect(tag + "_hit", proc.returncode == 1
                   and any(e.get("code") == code for e in payload.get("errors", [])), payload)

        data_mutation("node_category_drift", lambda s: s["nodes"][0].update(kind="wrong"), "node_category_drift")
        data_mutation("table_digest_drift", lambda s: None, "data_table_digest_mismatch", table=changed_csv)
        data_mutation("legend_not_data_driven", lambda s: s.update(legend=[]), "legend_not_auto_derived")
        data_mutation("data_binding_removed", lambda s: s.pop("data_binding"), "data_binding_missing")
        data_mutation("data_mapping_removed", lambda s: s["data_mapping"].pop(), "data_mapping_row_count_mismatch")

        def bad_csv(tag, content, code):
            table = os.path.join(td, tag + ".csv")
            with open(table, "w", encoding="utf-8") as f:
                f.write(content)
            target = os.path.join(td, tag + ".json")
            proc = run("data_legend", "sync", draft, table, target)
            payload = out_json(proc)
            expect(tag + "_hit_no_output", proc.returncode == 1 and not os.path.exists(target)
                   and any(e.get("code") == code for e in payload.get("errors", [])), payload)

        bad_csv("conflicting_csv", "entity,category\nA,x\nA,y\n", "csv_conflicting_category")
        bad_csv("empty_csv_cell", "entity,category\nA,\n", "csv_empty_required_cell")
        bad_csv("missing_csv_column", "entity,class\nA,x\n", "csv_column_missing")

        def coverage_mutation(tag, spec_change=None, svg_change=None, task=None, code=None):
            mutant_spec = copy.deepcopy(synced)
            if spec_change:
                spec_change(mutant_spec)
            sp = os.path.join(td, tag + ".spec.json")
            dump(sp, mutant_spec)
            content = open(svg, encoding="utf-8").read()
            if svg_change:
                content = svg_change(content)
            vp = os.path.join(td, tag + ".svg")
            with open(vp, "w", encoding="utf-8") as f:
                f.write(content)
            args = ["audit", sp, vp, "--task", task or task_path]
            proc = run("coverage_guard", *args)
            payload = out_json(proc)
            expect(tag + "_hit", proc.returncode == 1
                   and any(e.get("code") == code for e in payload.get("errors", [])), payload)

        coverage_mutation("coverage_phantom_required", lambda s: s["required"].append("GHOST"), code="required_not_in_actual_svg")
        coverage_mutation("coverage_missing_svg_id", lambda s: s["required_elements"][0].update(svg_id="node-Ghost"), code="svg_id_missing")
        coverage_mutation("coverage_unit_removed", svg_change=lambda t: t.replace("37 °C", "temperature"), code="svg_text_missing")
        coverage_mutation("coverage_wrong_category", lambda s: s["required_elements"][1].update(svg_id="node-Insulin"),
                          code="category_svg_id_mismatch")
        coverage_mutation("coverage_task_quote_mismatch", lambda s: s["required_elements"][0].update(task_quote="GHOST"),
                          code="task_quote_missing_or_mismatch")
        coverage_mutation("coverage_legend_removed", svg_change=lambda t: t.replace('id="layer-legend"', 'id="old-legend"'),
                          code="automatic_legend_missing")

        bad_coverage = copy.deepcopy(coverage)
        bad_coverage["ok"] = False
        bad_coverage["errors"] = [{"code": "forced_bench_mutation"}]
        bad_coverage_path = os.path.join(td, "bad_coverage.json")
        dump(bad_coverage_path, bad_coverage)
        bad_result_path = os.path.join(td, "bad_result.json")
        run("make_result", case_path, os.path.join(td, "trace_report.json"), bad_result_path,
            "--elements", synced_path, "--svg", svg, "--coverage", bad_coverage_path)
        bad_result = load(bad_result_path)
        expect("coverage_failure_status_partial", bad_result["status"] == "partial"
               and any(x.get("code") == "coverage_incomplete" for x in bad_result["uncertainty"]), bad_result["uncertainty"])

    print("TOTAL %d/%d" % (COUNT - len(FAILURES), COUNT))
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
