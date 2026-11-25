#!/usr/bin/env python3
"""interp_tool 自测：五段结构、异常维度绑定、原因可检验性排序、复核可执行；正向零误杀 + 变异必命中。"""
import json, os, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL = os.path.join(HERE, "..", "scripts", "interp_tool.py")
TMP = tempfile.mkdtemp()
checks = []


def run(*a):
    r = subprocess.run([sys.executable, TOOL, *a], capture_output=True, text=True)
    try:
        return r.returncode, json.loads(r.stdout)
    except Exception:
        return r.returncode, {"raw": r.stdout[:200]}


def dump(n, o):
    p = os.path.join(TMP, n); json.dump(o, open(p, "w", encoding="utf-8"), ensure_ascii=False); return p


def add(n, c, d=""):
    checks.append((n, c, d))


GOOD = {
    "case_id": "c1", "status": "issues", "analysis_version": "v1",
    "data_sources": [{"file": "exp1.csv", "field": "OD600", "threshold": "3σ", "version": "v2"}],
    "trends": [{"direction": "随浓度上升", "interval": "0-100μM", "control": "vehicle", "fitting": "logistic", "knee": "50μM", "deviation": "+15%"}],
    "anomalies": [{"dimension": "batch=3 通道B", "severity": "major", "threshold": "3σ", "deviation": "偏离对照 2.8σ", "evidence": "exp1.csv OD600"}],
    "causes": [{"candidate": "加样误差", "evidence_support": "同批复孔一致", "evidence_exclude": "非全局", "correlation_risk": "低", "testability": 3},
               {"candidate": "批次效应", "evidence_support": "跨批重现", "evidence_exclude": "单批", "correlation_risk": "中", "testability": 2}],
    "recheck_steps": [{"action": "回查 OD600 原始列", "target": "exp1.csv/OD600"}],
    "next_experiments": [{"change": "加 3 个复孔", "rationale": "区分加样误差与真差异"}],
    "unexplained": [], "gain": {}, "unchecked": [], "uncertainty": [], "change_log": []
}

rc, d = run("interp_check", dump("g.json", GOOD))
add("interp正向:五段合规零误杀", rc == 0 and d.get("ok"), str(d.get("errors"))[:150])

bad = json.loads(json.dumps(GOOD)); bad["anomalies"][0]["dimension"] = "某批数据"
rc, d = run("interp_check", dump("g1.json", bad))
add("interp变异:异常未绑定维度->被抓", rc == 1 and any("dimension" in e for e in d.get("errors", [])), str(d.get("errors"))[:150])

bad = json.loads(json.dumps(GOOD)); bad["anomalies"][0].pop("threshold")
rc, d = run("interp_check", dump("g2.json", bad))
add("interp变异:缺阈值->被抓", rc == 1 and any("threshold" in e for e in d.get("errors", [])), str(d.get("errors"))[:150])

bad = json.loads(json.dumps(GOOD)); bad["causes"][0]["testability"] = 1  # 破坏降序
rc, d = run("interp_check", dump("g3.json", bad))
add("interp变异:原因未按可检验性降序->被抓", rc == 1 and any("降序" in e for e in d.get("errors", [])), str(d.get("errors"))[:150])

bad = json.loads(json.dumps(GOOD)); bad["recheck_steps"][0].pop("target")
rc, d = run("interp_check", dump("g4.json", bad))
add("interp变异:复核无可执行目标->被抓", rc == 1 and any("target" in e for e in d.get("errors", [])), str(d.get("errors"))[:150])

rc, d = run("schema", dump("s.json", GOOD))
add("schema正向:合规", rc == 0 and d.get("ok"), str(d.get("errors"))[:150])

bad = json.loads(json.dumps(GOOD)); bad["data_sources"][0].pop("field")
rc, d = run("schema", dump("s1.json", bad))
add("schema变异:数据源缺字段->被抓", rc == 1, str(d.get("errors"))[:150])

ok = sum(1 for _, c, _ in checks if c)
for n, c, dd in checks:
    print(("PASS" if c else "FAIL"), n, ("| " + dd if not c else ""))
print("total %d/%d" % (ok, len(checks)))
sys.exit(0 if ok == len(checks) else 1)
