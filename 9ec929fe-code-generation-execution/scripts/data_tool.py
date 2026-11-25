#!/usr/bin/env python3
"""科研代码执行与独立复算（仅 Python 标准库）。

profile CSV                                  数据画像与输入 SHA256
recheck RESULT --csv CSV                     按显式口径重算聚合值及分组完备性
chartcheck RESULT --csv CSV                  逐项重算图中 series 并核对图件哈希
run CODE.py --log RUN.json [--input F] [--require F] [--timeout S] [--seed N] [-- ARG...]
sqlcheck RESULT --db DB.sqlite [--timeout S] 只读重跑 SQL 并逐行核对查询结果
schema RESULT                                版本、证据、覆盖率与增益契约校验

退出码：0 通过；1 校验/执行失败；2 调用错误。机器输出均为 stdout 的单个 JSON。
"""
import argparse
import csv
import hashlib
import importlib.metadata
import json
import math
import os
import platform
import re
import sqlite3
import statistics
import subprocess
import sys
import time
from datetime import datetime, timezone

VERSION = "2.0.0"
DEFAULT_MISSING = {"", "na", "n/a", "nan", "null", "none", "."}
OPS = {"sum", "count", "row_count", "mean", "min", "max", "median", "stdev", "sem"}
HEX64 = re.compile(r"^[0-9a-f]{64}$")


def emit(obj, rc=0):
    print(json.dumps(obj, ensure_ascii=False, allow_nan=False, sort_keys=True))
    return rc


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def load_json(path):
    with open(path, encoding="utf-8") as f:
        obj = json.load(f)
    if not isinstance(obj, dict):
        raise ValueError("JSON 顶层必须是对象")
    return obj


def number(value):
    """严格数值解析；不把非法文本、inf 或随便去逗号的字符串静默当数。"""
    if value is None or isinstance(value, bool):
        raise ValueError("非数值")
    text = str(value).strip()
    if not re.match(r"^[+-]?(?:(?:\d+(?:\.\d*)?)|(?:\.\d+))(?:[eE][+-]?\d+)?$", text):
        raise ValueError("非数值: %r" % text)
    result = float(text)
    if not math.isfinite(result):
        raise ValueError("非有限数值: %r" % text)
    return result


def read_csv(path):
    last = None
    for encoding in ("utf-8-sig", "gb18030"):
        try:
            with open(path, encoding=encoding, newline="") as f:
                reader = csv.DictReader(f)
                fields = reader.fieldnames
                if not fields or any(x is None or x == "" for x in fields):
                    raise ValueError("缺表头或存在空列名")
                if len(set(fields)) != len(fields):
                    raise ValueError("存在重复列名")
                rows = list(reader)
            if any(None in row for row in rows):
                raise ValueError("存在超出表头宽度的行")
            return rows, fields, encoding
        except UnicodeDecodeError as exc:
            last = exc
    raise ValueError("CSV 解码失败: %s" % last)


def close(actual, expected, tolerance):
    try:
        expected = number(expected)
    except ValueError:
        return False
    return math.isclose(actual, expected, rel_tol=tolerance, abs_tol=tolerance)


def select_rows(rows, fields, spec):
    selected = list(rows)
    where = spec.get("where", {})
    if not isinstance(where, dict):
        raise ValueError("where 必须是 {column: exact_value} 对象")
    for col in where:
        if col not in fields:
            raise ValueError("筛选缺列: %s" % col)
    selected = [r for r in selected if all(str(r.get(c, "")) == str(v) for c, v in where.items())]
    dedup = spec.get("drop_duplicates", False)
    if dedup:
        keys = fields if dedup is True else dedup
        if not isinstance(keys, list) or not keys or any(k not in fields for k in keys):
            raise ValueError("drop_duplicates 必须是 true 或有效列名数组")
        seen, unique = set(), []
        for row in selected:
            key = tuple(row[k] for k in keys)
            if key not in seen:
                seen.add(key)
                unique.append(row)
        selected = unique
    return selected


