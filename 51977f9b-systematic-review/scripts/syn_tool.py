#!/usr/bin/env python3
"""可复核系统综述机检器；仅使用 Python 标准库。

命令（在 Skill 根目录运行）：
  hash <file> [file ...]                    计算文件 SHA-256
  schema <result.json> [--case case.json] [--verify-artifacts]
  protocol_check <result.json>              检索式、标准版本及时序
  screen_check <result.json>                去重、两轮筛选、理由码、分歧与计数
  quality_check <result.json>               质量量表逐项重算及证据
  cite_check <result.json>                  论断引用、纳入集与精确定位
  quote_check <result.json> [--root DIR]    逐字引文、原文/抽取文本 SHA-256
  theme_check <result.json>                 主题由实际引用文献归纳
  synthesis_check <result.json>             研究空白排除证据与冲突矩阵
  exception_check <result.json>             七类题面点名失败的处置闭环
  gain_check <result.json> [--baseline FILE] [--update]
  audit <result.json> [--baseline FILE] [--case FILE] [--root DIR]
            [--verify-artifacts] [--allow-gain-not-run]

退出码：0=通过；1=机检/输入失败；2=命令行用法错误。stdout 始终为一个 JSON 对象。
"""
import argparse
import copy
import datetime as _datetime
import hashlib
import json
import math
import os
import re
import sys
import tempfile

TOOL_VERSION = "2.0.0"
SCHEMA_VERSION = "2.0.0"
SKILL_VERSION = "2.0.0"
HEX64 = re.compile(r"^[0-9a-f]{64}$")
STAGES = {"dedup", "title_abstract", "full_text"}
DECISIONS = {"include", "exclude"}
EXCEPTION_TYPES = {
    "empty_search", "database_or_interface_timeout", "full_text_unavailable",
    "terminology_ambiguity", "criterion_conflict",
    "contradictory_included_evidence", "permission_denied",
    "duplicate_records", "metadata_missing", "context_overflow", "interrupted_run",
}


class Report:
    def __init__(self):
        self.errors = []
        self.warnings = []
        self.not_checked = []
        self.metrics = {}

    def error(self, code, path, message):
        self.errors.append({"code": code, "path": path, "message": message})

    def warn(self, code, path, message):
        self.warnings.append({"code": code, "path": path, "message": message})

    def unchecked(self, code, path, message):
        self.not_checked.append({"code": code, "path": path, "message": message})


def _load(path):
    with open(path, encoding="utf-8") as f:
        value = json.load(f)
    if not isinstance(value, dict):
        raise ValueError("顶层 JSON 必须是对象")
    return value


