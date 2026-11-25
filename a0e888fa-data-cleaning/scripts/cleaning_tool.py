#!/usr/bin/env python3
"""字段级清洗规则、跨表键审计、可逆转换和报告一致性检查；仅用 Python 标准库。

  plan DICTIONARY.json [--csv DATA.csv]
  keys LEFT.csv RIGHT.csv --left-key ID --right-key SAMPLE_ID
  convert PLAN.json --input DATA.csv --out CLEANED.csv --audit AUDIT.json
          [--source-encoding ENCODING] [--output-encoding ENCODING]
  audit RESULT.json --cleaned CLEANED.csv --report QUALITY.json

退出码：0=检查通过；1=发现数据/契约问题；2=命令行用法错误。所有结果均为 JSON。
"""
import csv
import datetime
import decimal
import hashlib
import io
import json
import math
import os
import sys
import tempfile
import unicodedata

TOOL_VERSION = "3.0.0"
D = decimal.Decimal
decimal.getcontext().prec = 50


def emit(obj, code=0):
    try:
        print(json.dumps(obj, ensure_ascii=False, allow_nan=False))
    except (TypeError, ValueError) as exc:
        print(json.dumps({"ok": False, "error_code": "NON_JSON_RESULT", "error": str(exc)}, ensure_ascii=False))
        return 1
    return code


def load_json(path):
    with open(path, "r", encoding="utf-8") as fh:
        obj = json.load(fh)
    if not isinstance(obj, dict):
        raise ValueError("JSON 顶层必须是对象")
    return obj


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(65536), b""):
            h.update(block)
    return h.hexdigest()


def failure(code, message, **extra):
    obj = {"ok": False, "error_code": code, "error": message, "tool_version": TOOL_VERSION}
    obj.update(extra)
    return obj


def read_csv(path, encoding="auto"):
    """严格解码；不以 latin-1 静默吞掉乱码。保留原始字符串和 CSV 行号。"""
    raw = open(path, "rb").read()
    if b"\x00" in raw[:4096] and not raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        raise ValueError("FILE_CORRUPT: CSV 含 NUL 字节")
    attempts = [encoding] if encoding != "auto" else (
        ["utf-8-sig"] if raw.startswith(b"\xef\xbb\xbf") else
        ["utf-16"] if raw.startswith((b"\xff\xfe", b"\xfe\xff")) else
        ["utf-8", "gb18030"])
    last = None
    for enc in attempts:
        try:
            text = raw.decode(enc, errors="strict")
            if "\ufffd" in text:
                raise ValueError("ENCODING_CORRUPT: 文本含 U+FFFD 替换字符")
            reader = csv.DictReader(io.StringIO(text, newline=""), strict=True)
            fields = reader.fieldnames
            if not fields or any(x is None or x == "" for x in fields):
                raise ValueError("FILE_CORRUPT: 表头为空")
            if len(fields) != len(set(fields)):
                raise ValueError("FILE_CORRUPT: 表头字段重复")
            rows = []
            for line_no, row in enumerate(reader, 2):
                if None in row or any(isinstance(v, list) for v in row.values()):
                    raise ValueError("FILE_CORRUPT: 第 %d 行字段数与表头不符" % line_no)
                row["_csv_line"] = line_no
                rows.append(row)
            return rows, fields, enc
        except (UnicodeDecodeError, UnicodeError) as exc:
            last = exc
            continue
        except csv.Error as exc:
            raise ValueError("FILE_CORRUPT: CSV 语法错误: %s" % exc)
    raise ValueError("ENCODING_UNKNOWN: 严格解码失败；请明确 source-encoding（%s）" % last)


def clean_row(row):
    return {k: v for k, v in row.items() if k != "_csv_line"}


def is_missing(value, tokens):
    return str(value if value is not None else "").strip() in {str(x) for x in tokens}


