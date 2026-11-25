#!/usr/bin/env python3
"""tpl_audit 自测：模板反推、交叉引用联动、转换保真；正向零误杀 + 变异必命中。"""
import json, os, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL = os.path.join(HERE, "..", "scripts", "tpl_audit.py")
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


TPL = "学位论文格式规范\n摘要 不超过500字。关键词 3-5个。一级标题 黑体三号。三线表。页边距 上下2.54cm。行距 1.5倍。参考文献 GB/T 7714。"
tp = os.path.join(TMP, "tpl.txt"); open(tp, "w", encoding="utf-8").write(TPL)

rc, d = run("reverse", tp)
add("reverse:从模板反推出检查项", rc == 0 and d.get("n_requirements", 0) >= 5, str(d.get("n_requirements")))

DOC = {"figures": [{"number": "图1", "caption": "流程图"}, {"number": "图2", "caption": "结果"}],
       "cross_refs": [{"target_number": "图2", "text": "如图2所示"}]}
rc, d = run("xcheck", dump("d.json", DOC))
add("xcheck:编号-题注-引用三对齐零误杀", rc == 0 and d.get("ok"), str(d.get("errors"))[:120])

bad = json.loads(json.dumps(DOC)); bad["cross_refs"][0]["target_number"] = "图3"
rc, d = run("xcheck", dump("d1.json", bad))
add("xcheck:引用指向不存在图->被抓", rc == 1 and any("不存在" in e for e in d.get("errors", [])), str(d.get("errors"))[:120])

BEFORE = {"formulas": ["E=mc^2"], "footnotes": ["注1"], "captions": ["图1流程"], "field_codes": ["REF _Ref1"], "annotations": []}
AFTER = {"formulas": ["E=mc^2"], "footnotes": ["注1"], "captions": ["图1流程"], "field_codes": ["REF _Ref1"], "annotations": []}
rc, d = run("fidelity", dump("b.json", BEFORE), dump("a.json", AFTER))
add("fidelity:无丢失零误杀", rc == 0 and d.get("ok"), str(d.get("errors"))[:120])

lost = json.loads(json.dumps(AFTER)); lost["formulas"] = []
rc, d = run("fidelity", dump("b2.json", BEFORE), dump("a2.json", lost))
add("fidelity:公式转换丢失->被抓", rc == 1 and any("formulas" in e for e in d.get("errors", [])), str(d.get("errors"))[:120])

ok = sum(1 for _, c, _ in checks if c)
for n, c, dd in checks:
    print(("PASS" if c else "FAIL"), n, ("| " + dd if not c else ""))
print("total %d/%d" % (ok, len(checks)))
sys.exit(0 if ok == len(checks) else 1)
