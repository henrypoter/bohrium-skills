#!/usr/bin/env python3
"""原命令回归 + 选检验/数值推断/结论审计的正向与变异测试。只用标准库合成数据。"""
import copy
import csv
import hashlib
import json
import math
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL = os.path.join(HERE, "..", "scripts", "data_tool.py")
STATS = os.path.join(HERE, "..", "scripts", "stats_tool.py")
TMP = tempfile.mkdtemp(prefix="stats-bench-")
checks = []


def invoke(tool, *args):
    r = subprocess.run([sys.executable, tool, *map(str, args)], capture_output=True, text=True)
    try:
        return r.returncode, json.loads(r.stdout)
    except Exception:
        return r.returncode, {"raw": r.stdout[:300], "stderr": r.stderr[:300]}


def run(*args):
    return invoke(TOOL, *args)


def stats(*args):
    return invoke(STATS, *args)


def dump(name, obj):
    path = os.path.join(TMP, name)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False)
    return path


def text(name, content):
    path = os.path.join(TMP, name)
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(content)
    return path


def add(name, condition, detail=""):
    checks.append((name, bool(condition), detail))


def checksum(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


# 原 10 项回归。
CSV = """id,value,unit_mixed,score
1,10,1,12
2,20,5000,15
3,,300,N/A
4,30,7,18
1,10,1,12
5,1000,4,20
"""
csvp = text("data.csv", CSV)
rc, d = run("profile", csvp)
cols = {c["column"]: c for c in d.get("columns", [])}
add("profile:缺失与重复行", rc == 0 and d.get("rows") == 6 and d.get("duplicate_rows") == 1
    and cols["value"]["missing"] == 1, str(d))
add("profile:量级不一致告警", "scale_warning" in cols["unit_mixed"], str(d))
add("profile:异常值(IQR)检出", cols["value"].get("outliers_iqr", 0) >= 1, str(d))
add("profile:脏数值计数", cols["score"].get("dirty_numeric_count") == 1, str(d))
BASE = {"case_id": "c1", "status": "issues",
        "questions": [{"id": "Q1", "answer": "value 合计 1070", "evidence": ["data.csv:value 列求和"]}],
        "aggregates": [{"column": "value", "op": "sum", "value": 1070},
                       {"column": "value", "op": "count", "value": 5},
                       {"column": "score", "op": "mean", "value": 15.4}],
        "data_dictionary": {"value": "测量值", "unit_mixed": "单位混用列", "score": "评分"},
        "lineage": {"snapshot": "snap-2026-11-20", "tables": ["data.csv"], "filters": []},
        "gain": {"baseline_accuracy": 0.55, "skill_accuracy": 0.9, "rework_rounds_saved": 2},
        "unchecked": [], "sources": ["data.csv"], "uncertainty": [], "change_log": []}
rc, d = run("recheck", dump("r.json", BASE), "--csv", csvp)
add("recheck:聚合可独立复算", rc == 0 and d.get("checked") == 3, str(d))
bad = copy.deepcopy(BASE)
bad["aggregates"][0]["value"] = 1000
rc, d = run("recheck", dump("r2.json", bad), "--csv", csvp)
add("recheck:篡改数值被抓出", rc == 1 and len(d.get("mismatches", [])) == 1, str(d))
rc, d = run("schema", dump("s.json", BASE))
add("schema正向:合规零误杀", rc == 0 and d.get("ok"), str(d))
bad = copy.deepcopy(BASE)
bad.pop("lineage")
rc, d = run("schema", dump("s2.json", bad))
add("schema变异:缺lineage->失败", rc == 1, str(d))
bad = copy.deepcopy(BASE)
bad["questions"][0].pop("evidence")
rc, d = run("schema", dump("s3.json", bad))
add("schema变异:结论缺evidence->失败", rc == 1 and any("evidence" in e for e in d.get("errors", [])), str(d))
bad = copy.deepcopy(BASE)
bad["aggregates"][0].pop("value")
rc, d = run("schema", dump("s4.json", bad))
add("schema变异:aggregate缺value->失败", rc == 1, str(d))


def make_spec(name="A1", **updates):
    spec = {"spec_version": "spec-1", "dictionary_version": "dict-1", "analysis_id": name,
            "design": "independent", "value": "y", "group": "arm", "unit": "mg/L",
            "alpha": .05, "max_missing_fraction": .20, "missing_tokens": ["", "-999"],
            "random_seed": 17, "minimum_important_effect": .2}
    spec.update(updates)
    return spec


def two_group_text(a, b, missing_a=0):
    lines = ["id,arm,y"]
    for i, x in enumerate(a):
        lines.append("a%d,A,%s" % (i, x))
    for i in range(missing_a):
        lines.append("am%d,A,-999" % i)
    for i, x in enumerate(b):
        lines.append("b%d,B,%s" % (i, x))
    return "\n".join(lines) + "\n"


A = [10, 11, 9, 10, 12, 11, 9, 10]
B = [8, 8, 7, 9, 8, 7, 8, 8]
normal_csv = text("normal-two.csv", two_group_text(A, B))
normal_spec = dump("normal-spec.json", make_spec())

# recommend：设计与分布驱动的选择，正向不误报。
rc, d = stats("recommend", normal_csv, "--spec", normal_spec)
add("recommend正向:两组通过筛查选Welch", rc == 0 and d.get("recommendation", {}).get("test") == "welch_t"
    and d.get("descriptive_statistics", {}).get("A", {}).get("n") == 8, str(d))
small_csv = text("small.csv", two_group_text([1, 2, 2, 3, 20], [2, 3, 3, 4, 5]))
rc, d = stats("recommend", small_csv, "--spec", normal_spec)
add("recommend:小样本/偏态自动改秩检验", rc == 0 and d.get("recommendation", {}).get("test") == "mann_whitney_u", str(d))

paired_csv = text("paired-zero.csv", "pair,arm,y\n" + "".join("p%d,A,3\np%d,B,1\n" % (i, i) for i in range(8)))
paired_spec = dump("paired-spec.json", make_spec(design="paired", pair="pair"))
rc, d = stats("recommend", paired_csv, "--spec", paired_spec)
add("recommend:配对零方差不崩溃并改Wilcoxon", rc == 0 and d.get("recommendation", {}).get("test") == "wilcoxon_signed_rank"
    and any(x["code"] == "ZERO_DIFFERENCE_VARIANCE" for x in d.get("warnings", [])), str(d))

# 异常：样本量、缺失、字段单位全部硬阻断，并给主动追问。
too_small = text("too-small.csv", two_group_text([1, 2], [2, 3, 4]))
rc, d = stats("recommend", too_small, "--spec", normal_spec)
add("recommend变异:样本量不足必阻断", rc == 1 and any(x["code"] == "SAMPLE_TOO_SMALL" for x in d.get("blockers", [])), str(d))
high_missing = text("high-missing.csv", two_group_text([1, 2, 3], [2, 3, 4, 5], missing_a=2))
rc, d = stats("recommend", high_missing, "--spec", normal_spec)
add("recommend变异:高缺失不以0硬算", rc == 1 and any(x["code"] == "HIGH_MISSING" for x in d.get("blockers", [])), str(d))
unknown_spec = dump("unknown-unit.json", make_spec(unit="?"))
rc, d = stats("infer", normal_csv, "--spec", unknown_spec)
add("infer变异:单位不明主动追问而非硬算", rc == 1 and any(x["code"] == "UNIT_UNKNOWN" for x in d.get("blockers", []))
    and d.get("questions"), str(d))
dirty_csv = text("dirty.csv", two_group_text(A[:-1] + ["bad"], B))
rc, d = stats("recommend", dirty_csv, "--spec", normal_spec)
add("recommend变异:脏数值不静默删除", rc == 1 and any(x["code"] == "DIRTY_NUMERIC" for x in d.get("blockers", [])), str(d))

# Welch 数值：均值差独立金标准为 2.375；df、双侧 p、Hedges g 与区间同时交付。
analysis_path = os.path.join(TMP, "normal-analysis.json")
rc, d = stats("infer", normal_csv, "--spec", normal_spec, "--out", analysis_path)
a = d.get("analysis", {})
test, effect = a.get("test", {}), a.get("effect", {})
# 均值、样本方差和 Welch t 均由输入独立复算，不只检查字段非空。
mean_diff = (sum(A) / len(A)) - (sum(B) / len(B))
va = sum((x - sum(A) / len(A)) ** 2 for x in A) / (len(A) - 1)
vb = sum((x - sum(B) / len(B)) ** 2 for x in B) / (len(B) - 1)
expected_t = mean_diff / math.sqrt(va / len(A) + vb / len(B))
add("infer正向:Welch数值与独立公式一致", rc == 0 and abs(a.get("estimate", {}).get("value", 0) - mean_diff) < 1e-12
    and abs(test.get("statistic", 0) - expected_t) < 1e-10
    and 0 < test.get("p_value", 1) < 0.001 and test.get("df") > 10, str(d))
add("infer正向:效应量/区间/结论同向绑定", effect.get("name") == "hedges_g" and effect.get("value") > 0
    and effect["ci"][0] <= effect["value"] <= effect["ci"][1]
    and a.get("conclusion", {}).get("effect_value") == effect.get("value")
    and a.get("conclusion", {}).get("effect_ci") == effect.get("ci")
    and a.get("conclusion", {}).get("practical_importance", {}).get("label") == "potentially_important", str(d))

# 非参数与配对零方差输出仍是合法有限数值，而非 NaN/除零崩溃。
rc, d = stats("infer", small_csv, "--spec", normal_spec)
add("infer:Mann–Whitney含有限p/秩双列效应与区间", rc == 0 and d["analysis"]["test"]["name"] == "mann_whitney_u"
    and 0 <= d["analysis"]["test"]["p_value"] <= 1
    and all(math.isfinite(x) for x in d["analysis"]["effect"]["ci"]), str(d))
rc, d = stats("infer", paired_csv, "--spec", paired_spec)
add("infer:恒定非零配对差用Wilcoxon且区间有限", rc == 0 and 0 < d["analysis"]["test"]["p_value"] < .01
    and d["analysis"]["effect"]["value"] == 1.0
    and all(math.isfinite(x) for x in d["analysis"]["estimate"]["ci"]), str(d))
zero_csv = text("paired-all-zero.csv", "pair,arm,y\n" + "".join("p%d,A,1\np%d,B,1\n" % (i, i) for i in range(8)))
rc, d = stats("infer", zero_csv, "--spec", paired_spec)
add("infer:全零配对差安全返回p=1/效应0", rc == 0 and d["analysis"]["test"]["p_value"] == 1.0
    and d["analysis"]["effect"]["value"] == 0.0 and d["analysis"]["estimate"]["ci"] == [0.0, 0.0], str(d))

# 三组 omnibus + 全对比较 + Holm；每组 n=8 且组内方差非零。
C = [13, 14, 12, 13, 15, 14, 12, 13]
three_csv = text("three.csv", two_group_text(A, B) + "".join("c%d,C,%s\n" % (i, x) for i, x in enumerate(C)))
three_spec = dump("three-spec.json", make_spec(pairwise=True))
three_path = os.path.join(TMP, "three-analysis.json")
rc, d = stats("infer", three_csv, "--spec", three_spec, "--out", three_path)
ta = d.get("analysis", {})
adj = [x.get("test", {}).get("p_adjusted_holm") for x in ta.get("pairwise", [])]
add("infer:三组选ANOVA且效应用固定种子bootstrap区间", rc == 0 and ta.get("test", {}).get("name") == "one_way_anova"
    and ta.get("effect", {}).get("name") == "eta_squared" and all(math.isfinite(x) for x in ta.get("effect", {}).get("ci", [])), str(d))
add("infer:多重比较Holm字段齐全", len(adj) == 3 and all(x is not None and 0 <= x <= 1 for x in adj), str(adj))
C_wide = [3, 8, 11, 13, 13, 15, 18, 23]
wide_csv = text("wide-variance.csv", two_group_text(A, B) + "".join("w%d,C,%s\n" % (i, x) for i, x in enumerate(C_wide)))
rc, d = stats("recommend", wide_csv, "--spec", three_spec)
add("recommend变异:多组方差明显不齐改Kruskal", rc == 0 and d.get("recommendation", {}).get("test") == "kruskal_wallis"
    and d.get("recommendation", {}).get("variance_screen", {}).get("max_min_ratio", 0) > 4, str(d))

# audit：外部 infer 原样复制、结论/效应/CI/p 值一致、版本与血缘齐全。
analysis_obj = json.load(open(analysis_path, encoding="utf-8"))["analysis"]
RESULT = {"case_id": "stats-demo", "status": "pass",
          "questions": [{"id": "Q1", "answer": "A 高于 B，但因果不在本分析范围",
                         "evidence": ["analysis:A1.effect", "analysis:A1.test"]}],
          "statistics": [analysis_obj],
          "data_dictionary": {"y": {"semantic": "浓度", "unit": "mg/L", "source": "dictionary.fields.y"}},
          "lineage": {"snapshot": "snap-stats", "inputs": [{"path": normal_csv, "sha256": checksum(normal_csv)}]},
          "run": {"skill_version": "3.0.0", "tool_version": "3.0.0", "ruleset_version": "stats-rules-1",
                  "dictionary_version": "dict-1", "python_version": sys.version.split()[0],
                  "started_at": "2026-01-01T00:00:00Z", "random_seed": 17},
          "quality": analysis_obj["sample_quality"], "unchecked": [], "sources": ["normal-two.csv"],
          "uncertainty": [], "change_log": [],
          "artifacts": [{"path": analysis_path, "sha256": checksum(analysis_path), "type": "analysis"}]}
rc, d = stats("audit", dump("result-good.json", RESULT), "--analysis", analysis_path)
add("audit正向:数值/CI/结论/版本零误杀", rc == 0 and d.get("analyses_checked") == 1, str(d))
bad = copy.deepcopy(RESULT)
bad["statistics"][0]["conclusion"]["effect_value"] = 0
rc, d = stats("audit", dump("result-effect-bad.json", bad), "--analysis", analysis_path)
add("audit变异:结论脱离效应量必命中", rc == 1 and any(x["code"] in {"RESULT_ANALYSIS_MISMATCH", "EFFECT_CI_NOT_BOUND_TO_CONCLUSION"} for x in d.get("errors", [])), str(d))
bad = copy.deepcopy(RESULT)
bad["statistics"][0]["conclusion"]["statistically_significant"] = False
rc, d = stats("audit", dump("result-significance-bad.json", bad), "--analysis", analysis_path)
add("audit变异:p值与显著性表述冲突必命中", rc == 1 and any(x["code"] in {"RESULT_ANALYSIS_MISMATCH", "P_VALUE_CONCLUSION_MISMATCH"} for x in d.get("errors", [])), str(d))
bad = copy.deepcopy(RESULT)
bad["statistics"][0]["effect"]["ci"] = [100, 101]
rc, d = stats("audit", dump("result-ci-bad.json", bad), "--analysis", analysis_path)
add("audit变异:区间不包含效应点必命中", rc == 1 and any(x["code"] in {"RESULT_ANALYSIS_MISMATCH", "CI_DOES_NOT_CONTAIN_ESTIMATE"} for x in d.get("errors", [])), str(d))
bad = copy.deepcopy(RESULT)
bad["run"].pop("python_version")
rc, d = stats("audit", dump("result-version-bad.json", bad), "--analysis", analysis_path)
add("audit变异:缺运行版本必命中", rc == 1 and any(x["code"] == "VERSION_FIELD_MISSING" for x in d.get("errors", [])), str(d))

three_obj = json.load(open(three_path, encoding="utf-8"))["analysis"]
three_result = copy.deepcopy(RESULT)
three_result["statistics"] = [three_obj]
three_result["quality"] = three_obj["sample_quality"]
bad = copy.deepcopy(three_result)
bad["statistics"][0]["pairwise"][0]["test"].pop("p_adjusted_holm")
rc, d = stats("audit", dump("result-holm-bad.json", bad), "--analysis", three_path)
add("audit变异:多重比较未校正必命中", rc == 1 and any(x["code"] in {"RESULT_ANALYSIS_MISMATCH", "HOLM_ADJUSTMENT_MISSING"} for x in d.get("errors", [])), str(d))
rc, d = stats("audit", dump("result-three-good.json", three_result), "--analysis", three_path)
add("audit正向:多组Holm合规零误杀", rc == 0, str(d))
bad = copy.deepcopy(RESULT)
bad["lineage"]["inputs"][0]["sha256"] = "0" * 64
rc, d = stats("audit", dump("result-hash-bad.json", bad), "--analysis", analysis_path)
add("audit变异:输入SHA256造假必命中", rc == 1 and any(x["code"] == "INPUT_HASH_MISMATCH" for x in d.get("errors", [])), str(d))
bad = copy.deepcopy(RESULT)
bad["run"]["dictionary_version"] = "different-dictionary"
rc, d = stats("audit", dump("result-dict-version-bad.json", bad), "--analysis", analysis_path)
add("audit变异:结果与外部分析字典版本冲突必命中", rc == 1 and any(x["code"] == "RUN_ANALYSIS_DICTIONARY_VERSION_MISMATCH" for x in d.get("errors", [])), str(d))

ok = sum(1 for _, condition, _ in checks if condition)
for name, condition, detail in checks:
    print(("PASS" if condition else "FAIL"), name, ("| " + detail if not condition else ""))
print("total %d/%d" % (ok, len(checks)))
sys.exit(0 if ok == len(checks) else 1)