def cmd_plan(dictionary_path, csv_path=None):
    try:
        dictionary = load_json(dictionary_path)
        fields = dictionary.get("fields")
        if not isinstance(fields, dict) or not fields:
            return emit(failure("DICTIONARY_INVALID", "dictionary.fields 必须是非空对象"), 1)
        version = str(dictionary.get("dictionary_version") or "").strip()
        if not version:
            return emit(failure("VERSION_MISSING", "缺 dictionary_version"), 1)
        rows, headers = ([], list(fields))
        encoding = "not_read"
        if csv_path:
            rows, headers, encoding = read_csv(csv_path)
            if not rows:
                return emit(failure("EMPTY_TABLE", "空表：保留字段规则，不计算或填补"), 1)
        blockers, warnings, plans = [], [], []
        for name in dict.fromkeys(list(fields) + headers):
            spec = fields.get(name)
            if not isinstance(spec, dict):
                blockers.append({"code": "FIELD_SEMANTICS_UNKNOWN", "field": name,
                                 "question": "请补充字段含义、角色、单位与缺失令牌；暂不计算"})
                plans.append({"field": name, "action": "quarantine_pending_dictionary",
                              "source": "CSV.header", "requires_confirmation": True})
                continue
            role = str(spec.get("role") or "unknown")
            semantic = str(spec.get("semantic") or "").strip()
            unit = str(spec.get("unit") or "").strip()
            tokens = spec.get("missing_tokens", ["", "NA", "N/A", "-999"])
            if not isinstance(tokens, list):
                return emit(failure("DICTIONARY_INVALID", "%s.missing_tokens 必须是数组" % name), 1)
            source = "dictionary.fields.%s" % name
            item = {"field": name, "semantic": semantic, "role": role, "unit": unit or None,
                    "missing_tokens": tokens, "source": source,
                    "missing_policy": "flag_and_exclude_not_impute",
                    "outlier_policy": "physical_range_then_IQR_flag_no_auto_delete",
                    "requires_confirmation": False}
            if not semantic or role == "unknown":
                blockers.append({"code": "FIELD_SEMANTICS_UNKNOWN", "field": name,
                                 "question": "字段 %s 的 semantic/role 是什么？" % name})
                item["requires_confirmation"] = True
            if role == "measurement":
                if not unit or unit.lower() in {"?", "unknown", "未知", "none"}:
                    blockers.append({"code": "UNIT_UNKNOWN", "field": name,
                                     "question": "字段 %s 的单位与目标单位是什么？" % name})
                    item["conversion"] = "blocked_until_unit_confirmed"
                else:
                    item["conversion"] = {"from_unit": unit, "target_unit": spec.get("target_unit") or unit,
                                           "rule": "Decimal_exact_with_original_and_inverse_audit"}
                if spec.get("physical_range") is not None:
                    item["physical_range"] = spec["physical_range"]
            elif role == "identifier":
                item["dedup_policy"] = "normalized_real_key; retain_by_explicit_version_rule; never_whole_row_only"
            elif role == "categorical":
                item["numeric_policy"] = "coded_category_not_continuous"
                item["codes"] = spec.get("codes", {})
            else:
                item["numeric_policy"] = "not_assumed_numeric"
            if csv_path and name not in headers:
                blockers.append({"code": "FIELD_NOT_FOUND", "field": name,
                                 "question": "材料中未找到字段 %s；若被排除请记录原因" % name})
            if csv_path and name in headers:
                missing_lines = [r["_csv_line"] for r in rows if is_missing(r.get(name), tokens)]
                item["missing_count"] = len(missing_lines)
                item["missing_row_locators"] = missing_lines[:100]
                if len(missing_lines) == len(rows):
                    blockers.append({"code": "ALL_COLUMN_MISSING", "field": name,
                                     "question": "字段 %s 全列缺失；请补数或终止该字段分析，禁止填补" % name})
                    item["action"] = "block_field_all_missing"
                elif missing_lines:
                    item["action"] = "retain_original_and_add_missing_flag"
                    warnings.append({"code": "MISSING_VALUES", "field": name, "count": len(missing_lines)})
            plans.append(item)
        result = {"ok": not blockers, "tool_version": TOOL_VERSION, "dictionary_version": version,
                  "source_encoding": encoding, "field_rules": plans,
                  "blockers": blockers, "warnings": warnings,
                  "rule_contract": "missing/outliers/duplicates/conversions all retain row locators and originals"}
        return emit(result, 0 if not blockers else 1)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        code = "PERMISSION_DENIED" if isinstance(exc, PermissionError) else "INPUT_INVALID"
        return emit(failure(code, str(exc)), 1)


