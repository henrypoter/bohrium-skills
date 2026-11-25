#!/usr/bin/env python3
"""Positive + mandatory-hit mutation bench for bounded parameter optimization."""
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
TMP = tempfile.mkdtemp(prefix="parameter-bench-")
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


def dump(name, obj):
    path = os.path.join(TMP, name)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(obj, handle, ensure_ascii=False)
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
PROBLEM_PATH = os.path.join(FIX, "problem.json")

# optimize: true enumeration, constraints, cost and fail-closed limits
OPT = os.path.join(TMP, "optimization.json")
rc, out = run("optimize", PROBLEM_PATH, "--out", OPT)
add("optimize 正向六点穷举零误杀", rc == 0 and out.get("evaluated_count") == 6 and out.get("feasible_count") == 3, out)
add("optimize 正向推荐由真实算术产生", out.get("recommended", {}).get("parameters") == {"temperature": "60", "duration": "1"} and out.get("recommended", {}).get("costs", {}).get("money") == "55", out)
generated = json.load(open(OPT, encoding="utf-8"))
add("optimize 约束冲突候选记录拒绝码", any(row["index"] == 5 and "constraint:load" in row["rejection_reasons"] for row in generated["rejected_candidates"]), generated["rejected_candidates"])
no = copy.deepcopy(PROBLEM); no["responses"]["yield"]["acceptable_min"] = 100
rc, out = run("optimize", dump("no_feasible_problem.json", no), "--out", os.path.join(TMP, "no_feasible_opt.json"))
add("optimize 无可行解完整枚举后交人工", rc == 1 and out.get("feasible_count") == 0 and out.get("evaluated_count") == 6 and out.get("recommended") is None, out)
capped = copy.deepcopy(PROBLEM); capped["search"]["max_evaluations"] = 2
rc, out = run("optimize", dump("capped_problem.json", capped), "--out", os.path.join(TMP, "capped_opt.json"))
add("optimize 网格超上限拒绝静默截断", rc == 2 and "拒绝静默截断" in out.get("error", ""), out)
nonfinite = copy.deepcopy(PROBLEM); nonfinite["responses"]["yield"]["model"]["intercept"] = float("nan")
rc, out = run("optimize", dump("nan_problem.json", nonfinite), "--out", os.path.join(TMP, "nan_opt.json"))
add("optimize NaN模型系数不得放行", rc == 2 and not out.get("ok", True), out)
conflict = copy.deepcopy(PROBLEM); conflict["limits"]["temperature"]["min"] = 70
rc, out = run("optimize", dump("conflict_problem.json", conflict), "--out", os.path.join(TMP, "conflict_opt.json"))
add("optimize min>max约束冲突必命中", rc == 2 and "min>max" in out.get("error", ""), out)
budget = copy.deepcopy(PROBLEM); budget["costs"]["money"]["max"] = 50
rc, out = run("optimize", dump("budget_problem.json", budget), "--out", os.path.join(TMP, "budget_opt.json"))
add("optimize 费用预算真实裁剪推荐点", rc == 0 and out.get("recommended", {}).get("costs", {}).get("money") == "50", out)

# replay: deterministic full-artifact verification
rc, out = run("replay", PROBLEM_PATH, GOOD)
add("replay 正向完整重放哈希一致", rc == 0 and out.get("recommended_match"), out)
bad = copy.deepcopy(BASE); bad["optimization"]["recommended"]["score"] = "0.999"
rc, out = run("replay", PROBLEM_PATH, dump("tampered_replay.json", bad))
add("replay 变异推荐分数篡改必命中", rc == 1 and not out.get("recommended_match"), out)
bad = copy.deepcopy(BASE); bad["optimization"]["rejected_candidates"] = []
rc, out = run("replay", PROBLEM_PATH, dump("missing_rejected_replay.json", bad))
add("replay 变异删除拒绝轨迹必命中", rc == 1 and out.get("actual_sha256") != out.get("expected_sha256"), out)

# audit/schema: versions, response definitions, stopping and costs
rc, out = run("audit", GOOD)
add("audit 正向完整参数链路零误杀", rc == 0 and out.get("feasible_count") == 3, out)
rc, out = run("schema", GOOD)
add("schema 别名正向零误杀", rc == 0 and out.get("ok"), out)
bad = copy.deepcopy(BASE); bad["response_metrics"][0]["uncertainty"] = {}
rc, out = run("audit", dump("no_uncertainty.json", bad))
add("audit 变异响应无不确定度必命中", rc == 1 and err(out, "uncertainty"), out)
bad = copy.deepcopy(BASE); bad["optimization"]["evaluated_count"] = 5
rc, out = run("audit", dump("bad_evaluation_count.json", bad))
add("audit 变异评估计数不符必命中", rc == 1 and err(out, "evaluated_count"), out)
bad = copy.deepcopy(BASE); bad["optimization"]["recommended"] = copy.deepcopy(bad["optimization"]["feasible_candidates"][1])
rc, out = run("audit", dump("not_first_recommendation.json", bad))
add("audit 变异推荐非确定排序首项必命中", rc == 1 and err(out, "recommended"), out)
bad = copy.deepcopy(BASE); bad["cost_budget"]["selected_cost"] = 54
rc, out = run("audit", dump("cost_mismatch.json", bad))
add("audit 变异成本口径不一致必命中", rc == 1 and err(out, "selected_cost"), out)
bad = copy.deepcopy(BASE); bad["search"]["stop_reason"] = "early_guess"
rc, out = run("audit", dump("bad_stop.json", bad))
add("audit 变异停止原因不一致必命中", rc == 1 and err(out, "stop_reason"), out)
bad = copy.deepcopy(BASE); bad["exception_register"] = bad["exception_register"][:-1]
rc, out = run("audit", dump("missing_permission_exception.json", bad))
add("audit 变异漏权限异常必命中", rc == 1 and err(out, "insufficient_permissions"), out)
bad = copy.deepcopy(BASE); bad.pop("result_schema_version")
rc, out = run("audit", dump("no_version.json", bad))
add("audit 变异缺结果版本必命中", rc == 1 and err(out, "result_schema_version"), out)

