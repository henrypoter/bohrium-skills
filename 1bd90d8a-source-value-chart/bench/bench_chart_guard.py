#!/usr/bin/env python3
"""Positive-zero-false-reject + mutation-must-fail tests for chart_guard.py."""
import copy
import hashlib
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
TOOL = os.path.join(ROOT, "scripts", "chart_guard.py")
TMP = tempfile.mkdtemp(prefix="chart-guard-bench-")
checks = []


def add(name, condition, detail=""):
    checks.append((name, bool(condition), detail))


def run(*args):
    proc = subprocess.run([sys.executable, TOOL, *args], cwd=ROOT, capture_output=True, text=True)
    try:
        payload = json.loads(proc.stdout)
    except Exception:
        payload = {"raw": proc.stdout[-400:], "stderr": proc.stderr[-400:]}
    return proc.returncode, payload


def dump(name, obj):
    path = os.path.join(TMP, name)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False)
    return path


def clone(obj):
    return copy.deepcopy(obj)


# preflight: valid scientific mappings and all fatal ambiguity classes.
spec = json.load(open(os.path.join(ROOT, "templates", "chart_spec.example.json"), encoding="utf-8"))
for p in spec["panels"]:
    p["source"]["file"] = os.path.join(ROOT, p["source"]["file"])
rc, out = run("preflight", "--spec", dump("spec-ok.json", spec))
add("preflight正向:完整spec零误杀", rc == 0 and out["ok"] and len(out["source_versions"]) == 2, str(out)[:300])

bad = clone(spec); bad["panels"][0]["y"]["column"] = "mean_exp"
rc, out = run("preflight", "--spec", dump("spec-missing.json", bad))
add("preflight变异:缺列必命中", rc == 1 and any(e["code"] == "missing_column" for e in out["errors"]))
bad = clone(spec); bad["panels"][0]["source"]["file"] = os.path.join(TMP, "dup.csv")
with open(os.path.join(ROOT, "templates", "demo_bar.csv"), encoding="utf-8") as f:
    lines = f.read().splitlines()
with open(bad["panels"][0]["source"]["file"], "w", encoding="utf-8") as f:
    f.write("\n".join(lines + [lines[1]]) + "\n")
rc, out = run("preflight", "--spec", dump("spec-dup.json", bad))
add("preflight变异:同键重复行必命中", rc == 1 and any(e["code"] == "duplicate_glyph_key" for e in out["errors"]))
bad = clone(spec); bad["panels"][0]["error"]["column"] = "p_label"
rc, out = run("preflight", "--spec", dump("spec-errorbar.json", bad))
add("preflight变异:非数值误差线必命中", rc == 1 and any(e["code"] == "invalid_errorbar" for e in out["errors"]))
bad = clone(spec); bad["caption"] = "A plot."
rc, out = run("preflight", "--spec", dump("spec-caption.json", bad))
add("preflight变异:误差线含义缺失必命中", rc == 1 and any(e["code"] == "errorbar_caption" for e in out["errors"]))
bad = clone(spec); bad["statistics"].pop("n")
rc, out = run("preflight", "--spec", dump("spec-n.json", bad))
add("preflight变异:样本量缺失必命中", rc == 1 and any(e["code"] == "sample_size" for e in out["errors"]))
bad = clone(spec); bad["panels"][0]["y"]["quote"] = "mean_expr,wrong"
rc, out = run("preflight", "--spec", dump("spec-quote.json", bad))
add("preflight变异:quote错锚必命中", rc == 1 and any(e["code"] == "quote_mismatch" for e in out["errors"]))
bad = clone(spec); bad["panels"][0]["source"]["file"] = os.path.join(TMP, "nonnumeric.csv")
with open(bad["panels"][0]["source"]["file"], "w", encoding="utf-8") as f:
    f.write("treatment,cell_line,mean_expr,sd,p_label\nDMSO,A549,not_a_number,0.1,ns\n")
rc, out = run("preflight", "--spec", dump("spec-nonnumeric.json", bad))
add("preflight变异:非空非数值不得静默丢弃", rc == 1 and any(e["code"] == "nonnumeric_value" for e in out["errors"]))
warn = clone(spec); warn["panels"][0]["source"]["file"] = os.path.join(TMP, "warn.csv")
with open(warn["panels"][0]["source"]["file"], "w", encoding="utf-8") as f:
    f.write("treatment,cell_line,mean_expr,sd,p_label\nVery-long-treatment-entity-name-that-needs-wrapping,A549,0.00001,0.1,ns\n")