def norm_key(value):
    return " ".join(unicodedata.normalize("NFKC", str(value or "")).strip().casefold().split())


def cmd_keys(left_path, right_path, left_key, right_key):
    try:
        left, lf, le = read_csv(left_path)
        right, rf, re = read_csv(right_path)
        if left_key not in lf or right_key not in rf:
            return emit(failure("KEY_NOT_FOUND", "指定键不在表头", left_fields=lf, right_fields=rf), 1)
        errors, issues = [], []
        maps, unmatched = {}, {}
        for side, rows, key in (("left", left, left_key), ("right", right, right_key)):
            groups = {}
            for row in rows:
                raw = row.get(key)
                nk = norm_key(raw)
                groups.setdefault(nk, []).append({"row": row["_csv_line"], "original": raw})
            maps[side] = groups
            blank = [x for x in groups.get("", [])]
            if blank:
                errors.append({"code": "KEY_MISSING", "table": side, "rows": blank})
            dups = [{"normalized_key": k, "occurrences": v} for k, v in groups.items() if k and len(v) > 1]
            if dups:
                errors.append({"code": "PRIMARY_KEY_CONFLICT", "table": side,
                               "action": "不要连接或静默去重；先给保留规则", "duplicates": dups})
        lk = set(maps["left"]) - {""}
        rk = set(maps["right"]) - {""}
        unmatched = {"left_only": sorted(lk - rk), "right_only": sorted(rk - lk)}
        if unmatched["left_only"] or unmatched["right_only"]:
            issues.append({"code": "UNMATCHED_KEYS", "action": "join 采用明确策略；禁止当作 0", **unmatched})
        conflicts = []
        common = [x for x in lf if x in rf and x not in {left_key, right_key}]
        if len(lk & rk) and not any(e["code"] == "PRIMARY_KEY_CONFLICT" for e in errors):
            for key in sorted(lk & rk):
                lrow = left[[r["_csv_line"] for r in left].index(maps["left"][key][0]["row"])]
                rrow = right[[r["_csv_line"] for r in right].index(maps["right"][key][0]["row"])]
                for col in common:
                    if norm_key(lrow.get(col)) != norm_key(rrow.get(col)):
                        conflicts.append({"normalized_key": key, "field": col,
                                          "left": {"row": lrow["_csv_line"], "value": lrow.get(col)},
                                          "right": {"row": rrow["_csv_line"], "value": rrow.get(col)}})
        if conflicts:
            errors.append({"code": "CROSS_TABLE_VALUE_CONFLICT", "action": "按来源版本裁决并保留两值",
                           "conflicts": conflicts})
        normalization = []
        for side, rows, key in (("left", left, left_key), ("right", right, right_key)):
            for row in rows:
                if str(row.get(key)) != norm_key(row.get(key)):
                    normalization.append({"table": side, "row": row["_csv_line"],
                                          "original": row.get(key), "normalized": norm_key(row.get(key))})
        out = {"ok": not errors, "tool_version": TOOL_VERSION,
               "inputs": {"left": {"path": left_path, "sha256": sha256(left_path), "encoding": le},
                          "right": {"path": right_path, "sha256": sha256(right_path), "encoding": re}},
               "keys": {"left": left_key, "right": right_key,
                        "normalization": "NFKC + trim + collapse-space + casefold; originals retained"},
               "rows": {"left": len(left), "right": len(right), "matched_keys": len(lk & rk)},
               "normalization_map": normalization, "errors": errors, "issues": issues}
        return emit(out, 0 if not errors else 1)
    except (OSError, ValueError) as exc:
        code = "PERMISSION_DENIED" if isinstance(exc, PermissionError) else "INPUT_INVALID"
        return emit(failure(code, str(exc)), 1)


