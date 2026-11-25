#!/usr/bin/env python3
"""正向零误杀 + 变异必命中的标准库回归测试；所有数据均为合成示例。"""
import copy
import hashlib
import json
import os
import sqlite3
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
TOOL = os.path.join(ROOT, "scripts", "data_tool.py")
TMP = tempfile.mkdtemp(prefix="code-exec-bench-")
CHECKS = []


def digest(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        h.update(f.read())
    return h.hexdigest()


def dump(name, obj):
    path = os.path.join(TMP, name)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2, allow_nan=False)
    return path


def run(*args):
    proc = subprocess.run([sys.executable, TOOL, *args], capture_output=True, text=True, timeout=15)
    try:
        data = json.loads(proc.stdout)
    except Exception:
        data = {"raw": proc.stdout[:300], "stderr": proc.stderr[:300]}
    return proc.returncode, data


def add(name, condition, detail=""):
    CHECKS.append((name, bool(condition), detail))


def write(name, content):
    path = os.path.join(TMP, name)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return path


CSV = write("analysis.csv", """id,grp,value,score
1,A,10,2
2,A,20,4
3,B,-999,6
4,B,40,bad
5,B,60,10
6,B,60,10
""")
CLEAN = write("clean.csv", """id,value
1,1.5
2,2.5
3,3.5
""")
HASH = digest(CSV)


def aggregate(aid, op, value, **kw):
    base = {"id": aid, "column": "value", "op": op, "value": value,
            "where": {"grp": "A"}}
    base.update(kw)
    return base


AGGS = [
    aggregate("a_sum", "sum", 30),
    aggregate("a_mean", "mean", 15),
    aggregate("a_count", "count", 2),
    aggregate("a_median", "median", 15),
    aggregate("a_sd", "stdev", 7.0710678118654755),
    aggregate("a_sem", "sem", 5),
    aggregate("b_sum", "sum", 160, where={"grp": "B"}, missing_values=["", "-999"],
              drop_duplicates=["id", "grp", "value"]),
    {"id": "all_rows", "column": None, "op": "row_count", "value": {"A": 2, "B": 4},
     "group_by": ["grp"]},
]
BASE = {
    "schema_version": "2.0.0", "skill_version": "2.0.0", "case_id": "SYNTHETIC-BENCH",
    "status": "issues",
    "questions": [{"id": "Q1", "answer": "示例：A 组均值为 15",
                   "evidence": [{"artifact": "analysis.csv", "location": "rows 1-2; column value",
                                 "quote": "1,A,10,2\n2,A,20,4", "sha256": HASH}]}],
    "aggregates": AGGS, "figures": [], "queries": [], "runs": [],
    "coverage": {k: {"status": "pass", "evidence": "bench"} for k in
                 ("cleaning", "statistics", "visualization", "execution", "query")},
    "data_dictionary": {"value": "合成测量值", "score": "含脏值的评分"},
    "lineage": {"snapshot": "synthetic-v1", "tables": ["analysis.csv"], "filters": ["grp=A"],
                "join_keys": [], "source_sha256": HASH, "command": "python3 analysis.py"},
    "gain": {"protocol_version": "1.0.0", "same_input": True, "same_permissions": True,
             "baseline": {"status": "not_checked", "quality": {}, "efficiency": {}, "evidence": []},
             "skill": {"status": "not_checked", "quality": {}, "efficiency": {}, "evidence": []}},
    "unchecked": [], "sources": [{"path": "analysis.csv", "sha256": HASH}],
    "uncertainty": ["合成样例，不代表正式案例"], "change_log": []
}

# profile：正向不产生脏值/重复/量级误报；变异逐项命中。
rc, out = run("profile", CLEAN)
add("profile 正向：干净数据零误杀", rc == 0 and out["rows"] == 3 and out["duplicate_rows"] == 0
    and all(c["dirty_numeric_count"] == 0 and c["outliers_iqr"] == 0 for c in out["columns"]), str(out)[:200])
