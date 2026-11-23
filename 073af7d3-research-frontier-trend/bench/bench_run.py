#!/usr/bin/env python3
"""trend_tool 自测：趋势时间证据回路、空白证据、交付校验。"""
import json, os, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL = os.path.join(HERE, "..", "scripts", "trend_tool.py")
TMP = tempfile.mkdtemp()
checks = []


def run(*a):
    r = subprocess.run([sys.executable, TOOL, *a], capture_output=True, text=True)
    try:
        return r.returncode, json.loads(r.stdout)
    except Exception:
        return r.returncode, {"raw": r.stdout[:150]}


def dump(n, o):
    p = os.path.join(TMP, n); json.dump(o, open(p, "w", encoding="utf-8"), ensure_ascii=False); return p


def add(n, c, d=""):
    checks.append((n, c, d))


GOOD = {"case_id": "c1", "status": "issues", "analysis_version": "v1",
        "records": [{"id": "R1", "title": "A"}, {"id": "R2", "title": "B"}],
        "trends": [{"id": "T1", "text": "机制X上升", "year_range": "2018-2024",
                    "citations": [{"record_id": "R1", "location": "图2"}]}],
        "evolution": [{"stage": "早期", "period": "2018-2020"}, {"stage": "成熟", "period": "2021-2024"}],
        "gaps": [{"text": "无长期随访", "evidence": "排除证据:3库0命中"}],
        "representative_works": [{"period": "2020", "record_id": "R1"}, {"period": "2023", "record_id": "R2"}],
        "gain": {}, "unchecked": [], "sources": [], "uncertainty": [], "change_log": []}

rc, d = run("trend_check", dump("g.json", GOOD))
add("trend正向:时间证据闭合", rc == 0 and d.get("ok"), str(d)[:150])

bad = json.loads(json.dumps(GOOD)); bad["trends"][0].pop("year_range")
rc, d = run("trend_check", dump("b1.json", bad))
add("trend变异:缺时间被抓", rc == 1 and d.get("trends_without_time"), str(d.get("trends_without_time")))

bad = json.loads(json.dumps(GOOD)); bad["trends"][0]["citations"] = [{"record_id": "R9", "location": "p1"}]
rc, d = run("trend_check", dump("b2.json", bad))
add("trend变异:悬空引用被抓", rc == 1 and d.get("dangling_citations"), str(d.get("dangling_citations")))

bad = json.loads(json.dumps(GOOD)); bad["trends"][0]["citations"] = []
rc, d = run("trend_check", dump("b3.json", bad))
add("trend变异:趋势无引用被抓", rc == 1 and any("无引用" in e for e in d.get("errors", [])), str(d.get("errors")))

bad = json.loads(json.dumps(GOOD)); bad["gaps"][0].pop("evidence")
rc, d = run("trend_check", dump("b4.json", bad))
add("trend变异:空白无证据被抓", rc == 1 and any("排除证据" in e for e in d.get("errors", [])), str(d.get("errors")))

bad = json.loads(json.dumps(GOOD)); bad["evolution"][0].pop("stage")
rc, d = run("trend_check", dump("b5.json", bad))
add("trend变异:演化缺阶段被抓", rc == 1 and any("stage" in e for e in d.get("errors", [])), str(d.get("errors")))

rc, d = run("schema", dump("g.json", GOOD))
add("schema正向:合规零误杀", rc == 0 and d.get("ok"), str(d.get("errors")))

bad = json.loads(json.dumps(GOOD)); bad["representative_works"][0].pop("record_id")
rc, d = run("schema", dump("b6.json", bad))
add("schema变异:代表作缺record_id->失败", rc == 1, str(d.get("errors"))[:120])

ok = sum(1 for _, c, _ in checks if c)
for n, c, dd in checks:
    print(("PASS" if c else "FAIL"), n, ("| " + dd if not c else ""))
print("total %d/%d" % (ok, len(checks)))
sys.exit(0 if ok == len(checks) else 1)