def _emit(command, report):
    value = {
        "ok": not report.errors,
        "command": command,
        "tool_version": TOOL_VERSION,
        "schema_version": SCHEMA_VERSION,
        "errors": report.errors,
        "warnings": report.warnings,
        "not_checked": report.not_checked,
        "metrics": report.metrics,
    }
    print(json.dumps(value, ensure_ascii=False, sort_keys=True))
    return 0 if not report.errors else 1


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha_text(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _sha_object(value):
    return _sha_text(_canonical(value))


def _file_sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def _is_hash(value):
    return isinstance(value, str) and bool(HEX64.fullmatch(value))


def _items(value):
    return value if isinstance(value, list) else []


def _mapping(value):
    return value if isinstance(value, dict) else {}


def _index(values, key="id"):
    return {v.get(key): v for v in _items(values) if isinstance(v, dict) and v.get(key)}


def _parse_time(value):
    if not isinstance(value, str):
        raise ValueError("not a string")
    text = value[:-1] + "+00:00" if value.endswith("Z") else value
    parsed = _datetime.datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        raise ValueError("timezone required")
    return parsed


def _norm_ws(text):
    return re.sub(r"\s+", " ", text).strip()


def _resolve(path, result_path, root=None):
    if os.path.isabs(path):
        return path
    if root:
        candidate = os.path.join(root, path)
        if os.path.exists(candidate):
            return candidate
    return os.path.join(os.path.dirname(os.path.abspath(result_path)), path)


def _precision_ok(location):
    if not isinstance(location, dict):
        return False
    if location.get("field"):
        return True
    return bool(location.get("sentence") and (location.get("page") or location.get("paragraph")))


def _valid_evidence_shape(value):
    if not isinstance(value, dict):
        return False
    return all(value.get(k) for k in ("quote", "quote_sha256", "source_sha256")) and _precision_ok(value.get("location"))


def _require_fields(d, fields, prefix, report, code="missing_field"):
    for field in fields:
        if field not in d or d.get(field) in (None, ""):
            report.error(code, "%s.%s" % (prefix, field), "必填字段缺失或为空")


def _run_logging():
    """Context manager used only by main; avoids traceback as normal UX."""
    class SuppressBrokenPipe:
        def __enter__(self):
            return None

        def __exit__(self, exc_type, exc, tb):
            return exc_type == BrokenPipeError
    return SuppressBrokenPipe()


def check_schema(d, result_path, case_path=None, verify_artifacts=False, root=None):
    r = Report()
    required = (
        "schema_version", "skill_version", "case_id", "status", "run",
        "research_question", "search", "protocol", "screening_criteria", "records",
        "decisions", "duplicates", "included", "excluded", "quality_scales",
        "quality_appraisals", "claims", "themes", "conflicts", "research_gaps",
        "exceptions", "counts", "gain", "unchecked", "not_checked", "sources",
        "uncertainty", "change_log", "artifacts",
    )
    _require_fields(d, (), "$", r)
    for key in required:
        if key not in d:
            r.error("missing_field", "$.%s" % key, "缺顶层字段")
    if d.get("schema_version") != SCHEMA_VERSION:
        r.error("schema_version", "$.schema_version", "应为 %s" % SCHEMA_VERSION)
    if d.get("skill_version") != SKILL_VERSION:
        r.error("skill_version", "$.skill_version", "应为 %s" % SKILL_VERSION)
    if d.get("status") not in {"pass", "issues", "partial", "failed"}:
        r.error("status", "$.status", "仅允许 pass/issues/partial/failed")
    if not d.get("case_id"):
        r.error("case_id", "$.case_id", "case_id 不得为空")

    run = _mapping(d.get("run"))
    _require_fields(run, ("run_id", "started_at", "finished_at", "input", "permissions", "checkpoints"),
                    "$.run", r)
    inputs = _mapping(run.get("input"))
    for name in ("case", "task"):
        item = _mapping(inputs.get(name))
        _require_fields(item, ("path", "sha256"), "$.run.input.%s" % name, r)
        if "sha256" in item and not _is_hash(item.get("sha256")):
            r.error("hash_format", "$.run.input.%s.sha256" % name, "须为小写 SHA-256")
    if run.get("tool_version") != TOOL_VERSION:
        r.error("tool_version", "$.run.tool_version", "运行工具版本与机检器不一致")
    for field in ("started_at", "finished_at"):
        try:
            _parse_time(run.get(field))
        except (ValueError, TypeError):
            r.error("timestamp", "$.run.%s" % field, "须为带时区 ISO-8601")
    for field in ("elapsed_seconds", "model_requests", "manual_rework_items"):
        if field not in run:
            r.error("missing_field", "$.run.%s" % field, "指标字段必须存在；未知显式为 null")
        elif run.get(field) is None:
            if not _mapping(run.get("metric_notes")).get(field):
                r.error("metric_unknown", "$.run.metric_notes.%s" % field, "未知效率指标须写明 not_checked 原因")
        elif not isinstance(run.get(field), (int, float)) or run.get(field) < 0:
            r.error("metric", "$.run.%s" % field, "须为非负数或带说明的 null")
    steps = _items(run.get("checkpoints"))
    if not steps:
        r.error("checkpoints", "$.run.checkpoints", "至少一个检查点，供中断定位")
    for i, cp in enumerate(steps):
        _require_fields(_mapping(cp), ("step", "status", "output_path"), "$.run.checkpoints[%d]" % i, r)
        if cp.get("status") not in {"completed", "pending", "failed", "skipped"}:
            r.error("checkpoint_status", "$.run.checkpoints[%d].status" % i, "非法状态")
    if d.get("status") == "failed" and not any(cp.get("status") == "failed" for cp in steps):
        r.error("failed_step", "$.run.checkpoints", "failed 结果必须定位失败步骤")
    if d.get("status") == "pass" and (d.get("unchecked") or d.get("not_checked")):
        r.error("unchecked_on_pass", "$.status", "pass 时 unchecked/not_checked 必须为空，否则用 issues/partial")

    records = _items(d.get("records"))
    record_ids = set()
    for i, rec in enumerate(records):
        _require_fields(_mapping(rec), ("id", "title", "source"), "$.records[%d]" % i, r)
        rid = rec.get("id")
        if rid in record_ids:
            r.error("duplicate_record_id", "$.records[%d].id" % i, "记录 ID 重复")
        record_ids.add(rid)
        source = _mapping(rec.get("source"))
        _require_fields(source, ("path", "sha256", "text_path", "text_sha256", "extractor", "extractor_version"),
                        "$.records[%d].source" % i, r)
        for key in ("sha256", "text_sha256"):
            if key in source and not _is_hash(source.get(key)):
                r.error("hash_format", "$.records[%d].source.%s" % (i, key), "须为小写 SHA-256")

    counts = _mapping(d.get("counts"))
    for key in ("records_raw", "records_unique", "included", "excluded", "duplicates", "undecided"):
        if not isinstance(counts.get(key), int) or counts.get(key) < 0:
            r.error("count", "$.counts.%s" % key, "须为非负整数")
    if all(isinstance(counts.get(k), int) for k in ("records_raw", "records_unique", "duplicates")):
        if counts["records_raw"] != counts["records_unique"] + counts["duplicates"]:
            r.error("count_identity", "$.counts", "records_raw=records_unique+duplicates")
    if all(isinstance(counts.get(k), int) for k in ("records_unique", "included", "excluded", "undecided")):
        if counts["records_unique"] != counts["included"] + counts["excluded"] + counts["undecided"]:
            r.error("count_identity", "$.counts", "records_unique=included+excluded+undecided")

    gain = _mapping(d.get("gain"))
    if gain.get("comparison_status") not in {"completed", "not_run", "not_available"}:
        r.error("gain_status", "$.gain.comparison_status", "须为 completed/not_run/not_available")
    if gain.get("comparison_status") != "completed" and not gain.get("reason"):
        r.error("gain_reason", "$.gain.reason", "未完成对照必须说明原因，禁止编造")

    for i, item in enumerate(_items(d.get("change_log"))):
        _require_fields(_mapping(item), ("at", "actor", "field", "old", "new", "reason"),
                        "$.change_log[%d]" % i, r)
    r.metrics.update({"records": len(records), "claims": len(_items(d.get("claims"))),
                      "decisions": len(_items(d.get("decisions")))})

    if case_path:
        try:
            case = _load(case_path)
            expected_case_id = case.get("case_id", case.get("id"))
            if expected_case_id and d.get("case_id") != expected_case_id:
                r.error("case_identity", "$.case_id", "与输入 case_id 不一致")
            actual_case_hash = _file_sha(case_path)
            if _mapping(inputs.get("case")).get("sha256") != actual_case_hash:
                r.error("case_hash", "$.run.input.case.sha256", "与实际 case.json 不一致")
            for field in _contract_fields(case.get("output_contract")):
                if field not in d:
                    r.error("output_contract", "$.%s" % field, "缺原始 output_contract 字段")
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            r.error("case_read", "--case", str(exc))

    if verify_artifacts:
        _verify_artifacts(d, result_path, r, root)
    return r


def _contract_fields(contract):
    if isinstance(contract, list):
        return [x for x in contract if isinstance(x, str)]
    if not isinstance(contract, dict):
        return []
    if isinstance(contract.get("properties"), dict):
        required = contract.get("required")
        return list(required) if isinstance(required, list) else list(contract["properties"])
    fields = contract.get("fields")
    if isinstance(fields, list):
        return [x.get("name") if isinstance(x, dict) else x for x in fields
                if isinstance(x, str) or (isinstance(x, dict) and x.get("name"))]
    if isinstance(fields, dict):
        return list(fields)
    required = contract.get("required")
    return list(required) if isinstance(required, list) and all(isinstance(x, str) for x in required) else []


def _verify_artifacts(d, result_path, r, root=None):
    for i, artifact in enumerate(_items(d.get("artifacts"))):
        path = "$.artifacts[%d]" % i
        _require_fields(_mapping(artifact), ("path", "sha256", "media_type"), path, r)
        if not artifact.get("path") or not artifact.get("sha256"):
            continue
        actual_path = _resolve(artifact["path"], result_path, root)
        if not os.path.isfile(actual_path):
            r.error("artifact_missing", path + ".path", actual_path)
            continue
        actual_hash = _file_sha(actual_path)
        if artifact.get("sha256") != actual_hash:
            r.error("artifact_hash", path + ".sha256", "应为 %s" % actual_hash)


def check_protocol(d):
    r = Report()
    protocol = _mapping(d.get("protocol"))
    question = _mapping(d.get("research_question"))
    criteria = _items(d.get("screening_criteria"))
    _require_fields(protocol, ("version", "created_at", "criteria_sha256", "conflict_policy"), "$.protocol", r)
    _require_fields(question, ("text", "framework", "elements"), "$.research_question", r)
    if not _items(question.get("elements")):
        r.error("question_elements", "$.research_question.elements", "研究问题须结构化，不得只有关键词串")
    for i, element in enumerate(_items(question.get("elements"))):
        _require_fields(_mapping(element), ("id", "concept", "synonyms", "controlled_terms"),
                        "$.research_question.elements[%d]" % i, r)
        if not isinstance(element.get("synonyms"), list) or not isinstance(element.get("controlled_terms"), list):
            r.error("term_variants", "$.research_question.elements[%d]" % i, "同义词与受控词须为数组（可空）")
    if protocol.get("criteria_sha256") != _sha_object(criteria):
        r.error("criteria_hash", "$.protocol.criteria_sha256", "标准清单被改动或哈希错误；应变更版本并留 change_log")
    criterion_ids = set()
    for i, c in enumerate(criteria):
        path = "$.screening_criteria[%d]" % i
        _require_fields(_mapping(c), ("id", "type", "stage", "criterion", "operational_test",
                                      "priority", "reason_code", "effective_version"), path, r)
        if c.get("id") in criterion_ids:
            r.error("criterion_id", path + ".id", "重复")
        criterion_ids.add(c.get("id"))
        if c.get("type") not in {"include", "exclude", "dedup"}:
            r.error("criterion_type", path + ".type", "非法")
        if c.get("stage") not in STAGES | {"both"}:
            r.error("criterion_stage", path + ".stage", "非法")
        if c.get("effective_version") != protocol.get("version"):
            r.error("criteria_version", path + ".effective_version", "与 protocol.version 不一致")
        if not isinstance(c.get("priority"), int):
            r.error("priority", path + ".priority", "须为整数；冲突按数值大者优先")
        test = str(c.get("operational_test", ""))
        if len(test) < 4 or test.strip() in {"相关", "合理", "符合主题"}:
            r.error("operational_test", path + ".operational_test", "不是可判定条款")

    search = _mapping(d.get("search"))
    databases = _index(search.get("databases"), "name")
    if not databases:
        r.error("databases", "$.search.databases", "至少声明一个数据库/来源及接口")
    for name, db in databases.items():
        _require_fields(db, ("name", "interface", "fields"), "$.search.databases[%s]" % name, r)
    queries = _items(search.get("queries"))
    if not queries:
        r.error("queries", "$.search.queries", "至少一条实际检索式")
    query_ids = set()
    zero_queries = 0
    for i, q in enumerate(queries):
        path = "$.search.queries[%d]" % i
        _require_fields(_mapping(q), ("id", "database", "fields", "query", "filters", "run_at", "intent", "result_count"), path, r)
        if q.get("id") in query_ids:
            r.error("query_id", path + ".id", "重复")
        query_ids.add(q.get("id"))
        if q.get("database") not in databases:
            r.error("query_database", path + ".database", "未在 databases 声明")
        query = q.get("query")
        if not isinstance(query, str) or not re.search(r"\b(AND|OR|NOT)\b", query, re.I):
            r.error("query_not_executable", path + ".query", "须保留含布尔逻辑的完整检索式，不得退化为关键词串")
        filters = _mapping(q.get("filters"))
        _require_fields(filters, ("languages",), path + ".filters", r)
        if "date_from" not in filters or "date_to" not in filters:
            r.error("query_dates", path + ".filters", "时间上下限须显式填写；无限用 null 并在 intent 说明")
        try:
            _parse_time(q.get("run_at"))
        except (ValueError, TypeError):
            r.error("run_at", path + ".run_at", "须为带时区 ISO-8601")
        if not isinstance(q.get("result_count"), int) or q.get("result_count") < 0:
            r.error("result_count", path + ".result_count", "须为真实非负整数")
        elif q.get("result_count") == 0:
            zero_queries += 1
            handling = _mapping(q.get("empty_search_handling"))
            _require_fields(handling, ("classification", "actions", "follow_up_query_ids"), path + ".empty_search_handling", r)
            if handling.get("classification") not in {"no_evidence_in_scope", "overly_restrictive", "not_checked"}:
                r.error("empty_search", path + ".empty_search_handling.classification", "非法分类")
    try:
        protocol_time = _parse_time(protocol.get("created_at"))
        for i, decision in enumerate(_items(d.get("decisions"))):
            if _parse_time(decision.get("decided_at")) < protocol_time:
                r.error("criteria_not_prospective", "$.decisions[%d].decided_at" % i, "判定早于标准定稿")
    except (ValueError, TypeError):
        r.error("protocol_time", "$.protocol.created_at", "须为带时区 ISO-8601")
    r.metrics.update({"criteria": len(criteria), "queries": len(queries), "zero_queries": zero_queries})
    return r


def _final_decision(decisions):
    if not decisions:
        return None
    # 输入顺序为稳定 tie-breaker；显式裁决优先于同一阶段普通判定。
    return sorted(enumerate(decisions), key=lambda pair: (
        bool(pair[1].get("resolves_disagreement")), pair[1].get("decided_at", ""), pair[0]))[-1][1]


def check_screen(d):
    r = Report()
    records = _index(d.get("records"))
    criteria = _index(d.get("screening_criteria"))
    decisions = _items(d.get("decisions"))
    protocol = _mapping(d.get("protocol"))
    included = {x.get("id") for x in _items(d.get("included"))}
    excluded = {x.get("id") for x in _items(d.get("excluded"))}
    by_record_stage = {}
    decision_ids = set()
    complete_reasons = 0
    for i, decision in enumerate(decisions):
        path = "$.decisions[%d]" % i
        _require_fields(_mapping(decision), ("id", "record_id", "stage", "decision", "reviewer",
                                             "protocol_version", "criterion_ids", "reason_codes", "evidence", "decided_at"), path, r)
        did = decision.get("id")
        if did in decision_ids:
            r.error("decision_id", path + ".id", "重复")
        decision_ids.add(did)
        rid = decision.get("record_id")
        if rid not in records:
            r.error("decision_record", path + ".record_id", "不在文献清单")
            continue
        stage = decision.get("stage")
        if stage not in STAGES:
            r.error("decision_stage", path + ".stage", "非法")
            continue
        if decision.get("decision") not in DECISIONS:
            r.error("decision_value", path + ".decision", "非法")
        if decision.get("protocol_version") != protocol.get("version"):
            r.error("decision_protocol", path + ".protocol_version", "判定使用了其他标准版本；需重筛或显式迁移")
        criterion_ids = decision.get("criterion_ids")
        reason_codes = decision.get("reason_codes")
        if not isinstance(criterion_ids, list) or not criterion_ids or any(x not in criteria for x in criterion_ids):
            r.error("decision_criteria", path + ".criterion_ids", "至少引用一个已预注册条款")
        if not isinstance(reason_codes, list) or not reason_codes:
            r.error("reason_codes", path + ".reason_codes", "每次纳入/排除均须理由码")
        else:
            allowed = {criteria[x].get("reason_code") for x in _items(criterion_ids) if x in criteria}
            if any(x not in allowed for x in reason_codes):
                r.error("reason_code_mapping", path + ".reason_codes", "理由码必须来自所引用条款")
        evidence = _mapping(decision.get("evidence"))
        if not _valid_evidence_shape(evidence):
            r.error("decision_evidence", path + ".evidence", "须含逐字 quote、quote_sha256/source_sha256 与句/字段级 location")
        if reason_codes and criterion_ids and _valid_evidence_shape(evidence):
            complete_reasons += 1
        try:
            _parse_time(decision.get("decided_at"))
        except (ValueError, TypeError):
            r.error("decision_time", path + ".decided_at", "须为带时区 ISO-8601")
        by_record_stage.setdefault((rid, stage), []).append(decision)

    for (rid, stage), group in by_record_stage.items():
        ordinary = [x for x in group if not x.get("resolves_disagreement")]
        votes = {x.get("decision") for x in ordinary}
        adjudications = [x for x in group if x.get("resolves_disagreement")]
        if len(votes) > 1 and not adjudications:
            r.error("unresolved_disagreement", "$.decisions[%s:%s]" % (rid, stage), "双人筛选分歧必须裁决，不得静默取其一")
        for adj in adjudications:
            refs = adj.get("adjudicates")
            if not isinstance(refs, list) or not refs or any(x not in decision_ids for x in refs):
                r.error("adjudication_links", "$.decisions[%s].adjudicates" % adj.get("id"), "裁决须回链分歧判定 ID")

    duplicates = _items(d.get("duplicates"))
    duplicate_ids = set()
    survivors = set()
    for i, cluster in enumerate(duplicates):
        path = "$.duplicates[%d]" % i
        _require_fields(_mapping(cluster), ("survivor_id", "duplicate_ids", "match_basis", "evidence"), path, r)
        survivor = cluster.get("survivor_id")
        if survivor not in records:
            r.error("dedup_survivor", path + ".survivor_id", "保留记录不存在")
        survivors.add(survivor)
        basis = _mapping(cluster.get("match_basis"))
        if basis.get("method") not in {"doi", "title_author_year", "manual_verified"} or not basis.get("normalized_value"):
            r.error("dedup_basis", path + ".match_basis", "须记录规范化方法与值；不得仅以相似为由合并")
        for rid in _items(cluster.get("duplicate_ids")):
            if rid not in records:
                r.error("dedup_record", path + ".duplicate_ids", "重复记录不存在: %s" % rid)
            if rid == survivor:
                r.error("dedup_self", path + ".duplicate_ids", "survivor 不能同时是 duplicate")
            if rid in duplicate_ids:
                r.error("dedup_overlap", path + ".duplicate_ids", "重复记录出现在多个簇")
            duplicate_ids.add(rid)
            final = _final_decision(by_record_stage.get((rid, "dedup"), []))
            if not final or final.get("decision") != "exclude" or "DUP" not in _items(final.get("reason_codes")):
                r.error("dedup_decision", path + ".duplicate_ids", "%s 缺 DUP 去重判定" % rid)
        if not cluster.get("evidence"):
            r.error("dedup_evidence", path + ".evidence", "须保留可人工复核的 DOI/题名等依据")

    expected_included, expected_excluded, undecided = set(), set(), set()
    for rid in records:
        if rid in duplicate_ids:
            continue
        dedup_final = _final_decision(by_record_stage.get((rid, "dedup"), []))
        title_final = _final_decision(by_record_stage.get((rid, "title_abstract"), []))
        full_final = _final_decision(by_record_stage.get((rid, "full_text"), []))
        if dedup_final and dedup_final.get("decision") == "exclude":
            r.error("unregistered_duplicate", "$.duplicates", "%s 有 DUP 判定但未登记去重依据" % rid)
            continue
        if title_final and title_final.get("decision") == "exclude":
            expected_excluded.add(rid)
        elif title_final and title_final.get("decision") == "include":
            if full_final and full_final.get("decision") == "exclude":
                expected_excluded.add(rid)
            elif full_final and full_final.get("decision") == "include":
                expected_included.add(rid)
            else:
                undecided.add(rid)
                r.error("full_text_missing", "$.decisions", "%s 题录纳入但缺全文轮最终判定" % rid)
        else:
            undecided.add(rid)
            r.error("title_decision_missing", "$.decisions", "%s 缺题录轮最终判定" % rid)
    if included != expected_included:
        r.error("included_set", "$.included", "应由最终判定重算为 %s，实际为 %s" % (sorted(expected_included), sorted(included)))
    if excluded != expected_excluded:
        r.error("excluded_set", "$.excluded", "应由最终判定重算为 %s，实际为 %s" % (sorted(expected_excluded), sorted(excluded)))
    counts = _mapping(d.get("counts"))
    actual = {"records_raw": len(records), "records_unique": len(records) - len(duplicate_ids),
              "included": len(expected_included), "excluded": len(expected_excluded),
              "duplicates": len(duplicate_ids), "undecided": len(undecided)}
    for key, value in actual.items():
        if counts.get(key) != value:
            r.error("count_recompute", "$.counts.%s" % key, "重算值 %s，填报值 %s" % (value, counts.get(key)))
    r.metrics.update(actual)
    r.metrics["reason_completeness"] = _ratio(complete_reasons, len(decisions))
    return r


def check_quality(d):
    r = Report()
    included = {x.get("id") for x in _items(d.get("included"))}
    scales = _index(d.get("quality_scales"))
    appraisals = _items(d.get("quality_appraisals"))
    seen = set()
    claims = set(_index(d.get("claims")))
    for i, appraisal in enumerate(appraisals):
        path = "$.quality_appraisals[%d]" % i
        _require_fields(_mapping(appraisal), ("record_id", "scale_id", "scale_version", "items", "overall",
                                              "impact_on_synthesis", "claim_ids"), path, r)
        rid = appraisal.get("record_id")
        if rid not in included:
            r.error("quality_record", path + ".record_id", "质量评价对象不在纳入集")
        if rid in seen:
            r.error("quality_duplicate", path + ".record_id", "同一记录重复评价；请合并评审与裁决留痕")
        seen.add(rid)
        scale = scales.get(appraisal.get("scale_id"))
        if not scale:
            r.error("quality_scale", path + ".scale_id", "量表未定义")
            continue
        if appraisal.get("scale_version") != scale.get("version"):
            r.error("quality_version", path + ".scale_version", "量表版本不一致")
        dimensions = {x.get("id"): x for x in _items(scale.get("dimensions"))}
        item_map = {}
        for j, item in enumerate(_items(appraisal.get("items"))):
            ipath = "%s.items[%d]" % (path, j)
            _require_fields(_mapping(item), ("dimension_id", "judgement", "evidence"), ipath, r)
            dim = dimensions.get(item.get("dimension_id"))
            if not dim:
                r.error("quality_dimension", ipath + ".dimension_id", "不在量表内")
                continue
            if item.get("dimension_id") in item_map:
                r.error("quality_item_duplicate", ipath + ".dimension_id", "维度重复")
            item_map[item.get("dimension_id")] = item
            scores = _mapping(dim.get("scores"))
            if item.get("judgement") not in scores or not isinstance(scores.get(item.get("judgement")), (int, float)):
                r.error("quality_judgement", ipath + ".judgement", "判定不在预设评分映射中")
            if not _valid_evidence_shape(_mapping(item.get("evidence"))):
                r.error("quality_evidence", ipath + ".evidence", "每个维度须逐字依据、哈希与精确定位")
        if set(item_map) != set(dimensions):
            r.error("quality_dimensions", path + ".items", "必须逐条覆盖量表全部维度")
        score = sum(dimensions[k]["scores"][v.get("judgement")] for k, v in item_map.items()
                    if k in dimensions and v.get("judgement") in dimensions[k].get("scores", {}))
        max_score = sum(max(_mapping(dim.get("scores")).values() or [0]) for dim in dimensions.values())
        normalized = score / max_score if max_score else None
        overall = _mapping(appraisal.get("overall"))
        if overall.get("score") != score or overall.get("max_score") != max_score:
            r.error("quality_score", path + ".overall", "总分重算为 %s/%s" % (score, max_score))
        if normalized is None or not isinstance(overall.get("normalized_score"), (int, float)) or not math.isclose(overall.get("normalized_score"), normalized, abs_tol=1e-9):
            r.error("quality_normalized", path + ".overall.normalized_score", "归一化分数应为 %s" % normalized)
        expected_rating = None
        thresholds = sorted(_items(scale.get("rating_thresholds")), key=lambda x: x.get("min", 0), reverse=True)
        for threshold in thresholds:
            if normalized is not None and normalized >= threshold.get("min", 0):
                expected_rating = threshold.get("rating")
                break
        if overall.get("rating") != expected_rating:
            r.error("quality_rating", path + ".overall.rating", "阈值重算为 %s，填报为 %s" % (expected_rating, overall.get("rating")))
        if not appraisal.get("claim_ids") or any(x not in claims for x in _items(appraisal.get("claim_ids"))):
            r.error("quality_claims", path + ".claim_ids", "质量等级必须关联其实际影响的论断")
    missing = included - seen
    if missing:
        r.error("quality_coverage", "$.quality_appraisals", "纳入研究缺质量评价: %s" % sorted(missing))
    r.metrics.update({"included": len(included), "appraised": len(seen & included),
                      "coverage": _ratio(len(seen & included), len(included))})
    return r


def check_citations(d):
    r = Report()
    records = set(_index(d.get("records")))
    included = {x.get("id") for x in _items(d.get("included"))}
    claims = _items(d.get("claims"))
    themes = set(_index(d.get("themes")))
    uncited, dangling, outside_included = [], [], []
    n_citations = precise = 0
    if not claims:
        if included:
            r.error("claims_empty", "$.claims", "有纳入研究时综述必须输出论断")
        else:
            r.unchecked("claims_empty", "$.claims", "纳入集为空；只允许输出有边界的检索局限/空白，不得编造综合论断")
    for i, claim in enumerate(claims):
        path = "$.claims[%d]" % i
        _require_fields(_mapping(claim), ("id", "text", "kind", "theme", "citations"), path, r)
        if claim.get("kind") not in {"material_fact", "inference", "uncertain"}:
            r.error("claim_kind", path + ".kind", "必须区分材料事实/合理推断/无法确定")
        if claim.get("kind") == "inference" and not claim.get("inference_rationale"):
            r.error("inference_rationale", path + ".inference_rationale", "推断须说明跨越事实的理由")
        if claim.get("kind") == "uncertain" and not claim.get("uncertainty"):
            r.error("claim_uncertainty", path + ".uncertainty", "无法确定项须说明限制")
        if claim.get("theme") not in themes:
            r.error("claim_theme", path + ".theme", "主题未声明")
        citations = _items(claim.get("citations"))
        if not citations:
            uncited.append(claim.get("id") or "claims[%d]" % i)
        for j, citation in enumerate(citations):
            cpath = "%s.citations[%d]" % (path, j)
            n_citations += 1
            rid = citation.get("record_id")
            if rid not in records:
                dangling.append({"claim": claim.get("id"), "record_id": rid})
            elif rid not in included:
                outside_included.append({"claim": claim.get("id"), "record_id": rid})
            if not _valid_evidence_shape(citation):
                r.error("citation_evidence", cpath, "须含 quote、双哈希与句/字段级 location")
            if _precision_ok(citation.get("location")):
                precise += 1
            if citation.get("support") not in {"direct", "partial", "contradicts"}:
                r.error("support_type", cpath + ".support", "须标 direct/partial/contradicts")
    if uncited:
        r.error("uncited_claims", "$.claims", "存在无引用论断: %s" % uncited)
    if dangling:
        r.error("dangling_citations", "$.claims", "引用不在文献清单: %s" % dangling)
    if outside_included:
        r.error("citation_outside_included", "$.claims", "综合论断不能使用已排除文献: %s" % outside_included)
    r.metrics.update({"uncited_claims": uncited, "dangling_citations": dangling,
                      "outside_included": outside_included, "claims": len(claims),
                      "citations": n_citations, "citation_coverage": _ratio(len(claims) - len(uncited), len(claims)),
                      "precise_location_rate": _ratio(precise, n_citations)})
    return r


def _evidence_spans(d):
    for i, claim in enumerate(_items(d.get("claims"))):
        for j, citation in enumerate(_items(claim.get("citations"))):
            yield "$.claims[%d].citations[%d]" % (i, j), citation.get("record_id"), citation
    for i, decision in enumerate(_items(d.get("decisions"))):
        yield "$.decisions[%d].evidence" % i, decision.get("record_id"), decision.get("evidence")
    for i, appraisal in enumerate(_items(d.get("quality_appraisals"))):
        for j, item in enumerate(_items(appraisal.get("items"))):
            yield "$.quality_appraisals[%d].items[%d].evidence" % (i, j), appraisal.get("record_id"), item.get("evidence")
    for i, conflict in enumerate(_items(d.get("conflicts"))):
        for j, position in enumerate(_items(conflict.get("positions"))):
            yield "$.conflicts[%d].positions[%d].citation" % (i, j), position.get("record_id"), position.get("citation")


def check_quotes(d, result_path, root=None):
    r = Report()
    records = _index(d.get("records"))
    verified = 0
    total = 0
    texts = {}
    for path, rid, evidence in _evidence_spans(d):
        total += 1
        if rid not in records:
            r.error("quote_record", path, "record_id 不在清单: %s" % rid)
            continue
        if not isinstance(evidence, dict):
            r.error("quote_shape", path, "证据对象缺失")
            continue
        quote = evidence.get("quote")
        if not isinstance(quote, str) or not quote.strip():
            r.error("quote_empty", path + ".quote", "逐字引文为空")
            continue
        if evidence.get("quote_sha256") != _sha_text(quote):
            r.error("quote_hash", path + ".quote_sha256", "应为 %s" % _sha_text(quote))
        if not _precision_ok(evidence.get("location")):
            r.error("quote_location", path + ".location", "须精确到 page/paragraph+sentence 或 field")
        source = _mapping(records[rid].get("source"))
        if evidence.get("source_sha256") != source.get("sha256"):
            r.error("source_link", path + ".source_sha256", "与记录原文哈希不一致")
        cache_key = (rid, root)
        if cache_key not in texts:
            entry = {}
            original_path = _resolve(source.get("path", ""), result_path, root)
            text_path = _resolve(source.get("text_path", ""), result_path, root)
            try:
                if _file_sha(original_path) != source.get("sha256"):
                    r.error("source_file_hash", "$.records[%s].source.sha256" % rid, "原文件已变化或路径错误")
            except OSError as exc:
                r.error("source_file_unreadable", "$.records[%s].source.path" % rid, str(exc))
            try:
                if _file_sha(text_path) != source.get("text_sha256"):
                    r.error("text_file_hash", "$.records[%s].source.text_sha256" % rid, "抽取文本已变化或路径错误")
                with open(text_path, encoding="utf-8") as f:
                    entry["text"] = f.read()
            except (OSError, UnicodeError) as exc:
                r.error("text_file_unreadable", "$.records[%s].source.text_path" % rid, str(exc))
            texts[cache_key] = entry
        text = texts[cache_key].get("text")
        if text is not None:
            if quote in text:
                verified += 1
            elif _norm_ws(quote) and _norm_ws(quote) in _norm_ws(text):
                verified += 1
            else:
                r.error("quote_not_verbatim", path + ".quote", "在该记录经哈希锁定的抽取文本中未找到逐字引文")
    if total == 0:
        if d.get("included"):
            r.error("no_evidence_spans", "$", "有纳入研究但没有可核验证据片段")
        else:
            r.unchecked("no_evidence_spans", "$", "空纳入集没有原文证据；结果必须保持 partial/issues 并说明检索边界")
    r.metrics.update({"evidence_spans": total, "verbatim_verified": verified,
                      "verbatim_rate": _ratio(verified, total)})
    return r


def check_themes(d):
    r = Report()
    themes = _index(d.get("themes"))
    claims = _index(d.get("claims"))
    included = {x.get("id") for x in _items(d.get("included"))}
    if not themes:
        if d.get("included"):
            r.error("themes_empty", "$.themes", "有纳入研究时须从文献归纳至少一个主题")
        else:
            r.unchecked("themes_empty", "$.themes", "空纳入集不归纳主题，避免由排除文献拼主题")
    assigned = set()
    for tid, theme in themes.items():
        path = "$.themes[%s]" % tid
        _require_fields(theme, ("id", "name", "derived_from", "claim_ids", "induction_note"), path, r)
        claim_ids = _items(theme.get("claim_ids"))
        if not claim_ids:
            r.error("theme_claims", path + ".claim_ids", "预设主题无论断支撑")
        actual_records = set()
        for cid in claim_ids:
            if cid in assigned:
                r.error("theme_claim_overlap", path + ".claim_ids", "论断重复分配到多个主题: %s" % cid)
            assigned.add(cid)
            claim = claims.get(cid)
            if not claim:
                r.error("theme_claim_dangling", path + ".claim_ids", "论断不存在: %s" % cid)
                continue
            if claim.get("theme") != tid:
                r.error("theme_claim_backlink", path + ".claim_ids", "%s 未回链本主题" % cid)
            if not _items(claim.get("citations")):
                r.error("theme_uncited", path + ".claim_ids", "%s 无引用" % cid)
            actual_records.update(x.get("record_id") for x in _items(claim.get("citations")))
        derived = set(_items(theme.get("derived_from")))
        if derived != actual_records:
            r.error("theme_derivation", path + ".derived_from", "须等于本主题论断实际引用文献集合 %s，实际 %s" % (sorted(actual_records), sorted(derived)))
        if not derived <= included:
            r.error("theme_excluded", path + ".derived_from", "主题不能由已排除文献支撑")
    unclassified = set(claims) - assigned
    if unclassified:
        r.error("unclassified_claims", "$.claims", "论断未纳入主题证据表: %s" % sorted(unclassified))
    r.metrics.update({"themes": len(themes), "claims_assigned": len(assigned), "unclassified": sorted(unclassified)})
    return r


def check_synthesis(d):
    r = Report()
    queries = set(_index(_mapping(d.get("search")).get("queries")))
    decisions = _items(d.get("decisions"))
    excluded = {x.get("id") for x in _items(d.get("excluded"))}
    claims = set(_index(d.get("claims")))
    gaps = _items(d.get("research_gaps"))
    if not gaps:
        r.error("gaps_empty", "$.research_gaps", "无空白也须显式 not_checked；不得省略该字段的语义检查")
    for i, gap in enumerate(gaps):
        path = "$.research_gaps[%d]" % i
        _require_fields(_mapping(gap), ("id", "statement", "kind", "bounded_to", "not_claimed", "evidence"), path, r)
        if gap.get("kind") not in {"evidence_of_absence", "search_limitation", "unchecked"}:
            r.error("gap_kind", path + ".kind", "非法")
        evidence = _mapping(gap.get("evidence"))
        if gap.get("kind") == "unchecked":
            if not evidence.get("reason"):
                r.error("gap_unchecked", path + ".evidence.reason", "未检查必须说明原因")
            r.unchecked("research_gap", path, evidence.get("reason", "not_checked"))
            continue
        query_ids = _items(evidence.get("query_ids"))
        if not query_ids or any(x not in queries for x in query_ids):
            r.error("gap_queries", path + ".evidence.query_ids", "空白须回链实际检索式")
        if gap.get("kind") == "search_limitation":
            if not evidence.get("limitation"):
                r.error("gap_limitation", path + ".evidence.limitation", "检索局限须说明是什么未覆盖")
            r.unchecked("global_absence", path, "仅支持有边界的检索局限，不支持全局不存在")
            continue
        record_ids = set(_items(evidence.get("excluded_record_ids")))
        reason_codes = set(_items(evidence.get("reason_codes")))
        if not record_ids or not record_ids <= excluded:
            r.error("gap_exclusions", path + ".evidence.excluded_record_ids", "证据性空白必须有已排除研究，不得把未检索当不存在")
        if not reason_codes:
            r.error("gap_reason_codes", path + ".evidence.reason_codes", "须给出排除理由码")
        matching = set()
        for decision in decisions:
            if decision.get("record_id") in record_ids and decision.get("decision") == "exclude":
                matching.update(_items(decision.get("reason_codes")))
        if not reason_codes <= matching:
            r.error("gap_reason_backlink", path + ".evidence.reason_codes", "理由码未出现在所指研究的排除判定中")
        if not evidence.get("claim_ids") or any(x not in claims for x in _items(evidence.get("claim_ids"))):
            r.error("gap_claims", path + ".evidence.claim_ids", "空白须关联受影响论断")

    conflicts = _items(d.get("conflicts"))
    conflict_ids = set()
    for i, conflict in enumerate(conflicts):
        path = "$.conflicts[%d]" % i
        _require_fields(_mapping(conflict), ("id", "claim_ids", "record_ids", "positions", "resolution", "impact_on_claims"), path, r)
        conflict_ids.add(conflict.get("id"))
        if any(x not in claims for x in _items(conflict.get("claim_ids"))):
            r.error("conflict_claims", path + ".claim_ids", "冲突须关联论断")
        positions = _items(conflict.get("positions"))
        support_values = {_mapping(x.get("citation")).get("support") for x in positions}
        if len(positions) < 2 or not {"direct", "contradicts"} <= support_values:
            r.error("conflict_positions", path + ".positions", "至少保留相反两端，且 citation.support 标 direct/contradicts")
        for j, position in enumerate(positions):
            if position.get("record_id") not in _items(conflict.get("record_ids")):
                r.error("conflict_record", "%s.positions[%d].record_id" % (path, j), "未在 record_ids 声明")
            if not _valid_evidence_shape(_mapping(position.get("citation"))):
                r.error("conflict_evidence", "%s.positions[%d].citation" % (path, j), "冲突两端均须逐字证据")
    if not conflicts:
        assessment = _mapping(d.get("conflict_assessment"))
        if not assessment.get("status") or not assessment.get("note"):
            r.error("conflict_assessment", "$.conflict_assessment", "未检出冲突时须说明覆盖范围/不可判断项")
        if assessment.get("status") == "not_checked":
            r.unchecked("conflicts", "$.conflict_assessment", assessment.get("note", "not_checked"))
    for i, exception in enumerate(_items(d.get("exceptions"))):
        if exception.get("type") == "contradictory_included_evidence" and exception.get("status") != "pending":
            if not set(_items(exception.get("affected_ids"))) & conflict_ids:
                r.error("exception_conflict_link", "$.exceptions[%d].affected_ids" % i, "矛盾证据异常必须回链冲突矩阵")
    r.metrics.update({"gaps": len(gaps), "conflicts": len(conflicts)})
    return r


def check_exceptions(d):
    r = Report()
    exceptions = _items(d.get("exceptions"))
    handled = set()
    for i, item in enumerate(exceptions):
        path = "$.exceptions[%d]" % i
        _require_fields(_mapping(item), ("type", "signal", "action", "status", "affected_ids", "disposition"), path, r)
        kind = item.get("type")
        if kind not in EXCEPTION_TYPES:
            r.error("exception_type", path + ".type", "未知异常类型")
        handled.add(kind)
        if item.get("status") not in {"resolved", "degraded", "human_review", "pending"}:
            r.error("exception_status", path + ".status", "非法状态")
        if item.get("status") == "pending" and d.get("status") == "pass":
            r.error("pending_on_pass", path + ".status", "有待人工事项不得 pass")
        if kind in {"database_or_interface_timeout", "permission_denied"} and item.get("status") == "resolved" and not item.get("retry_evidence"):
            r.error("retry_evidence", path + ".retry_evidence", "重试解决后须留重跑查询/读取记录")
    queries = _items(_mapping(d.get("search")).get("queries"))
    for i, query in enumerate(queries):
        if query.get("result_count") == 0 and "empty_search" not in handled:
            r.error("empty_search_unhandled", "$.search.queries[%d]" % i, "检索为空须登记分类与放宽/重跑动作")
        error = _mapping(query.get("error"))
        if error.get("type") == "timeout" and "database_or_interface_timeout" not in handled:
            r.error("timeout_unhandled", "$.search.queries[%d].error" % i, "接口超时须登记降级/重试与影响")
    for i, record in enumerate(_items(d.get("records"))):
        availability = _mapping(record.get("availability"))
        if availability.get("full_text") is False and "full_text_unavailable" not in handled:
            r.error("full_text_unhandled", "$.records[%d].availability.full_text" % i, "全文不可得须标注并说明仅摘要可判/转人工")
    if d.get("status") == "failed" and _mapping(d.get("run")).get("permission_denied") and "permission_denied" not in handled:
        r.error("permission_unhandled", "$.run.permission_denied", "权限不足须停止相关读取并交人工，不得绕过")
    r.metrics.update({"exceptions": len(exceptions), "types": sorted(handled)})
    return r


def _ratio(numerator, denominator):
    return numerator / denominator if denominator else None


def _derive_metrics(d):
    claims = _items(d.get("claims"))
    citations = [c for claim in claims for c in _items(claim.get("citations"))]
    records = set(_index(d.get("records")))
    decisions = _items(d.get("decisions"))
    complete = sum(1 for x in decisions if x.get("reason_codes") and x.get("criterion_ids") and _valid_evidence_shape(x.get("evidence")))
    included = {x.get("id") for x in _items(d.get("included"))}
    appraised = {x.get("record_id") for x in _items(d.get("quality_appraisals"))} & included
    structurally_verifiable = sum(1 for c in citations if _valid_evidence_shape(c))
    gaps = _items(d.get("research_gaps"))
    evidenced_gaps = sum(1 for g in gaps if g.get("kind") in {"evidence_of_absence", "search_limitation"} and _mapping(g.get("evidence")).get("query_ids"))
    run = _mapping(d.get("run"))
    return {
        "claims": len(claims),
        "citations": len(citations),
        "claim_citation_coverage": _ratio(sum(bool(_items(c.get("citations"))) for c in claims), len(claims)),
        "resolvable_citation_rate": _ratio(sum(c.get("record_id") in records for c in citations), len(citations)),
        "verifiable_quote_rate": _ratio(structurally_verifiable, len(citations)),
        "screening_reason_completeness": _ratio(complete, len(decisions)),
        "quality_appraisal_coverage": _ratio(len(appraised), len(included)),
        "evidenced_gap_rate": _ratio(evidenced_gaps, len(gaps)),
        "elapsed_seconds": run.get("elapsed_seconds"),
        "model_requests": run.get("model_requests"),
        "manual_rework_items": run.get("manual_rework_items"),
    }


def check_gain(d, result_path, baseline_path=None, update=False):
    r = Report()
    gain = _mapping(d.get("gain"))
    status = gain.get("comparison_status")
    if status != "completed" and not baseline_path:
        r.unchecked("gain_not_run", "$.gain", gain.get("reason", "基础 Agent 对照未运行/未提供"))
        r.error("gain_not_run", "$.gain.comparison_status", "无同输入对照证据；禁止填报增益数值")
        r.metrics = {"comparison_status": status}
        return r, d
    if not baseline_path:
        baseline_path = _mapping(gain.get("baseline")).get("result_path")
    if not baseline_path:
        r.error("baseline_path", "$.gain.baseline.result_path", "completed 对照须给基础 Agent 结果路径")
        return r, d
    baseline_resolved = _resolve(baseline_path, result_path)
    try:
        baseline = _load(baseline_resolved)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        r.error("baseline_read", "--baseline", str(exc))
        return r, d
    same_case = d.get("case_id") == baseline.get("case_id")
    skill_inputs = _mapping(_mapping(d.get("run")).get("input"))
    base_inputs = _mapping(_mapping(baseline.get("run")).get("input"))
    same_input = all(_mapping(skill_inputs.get(k)).get("sha256") == _mapping(base_inputs.get(k)).get("sha256") for k in ("case", "task"))
    same_permissions = _mapping(d.get("run")).get("permissions") == _mapping(baseline.get("run")).get("permissions")
    if not same_case or not same_input:
        r.error("different_input", "$.gain.design", "基础与 Skill 必须使用相同 case/task 哈希及 case_id")
    if not same_permissions:
        r.error("different_permissions", "$.gain.design", "双方 permissions 必须一致")
    skill_metrics = _derive_metrics(d)
    base_metrics = _derive_metrics(baseline)
    quality_keys = ("claim_citation_coverage", "resolvable_citation_rate", "verifiable_quote_rate",
                    "screening_reason_completeness", "quality_appraisal_coverage", "evidenced_gap_rate")
    efficiency_keys = ("elapsed_seconds", "model_requests", "manual_rework_items")
    deltas = {}
    for key in quality_keys + efficiency_keys:
        a, b = skill_metrics.get(key), base_metrics.get(key)
        deltas[key] = a - b if isinstance(a, (int, float)) and isinstance(b, (int, float)) else None
    baseline_hash = _file_sha(baseline_resolved)
    derived = {
        "comparison_status": "completed",
        "design": {"same_case_id": same_case, "same_input": same_input, "same_permissions": same_permissions,
                   "case_sha256": _mapping(skill_inputs.get("case")).get("sha256"),
                   "task_sha256": _mapping(skill_inputs.get("task")).get("sha256"),
                   "permissions": _mapping(d.get("run")).get("permissions")},
        "baseline": {"result_path": baseline_path, "result_sha256": baseline_hash,
                     "run_id": _mapping(baseline.get("run")).get("run_id"), "metrics": base_metrics},
        "skill": {"run_id": _mapping(d.get("run")).get("run_id"), "metrics": skill_metrics},
        "delta_skill_minus_baseline": deltas,
        "metric_definitions": {
            "claim_citation_coverage": "至少一条引用的论断数/论断总数",
            "resolvable_citation_rate": "record_id 在清单内的引用数/引用总数",
            "verifiable_quote_rate": "具逐字引文、双哈希、精确定位的引用数/引用总数（audit 另验原文）",
            "screening_reason_completeness": "理由码+条款+证据均完整的判定数/判定总数",
            "quality_appraisal_coverage": "有质量评价的纳入研究数/纳入研究数",
            "evidenced_gap_rate": "带实际检索式与边界证据的空白数/空白总数；unchecked 不计",
            "manual_rework_items": "运行记录中的人工返工项；0 仅在日志未发现返工时成立",
        },
    }
    improved = [k for k in quality_keys if isinstance(deltas[k], (int, float)) and deltas[k] > 0]
    regressed = [k for k in quality_keys if isinstance(deltas[k], (int, float)) and deltas[k] < 0]
    efficiency_improved = [k for k in efficiency_keys if isinstance(deltas[k], (int, float)) and deltas[k] < 0]
    derived["improved_quality_metrics"] = improved
    derived["regressed_quality_metrics"] = regressed
    derived["improved_efficiency_metrics_lower_is_better"] = efficiency_improved
    if update:
        if r.errors:
            return r, d
        updated = copy.deepcopy(d)
        updated["gain"] = derived
        fd, temp_path = tempfile.mkstemp(prefix=".result-", suffix=".json", dir=os.path.dirname(os.path.abspath(result_path)))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(updated, f, ensure_ascii=False, indent=2, sort_keys=True)
                f.write("\n")
            os.replace(temp_path, result_path)
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)
        r.metrics = {"updated": result_path, "improved_quality_metrics": improved,
                     "improved_efficiency_metrics_lower_is_better": efficiency_improved}
        return r, updated
    if gain.get("baseline", {}).get("result_sha256") != baseline_hash:
        r.error("baseline_hash", "$.gain.baseline.result_sha256", "与基础结果实际文件不一致")
    for section, expected in (("design", derived["design"]), ("baseline", derived["baseline"]),
                              ("skill", derived["skill"]), ("delta_skill_minus_baseline", deltas)):
        actual = gain.get(section)
        if actual != expected:
            r.error("gain_recompute", "$.gain.%s" % section, "与原始运行记录重算不一致；用 gain_check --update 由原始记录生成")
    r.metrics = {"baseline": base_metrics, "skill": skill_metrics, "delta_skill_minus_baseline": deltas,
                 "improved_quality_metrics": improved, "regressed_quality_metrics": regressed,
                 "improved_efficiency_metrics_lower_is_better": efficiency_improved}
    return r, d


