#!/usr/bin/env python3
"""query_tool 自测：查询快照/SQL/金标准、字段字典、关联路径；正向零误杀 + 变异必命中。"""
import json, os, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL = os.path.join(HERE, "..", "scripts", "query_tool.py")
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
    "case_id": "c1", "status": "issues", "query_version": "v1",
    "queries": [{"id": "Q1", "snapshot": "snap-2026-11-20", "connection": {"permission": "read-only"},
                 "sql": "SELECT * FROM samples WHERE year=2025", "result": [{"n": 12}], "golden": {"n": 12}}],
    "field_dict": [{"field": "sample_status", "meaning": "样本状态(排除/纳入)", "range": "0/1"}],
    "joins": [{"left": "samples", "right": "assays", "on": "sample_id", "one_to_many": True}],
    "results": [], "gain": {}, "unchecked": [], "sources": [], "uncertainty": [], "change_log": []
}

rc, d = run("query_check", dump("g.json", GOOD))
add("query正向:合规零误杀", rc == 0 and d.get("ok"), str(d.get("errors"))[:150])

bad = json.loads(json.dumps(GOOD)); bad["queries"][0].pop("snapshot")
rc, d = run("query_check", dump("g1.json", bad))
add("query变异:缺快照->被抓", rc == 1 and any("snapshot" in e for e in d.get("errors", [])), str(d.get("errors"))[:150])

bad = json.loads(json.dumps(GOOD)); bad["queries"][0].pop("golden"); bad["queries"][0].pop("recheck", None)
rc, d = run("query_check", dump("g2.json", bad))
add("query变异:无金标准/复算->被抓", rc == 1 and any("golden" in e or "recheck" in e for e in d.get("errors", [])), str(d.get("errors"))[:150])

bad = json.loads(json.dumps(GOOD)); bad["field_dict"][0].pop("meaning")
rc, d = run("query_check", dump("g3.json", bad))
add("query变异:字段无含义->被抓", rc == 1 and any("meaning" in e for e in d.get("errors", [])), str(d.get("errors"))[:150])

bad = json.loads(json.dumps(GOOD)); bad["joins"][0].pop("on")
rc, d = run("query_check", dump("g4.json", bad))
add("query变异:关联无连接键->被抓", rc == 1 and any("on" in e for e in d.get("errors", [])), str(d.get("errors"))[:150])

rc, d = run("schema", dump("s.json", GOOD))
add("schema正向:合规", rc == 0 and d.get("ok"), str(d.get("errors"))[:150])

ok = sum(1 for _, c, _ in checks if c)
for n, c, dd in checks:
    print(("PASS" if c else "FAIL"), n, ("| " + dd if not c else ""))
print("total %d/%d" % (ok, len(checks)))
sys.exit(0 if ok == len(checks) else 1)