def compute_aggregate(rows, fields, spec):
    """返回 (值, 诊断)。非法非缺失数值直接报错，不以缺失名义丢弃。"""
    op = str(spec.get("op", "")).lower()
    if op not in OPS:
        raise ValueError("不支持的 op: %s" % op)
    selected = select_rows(rows, fields, spec)
    group_by = spec.get("group_by")
    groups = group_by if isinstance(group_by, list) else ([group_by] if group_by else [])
    if any(g not in fields for g in groups):
        raise ValueError("分组缺列")
    col = spec.get("column")
    if op != "row_count" and col not in fields:
        raise ValueError("聚合缺列: %s" % col)
    missing = {str(x).strip().casefold() for x in spec.get("missing_values", sorted(DEFAULT_MISSING))}
    buckets = {}
    diagnostics = {"input_rows": len(rows), "selected_rows": len(selected), "excluded_missing": 0}
    for row in selected:
        key = tuple(str(row[g]) for g in groups)
        if op == "row_count":
            buckets.setdefault(key, []).append(None)
            continue
        raw = row.get(col)
        if str(raw).strip().casefold() in missing:
            diagnostics["excluded_missing"] += 1
            continue
        try:
            val = number(raw)
        except ValueError as exc:
            raise ValueError("列 %s 含未声明的脏数值 %r" % (col, raw)) from exc
        buckets.setdefault(key, []).append(val)
    # 无分组且没有可用值时也必须产生一个桶，避免把空查询误报为通过。
    if not groups and not buckets:
        buckets[()] = []

    def calculate(vals):
        if op == "row_count":
            return len(vals)
        if op == "count":
            return len(vals)
        if not vals:
            raise ValueError("聚合口径下没有可用数值")
        if op == "sum":
            value = math.fsum(vals)
        elif op == "mean":
            value = math.fsum(vals) / len(vals)
        elif op == "min":
            value = min(vals)
        elif op == "max":
            value = max(vals)
        elif op == "median":
            value = statistics.median(vals)
        elif op == "stdev":
            if len(vals) < 2:
                raise ValueError("stdev 至少需要 2 个值")
            value = statistics.stdev(vals)
        elif op == "sem":
            if len(vals) < 2:
                raise ValueError("sem 至少需要 2 个值")
            value = statistics.stdev(vals) / math.sqrt(len(vals))
        else:
            raise AssertionError(op)
        if not math.isfinite(value):
            raise ValueError("数值溢出/非有限结果")
        return value

    if not groups:
        return calculate(buckets[()]), diagnostics
    computed = {"|".join(k) if len(k) > 1 else k[0]: calculate(v) for k, v in buckets.items()}
    return computed, diagnostics


def compare_computed(computed, claimed, tolerance, context):
    errors = []
    if isinstance(computed, dict):
        if not isinstance(claimed, dict):
            return [dict(context, error="分组聚合的 value 必须是对象")]
        for key in sorted(set(computed) | set(claimed)):
            if key not in computed:
                errors.append(dict(context, group=key, error="上报了数据中不存在的组"))
            elif key not in claimed:
                errors.append(dict(context, group=key, error="漏报数据中的组", recomputed=computed[key]))
            elif not close(computed[key], claimed[key], tolerance):
                errors.append(dict(context, group=key, error="数值不一致",
                                   recomputed=computed[key], reported=claimed[key]))
    elif not close(computed, claimed, tolerance):
        errors.append(dict(context, error="数值不一致", recomputed=computed, reported=claimed))
    return errors


def check_items(result, rows, fields, items, default_tolerance):
    errors, checked, diagnostics = [], 0, []
    for i, spec in enumerate(items):
        context = {"id": spec.get("id", "aggregate[%d]" % i), "column": spec.get("column"),
                   "op": spec.get("op")}
        try:
            computed, diag = compute_aggregate(rows, fields, spec)
            diag["id"] = context["id"]
            diagnostics.append(diag)
            checked += len(computed) if isinstance(computed, dict) else 1
            errors.extend(compare_computed(computed, spec.get("value"),
                                           float(spec.get("tolerance", default_tolerance)), context))
        except (ValueError, OverflowError) as exc:
            errors.append(dict(context, error=str(exc)))
    return errors, checked, diagnostics


