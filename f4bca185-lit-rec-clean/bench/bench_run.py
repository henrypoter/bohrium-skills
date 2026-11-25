#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Positive zero-false-alarm + required mutation-detection bench for all commands."""
import copy
import csv
import hashlib
import json
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOL = os.path.join(ROOT, "scripts", "literature_clean.py")
TMP = tempfile.mkdtemp(prefix="literature-clean-bench-")
checks = []


def add(name, condition, detail=""):
    checks.append((name, bool(condition), detail))


def run(*args):
    return subprocess.run([sys.executable, TOOL] + list(args), text=True, capture_output=True)


def dump(name, obj):
    path = os.path.join(TMP, name)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
    return path


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def write_csv(name, rows, headers):
    path = os.path.join(TMP, name)
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=headers)
        w.writeheader()
        w.writerows(rows)
    return path


RULES = {
    "version": "bench-1",
    "fields": {
        "paper_id": {"type": "string", "aliases": ["Paper"], "required": True},
        "experiment_id": {"type": "string", "aliases": ["Experiment"], "required": True},
        "material": {"type": "string", "aliases": ["Material"], "allowed": ["alpha", "beta"],
                     "synonyms": {"α": "alpha", "Alpha": "alpha"}},
        "condition": {"type": "string", "aliases": ["Condition"], "required": True},
        "metric": {"type": "string", "aliases": ["Metric"], "required": True},
        "potential": {"type": "number", "aliases": ["Potential"], "target_unit": "mV",
                      "conversions": {"mV": {"factor": "1"}, "V": {"factor": "1000"}},
                      "unit_aliases": {"mv": "mV"}, "min": -10000, "max": 10000,
                      "rule_id": "R-POTENTIAL-V1"},
        "concentration": {"type": "number", "aliases": ["Concentration"], "target_unit": "mg/L",
                          "conversions": {"mg/L": {"factor": "1"}, "ug/mL": {"factor": "1"},
                                          "g/L": {"factor": "1000"}, "mg/mL": {"factor": "1000"}},
                          "rule_id": "R-CONC-V1"}
    },
    "dedupe": {"identity_keys": ["paper_id", "experiment_id", "material", "condition", "metric"],
               "rule_id": "R-DEDUPE-BENCH"}
}
rules_path = dump("rules.json", RULES)
HEADERS = ["Paper", "Experiment", "Material", "Condition", "Metric", "Potential", "Concentration"]
GOOD = [
    {"Paper": "P1", "Experiment": "E1", "Material": "α", "Condition": "25C", "Metric": "ocp",
     "Potential": "0.5 V", "Concentration": "2 g/L"},
    {"Paper": "P1", "Experiment": "E1", "Material": "Alpha", "Condition": "25C", "Metric": "ocp",
     "Potential": "500 mV", "Concentration": "2000 mg/L"},
    {"Paper": "P1", "Experiment": "E2", "Material": "alpha", "Condition": "25C", "Metric": "ocp",
     "Potential": "500 mV", "Concentration": "2000 mg/L"}
]
good_path = write_csv("good.csv", GOOD, HEADERS)
case_path = dump("case.json", {"case_id": "BENCH-Q6", "output_contract": {"required": ["case_id", "status", "custom_note"]}})
out1 = os.path.join(TMP, "out1")
r = run("clean", "--input", good_path, "--rules", rules_path, "--out", out1, "--case", case_path)
res1 = load(os.path.join(out1, "result.json")) if r.returncode == 0 else {}
add("clean 正向命令成功", r.returncode == 0, r.stdout + r.stderr)
add("clean 正向零误杀", res1.get("status") == "success" and res1.get("review") == [], str(res1.get("review"))[:200])
add("clean 真换算 0.5V=500mV", res1.get("records", [{}])[0].get("potential") == "500")
add("clean 复合单位/前缀 2g/L=2000mg/L", res1.get("records", [{}])[0].get("concentration") == "2000")
add("clean 精确重复合并", res1.get("summary", {}).get("duplicate_rows_removed") == 1)
add("clean 不同实验零错并", res1.get("summary", {}).get("output_rows") == 2)
add("clean 保留原 output_contract 字段", "custom_note" in res1)
changes = [json.loads(x) for x in open(os.path.join(out1, "changes.jsonl"), encoding="utf-8") if x.strip()]
add("clean 变更含公式/规则/行定位", any(c.get("formula") and c.get("rule_id") and c["source_ref"].get("row") for c in changes))
lineage = [json.loads(x) for x in open(os.path.join(out1, "lineage.jsonl"), encoding="utf-8") if x.strip()]
add("clean 原值可回链", len(lineage[0].get("raw_records", [])) == 2 and lineage[0]["field_rules"]["potential"]["original"] == "0.5 V")

r = run("audit", "--out", out1, "--input", good_path)
add("audit 正向零误杀", r.returncode == 0 and json.loads(r.stdout)["ok"], r.stdout + r.stderr)