rc, out = run("profile", CSV)
cols = {c["column"]: c for c in out.get("columns", [])}
add("profile 变异：脏数值必命中", rc == 0 and cols["score"]["dirty_numeric_count"] == 1, str(out)[:200])
duplicate_csv = write("duplicate.csv", "id,value\n1,2\n1,2\n")
rc, out = run("profile", duplicate_csv)
add("profile 变异：完全重复行必命中", rc == 0 and out["duplicate_rows"] == 1, str(out)[:200])
anomaly_csv = write("anomaly.csv", "value\n1\n1\n1\n1\n1\n1000\n")
rc, out = run("profile", anomaly_csv)
add("profile 变异：IQR 异常值必命中", rc == 0 and out["columns"][0]["outliers_iqr"] == 1, str(out)[:200])
header_only = write("empty.csv", "id,value\n")
rc, out = run("profile", header_only)
add("profile 变异：空表失败而非零行通过", rc == 1 and not out.get("ok", True))
dup_header = write("dup.csv", "id,id\n1,2\n")
rc, out = run("profile", dup_header)
add("profile 变异：重复列名失败", rc == 1 and "重复列名" in out.get("error", ""))

# recheck：八种聚合真实复算；每个静默错误均变异。
rc, out = run("recheck", dump("good.json", BASE), "--csv", CSV)
add("recheck 正向：8 种口径与分组完备", rc == 0 and out["checked"] == 9, str(out)[:400])
bad = copy.deepcopy(BASE); bad["aggregates"][0]["value"] = 31
rc, out = run("recheck", dump("wrong.json", bad), "--csv", CSV)
add("recheck 变异：篡改 sum 必命中", rc == 1 and any(e.get("id") == "a_sum" for e in out["mismatches"]))
bad = copy.deepcopy(BASE); bad["aggregates"] = [{"id": "dirty", "column": "score", "op": "mean", "value": 6}]
rc, out = run("recheck", dump("dirty.json", bad), "--csv", CSV)
add("recheck 变异：脏数值不得静默排除", rc == 1 and "脏数值" in str(out["mismatches"]))
bad = copy.deepcopy(BASE); bad["aggregates"] = [dict(bad["aggregates"][-1], value={"A": 2})]
rc, out = run("recheck", dump("groups.json", bad), "--csv", CSV)
add("recheck 变异：漏报 B 组必命中", rc == 1 and any("漏报" in e.get("error", "") for e in out["mismatches"]))
bad = copy.deepcopy(BASE); bad["aggregates"] = [aggregate("missing_col", "mean", 1, where={"absent": 1})]
rc, out = run("recheck", dump("missing-col.json", bad), "--csv", CSV)
add("recheck 变异：筛选缺列必命中", rc == 1 and "缺列" in str(out["mismatches"]))
bad = copy.deepcopy(BASE); bad["lineage"]["source_sha256"] = "0" * 64
rc, out = run("recheck", dump("hash.json", bad), "--csv", CSV)
add("recheck 变异：错输入快照必命中", rc == 1 and any("哈希" in e.get("error", "") for e in out["mismatches"]))
bad = copy.deepcopy(BASE); bad["aggregates"] = []
rc, out = run("recheck", dump("noaggs.json", bad), "--csv", CSV)
add("recheck 变异：无复算声明不通过", rc == 1 and "没有声明" in str(out["mismatches"]))
overflow_csv = write("overflow.csv", "value\n1e308\n1e308\n")
bad = copy.deepcopy(BASE); bad["aggregates"] = [{"id": "overflow", "column": "value", "op": "sum", "value": 0}]
bad["lineage"]["source_sha256"] = digest(overflow_csv)
rc, out = run("recheck", dump("overflow.json", bad), "--csv", overflow_csv)
add("recheck 变异：数值溢出必命中", rc == 1 and ("溢出" in str(out["mismatches"]) or "overflow" in str(out["mismatches"])))

# chartcheck：图中每个 series 与源表、图件哈希逐项核对。
svg = write("figure.svg", "<svg xmlns='http://www.w3.org/2000/svg'><title>synthetic</title></svg>\n")
fig_base = copy.deepcopy(BASE)
fig_base["figures"] = [{"id": "F1", "path": svg, "sha256": digest(svg),
                        "axes": {"x": {"label": "Group", "unit": "", "unit_required": False},
                                 "y": {"label": "Mean value", "unit": "mg/L", "unit_required": True}},
                        "legend": ["A"], "caption": "A 组 n=2；均值为 15。",
                        "series": [{"id": "F1-A", "column": "value", "op": "mean", "value": 15,
                                    "where": {"grp": "A"}}]}]