def cmd_profile(path):
    rows, fields, encoding = read_csv(path)
    if not rows:
        return emit({"ok": False, "error": "空表", "sha256": sha256(path)}, 1)
    profiles = []
    for col in fields:
        vals = [row[col] for row in rows]
        present = [v for v in vals if str(v).strip() != ""]
        nums, dirty = [], 0
        for val in present:
            try:
                nums.append(number(val))
            except ValueError:
                dirty += 1
        item = {"column": col, "missing": len(vals) - len(present),
                "missing_pct": round(100 * (len(vals) - len(present)) / len(vals), 6),
                "n_unique": len(set(present)), "numeric": bool(present) and not dirty,
                "dirty_numeric_count": dirty}
        if present and not dirty:
            item.update(min=min(nums), max=max(nums))
            ordered = sorted(nums)
            q1, q3 = statistics.quantiles(ordered, n=4, method="inclusive")[0::2] if len(ordered) > 1 else (ordered[0], ordered[0])
            iqr = q3 - q1
            low, high = q1 - 1.5 * iqr, q3 + 1.5 * iqr
            outliers = [x for x in nums if x < low or x > high]
            item["outliers_iqr"] = len(outliers)
            item["outlier_examples"] = outliers[:5]
            magnitudes = [abs(x) for x in nums if x != 0]
            if magnitudes and max(magnitudes) / min(magnitudes) >= 1000:
                item["scale_warning"] = "非零绝对值量级跨 >=3 个数量级；须按字典确认，不自动换算"
        profiles.append(item)
    duplicate_rows = len(rows) - len({tuple(row[c] for c in fields) for row in rows})
    return emit({"ok": True, "tool_version": VERSION, "encoding": encoding, "rows": len(rows),
                 "cols": len(fields), "duplicate_rows": duplicate_rows,
                 "sha256": sha256(path), "columns": profiles})


def cmd_recheck(result_path, csv_path, tolerance=1e-9):
    result = load_json(result_path)
    rows, fields, _ = read_csv(csv_path)
    expected_hash = result.get("lineage", {}).get("source_sha256")
    actual_hash = sha256(csv_path)
    errors, checked, diagnostics = check_items(result, rows, fields, result.get("aggregates", []), tolerance)
    if expected_hash and expected_hash != actual_hash:
        errors.append({"id": "lineage.source_sha256", "error": "输入快照哈希不一致",
                       "expected": expected_hash, "actual": actual_hash})
    if not result.get("aggregates"):
        errors.append({"id": "aggregates", "error": "没有声明可复算聚合值；缺项须标 not_checked"})
    return emit({"ok": not errors, "checked": checked, "source_sha256": actual_hash,
                 "diagnostics": diagnostics, "mismatches": errors}, 0 if not errors else 1)


def cmd_chartcheck(result_path, csv_path):
    result = load_json(result_path)
    rows, fields, _ = read_csv(csv_path)
    errors, checked = [], 0
    figures = result.get("figures", [])
    if not figures:
        errors.append({"id": "figures", "error": "无图件；若任务不要求图须在 coverage.visualization 标 not_checked"})
    for i, fig in enumerate(figures):
        fid = fig.get("id", "figure[%d]" % i)
        for axis in ("x", "y"):
            axis_spec = fig.get("axes", {}).get(axis, {})
            if not axis_spec.get("label"):
                errors.append({"id": fid, "error": "%s 轴缺标目" % axis})
            if axis_spec.get("unit_required", False) and not axis_spec.get("unit"):
                errors.append({"id": fid, "error": "%s 轴缺单位" % axis})
        if not fig.get("caption") or not fig.get("legend") is not None:
            errors.append({"id": fid, "error": "缺独立图注或 legend 字段(无图例时须为空数组)"})
        path = fig.get("path")
        if not path or not os.path.isfile(path):
            errors.append({"id": fid, "error": "图件不存在", "path": path})
        elif fig.get("sha256") != sha256(path):
            errors.append({"id": fid, "error": "图件 SHA256 不一致"})
        items = []
        for j, series in enumerate(fig.get("series", [])):
            item = dict(series)
            item.setdefault("id", "%s.series[%d]" % (fid, j))
            items.append(item)
        if not items:
            errors.append({"id": fid, "error": "图中数值 series 为空，无法逐项复算"})
        item_errors, n, _ = check_items(result, rows, fields, items, 1e-9)
        errors.extend(dict(e, figure=fid) for e in item_errors)
        checked += n
    return emit({"ok": not errors, "checked": checked, "mismatches": errors}, 0 if not errors else 1)


