#!/usr/bin/env python3
"""read_tool 自测：证据逐字回链、支持度分档、交付校验。"""
import json, os, re, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL = os.path.join(HERE, "..", "scripts", "read_tool.py")
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


SRC = "我们在45例样本中观察到显著差异。机制研究表明X蛋白起关键作用。"
srcp = os.path.join(TMP, "src.txt")
open(srcp, "w", encoding="utf-8").write(SRC)

GOOD = {"case_id": "c1", "status": "issues", "material_version": "v1",
        "answers": [{"id": "A1", "question": "样本量?", "answer": "45例", "support": "full",
                     "evidence": [{"quote": "我们在45例样本中观察到显著差异", "location": "结果第1段"}]},
                    {"id": "A2", "question": "机制?", "answer": "X蛋白", "support": "partial",
                     "evidence": [{"quote": "机制研究表明X蛋白起关键作用", "location": "讨论"}]}],
        "gain": {}, "unchecked": [], "sources": [], "uncertainty": [], "change_log": []}

rc, d = run("support_check", dump("g.json", GOOD), "--text", srcp)
add("support正向:引文都在原文", rc == 0 and d.get("ok"), str(d)[:150])

bad = json.loads(json.dumps(GOOD)); bad["answers"][0]["evidence"] = [{"quote": "这句话原文里没有", "location": "x"}]
rc, d = run("support_check", dump("b1.json", bad), "--text", srcp)
add("support变异:引文不在原文被抓", rc == 1 and d.get("quote_not_in_source"), str(d.get("quote_not_in_source"))[:140])

bad = json.loads(json.dumps(GOOD)); bad["answers"][0]["support"] = "high"
rc, d = run("support_check", dump("b2.json", bad), "--text", srcp)
add("support变异:支持度非法被抓", rc == 1 and d.get("missing_support_level"), str(d.get("missing_support_level")))

bad = json.loads(json.dumps(GOOD)); bad["answers"][0]["evidence"] = []
rc, d = run("support_check", dump("b3.json", bad), "--text", srcp)
add("support变异:full无证据被抓", rc == 1 and any("无证据" in e for e in d.get("errors", [])), str(d.get("errors"))[:140])

rc, d = run("support_check", dump("g.json", GOOD))
add("support无原文:仅结构校验零误杀", rc == 0 and d.get("ok"), str(d)[:150])

rc, d = run("schema", dump("g.json", GOOD))
add("schema正向:合规零误杀", rc == 0 and d.get("ok"), str(d.get("errors"))[:150])

bad = json.loads(json.dumps(GOOD)); bad.pop("material_version")
rc, d = run("schema", dump("b4.json", bad))
add("schema变异:缺material_version->失败", rc == 1, str(d.get("errors"))[:120])

ok = sum(1 for _, c, _ in checks if c)
for n, c, dd in checks:
    print(("PASS" if c else "FAIL"), n, ("| " + dd if not c else ""))
extra = subprocess.run([sys.executable, os.path.join(HERE, "bench_delivery_guard.py")],
                       capture_output=True, text=True)
print(extra.stdout, end="")
match = re.search(r"total (\d+)/(\d+)", extra.stdout)
extra_ok, extra_total = (int(match.group(1)), int(match.group(2))) if match else (0, 1)
print("combined total %d/%d" % (ok + extra_ok, len(checks) + extra_total))
sys.exit(0 if extra.returncode == 0 and ok == len(checks) and extra_ok == extra_total else 1)