# 浓度统一折算到 g/L；Decimal 十进制比例保证有限小数换算不静默舍入。
UNIT_SCALE = {
    "g/l": ("concentration", D("1")), "kg/l": ("concentration", D("1000")),
    "mg/l": ("concentration", D("0.001")), "ug/l": ("concentration", D("0.000001")),
    "μg/l": ("concentration", D("0.000001")), "µg/l": ("concentration", D("0.000001")),
    "ng/l": ("concentration", D("0.000000001")), "g/ml": ("concentration", D("1000")),
    "mg/ml": ("concentration", D("1")), "ug/ml": ("concentration", D("0.001")),
    "μg/ml": ("concentration", D("0.001")), "µg/ml": ("concentration", D("0.001")),
    "kg": ("mass", D("1")), "g": ("mass", D("0.001")), "mg": ("mass", D("0.000001")),
    "ug": ("mass", D("0.000000001")), "μg": ("mass", D("0.000000001")), "µg": ("mass", D("0.000000001")),
    "l": ("volume", D("1")), "ml": ("volume", D("0.001")), "ul": ("volume", D("0.000001")),
    "μl": ("volume", D("0.000001")), "µl": ("volume", D("0.000001")),
}


def canonical_unit(unit):
    return str(unit or "").strip().replace("／", "/").replace(" ", "").lower()


def dec_text(value):
    if value == 0:
        return "0"
    return format(value.normalize(), "f")