def cmd_run(code, log_path, inputs, requires, timeout, seed, child_args, packages):
    if os.path.exists(log_path):
        raise ValueError("run 日志已存在；每次执行使用新文件名，禁止覆盖失败现场: %s" % log_path)
    started = datetime.now(timezone.utc).isoformat()
    input_records, missing_inputs = [], []
    package_records = {}
    for package in packages:
        try:
            package_records[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            missing_inputs.append({"path": package, "error": "依赖缺失/未在当前解释器安装",
                                   "type": "dependency_missing"})
    for path in inputs:
        try:
            input_records.append({"path": os.path.abspath(path), "sha256": sha256(path),
                                  "bytes": os.path.getsize(path)})
        except OSError as exc:
            missing_inputs.append({"path": path, "error": str(exc)})
    log = {"run_version": "1.0.0", "tool_version": VERSION, "code": os.path.abspath(code),
           "command": [sys.executable, os.path.abspath(code)] + list(child_args),
           "cwd": os.getcwd(), "started_utc": started, "python": sys.version,
           "platform": platform.platform(), "seed": seed, "env": {"PYTHONHASHSEED": str(seed)},
           "packages": package_records, "inputs": input_records, "input_errors": missing_inputs, "artifacts": [],
           "exit_status": None, "timed_out": False}
    try:
        log["code_sha256"] = sha256(code)
    except OSError as exc:
        log["input_errors"].append({"path": code, "error": str(exc)})
    rc = 1
    if not log["input_errors"]:
        env = os.environ.copy()
        env["PYTHONHASHSEED"] = str(seed)
        before = time.monotonic()
        try:
            proc = subprocess.run([sys.executable, os.path.abspath(code)] + list(child_args),
                                  capture_output=True, text=True, timeout=timeout, env=env)
            log["exit_status"] = proc.returncode
            log["stdout"] = proc.stdout[-65536:]
            log["stderr"] = proc.stderr[-65536:]
            rc = proc.returncode
        except subprocess.TimeoutExpired as exc:
            log.update(timed_out=True, exit_status="timeout",
                       stdout=(exc.stdout or b"").decode() if isinstance(exc.stdout, bytes) else (exc.stdout or ""),
                       stderr=(exc.stderr or b"").decode() if isinstance(exc.stderr, bytes) else (exc.stderr or ""))
            rc = 124
        except OSError as exc:
            log["stderr"] = str(exc)
            rc = 126
        log["wall_seconds"] = round(time.monotonic() - before, 6)
    for path in requires:
        try:
            if not os.path.isfile(path) or os.path.getsize(path) == 0:
                raise OSError("必需产物不存在或为空")
            log["artifacts"].append({"path": os.path.abspath(path), "sha256": sha256(path),
                                     "bytes": os.path.getsize(path)})
        except OSError as exc:
            log.setdefault("artifact_errors", []).append({"path": path, "error": str(exc)})
            if rc == 0:
                rc = 1
    log["finished_utc"] = datetime.now(timezone.utc).isoformat()
    log["ok"] = rc == 0 and not log.get("artifact_errors")
    with open(log_path, "x", encoding="utf-8") as f:
        json.dump(log, f, ensure_ascii=False, indent=2, allow_nan=False)
    return emit({"ok": log["ok"], "log": os.path.abspath(log_path), "exit_status": log["exit_status"],
                 "timed_out": log["timed_out"], "artifacts": log["artifacts"],
                 "errors": log.get("input_errors", []) + log.get("artifact_errors", [])},
                0 if log["ok"] else (rc if isinstance(rc, int) and rc else 1))


def normalized_cell(value):
    if value is None:
        return None
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("SQL 返回非有限数")
    return value


def sql_cells_equal(actual, expected):
    if isinstance(actual, (int, float)) and not isinstance(actual, bool):
        try:
            return close(float(actual), expected, 1e-9)
        except (ValueError, TypeError):
            return False
    return actual == expected


def cmd_sqlcheck(result_path, db_path, timeout):
    result = load_json(result_path)
    queries = result.get("queries", [])
    if not queries:
        return emit({"ok": False, "mismatches": [{"error": "queries 为空"}]}, 1)
    uri = "file:" + os.path.realpath(db_path).replace("?", "%3f").replace("#", "%23") + "?mode=ro"
    connection = sqlite3.connect(uri, uri=True, timeout=min(timeout, 5))
    errors, reports = [], []
    try:
        for i, query in enumerate(queries):
            qid = query.get("id", "query[%d]" % i)
            sql = query.get("sql", "")
            if not re.match(r"^\s*(SELECT|WITH)\b", sql, re.I | re.S):
                errors.append({"id": qid, "error": "仅允许 SELECT/WITH"})
                continue
            state = {"failed": False}
            started = time.monotonic()

            def progress():
                if time.monotonic() - started > timeout:
                    state["failed"] = True
                    return 1
                return 0

            connection.set_progress_handler(progress, 1000)
            try:
                cursor = connection.execute(sql)
                columns = [x[0] for x in (cursor.description or [])]
                rows = [tuple(normalized_cell(v) for v in row) for row in cursor.fetchmany(10001)]
                if len(rows) > 10000:
                    raise ValueError("结果超过 10000 行，先聚合或显式 LIMIT")
                expected_columns = query.get("columns")
                expected_rows = query.get("rows")
                if columns != expected_columns:
                    errors.append({"id": qid, "error": "列名/顺序不一致", "actual": columns,
                                   "expected": expected_columns})
                if not isinstance(expected_rows, list) or len(rows) != len(expected_rows):
                    errors.append({"id": qid, "error": "行数不一致", "actual": len(rows),
                                   "expected": len(expected_rows) if isinstance(expected_rows, list) else None})
                else:
                    for rix, (actual, expected) in enumerate(zip(rows, expected_rows)):
                        if not isinstance(expected, list) or len(actual) != len(expected) or any(
                                not sql_cells_equal(a, e) for a, e in zip(actual, expected)):
                            errors.append({"id": qid, "row": rix, "error": "单元格不一致",
                                           "actual": list(actual), "reported": expected})
                digest = hashlib.sha256(json.dumps([columns, rows], ensure_ascii=False,
                                                    default=str).encode()).hexdigest()
                reports.append({"id": qid, "row_count": len(rows), "columns": columns,
                                "result_sha256": digest, "empty_result": not rows})
            except (sqlite3.Error, ValueError) as exc:
                errors.append({"id": qid, "error": ("查询超时" if state["failed"] else str(exc))})
            finally:
                connection.set_progress_handler(None, 0)
    finally:
        connection.close()
    return emit({"ok": not errors, "database_sha256": sha256(db_path), "queries": reports,
                 "mismatches": errors}, 0 if not errors else 1)


def schema_errors(result):
    errors = []
    required = ("schema_version", "skill_version", "case_id", "status", "questions", "aggregates",
                "figures", "queries", "runs", "coverage", "data_dictionary", "lineage", "gain",
                "unchecked", "sources", "uncertainty", "change_log")
    for key in required:
        if key not in result:
            errors.append("缺顶层字段 %s" % key)
    if result.get("schema_version") != VERSION or result.get("skill_version") != VERSION:
        errors.append("schema_version/skill_version 必须为 %s" % VERSION)
    if not result.get("case_id"):
        errors.append("case_id 为空")
    if result.get("status") not in {"pass", "issues", "partial", "failed"}:
        errors.append("status 非法")
    for i, question in enumerate(result.get("questions", [])):
        if not question.get("id") or question.get("answer") in (None, ""):
            errors.append("questions[%d] 缺 id/answer" % i)
        evidence = question.get("evidence")
        if not isinstance(evidence, list) or not evidence:
            errors.append("questions[%d] 缺 evidence" % i)
            continue
        for j, item in enumerate(evidence):
            if not isinstance(item, dict) or not item.get("artifact") or not item.get("location"):
                errors.append("questions[%d].evidence[%d] 缺 artifact/location" % (i, j))
            elif not item.get("quote") and not HEX64.match(str(item.get("sha256", ""))):
                errors.append("questions[%d].evidence[%d] 须含逐字 quote 或 sha256" % (i, j))
    coverage = result.get("coverage", {})
    for key in ("cleaning", "statistics", "visualization", "execution", "query"):
        state = coverage.get(key, {})
        if state.get("status") not in {"pass", "issues", "not_checked"}:
            errors.append("coverage.%s 缺合法 status" % key)
        if state.get("status") == "not_checked" and not state.get("reason"):
            errors.append("coverage.%s not_checked 缺 reason" % key)
    lineage = result.get("lineage", {})
    for key in ("snapshot", "tables", "filters", "join_keys", "source_sha256", "command"):
        if key not in lineage:
            errors.append("lineage 缺 %s" % key)
    if not HEX64.match(str(lineage.get("source_sha256", ""))):
        errors.append("lineage.source_sha256 须为 SHA256")
    for i, source in enumerate(result.get("sources", [])):
        if not isinstance(source, dict) or not source.get("path") or not HEX64.match(str(source.get("sha256", ""))):
            errors.append("sources[%d] 须含 path/sha256" % i)
    gain = result.get("gain", {})
    if not gain.get("protocol_version") or gain.get("same_input") is not True or gain.get("same_permissions") is not True:
        errors.append("gain 须声明 protocol_version 且 same_input/same_permissions=true")
    for arm in ("baseline", "skill"):
        record = gain.get(arm, {})
        if record.get("status") not in {"measured", "not_checked"}:
            errors.append("gain.%s.status 只能 measured/not_checked" % arm)
        if not isinstance(record.get("quality"), dict) or not isinstance(record.get("efficiency"), dict):
            errors.append("gain.%s 须含 quality/efficiency 对象(未测值用 null)" % arm)
        if record.get("status") == "measured" and not record.get("evidence"):
            errors.append("gain.%s measured 缺 evidence" % arm)
    if result.get("status") == "pass" and any(result.get(k) for k in ("unchecked", "uncertainty")):
        errors.append("status=pass 但 unchecked/uncertainty 非空")
    return errors


def cmd_schema(path):
    result = load_json(path)
    errors = schema_errors(result)
    return emit({"ok": not errors, "errors": errors, "tool_version": VERSION}, 0 if not errors else 1)


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)
    x = sub.add_parser("profile"); x.add_argument("csv")
    for name in ("recheck", "chartcheck"):
        x = sub.add_parser(name); x.add_argument("result"); x.add_argument("--csv", required=True)
        if name == "recheck": x.add_argument("--tolerance", type=float, default=1e-9)
    x = sub.add_parser("run"); x.add_argument("code"); x.add_argument("--log", required=True)
    x.add_argument("--input", action="append", default=[]); x.add_argument("--require", action="append", default=[])
    x.add_argument("--package", action="append", default=[])
    x.add_argument("--timeout", type=float, default=60); x.add_argument("--seed", type=int, default=0)
    x = sub.add_parser("sqlcheck"); x.add_argument("result"); x.add_argument("--db", required=True)
    x.add_argument("--timeout", type=float, default=10)
    x = sub.add_parser("schema"); x.add_argument("result")
    return p


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    child_args = []
    if argv and argv[0] == "run" and "--" in argv:
        split = argv.index("--")
        argv, child_args = argv[:split], argv[split + 1:]
    args = parser().parse_args(argv)
    if args.command == "profile": return cmd_profile(args.csv)
    if args.command == "recheck": return cmd_recheck(args.result, args.csv, args.tolerance)
    if args.command == "chartcheck": return cmd_chartcheck(args.result, args.csv)
    if args.command == "run": return cmd_run(args.code, args.log, args.input, args.require,
                                             args.timeout, args.seed, child_args, args.package)
    if args.command == "sqlcheck": return cmd_sqlcheck(args.result, args.db, args.timeout)
    if args.command == "schema": return cmd_schema(args.result)
    return 2


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, json.JSONDecodeError, csv.Error) as exc:
        sys.exit(emit({"ok": False, "error": str(exc), "error_type": type(exc).__name__}, 1))
