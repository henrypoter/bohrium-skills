#!/usr/bin/env python3
"""End-to-end positive/mutation bench for all five routed workflows."""
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
TMP = tempfile.mkdtemp(prefix="integrated-bench-")
CHECKS = []


def run(*args):
    proc = subprocess.run([sys.executable, TOOL, *args], capture_output=True, text=True)
    try:
        return proc.returncode, json.loads(proc.stdout)
    except Exception:
        return proc.returncode, {"raw": proc.stdout[:300], "stderr": proc.stderr[:300]}


def read(name):
    with open(os.path.join(FIX, name), encoding="utf-8") as handle:
        return json.load(handle)


def dump(name, value, raw=False):
    path = os.path.join(TMP, name)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(value if raw else json.dumps(value, ensure_ascii=False))
    return path


def add(name, condition, detail=""):
    CHECKS.append((name, bool(condition), str(detail)))


def err(data, phrase):
    return any(phrase in item for item in data.get("errors", []))


def violation(data, phrase):
    return any(phrase in item.get("issue", "") for item in data.get("violations", []))


BASE = read("good_result.json")
PROBLEM = read("problem.json")
GOOD = dump("good.json", BASE)
CASE = os.path.join(FIX, "example_input.json")
PROBLEM_PATH = os.path.join(FIX, "problem.json")

# route: five exact routes, no spurious extra routes, mixed and unsupported cases
route_inputs = {
    "generation": "请设计实验并生成方案。",
    "comparison": "请比较候选方案并给出选择理由。",
    "feasibility": "请做可行性评估和资源核验。",
    "parameter": "请给出参数优化建议和搜索策略。",
    "interpretation": "请做实验结果解释和异常分析。",
}
for index, (route, text) in enumerate(route_inputs.items()):
    task = dump("route_%d.md" % index, text, raw=True)
    out_path = os.path.join(TMP, "route_%d.json" % index)
    rc, out = run("route", "--task", task, "--case", CASE, "--out", out_path)
    add("route 正向%s且零误报" % route, rc == 0 and out.get("primary") == route and out.get("routes") == [route], out)
mixed = dump("mixed.md", "请比较候选方案，完成可行性评估、参数优化建议及结果解释。", raw=True)
rc, out = run("route", "--task", mixed, "--case", CASE, "--out", os.path.join(TMP, "mixed_route.json"))
add("route 混合任务保留四个独立流程", rc == 0 and set(out.get("routes", [])) == {"comparison", "feasibility", "parameter", "interpretation"}, out)
unknown = dump("unknown.md", "请整理日程。", raw=True)
rc, out = run("route", "--task", unknown, "--case", CASE, "--out", os.path.join(TMP, "unknown_route.json"))
add("route 不支持输入必须停止而非默认生成", rc == 1 and out.get("primary") == "unsupported", out)
explicit_case = copy.deepcopy(read("example_input.json")); explicit_case["task_type"] = "parameter"
rc, out = run("route", "--task", unknown, "--case", dump("explicit_case.json", explicit_case), "--out", os.path.join(TMP, "explicit_route.json"))
add("route 显式case.task_type有字段级证据", rc == 0 and out.get("primary") == "parameter", out)

# compare: normalized ranking, sensitivity, hard rejection and inconsistent units/fields
COMP_IN = os.path.join(FIX, "comparison_input.json")
COMP_OUT = os.path.join(TMP, "comparison.json")
rc, out = run("compare", COMP_IN, "--out", COMP_OUT)
add("compare 正向归一化权衡零误杀", rc == 0 and out.get("recommended", {}).get("id") == "B" and out.get("evaluated_count") == 3, out)
comparison = json.load(open(COMP_OUT, encoding="utf-8"))
add("compare 输出含逐项权重敏感性", len(comparison.get("sensitivity", [])) == 4 and all("stable" in row for row in comparison["sensitivity"]), comparison)
reject = read("comparison_input.json"); reject["metrics"]["cost"]["max"] = 60
rc, out = run("compare", dump("comparison_reject.json", reject), "--out", os.path.join(TMP, "comparison_reject_out.json"))
add("compare 硬预算变异必拒绝B", rc == 0 and out.get("recommended", {}).get("id") != "B", out)
bad_compare = read("comparison_input.json"); bad_compare["candidates"][0]["metrics"].pop("cost")
rc, out = run("compare", dump("comparison_missing_metric.json", bad_compare), "--out", os.path.join(TMP, "bad_compare_out.json"))
add("compare 指标口径不齐不得计算总分", rc == 2 and "指标集合不一致" in out.get("error", ""), out)
bad_compare = read("comparison_input.json"); bad_compare["candidates"][0]["metrics"]["yield"] = float("nan")
rc, out = run("compare", dump("comparison_nan.json", bad_compare), "--out", os.path.join(TMP, "nan_compare_out.json"))
add("compare NaN指标必命中", rc == 2 and not out.get("ok", True), out)