# Range and uncertainty arithmetic.
range_rows = [dict(GOOD[2], Potential="1–2 V")]
range_path = write_csv("range.csv", range_rows, HEADERS)
out_range = os.path.join(TMP, "range")
r = run("clean", "--input", range_path, "--rules", rules_path, "--out", out_range, "--case-id", "RANGE")
rr = load(os.path.join(out_range, "result.json"))
add("clean 区间真换算", r.returncode == 0 and rr["records"][0]["potential"] == "1000..2000"
    and rr["records"][0]["potential__low"] == "1000" and rr["records"][0]["potential__high"] == "2000")

# Mutations/dirty inputs must be visible and never silently converted/merged.
def dirty_case(name, mutate, expected_type, expected_rows=None):
    rows = copy.deepcopy(GOOD)
    mutate(rows)
    path = write_csv(name + ".csv", rows, HEADERS)
    out = os.path.join(TMP, name)
    r = run("clean", "--input", path, "--rules", rules_path, "--out", out, "--case-id", name)
    doc = load(os.path.join(out, "result.json"))
    types = [q["type"] for q in doc["review"]]
    add("变异命中 " + name, r.returncode == 0 and expected_type in types and doc["status"] == "partial"
        and (expected_rows is None or doc["summary"]["output_rows"] == expected_rows), str(doc["review"])[:220])
    return doc


doc = dirty_case("unknown_unit", lambda x: x[0].update(Potential="500 uV"), "UNKNOWN_UNIT", 3)
add("未知单位不编造换算", doc["records"][0]["potential"] == "")
dirty_case("scientific_conflict", lambda x: x[1].update(Potential="600 mV"), "DUPLICATE_CONFLICT", 3)
dirty_case("missing_identity", lambda x: x[0].update(Experiment=""), "INSUFFICIENT_IDENTITY", 3)
dirty_case("missing_required", lambda x: x[0].update(Paper=""), "MISSING_VALUE")
dirty_case("out_of_range", lambda x: x[0].update(Potential="20 V"), "OUT_OF_RANGE")
dirty_case("not_allowed", lambda x: x[0].update(Material="gamma"), "NOT_ALLOWED")
dirty_case("invalid_number", lambda x: x[0].update(Potential="five V"), "INVALID_NUMBER")
dirty_case("reversed_range", lambda x: x[0].update(Potential="2–1 V"), "REVERSED_RANGE")

alias_headers = HEADERS + ["potential"]
alias_rows = [dict(row, potential="600 mV" if i == 0 else row["Potential"]) for i, row in enumerate(GOOD)]
alias_path = write_csv("alias.csv", alias_rows, alias_headers)
r = run("clean", "--input", alias_path, "--rules", rules_path, "--out", os.path.join(TMP, "alias"), "--case-id", "ALIAS")
alias_doc = load(os.path.join(TMP, "alias", "result.json"))
add("变异命中 同义字段冲突", any(q["type"] == "ALIAS_CONFLICT" for q in alias_doc["review"]))

unmapped_headers = HEADERS + ["Mystery"]
unmapped_path = write_csv("unmapped.csv", [dict(r, Mystery="x") for r in GOOD], unmapped_headers)
run("clean", "--input", unmapped_path, "--rules", rules_path, "--out", os.path.join(TMP, "unmapped"), "--case-id", "UNMAPPED")
add("变异命中 未映射字段", any(q["type"] == "UNMAPPED_FIELD" for q in load(os.path.join(TMP, "unmapped", "result.json"))["review"]))

empty_path = write_csv("empty.csv", [], HEADERS)
r = run("clean", "--input", empty_path, "--rules", rules_path, "--out", os.path.join(TMP, "empty"), "--case-id", "EMPTY")
add("变异命中 空表", r.returncode == 0 and load(os.path.join(TMP, "empty", "result.json"))["status"] == "failed")

bad_encoding = os.path.join(TMP, "latin.csv")
with open(bad_encoding, "wb") as f:
    f.write("Paper,Experiment\nP\377,E\n".encode("latin-1"))
r = run("clean", "--input", bad_encoding, "--rules", rules_path, "--out", os.path.join(TMP, "encoding"))
add("变异命中 编码错乱", r.returncode == 1 and "ENCODING_ERROR" in r.stderr, r.stderr[:180])

bad_rules = copy.deepcopy(RULES)
bad_rules["fields"]["other"] = {"aliases": ["Paper"]}
r = run("clean", "--input", good_path, "--rules", dump("bad_rules.json", bad_rules), "--out", os.path.join(TMP, "bad_rules"))
add("变异命中 规则别名碰撞", r.returncode == 1 and "字段别名冲突" in r.stderr, r.stderr[:180])