# params: inverse bounds, range and step
rc, out = run("params", GOOD, "--spec", PROBLEM_PATH)
add("params 正向两参数量程反推零误杀", rc == 0 and out.get("derived_intersections", {}).get("temperature") == {"min": "40", "max": "60"}, out)
bad = copy.deepcopy(BASE); bad["parameters"][0]["value"] = 70
rc, out = run("params", dump("out_of_range.json", bad), "--spec", PROBLEM_PATH)
add("params 变异推荐越界必命中", rc == 1 and violation(out, "越出"), out)
bad = copy.deepcopy(BASE); bad["parameters"][0]["derived_max"] = 80
rc, out = run("params", dump("wrong_derived.json", bad), "--spec", PROBLEM_PATH)
add("params 变异反推上限造假必命中", rc == 1 and violation(out, "derived_max"), out)
bad = copy.deepcopy(BASE); bad["parameters"][0]["value"] = 55
rc, out = run("params", dump("wrong_grid_step.json", bad), "--spec", PROBLEM_PATH)
add("params 变异不满足设备步进必命中", rc == 1 and violation(out, "步进"), out)
bad = copy.deepcopy(BASE); bad["parameters"][0]["unit"] = "K"
rc, out = run("params", dump("wrong_parameter_unit.json", bad), "--spec", PROBLEM_PATH)
add("params 变异摄氏度开尔文混用必命中", rc == 1 and violation(out, "单位"), out)

# verify: content addressing and exact quotes
rc, out = run("verify", GOOD, "--source-root", FIX)
add("verify 正向五处定位零误杀", rc == 0 and out.get("verified_evidence") == 5, out)
bad = copy.deepcopy(BASE); bad["judgments"][0]["evidence"][0]["quote"] = "50"
rc, out = run("verify", dump("wrong_recommendation_quote.json", bad), "--source-root", FIX)
add("verify 变异引文与字段值不符必命中", rc == 1 and err(out, "quote"), out)
bad = copy.deepcopy(BASE); bad["response_metrics"][0]["evidence"][0]["location"] = "#/measurements/missing"
rc, out = run("verify", dump("wrong_metric_pointer.json", bad), "--source-root", FIX)
add("verify 变异响应口径定位失效必命中", rc == 1 and err(out, "定位失败"), out)
bad = copy.deepcopy(BASE); bad["sources"][0]["sha256"] = "0" * 64
rc, out = run("verify", dump("source_hash_mismatch.json", bad), "--source-root", FIX)
add("verify 变异输入版本篡改必命中", rc == 1 and err(out, "SHA-256"), out)

# gain: same case/input/permissions, measured objective fields
baseline = copy.deepcopy(BASE); baseline["response_metrics"] = []; baseline["exception_register"] = []
BASELINE = dump("baseline.json", baseline)
GAIN = os.path.join(TMP, "with_gain.json")
rc, out = run("gain", BASELINE, GOOD, "--out", GAIN)
add("gain 正向同条件质量对照零误杀", rc == 0 and out.get("gain", {}).get("quality", {}).get("skill_feasible_recommendation") == 1, out)
rc, checked = run("audit", GAIN)
add("gain 产物回读契约仍通过", rc == 0 and checked.get("ok"), checked)
wrong = copy.deepcopy(BASE); wrong["input_digest"] = "c" * 64
rc, out = run("gain", BASELINE, dump("wrong_input.json", wrong), "--out", os.path.join(TMP, "wrong_gain.json"))
add("gain 变异不同输入拒绝比较", rc == 2 and "input_digest" in out.get("error", ""), out)
wrong = copy.deepcopy(BASE); wrong["permissions_digest"] = "d" * 64
rc, out = run("gain", BASELINE, dump("wrong_permission.json", wrong), "--out", os.path.join(TMP, "wrong_gain2.json"))
add("gain 变异不同权限拒绝比较", rc == 2 and "permissions_digest" in out.get("error", ""), out)

passed = sum(ok for _, ok, _ in CHECKS)
for name, ok, detail in CHECKS:
    print(("PASS" if ok else "FAIL"), name, ("| " + detail[:500] if not ok else ""))
print("total %d/%d" % (passed, len(CHECKS)))
sys.exit(0 if passed == len(CHECKS) else 1)