# interpretation: arithmetic fit, zero false positive on exact line, anomaly and invalid domain
OBS = os.path.join(FIX, "observations.json")
INTERP_OUT = os.path.join(TMP, "interpretation.json")
rc, out = run("interpret", OBS, "--out", INTERP_OUT)
add("interpret 正向极端残差绑定O7", rc == 0 and out.get("flagged_anomalies") == ["O7"], out)
clean = {"dataset_version": "clean-v1", "unit": "%", "observations": [{"id": str(i), "x": i, "y": 2 * i} for i in range(1, 5)]}
rc, out = run("interpret", dump("clean_observations.json", clean), "--out", os.path.join(TMP, "clean_interpretation.json"))
add("interpret 完美线性零异常误杀", rc == 0 and out.get("flagged_anomalies") == [], out)
constant_x = copy.deepcopy(clean)
for row in constant_x["observations"]: row["x"] = 1
rc, out = run("interpret", dump("constant_x.json", constant_x), "--out", os.path.join(TMP, "constant_interpretation.json"))
add("interpret 不可拟合变异必命中", rc == 2 and "至少两个不同值" in out.get("error", ""), out)
nan_obs = copy.deepcopy(clean); nan_obs["observations"][0]["y"] = float("nan")
rc, out = run("interpret", dump("nan_observations.json", nan_obs), "--out", os.path.join(TMP, "nan_interpretation.json"))
add("interpret NaN观测不得放行", rc == 2 and not out.get("ok", True), out)

# resources: four-state fields, sample, true cost and schedule
rc, out = run("resources", GOOD)
add("resources 正向四态/预算/排期零误杀", rc == 0 and out.get("computed", {}).get("elapsed_hours") == "16", out)
bad = copy.deepcopy(BASE); bad["resources"]["cost_estimate"]["line_items"][0]["subtotal"] = 201
rc, out = run("resources", dump("router_bad_cost.json", bad))
add("resources 成本乘法变异必命中", rc == 1 and err(out, "subtotal"), out)
bad = copy.deepcopy(BASE); bad["resources"]["sample"]["available"] = 1
rc, out = run("resources", dump("router_bad_sample.json", bad))
add("resources 样本不足变异必命中", rc == 1 and err(out, "样本不足"), out)
bad = copy.deepcopy(BASE); bad["resources"]["time_estimate"]["elapsed_hours"] = 12
rc, out = run("resources", dump("router_bad_schedule.json", bad))
add("resources 排期算术变异必命中", rc == 1 and err(out, "关键路径"), out)
bad = copy.deepcopy(BASE); bad["resources"]["equipment"][0] = {"availability": "not_checked"}
rc, out = run("resources", dump("router_unknown_equipment.json", bad))
add("resources 设备不明必须给not_checked理由", rc == 1 and err(out, "not_checked"), out)

# optimize/replay: router's parameter branch really executes and reproduces
OPT = os.path.join(TMP, "optimization.json")
rc, out = run("optimize", PROBLEM_PATH, "--out", OPT)
add("optimize 路由参数流程正向六点全枚举", rc == 0 and out.get("evaluated_count") == 6 and out.get("feasible_count") == 3, out)
rc, out = run("replay", PROBLEM_PATH, OPT)
add("replay 参数流程原始产物完整重放", rc == 0 and out.get("recommended_match"), out)
tampered = json.load(open(OPT, encoding="utf-8")); tampered["recommended"]["score"] = "1"
rc, out = run("replay", PROBLEM_PATH, dump("tampered_optimization.json", tampered))
add("replay 篡改推荐必命中", rc == 1 and not out.get("recommended_match"), out)
no = copy.deepcopy(PROBLEM); no["responses"]["yield"]["acceptable_min"] = 100
rc, out = run("optimize", dump("router_no_feasible.json", no), "--out", os.path.join(TMP, "router_no_feasible_out.json"))
add("optimize 无可行解不伪造推荐", rc == 1 and out.get("recommended") is None and out.get("evaluated_count") == 6, out)
cap = copy.deepcopy(PROBLEM); cap["search"]["max_evaluations"] = 2
rc, out = run("optimize", dump("router_capped.json", cap), "--out", os.path.join(TMP, "router_capped_out.json"))
add("optimize 超网格预算拒绝静默截断", rc == 2 and "拒绝静默截断" in out.get("error", ""), out)