out2 = os.path.join(TMP, "out2")
run("clean", "--input", good_path, "--rules", rules_path, "--out", out2, "--case", case_path)
add("clean 重跑字节确定", all(open(os.path.join(out1, n), "rb").read() == open(os.path.join(out2, n), "rb").read()
                              for n in ("cleaned.csv", "changes.jsonl", "lineage.jsonl", "review.json", "result.json")))

# Audit mutations: alter a copy, never the positive fixture.
def clone_out(name):
    dst = os.path.join(TMP, name)
    os.makedirs(dst)
    for n in os.listdir(out1):
        with open(os.path.join(out1, n), "rb") as src, open(os.path.join(dst, n), "wb") as dstf:
            dstf.write(src.read())
    return dst


bad_out = clone_out("audit_formula")
bad_changes = [json.loads(x) for x in open(os.path.join(bad_out, "changes.jsonl"), encoding="utf-8") if x.strip()]
for c in bad_changes:
    if c["action"] == "unit_conversion":
        c.pop("formula", None)
with open(os.path.join(bad_out, "changes.jsonl"), "w", encoding="utf-8") as f:
    for c in bad_changes:
        f.write(json.dumps(c, ensure_ascii=False) + "\n")
r = run("audit", "--out", bad_out)
add("audit 变异命中 无公式换算", r.returncode == 1 and "单位换算无公式" in r.stdout, r.stdout[:200])

bad_out = clone_out("audit_lineage")
lines = [json.loads(x) for x in open(os.path.join(bad_out, "lineage.jsonl"), encoding="utf-8") if x.strip()]
lines[0]["raw_records"] = []
with open(os.path.join(bad_out, "lineage.jsonl"), "w", encoding="utf-8") as f:
    for line in lines:
        f.write(json.dumps(line, ensure_ascii=False) + "\n")
r = run("audit", "--out", bad_out)
add("audit 变异命中 断原值链", r.returncode == 1 and "缺 raw_records" in r.stdout, r.stdout[:200])

bad_out = clone_out("audit_status")
doc = load(os.path.join(bad_out, "result.json"))
doc["review"] = [{"id": "Q1", "type": "X", "signal": "s", "action": "a", "source_ref": {"row": 1}, "status": "pending"}]
doc["status"] = "success"
dump_path = os.path.join(bad_out, "result.json")
with open(dump_path, "w", encoding="utf-8") as f:
    json.dump(doc, f, ensure_ascii=False)
with open(os.path.join(bad_out, "review.json"), "w", encoding="utf-8") as f:
    json.dump(doc["review"], f, ensure_ascii=False)
r = run("audit", "--out", bad_out)
add("audit 变异命中 待确认却成功", r.returncode == 1 and "有待确认项" in r.stdout, r.stdout[:200])

r = run("audit", "--out", out1, "--input", range_path)
add("audit 变异命中 来源哈希错配", r.returncode == 1 and "SHA256" in r.stdout, r.stdout[:180])

run_meta = {"input_sha256": hashlib.sha256(b"same").hexdigest(), "permissions": "no-network/read-only",
            "model": "same-model", "budget_seconds": 900}
baseline = {"run": run_meta, "correct_cells": 8, "total_cells": 10, "false_merges": 1,
            "manual_corrections": 6, "runtime_seconds": 200}
skill = {"run": run_meta, "correct_cells": 10, "total_cells": 10, "false_merges": 0,
         "manual_corrections": 1, "runtime_seconds": 120}
gain_path = os.path.join(TMP, "gain.json")
r = run("gain", "--baseline", dump("baseline.json", baseline), "--skill", dump("skill.json", skill), "--out", gain_path)
gain = load(gain_path) if r.returncode == 0 else {}
add("gain 正向公平对照零误杀", r.returncode == 0 and abs(gain.get("delta", {}).get("cell_accuracy", 0) - 0.2) < 1e-12
    and gain["delta"]["false_merges"] == -1, r.stdout + r.stderr)
bad_skill = copy.deepcopy(skill)
bad_skill["run"] = dict(run_meta, input_sha256="different")
r = run("gain", "--baseline", dump("baseline.json", baseline), "--skill", dump("bad_skill.json", bad_skill), "--out", gain_path)
add("gain 变异命中 不同输入", r.returncode == 1 and "input_sha256" in r.stdout, r.stdout[:180])
bad_skill = copy.deepcopy(skill)
bad_skill["correct_cells"] = 11
r = run("gain", "--baseline", dump("baseline.json", baseline), "--skill", dump("bad_skill2.json", bad_skill), "--out", gain_path)
add("gain 变异命中 不可能指标", r.returncode == 1 and "非法" in r.stdout, r.stdout[:180])

passed = sum(c for _, c, _ in checks)
for name, ok, detail in checks:
    print(("PASS" if ok else "FAIL") + " " + name + ((" | " + detail) if not ok else ""))
print("BENCH %s (%d/%d)" % ("PASS" if passed == len(checks) else "FAIL", passed, len(checks)))
sys.exit(0 if passed == len(checks) else 1)
