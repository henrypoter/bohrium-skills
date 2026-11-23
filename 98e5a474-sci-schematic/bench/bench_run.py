#!/usr/bin/env python3
"""fig_tool 自测：SVG 可编辑性(文字未转曲)、元素-数据映射、交付校验。"""
import json, os, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL = os.path.join(HERE, "..", "scripts", "fig_tool.py")
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


SVG_OK = ('<svg xmlns="http://www.w3.org/2000/svg" width="400" height="300">'
          '<rect x="10" y="10" width="100" height="50" fill="red"/>'
          '<text x="20" y="40">对照组</text><circle cx="200" cy="100" r="30"/></svg>')
sp = os.path.join(TMP, "ok.svg"); open(sp, "w").write(SVG_OK)
rc, d = run("svg_check", sp)
add("svg正向:可编辑(含text)通过", rc == 0 and d.get("ok") and d.get("text_elements") == 1, str(d)[:150])

paths = "".join('<path d="M%d %d L%d %d"/>' % (i, i, i + 40, i + 40) for i in range(10, 120, 10))
SVG_PATH = '<svg xmlns="http://www.w3.org/2000/svg" width="400" height="300">%s</svg>' % paths
sp2 = os.path.join(TMP, "path.svg"); open(sp2, "w").write(SVG_PATH)
rc, d = run("svg_check", sp2)
add("svg变异:文字转曲被抓", rc == 1 and any("转曲" in e for e in d.get("errors", [])), str(d.get("errors"))[:140])

SVG_NODIM = '<svg xmlns="http://www.w3.org/2000/svg"><rect x="1" y="1" width="10" height="10"/><text x="2" y="5">t</text></svg>'
sp3 = os.path.join(TMP, "nodim.svg"); open(sp3, "w").write(SVG_NODIM)
rc, d = run("svg_check", sp3)
add("svg变异:缺尺寸被抓", rc == 1 and any("尺寸" in e or "viewBox" in e for e in d.get("errors", [])), str(d.get("errors"))[:140])

MAP = {"mapping": [{"element": "rect1", "source": "data.csv", "source_location": "A列"},
                   {"element": "text1", "source": "data.csv", "source_location": "标题"}]}
rc, d = run("element_map", dump("m.json", MAP))
add("map正向:元素均有来源", rc == 0 and d.get("ok"), str(d)[:150])

bad = json.loads(json.dumps(MAP)); bad["mapping"].append({"element": "rect2"})
rc, d = run("element_map", dump("b1.json", bad))
add("map变异:未映射元素被抓", rc == 1 and d.get("unmapped_elements"), str(d.get("unmapped_elements")))

bad = json.loads(json.dumps(MAP)); bad["mapping"][0].pop("source_location")
rc, d = run("element_map", dump("b2.json", bad))
add("map变异:缺来源定位被抓", rc == 1 and any("source_location" in e for e in d.get("errors", [])), str(d.get("errors"))[:140])

FIG = {"case_id": "c1", "status": "issues", "figure_version": "v1",
       "figures": [{"id": "F1", "svg": "f.svg", "png": "f.png", "figure_type": "schematic"}],
       "mapping": MAP["mapping"], "gain": {}, "unchecked": [], "sources": [], "uncertainty": [], "change_log": []}
rc, d = run("schema", dump("f.json", FIG))
add("schema正向:合规零误杀", rc == 0 and d.get("ok"), str(d.get("errors"))[:150])

bad = json.loads(json.dumps(FIG)); bad["figures"][0].pop("png")
rc, d = run("schema", dump("b3.json", bad))
add("schema变异:缺渲染PNG->失败", rc == 1, str(d.get("errors"))[:140])

ok = sum(1 for _, c, _ in checks if c)
for n, c, dd in checks:
    print(("PASS" if c else "FAIL"), n, ("| " + dd if not c else ""))
print("total %d/%d" % (ok, len(checks)))
sys.exit(0 if ok == len(checks) else 1)
