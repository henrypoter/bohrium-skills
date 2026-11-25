#!/usr/bin/env python3
"""End-to-end five-chart mapping/export bench plus deterministic map mutations."""
import copy
import importlib.util
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
TMP = tempfile.mkdtemp(prefix="mapping-bench-")
checks = []


def add(name, condition, detail=""):
    checks.append((name, bool(condition), detail))


def write(name, text):
    path = os.path.join(TMP, name)
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(text)
    return path


def dump(name, obj):
    return write(name, json.dumps(obj, ensure_ascii=False))


def run(*args):
    return subprocess.run([sys.executable, *args], cwd=ROOT, capture_output=True, text=True)


bar = write("bar.csv", "treatment,cell_line,mean_expr,sd,p_label\nDMSO,A549,0.02,0.05,ns\nDrugX,A549,1.18,0.11,*\nDMSO,HeLa,0.11,0.06,ns\nDrugX,HeLa,1.47,0.09,**\n")
line = write("line.csv", "time_h,dose,rel_viability,sem\n0,low,1.00,0.03\n2,low,0.92,0.04\n24,low,0.66,0.04\n0,high,1.00,0.02\n2,high,0.74,0.03\n24,high,0.31,0.03\n")
box = write("box.csv", "group,response\nA,1\nA,2\nA,3\nA,4\nA,5\nA,100\n")
heat = write("heat.csv", "gene,sample,expression\nTP53,S1,1.0\nTP53,S2,2.0\nEGFR,S1,3.0\nEGFR,S2,4.0\n")
scatter = write("scatter.csv", "time,condition,response,se\n0,A,1,0.1\n2,A,4,0.2\n24,A,8,0.3\n")
caption = "Five-panel synthetic bench only. Error bars are SD in (a), SEM in (b,e); n=3; *p<=0.05, **p<=0.01; two-tailed t-test. Not an official result."
spec = {"figure_id": "allfig", "style": "nature_single", "caption": caption,
        "statistics": {"n": 3, "test": "two-tailed t-test"}, "layout": {"ncols": 3}, "panels": [
    {"panel_id": "a", "chart_type": "bar", "source": {"file": bar},
     "x": {"column": "treatment", "quote": "treatment,cell_line"},
     "y": {"column": "mean_expr", "unit": "log2 FC", "quote": "mean_expr,sd"},
     "series": {"column": "cell_line", "quote": "treatment,cell_line"},
     "error": {"column": "sd", "kind": "sd", "quote": "mean_expr,sd"},
     "significance": {"column": "p_label", "quote": "sd,p_label"}},
    {"panel_id": "b", "chart_type": "line", "source": {"file": line},
     "x": {"column": "time_h", "unit": "h", "quote": "time_h,dose"},
     "y": {"column": "rel_viability", "unit": "fold", "quote": "rel_viability,sem"},
     "series": {"column": "dose", "quote": "time_h,dose"},
     "error": {"column": "sem", "kind": "sem", "quote": "rel_viability,sem"}},
    {"panel_id": "c", "chart_type": "box", "source": {"file": box},
     "x": {"column": "group", "quote": "group,response"},
     "y": {"column": "response", "unit": "a.u.", "quote": "group,response"}},
    {"panel_id": "d", "chart_type": "heatmap", "source": {"file": heat},
     "x": {"column": "sample", "quote": "gene,sample"},
     "y": {"column": "gene", "quote": "gene,sample"},
     "value": {"column": "expression", "unit": "a.u.", "quote": "sample,expression"}},
    {"panel_id": "e", "chart_type": "scatter", "source": {"file": scatter},
     "x": {"column": "time", "unit": "h", "quote": "time,condition"},
     "y": {"column": "response", "unit": "a.u.", "quote": "response,se"},
     "error": {"column": "se", "kind": "se", "quote": "response,se"}}
]}
spec_path = dump("spec.json", spec)
outdir = os.path.join(TMP, "out")
proc = run("scripts/build_figure.py", "--spec", spec_path, "--outdir", outdir, "--styles", "templates/styles.json")
add("build正向:五图型完整构建零误杀", proc.returncode == 0, (proc.stdout + proc.stderr)[-1000:])
mp_path = os.path.join(outdir, "allfig_mapping_report.json")
if not os.path.exists(mp_path):
    for name, ok, detail in checks:
        print(("PASS" if ok else "FAIL"), name, detail)
    print("mapping total 0/1")
    sys.exit(1)
with open(mp_path, encoding="utf-8") as f:
    mapping = json.load(f)
