#!/usr/bin/env python3
"""Mutation bench: every command has a valid positive and must-fail mutants."""
import copy
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
TOOL = os.path.join(ROOT, "scripts", "exp_tool.py")
FIX = os.path.join(HERE, "fixtures")
TMP = tempfile.mkdtemp(prefix="feasibility-bench-")
CHECKS = []


def run(*args):
    proc = subprocess.run([sys.executable, TOOL, *args], capture_output=True, text=True)
    try:
        return proc.returncode, json.loads(proc.stdout)
    except Exception:
        return proc.returncode, {"raw": proc.stdout[:300], "stderr": proc.stderr[:300]}


def clone():
    with open(os.path.join(FIX, "good_result.json"), encoding="utf-8") as handle:
        return json.load(handle)


def dump(name, obj):
    path = os.path.join(TMP, name)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(obj, handle, ensure_ascii=False)
    return path


def add(name, condition, detail=""):
    CHECKS.append((name, bool(condition), str(detail)))


def has_errors(data, phrase):
    return any(phrase in item for item in data.get("errors", []))


def has_violations(data, phrase):
    return any(phrase in item.get("issue", "") for item in data.get("violations", []))


BASE = clone()
GOOD = dump("good.json", BASE)
SPEC = os.path.join(FIX, "limits.json")

# audit/schema: 1 positive + 8 mutants
rc, out = run("audit", GOOD)
add("audit 正向七类/十异常零误杀", rc == 0 and out.get("ok"), out)
rc, out = run("schema", GOOD)
add("schema 别名正向零误杀", rc == 0 and out.get("ok"), out)
bad = clone(); bad["feasibility"]["checks"] = [c for c in bad["feasibility"]["checks"] if c["category"] != "伦理与安全"]
rc, out = run("audit", dump("missing_category.json", bad))
add("audit 变异缺伦理检查必命中", rc == 1 and has_errors(out, "伦理与安全"), out)
bad = clone(); bad["exception_register"].append(copy.deepcopy(bad["exception_register"][0]))
rc, out = run("audit", dump("duplicate_exception.json", bad))
add("audit 变异异常重复必命中", rc == 1 and has_errors(out, "plan_missing_pages"), out)
bad = clone(); bad["feasibility"]["checks"][2]["conditions"] = []
rc, out = run("audit", dump("conditional_no_condition.json", bad))
add("audit 变异条件可行无条件必命中", rc == 1 and has_errors(out, "conditional"), out)
bad = clone(); bad["feasibility"]["checks"][0].update(status="not_checked", reason="", evidence=[])
bad["feasibility"]["overall"] = "partial"
rc, out = run("audit", dump("not_checked_no_reason.json", bad))
add("audit 变异未核验无理由必命中", rc == 1 and has_errors(out, "not_checked"), out)
bad = clone(); bad.pop("result_schema_version")
rc, out = run("audit", dump("no_schema_version.json", bad))
add("audit 变异缺结果版本必命中", rc == 1 and has_errors(out, "result_schema_version"), out)
bad = clone(); bad["judgments"][0]["evidence"][0]["sha256"] = "xyz"
rc, out = run("audit", dump("bad_evidence_hash.json", bad))
add("audit 变异证据哈希非法必命中", rc == 1 and has_errors(out, "sha256"), out)
bad = clone(); bad["gain"]["design"]["same_permissions"] = False
rc, out = run("audit", dump("unfair_gain.json", bad))
add("audit 变异对照权限不一致必命中", rc == 1 and has_errors(out, "same_permissions"), out)

# resources: arithmetic, four-state availability, sample and approvals
rc, out = run("resources", GOOD)
add("resources 正向资源/预算关键路径零误杀", rc == 0 and out.get("computed", {}).get("expected_elapsed_hours") == "40", out)
bad = clone(); bad["resources"]["cost_estimate"]["line_items"][0]["subtotal"] = 201
rc, out = run("resources", dump("bad_subtotal.json", bad))
add("resources 变异分项乘法错误必命中", rc == 1 and has_errors(out, "subtotal"), out)
bad = clone(); bad["resources"]["cost_estimate"]["within_budget"] = False
rc, out = run("resources", dump("bad_budget_boolean.json", bad))
add("resources 变异预算布尔与真值不符必命中", rc == 1 and has_errors(out, "within_budget"), out)
bad = clone(); bad["resources"]["time_estimate"]["steps"][1]["duration_hours"] = 13
rc, out = run("resources", dump("bad_duration.json", bad))
add("resources 变异步骤时长错误必命中", rc == 1 and has_errors(out, "duration_hours"), out)
bad = clone(); bad["resources"]["time_estimate"]["elapsed_hours"] = 28
rc, out = run("resources", dump("bad_critical_path.json", bad))
add("resources 变异漏采购等待必命中", rc == 1 and has_errors(out, "关键路径"), out)
bad = clone(); bad["resources"]["sample"]["available"] = 5
rc, out = run("resources", dump("sample_shortage.json", bad))
add("resources 变异样本不足必命中", rc == 1 and has_errors(out, "样本"), out)
bad = clone(); bad["resources"]["equipment"][0].pop("precision")
rc, out = run("resources", dump("unknown_precision.json", bad))
add("resources 变异设备缺精度必命中", rc == 1 and has_errors(out, "precision"), out)
bad = clone(); bad["resources"]["ethics"] = {"status": "pending"}
rc, out = run("resources", dump("pending_ethics.json", bad))
add("resources 变异伦理待定无动作必命中", rc == 1 and has_errors(out, "禁止放行"), out)