def atomic_bytes(path, data):
    target = os.path.abspath(path)
    directory = os.path.dirname(target) or "."
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".cleaning-", dir=directory)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, target)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def cmd_convert(plan_path, input_path, out_path, audit_path, source_encoding="auto", output_encoding="utf-8"):
    try:
        if os.path.abspath(input_path) in {os.path.abspath(out_path), os.path.abspath(audit_path)}:
            return emit(failure("UNSAFE_OVERWRITE", "不得覆盖原始输入；out/audit 必须另设路径"), 1)
        if os.path.abspath(out_path) == os.path.abspath(audit_path):
            return emit(failure("OUTPUT_CONFLICT", "out 与 audit 不能是同一路径"), 1)
        plan = load_json(plan_path)
        if not str(plan.get("plan_version") or "").strip():
            return emit(failure("VERSION_MISSING", "转换计划缺 plan_version"), 1)
        operations = plan.get("operations", [])
        if not isinstance(operations, list):
            return emit(failure("PLAN_INVALID", "operations 必须是数组"), 1)
        rows, fields, actual_encoding = read_csv(input_path, source_encoding)
        if not rows:
            return emit(failure("EMPTY_TABLE", "空表：拒绝产生貌似成功的转换文件"), 1)
        output_fields = list(fields)
        for op in operations:
            col = op.get("column")
            if col not in fields:
                return emit(failure("FIELD_NOT_FOUND", "转换字段不存在: %s" % col), 1)
            original_col = col + "__original"
            if original_col in fields:
                return emit(failure("FIELD_CONFLICT", "原始值保留列已存在: %s" % original_col), 1)
            if original_col not in output_fields:
                output_fields.append(original_col)
        changes = []
        for row in rows:
            for op in operations:
                col = op["column"]
                original = row.get(col, "")
                tokens = op.get("missing_tokens", plan.get("missing_tokens", ["", "NA", "N/A", "-999"]))
                if is_missing(original, tokens):
                    continue
                unit_col = op.get("unit_column")
                from_raw = row.get(unit_col) if unit_col else op.get("from_unit")
                to_raw = op.get("to_unit")
                src, dst = canonical_unit(from_raw), canonical_unit(to_raw)
                if src not in UNIT_SCALE or dst not in UNIT_SCALE:
                    return emit(failure("UNIT_UNKNOWN", "不支持或缺失单位", row=row["_csv_line"],
                                        field=col, from_unit=from_raw, to_unit=to_raw,
                                        question="请确认单位；本行不换算、不猜比例"), 1)
                sd, sf = UNIT_SCALE[src]
                dd, df = UNIT_SCALE[dst]
                if sd != dd:
                    return emit(failure("UNIT_DIMENSION_MISMATCH", "量纲不同", row=row["_csv_line"],
                                        from_unit=from_raw, to_unit=to_raw), 1)
                try:
                    original_dec = D(str(original).strip())
                    if not original_dec.is_finite():
                        raise decimal.InvalidOperation
                    converted = original_dec * sf / df
                    roundtrip = converted * df / sf
                    if roundtrip != original_dec:
                        raise ArithmeticError("Decimal 逆转换不等于原值")
                except (decimal.InvalidOperation, ValueError, ArithmeticError) as exc:
                    return emit(failure("NUMERIC_CONVERSION_FAILED", str(exc), row=row["_csv_line"],
                                        field=col, original=original), 1)
                converted_text = dec_text(converted)
                changes.append({"row": row["_csv_line"], "field": col, "original": original,
                                "converted": converted_text, "from_unit": from_raw, "to_unit": to_raw,
                                "formula": "converted=original*%s/%s" % (sf, df),
                                "inverse_formula": "original=converted*%s/%s" % (df, sf),
                                "roundtrip_exact": True})
        by_cell = {(x["row"], x["field"]): x for x in changes}
        buffer = io.StringIO(newline="")
        writer = csv.DictWriter(buffer, fieldnames=output_fields, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        for row in rows:
            outrow = clean_row(row)
            for op in operations:
                col = op["column"]
                outrow[col + "__original"] = row.get(col, "")
                cell = by_cell.get((row["_csv_line"], col))
                if cell:
                    outrow[col] = cell["converted"]
            writer.writerow(outrow)
        data = buffer.getvalue().encode(output_encoding, errors="strict")
        atomic_bytes(out_path, data)
        audit = {"ok": True, "tool_version": TOOL_VERSION, "plan_version": plan["plan_version"],
                 "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                 "input": {"path": input_path, "sha256": sha256(input_path), "encoding": actual_encoding},
                 "output": {"path": out_path, "sha256": sha256(out_path), "encoding": output_encoding},
                 "encoding_conversion": {"from": actual_encoding, "to": output_encoding,
                                          "original_file_retained": True},
                 "precision": "decimal.Context(prec=50); original text retained in __original; exact numeric inverse checked",
                 "conversion_count": len(changes), "changes": changes}
        atomic_bytes(audit_path, (json.dumps(audit, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8"))
        return emit({"ok": True, "tool_version": TOOL_VERSION, "out": out_path, "audit": audit_path,
                     "conversion_count": len(changes), "all_roundtrips_exact": True})
    except (OSError, ValueError, ArithmeticError, UnicodeError, json.JSONDecodeError) as exc:
        code = "PERMISSION_DENIED" if isinstance(exc, PermissionError) else "CONVERSION_FAILED"
        return emit(failure(code, str(exc)), 1)


def cmd_audit(result_path, cleaned_path, report_path):
    try:
        result, report = load_json(result_path), load_json(report_path)
        rows, headers, encoding = read_csv(cleaned_path)
        errors = []
        for key in ("case_id", "status", "questions", "run", "lineage", "rule_trace", "quality_summary",
                    "unchecked", "sources", "uncertainty", "change_log", "artifacts"):
            if key not in result:
                errors.append({"code": "RESULT_FIELD_MISSING", "field": key})
        run = result.get("run") or {}
        for key in ("skill_version", "tool_version", "ruleset_version", "dictionary_version", "python_version",
                    "started_at", "random_seed"):
            if run.get(key) in (None, ""):
                errors.append({"code": "VERSION_FIELD_MISSING", "field": "run." + key})
        lineage = result.get("lineage") or {}
        if not lineage.get("snapshot"):
            errors.append({"code": "SNAPSHOT_MISSING", "field": "lineage.snapshot"})
        def verify_record(item, kind):
            if not isinstance(item, dict) or not item.get("path") or not item.get("sha256"):
                errors.append({"code": kind + "_HASH_MISSING", "item": item})
                return
            path = item["path"]
            candidate = path if os.path.isabs(path) else os.path.join(os.path.dirname(os.path.abspath(result_path)), path)
            if not os.path.isfile(candidate):
                errors.append({"code": kind + "_FILE_NOT_FOUND", "path": path})
            elif sha256(candidate) != item["sha256"]:
                errors.append({"code": kind + "_HASH_MISMATCH", "path": path})
        for item in lineage.get("inputs", []):
            verify_record(item, "INPUT")
        for item in result.get("artifacts", []):
            verify_record(item, "ARTIFACT")
        if not result.get("rule_trace"):
            errors.append({"code": "FIELD_RULES_MISSING", "field": "rule_trace"})
        for i, rule in enumerate(result.get("rule_trace", [])):
            for key in ("field", "rule", "rationale", "source"):
                if rule.get(key) in (None, ""):
                    errors.append({"code": "RULE_NOT_TRACEABLE", "index": i, "field": key})
        traced_fields = {rule.get("field") for rule in result.get("rule_trace", [])}
        untraced = [field for field in headers if field not in traced_fields and not field.endswith("__original")]
        if untraced:
            errors.append({"code": "FIELD_RULE_UNTRACED", "fields": untraced,
                           "action": "每个原始字段都要写处理规则；未使用也要声明 retain/exclude 及理由"})
        for i, q in enumerate(result.get("questions", [])):
            if not q.get("evidence"):
                errors.append({"code": "EVIDENCE_MISSING", "index": i})
        for key in ("report_version", "case_id", "snapshot", "rows_before", "rows_after", "missing_by_field"):
            if key not in report:
                errors.append({"code": "REPORT_FIELD_MISSING", "field": key})
        summary = result.get("quality_summary") or {}
        for key in ("rows_before", "rows_after", "missing_by_field", "duplicate_groups", "outliers", "conversion_count"):
            if key in report and summary.get(key) != report.get(key):
                errors.append({"code": "REPORT_RESULT_MISMATCH", "field": key,
                               "result": summary.get(key), "report": report.get(key)})
        if report.get("case_id") != result.get("case_id"):
            errors.append({"code": "CASE_ID_MISMATCH"})
        if report.get("snapshot") != lineage.get("snapshot"):
            errors.append({"code": "SNAPSHOT_MISMATCH"})
        if report.get("rows_after") != len(rows):
            errors.append({"code": "CLEANED_ROW_COUNT_MISMATCH", "report": report.get("rows_after"), "actual": len(rows)})
        missing_tokens = report.get("missing_tokens_by_field", {})
        actual_missing = {}
        for col in headers:
            tokens = missing_tokens.get(col, ["", "NA", "N/A", "-999"])
            n = sum(is_missing(row.get(col), tokens) for row in rows)
            if n or col in report.get("missing_by_field", {}):
                actual_missing[col] = n
        if actual_missing != report.get("missing_by_field", {}):
            errors.append({"code": "MISSING_COUNT_MISMATCH", "report": report.get("missing_by_field"), "actual": actual_missing})
        out = {"ok": not errors, "tool_version": TOOL_VERSION, "case_id": result.get("case_id"),
               "cleaned_rows": len(rows), "encoding": encoding, "errors": errors,
               "verified": ["result↔report counts", "report↔cleaned rows/missing", "field rule locators",
                            "versions/snapshot/input hashes/question evidence"]}
        return emit(out, 0 if not errors else 1)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        code = "PERMISSION_DENIED" if isinstance(exc, PermissionError) else "AUDIT_INPUT_INVALID"
        return emit(failure(code, str(exc)), 1)


def main(argv):
    if not argv:
        print(__doc__)
        return 2
    try:
        cmd = argv[0]
        if cmd == "plan" and len(argv) >= 2:
            cp = argv[argv.index("--csv") + 1] if "--csv" in argv else None
            return cmd_plan(argv[1], cp)
        if cmd == "keys" and len(argv) >= 3:
            lk = argv[argv.index("--left-key") + 1]
            rk = argv[argv.index("--right-key") + 1]
            return cmd_keys(argv[1], argv[2], lk, rk)
        if cmd == "convert" and len(argv) >= 2:
            def option(name, default=None):
                return argv[argv.index(name) + 1] if name in argv else default
            required = [option("--input"), option("--out"), option("--audit")]
            if not all(required):
                raise ValueError("convert 需要 --input --out --audit")
            return cmd_convert(argv[1], *required, option("--source-encoding", "auto"),
                               option("--output-encoding", "utf-8"))
        if cmd == "audit" and len(argv) >= 2:
            if "--cleaned" not in argv or "--report" not in argv:
                raise ValueError("audit 需要 --cleaned --report")
            return cmd_audit(argv[1], argv[argv.index("--cleaned") + 1], argv[argv.index("--report") + 1])
        print(__doc__)
        return 2
    except (ValueError, IndexError) as exc:
        return emit(failure("USAGE_ERROR", str(exc)), 2)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
