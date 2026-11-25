#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Configurable literature-table cleaning; Python standard library only.

Commands
  clean --input TABLE --rules RULES.json --out DIR [--case case.json] [--gain gain.json]
  audit --out DIR [--input TABLE]
  gain  --baseline METRICS.json --skill METRICS.json --out gain.json

CSV/TSV/JSON/JSONL are accepted. No value is silently invented: unknown units,
conflicting aliases, missing identity, out-of-range values and scientific conflicts
are emitted to review.json. Decimal, not binary float, performs unit conversion.
"""
import argparse
import csv
import decimal
import hashlib
import json
import math
import os
import re
import sys
import unicodedata
from collections import Counter, OrderedDict

Decimal = decimal.Decimal
decimal.getcontext().prec = 40
NUM = r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?"
SCALAR_RE = re.compile(r"^(%s)\s*(.*)$" % NUM)
RANGE_RE = re.compile(r"^(%s)\s*(?:–|—|~|\.\.|\bto\b)\s*(%s)\s*(.*)$" % (NUM, NUM))
PM_RE = re.compile(r"^(%s)\s*(?:±|\+/-)\s*(%s)\s*(.*)$" % (NUM, NUM))
MISSING = {"", "na", "n/a", "null", "none", "not reported", "not_reported", "未报告", "缺失"}
STATUSES = {"success", "partial", "failed", "refused"}


class CleanError(Exception):
    pass


def norm_text(value):
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", str(value or "")).strip())


def norm_key(value):
    return norm_text(value).casefold()


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def read_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def write_json(path, obj):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")


def is_missing(value, extra=()):
    return norm_text(value).casefold() in MISSING | {norm_key(x) for x in extra}


def read_table(path, encoding="utf-8-sig", delimiter=None):
    """Return (rows, fieldnames, encoding, delimiter). Empty tables are valid input."""
    ext = os.path.splitext(path)[1].lower()
    try:
        if ext == ".jsonl":
            with open(path, encoding=encoding) as f:
                rows = [json.loads(line) for line in f if line.strip()]
            if not all(isinstance(r, dict) for r in rows):
                raise CleanError("JSONL 每行必须是对象")
            fields = list(OrderedDict((k, None) for r in rows for k in r).keys())
            return rows, fields, encoding, None
        if ext == ".json":
            data = read_json(path)
            if isinstance(data, dict):
                data = data.get("records", data.get("rows", data.get("data")))
            if data is None or not isinstance(data, list) or not all(isinstance(r, dict) for r in data):
                raise CleanError("JSON 输入须为对象数组，或含 records/rows/data 对象数组")
            fields = list(OrderedDict((k, None) for r in rows for k in r).keys()) if (rows := data) else []
            return rows, fields, encoding, None
        with open(path, encoding=encoding, newline="") as f:
            sample = f.read(8192)
            f.seek(0)
            delim = delimiter or ("\t" if ext in (".tsv", ".tab") else None)
            if not delim:
                try:
                    delim = csv.Sniffer().sniff(sample, delimiters=",\t|;").delimiter
                except csv.Error:
                    delim = ","
            reader = csv.DictReader(f, delimiter=delim)
            fields = reader.fieldnames or []
            if len(fields) != len(set(fields)):
                raise CleanError("表头存在重复列名")
            rows = [dict(r) for r in reader]
            if any(None in r for r in rows):
                raise CleanError("某行字段数多于表头，需先修复分隔符/引号")
            return rows, fields, encoding, delim
    except UnicodeDecodeError as e:
        raise CleanError("ENCODING_ERROR: %s；用 --encoding 显式指定真实编码，不做猜测转码" % e)


def validate_rules(rules):
    fields = rules.get("fields")
    if not isinstance(fields, dict) or not fields:
        raise CleanError("rules.fields 必须是非空对象")
    aliases = {}
    for canonical, cfg in fields.items():
        if cfg.get("type", "string") not in ("string", "number", "integer"):
            raise CleanError("%s: type 仅支持 string/number/integer" % canonical)
        for alias in [canonical] + list(cfg.get("aliases", [])):
            key = norm_key(alias)
            if not key:
                raise CleanError("%s: 空别名" % canonical)
            if key in aliases and aliases[key] != canonical:
                raise CleanError("字段别名冲突: %r 同时映射 %s/%s" % (alias, aliases[key], canonical))
            aliases[key] = canonical
        target = cfg.get("target_unit")
        conversions = cfg.get("conversions", {})
        if target:
            if target not in conversions:
                raise CleanError("%s: conversions 必须至少声明目标单位 %s 的恒等规则" % (canonical, target))
            for unit, cv in conversions.items():
                try:
                    Decimal(str(cv.get("factor", "1")))
                    Decimal(str(cv.get("offset", "0")))
                except Exception:
                    raise CleanError("%s/%s: factor/offset 非法" % (canonical, unit))
    dedupe = rules.get("dedupe", {})
    for key in dedupe.get("identity_keys", []):
        if key not in fields:
            raise CleanError("dedupe.identity_keys 中 %s 未在 fields 声明" % key)
    return aliases


def decimal_text(value, places=None):
    if places is not None:
        quantum = Decimal(1).scaleb(-int(places))
        value = value.quantize(quantum, rounding=decimal.ROUND_HALF_UP)
    text = format(value, "f")
    if "." in text and places is None:
        text = text.rstrip("0").rstrip(".")
    return "0" if text in ("-0", "") else text


def convert_decimal(value, cfg, unit):
    target = cfg.get("target_unit")
    if not target:
        return value, unit, None, None, None
    aliases = cfg.get("unit_aliases", {})
    canonical_unit = aliases.get(unit, aliases.get(norm_key(unit), unit))
    cv = cfg.get("conversions", {}).get(canonical_unit)
    if cv is None:
        raise CleanError("UNKNOWN_UNIT:%s" % (unit or "<missing>"))
    factor, offset = Decimal(str(cv.get("factor", "1"))), Decimal(str(cv.get("offset", "0")))
    answer = value * factor + offset
    formula = "(%s)*(%s)+(%s)" % (decimal_text(value), decimal_text(factor), decimal_text(offset))
    return answer, target, formula, decimal_text(factor), decimal_text(offset)


def parse_number(raw, cfg):
    text = norm_text(raw)
    if cfg.get("thousands_separator"):
        text = text.replace(cfg["thousands_separator"], "")
    # Try compound forms first; otherwise the scalar grammar would treat the
    # second endpoint as part of a unit (e.g. 2–1 V -> unit "–1 V").
    kind, match = "range", RANGE_RE.fullmatch(text)
    if not match:
        kind, match = "pm", PM_RE.fullmatch(text)
    if not match:
        kind, match = "scalar", SCALAR_RE.fullmatch(text)
    if not match:
        raise CleanError("INVALID_NUMBER:%s" % text)
    unit = norm_text(match.group(match.lastindex))
    values = [Decimal(match.group(i)) for i in range(1, match.lastindex)]
    if kind == "range" and values[0] > values[1]:
        raise CleanError("REVERSED_RANGE:%s" % text)
    if kind == "pm" and values[1] < 0:
        raise CleanError("NEGATIVE_ERROR:%s" % text)
    return kind, values, unit


def check_bounds(value, cfg):
    if value is None:
        return None
    if "min" in cfg and value < Decimal(str(cfg["min"])):
        return "BELOW_MIN:%s<%s" % (value, cfg["min"])
    if "max" in cfg and value > Decimal(str(cfg["max"])):
        return "ABOVE_MAX:%s>%s" % (value, cfg["max"])
    return None


def process_field(raw_value, cfg, canonical, row):
    """Return value, extras, provenance, issues. All numeric work is real Decimal work."""
    extras, issues = {}, []
    raw = norm_text(raw_value)
    provenance = {"rule_id": cfg.get("rule_id", "R-FIELD:" + canonical), "original": raw_value,
                  "original_header": None, "original_unit": None, "target_unit": cfg.get("target_unit")}
    if is_missing(raw, cfg.get("missing_tokens", [])):
        if cfg.get("required") or cfg.get("review_missing"):
            issues.append(("MISSING_VALUE", "必填/受控字段为空；保持空缺并人工补原文", "missing token"))
        return "", extras, provenance, issues, "missing"
    if cfg.get("type", "string") == "string":
        synonyms = cfg.get("synonyms", {})
        value = synonyms.get(raw, synonyms.get(norm_key(raw), raw))
        allowed = cfg.get("allowed")
        if allowed is not None and value not in allowed:
            issues.append(("NOT_ALLOWED", "值不在允许集合；保留原值待确认，不强行归一", "allowed=%r" % allowed))
        return value, extras, provenance, issues, "string"
    try:
        kind, values, unit = parse_number(raw, cfg)
        if not unit and cfg.get("implied_unit") is not None:
            unit = cfg["implied_unit"]
            provenance["implied_unit_rule"] = cfg.get("rule_id", canonical)
        provenance["original_unit"] = unit or None
        converted = [convert_decimal(v, cfg, unit) for v in values]
        nums = [x[0] for x in converted]
        target = converted[0][1]
        if converted[0][2]:
            provenance.update(formula=converted[0][2], factor=converted[0][3], offset=converted[0][4])
        places = cfg.get("decimal_places")
        texts = [decimal_text(v, places) for v in nums]
        if kind == "scalar":
            value = texts[0]
        elif kind == "range":
            value = texts[0] + ".." + texts[1]
            extras.update({canonical + "__low": texts[0], canonical + "__high": texts[1]})
        else:
            value = texts[0]
            extras[canonical + "__error"] = texts[1]
        for n in nums:
            problem = check_bounds(n, cfg)
            if problem:
                issues.append(("OUT_OF_RANGE", "越界值不删除、不截断；核对原值/单位/规则", problem))
                break
        if cfg.get("type") == "integer" and any(v != v.to_integral_value() for v in nums):
            issues.append(("NOT_INTEGER", "转换后不是整数；保留值并待确认", value))
        signature = kind + ":" + "|".join(decimal_text(v) for v in nums) + ":" + str(target or unit)
        return value, extras, provenance, issues, signature
    except (CleanError, decimal.InvalidOperation, ValueError) as e:
        code = str(e).split(":", 1)[0]
        if code not in ("UNKNOWN_UNIT", "INVALID_NUMBER", "REVERSED_RANGE", "NEGATIVE_ERROR"):
            code = "INVALID_NUMBER"
        actions = {
            "UNKNOWN_UNIT": "原值留空、原文保留；把新单位加入经审核的 conversions 后重跑",
            "INVALID_NUMBER": "不猜数值；核对数字区域、区间/误差格式与原表",
            "REVERSED_RANGE": "不自动交换端点；回原文核对区间",
            "NEGATIVE_ERROR": "不取绝对值；回原文核对误差语义",
        }
        issues.append((code, actions[code], str(e)))
        provenance["error"] = str(e)
        return "", extras, provenance, issues, "invalid"


def contract_defaults(result, case):
    if not isinstance(case, dict):
        return
    contract = case.get("output_contract", {})
    keys = []
    if isinstance(contract, list):
        keys = [str(k) for k in contract]
    elif isinstance(contract, dict):
        if isinstance(contract.get("required"), list):
            keys += contract["required"]
        if isinstance(contract.get("properties"), dict):
            keys += list(contract["properties"])
        keys += [k for k, v in contract.items() if isinstance(v, str)]
    for key in OrderedDict((k, None) for k in keys):
        if key not in result:
            result[key] = [] if key.endswith(("s", "records", "uncertainty", "gaps")) else None


def issue(issue_type, message, signal, source_ref, field=None):
    return {"id": "", "type": issue_type, "signal": signal, "action": message,
            "source_ref": source_ref, "field": field, "status": "pending"}


def pending_gain(input_hash, summary):
    return {"status": "baseline_not_provided",
            "protocol": {"same_input": True, "same_permissions": True, "same_model": True,
                         "same_budget": True, "input_sha256": input_hash,
                         "quality_metric": "correct_cells/total_cells; false_merges 独立报告",
                         "efficiency_metric": "runtime_seconds 与 manual_corrections"},
            "baseline_metrics": None,
            "skill_metrics": {"input_rows": summary["input_rows"], "pending_reviews": summary["review_pending"]},
            "delta": None,
            "note": "平台未提供同输入基础 Agent 实测数据时不填分数；用 gain 子命令读取双方实测指标后计算。"}


def clean_command(args):
    rows, headers, encoding, delimiter = read_table(args.input, args.encoding, args.delimiter)
    rules = read_json(args.rules)
    aliases = validate_rules(rules)
    fields = rules["fields"]
    input_hash = sha256(args.input)
    source = {"path": os.path.basename(args.input), "sha256": input_hash,
              "encoding": encoding, "delimiter": delimiter, "rows": len(rows)}
    reviews = []
    for header in headers:
        if norm_key(header) not in aliases:
            reviews.append(issue("UNMAPPED_FIELD", "未映射列不进入统计；补充 aliases 或明确忽略", "未声明列名",
                                 {"source_file": source["path"], "row": 0, "column": header}, header))
    if not rows:
        reviews.append(issue("EMPTY_TABLE", "不生成统计结论；检查是否空表或表头错位", "0 data rows",
                             {"source_file": source["path"], "row": 0}))
    records, lineages, changes = [], [], []
    for row_index, raw in enumerate(rows, 1):
        ref = {"source_file": source["path"], "source_sha256": input_hash, "row": row_index}
        rec = OrderedDict()
        provs, sigs = {}, {}
        for canonical, cfg in fields.items():
            found = [(h, raw[h]) for h in headers if norm_key(h) in aliases and aliases[norm_key(h)] == canonical]
            distinct = {norm_text(v) for _, v in found if not is_missing(v, cfg.get("missing_tokens", []))}
            if len(distinct) > 1:
                rec[canonical] = ""
                provs[canonical] = {"rule_id": cfg.get("rule_id", "R-FIELD:" + canonical),
                                    "original": {h: v for h, v in found}}
                reviews.append(issue("ALIAS_CONFLICT", "同一行多个别名值冲突；不选值，回原始字段裁决",
                                     repr({h: v for h, v in found}), ref, canonical))
                sigs[canonical] = "conflict"
                continue
            header, raw_value = found[0] if found else (None, "")
            value, extras, prov, problems, sig = process_field(raw_value, cfg, canonical, raw)
            prov["original_header"] = header
            rec[canonical] = value
            rec.update(extras)
            provs[canonical], sigs[canonical] = prov, sig
            for typ, action, signal in problems:
                reviews.append(issue(typ, action, signal, ref, canonical))
            original_unit = prov.get("original_unit")
            changed = (header != canonical or norm_text(raw_value) != norm_text(value)
                       or (cfg.get("target_unit") and original_unit != cfg.get("target_unit") and bool(value)))
            if changed:
                action = "unit_conversion" if cfg.get("target_unit") and original_unit != cfg.get("target_unit") and value else "normalization"
                item = {"rule_id": prov.get("rule_id"), "action": action, "field": canonical,
                        "source_ref": dict(ref, column=header), "original": raw_value,
                        "normalized": value, "original_unit": original_unit,
                        "target_unit": cfg.get("target_unit")}
                for key in ("formula", "factor", "offset", "error"):
                    if key in prov:
                        item[key] = prov[key]
                changes.append(item)
        records.append({"values": rec, "source_refs": [ref], "raw_records": [raw],
                        "provenance": provs, "signatures": sigs})
    # Merge only exact normalized duplicates inside a complete scientific identity.
    dedupe = rules.get("dedupe", {})
    identity_keys = dedupe.get("identity_keys", [])
    groups, singles = OrderedDict(), []
    for idx, item in enumerate(records):
        key = tuple(norm_text(item["values"].get(k)) for k in identity_keys)
        if identity_keys and all(key):
            groups.setdefault(key, []).append((idx, item))
        else:
            singles.append((idx, item))
            if identity_keys:
                missing = [k for k in identity_keys if not norm_text(item["values"].get(k))]
                reviews.append(issue("INSUFFICIENT_IDENTITY", "身份键不全，禁止自动合并", "missing=" + ",".join(missing),
                                     item["source_refs"][0]))
    ordered_groups = singles + list(groups.values())
    ordered_groups.sort(key=lambda g: g[0][0] if isinstance(g, list) else g[0])
    merged = []
    for group in ordered_groups:
        pairs = group if isinstance(group, list) and isinstance(group[0], tuple) else [group]
        if not identity_keys or len(pairs) == 1:
            merged.append(pairs[0][1])
            continue
        signature_groups = OrderedDict()
        for idx, item in pairs:
            signature = json.dumps(item["signatures"], ensure_ascii=False, sort_keys=True)
            signature_groups.setdefault(signature, []).append(item)
        if len(signature_groups) > 1:
            refs = [it["source_refs"][0] for _, it in pairs]
            reviews.append(issue("DUPLICATE_CONFLICT", "身份相同但值不同：可能是科学冲突，保留全部行，不合并",
                                 "identity=%r; distinct_values=%d" % (pairs[0][1]["values"], len(signature_groups)),
                                 refs[0]))
        for duplicates in signature_groups.values():
            base = duplicates[0]
            if len(duplicates) > 1:
                base["source_refs"] = [r for it in duplicates for r in it["source_refs"]]
                base["raw_records"] = [r for it in duplicates for r in it["raw_records"]]
                for it in duplicates[1:]:
                    changes.append({"rule_id": dedupe.get("rule_id", "R-DEDUPE-EXACT"),
                                    "action": "exact_duplicate_merge", "field": "*",
                                    "source_ref": it["source_refs"][0],
                                    "original": "duplicate extraction row", "normalized": "merged into first identical row",
                                    "identity_keys": identity_keys,
                                    "compare_fields": sorted(base["signatures"])})
            base["duplicate_count"] = len(duplicates)
            merged.append(base)
    cleaned, final_lineages = [], []
    for i, item in enumerate(merged, 1):
        lid = "L%06d" % i
        row = OrderedDict()
        row["_lineage_id"] = lid
        row.update(item["values"])
        row["duplicate_count"] = item.get("duplicate_count", 1)
        row["_source_rows"] = ";".join("%s#%s" % (r["source_file"], r["row"]) for r in item["source_refs"])
        cleaned.append(row)
        final_lineages.append({"lineage_id": lid, "source_refs": item["source_refs"],
                               "raw_records": item["raw_records"], "cleaned_record": row,
                               "field_rules": item["provenance"], "normalized_signatures": item["signatures"]})
    for i, r in enumerate(reviews, 1):
        r["id"] = "Q%06d" % i
    os.makedirs(args.out, exist_ok=True)
    csv_path = os.path.join(args.out, "cleaned.csv")
    fieldnames = list(OrderedDict((k, None) for r in cleaned for k in r).keys())
    if not fieldnames:
        fieldnames = ["_lineage_id"] + list(fields) + ["duplicate_count", "_source_rows"]
    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="raise")
        writer.writeheader()
        writer.writerows(cleaned)
    with open(os.path.join(args.out, "changes.jsonl"), "w", encoding="utf-8") as f:
        for item in changes:
            f.write(json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n")
    with open(os.path.join(args.out, "lineage.jsonl"), "w", encoding="utf-8") as f:
        for item in final_lineages:
            f.write(json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n")
    write_json(os.path.join(args.out, "review.json"), reviews)
    case = read_json(args.case) if args.case else {}
    case_id = args.case_id or case.get("case_id", "")
    counts = Counter(r["type"] for r in reviews)
    summary = {"input_rows": len(rows), "output_rows": len(cleaned),
               "duplicate_rows_removed": len(rows) - len(cleaned),
               "changed_values": sum(c["action"] != "exact_duplicate_merge" for c in changes),
               "unit_conversions": sum(c["action"] == "unit_conversion" for c in changes),
               "review_pending": len(reviews), "review_by_type": dict(sorted(counts.items()))}
    status = "failed" if not rows else ("partial" if reviews else "success")
    gain = read_json(args.gain) if args.gain else pending_gain(input_hash, summary)
    result = {"case_id": case_id, "status": status, "task": "文献抽取表清洗、标准化、精确去重与行级追溯",
              "cleaned_table": "cleaned.csv", "records": cleaned, "review": reviews,
              "sources": [source], "uncertainty": ["%s %s: %s" % (r["id"], r["type"], r["signal"]) for r in reviews],
              "summary": summary, "change_records": changes, "gain": gain,
              "rules_version": rules.get("version", "unversioned"),
              "artifacts": {"cleaned_csv": "cleaned.csv", "changes": "changes.jsonl", "lineage": "lineage.jsonl",
                            "review": "review.json", "rules": os.path.basename(args.rules)}}
    contract_defaults(result, case)
    write_json(os.path.join(args.out, "result.json"), result)
    print(json.dumps({"ok": True, "status": status, "summary": summary, "out": args.out}, ensure_ascii=False))
    return 0


def load_jsonl(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def audit_command(args):
    errors = []
    try:
        result = read_json(os.path.join(args.out, "result.json"))
        reviews = read_json(os.path.join(args.out, "review.json"))
        changes = load_jsonl(os.path.join(args.out, "changes.jsonl"))
        lineage = load_jsonl(os.path.join(args.out, "lineage.jsonl"))
        with open(os.path.join(args.out, "cleaned.csv"), encoding="utf-8", newline="") as f:
            cleaned = list(csv.DictReader(f))
    except Exception as e:
        print(json.dumps({"ok": False, "errors": ["artifact unreadable: %s" % e]}, ensure_ascii=False))
        return 1
    for key in ("case_id", "status", "records", "summary", "sources", "uncertainty", "change_records", "gain", "artifacts"):
        if key not in result:
            errors.append("result 缺字段 " + key)
    if result.get("status") not in STATUSES:
        errors.append("status 非法")
    if result.get("case_id") in (None, ""):
        errors.append("case_id 为空")
    # CSV has no integer type; duplicate_count is the sole generated integer.
    csv_records = []
    for row in cleaned:
        normalized = dict(row)
        if str(normalized.get("duplicate_count", "")).isdigit():
            normalized["duplicate_count"] = int(normalized["duplicate_count"])
        csv_records.append(normalized)
    if csv_records != result.get("records"):
        errors.append("result.records 与 cleaned.csv 不一致")
    if len(lineage) != len(cleaned):
        errors.append("lineage 行数与 cleaned.csv 不一致")
    ids = set()
    for i, item in enumerate(lineage):
        lid = item.get("lineage_id")
        ids.add(lid)
        if i >= len(cleaned) or cleaned[i].get("_lineage_id") != lid:
            errors.append("lineage[%d] id 顺序/绑定错误" % i)
        if item.get("cleaned_record") != (csv_records[i] if i < len(csv_records) else None):
            errors.append("lineage[%d] cleaned_record 被改写" % i)
        if not item.get("source_refs") or not item.get("raw_records"):
            errors.append("lineage[%d] 缺 raw_records/source_refs" % i)
        for ref in item.get("source_refs", []):
            if not ref.get("source_file") or not isinstance(ref.get("row"), int) or ref.get("row", 0) < 1:
                errors.append("lineage[%d] source_ref 不可定位" % i)
        for field, prov in item.get("field_rules", {}).items():
            if not prov.get("rule_id") or "original" not in prov:
                errors.append("lineage[%d].%s 缺规则或原值" % (i, field))
    for i, ch in enumerate(changes):
        for key in ("rule_id", "action", "field", "source_ref", "original", "normalized"):
            if key not in ch:
                errors.append("changes[%d] 缺 %s" % (i, key))
        if ch.get("action") == "unit_conversion" and not ch.get("formula"):
            errors.append("changes[%d] 单位换算无公式" % i)
        if ch.get("action") == "exact_duplicate_merge" and not ch.get("identity_keys"):
            errors.append("changes[%d] 合并无身份键" % i)
    pending = [r for r in reviews if r.get("status") == "pending"]
    for i, r in enumerate(reviews):
        for key in ("id", "type", "signal", "action", "source_ref", "status"):
            if not r.get(key):
                errors.append("review[%d] 缺 %s" % (i, key))
    if pending and result.get("status") == "success":
        errors.append("有待确认项却标 success")
    if not pending and cleaned and result.get("status") != "success":
        errors.append("无待确认项且非空，状态应为 success")
    gain = result.get("gain") or {}
    if "status" not in gain or "protocol" not in gain or "delta" not in gain:
        errors.append("gain 缺 status/protocol/delta")
    if args.input:
        actual = sha256(args.input)
        if not any(s.get("sha256") == actual for s in result.get("sources", [])):
            errors.append("输入 SHA256 与 sources 不一致")
    print(json.dumps({"ok": not errors, "errors": errors, "rows": len(cleaned),
                      "changes": len(changes), "pending_reviews": len(pending)}, ensure_ascii=False))
    return 1 if errors else 0


def validate_metrics(doc, label):
    run = doc.get("run", {})
    for key in ("input_sha256", "permissions", "model", "budget_seconds"):
        if key not in run:
            raise CleanError("%s.run 缺 %s" % (label, key))
    for key in ("correct_cells", "total_cells", "false_merges", "manual_corrections", "runtime_seconds"):
        if key not in doc or not isinstance(doc[key], (int, float)) or isinstance(doc[key], bool):
            raise CleanError("%s 缺数值指标 %s" % (label, key))
    if doc["total_cells"] <= 0 or not 0 <= doc["correct_cells"] <= doc["total_cells"]:
        raise CleanError("%s correct_cells/total_cells 非法" % label)
    if min(doc["false_merges"], doc["manual_corrections"], doc["runtime_seconds"]) < 0:
        raise CleanError("%s 指标不得为负" % label)


def gain_command(args):
    try:
        baseline, skill = read_json(args.baseline), read_json(args.skill)
        validate_metrics(baseline, "baseline")
        validate_metrics(skill, "skill")
        for key in ("input_sha256", "permissions", "model", "budget_seconds"):
            if baseline["run"][key] != skill["run"][key]:
                raise CleanError("对照不公平: run.%s 不一致" % key)
        bacc = baseline["correct_cells"] / baseline["total_cells"]
        sacc = skill["correct_cells"] / skill["total_cells"]
        out = {"status": "complete", "protocol": {"same_input": True, "same_permissions": True,
               "same_model": True, "same_budget": True, "input_sha256": skill["run"]["input_sha256"],
               "quality_metric": "correct_cells/total_cells; false_merges 独立报告",
               "efficiency_metric": "runtime_seconds 与 manual_corrections"},
               "baseline_metrics": baseline, "skill_metrics": skill,
               "delta": {"cell_accuracy": sacc - bacc, "baseline_cell_accuracy": bacc,
                         "skill_cell_accuracy": sacc,
                         "false_merges": skill["false_merges"] - baseline["false_merges"],
                         "runtime_seconds": skill["runtime_seconds"] - baseline["runtime_seconds"],
                         "manual_corrections": skill["manual_corrections"] - baseline["manual_corrections"]}}
        write_json(args.out, out)
        print(json.dumps({"ok": True, "delta": out["delta"]}, ensure_ascii=False))
        return 0
    except (CleanError, OSError, ValueError, json.JSONDecodeError) as e:
        print(json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False))
        return 1


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="command", required=True)
    p = sub.add_parser("clean")
    p.add_argument("--input", required=True)
    p.add_argument("--rules", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--case")
    p.add_argument("--case-id", default="")
    p.add_argument("--gain")
    p.add_argument("--encoding", default="utf-8-sig")
    p.add_argument("--delimiter")
    p.set_defaults(func=clean_command)
    p = sub.add_parser("audit")
    p.add_argument("--out", required=True)
    p.add_argument("--input")
    p.set_defaults(func=audit_command)
    p = sub.add_parser("gain")
    p.add_argument("--baseline", required=True)
    p.add_argument("--skill", required=True)
    p.add_argument("--out", required=True)
    p.set_defaults(func=gain_command)
    args = ap.parse_args(argv)
    try:
        return args.func(args)
    except (CleanError, OSError, ValueError, json.JSONDecodeError) as e:
        print(json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