rc, out = run("chartcheck", dump("figure-good.json", fig_base), "--csv", CSV)
add("chartcheck 正向：图值/轴/单位/图注/哈希", rc == 0 and out["checked"] == 1, str(out)[:300])
bad = copy.deepcopy(fig_base); bad["figures"][0]["series"][0]["value"] = 14
rc, out = run("chartcheck", dump("figure-wrong.json", bad), "--csv", CSV)
add("chartcheck 变异：图值偏离源数据必命中", rc == 1 and any(e.get("figure") == "F1" for e in out["mismatches"]))
bad = copy.deepcopy(fig_base); bad["figures"][0]["axes"]["y"]["unit"] = ""
rc, out = run("chartcheck", dump("figure-unit.json", bad), "--csv", CSV)
add("chartcheck 变异：必需单位缺失必命中", rc == 1 and "缺单位" in str(out["mismatches"]))
bad = copy.deepcopy(fig_base); bad["figures"][0]["sha256"] = "0" * 64
rc, out = run("chartcheck", dump("figure-hash.json", bad), "--csv", CSV)
add("chartcheck 变异：图件哈希篡改必命中", rc == 1 and "图件 SHA256" in str(out["mismatches"]))

# run：真实执行、输入/代码/产物哈希、环境/种子、退出码、超时、缺产物。
child = write("child.py", """import json, random, sys
random.seed(int(sys.argv[1]))
out = {'random': random.random(), 'input': open(sys.argv[2], encoding='utf-8').read().splitlines()[1]}
with open(sys.argv[3], 'w', encoding='utf-8') as f: json.dump(out, f)
print(json.dumps(out))
""")
artifact = os.path.join(TMP, "child-output.json")
runlog = os.path.join(TMP, "run.json")
rc, out = run("run", child, "--log", runlog, "--input", CLEAN, "--require", artifact,
              "--seed", "7", "--", "7", CLEAN, artifact)
with open(runlog, encoding="utf-8") as f:
    log = json.load(f)
add("run 正向：真执行并留全血缘", rc == 0 and log["exit_status"] == 0 and log["seed"] == 7
    and len(log["inputs"]) == 1 and len(log["artifacts"]) == 1 and len(log["code_sha256"]) == 64, str(out)[:300])
rc, out = run("run", child, "--log", runlog, "--", "7", CLEAN, artifact)
add("run 变异：同名日志禁止覆盖失败现场", rc == 1 and "禁止覆盖" in out.get("error", ""))
failing = write("fail.py", "import sys\nprint('deliberate failure', file=sys.stderr)\nsys.exit(3)\n")
rc, out = run("run", failing, "--log", os.path.join(TMP, "fail-log.json"))
add("run 变异：子进程退出码原样保留", rc == 3 and out["exit_status"] == 3 and not out["ok"])
missing_art = os.path.join(TMP, "not-created.txt")
rc, out = run("run", child, "--log", os.path.join(TMP, "missing-art-log.json"), "--require", missing_art,
              "--", "7", CLEAN, artifact)
add("run 变异：必需产物缺失必失败", rc == 1 and out["errors"], str(out)[:200])
sleepy = write("sleepy.py", "import time\ntime.sleep(2)\n")
rc, out = run("run", sleepy, "--log", os.path.join(TMP, "timeout-log.json"), "--timeout", "0.05")
add("run 变异：超时保留失败现场", rc == 124 and out["timed_out"])
rc, out = run("run", child, "--log", os.path.join(TMP, "missing-input-log.json"),
              "--input", os.path.join(TMP, "absent.csv"), "--", "7", CLEAN, artifact)
add("run 变异：输入缺失不得执行", rc == 1 and out["errors"] and out["exit_status"] is None)
rc, out = run("run", child, "--log", os.path.join(TMP, "dependency-log.json"),
              "--package", "package-that-does-not-exist-bench", "--", "7", CLEAN, artifact)
add("run 变异：依赖缺失前置终止并记录", rc == 1 and any(e.get("type") == "dependency_missing" for e in out["errors"]))