# params and route-aware audit/schema
rc, out = run("params", GOOD, "--spec", PROBLEM_PATH)
add("params 正向量程反推零误杀", rc == 0 and out.get("derived_intersections", {}).get("temperature") == {"min": "40", "max": "60"}, out)
bad = copy.deepcopy(BASE); bad["parameters"][0]["value"] = 70
rc, out = run("params", dump("router_out_of_range.json", bad), "--spec", PROBLEM_PATH)
add("params 推荐越界变异必命中", rc == 1 and violation(out, "越出"), out)
bad = copy.deepcopy(BASE); bad["parameters"][0]["value"] = 55
rc, out = run("params", dump("router_bad_step.json", bad), "--spec", PROBLEM_PATH)
add("params 步进变异必命中", rc == 1 and violation(out, "步进"), out)
rc, out = run("audit", GOOD)
add("audit 生成分支正向零误杀", rc == 0 and out.get("routes") == ["generation"], out)
rc, out = run("schema", GOOD)
add("schema 别名正向零误杀", rc == 0 and out.get("ok"), out)
bad = copy.deepcopy(BASE); bad["routing"]["primary"] = "comparison"
rc, out = run("audit", dump("wrong_primary.json", bad))
add("audit 主路由篡改必命中", rc == 1 and err(out, "primary"), out)
bad = copy.deepcopy(BASE); bad["routing"]["routes"] = []
rc, out = run("audit", dump("no_route.json", bad))
add("audit 未分诊结果不得交付", rc == 1 and err(out, "routes"), out)
bad = copy.deepcopy(BASE); bad["exception_register"] = bad["exception_register"][:-1]
rc, out = run("audit", dump("missing_execution_exception.json", bad))
add("audit 执行失败异常缺失必命中", rc == 1 and err(out, "execution_failed"), out)
bad = copy.deepcopy(BASE); bad.pop("result_schema_version")
rc, out = run("audit", dump("router_no_version.json", bad))
add("audit 结果版本缺失必命中", rc == 1 and err(out, "result_schema_version"), out)

# Positive dynamic-contract coverage for the other four routed result shapes
def routed(route, key, artifact, extra_codes=()):
    result = copy.deepcopy(BASE)
    row = copy.deepcopy(result["routing"]["routes"][0])
    row["route"] = route
    result["routing"]["primary"] = route
    result["routing"]["routes"] = [row]
    result[key] = artifact
    for code in extra_codes:
        result["exception_register"].append({"code": code, "signal": "示例信号", "action": "降级并交负责人", "disposition": "manual", "owner": "示例负责人", "linked_fields": [key]})
    return result

comp_result = routed("comparison", "comparison", comparison)
rc, out = run("audit", dump("positive_comparison_result.json", comp_result))
add("audit 比较路由专属结果正向零误杀", rc == 0 and out.get("routes") == ["comparison"], out)
interp_result = routed("interpretation", "interpretation", json.load(open(INTERP_OUT, encoding="utf-8")), ["conflicting_metrics"])
rc, out = run("audit", dump("positive_interpretation_result.json", interp_result))
add("audit 解释路由专属结果正向零误杀", rc == 0 and out.get("routes") == ["interpretation"], out)
optimization = json.load(open(OPT, encoding="utf-8"))
param_result = routed("parameter", "optimization", optimization,
                      ["no_feasible_solution", "conflicting_constraints", "equipment_error", "conflicting_metrics", "insufficient_permissions"])
