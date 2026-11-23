#!/usr/bin/env python3
"""annotation_tool 自测：锚点核验、笔记支撑、关联依据、版本归并、可复现契约；正向零误杀 + 变异必命中。"""
import json, os, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL = os.path.join(HERE, "..", "scripts", "annotation_tool.py")
TMP = tempfile.mkdtemp()
checks = []


def run(*a):
    r = subprocess.run([sys.executable, TOOL, *a], capture_output=True, text=True)
    try:
        return r.returncode, json.loads(r.stdout)
    except Exception:
        return r.returncode, {"raw": r.stdout[:150]}


def dump(n, o):
    p = os.path.join(TMP, n); json.dump(o, open(p, "w", encoding="utf-8"), ensure_ascii=False); return p


def add(n, c, d=""):
    checks.append((n, c, d))


SRC = "我们在45例样本中观察到显著差异。机制研究表明X蛋白起关键作用。"
srcp = os.path.join(TMP, "src.txt"); open(srcp, "w", encoding="utf-8").write(SRC)

ANN = {"annotations": [
    {"id": "A1", "type": "highlight", "source_file": "paper.pdf", "page": 3, "color": "yellow",
     "quote": "我们在45例样本中观察到显著差异", "note": "样本量关键"},
    {"id": "A2", "type": "margin", "source_file": "paper.pdf", "page": 5,
     "quote": "机制研究表明X蛋白起关键作用", "note": "机制"}]}

rc, d = run("anchor_check", dump("a.json", ANN), "--text", srcp)
add("anchor正向:锚点都在原文", rc == 0 and d.get("ok"), str(d)[:150])

bad = json.loads(json.dumps(ANN)); bad["annotations"][0]["quote"] = "原文里没有这句"
rc, d = run("anchor_check", dump("a1.json", bad), "--text", srcp)
add("anchor变异:锚点错位被抓", rc == 1 and d.get("anchor_not_in_source"), str(d.get("anchor_not_in_source"))[:120])

bad = json.loads(json.dumps(ANN)); bad["annotations"][0]["type"] = "note"
rc, d = run("anchor_check", dump("a2.json", bad), "--text", srcp)
add("anchor变异:类型混同被抓", rc == 1 and d.get("type_invalid_or_mixed"), str(d.get("type_invalid_or_mixed")))

bad = json.loads(json.dumps(ANN)); bad["annotations"][0].pop("page")
rc, d = run("anchor_check", dump("a3.json", bad), "--text", srcp)
add("anchor变异:缺页码被抓", rc == 1 and any(m.get("field") == "page" for m in d.get("missing_field", [])), str(d.get("missing_field")))

NOTE = {"notes": [
    {"id": "N1", "kind": "conclusion", "claim": "X蛋白起关键作用",
     "support": [{"annotation_id": "A2", "quote": "机制研究表明X蛋白起关键作用", "location": "p5"}]}]}
rc, d = run("note_check", dump("n.json", NOTE))
add("note正向:论断有支撑", rc == 0 and d.get("ok"), str(d)[:150])

bad = json.loads(json.dumps(NOTE)); bad["notes"][0]["support"] = []
rc, d = run("note_check", dump("n1.json", bad))
add("note变异:摘抄(无支撑)被抓", rc == 1 and d.get("notes_without_support"), str(d.get("notes_without_support")))

LINK = {"links": [{"from": "N1", "to": "N2", "relation": "supports", "basis": "两条证据独立指向同一结论"}]}
rc, d = run("link_check", dump("l.json", LINK))
add("link正向:关联有依据", rc == 0 and d.get("ok"), str(d)[:150])

bad = json.loads(json.dumps(LINK)); bad["links"][0]["basis"] = "都提到X"
rc, d = run("link_check", dump("l1.json", bad))
add("link变异:关键词误连被抓", rc == 1 and d.get("links_keyword_only"), str(d.get("links_keyword_only")))

bad = json.loads(json.dumps(LINK)); bad["links"][0]["basis"] = ""
rc, d = run("link_check", dump("l2.json", bad))
add("link变异:无依据被抓", rc == 1 and d.get("links_without_basis"), str(d.get("links_without_basis")))

FILES = {"files": [{"path": "a.pdf", "sha256": "h1"}, {"path": "a_copy.pdf", "sha256": "h1"},
                   {"path": "b.pdf", "sha256": "h2"}]}
rc, d = run("version_check", dump("f.json", FILES))
add("version正向:重复归并", rc == 0 and d.get("n_duplicate_groups") == 1, str(d)[:150])

bad = json.loads(json.dumps(FILES)); bad["files"][0].pop("sha256")
rc, d = run("version_check", dump("f1.json", bad))
add("version变异:缺哈希被抓", rc == 1 and d.get("files_without_hash"), str(d.get("files_without_hash")))

RES = {"case_id": "c1", "status": "issues", "script_version": "annotate-v1.0",
       "sources": [{"file": "paper.pdf", "sha256": "h1"}], "annotations": ANN["annotations"],
       "notes": NOTE["notes"], "links": LINK["links"], "counts": {}, "skipped": [], "conflicts": [],
       "gain": {}, "unchecked": [], "uncertainty": [], "change_log": []}
rc, d = run("schema", dump("r.json", RES))
add("schema正向:合规零误杀", rc == 0 and d.get("ok"), str(d.get("errors")))

bad = json.loads(json.dumps(RES)); bad["sources"][0].pop("sha256")
rc, d = run("schema", dump("r1.json", bad))
add("schema变异:缺文件哈希->失败", rc == 1, str(d.get("errors"))[:120])

ok = sum(1 for _, c, _ in checks if c)
for n, c, dd in checks:
    print(("PASS" if c else "FAIL"), n, ("| " + dd if not c else ""))
print("total %d/%d" % (ok, len(checks)))
sys.exit(0 if ok == len(checks) else 1)
