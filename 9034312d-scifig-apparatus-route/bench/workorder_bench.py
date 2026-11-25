#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""workorder_guard/scifig 工单审计 bench：正向零误杀 + 定向变异必命中。"""
import copy
import hashlib
import json
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GUARD = os.path.join(ROOT, "scripts", "workorder_guard.py")
SCIFIG = os.path.join(ROOT, "scripts", "scifig.py")
FIGTOOL = os.path.join(ROOT, "scripts", "fig_tool.py")
EX = os.path.join(ROOT, "examples")
BASE = json.load(open(os.path.join(EX, "workorder_spec.example.json"), encoding="utf-8"))
MAT = os.path.join(EX, "workorder_material.example.txt")
FAILURES = []
COUNT = 0


def expect(name, condition, detail=""):
    global COUNT
    COUNT += 1
    print(("PASS " if condition else "FAIL ") + name + (" | " + str(detail)[:240] if not condition and detail else ""))
    if not condition:
        FAILURES.append(name)


def dump(path, obj):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False)


def main():
    with tempfile.TemporaryDirectory(prefix="scifig_workorder_bench_") as td:
        serial = [0]

        def audit(tag, spec, require=True):
            serial[0] += 1
            sp = os.path.join(td, "%s_%d.json" % (tag, serial[0]))
            rp = os.path.join(td, "%s_%d.audit.json" % (tag, serial[0]))
            dump(sp, spec)
            cmd = [sys.executable, GUARD, "audit", sp, MAT]
            if require:
                cmd.append("--require")
            cmd += ["--out", rp]
            proc = subprocess.run(cmd, capture_output=True, text=True)
            report = json.load(open(rp, encoding="utf-8")) if os.path.isfile(rp) else {}
            return proc, report, sp, rp

        # Positive: the complete workorder passes both standalone and integrated checks.
        proc, rep, sp, ap = audit("positive", BASE)
        expect("positive_workorder_zero_false_positive", proc.returncode == 0 and rep.get("ok"), proc.stdout)
        expect("positive_all_anchors_verified", len(rep.get("source_anchors", [])) == 4
               and all(x.get("status") == "verified" for x in rep.get("source_anchors", [])), rep.get("source_anchors"))
        expect("positive_completion_answered", rep.get("completion_ceiling") == "answered")
        svg = os.path.join(td, "positive.svg")
        subprocess.run([sys.executable, SCIFIG, "render", sp, svg], capture_output=True, text=True)
        vr = subprocess.run([sys.executable, SCIFIG, "verify", sp, svg, MAT], capture_output=True, text=True)
        vp = os.path.join(td, "positive.verify.json")
        verify = json.load(open(vp, encoding="utf-8"))
        expect("positive_scifig_integrated_pass", vr.returncode == 0 and verify.get("verdict") == "pass"
               and verify.get("score", {}).get("value") == 100, verify.get("workorder"))
        casep = os.path.join(td, "case.json")
        dump(casep, {"case_id": "bench-workorder", "output_contract": {
            "editable_source": None, "rendered_preview": None, "source_trace": None}})
        resp = os.path.join(td, "result.json")
        rr = subprocess.run([sys.executable, SCIFIG, "result", "--case-id", "bench-workorder",
                             "--case", casep, "--spec", sp, "--svg", svg, "--verify", vp,
                             "--workorder-audit", ap, "--source", MAT, "--status", "success",
                             "--out", resp], capture_output=True, text=True)
        result = json.load(open(resp, encoding="utf-8"))
        expect("positive_result_contract_and_versions", rr.returncode == 0
               and result.get("result_schema_version") == "scifig-result/2.0"
               and all(k in result for k in ("editable_source", "rendered_preview", "source_trace"))
               and result.get("output_contract_null_fields") == [], result.get("output_contract_null_fields"))
        expect("positive_result_hashes_replay", len(result.get("source_manifest", [])) == 3
               and all(len(x.get("sha256", "")) == 64 for x in result.get("source_manifest", []))
               and result.get("reproduction", {}).get("commands"), result.get("source_manifest"))
        schema_ok = subprocess.run([sys.executable, FIGTOOL, "schema", resp], capture_output=True, text=True)
        expect("v2_fig_tool_schema_zero_false_positive", schema_ok.returncode == 0
               and json.loads(schema_ok.stdout).get("schema_mode") == "v2", schema_ok.stdout + schema_ok.stderr)
        broken = copy.deepcopy(result)
        broken["source_manifest"][0]["sha256"] = "not-a-sha"
        broken_path = os.path.join(td, "broken_result.json")
        dump(broken_path, broken)
        schema_bad = subprocess.run([sys.executable, FIGTOOL, "schema", broken_path], capture_output=True, text=True)
        expect("v2_bad_manifest_hash_hit", schema_bad.returncode == 1
               and any("sha256" in x for x in json.loads(schema_bad.stdout).get("errors", [])), schema_bad.stdout)

        def mutation(tag, change, code, ok=False, completion=None):
            spec = copy.deepcopy(BASE)
            change(spec)
            proc, report, _, _ = audit(tag, spec)
            expect(tag + "_target_hit", code in {x.get("code") for x in report.get("errors", []) + report.get("limitations", [])},
                   report)
            expect(tag + "_exit_contract", proc.returncode == (0 if ok else 1), proc.returncode)
            if completion:
                expect(tag + "_completion", report.get("completion_ceiling") == completion, report.get("completion_ceiling"))

        mutation("parameter_status_removed", lambda s: s["workorder"]["parameters"][0].pop("status"),
                 "parameter_fields")
        mutation("parameter_value_missing", lambda s: s["workorder"]["parameters"][0].update(value=""),
                 "parameter_value_missing")
        mutation("parameter_not_stated", lambda s: s["workorder"]["parameters"][0].update(
            status="not_stated", reason="材料未提供", value=None), "parameter_not_stated", ok=True, completion="partial")
        mutation("parameter_conflict_candidates", lambda s: s["workorder"]["parameters"][0].update(
            status="conflicted", reason="两处材料冲突"), "conflict_candidates")
        mutation("workorder_quote_fabricated", lambda s: s["workorder"]["parameters"][0]["source"].update(
            quote="设定流量 999 mL/min"), "quote_not_found")
        mutation("interface_medium_conflict", lambda s: s["workorder"]["interfaces"][1].update(medium="liquid"),
                 "interface_medium_conflict")
        mutation("interface_direction_conflict", lambda s: s["workorder"]["interfaces"][0].update(direction="in"),
                 "interface_direction_conflict")
        mutation("interface_reference_unknown", lambda s: s["edges"][0].update(to_interface="r1.unknown"),
                 "interface_reference_unknown")

        def duplicate_interface(s):
            s["workorder"]["interfaces"].append(copy.deepcopy(s["workorder"]["interfaces"][0]))
        mutation("interface_duplicate", duplicate_interface, "interface_duplicate")

        def reverse_order(s):
            s["workorder"]["order_assertions"].append({"before": "r1", "after": "p1",
                "source": {"locator": "句2", "quote": "先启动 P-1，再加热 R-1"}})
        mutation("process_order_conflict", reverse_order, "process_order_conflict")
        mutation("process_unresolved", lambda s: s["workorder"]["ambiguities"].append(
            {"id": "a1", "description": "两支路先后不明", "status": "unresolved"}),
            "process_unresolved", ok=True, completion="partial")
        mutation("conservative_choice_undocumented", lambda s: s["workorder"]["ambiguities"].append(
            {"id": "a1", "description": "并行关系不明", "status": "conservative_choice"}),
            "ambiguity_decision")

        absent = copy.deepcopy(BASE)
        absent.pop("workorder")
        proc, report, _, _ = audit("workorder_required", absent, require=True)
        expect("workorder_required_mutation", proc.returncode == 1
               and any(x.get("code") == "workorder_not_declared" for x in report.get("errors", [])))
        proc, report, _, _ = audit("legacy_compatibility", absent, require=False)
        expect("legacy_no_require_zero_false_positive", proc.returncode == 0
               and report.get("status") == "not_declared" and report.get("warnings"))

        # Integrated mutation must prevent a false success result.
        conflict = copy.deepcopy(BASE)
        conflict["workorder"]["interfaces"][1]["medium"] = "liquid"
        proc, report, cp, cap = audit("integrated_conflict", conflict)
        csvg = os.path.join(td, "conflict.svg")
        subprocess.run([sys.executable, SCIFIG, "render", cp, csvg], capture_output=True, text=True)
        subprocess.run([sys.executable, SCIFIG, "verify", cp, csvg, MAT], capture_output=True, text=True)
        cvp = os.path.join(td, "conflict.verify.json")
        cv = json.load(open(cvp, encoding="utf-8"))
        cres = os.path.join(td, "conflict.result.json")
        subprocess.run([sys.executable, SCIFIG, "result", "--case-id", "conflict", "--spec", cp,
                        "--svg", csvg, "--verify", cvp, "--source", MAT, "--status", "success",
                        "--out", cres], capture_output=True, text=True)
        cr = json.load(open(cres, encoding="utf-8"))
        expect("integrated_conflict_verify_hit", cv.get("verdict") == "issues"
               and cv.get("fails", 0) >= 1
               and any(x.get("code") == "interface_medium_conflict" for x in cv.get("workorder", {}).get("errors", [])), cv)
        expect("integrated_conflict_status_partial", cr.get("status") == "partial"
               and any("interface_medium_conflict" in u for u in cr.get("uncertainty", [])), cr.get("uncertainty"))

    print("TOTAL %d/%d" % (COUNT - len(FAILURES), COUNT))
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