def check_audit(d, result_path, baseline_path=None, case_path=None, root=None,
                verify_artifacts=False, allow_gain_not_run=False):
    r = Report()
    checks = {
        "schema": check_schema(d, result_path, case_path, verify_artifacts, root),
        "protocol_check": check_protocol(d),
        "screen_check": check_screen(d),
        "quality_check": check_quality(d),
        "cite_check": check_citations(d),
        "quote_check": check_quotes(d, result_path, root),
        "theme_check": check_themes(d),
        "synthesis_check": check_synthesis(d),
        "exception_check": check_exceptions(d),
    }
    gain_report, _ = check_gain(d, result_path, baseline_path, False)
    if allow_gain_not_run and d.get("gain", {}).get("comparison_status") != "completed":
        gain_report.errors = [e for e in gain_report.errors if e["code"] != "gain_not_run"]
    checks["gain_check"] = gain_report
    for report in checks.values():
        r.errors.extend(report.errors)
        r.warnings.extend(report.warnings)
        r.not_checked.extend(report.not_checked)
    r.metrics = {name: {"ok": not report.errors, "errors": len(report.errors), "metrics": report.metrics}
                 for name, report in checks.items()}
    r.metrics["all_checks_passed"] = not r.errors
    return r


class JsonArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        raise ValueError("命令行用法错误: %s" % message)


