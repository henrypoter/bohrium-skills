#!/usr/bin/env python3
"""file_tool 自测：哈希去重、版本链、目录规范核验、交付校验。"""
import json, os, shutil, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL = os.path.join(HERE, "..", "scripts", "file_tool.py")
TMP = tempfile.mkdtemp()
checks = []


def run(*a):
    r = subprocess.run([sys.executable, TOOL, *a], capture_output=True, text=True)
    try:
        return r.returncode, json.loads(r.stdout)
    except Exception:
        return r.returncode, {"raw": r.stdout[:200]}


def add(n, c, d=""):
    checks.append((n, c, d))


BATCH = os.path.join(TMP, "batch")
os.makedirs(os.path.join(BATCH, "data"), exist_ok=True)
open(os.path.join(BATCH, "report_v1.pdf"), "w").write("AAA")
open(os.path.join(BATCH, "report_v2.pdf"), "w").write("BBBB")
open(os.path.join(BATCH, "report_final.pdf"), "w").write("CCCCC")
open(os.path.join(BATCH, "a.txt"), "w").write("same-content")
open(os.path.join(BATCH, "a_copy.txt"), "w").write("same-content")
open(os.path.join(BATCH, "empty.txt"), "w").write("")
open(os.path.join(BATCH, "data", "raw.csv"), "w").write("x,y\n1,2\n")

# 1) 清单基础
rc, d = run("inventory", BATCH)
add("inventory:文件数与嵌套", rc == 0 and d.get("n_files") == 7, str(d.get("n_files")))

# 2) 哈希重复组
add("inventory:内容哈希重复组", len(d.get("duplicate_groups", [])) == 1
    and sorted(d["duplicate_groups"][0]["files"]) == ["a.txt", "a_copy.txt"],
    str(d.get("duplicate_groups"))[:160])

# 3) 版本链
add("inventory:版本链识别", any(len(v["files"]) == 3 for v in d.get("version_chains", [])),
    str(d.get("version_chains"))[:160])

# 4) 空文件
add("inventory:空文件列出", d.get("empty_files") == ["empty.txt"], str(d.get("empty_files")))

# 5) 目录规范通过
spec = {"path_patterns": ["^data/.+$", "^[^/]+$"], "required_meta": [],
        "manifest_csv": None}
sp = os.path.join(TMP, "spec.json")
json.dump(spec, open(sp, "w"), ensure_ascii=False)
rc, d = run("checkmap", BATCH, "--spec", sp)
add("checkmap:规范内零误报", rc == 0 and d.get("ok"), str(d)[:160])

# 6) 路径违规被抓
open(os.path.join(BATCH, "data", "deep", ), "w") if False else None
os.makedirs(os.path.join(BATCH, "misc"), exist_ok=True)
open(os.path.join(BATCH, "misc", "x.bin"), "w").write("z")
spec2 = {"path_patterns": ["^data/.+$", "^[^/]+$"], "required_meta": []}
sp2 = os.path.join(TMP, "spec2.json")
json.dump(spec2, open(sp2, "w"), ensure_ascii=False)
rc, d = run("checkmap", BATCH, "--spec", sp2)
add("checkmap:路径违规被抓", rc == 1 and "misc/x.bin" in d.get("path_violations", []),
    str(d.get("path_violations"))[:120])

BASE = {"case_id": "c1", "status": "issues", "directory_tree": {"data": ["raw.csv"]},
        "manifest": [{"path": "data/raw.csv", "sha256": "abc", "source": "raw", "version": "v1"}],
        "dedup": {"groups": 1}, "versions": {"report": ["report_v1.pdf", "report_v2.pdf"]},
        "operations": [{"action": "move", "src": "raw.csv", "dst": "data/raw.csv", "result": "ok"}],
        "gain": {"baseline_fill_rate": 0.6, "skill_fill_rate": 0.98},
        "unchecked": [], "sources": ["upload batch"], "uncertainty": [], "change_log": []}

# 7) schema 正向
rc, d = run("schema", json.dump(BASE, open(os.path.join(TMP, "r.json"), "w"), ensure_ascii=False) or os.path.join(TMP, "r.json"))
add("schema正向:合规零误杀", rc == 0 and d.get("ok"), str(d.get("errors"))[:150])

# 8) schema 变异：manifest 缺 sha256
bad = json.loads(json.dumps(BASE)); bad["manifest"][0].pop("sha256")
p = os.path.join(TMP, "r2.json"); json.dump(bad, open(p, "w"), ensure_ascii=False)
rc, d = run("schema", p)
add("schema变异:manifest缺sha256->失败", rc == 1 and any("sha256" in e for e in d.get("errors", [])),
    str(d.get("errors"))[:120])

# 9) schema 变异：操作缺 result
bad = json.loads(json.dumps(BASE)); bad["operations"][0].pop("result")
p = os.path.join(TMP, "r3.json"); json.dump(bad, open(p, "w"), ensure_ascii=False)
rc, d = run("schema", p)
add("schema变异:操作缺result->失败", rc == 1 and any("result" in e for e in d.get("errors", [])),
    str(d.get("errors"))[:120])

# 10) schema 变异：缺目录树
bad = json.loads(json.dumps(BASE)); bad.pop("directory_tree")
p = os.path.join(TMP, "r4.json"); json.dump(bad, open(p, "w"), ensure_ascii=False)
rc, d = run("schema", p)
add("schema变异:缺directory_tree->失败", rc == 1, str(d.get("errors"))[:120])

ok = sum(1 for _, c, _ in checks if c)
for n, c, dd in checks:
    print(("PASS" if c else "FAIL"), n, ("| " + dd if not c else ""))
print("total %d/%d" % (ok, len(checks)))
sys.exit(0 if ok == len(checks) else 1)
