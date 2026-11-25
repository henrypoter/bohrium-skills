#!/usr/bin/env python3
"""旧命令回归 + 新命令正向零误杀/变异必命中；仅使用标准库和临时合成数据。"""
import copy
import hashlib
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL = os.path.join(HERE, "..", "scripts", "data_tool.py")
CLEAN = os.path.join(HERE, "..", "scripts", "cleaning_tool.py")
TMP = tempfile.mkdtemp(prefix="cleaning-bench-")
checks = []


def invoke(tool, *args):
    r = subprocess.run([sys.executable, tool, *map(str, args)], capture_output=True, text=True)
    try:
        return r.returncode, json.loads(r.stdout)
    except Exception:
        return r.returncode, {"raw": r.stdout[:300], "stderr": r.stderr[:300]}


def run(*args):
    return invoke(TOOL, *args)


def clean(*args):
    return invoke(CLEAN, *args)


def dump(name, obj):
    path = os.path.join(TMP, name)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False)
    return path


def text(name, content, encoding="utf-8"):
    path = os.path.join(TMP, name)
    with open(path, "w", encoding=encoding, newline="") as fh:
        fh.write(content)
    return path


def add(name, condition, detail=""):
    checks.append((name, bool(condition), detail))


def checksum(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


CSV = """id,value,unit_mixed,score
1,10,1,12
2,20,5000,15
3,,300,N/A
4,30,7,18
1,10,1,12
5,1000,4,20
"""
csvp = text("data.csv", CSV)

# 原有 10 项：确保优化没有推倒或破坏成熟能力。
rc, d = run("profile", csvp)
cols = {c["column"]: c for c in d.get("columns", [])}
add("profile:缺失与重复行", rc == 0 and d.get("rows") == 6 and d.get("duplicate_rows") == 1
    and cols["value"]["missing"] == 1, str(d))
add("profile:量级不一致告警", "scale_warning" in cols["unit_mixed"], str(cols.get("unit_mixed")))
add("profile:异常值(IQR)检出", cols["value"].get("outliers_iqr", 0) >= 1, str(cols["value"]))
add("profile:脏数值计数", cols["score"].get("dirty_numeric_count") == 1, str(cols["score"]))

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
add("schema变异:缺lineage->失败", rc == 1 and any("lineage" in e for e in d.get("errors", [])), str(d))
bad = copy.deepcopy(BASE)
bad["questions"][0].pop("evidence")
rc, d = run("schema", dump("s3.json", bad))
add("schema变异:结论缺evidence->失败", rc == 1 and any("evidence" in e for e in d.get("errors", [])), str(d))
bad = copy.deepcopy(BASE)
bad["aggregates"][0].pop("value")
rc, d = run("schema", dump("s4.json", bad))
add("schema变异:aggregate缺value->失败", rc == 1, str(d))

# plan：字典驱动字段规则，不把编码字段当连续变量，也不自动填补。
DICT = {"dictionary_version": "dict-1", "fields": {
    "sample_id": {"role": "identifier", "semantic": "样品编号", "missing_tokens": [""]},
    "value": {"role": "measurement", "semantic": "浓度", "unit": "mg/L", "target_unit": "μg/L",
              "physical_range": [0, 10000], "missing_tokens": ["", "-999"]},
    "sex": {"role": "categorical", "semantic": "性别编码", "codes": {"1": "男", "2": "女", "9": "未知"},
            "missing_tokens": ["", "9"]}}}
plan_csv = text("plan.csv", "sample_id,value,sex\nS1,1.2,1\nS2,-999,2\n")
dictp = dump("dictionary.json", DICT)
rc, d = clean("plan", dictp, "--csv", plan_csv)
add("plan正向:字段策略与来源定位零误杀", rc == 0 and len(d.get("field_rules", [])) == 3
    and all(x.get("source") for x in d.get("field_rules", []))
    and d["field_rules"][2]["numeric_policy"] == "coded_category_not_continuous", str(d))

all_missing = copy.deepcopy(DICT)
all_missing_csv = text("all-missing.csv", "sample_id,value,sex\nS1,-999,1\nS2,,2\n")
rc, d = clean("plan", dictp, "--csv", all_missing_csv)
add("plan变异:全列缺失阻断且不填补", rc == 1 and any(x["code"] == "ALL_COLUMN_MISSING" for x in d.get("blockers", [])), str(d))
unknown_unit = copy.deepcopy(DICT)
unknown_unit["fields"]["value"]["unit"] = "?"
rc, d = clean("plan", dump("unknown-unit.json", unknown_unit), "--csv", plan_csv)
add("plan变异:单位不明主动提问", rc == 1 and any(x["code"] == "UNIT_UNKNOWN" and x.get("question") for x in d.get("blockers", [])), str(d))
corrupt = os.path.join(TMP, "corrupt.csv")
with open(corrupt, "wb") as fh:
    fh.write(b"\xff\x00\x00broken")
rc, d = clean("plan", dictp, "--csv", corrupt)
add("plan变异:损坏/乱码不静默吞掉", rc == 1 and d.get("error_code") in {"INPUT_INVALID", "ENCODING_UNKNOWN"}, str(d))

# keys：大小写/空白归一只用于匹配，重复主键和同键值冲突均带行号阻断。
left = text("left.csv", "id,batch,left_only\n A01 ,x,1\nB02,Y,2\n")
right = text("right.csv", "sample_id,batch,right_only\na01,X,3\nB02,y,4\n")
rc, d = clean("keys", left, right, "--left-key", "id", "--right-key", "sample_id")
add("keys正向:跨表近似键对齐且保留原值", rc == 0 and d.get("rows", {}).get("matched_keys") == 2
    and len(d.get("normalization_map", [])) >= 1, str(d))
dup_left = text("dup-left.csv", "id,batch\nA01,x\na01,y\n")
rc, d = clean("keys", dup_left, right, "--left-key", "id", "--right-key", "sample_id")
add("keys变异:主键冲突必命中并定位", rc == 1 and any(x["code"] == "PRIMARY_KEY_CONFLICT" and x["duplicates"][0]["occurrences"] for x in d.get("errors", [])), str(d))
conflict_right = text("conflict-right.csv", "sample_id,batch\na01,Z\nB02,y\n")
rc, d = clean("keys", left, conflict_right, "--left-key", "id", "--right-key", "sample_id")
add("keys变异:同键跨表值冲突必命中", rc == 1 and any(x["code"] == "CROSS_TABLE_VALUE_CONFLICT" for x in d.get("errors", [])), str(d))

# convert：混合单位逐行转换，原值/公式/逆换算/哈希可审计。
convert_csv = text("convert.csv", "id,conc,unit\n1,1.25,mg/L\n2,2.5,μg/mL\n3,-999,mg/L\n")
convert_plan = {"plan_version": "units-1", "missing_tokens": ["-999"],
                "operations": [{"column": "conc", "unit_column": "unit", "to_unit": "μg/L"}]}
cp = dump("convert-plan.json", convert_plan)
out = os.path.join(TMP, "converted.csv")
audit = os.path.join(TMP, "convert-audit.json")
rc, d = clean("convert", cp, "--input", convert_csv, "--out", out, "--audit", audit)
with open(audit, encoding="utf-8") as fh:
    conversion_audit = json.load(fh) if os.path.exists(audit) else {}
add("convert正向:混合单位可逆且缺失不换算", rc == 0 and d.get("conversion_count") == 2
    and conversion_audit.get("changes", [{}, {}])[0].get("converted") == "1250"
    and conversion_audit.get("changes", [{}, {}])[1].get("converted") == "2500"
    and all(x.get("roundtrip_exact") for x in conversion_audit.get("changes", [])), str(d))
with open(out, encoding="utf-8") as fh:
    converted_text = fh.read()
add("convert正向:原值列与输入输出哈希留痕", "conc__original" in converted_text and "1.25" in converted_text
    and len(conversion_audit.get("input", {}).get("sha256", "")) == 64, converted_text)
unknown_convert = {"plan_version": "units-1", "operations": [{"column": "conc", "unit_column": "unit", "to_unit": "mystery/unit"}]}
no_out = os.path.join(TMP, "must-not-exist.csv")
rc, d = clean("convert", dump("bad-convert.json", unknown_convert), "--input", convert_csv,
              "--out", no_out, "--audit", os.path.join(TMP, "must-not-exist.json"))
add("convert变异:未知单位失败且不写清洗表", rc == 1 and d.get("error_code") == "UNIT_UNKNOWN" and not os.path.exists(no_out), str(d))
bad_number = text("bad-number.csv", "id,conc\n1,not-a-number\n")
number_plan = {"plan_version": "units-1", "operations": [{"column": "conc", "from_unit": "mg/L", "to_unit": "g/L"}]}
rc, d = clean("convert", dump("number-plan.json", number_plan), "--input", bad_number,
              "--out", no_out, "--audit", os.path.join(TMP, "bad-number-audit.json"))
add("convert变异:坏数值不静默置零", rc == 1 and d.get("error_code") == "NUMERIC_CONVERSION_FAILED", str(d))
gbk = text("gbk.csv", "id,名称\n1,样品甲\n", "gbk")
gbk_out = os.path.join(TMP, "gbk-utf8.csv")
rc, d = clean("convert", dump("transcode.json", {"plan_version": "enc-1", "operations": []}),
              "--input", gbk, "--source-encoding", "gbk", "--output-encoding", "utf-8",
              "--out", gbk_out, "--audit", os.path.join(TMP, "gbk-audit.json"))
with open(gbk_out, encoding="utf-8") as fh:
    decoded = fh.read()
add("convert正向:显式编码转换无乱码", rc == 0 and "样品甲" in decoded, str(d) + decoded)

# audit：结果、质量报告和真实清洗表三方对账。
cleaned = text("cleaned.csv", "id,value\n1,10\n2,\n3,30\n")
report = {"report_version": "qr-1", "case_id": "case-demo", "snapshot": "snap-demo",
          "rows_before": 4, "rows_after": 3, "missing_by_field": {"value": 1},
          "missing_tokens_by_field": {"value": ["", "-999"]},
          "duplicate_groups": 1, "outliers": 0, "conversion_count": 0}
RESULT = {"case_id": "case-demo", "status": "issues",
          "questions": [{"id": "Q1", "answer": "保留缺失标记", "evidence": ["cleaned.csv:line 3", "quality.json:missing_by_field"]}],
          "run": {"skill_version": "3.0.0", "tool_version": "3.0.0", "ruleset_version": "rules-1",
                  "dictionary_version": "dict-1", "python_version": sys.version.split()[0],
                  "started_at": "2026-01-01T00:00:00Z", "random_seed": 0},
          "lineage": {"snapshot": "snap-demo", "inputs": [{"path": csvp, "sha256": checksum(csvp)}]},
          "rule_trace": [{"field": "id", "rule": "retain original identifier", "rationale": "row lineage",
                          "source": "dictionary.fields.id"},
                         {"field": "value", "rule": "blank remains missing", "rationale": "not zero",
                          "source": "dictionary.fields.value"}],
          "quality_summary": {k: report[k] for k in ("rows_before", "rows_after", "missing_by_field", "duplicate_groups", "outliers", "conversion_count")},
          "unchecked": [], "sources": [csvp], "uncertainty": [], "change_log": [],
          "artifacts": [{"path": cleaned, "sha256": checksum(cleaned), "type": "cleaned_table"}]}
rp = dump("quality.json", report)
rc, d = clean("audit", dump("result-good.json", RESULT), "--cleaned", cleaned, "--report", rp)
add("audit正向:三方数字一致零误杀", rc == 0 and d.get("cleaned_rows") == 3, str(d))
bad_result = copy.deepcopy(RESULT)
bad_result["quality_summary"]["rows_after"] = 2
rc, d = clean("audit", dump("result-count-bad.json", bad_result), "--cleaned", cleaned, "--report", rp)
add("audit变异:报告与结果行数不一致必命中", rc == 1 and any(x["code"] == "REPORT_RESULT_MISMATCH" for x in d.get("errors", [])), str(d))
bad_report = copy.deepcopy(report)
bad_report["missing_by_field"]["value"] = 0
rc, d = clean("audit", dump("result-good-2.json", RESULT), "--cleaned", cleaned, "--report", dump("quality-bad.json", bad_report))
add("audit变异:报告与清洗表缺失数不一致必命中", rc == 1 and any(x["code"] in {"MISSING_COUNT_MISMATCH", "REPORT_RESULT_MISMATCH"} for x in d.get("errors", [])), str(d))
bad_result = copy.deepcopy(RESULT)
bad_result["run"].pop("tool_version")
rc, d = clean("audit", dump("result-version-bad.json", bad_result), "--cleaned", cleaned, "--report", rp)
add("audit变异:缺工具版本必命中", rc == 1 and any(x["code"] == "VERSION_FIELD_MISSING" for x in d.get("errors", [])), str(d))
bad_result = copy.deepcopy(RESULT)
bad_result["rule_trace"][0].pop("source")
rc, d = clean("audit", dump("result-source-bad.json", bad_result), "--cleaned", cleaned, "--report", rp)
add("audit变异:字段规则无来源定位必命中", rc == 1 and any(x["code"] == "RULE_NOT_TRACEABLE" for x in d.get("errors", [])), str(d))
bad_result = copy.deepcopy(RESULT)
bad_result["lineage"]["inputs"][0]["sha256"] = "0" * 64
rc, d = clean("audit", dump("result-hash-bad.json", bad_result), "--cleaned", cleaned, "--report", rp)
add("audit变异:输入SHA256造假必命中", rc == 1 and any(x["code"] == "INPUT_HASH_MISMATCH" for x in d.get("errors", [])), str(d))
bad_result = copy.deepcopy(RESULT)
bad_result["rule_trace"] = [bad_result["rule_trace"][1]]
rc, d = clean("audit", dump("result-untraced-field.json", bad_result), "--cleaned", cleaned, "--report", rp)
add("audit变异:清洗表字段无处理规则必命中", rc == 1 and any(x["code"] == "FIELD_RULE_UNTRACED" and x.get("fields") == ["id"] for x in d.get("errors", [])), str(d))

ok = sum(1 for _, condition, _ in checks if condition)
for name, condition, detail in checks:
    print(("PASS" if condition else "FAIL"), name, ("| " + detail if not condition else ""))
print("total %d/%d" % (ok, len(checks)))
sys.exit(0 if ok == len(checks) else 1)
