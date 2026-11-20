#!/usr/bin/env python3
"""search_tool v2 自测：四命令正向零误杀 + 六处变异必命中。"""
import json, os, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL = os.path.join(HERE, "..", "scripts", "search_tool.py")
FIX = os.path.join(HERE, "fixtures")
checks = []


def run(cmd, path):
    r = subprocess.run([sys.executable, TOOL, cmd, path], capture_output=True, text=True)
    try:
        return r.returncode, json.loads(r.stdout)
    except Exception:
        return r.returncode, {"raw": r.stdout[:200]}


def tmp_copy(mutate, name):
    d = json.load(open(os.path.join(FIX, "good_result.json"), encoding="utf-8"))
    mutate(d)
    p = os.path.join(tempfile.gettempdir(), name)
    json.dump(d, open(p, "w", encoding="utf-8"), ensure_ascii=False)
    return p


def add(name, cond, detail=""):
    checks.append((name, cond, detail))


# 1) dedup 正向：DOI 精确重复 1 组，且预印本/正式版近似候选被发现
rc, d = run("dedup", os.path.join(FIX, "records.json"))
near_pairs = {(n["a"], n["b"]) for n in d.get("near_duplicate_candidates", [])}
add("dedup正向:精确重复+近似候选", rc == 0 and d.get("exact_duplicate_groups") == 1
    and ("R1", "R3") in near_pairs, str(d)[:160])

# 2) dedup 变异：缺文件失败
rc, _ = run("dedup", os.path.join(FIX, "不存在.json"))
add("dedup变异:缺文件->失败", rc == 1, "rc=%d" % rc)

# 3) audit 正向：闭合通过
rc, d = run("audit", os.path.join(FIX, "good_result.json"))
add("audit正向:计数闭合零误杀", rc == 0 and d.get("ok"), str(d.get("errors"))[:120])

# 4) audit 变异1：少一条判定 -> 闭合失败
def m1(d):
    d["screening"].pop()
rc, d = run("audit", tmp_copy(m1, "a1.json"))
add("audit变异:少一条判定->不闭合", rc == 1 and any("筛选合计" in e for e in d.get("errors", [])), str(d.get("errors"))[:120])

# 5) audit 变异2：未知理由码
def m2(d):
    d["screening"][0]["reason_code"] = "E99"
rc, d = run("audit", tmp_copy(m2, "a2.json"))
add("audit变异:未知理由码->失败", rc == 1 and any("不在字典内" in e for e in d.get("errors", [])), str(d.get("errors"))[:120])

# 6) audit 变异3：纳入判定却用排除码（方向矛盾）
def m3(d):
    d["screening"][0]["reason_code"] = "E3"
rc, d = run("audit", tmp_copy(m3, "a3.json"))
add("audit变异:码族与方向矛盾->失败", rc == 1 and any("矛盾" in e for e in d.get("errors", [])), str(d.get("errors"))[:120])

# 7) agreement 正向：一致率/kappa/分歧条数
rc, d = run("agreement", os.path.join(FIX, "pairs.json"))
add("agreement正向:一致率与kappa",
    rc == 0 and abs(d.get("decision_agreement", 0) - 2 / 3) < 1e-3
    and abs(d.get("cohen_kappa", 0) - 1 / 3) < 1e-3 and len(d.get("disagreements", [])) == 3,
    str({k: d.get(k) for k in ("decision_agreement", "cohen_kappa")}))

# 8) agreement 变异：空 pairs 失败
p = os.path.join(tempfile.gettempdir(), "p0.json")
json.dump({"pairs": []}, open(p, "w"))
rc, _ = run("agreement", p)
add("agreement变异:空pairs->失败", rc == 1, "rc=%d" % rc)

# 9) schema 正向
rc, d = run("schema", os.path.join(FIX, "good_result.json"))
add("schema正向:合规结果零误杀", rc == 0 and d.get("ok"), str(d.get("errors"))[:120])

# 10) schema 变异：记录缺来源
def m4(d):
    d["records"][0].pop("source")
rc, d = run("schema", tmp_copy(m4, "s1.json"))
add("schema变异:记录缺source->失败", rc == 1 and any("source" in e for e in d.get("errors", [])), str(d.get("errors"))[:120])

ok = 0
for name, cond, detail in checks:
    print(("PASS" if cond else "FAIL"), name, ("| " + detail if not cond else ""))
    ok += 1 if cond else 0
print("total %d/%d" % (ok, len(checks)))
sys.exit(0 if ok == len(checks) else 1)
