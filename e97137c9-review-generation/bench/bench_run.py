#!/usr/bin/env python3
"""syn_tool 自测：论断-引用回路、主题覆盖、交付校验；正向零误杀 + 变异必命中。"""
import json, os, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL = os.path.join(HERE, "..", "scripts", "syn_tool.py")
TMP = tempfile.mkdtemp()
checks = []


def run(*a):
    r = subprocess.run([sys.executable, TOOL, *a], capture_output=True, text=True)
    try:
        return r.returncode, json.loads(r.stdout)
    except Exception:
        return r.returncode, {"raw": r.stdout[:150]}


def dump(n, o):
    p = os.path.join(TMP, n)
    json.dump(o, open(p, "w", encoding="utf-8"), ensure_ascii=False)
    return p


def add(n, c, d=""):
    checks.append((n, c, d))


GOOD = {"case_id": "c1", "status": "issues",
        "screening_criteria": [{"criterion": "纳入原始研究", "judgement": "对象匹配"}],
        "records": [{"id": "R1", "title": "A"}, {"id": "R2", "title": "B"}],
        "included": [{"id": "R1", "title": "A", "screening_reason": "对象匹配"}],
        "claims": [{"id": "C1", "text": "机制X", "theme": "机制",
                    "citations": [{"record_id": "R1", "location": "结果第2段"}]},
                   {"id": "C2", "text": "背景Y", "theme": "背景",
                    "citations": [{"record_id": "R2", "location": "引言"}]}],
        "themes": [{"name": "机制"}, {"name": "背景"}],
        "counts": {"included": 1, "excluded": 1, "records_raw": 2},
        "gain": {}, "unchecked": [], "sources": [], "uncertainty": [], "change_log": []}

rc, d = run("cite_check", dump("g.json", GOOD))
add("cite正向:论断引用闭合", rc == 0 and d.get("ok"), str(d)[:150])

bad = json.loads(json.dumps(GOOD)); bad["claims"][0]["citations"] = []
rc, d = run("cite_check", dump("b1.json", bad))
add("cite变异:论断无引用被抓", rc == 1 and d.get("uncited_claims"), str(d.get("uncited_claims"))[:120])

bad = json.loads(json.dumps(GOOD)); bad["claims"][0]["citations"] = [{"record_id": "R9", "location": "p1"}]
rc, d = run("cite_check", dump("b2.json", bad))
add("cite变异:悬空引用被抓", rc == 1 and d.get("dangling_citations"), str(d.get("dangling_citations"))[:120])

bad = json.loads(json.dumps(GOOD)); bad["claims"][0]["citations"] = [{"record_id": "R1"}]
rc, d = run("cite_check", dump("b3.json", bad))
add("cite变异:引用缺定位被抓", rc == 1 and any("location" in e for e in d.get("errors", [])), str(d.get("errors"))[:120])

rc, d = run("theme_check", dump("g.json", GOOD))
add("theme正向:主题均有论断", rc == 0 and d.get("ok"), str(d)[:150])

bad = json.loads(json.dumps(GOOD)); bad["themes"].append({"name": "方法"})
rc, d = run("theme_check", dump("b4.json", bad))
add("theme变异:主题无论断被抓", rc == 1 and "方法" in d.get("themes_without_claims", []), str(d.get("themes_without_claims")))

bad = json.loads(json.dumps(GOOD)); bad["claims"][0]["citations"] = []
rc, d = run("theme_check", dump("b5.json", bad))
add("theme变异:主题无带引用论断被抓", rc == 1 and d.get("themes_without_cited_claim"), str(d.get("themes_without_cited_claim")))

rc, d = run("schema", dump("g.json", GOOD))
add("schema正向:合规零误杀", rc == 0 and d.get("ok"), str(d.get("errors"))[:150])

bad = json.loads(json.dumps(GOOD)); bad.pop("screening_criteria")
rc, d = run("schema", dump("b6.json", bad))
add("schema变异:缺筛选标准->失败", rc == 1, str(d.get("errors"))[:120])

bad = json.loads(json.dumps(GOOD)); bad["counts"]["excluded"] = 99
rc, d = run("schema", dump("b7.json", bad))
add("schema变异:计数矛盾->失败", rc == 1, str(d.get("errors"))[:120])

ok = sum(1 for _, c, _ in checks if c)
for n, c, dd in checks:
    print(("PASS" if c else "FAIL"), n, ("| " + dd if not c else ""))
print("total %d/%d" % (ok, len(checks)))
sys.exit(0 if ok == len(checks) else 1)