rc, out = run("preflight", "--spec", dump("spec-warn.json", warn))
codes = {w["code"] for w in out["warnings"]}
add("preflight正向:长标签/量级仅告警不误杀", rc == 0 and {"long_label", "magnitude"} <= codes, str(out)[:400])

# Bidirectional lookup, using actual source cell evidence.
demo = os.path.join(ROOT, "templates", "demo_bar.csv")
mapping = {"elements": [
    {"panel": "a", "glyph": "bar", "series": "A549", "value": 0.02,
     "source": {"file": demo, "columns": ["treatment", "mean_expr"], "rows": [2]}},
    {"panel": "a", "glyph": "bar", "series": "A549", "value": 1.18,
     "source": {"file": demo, "columns": ["treatment", "mean_expr"], "rows": [3]}}]}
mp = dump("mapping.json", mapping)
rc, out = run("lookup", "--mapping", mp, "--element", "1")
add("lookup正向:图元到字段行值", rc == 0 and out["source_evidence"][0]["cells"]["mean_expr"] == "1.18")
rc, out = run("lookup", "--mapping", mp, "--source", demo, "--row", "3")
add("lookup正向:数据行反查图元", rc == 0 and out["glyphs"][0]["element_index"] == 1)
rc, out = run("lookup", "--mapping", mp, "--element", "9")
add("lookup变异:不存在图元必命中", rc == 1 and not out["ok"])
rc, out = run("lookup", "--mapping", mp, "--source", demo, "--row", "4")
add("lookup变异:未渲染数据行反查必命中", rc == 1 and "no glyph" in out["error"])

# Source-preserving SVG editing with preconditions and scientific cell equality.
svg_src = os.path.join(ROOT, "templates", "demo_edit.svg")
svg = os.path.join(TMP, "original.svg")
with open(svg_src, encoding="utf-8") as f:
    svg_text = f.read()
with open(svg, "w", encoding="utf-8") as f:
    f.write(svg_text)
svg_hash = hashlib.sha256(svg_text.encode("utf-8")).hexdigest()
edits = json.load(open(os.path.join(ROOT, "templates", "svg_edits.example.json"), encoding="utf-8"))
edits["input_sha256"] = svg_hash
edits["operations"][0]["source"]["file"] = demo
edited, edit_log = os.path.join(TMP, "edited.svg"), os.path.join(TMP, "edit-log.json")
rc, out = run("edit-svg", "--input", svg, "--operations", dump("edits-ok.json", edits), "--output", edited, "--log", edit_log)
with open(edited, encoding="utf-8") as f:
    edited_text = f.read()
add("edit-svg正向:文本样式修改且原图不变", rc == 0 and out["original_preserved"] and hashlib.sha256(open(svg, "rb").read()).hexdigest() == svg_hash and "DrugX" in edited_text and "#E69F00" in edited_text)
bad = clone(edits); bad["input_sha256"] = "0" * 64
rc, out = run("edit-svg", "--input", svg, "--operations", dump("edits-hash.json", bad), "--output", os.path.join(TMP, "bad1.svg"), "--log", os.path.join(TMP, "bad1.json"))
add("edit-svg变异:源版本哈希变化必命中", rc == 1 and "precondition" in out["errors"][0])
bad = clone(edits); bad["operations"][0]["expected"] = "Wrong old title"
rc, out = run("edit-svg", "--input", svg, "--operations", dump("edits-expected.json", bad), "--output", os.path.join(TMP, "bad2.svg"), "--log", os.path.join(TMP, "bad2.json"))
add("edit-svg变异:旧值前置条件失败必命中", rc == 1 and "precondition" in out["errors"][0])
bad = clone(edits); bad["operations"][0]["value"] = "InventedEntity"
rc, out = run("edit-svg", "--input", svg, "--operations", dump("edits-source.json", bad), "--output", os.path.join(TMP, "bad3.svg"), "--log", os.path.join(TMP, "bad3.json"))
add("edit-svg变异:编辑值不等于源单元格必命中", rc == 1 and "does not equal source" in out["errors"][0])
bad = clone(edits); bad["operations"][0]["id"] = "panel-a"
rc, out = run("edit-svg", "--input", svg, "--operations", dump("edits-container.json", bad), "--output", os.path.join(TMP, "bad4.svg"), "--log", os.path.join(TMP, "bad4.json"))
add("edit-svg变异:含子节点文本覆盖被阻止", rc == 1 and "child nodes" in out["errors"][0])
rc, out = run("edit-svg", "--input", svg, "--operations", dump("edits-same.json", edits), "--output", svg, "--log", os.path.join(TMP, "bad5.json"))
add("edit-svg变异:原地覆盖源文件被阻止", rc == 1 and "immutable" in out["errors"][0])