line_x = sorted(e["dx"] for e in mapping["elements"] if e["panel"] == "b")
scatter_x = sorted(e["dx"] for e in mapping["elements"] if e["panel"] == "e")
add("build正向:不规则数值x不转成等距类别", line_x == [0.0, 0.0, 2.0, 2.0, 24.0, 24.0] and scatter_x == [0.0, 2.0, 24.0], str((line_x, scatter_x)))
add("build正向:误差线端点/热图格心/箱线图统计齐全",
    all("pixel_y_error_low" in e for e in mapping["elements"] if e.get("error_column")) and
    all("pixel_x" in e and "pixel_y" in e for e in mapping["elements"] if e["glyph"] == "heatmap_cell") and
    all(all(k in e for k in ("q1", "median", "q3", "whisker_low", "whisker_high", "outliers")) for e in mapping["elements"] if e["glyph"] == "box"))

spec_mod = importlib.util.spec_from_file_location("audit_outputs", os.path.join(ROOT, "scripts", "audit_outputs.py"))
audit = importlib.util.module_from_spec(spec_mod); spec_mod.loader.exec_module(audit)
problems, report = audit.verify_map(mapping)
add("verify_map正向:数值/几何/图例/统计零误杀", not problems and report["value_domain"] == "pass" and report["geometry"] == "pass", str(problems)[:1200])


def mutation(name, mutate, needle):
    bad = copy.deepcopy(mapping)
    mutate(bad)
    probs, _ = audit.verify_map(bad)
    add(name, any(needle in p for p in probs), str(probs)[:900])


mutation("verify变异:图元值篡改必命中", lambda m: m["elements"][0].update(value=m["elements"][0]["value"] + .2), "value mismatch")
mutation("verify变异:x像素几何篡改必命中", lambda m: m["elements"][0].update(pixel_x=m["elements"][0]["pixel_x"] + 50), "x geometry mismatch")
mutation("verify变异:误差线数值篡改必命中", lambda m: m["elements"][0].update(error=m["elements"][0]["error"] + .1), "error-bar value mismatch")
mutation("verify变异:误差线端点篡改必命中", lambda m: m["elements"][0].update(pixel_y_error_high=m["elements"][0]["pixel_y_error_high"] + 40), "error-bar geometry mismatch")
mutation("verify变异:显著性标记篡改必命中", lambda m: next(e for e in m["elements"] if e.get("significance") == "*").update(significance="***"), "significance mismatch")
mutation("verify变异:系列实体错配必命中", lambda m: m["elements"][0].update(series="HeLa"), "series/entity mismatch")
mutation("verify变异:热图格心几何篡改必命中", lambda m: next(e for e in m["elements"] if e["glyph"] == "heatmap_cell").update(pixel_y=next(e for e in m["elements"] if e["glyph"] == "heatmap_cell")["pixel_y"] + 50), "geometry mismatch")
mutation("verify变异:箱线图四分位数篡改必命中", lambda m: next(e for e in m["elements"] if e["glyph"] == "box").update(q1=99), "box statistic mismatch")
mutation("verify变异:箱线图离群值漏报必命中", lambda m: next(e for e in m["elements"] if e["glyph"] == "box").update(outliers=[]), "box outliers mismatch")
mutation("verify变异:图例系列被替换必命中", lambda m: m["panels"]["a"].update(legend_labels=["A549", "Wrong"]), "legend mismatch")
mutation("verify变异:源版本哈希改变必命中", lambda m: m["elements"][0].update(source_sha256="0" * 64), "source version changed")

req = dump("required.json", {"required": [{"figure_id": "allfig", "chart_type": "bar"}]})
proc = run("scripts/audit_outputs.py", "--outdir", TMP, "--require", req)
add("audit正向:五图型导出与映射闭环通过", proc.returncode == 0, (proc.stdout + proc.stderr)[-1200:])
proc = run("scripts/audit_outputs.py", "--outdir", TMP)
add("audit变异:无required清单不得宣称完整", proc.returncode == 3 and "completeness NOT proven" in proc.stdout, proc.stdout[-500:])
bad_req = dump("required-missing.json", {"required": [{"figure_id": "absent", "chart_type": "bar"}]})
proc = run("scripts/audit_outputs.py", "--outdir", TMP, "--require", bad_req)
add("audit变异:必做图缺失必命中", proc.returncode == 3 and "not produced" in proc.stdout, proc.stdout[-500:])

passed = sum(c for _, c, _ in checks)
for name, ok, detail in checks:
    print(("PASS" if ok else "FAIL"), name, ("| " + detail if not ok else ""))
print("mapping total %d/%d" % (passed, len(checks)))
sys.exit(0 if passed == len(checks) else 1)
