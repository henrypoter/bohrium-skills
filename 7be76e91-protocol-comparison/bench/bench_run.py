#!/usr/bin/env python3
"""exp_tool 自测：六要素覆盖、参数自洽、设备量程核验、交付校验。"""
import json, os, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL = os.path.join(HERE, "..", "scripts", "exp_tool.py")
TMP = tempfile.mkdtemp()
checks = []


def run(*a):
    r = subprocess.run([sys.executable, TOOL, *a], capture_output=True, text=True)
    try:
        return r.returncode, json.loads(r.stdout)
    except Exception:
        return r.returncode, {"raw": r.stdout[:200]}


def dump(name, obj):
    p = os.path.join(TMP, name)
    json.dump(obj, open(p, "w", encoding="utf-8"), ensure_ascii=False)
    return p


def add(n, c, d=""):
    checks.append((n, c, d))


BASE = {
    "case_id": "c1", "status": "issues", "plan_version": "plan-v1.0",
    "research_goal": {"objective": "测药物A对细胞增殖的剂量效应",
                      "hypothesis": "药物A 在 10-100 uM 内剂量依赖抑制增殖", "constraints": ["预算5万"]},
    "variables": [{"id": "V1", "name": "药物A终浓度", "type": "independent",
                   "operational_definition": "培养液终浓度", "unit": "uM", "range": "0-100"}],
    "controls": [{"id": "C1", "type": "negative", "purpose": "溶剂对照", "confounder_excluded": "DMSO 溶剂效应"}],
    "steps": [{"id": "S1", "action": "铺板", "equipment": "96孔板", "material": "细胞悬液",
               "duration": "0.5h", "parameter_range": "5000细胞/孔"}],
    "resources": {"equipment": ["酶标仪"], "materials": ["CCK-8"], "sample": "细胞株X",
                  "time_estimate": "2周", "cost_estimate": "1.2万"},
    "parameters": [{"name": "temperature", "value": 75, "unit": "C", "min": 20, "max": 90},
                   {"name": "dose", "value": 50, "unit": "uM", "min": 0, "max": 100}],
    "risks": [{"id": "R1", "failure_mode": "无信号", "trigger": "吸光度<0.1",
               "consequence": "数据不可用", "mitigation": "复孔并重复三次", "stop_rule": "三次仍无信号则停"}],
    "judgments": [{"id": "J1", "claim": "选 CCK-8", "evidence": "线性范围覆盖", "source": "手册 p12",
                   "confidence": "high"}],
    "expert_confirmation": ["溶解度需实验员确认"],
    "gain": {"baseline_completeness": 0.6, "skill_completeness": 0.95, "rework_rounds_saved": 1},
    "unchecked": [], "sources": ["设备手册 p12"], "uncertainty": [], "change_log": [],
}
SPEC = {"limits": {"temperature": {"min": 4, "max": 80, "unit": "C"},
                   "dose": {"min": 0, "max": 200, "unit": "uM"}}}

# 1) 六要素齐备
rc, d = run("check", dump("p1.json", BASE))
add("check:六要素齐备", rc == 0 and not d.get("missing_elements"), str(d.get("missing_elements")))

# 2) 缺风险要素
bad = json.loads(json.dumps(BASE)); bad["risks"] = []
rc, d = run("check", dump("p2.json", bad))
add("check:缺风险要素被列出", rc == 1 and "风险和异常" in d.get("missing_elements", []), str(d.get("missing_elements")))

# 3) 参数越出自述区间
bad = json.loads(json.dumps(BASE)); bad["parameters"][1]["value"] = 150
rc, d = run("check", dump("p3.json", bad))
add("check:参数越自述区间", rc == 1 and any("高于自述上限" in e for e in d.get("errors", [])), str(d.get("errors"))[:120])

# 4) 设备量程内
rc, d = run("params", dump("p1.json", BASE), "--spec", dump("spec.json", SPEC))
add("params:量程内通过", rc == 0 and d.get("ok"), str(d.get("violations"))[:140])

# 5) 超设备上限
bad = json.loads(json.dumps(BASE)); bad["parameters"][0]["value"] = 95; bad["parameters"][0]["max"] = 120
rc, d = run("params", dump("p4.json", bad), "--spec", os.path.join(TMP, "spec.json"))
add("params:超设备上限被抓", rc == 1 and any("上限" in v["issue"] for v in d.get("violations", [])), str(d.get("violations"))[:140])

# 6) 单位不一致
bad = json.loads(json.dumps(BASE)); bad["parameters"][0]["unit"] = "K"
rc, d = run("params", dump("p5.json", bad), "--spec", os.path.join(TMP, "spec.json"))
add("params:单位不一致被抓", rc == 1 and any("单位" in v["issue"] for v in d.get("violations", [])), str(d.get("violations"))[:140])

# 7) 未声明限值的参数
bad = json.loads(json.dumps(BASE)); bad["parameters"].append({"name": "pressure", "value": 1, "unit": "bar"})
rc, d = run("params", dump("p6.json", bad), "--spec", os.path.join(TMP, "spec.json"))
add("params:未声明限值须提示补来源", rc == 1 and any("未声明" in v["issue"] for v in d.get("violations", [])), str(d.get("violations"))[:140])

# 8) schema 正向
rc, d = run("schema", dump("p1b.json", BASE))
add("schema正向:合规零误杀", rc == 0 and d.get("ok"), str(d.get("errors"))[:150])

# 9) schema 变异：缺方案版本
bad = json.loads(json.dumps(BASE)); bad.pop("plan_version")
rc, d = run("schema", dump("p7.json", bad))
add("schema变异:缺plan_version->失败", rc == 1 and any("plan_version" in e for e in d.get("errors", [])), str(d.get("errors"))[:120])

# 10) schema 变异：缺专家确认
bad = json.loads(json.dumps(BASE)); bad.pop("expert_confirmation")
rc, d = run("schema", dump("p8.json", bad))
add("schema变异:缺expert_confirmation->失败", rc == 1, str(d.get("errors"))[:120])

ok = sum(1 for _, c, _ in checks if c)
for n, c, dd in checks:
    print(("PASS" if c else "FAIL"), n, ("| " + dd if not c else ""))
print("total %d/%d" % (ok, len(checks)))
sys.exit(0 if ok == len(checks) else 1)