# sqlcheck：只读实跑并逐单元格比较，空查询显式告警，DML/错结果命中。
db = os.path.join(TMP, "bench.sqlite")
con = sqlite3.connect(db)
con.execute("create table t(id integer primary key, grp text, value real)")
con.executemany("insert into t values(?,?,?)", [(1, "A", 10), (2, "A", 20), (3, "B", 40)])
con.commit(); con.close()
sql_base = copy.deepcopy(BASE)
sql_base["queries"] = [{"id": "Q", "sql": "SELECT grp, SUM(value) AS total FROM t GROUP BY grp ORDER BY grp",
                        "columns": ["grp", "total"], "rows": [["A", 30], ["B", 40]]}]
rc, out = run("sqlcheck", dump("sql-good.json", sql_base), "--db", db)
add("sqlcheck 正向：SQLite 实跑逐行一致", rc == 0 and out["queries"][0]["row_count"] == 2, str(out)[:300])
bad = copy.deepcopy(sql_base); bad["queries"][0]["rows"][0][1] = 31
rc, out = run("sqlcheck", dump("sql-wrong.json", bad), "--db", db)
add("sqlcheck 变异：查询单元格篡改必命中", rc == 1 and "单元格" in str(out["mismatches"]))
empty = copy.deepcopy(sql_base); empty["queries"] = [{"id": "EMPTY", "sql": "SELECT id FROM t WHERE id>99",
                                                       "columns": ["id"], "rows": []}]
rc, out = run("sqlcheck", dump("sql-empty.json", empty), "--db", db)
add("sqlcheck 正向：真空结果不误杀且标记", rc == 0 and out["queries"][0]["empty_result"])
dml = copy.deepcopy(sql_base); dml["queries"] = [{"id": "DML", "sql": "DELETE FROM t", "columns": [], "rows": []}]
rc, out = run("sqlcheck", dump("sql-dml.json", dml), "--db", db)
add("sqlcheck 变异：非只读 SELECT 必拒绝", rc == 1 and "仅允许" in str(out["mismatches"]))
missing_table = copy.deepcopy(sql_base); missing_table["queries"][0]["sql"] = "SELECT * FROM absent"
rc, out = run("sqlcheck", dump("sql-missing.json", missing_table), "--db", db)
add("sqlcheck 变异：查询失败保留 SQLite 原因", rc == 1 and "absent" in str(out["mismatches"]))

# schema：正向及版本、证据定位、not_checked 理由、公平对照变异。
rc, out = run("schema", dump("schema-good.json", BASE))
add("schema 正向：完整契约零误杀", rc == 0, str(out)[:300])
for name, mutate, needle in [
    ("缺版本字段", lambda x: x.pop("schema_version"), "schema_version"),
    ("证据无定位", lambda x: x["questions"][0]["evidence"][0].pop("location"), "location"),
    ("证据无引文和哈希", lambda x: (x["questions"][0]["evidence"][0].pop("quote"),
                                      x["questions"][0]["evidence"][0].pop("sha256")), "quote"),
    ("not_checked无理由", lambda x: x["coverage"].update(visualization={"status": "not_checked"}), "reason"),
    ("对照输入不同", lambda x: x["gain"].update(same_input=False), "same_input"),
    ("已测增益无证据", lambda x: x["gain"]["baseline"].update(status="measured"), "evidence"),
]:
    bad = copy.deepcopy(BASE); mutate(bad)
    rc, out = run("schema", dump("schema-%d.json" % len(CHECKS), bad))
    add("schema 变异：" + name, rc == 1 and needle in str(out["errors"]), str(out)[:200])

# 交付的最小示例也接受同一套 schema 与 recheck，而非只测临时对象。
fixture_result = os.path.join(HERE, "fixtures", "good_result.json")
fixture_csv = os.path.join(HERE, "fixtures", "sample_data.csv")
rc1, out1 = run("schema", fixture_result)
rc2, out2 = run("recheck", fixture_result, "--csv", fixture_csv)
add("发布夹具：good_result 通过 schema+recheck", rc1 == 0 and rc2 == 0,
    str({"schema": out1, "recheck": out2})[:400])

passed = sum(ok for _, ok, _ in CHECKS)
for name, ok, detail in CHECKS:
    print(("PASS" if ok else "FAIL"), name, ("| " + detail if not ok else ""))
print("total %d/%d" % (passed, len(CHECKS)))
sys.exit(0 if passed == len(CHECKS) else 1)
