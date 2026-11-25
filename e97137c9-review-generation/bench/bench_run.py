#!/usr/bin/env python3
"""syn_tool 自测：所有命令均有正向零误杀与变异必命中。"""
import copy
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
FIXTURES = os.path.join(HERE, "fixtures")
TOOL = os.path.join(HERE, "..", "scripts", "syn_tool.py")
TMP = tempfile.mkdtemp(prefix="review-bench-")
checks = []

with open(os.path.join(FIXTURES, "good_result.json"), encoding="utf-8") as f:
    GOOD = json.load(f)


def run(*args):
    result = subprocess.run([sys.executable, TOOL, *args], capture_output=True, text=True)
    try:
        return result.returncode, json.loads(result.stdout)
    except Exception:
        return result.returncode, {"raw": result.stdout[:200], "stderr": result.stderr[:200]}


def dump(name, value):
    path = os.path.join(TMP, name)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(value, f, ensure_ascii=False)
    return path


def add(name, condition, detail=""):
    checks.append((name, condition, detail))


def good_path():
    return dump("good.json", GOOD)


def mutation(name):
    value = copy.deepcopy(GOOD)
    return dump(name, value), value


# 先修改对象再落盘的辅助，避免测试误判共享 GOOD。
def changed(name, fn):
    value = copy.deepcopy(GOOD)
    fn(value)
    return dump(name, value)


path = good_path()
rc, out = run("cite_check", path)
add("cite 正向：引用回路零误杀", rc == 0 and out.get("ok"), str(out))
rc, out = run("cite_check", changed("cite-missing.json", lambda d: d["claims"][0].update(citations=[])))
add("cite 变异：无引用必命中", rc == 1 and out.get("uncited_claims"), str(out))
rc, out = run("cite_check", changed("cite-dangling.json", lambda d: d["claims"][0]["citations"][0].update(record_id="R9")))
add("cite 变异：悬空引用必命中", rc == 1 and out.get("dangling_citations"), str(out))
rc, out = run("cite_check", changed("cite-location.json", lambda d: d["claims"][0]["citations"][0].pop("location")))
add("cite 变异：缺定位必命中", rc == 1 and any("location" in e for e in out.get("errors", [])), str(out))

rc, out = run("theme_check", path)
add("theme 正向：主题覆盖零误杀", rc == 0 and out.get("ok"), str(out))
rc, out = run("theme_check", changed("theme-empty.json", lambda d: d["themes"].append({"name": "空主题"})))
add("theme 变异：空主题必命中", rc == 1 and "空主题" in out.get("themes_without_claims", []), str(out))
rc, out = run("theme_check", changed("theme-weak.json", lambda d: d["claims"][0].update(citations=[])))
add("theme 变异：主题无带引用论断必命中", rc == 1 and out.get("themes_without_cited_claim"), str(out))

rc, out = run("schema", path)
add("schema 正向：附加字段契约零误杀", rc == 0 and out.get("ok"), str(out))
rc, out = run("schema", changed("schema-required.json", lambda d: d.pop("screening_criteria")))
add("schema 变异：缺筛选标准必命中", rc == 1, str(out))
rc, out = run("schema", changed("schema-count.json", lambda d: d["counts"].update(excluded=99)))
add("schema 变异：计数矛盾必命中", rc == 1, str(out))

rc, out = run("screen_check", path)
add("screen 正向：判据与决定闭合零误杀", rc == 0 and out.get("ok"), str(out))
rc, out = run("screen_check", changed("screen-ref.json", lambda d: d["records"][0].update(criterion_ids=["S9"])))
add("screen 变异：未知判据引用必命中", rc == 1 and any("criterion_ids" in e for e in out.get("errors", [])), str(out))

rc, out = run("evidence_check", path)
add("evidence 正向：摘录与强度零误杀", rc == 0 and out.get("ok"), str(out))
rc, out = run("evidence_check", changed("evidence-quote.json", lambda d: d["claims"][0]["citations"][0].update(quote="")))
add("evidence 变异：缺原文摘录必命中", rc == 1 and any("quote" in e for e in out.get("errors", [])), str(out))

rc, out = run("grounding_check", path)
add("grounding 正向：主题/空白/冲突零误杀", rc == 0 and out.get("ok"), str(out))
rc, out = run("grounding_check", changed("grounding-gap.json", lambda d: d["research_gaps"][0].update(basis_claim_ids=["C9"])))
add("grounding 变异：无锚点研究空白必命中", rc == 1 and any("basis_claim_ids" in e for e in out.get("errors", [])), str(out))

prov_args = (path, "--input", os.path.join(FIXTURES, "case.json"), "--source-root", os.path.join(FIXTURES, "sources"))
rc, out = run("provenance_check", *prov_args)
add("provenance 正向：版本与哈希零误杀", rc == 0 and out.get("ok") and out.get("sources_checked") == 3, str(out))
bad_path = changed("provenance-hash.json", lambda d: d["sources"][0].update(sha256="0" * 64))
rc, out = run("provenance_check", bad_path, "--input", os.path.join(FIXTURES, "case.json"), "--source-root", os.path.join(FIXTURES, "sources"))
add("provenance 变异：来源哈希篡改必命中", rc == 1 and any("SHA-256" in e for e in out.get("errors", [])), str(out))

passed = sum(1 for _, condition, _ in checks if condition)
for name, condition, detail in checks:
    print(("PASS" if condition else "FAIL"), name, ("| " + detail if not condition else ""))
print("total %d/%d" % (passed, len(checks)))
sys.exit(0 if passed == len(checks) else 1)
