#!/usr/bin/env python3
"""review_tool 自测：引文核验(误报抑制)、分面覆盖、交付校验；正向零误杀 + 变异必命中。"""
import json, os, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL = os.path.join(HERE, "..", "scripts", "review_tool.py")
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


TEXT = "我们在 45 例样本中观察到显著差异。统计分析采用双因素方差分析，未报告效应量。参考文献 [12] 的结论与本文明述相反。"
ISSUES = [
    {"id": "P1", "category": "statistics", "severity": "major",
     "location": "结果 第2段", "quote": "统计分析采用双因素方差分析，未报告效应量",
     "claim": "统计报告缺效应量与置信区间", "fix": "补充效应量与 95% CI"},
    {"id": "P2", "category": "citation", "severity": "critical",
     "location": "讨论 第1段", "quote": "参考文献 [12] 的结论与本文明述相反",
     "claim": "引用支持与本文论断冲突", "fix": "核对 [12] 原文并改写论断"},
    {"id": "P3", "category": "fact", "severity": "minor",
     "location": "引言 第3段", "quote": "该机制在 1990 年已被证实",
     "claim": "该引文不在原文中（误报测试）", "fix": "若不存在应删除"},
]


def add(n, c, d=""):
    checks.append((n, c, d))


txt = os.path.join(TMP, "manuscript.txt")
open(txt, "w", encoding="utf-8").write(TEXT)

# 1) 有原文：P3 的 quote 不存在 -> 必须被抓出（误报抑制）
rc, d = run("verify", dump("i1.json", {"issues": ISSUES}), "--text", txt)
add("verify:引文不在原文中被抓出", rc == 1 and len(d.get("quote_not_in_source", [])) == 1
    and d["quote_not_in_source"][0]["id"] == "P3", str(d)[:180])

# 2) 无原文：只做重复检测，全部可核验 -> 通过
rc, d = run("verify", dump("i1b.json", {"issues": ISSUES[:2]}))
add("verify:无原文时零误杀", rc == 0 and d.get("ok"), str(d)[:150])

# 3) 重复问题检测
dup = ISSUES[:1] + [dict(ISSUES[0], id="P1dup")]
rc, d = run("verify", dump("i2.json", {"issues": dup}))
add("verify:重复问题检出", len(d.get("duplicates", [])) == 1, str(d.get("duplicates"))[:120])

# 4) summary 覆盖缺口
rc, d = run("summary", dump("i3.json", {"issues": ISSUES}))
add("summary:未覆盖类别被列出", rc == 0 and "design" in d.get("unchecked_categories", []),
    str(d.get("unchecked_categories")))

# 5) summary 六类全覆盖
full = [dict(ISSUES[0], id="C%d" % i, category=c) for i, c in enumerate(
    ["fact", "citation", "design", "statistics", "argument", "compliance"])]
rc, d = run("summary", dump("i4.json", {"issues": full}))
add("summary:六类全覆盖 ratio=1", rc == 0 and d.get("category_coverage") == 1.0, str(d.get("category_coverage")))

# 5b) logic_check：判对三件事（引文逐字 + 定位精确到句 + 建议可执行）
rc, d = run("logic_check", dump("i5.json", {"issues": ISSUES[:2]}), "--text", txt)
add("logic_check:合规零误杀", rc == 0 and d.get("ok"), str(d)[:150])

bad = json.loads(json.dumps(ISSUES[:1])); bad[0]["location"] = "第三章"
rc, d = run("logic_check", dump("i5a.json", {"issues": bad}), "--text", txt)
add("logic_check:定位只给章节名->被抓", rc == 1 and d.get("imprecise_location"), str(d.get("imprecise_location"))[:120])

bad = json.loads(json.dumps(ISSUES[:1])); bad[0]["fix"] = "改进论证"
rc, d = run("logic_check", dump("i5b.json", {"issues": bad}), "--text", txt)
add("logic_check:建议空泛->被抓", rc == 1 and d.get("unactionable_fix"), str(d.get("unactionable_fix"))[:120])

bad = json.loads(json.dumps(ISSUES[:1])); bad[0]["quote"] = "原文里没有这句话"
rc, d = run("logic_check", dump("i5c.json", {"issues": bad}), "--text", txt)
add("logic_check:引文不在原文->被抓", rc == 1 and d.get("quote_not_in_source"), str(d.get("quote_not_in_source"))[:120])

BASE = {"case_id": "c1", "status": "issues", "manuscript_version": "v1.2-2026-11-20",
        "issues": ISSUES[:2], "checked_scope": {"did": ["statistics", "citation"], "not_checked": ["design"]},
        "gain": {"baseline_f1": 0.51, "skill_f1": 0.78, "false_positive_rate": 0.06},
        "unchecked": ["未获取补充材料"], "sources": ["manuscript v1.2"], "uncertainty": [], "change_log": []}

# 6) schema 正向
rc, d = run("schema", dump("r1.json", BASE))
add("schema正向:合规零误杀", rc == 0 and d.get("ok"), str(d.get("errors"))[:150])

# 7) schema 变异：category 非法
bad = json.loads(json.dumps(BASE)); bad["issues"][0]["category"] = "typo"
rc, d = run("schema", dump("r2.json", bad))
add("schema变异:category非法->失败", rc == 1, str(d.get("errors"))[:120])

# 8) schema 变异：缺稿件版本
bad = json.loads(json.dumps(BASE)); bad.pop("manuscript_version")
rc, d = run("schema", dump("r3.json", bad))
add("schema变异:缺manuscript_version->失败", rc == 1 and any("manuscript_version" in e for e in d.get("errors", [])),
    str(d.get("errors"))[:120])

# 9) schema 变异：severity 非法
bad = json.loads(json.dumps(BASE)); bad["issues"][0]["severity"] = "high"
rc, d = run("schema", dump("r4.json", bad))
add("schema变异:severity非法->失败", rc == 1, str(d.get("errors"))[:120])

# 10) schema 变异：问题缺原文定位
bad = json.loads(json.dumps(BASE)); bad["issues"][0].pop("location")
rc, d = run("schema", dump("r5.json", bad))
add("schema变异:缺location->失败", rc == 1 and any("location" in e for e in d.get("errors", [])),
    str(d.get("errors"))[:120])

ok = sum(1 for _, c, _ in checks if c)
for n, c, dd in checks:
    print(("PASS" if c else "FAIL"), n, ("| " + dd if not c else ""))
print("total %d/%d" % (ok, len(checks)))
sys.exit(0 if ok == len(checks) else 1)
