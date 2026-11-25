#!/usr/bin/env python3
"""比较工具回归：每个命令均有合规零误杀与变异必命中。仅用合成 bench，不是官方案例答案。"""
import copy
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL = os.path.join(HERE, "..", "scripts", "exp_tool.py")
TMP = tempfile.mkdtemp(prefix="comparison-bench-")
with open(os.path.join(HERE, "fixtures", "good_result.json"), encoding="utf-8") as f:
    BASE = json.load(f)
SPEC = {
    "spec_version": "bench-spec-v1",
    "budget": {"amount": 1500, "currency": "CNY", "source_locator": "bench://budget#v1"},
    "time_window": {"value": 40, "unit": "h", "source_locator": "bench://window#v1"},
    "equipment": {"reader": {"available": True, "booking_status": "open", "source_locator": "bench://resources#reader"}},
    "materials": {"reagent": {"available": True, "lead_time": 2, "unit": "h", "source_locator": "bench://resources#reagent"}},
    "limits": {
        "temperature": {"min": 4, "max": 40, "unit": "C", "source_locator": "bench://limits#temperature"},
        "dose": {"min": 0, "max": 200, "unit": "uM", "source_locator": "bench://limits#dose"}
    }
}
checks = []


def dump(name, obj):
    path = os.path.join(TMP, name)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False)
    return path


def run(*args):
    result = subprocess.run([sys.executable, TOOL, *args], capture_output=True, text=True)
    try:
        payload = json.loads(result.stdout)
    except Exception:
        payload = {"raw": result.stdout[:200], "stderr": result.stderr[:200]}
    return result.returncode, payload


def add(name, condition, detail=""):
    checks.append((name, bool(condition), str(detail)[:300]))


def mutant():
    return copy.deepcopy(BASE)


def has_errors(payload, text):
    return any(text in x for x in payload.get("errors", []))


def has_violation(payload, kind):
    return any(x.get("type") == kind for x in payload.get("violations", []))


# 原有 check/params：保留正向并强化风险、参数窗口。
rc, d = run("check", dump("check-good.json", BASE))
add("check正向:六要素与风险替代路径零误杀", rc == 0 and d.get("ok"), d)
bad = mutant(); bad["risks"] = []
rc, d = run("check", dump("check-no-risk.json", bad))
add("check变异:缺风险和异常必命中", rc == 1 and "风险和异常" in d.get("missing_elements", []), d)
bad = mutant(); bad["risks"][0].pop("alternative_path")
rc, d = run("check", dump("check-no-fallback.json", bad))
add("check变异:风险缺替代路径必命中", rc == 1 and has_errors(d, "alternative_path"), d)
bad = mutant(); bad["parameters"][1]["value"] = 150
rc, d = run("check", dump("check-self-range.json", bad))
add("check变异:参数越自述区间必命中", rc == 1 and has_errors(d, "高于自述上限"), d)
bad = mutant(); bad["parameters"][0]["min"] = 50; bad["parameters"][0]["max"] = 40
rc, d = run("check", dump("check-empty-window.json", bad))
add("check变异:参数窗口为空必命中", rc == 1 and has_errors(d, "min>max"), d)

rc, d = run("params", dump("params-good.json", BASE), "--spec", dump("spec.json", SPEC))
add("params正向:量程内零误杀", rc == 0 and d.get("ok"), d)
bad = mutant(); bad["parameters"][0]["value"] = 95; bad["parameters"][0]["max"] = 120
rc, d = run("params", dump("params-over.json", bad), "--spec", os.path.join(TMP, "spec.json"))
add("params变异:超设备上限必命中", rc == 1 and any("上限" in x["issue"] for x in d.get("violations", [])), d)
bad = mutant(); bad["parameters"][0]["unit"] = "K"
rc, d = run("params", dump("params-unit.json", bad), "--spec", os.path.join(TMP, "spec.json"))
add("params变异:单位不一致必命中", rc == 1 and any("单位" in x["issue"] for x in d.get("violations", [])), d)
bad = mutant(); bad["parameters"].append({"name": "pressure", "value": 1, "unit": "bar"})
rc, d = run("params", dump("params-unknown.json", bad), "--spec", os.path.join(TMP, "spec.json"))
add("params变异:未声明限值必命中", rc == 1 and any("未声明" in x["issue"] for x in d.get("violations", [])), d)

