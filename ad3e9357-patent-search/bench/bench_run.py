#!/usr/bin/env python3
"""专利专用五命令自测：正向零误杀 + 定向变异必命中。仅用标准库。"""
import copy
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL = os.path.join(HERE, "..", "scripts", "search_tool.py")
FIX = os.path.join(HERE, "fixtures")
checks = []


def run(cmd, path):
    r = subprocess.run([sys.executable, TOOL, cmd, path], capture_output=True, text=True)
    try:
        return r.returncode, json.loads(r.stdout)
    except Exception:
        return r.returncode, {"raw": r.stdout[:300], "stderr": r.stderr[:300]}


def fixture(name):
    return json.load(open(os.path.join(FIX, name), encoding="utf-8"))


def tmp_json(d, name):
    p = os.path.join(tempfile.gettempdir(), "patent-skill-" + name)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False)
    return p


def tmp_result(mutate, name):
    d = fixture("good_result.json")
    mutate(d)
    for s in d.get("sources", []):
        if s.get("path") == "source.json":
            s["path"] = os.path.join(FIX, "source.json")
    return tmp_json(d, name)


def add(name, cond, detail=""):
    checks.append((name, bool(cond), detail))


# normalize：角色与种类代码保留，非法输入不得静默修正。
rc, d = run("normalize", os.path.join(FIX, "records.json"))
r0 = d.get("records", [{}])[0].get("normalized", {})
add("normalize正向:三类号码与优先权规范化", rc == 0 and
    r0.get("publication_number") == "US1000000B2" and
    r0.get("application_number") == "US16123456" and
    r0.get("priority_numbers") == ["US62123456"], str(d)[:240])
bad = fixture("records.json")
bad["records"][0]["application_number"] = "not-a-number"
rc, d = run("normalize", tmp_json(bad, "bad-number.json"))
add("normalize变异:非法号码必报错", rc == 1 and not d.get("ok"), str(d)[:160])

# family：简单族要求相同优先权集合，扩展族允许共享任一优先权。
rc, d = run("family", os.path.join(FIX, "records.json"))
add("family正向:简单/扩展族分口径且非完整", rc == 0 and
    d.get("simple", [{}])[0].get("members") == ["P1", "P2"] and
    d.get("extended", [{}])[0].get("members") == ["P1", "P2"] and
    d.get("complete") is False and d.get("claim_scope_equal") is False, str(d)[:240])
bad = fixture("records.json")
bad["records"][0]["simple_family_id"] = "F1"
bad["records"][1]["simple_family_id"] = "F1"
bad["records"][1]["priority_numbers"] = ["EP18123456"]
rc, d = run("family", tmp_json(bad, "bad-family.json"))
add("family变异:同简单族优先权冲突必命中", rc == 1 and any("不一致" in e for e in d.get("errors", [])), str(d)[:180])

# status：当前状态只能来自当前官方核验；历史事件不自动变成有效结论。
rc, d = run("status", os.path.join(FIX, "legal.json"))
cases = {x["id"]: x for x in d.get("cases", [])}
add("status正向:官方/二手/冲突三分支", rc == 0 and
    cases.get("CURRENT", {}).get("current_status") == "granted" and
    cases.get("UNKNOWN", {}).get("current_status") == "unknown" and
    cases.get("CONFLICT", {}).get("verification") == "conflict", str(d)[:220])
bad = fixture("legal.json")
bad["cases"][0]["events"].append({"effective_date": "2020-01-02", "status": "expired", "source_id": "OFFICIAL2", "official": True})
rc, d = run("status", tmp_json(bad, "bad-status.json"))
add("status变异:最新官方事件冲突->unknown", rc == 0 and d["cases"][0]["current_status"] == "unknown" and d["cases"][0]["event_conflict"], str(d)[:180])

# gain：qrels 真算，权限或输入不同直接拒绝。
rc, d = run("gain", os.path.join(FIX, "gain.json"))
add("gain正向:P/R/nDCG与成本真算", rc == 0 and
    d["metrics"]["baseline"]["precision_at_k"] == 0.5 and
    d["metrics"]["skill"]["recall_at_k"] == 1.0 and
    abs(d["metrics"]["delta"]["ndcg_at_k"] - 0.8262346571) < 1e-8 and
    d["metrics"]["cost_saved"]["tool_calls"] == 2, str(d)[:240])
bad = fixture("gain.json")
bad["same_permissions"] = False
rc, d = run("gain", tmp_json(bad, "bad-gain.json"))
add("gain变异:权限不同拒绝计算增益", rc == 1 and any("same_permissions" in e for e in d.get("errors", [])), str(d)[:160])

# audit 正向：哈希、逐字引文、字段绑定、族重算、状态与计数全部通过。
rc, d = run("audit", os.path.join(FIX, "good_result.json"))
add("audit正向:完整证据闭环零误杀", rc == 0 and d.get("ok") and d.get("evidence_quotes_checked") == 6, str(d)[:260])

mutations = [
    ("quote", lambda d: d["records"][0]["evidence"][0].__setitem__("quote", "A fabricated quote."),
     "逐字回源", "audit变异:伪造引文必命中"),
    ("hash", lambda d: d["sources"][0].__setitem__("sha256", "0" * 64),
     "sha256", "audit变异:原始响应哈希变化必命中"),
    ("red", lambda d: d["sources"][0].__setitem__("access", "red"),
     "红色受限", "audit变异:受限原文展示必命中"),
    ("status", lambda d: d["legal_status"][0].__setitem__("current_status", "granted"),
     "非当前官方", "audit变异:无官方核验给当前状态必命中"),
    ("family-complete", lambda d: d["families"].__setitem__("complete", True),
     "完整同族", "audit变异:观察链接冒称完整同族必命中"),
    ("family-group", lambda d: d["families"]["simple"][0]["members"].pop(),
     "重算不一致", "audit变异:漏族成员必被重算命中"),
    ("counts", lambda d: d["counts"].__setitem__("raw", 1),
     "计数不闭合", "audit变异:原始计数不闭合必命中"),
    ("binding", lambda d: d["records"][0].__setitem__("title", "Fabricated title"),
     "与原始字段不符", "audit变异:元数据字段错配必命中"),
    ("claims", lambda d: d["claims"][1].__setitem__("scope_comparison", "equivalent"),
     "范围等同", "audit变异:推定权利要求等同必命中"),
    ("gain", lambda d: d.__setitem__("gain", {"mode": "local_qrels", "metrics": {"invented": 1}}),
     "同输入", "audit变异:无公平对照的增益必命中")
]
for name, mutate, needle, label in mutations:
    rc, d = run("audit", tmp_result(mutate, "mutation-" + name + ".json"))
    add(label, rc == 1 and any(needle in e for e in d.get("errors", [])), str(d.get("errors"))[:220])

ok = 0
for name, passed, detail in checks:
    print(("PASS" if passed else "FAIL"), name, ("| " + detail if not passed else ""))
    ok += int(passed)
print("total %d/%d" % (ok, len(checks)))
sys.exit(0 if ok == len(checks) else 1)