param_result["response_metrics"] = []
for name in ("yield", "impurity"):
    param_result["response_metrics"].append({"name": name, "unit": "%", "measurement_method": "示例测量", "direction": "maximize", "acceptable_variation": "1", "model_ref": "problem", "uncertainty": {"method": "示例", "value": 1}, "evidence": copy.deepcopy(BASE["judgments"][0]["evidence"])})
param_result["search"] = {"stop_reason": optimization["stopping_reason"]}
param_result["cost_budget"] = {"currency": "CNY"}
rc, out = run("audit", dump("positive_parameter_result.json", param_result))
add("audit 参数路由专属结果正向零误杀", rc == 0 and out.get("routes") == ["parameter"], out)
feas_codes = ["plan_missing_pages", "missing_parameters", "unknown_equipment", "ethics_undetermined", "internal_contradiction", "oversized_document", "device_failure", "material_batch_variation", "insufficient_sample", "parameter_out_of_range"]
feas_result = routed("feasibility", "feasibility", {"overall": "feasible", "checks": []}, feas_codes)
for category in ("假设与变量", "对照组", "设备材料", "时间成本", "参数范围", "风险与异常", "伦理与安全"):
    feas_result["feasibility"]["checks"].append({"category": category, "status": "pass", "target": "#/temperature", "conclusion": "示例已核验", "evidence": copy.deepcopy(BASE["judgments"][0]["evidence"])})
rc, out = run("audit", dump("positive_feasibility_result.json", feas_result))
add("audit 可行性七类结果正向零误杀", rc == 0 and out.get("routes") == ["feasibility"], out)

# verify exact route quote and case field hashes
rc, out = run("verify", GOOD, "--source-root", FIX)
add("verify 路由/判断/参数三处证据零误杀", rc == 0 and out.get("verified_evidence") == 3, out)
bad = copy.deepcopy(BASE); bad["routing"]["routes"][0]["evidence"][0]["quote"] = "请生成论文。"
rc, out = run("verify", dump("router_wrong_quote.json", bad), "--source-root", FIX)
add("verify 路由引文篡改必命中", rc == 1 and err(out, "quote"), out)
bad = copy.deepcopy(BASE); bad["judgments"][0]["evidence"][0]["location"] = "#/missing"
rc, out = run("verify", dump("router_wrong_pointer.json", bad), "--source-root", FIX)
add("verify 原文字段定位失效必命中", rc == 1 and err(out, "定位失败"), out)
bad = copy.deepcopy(BASE); bad["sources"][0]["sha256"] = "0" * 64
rc, out = run("verify", dump("router_hash_tamper.json", bad), "--source-root", FIX)
add("verify 源版本篡改必命中", rc == 1 and err(out, "SHA-256"), out)

# gain: actual routed metrics and fairness guards
baseline = copy.deepcopy(BASE); baseline["parameters"] = []; baseline["controls"] = []
BASELINE = dump("baseline.json", baseline)
GAIN = os.path.join(TMP, "with_gain.json")
rc, out = run("gain", BASELINE, GOOD, "--out", GAIN)
add("gain 正向同输入同权限路由对照", rc == 0 and out.get("gain", {}).get("quality", {}).get("skill_sections_present", 0) > out.get("gain", {}).get("quality", {}).get("baseline_sections_present", 0), out)
rc, checked = run("audit", GAIN)
add("gain 产物回读仍满足路由契约", rc == 0 and checked.get("ok"), checked)
wrong = copy.deepcopy(BASE); wrong["input_digest"] = "c" * 64
rc, out = run("gain", BASELINE, dump("router_wrong_input.json", wrong), "--out", os.path.join(TMP, "wrong_gain.json"))
add("gain 不同输入拒绝比较", rc == 2 and "input_digest" in out.get("error", ""), out)
wrong = copy.deepcopy(BASE); wrong["permissions_digest"] = "d" * 64
rc, out = run("gain", BASELINE, dump("router_wrong_permission.json", wrong), "--out", os.path.join(TMP, "wrong_gain2.json"))
add("gain 不同权限拒绝比较", rc == 2 and "permissions_digest" in out.get("error", ""), out)

passed = sum(ok for _, ok, _ in CHECKS)
for name, ok, detail in CHECKS:
    print(("PASS" if ok else "FAIL"), name, ("| " + detail[:500] if not ok else ""))
print("total %d/%d" % (passed, len(CHECKS)))
sys.exit(0 if passed == len(CHECKS) else 1)