# compare：同口径、算术、淘汰规则、敏感性与全不可行恢复。
rc, d = run("compare", dump("compare-good.json", BASE))
add("compare正向:三候选同口径零误杀", rc == 0 and len(d.get("eligible_candidate_ids", [])) == 3, d)
bad = mutant(); bad["candidates"][1]["hard_constraints"][0]["status"] = "fail"
rc, d = run("compare", dump("compare-nonselected-fail.json", bad))
add("compare正向:未选候选失败不误伤可行选择", rc == 0 and d.get("eligible_candidate_ids") == ["P-A", "P-C"], d)
bad = mutant(); bad["candidates"][0]["cost_breakdown"]["total"] += 1
rc, d = run("compare", dump("compare-cost-sum.json", bad))
add("compare变异:成本分项和错误必命中", rc == 1 and has_errors(d, "cost_breakdown.total"), d)
bad = mutant(); bad["candidates"][0]["time_breakdown"]["total"] += 1
rc, d = run("compare", dump("compare-time-sum.json", bad))
add("compare变异:时间分项和错误必命中", rc == 1 and has_errors(d, "time_breakdown.total"), d)
bad = mutant(); bad["candidates"][0].pop("steps")
rc, d = run("compare", dump("compare-missing-field.json", bad))
add("compare变异:候选缺统一比较字段必命中", rc == 1 and has_errors(d, "缺可比字段 steps"), d)
bad = mutant(); bad["candidates"][0]["risks"][0].pop("alternative_path")
rc, d = run("compare", dump("compare-risk-fallback.json", bad))
add("compare变异:候选风险缺替代路径必命中", rc == 1 and has_errors(d, "alternative_path"), d)
bad = mutant(); bad["candidates"][0]["evidence"][0]["source_id"] = "UNKNOWN"
rc, d = run("compare", dump("compare-evidence-source.json", bad))
add("compare变异:候选证据未登记必命中", rc == 1 and has_errors(d, "未在 sources 登记"), d)
bad = mutant(); bad["candidates"][0]["hard_constraints"][0]["status"] = "unknown"
rc, d = run("compare", dump("compare-select-unknown.json", bad))
add("compare变异:选择unknown候选必拦截", rc == 1 and has_errors(d, "禁止放行"), d)
bad = mutant(); bad["selection"]["rejected"].pop(0)
rc, d = run("compare", dump("compare-reject.json", bad))
add("compare变异:漏舍弃理由必命中", rc == 1 and has_errors(d, "舍弃理由"), d)
bad = mutant(); bad["selection"]["sensitivity"] = []
rc, d = run("compare", dump("compare-sensitivity.json", bad))
add("compare变异:无结论翻转条件必命中", rc == 1 and has_errors(d, "sensitivity"), d)
bad = mutant(); bad["selection"]["selected_candidate_id"] = None
rc, d = run("compare", dump("compare-no-selection.json", bad))
add("compare变异:有可行候选却不选择必命中", rc == 1 and has_errors(d, "必须明确选择"), d)

all_bad = mutant()
for candidate in all_bad["candidates"]:
    candidate["hard_constraints"][0]["status"] = "fail"
all_bad["selection"]["selected_candidate_id"] = None
all_bad["selection"]["rejected"].insert(0, {"candidate_id": "P-A", "reason": "设备硬约束fail；当前无可执行路径"})
all_bad["status"] = "issues"
all_bad["recovery"] = {"status": "blocked", "action": "重新确认设备与预算后重跑，不强行选型", "decision_owner": "bench-owner"}
all_bad["exceptions"] = [{"type": "all_candidates_infeasible", "trigger": "3/3候选设备约束fail", "action": "补设备或改期并重算全矩阵", "impact": "当前不能选择", "decision_owner": "bench-owner", "status": "blocked"}]
rc, d = run("compare", dump("compare-all-blocked-valid.json", all_bad))
add("compare正向:全不可行诚实阻断不误杀", rc == 0 and d.get("eligible_candidate_ids") == [], d)
bad = copy.deepcopy(all_bad); bad["recovery"] = {"status": "not_blocked"}
rc, d = run("compare", dump("compare-all-no-recovery.json", bad))
add("compare变异:全不可行无恢复路径必命中", rc == 1 and has_errors(d, "recovery"), d)
bad = copy.deepcopy(all_bad); bad["selection"]["selected_candidate_id"] = "P-A"
rc, d = run("compare", dump("compare-all-force-select.json", bad))
add("compare变异:全不可行强行选择必命中", rc == 1 and has_errors(d, "必须为 null"), d)
bad = copy.deepcopy(all_bad); bad["exceptions"][0].pop("action")
rc, d = run("compare", dump("compare-all-no-action.json", bad))
add("compare变异:全不可行异常无action必命中", rc == 1 and has_errors(d, "all_candidates_infeasible"), d)