# params: true intersection, range, step, unit, empty intersection and mutex
rc, out = run("params", GOOD, "--spec", SPEC)
add("params 正向反推20-60且步进零误杀", rc == 0 and out.get("derived_intersections", {}).get("temperature") == {"min": "20", "max": "60"}, out)
bad = clone(); bad["parameters"][0]["value"] = 70
rc, out = run("params", dump("out_of_intersection.json", bad), "--spec", SPEC)
add("params 变异越出材料上限必命中", rc == 1 and has_violations(out, "交集"), out)
bad = clone(); bad["parameters"][0]["derived_min"] = 0
rc, out = run("params", dump("wrong_derived_min.json", bad), "--spec", SPEC)
add("params 变异反推下限造假必命中", rc == 1 and has_violations(out, "derived_min"), out)
bad = clone(); bad["parameters"][0]["value"] = 55
rc, out = run("params", dump("wrong_step.json", bad), "--spec", SPEC)
add("params 变异不满足步进必命中", rc == 1 and has_violations(out, "步进"), out)
bad = clone(); bad["parameters"][0]["unit"] = "K"
rc, out = run("params", dump("wrong_unit.json", bad), "--spec", SPEC)
add("params 变异单位不一致必命中", rc == 1 and has_violations(out, "单位"), out)
with open(SPEC, encoding="utf-8") as handle:
    conflict_spec = json.load(handle)
conflict_spec["limits"]["temperature"][1]["min"] = 90
bad = clone(); bad["parameters"][0]["value"] = 95; bad["parameters"][0]["derived_min"] = 90; bad["parameters"][0]["derived_max"] = 80
rc, out = run("params", dump("empty_intersection.json", bad), "--spec", dump("conflict_spec.json", conflict_spec))
add("params 变异交集为空必命中", rc == 1 and has_violations(out, "交集为空"), out)
mutex_spec = copy.deepcopy(json.load(open(SPEC, encoding="utf-8")))
mutex_spec["limits"]["dose"] = {"min": 0, "max": 5, "step": 1, "unit": "uM", "source": "示例", "mutex_with": ["temperature"]}
bad = clone(); bad["parameters"].append({"name": "dose", "value": 1, "unit": "uM", "derived_min": 0, "derived_max": 5, "evidence": copy.deepcopy(bad["parameters"][0]["evidence"])})
rc, out = run("params", dump("mutex.json", bad), "--spec", dump("mutex_spec.json", mutex_spec))
add("params 变异已选参数互斥必命中", rc == 1 and has_violations(out, "互斥"), out)
bad = clone(); bad["parameters"][0]["value"] = float("nan")
rc, out = run("params", dump("nan.json", bad), "--spec", SPEC)
add("params 变异NaN拒绝而非放行", rc == 2 and not out.get("ok", True), out)

# verify: real file hash + exact pointer/quote
rc, out = run("verify", GOOD, "--source-root", FIX)
add("verify 正向哈希/指针/引文零误杀", rc == 0 and out.get("verified_evidence") == 10, out)
bad = clone(); bad["judgments"][0]["evidence"][0]["quote"] = "51"
rc, out = run("verify", dump("wrong_quote.json", bad), "--source-root", FIX)
add("verify 变异非逐字引文必命中", rc == 1 and has_errors(out, "quote"), out)
bad = clone(); bad["judgments"][0]["evidence"][0]["location"] = "#/plan/not_there"
rc, out = run("verify", dump("wrong_pointer.json", bad), "--source-root", FIX)
add("verify 变异定位失效必命中", rc == 1 and has_errors(out, "定位失败"), out)
bad = clone(); bad["sources"][0]["sha256"] = "0" * 64
rc, out = run("verify", dump("source_tampered.json", bad), "--source-root", FIX)
add("verify 变异源文件版本被篡改必命中", rc == 1 and has_errors(out, "SHA-256"), out)

# gain: actual same-input comparison and fairness failures
baseline = clone(); baseline["judgments"] = []; baseline["feasibility"]["checks"] = baseline["feasibility"]["checks"][:5]
BASELINE = dump("baseline.json", baseline)
GAIN = os.path.join(TMP, "with_gain.json")
rc, out = run("gain", BASELINE, GOOD, "--out", GAIN)
add("gain 正向同输入实测质量对照零误杀", rc == 0 and out.get("gain", {}).get("quality", {}).get("skill_review_coverage") == 7, out)
rc, checked = run("audit", GAIN)
add("gain 产物回读仍满足交付契约", rc == 0 and checked.get("ok"), checked)
wrong = clone(); wrong["input_digest"] = "c" * 64
rc, out = run("gain", BASELINE, dump("wrong_input_gain.json", wrong), "--out", os.path.join(TMP, "wrong_gain.json"))
add("gain 变异输入不同拒绝比较", rc == 2 and "input_digest" in out.get("error", ""), out)
wrong = clone(); wrong["permissions_digest"] = "d" * 64
rc, out = run("gain", BASELINE, dump("wrong_permission_gain.json", wrong), "--out", os.path.join(TMP, "wrong_gain2.json"))
add("gain 变异权限不同拒绝比较", rc == 2 and "permissions_digest" in out.get("error", ""), out)

passed = sum(ok for _, ok, _ in CHECKS)
for name, ok, detail in CHECKS:
    print(("PASS" if ok else "FAIL"), name, ("| " + detail[:500] if not ok else ""))
print("total %d/%d" % (passed, len(CHECKS)))
sys.exit(0 if passed == len(CHECKS) else 1)
