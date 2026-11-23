#!/usr/bin/env python3
"""write_tool 自测：论断-引用回路、数值论断引用覆盖、结构完整性、交付校验。"""
import json, os, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL = os.path.join(HERE, "..", "scripts", "write_tool.py")
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


GOOD = {"case_id": "c1", "status": "issues", "draft_version": "v1.0",
        "required_sections": ["introduction", "methods", "results", "references"],
        "sections": [
            {"id": "introduction", "content": "背景",
             "claims": [{"id": "cl1", "text": "该机制在 2020 年被报道",
                         "citations": [{"ref_id": "r1", "location": "引言"}]}]},
            {"id": "methods", "content": "方法", "claims": []},
            {"id": "results", "content": "结果",
             "claims": [{"id": "cl2", "text": "样本量 n=45",
                         "citations": [{"ref_id": "r2", "location": "表1"}]}]},
            {"id": "references", "content": "refs", "claims": []}],
        "references": [{"ref_id": "r1", "title": "Paper A", "doi": "10.1/a"},
                       {"ref_id": "r2", "title": "Paper B", "doi": "10.1/b"}],
        "gain": {}, "unchecked": [], "sources": [], "uncertainty": [], "change_log": []}

rc, d = run("claim_check", dump("g.json", GOOD))
add("claim正向:论断引用闭合", rc == 0 and d.get("ok"), str(d)[:150])

bad = json.loads(json.dumps(GOOD)); bad["sections"][2]["claims"] = [{"id": "cl3", "text": "样本量 n=45"}]
rc, d = run("claim_check", dump("b1.json", bad))
add("claim变异:数值论断无引用被抓", rc == 1 and d.get("numeric_claims_without_citation"), str(d.get("numeric_claims_without_citation"))[:140])

bad = json.loads(json.dumps(GOOD)); bad["sections"][0]["claims"][0]["citations"] = [{"ref_id": "r9", "location": "p1"}]
rc, d = run("claim_check", dump("b2.json", bad))
add("claim变异:悬空引用被抓", rc == 1 and d.get("dangling_citations"), str(d.get("dangling_citations"))[:120])

bad = json.loads(json.dumps(GOOD)); bad["sections"][0]["claims"][0]["citations"] = []
rc, d = run("claim_check", dump("b3.json", bad))
add("claim变异:论断无引用被抓", rc == 1 and d.get("uncited_claims"), str(d.get("uncited_claims"))[:120])

rc, d = run("structure", dump("g.json", GOOD))
add("structure正向:章节完整", rc == 0 and d.get("ok"), str(d)[:150])

bad = json.loads(json.dumps(GOOD)); bad["sections"] = [s for s in bad["sections"] if s["id"] != "methods"]
rc, d = run("structure", dump("b4.json", bad))
add("structure变异:缺章节被抓", rc == 1 and "methods" in d.get("missing_sections", []), str(d.get("missing_sections")))

bad = json.loads(json.dumps(GOOD)); bad["sections"][1]["content"] = "   "
rc, d = run("structure", dump("b5.json", bad))
add("structure变异:空章节被抓", rc == 1 and d.get("empty_sections"), str(d.get("empty_sections")))

rc, d = run("schema", dump("g.json", GOOD))
add("schema正向:合规零误杀", rc == 0 and d.get("ok"), str(d.get("errors"))[:150])

bad = json.loads(json.dumps(GOOD)); bad.pop("draft_version")
rc, d = run("schema", dump("b6.json", bad))
add("schema变异:缺draft_version->失败", rc == 1, str(d.get("errors"))[:120])

ok = sum(1 for _, c, _ in checks if c)
for n, c, dd in checks:
    print(("PASS" if c else "FAIL"), n, ("| " + dd if not c else ""))
print("total %d/%d" % (ok, len(checks)))
sys.exit(0 if ok == len(checks) else 1)