# feasibility：资源/价格/档期合同均显式输入，错误单位不隐式换算。
rc, d = run("feasibility", dump("feas-good.json", BASE), "--spec", os.path.join(TMP, "spec.json"))
add("feasibility正向:资源约束内零误杀", rc == 0 and all(x == "resource_checks_pass" for x in d.get("candidate_status", {}).values()), d)
for label, edit, kind in [
    ("设备不可得", lambda s: s["equipment"]["reader"].update(available=False), "equipment_unavailable"),
    ("设备排期满", lambda s: s["equipment"]["reader"].update(booking_status="full"), "equipment_unavailable"),
    ("耗材缺货", lambda s: s["materials"]["reagent"].update(available=False), "material_unavailable"),
    ("耗材超预算", lambda s: s["budget"].update(amount=950), "budget_exceeded"),
    ("时间窗冲突", lambda s: s["time_window"].update(value=21), "time_window_conflict"),
    ("货期超时间窗", lambda s: s["materials"]["reagent"].update(lead_time=50), "time_window_conflict"),
    ("缺设备参数", lambda s: s.update(equipment={}), "missing_input"),
    ("缺预算", lambda s: s.pop("budget"), "missing_input")
]:
    spec = copy.deepcopy(SPEC); edit(spec)
    rc, d = run("feasibility", dump("feas-" + str(len(checks)) + ".json", BASE), "--spec", dump("spec-" + str(len(checks)) + ".json", spec))
    add("feasibility变异:" + label + "必命中", rc == 1 and has_violation(d, kind), d)
bad = mutant(); bad["candidates"][0]["parameters"][0].update(value=45, min=45, max=50)
rc, d = run("feasibility", dump("feas-param-window.json", bad), "--spec", os.path.join(TMP, "spec.json"))
add("feasibility变异:参数窗口超量程必命中", rc == 1 and has_violation(d, "parameter_window_conflict"), d)
spec = copy.deepcopy(SPEC); spec["limits"]["temperature"]["max"] = 30
rc, d = run("feasibility", dump("feas-empty-window.json", BASE), "--spec", dump("spec-empty-window.json", spec))
add("feasibility变异:参数交集为空必命中", rc == 1 and has_violation(d, "parameter_window_conflict"), d)
rc, d = run("feasibility", dump("feas-all.json", BASE), "--spec", dump("spec-all.json", dict(copy.deepcopy(SPEC), equipment={"reader": {"available": False}})))
add("feasibility变异:全部不可行给恢复动作", rc == 1 and has_violation(d, "all_candidates_infeasible"), d)

# schema：定位与版本字段硬检查。
rc, d = run("schema", dump("schema-good.json", BASE))
add("schema正向:版本/来源/运行记录零误杀", rc == 0 and d.get("ok"), d)
for key in ("plan_version", "source_version", "input_id", "run_record", "sources", "expert_confirmation"):
    bad = mutant(); bad.pop(key)
    rc, d = run("schema", dump("schema-no-" + key + ".json", bad))
    add("schema变异:缺" + key + "必命中", rc == 1 and has_errors(d, key), d)
bad = mutant(); bad["sources"][0]["locator"] = ""
rc, d = run("schema", dump("schema-no-locator.json", bad))
add("schema变异:来源无定位必命中", rc == 1 and has_errors(d, "locator"), d)

passed = sum(1 for _, ok, _ in checks if ok)
for name, ok, detail in checks:
    print(("PASS" if ok else "FAIL"), name, ("| " + detail if not ok else ""))
print("total %d/%d" % (passed, len(checks)))
sys.exit(0 if passed == len(checks) else 1)
