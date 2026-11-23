#!/usr/bin/env python3
"""data_tool 自测：数据画像(缺失/重复/异常值/量级不一致/脏数值) + 聚合复算 + 交付校验。"""
import json, os, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL = os.path.join(HERE, "..", "scripts", "data_tool.py")
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


CSV = """id,value,unit_mixed,score
1,10,1,12
2,20,5000,15
3,,300,N/A
4,30,7,18
1,10,1,12
5,1000,4,20
"""
csvp = os.path.join(TMP, "data.csv")
open(csvp, "w", encoding="utf-8").write(CSV)


def add(n, c, d=""):
    checks.append((n, c, d))


# 1) 画像：缺失/重复行
rc, d = run("profile", csvp)
cols = {c["column"]: c for c in d.get("columns", [])}
add("profile:缺失与重复行", rc == 0 and d.get("rows") == 6 and d.get("duplicate_rows") == 1
    and cols["value"]["missing"] == 1, str({k: d.get(k) for k in ("rows", "duplicate_rows")}))

# 2) 量级不一致告警
add("profile:量级不一致告警", "scale_warning" in cols["unit_mixed"], str(cols.get("unit_mixed"))[:140])

# 3) IQR 异常值
add("profile:异常值(IQR)检出", cols["value"].get("outliers_iqr", 0) >= 1, str(cols["value"].get("outlier_examples")))

# 4) 脏数值（N/A）
add("profile:脏数值计数", cols["score"].get("dirty_numeric_count") == 1, str(cols["score"])[:140])

BASE = {"case_id": "c1", "status": "issues",
        "questions": [{"id": "Q1", "answer": "value 合计 1070", "evidence": ["data.csv:value 列求和"]}],
        "aggregates": [{"column": "value", "op": "sum", "value": 1070},
                       {"column": "value", "op": "count", "value": 5},
                       {"column": "score", "op": "mean", "value": 15.4}],
        "data_dictionary": {"value": "测量值", "unit_mixed": "单位混用列", "score": "评分"},
        "lineage": {"snapshot": "snap-2026-11-20", "tables": ["data.csv"], "filters": []},
        "gain": {"baseline_accuracy": 0.55, "skill_accuracy": 0.9, "rework_rounds_saved": 2},
        "unchecked": [], "sources": ["data.csv"], "uncertainty": [], "change_log": []}

# 5) 复算一致
rc, d = run("recheck", dump("r.json", BASE), "--csv", csvp)
add("recheck:聚合可独立复算", rc == 0 and d.get("checked") == 3, str(d.get("mismatches"))[:160])

# 6) 复算发现不一致
bad = json.loads(json.dumps(BASE)); bad["aggregates"][0]["value"] = 1000
rc, d = run("recheck", dump("r2.json", bad), "--csv", csvp)
add("recheck:篡改数值被抓出", rc == 1 and len(d.get("mismatches", [])) == 1, str(d.get("mismatches"))[:160])

# 7) schema 正向
rc, d = run("schema", dump("s.json", BASE))
add("schema正向:合规零误杀", rc == 0 and d.get("ok"), str(d.get("errors"))[:150])

# 8) schema 变异：缺 lineage
bad = json.loads(json.dumps(BASE)); bad.pop("lineage")
rc, d = run("schema", dump("s2.json", bad))
add("schema变异:缺lineage->失败", rc == 1 and any("lineage" in e for e in d.get("errors", [])), str(d.get("errors"))[:120])

# 9) schema 变异：结论缺 evidence
bad = json.loads(json.dumps(BASE)); bad["questions"][0].pop("evidence")
rc, d = run("schema", dump("s3.json", bad))
add("schema变异:结论缺evidence->失败", rc == 1 and any("evidence" in e for e in d.get("errors", [])), str(d.get("errors"))[:120])

# 10) schema 变异：aggregate 缺 value
bad = json.loads(json.dumps(BASE)); bad["aggregates"][0].pop("value")
rc, d = run("schema", dump("s4.json", bad))
add("schema变异:aggregate缺value->失败", rc == 1, str(d.get("errors"))[:120])

ok = sum(1 for _, c, _ in checks if c)
for n, c, dd in checks:
    print(("PASS" if c else "FAIL"), n, ("| " + dd if not c else ""))
print("total %d/%d" % (ok, len(checks)))
sys.exit(0 if ok == len(checks) else 1)