# Fair comparison, including no fabricated aggregate and exact run identity.
base_path = os.path.join(ROOT, "templates", "run_record.baseline.example.json")
skill_path = os.path.join(ROOT, "templates", "run_record.skill.example.json")
base = json.load(open(base_path, encoding="utf-8")); skill = json.load(open(skill_path, encoding="utf-8"))
result = {"case_id": "example-demo", "gain": {"status": "not_run"}}
rc, out = run("compare", "--baseline", base_path, "--candidate", skill_path, "--result", dump("gain-result.json", result))
add("compare正向:同输入同导出实测增益", rc == 0 and out["gain"]["quality"]["glyph_value_accuracy"]["delta"] == 0.25 and out["gain"]["efficiency"]["manual_edits"]["reduction"] == 2)
bad = clone(skill); bad["input_sha256"] = "f" * 64
rc, out = run("compare", "--baseline", base_path, "--candidate", dump("skill-mismatch.json", bad))
add("compare变异:输入版本不一致必命中", rc == 1 and "unfair comparison" in out["error"])
bad = clone(skill); bad["export_spec"]["dpi"] = 600
rc, out = run("compare", "--baseline", base_path, "--candidate", dump("skill-export.json", bad))
add("compare变异:导出参数不一致必命中", rc == 1 and "export_spec" in out["error"])
bad = clone(skill); bad["metrics"]["glyph_value_errors"] = 99
rc, out = run("compare", "--baseline", base_path, "--candidate", dump("skill-metrics.json", bad))
add("compare变异:不可能计数必命中", rc == 1 and "exceeds" in out["error"])
bad = clone(skill); bad["condition"] = "baseline"
rc, out = run("compare", "--baseline", base_path, "--candidate", dump("skill-condition.json", bad))
add("compare变异:条件标签不合法必命中", rc == 1 and "condition" in out["error"])

# Dynamic original output_contract + actual output files + honest gain/status.
artifact = os.path.join(TMP, "artifact.svg")
with open(artifact, "w", encoding="utf-8") as f:
    f.write(svg_text)
res = {"case_id": "c1", "status": "complete", "custom_answer": "kept", "sources": [{"file": demo}],
       "uncertainty": [], "change_log": [], "outputs": [{"role_outputs": {"preview": [artifact]}}],
       "validation": {"missing_required": [], "verify_map": {}}, "gain": {"status": "not_run"}}
case = {"case_id": "c1", "output_contract": {"required": ["case_id", "status", "custom_answer", "outputs"]}}
rp, cp = dump("result-ok.json", res), dump("case.json", case)
rc, out = run("contract", "--result", rp, "--case", cp)
add("contract正向:原字段保留且产物存在", rc == 0 and out["ok"] and "custom_answer" in out["required_fields"])
bad = clone(res); bad.pop("custom_answer")
rc, out = run("contract", "--result", dump("result-field.json", bad), "--case", cp)
add("contract变异:原output_contract字段丢失必命中", rc == 1 and any("custom_answer" in e for e in out["errors"]))
bad = clone(res); bad["outputs"][0]["role_outputs"]["preview"] = [os.path.join(TMP, "absent.svg")]
rc, out = run("contract", "--result", dump("result-file.json", bad), "--case", cp)
add("contract变异:声明产物不存在必命中", rc == 1 and any("missing/empty" in e for e in out["errors"]))
bad = clone(res); bad["validation"]["verify_map"] = {"fig1": {"problems": ["value mismatch"]}}
rc, out = run("contract", "--result", dump("result-status.json", bad), "--case", cp)
add("contract变异:complete与复核失败矛盾必命中", rc == 1 and any("contradicts" in e for e in out["errors"]))
bad = clone(res); bad["gain"] = {"status": "measured"}
rc, out = run("contract", "--result", dump("result-gain.json", bad), "--case", cp)
add("contract变异:无证据实测增益必命中", rc == 1 and any("evidence" in e for e in out["errors"]))
bad = clone(res); bad["case_id"] = "other"
rc, out = run("contract", "--result", dump("result-case.json", bad), "--case", cp)
add("contract变异:case_id不一致必命中", rc == 1 and any("case_id differs" in e for e in out["errors"]))

passed = sum(c for _, c, _ in checks)
for name, ok, detail in checks:
    print(("PASS" if ok else "FAIL"), name, ("| " + detail if not ok else ""))
print("chart_guard total %d/%d" % (passed, len(checks)))
sys.exit(0 if passed == len(checks) else 1)