def _parser():
    p = JsonArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--version", action="version", version=TOOL_VERSION)
    sub = p.add_subparsers(dest="command", required=True)
    h = sub.add_parser("hash")
    h.add_argument("files", nargs="+")
    for name in ("schema", "protocol_check", "screen_check", "quality_check", "cite_check",
                 "theme_check", "synthesis_check", "exception_check"):
        q = sub.add_parser(name)
        q.add_argument("result")
        if name == "schema":
            q.add_argument("--case")
            q.add_argument("--root")
            q.add_argument("--verify-artifacts", action="store_true")
    q = sub.add_parser("quote_check")
    q.add_argument("result")
    q.add_argument("--root")
    q = sub.add_parser("gain_check")
    q.add_argument("result")
    q.add_argument("--baseline")
    q.add_argument("--update", action="store_true")
    q = sub.add_parser("audit")
    q.add_argument("result")
    q.add_argument("--baseline")
    q.add_argument("--case")
    q.add_argument("--root")
    q.add_argument("--verify-artifacts", action="store_true")
    q.add_argument("--allow-gain-not-run", action="store_true")
    return p


def main(argv=None):
    try:
        args = _parser().parse_args(argv)
    except ValueError as exc:
        r = Report()
        r.error("cli_usage", "argv", str(exc))
        _emit("cli", r)
        return 2
    with _run_logging():
        try:
            if args.command == "hash":
                r = Report()
                values = []
                for path in args.files:
                    try:
                        values.append({"path": path, "bytes": os.path.getsize(path), "sha256": _file_sha(path)})
                    except OSError as exc:
                        r.error("file_read", path, str(exc))
                r.metrics["files"] = values
                return _emit("hash", r)
            d = _load(args.result)
            if args.command == "schema":
                r = check_schema(d, args.result, args.case, args.verify_artifacts, args.root)
            elif args.command == "protocol_check":
                r = check_protocol(d)
            elif args.command == "screen_check":
                r = check_screen(d)
            elif args.command == "quality_check":
                r = check_quality(d)
            elif args.command == "cite_check":
                r = check_citations(d)
            elif args.command == "quote_check":
                r = check_quotes(d, args.result, args.root)
            elif args.command == "theme_check":
                r = check_themes(d)
            elif args.command == "synthesis_check":
                r = check_synthesis(d)
            elif args.command == "exception_check":
                r = check_exceptions(d)
            elif args.command == "gain_check":
                r, _ = check_gain(d, args.result, args.baseline, args.update)
            elif args.command == "audit":
                r = check_audit(d, args.result, args.baseline, args.case, args.root,
                                args.verify_artifacts, args.allow_gain_not_run)
            else:
                raise ValueError("unknown command")
            return _emit(args.command, r)
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
            r = Report()
            r.error("runtime_input", getattr(args, "result", ""), "%s: %s" % (type(exc).__name__, exc))
            return _emit(args.command, r)


if __name__ == "__main__":
    sys.exit(main())
