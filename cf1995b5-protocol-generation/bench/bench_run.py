#!/usr/bin/env python3
"""生成/优化工具回归：正向零误杀，科学字段与异常变异必命中；仅用合成 bench。"""
import copy
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL = os.path.join(HERE, "..", "scripts", "exp_tool.py")
TMP = tempfile.mkdtemp(prefix="generation-bench-")
with open(os.path.join(HERE, "fixtures", "good_result.json"), encoding="utf-8") as f:
    BASE = json.load(f)
SPEC = {
    "spec_version": "bench-spec-v1",
    "budget": {"amount": 2000, "currency": "CNY", "source_locator": "bench://budget#v1"},
    "time_window": {"value": 40, "unit": "h", "source_locator": "bench://window#v1"},
    "equipment": {"reader-open": {"available": True, "booking_status": "open", "source_locator": "bench://resources#reader"}},
    "materials": {"reagent-instock": {"available": True, "lead_time": 2, "unit": "h", "source_locator": "bench://resources#reagent"}},
    "parameter_costs": {"dose": {"fixed_other_cost": 0, "cost_per_unit": 10, "currency": "CNY", "source_locator": "bench://parameter-cost#dose"}},
    "limits": {
        "temperature": {"min": 4, "max": 40, "unit": "C", "source_locator": "bench://limits#temperature"},
        "dose": {"min": 0, "max": 80, "unit": "uM", "source_locator": "bench://limits#dose"}
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


# check：六要素与可执行风险。
rc, d = run("check", dump("check-good.json", BASE))
add("check正向:六要素/风险替代路径零误杀", rc == 0 and d.get("ok"), d)
bad = mutant(); bad["risks"] = []
rc, d = run("check", dump("check-no-risk.json", bad))
add("check变异:缺风险和异常必命中", rc == 1 and "风险和异常" in d.get("missing_elements", []), d)
for key in ("trigger", "consequence", "mitigation", "stop_rule", "alternative_path"):
    bad = mutant(); bad["risks"][0].pop(key)
    rc, d = run("check", dump("check-risk-" + key + ".json", bad))
    add("check变异:风险缺" + key + "必命中", rc == 1 and has_errors(d, key), d)
bad = mutant(); bad["variables"][0].pop("measurement_method")
rc, d = run("check", dump("check-no-method.json", bad))
add("check变异:变量无测量方式必命中", rc == 1 and has_errors(d, "measurement_method"), d)
bad = mutant(); bad["parameters"][1]["value"] = 150
rc, d = run("check", dump("check-range.json", bad))
add("check变异:参数越自述区间必命中", rc == 1 and has_errors(d, "高于自述上限"), d)
bad = mutant(); bad["judgments"][0].pop("source_locator")
rc, d = run("check", dump("check-judgment-source.json", bad))
add("check变异:判断无来源定位必命中", rc == 1 and has_errors(d, "source_locator"), d)

# params：设备与材料允许范围硬闸。
rc, d = run("params", dump("params-good.json", BASE), "--spec", dump("spec.json", SPEC))
add("params正向:量程内零误杀", rc == 0 and d.get("ok"), d)
bad = mutant(); bad["parameters"][0]["value"] = 95; bad["parameters"][0]["max"] = 120
rc, d = run("params", dump("params-over.json", bad), "--spec", os.path.join(TMP, "spec.json"))
add("params变异:超设备上限必命中", rc == 1 and any("允许范围" in x["issue"] for x in d.get("violations", [])), d)
bad = mutant(); bad["parameters"][0]["unit"] = "K"
rc, d = run("params", dump("params-unit.json", bad), "--spec", os.path.join(TMP, "spec.json"))
add("params变异:单位不一致必命中", rc == 1 and any("单位" in x["issue"] for x in d.get("violations", [])), d)
bad = mutant(); bad["parameters"].append({"name": "pressure", "value": 1, "unit": "bar", "min": 0, "max": 2, "source": "bench", "source_locator": "bench://p"})
rc, d = run("params", dump("params-unknown.json", bad), "--spec", os.path.join(TMP, "spec.json"))
add("params变异:未声明限值必命中", rc == 1 and any("未声明" in x["issue"] for x in d.get("violations", [])), d)

# controls：不机械要求某一种对照，而按目标声明的需求检查反向覆盖。
rc, d = run("controls", dump("controls-good.json", BASE))
add("controls正向:目标反推对照零误杀", rc == 0 and d.get("requirements") == 2, d)
bad = mutant(); bad["controls"].pop(0)
rc, d = run("controls", dump("controls-missing.json", bad))
add("controls变异:目标所需阴性对照未覆盖必命中", rc == 1 and has_errors(d, "CR1"), d)
bad = mutant(); bad["controls"][0]["type"] = "blank"
rc, d = run("controls", dump("controls-wrong-type.json", bad))
add("controls变异:对照类型与混杂不匹配必命中", rc == 1 and has_errors(d, "不符合所需类型"), d)
bad = mutant(); bad["controls"][0]["maps_requirement"] = "CR-X"
rc, d = run("controls", dump("controls-bad-map.json", bad))
add("controls变异:无效对照需求映射必命中", rc == 1 and has_errors(d, "未指向有效需求"), d)
bad = mutant(); bad["variables"].pop(1)
rc, d = run("controls", dump("controls-no-dependent.json", bad))
add("controls变异:缺因变量必命中", rc == 1 and has_errors(d, "dependent"), d)
bad = mutant(); bad["control_requirements"][0].pop("source_locator")
rc, d = run("controls", dump("controls-no-source.json", bad))
add("controls变异:对照依据无定位必命中", rc == 1 and has_errors(d, "source_locator"), d)

# optimize：输出可审计的裁剪域；任何科学参数改变都需人工确认。
rc, d = run("optimize", dump("opt-good.json", BASE), "--spec", os.path.join(TMP, "spec.json"))
add("optimize正向:资源内且预算/排期零误杀", rc == 0 and d.get("ok"), d)
add("optimize正向:量程裁剪保留来源和确认标记", rc == 0 and any(x.get("parameter") == "dose" and x.get("allowed_range") == [0, 80] and x.get("requires_confirmation") for x in d.get("clipped_parameter_domains", [])), d)
spec = copy.deepcopy(SPEC); spec["parameter_costs"]["dose"]["cost_per_unit"] = 50
rc, d = run("optimize", dump("opt-budget-param.json", BASE), "--spec", dump("spec-budget-param.json", spec))
add("optimize变异:预算反推剂量上限必命中", rc == 1 and has_violation(d, "budget_exceeded") and any(x.get("parameter") == "dose" and x.get("allowed_range") == [0, 40] and x.get("budget_max") == 40 for x in d.get("clipped_parameter_domains", [])), d)
bad = mutant(); bad["resources"]["cost_breakdown"]["total"] += 1
rc, d = run("optimize", dump("opt-cost-sum.json", bad), "--spec", os.path.join(TMP, "spec.json"))
add("optimize变异:成本算术错误必命中", rc == 1 and has_errors(d, "cost_breakdown.total"), d)
bad = mutant(); bad["resources"]["time_breakdown"]["total"] += 1
rc, d = run("optimize", dump("opt-time-sum.json", bad), "--spec", os.path.join(TMP, "spec.json"))
add("optimize变异:时间算术错误必命中", rc == 1 and has_errors(d, "time_breakdown.total"), d)
for label, edit, kind in [
    ("耗材超预算", lambda s: s["budget"].update(amount=1000), "budget_exceeded"),
    ("时间窗与样本量冲突", lambda s: s["time_window"].update(value=20), "time_window_conflict"),
    ("设备不可得", lambda s: s["equipment"]["reader-open"].update(available=False), "equipment_unavailable"),
    ("设备排期满", lambda s: s["equipment"]["reader-open"].update(booking_status="full"), "equipment_unavailable"),
    ("试剂缺货", lambda s: s["materials"]["reagent-instock"].update(available=False), "material_unavailable"),
    ("试剂货期超窗", lambda s: s["materials"]["reagent-instock"].update(lead_time=50), "time_window_conflict"),
    ("无设备参数", lambda s: s.update(equipment={}), "missing_input"),
    ("无预算", lambda s: s.pop("budget"), "missing_input"),
    ("无时间窗", lambda s: s.pop("time_window"), "missing_input")
]:
    spec = copy.deepcopy(SPEC); edit(spec)
    rc, d = run("optimize", dump("opt-" + str(len(checks)) + ".json", BASE), "--spec", dump("spec-" + str(len(checks)) + ".json", spec))
    add("optimize变异:" + label + "必命中", rc == 1 and has_violation(d, kind), d)
bad = mutant(); bad["resources"]["batches"] = 1
rc, d = run("optimize", dump("opt-batches.json", bad), "--spec", os.path.join(TMP, "spec.json"))
add("optimize变异:样本量所需批次数不足必命中", rc == 1 and any(x.get("minimum_batches") == 2 for x in d.get("violations", [])), d)
bad = mutant(); bad["resources"].pop("capacity_per_batch")
rc, d = run("optimize", dump("opt-no-capacity.json", bad), "--spec", os.path.join(TMP, "spec.json"))
add("optimize变异:排期字段缺失必命中", rc == 1 and has_violation(d, "missing_input"), d)
bad = mutant(); bad["parameters"][0].update(value=45, min=45, max=50)
rc, d = run("optimize", dump("opt-param-over.json", bad), "--spec", os.path.join(TMP, "spec.json"))
add("optimize变异:按设备量程拦截参数必命中", rc == 1 and has_violation(d, "parameter_window_conflict"), d)
spec = copy.deepcopy(SPEC); spec["limits"]["temperature"]["max"] = 30
rc, d = run("optimize", dump("opt-param-empty.json", BASE), "--spec", dump("spec-param-empty.json", spec))
add("optimize变异:参数可行域交集为空必命中", rc == 1 and has_violation(d, "parameter_window_conflict"), d)
spec = copy.deepcopy(SPEC); spec["budget"]["amount"] = 1000
bad = mutant(); bad["exceptions"] = [{"type": "budget_exceeded", "trigger": "1100>1000 CNY", "action": "复核非关键消耗", "alternative_path": "重报预算后重跑", "impact": "未解决前不可执行", "decision_owner": "bench-owner", "status": "blocked"}]
rc, d = run("optimize", dump("opt-exception-good.json", bad), "--spec", dump("spec-budget-low.json", spec))
add("optimize正向:完整异常记录不额外误报缺字段", rc == 1 and has_violation(d, "budget_exceeded") and not has_errors(d, "exceptions.budget_exceeded"), d)

# schema：输入、方案、来源、工具、变更五类版本可追溯。
rc, d = run("schema", dump("schema-good.json", BASE))
add("schema正向:版本/来源/运行记录零误杀", rc == 0 and d.get("ok"), d)
for key in ("plan_version", "source_version", "input_id", "run_record", "sources", "change_log"):
    bad = mutant(); bad.pop(key)
    rc, d = run("schema", dump("schema-no-" + key + ".json", bad))
    add("schema变异:缺" + key + "必命中", rc == 1 and has_errors(d, key), d)
bad = mutant(); bad["sources"][0]["locator"] = ""
rc, d = run("schema", dump("schema-no-locator.json", bad))
add("schema变异:来源无定位必命中", rc == 1 and has_errors(d, "locator"), d)
bad = mutant(); bad["change_log"] = ["初版"]
rc, d = run("schema", dump("schema-bad-log.json", bad))
add("schema变异:变更记录无版本原因必命中", rc == 1 and has_errors(d, "plan_version/change/reason"), d)

passed = sum(1 for _, ok, _ in checks if ok)
for name, ok, detail in checks:
    print(("PASS" if ok else "FAIL"), name, ("| " + detail if not ok else ""))
print("total %d/%d" % (passed, len(checks)))
sys.exit(0 if passed == len(checks) else 1)
