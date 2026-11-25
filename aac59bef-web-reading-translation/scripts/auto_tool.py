#!/usr/bin/env python3
"""科研自动化交付机检。纯标准库。

  trace RESULT.json   DAG/状态/恢复点/幂等键/权限与轨迹一致性
  resume RESULT.json  计算真正可续跑步骤（失败/阻塞依赖不当作完成）
  schema RESULT.json  result.json 2.0.0 结构、版本、定位、增益字段校验
  audit RESULT.json BILINGUAL.json [--snapshot P --meta M]
                       逐段字段回链，且可从原始 HTML 重算语料哈希
  compare BASELINE.json SKILL.json --out GAIN.json
                       同输入同权限实测记录的质量/效率算术对照
"""
import copy
import datetime
import hashlib
import json
import os
import re
import sys

TOOL_VERSION = "3.0.0"
SCHEMA_VERSION = "2.0.0"
STATES = {"pending", "done", "failed", "skipped", "blocked"}
PERMISSIONS = {"green", "yellow", "red"}
FAILURE_KINDS = {
    "login_expired", "second_factor_required", "paywall", "permission_denied", "cross_domain_redirect",
    "page_changed", "missing_article_element", "dynamic_render_failed", "lazy_load_unresolved", "pagination",
    "timeout", "network_error", "rate_limited", "http_error", "oversized_page", "translation_interrupted",
    "alignment_interrupted", "paragraph_misalignment", "sync_conflict", "field_missing", "field_type_error",
    "abstract_only", "access_control", "unversioned_snapshot", "unsupported_scheme", "extract_error",
}
SEMVER = re.compile(r"^\d+\.\d+\.\d+$")


def _load(path):
    with open(path, encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError("%s 顶层必须是对象" % path)
    return value


def _hash_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _canonical(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _emit(value, code=0):
    print(json.dumps(value, ensure_ascii=False))
    return code


def _graph(steps):
    return {s.get("id"): (s.get("depends_on") or []) for s in steps}


def _cycle(graph):
    color = {}

    def dfs(node, stack):
        color[node] = 1
        for other in graph.get(node, []):
            if other not in graph:
                continue
            if color.get(other) == 1:
                return stack + [node, other]
            if color.get(other, 0) == 0:
                found = dfs(other, stack + [node])
                if found:
                    return found
        color[node] = 2
        return None

    for node in graph:
        if color.get(node, 0) == 0:
            found = dfs(node, [])
            if found:
                return found
    return None


def trace_errors(document):
    errors, warnings = [], []
    steps = document.get("workflow") or []
    if not isinstance(steps, list):
        return ["workflow 必须是数组"], warnings
    ids = [s.get("id") for s in steps if isinstance(s, dict)]
    if len(ids) != len(set(ids)):
        errors.append("workflow 步骤 id 重复")
    graph = _graph(steps)
    for step in steps:
        sid = step.get("id")
        if not sid or not step.get("step"):
            errors.append("步骤缺 id/step")
        if step.get("state") not in STATES:
            errors.append("步骤 %s 状态非法: %s" % (sid, step.get("state")))
        deps = step.get("depends_on") or []
        if not isinstance(deps, list):
            errors.append("步骤 %s depends_on 必须是数组" % sid)
            deps = []
        if len(deps) != len(set(deps)):
            errors.append("步骤 %s 依赖重复" % sid)
        if sid in deps:
            errors.append("步骤 %s 自依赖" % sid)
        for dep in deps:
            if dep not in graph:
                errors.append("步骤 %s 依赖不存在的 %s" % (sid, dep))
        if step.get("input") in (None, "") or step.get("output") in (None, ""):
            errors.append("步骤 %s 缺 input/output(无法复跑)" % sid)
    cycle = _cycle(graph)
    if cycle:
        errors.append("依赖成环: %s" % " -> ".join(cycle))
    state = document.get("state") or {}
    failed = state.get("failed_step")
    resume_point = state.get("resume_point")
    failed_steps = [x.get("id") for x in steps if x.get("state") in {"failed", "blocked"}]
    if (failed or failed_steps) and not resume_point:
        errors.append("存在失败/阻塞步骤但缺 resume_point")
    if resume_point and resume_point not in graph:
        errors.append("resume_point %s 不在步骤列表中" % resume_point)
    done = {x.get("id") for x in steps if x.get("state") == "done"}
    recorded = set(state.get("completed_steps") or [])
    if done != recorded:
        errors.append("state.completed_steps 与 workflow.done 不一致: done=%s recorded=%s" % (sorted(done), sorted(recorded)))
    known_failure_steps = set()
    for index, failure in enumerate(document.get("failures") or []):
        for key in ("step", "kind", "signal", "action", "state"):
            if not failure.get(key):
                errors.append("failures[%d] 缺 %s" % (index, key))
        if failure.get("kind") not in FAILURE_KINDS:
            errors.append("failures[%d] kind 未登记: %s" % (index, failure.get("kind")))
        if failure.get("state") not in {"failed", "blocked", "recovered", "partial"}:
            errors.append("failures[%d] state 非法" % index)
        if not failure.get("idempotency_key"):
            errors.append("failures[%d] 缺 idempotency_key" % index)
        if failure.get("retry") is not None and (not isinstance(failure.get("retry"), int) or failure.get("retry") < 0):
            errors.append("failures[%d] retry 必须是非负整数" % index)
        known_failure_steps.add(failure.get("step"))
    keys = [f.get("idempotency_key") for f in (document.get("failures") or []) if f.get("idempotency_key")]
    if len(keys) != len(set(keys)):
        errors.append("idempotency_key 重复；同一事件只记一次并用 retry 记录次数")
    for sid in failed_steps:
        if sid not in known_failure_steps:
            errors.append("失败/阻塞步骤 %s 没有 failures 记录" % sid)
    for index, passing in enumerate(document.get("data_passing") or []):
        if passing.get("permission_scope") not in PERMISSIONS:
            errors.append("data_passing[%d] permission_scope 必须是 green/yellow/red" % index)
        if not passing.get("field_mapping"):
            errors.append("data_passing[%d] 缺 field_mapping" % index)
        if passing.get("from") not in graph or passing.get("to") not in graph:
            errors.append("data_passing[%d] from/to 不是已登记步骤" % index)
    logs = document.get("run_log") or []
    logged_steps = set()
    required_log_states = {"done", "failed", "blocked", "skipped"}
    for index, entry in enumerate(logs):
        if entry.get("step") not in graph:
            errors.append("run_log[%d].step 未登记" % index)
        logged_steps.add(entry.get("step"))
        for key in ("started_at", "ended_at", "result", "command"):
            if not entry.get(key):
                errors.append("run_log[%d] 缺 %s" % (index, key))
        for key in ("started_at", "ended_at"):
            value = entry.get(key)
            if value:
                try:
                    datetime.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
                except ValueError:
                    errors.append("run_log[%d].%s 不是 ISO 时间" % (index, key))
    for step in steps:
        if step.get("state") in required_log_states and step.get("id") not in logged_steps:
            errors.append("已执行步骤 %s 无 run_log" % step.get("id"))
    return errors, warnings


def cmd_trace(path):
    try:
        document = _load(path)
        errors, warnings = trace_errors(document)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return _emit({"ok": False, "errors": [str(exc)], "warnings": []}, 1)
    return _emit({"ok": not errors, "n_steps": len(document.get("workflow") or []),
                  "errors": errors, "warnings": warnings}, 0 if not errors else 1)


def cmd_resume(path):
    try:
        document = _load(path)
        pre_errors, _ = trace_errors(document)
        fatal = [x for x in pre_errors if "依赖" in x or "成环" in x or "id 重复" in x]
        if fatal:
            return _emit({"ok": False, "errors": fatal, "runnable_now": [], "waiting": []}, 1)
        steps = document.get("workflow") or []
        done = {s.get("id") for s in steps if s.get("state") == "done"}
        by_id = {s.get("id"): s for s in steps}
        runnable, waiting = [], []
        for step in steps:
            sid = step.get("id")
            if step.get("state") == "done":
                continue
            unmet, blocked = [], []
            for dep in step.get("depends_on") or []:
                if dep not in done:
                    unmet.append(dep)
                    dep_state = by_id.get(dep, {}).get("state")
                    if dep_state in {"failed", "blocked"} or (dep_state == "skipped" and not by_id.get(dep, {}).get("optional")):
                        blocked.append(dep)
            item = {"id": sid, "state": step.get("state"), "unmet_deps": unmet, "blocked_deps": blocked,
                    "action": "先恢复/人工处理阻塞上游" if blocked else "等待上游完成"}
            (waiting if unmet else runnable).append(item)
        return _emit({"ok": True, "runnable_now": [x["id"] for x in runnable], "waiting": waiting,
                      "resume_point": (document.get("state") or {}).get("resume_point")}, 0)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return _emit({"ok": False, "errors": [str(exc)], "runnable_now": [], "waiting": []}, 1)


def schema_errors(document):
    errors, warnings = [], []
    required = ("case_id", "status", "schema_version", "skill_version", "tool_version", "run_id", "generated_at",
                "input", "source", "corpus_sha256", "full_text_sha256", "extraction_status", "paragraphs", "machine_verification",
                "workflow", "state", "data_passing", "failures", "run_log", "gain", "artifacts",
                "unchecked", "sources", "uncertainty", "change_log")
    for key in required:
        if key not in document:
            errors.append("缺顶层字段 %s" % key)
    if document.get("status") not in {"pass", "issues", "partial", "failed"}:
        errors.append("status 非法")
    for key in ("schema_version", "skill_version", "tool_version"):
        if not SEMVER.match(str(document.get(key, ""))):
            errors.append("%s 必须为 x.y.z 版本字段" % key)
    if "schema_version" in document and document.get("schema_version") != SCHEMA_VERSION:
        errors.append("schema_version 不支持: %s" % document.get("schema_version"))
    if not document.get("case_id") or not document.get("run_id"):
        errors.append("case_id/run_id 不能为空")
    if document.get("generated_at"):
        try:
            datetime.datetime.fromisoformat(str(document["generated_at"]).replace("Z", "+00:00"))
        except ValueError:
            errors.append("generated_at 不是 ISO 时间")
    input_info = document.get("input") or {}
    for key in ("case_path", "task_path", "case_sha256", "task_sha256"):
        if not input_info.get(key):
            errors.append("input 缺 %s" % key)
    source = document.get("source") or {}
    early_failure = document.get("status") in {"failed", "partial"} and not document.get("paragraphs")
    for key in ("url", "fetched_at", "snapshot_path", "snapshot_sha256", "page_version", "root_dom_path"):
        if key not in source or (not source.get(key) and not early_failure):
            errors.append("source 缺 %s%s" % (key, "（早期失败也必须显式置 null）" if key not in source else ""))
    for key in ("case_sha256", "task_sha256"):
        if input_info.get(key) and not re.fullmatch(r"[0-9a-f]{64}", str(input_info[key])):
            errors.append("input.%s 必须是 sha256" % key)
    for key in ("snapshot_sha256",):
        if source.get(key) and not re.fullmatch(r"[0-9a-f]{64}", str(source[key])):
            errors.append("source.%s 必须是 sha256" % key)
    for key in ("corpus_sha256", "full_text_sha256"):
        if document.get(key) and not re.fullmatch(r"[0-9a-f]{64}", str(document[key])):
            errors.append("%s 必须是 sha256" % key)
    paragraphs = document.get("paragraphs")
    if not isinstance(paragraphs, list):
        errors.append("paragraphs 必须是数组")
        paragraphs = []
    ids = []
    for index, paragraph in enumerate(paragraphs):
        if not isinstance(paragraph, dict):
            errors.append("paragraphs[%d] 不是对象" % index)
            continue
        for key in ("id", "order", "kind", "quote", "source_sha256", "target", "location"):
            if key not in paragraph:
                errors.append("paragraphs[%d] 缺 %s" % (index, key))
        ids.append(paragraph.get("id"))
        loc = paragraph.get("location") or {}
        for key in ("url", "snapshot_sha256", "dom_path", "html_anchor", "block_order", "char_start", "char_end"):
            if key not in loc:
                errors.append("paragraphs[%d].location 缺 %s" % (index, key))
        if paragraph.get("source_sha256") and paragraph["source_sha256"] != hashlib.sha256(paragraph.get("quote", "").encode("utf-8")).hexdigest():
            errors.append("paragraphs[%d].source_sha256 与 quote 不匹配" % index)
        if paragraph.get("id") and not str(paragraph.get("id")).startswith("B"):
            warnings.append("paragraphs[%d].id 非工具生成的 Bxxxx" % index)
    if len(ids) != len(set(ids)):
        errors.append("paragraphs.id 重复")
    verification = document.get("machine_verification") or {}
    for key in ("status", "errors", "warnings", "source_blocks", "aligned_blocks", "missing_blocks",
                "protected_token_violations", "glossary_checks", "glossary_consistent_checks", "semantic_fidelity"):
        if key not in verification:
            errors.append("machine_verification 缺 %s" % key)
    if verification.get("semantic_fidelity") != "not_checked_by_tool":
        errors.append("semantic_fidelity 必须诚实保留 not_checked_by_tool；语义审校另记 change_log")
    sources = document.get("sources")
    if not isinstance(sources, list) or (not sources and not early_failure):
        errors.append("sources 必须是对象数组；除早期失败外至少一个可核验来源")
    else:
        for index, item in enumerate(sources):
            if not isinstance(item, dict):
                errors.append("sources[%d] 必须是对象" % index)
                continue
            for key in ("url", "fetched_at", "snapshot_sha256", "location"):
                if not item.get(key):
                    errors.append("sources[%d] 缺 %s" % (index, key))
    artifacts = document.get("artifacts") or []
    for index, item in enumerate(artifacts):
        if not isinstance(item, dict):
            errors.append("artifacts[%d] 必须是对象" % index)
            continue
        for key in ("path", "sha256", "media_type", "role"):
            if not item.get(key):
                errors.append("artifacts[%d] 缺 %s" % (index, key))
    for index, item in enumerate(document.get("unchecked") or []):
        if not isinstance(item, dict) or not item.get("item") or not item.get("reason") or item.get("status") != "not_checked":
            errors.append("unchecked[%d] 必须含 item/reason/status=not_checked" % index)
    gain = document.get("gain") or {}
    if gain.get("status") not in {"measured", "not_measured"}:
        errors.append("gain.status 必须是 measured/not_measured")
    elif gain["status"] == "not_measured":
        if not gain.get("reason"):
            errors.append("gain.not_measured 必须给 reason")
        if gain.get("baseline") is not None or gain.get("skill") is not None:
            errors.append("未实测时 gain.baseline/skill 必须为 null")
    else:
        for key in ("same_input", "same_permissions", "baseline", "skill", "delta", "evidence", "comparison_hash"):
            if key not in gain:
                errors.append("gain.measured 缺 %s" % key)
        if gain.get("same_input") is not True or gain.get("same_permissions") is not True:
            errors.append("measured gain 必须同输入同权限")
        if not re.fullmatch(r"[0-9a-f]{64}", str(gain.get("comparison_hash", ""))):
            errors.append("gain.comparison_hash 不是 sha256")
    trace, trace_warnings = trace_errors(document)
    errors.extend(trace)
    warnings.extend(trace_warnings)
    if document.get("status") in {"issues", "partial", "failed"} and not (document.get("unchecked") or document.get("failures") or verification.get("errors") or verification.get("warnings") or verification.get("missing_blocks")):
        errors.append("非 pass 状态必须在 unchecked/failures/machine_verification 中说明具体缺口")
    if document.get("status") == "pass":
        if not paragraphs:
            errors.append("status=pass 但 paragraphs 为空")
        if document.get("extraction_status") != "pass":
            errors.append("status=pass 但 extraction_status 不是 pass（分页/懒加载/权限缺口必须降级）")
        if verification.get("errors") or verification.get("warnings") or verification.get("missing_blocks"):
            errors.append("status=pass 但机器校验仍有 errors/warnings/missing")
        if verification.get("aligned_blocks") != verification.get("source_blocks"):
            errors.append("status=pass 但 aligned_blocks != source_blocks")
        if any(x.get("state") != "done" for x in document.get("workflow") or []):
            errors.append("status=pass 但工作流有未 done 步骤")
        if document.get("unchecked"):
            errors.append("status=pass 但 unchecked 非空")
    return errors, warnings


def cmd_schema(path):
    try:
        document = _load(path)
        errors, warnings = schema_errors(document)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        errors, warnings = [str(exc)], []
    return _emit({"ok": not errors, "errors": errors, "warnings": warnings,
                  "schema_version": SCHEMA_VERSION, "tool_version": TOOL_VERSION}, 0 if not errors else 1)


def cmd_audit(args):
    errors, warnings = [], []
    try:
        result = _load(args.result)
        bilingual = _load(args.bilingual)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return _emit({"ok": False, "errors": [str(exc)], "warnings": []}, 1)
    schema, schema_warnings = schema_errors(result)
    errors.extend(schema)
    warnings.extend(schema_warnings)
    for key in ("corpus_sha256", "full_text_sha256", "extraction_status"):
        if result.get(key) != bilingual.get(key):
            errors.append("result.%s 与 bilingual 不一致" % key)
    if result.get("source") != bilingual.get("source"):
        errors.append("result.source 与 bilingual.source 不一致")
    if result.get("machine_verification") != bilingual.get("verification"):
        errors.append("result.machine_verification 与 bilingual.verification 不一致")
    expected_paragraphs = bilingual.get("paragraphs") or []
    actual_paragraphs = result.get("paragraphs") or []
    if result.get("status") == "pass" and len(actual_paragraphs) != len(expected_paragraphs):
        errors.append("pass 结果未逐段包含 bilingual 的全部段落")
    actual_by_id = {p.get("id"): p for p in actual_paragraphs}
    for expected in expected_paragraphs:
        actual = actual_by_id.get(expected.get("id"))
        if actual is None:
            if result.get("status") == "pass":
                errors.append("result 缺段落 " + str(expected.get("id")))
            continue
        for key in ("order", "kind", "section_path", "section_kind", "location", "quote", "source_sha256", "target"):
            if actual.get(key) != expected.get(key):
                errors.append("%s 字段 %s 与 bilingual/原文锚点不一致" % (expected.get("id"), key))
        for key in ("formulas", "table"):
            if key in expected and actual.get(key) != expected.get(key):
                errors.append("%s 的 %s 结构被改变" % (expected.get("id"), key))
    for actual in actual_paragraphs:
        if actual.get("id") not in {x.get("id") for x in expected_paragraphs}:
            errors.append("result 出现 bilingual 不存在的段落 " + str(actual.get("id")))
    if bool(args.snapshot) != bool(args.meta):
        errors.append("--snapshot 与 --meta 必须同时提供")
    if args.snapshot and args.meta:
        try:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            if script_dir not in sys.path:
                sys.path.insert(0, script_dir)
            import webread
            corpus = webread.extract_document(args.snapshot, args.meta)
            if corpus.get("corpus_sha256") != bilingual.get("corpus_sha256"):
                errors.append("从原始快照重算的 corpus_sha256 不同，产物不是该页面的可复跑结果")
            if corpus.get("full_text_sha256") != bilingual.get("full_text_sha256"):
                errors.append("从原始快照重算的 full_text_sha256 不同")
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
            errors.append("原始快照重算失败: " + str(exc))
    artifact_report = []
    base = os.path.dirname(os.path.abspath(args.result))
    for index, artifact in enumerate(result.get("artifacts") or []):
        path = artifact.get("path", "")
        resolved = path if os.path.isabs(path) else os.path.join(base, path)
        if not os.path.isfile(resolved):
            errors.append("artifacts[%d] 文件不存在: %s" % (index, path))
            continue
        actual = _hash_file(resolved)
        artifact_report.append({"path": path, "bytes": os.path.getsize(resolved), "sha256": actual})
        if actual != artifact.get("sha256"):
            errors.append("artifacts[%d] sha256 与文件实际内容不符" % index)
    return _emit({"ok": not errors and not warnings, "errors": errors, "warnings": warnings,
                  "checked_paragraphs": len(actual_paragraphs), "snapshot_recomputed": bool(args.snapshot),
                  "artifacts": artifact_report, "audit_version": TOOL_VERSION}, 0 if not errors and not warnings else 1)


def _ratio(numerator, denominator):
    if denominator == 0:
        return None
    return numerator / denominator


def _run_metrics(document):
    errors = []
    for key in ("case_id", "run_id", "source_sha256", "permissions", "totals", "evidence"):
        if key not in document:
            errors.append("run 缺 " + key)
    if not re.fullmatch(r"[0-9a-f]{64}", str(document.get("source_sha256", ""))):
        errors.append("run.source_sha256 必须是 sha256")
    permissions = document.get("permissions")
    if not isinstance(permissions, list) or not permissions or not all(isinstance(x, str) and x for x in permissions):
        errors.append("run.permissions 必须是非空字符串数组")
        permissions = []
    totals = document.get("totals") or {}
    nonnegative = ("expected_body_blocks", "extracted_body_blocks", "translated_body_blocks", "quote_verified_blocks",
                   "protected_tokens_total", "protected_token_violations", "glossary_checks", "glossary_consistent_checks",
                   "manual_actions", "repeated_fetches")
    for key in nonnegative:
        if not isinstance(totals.get(key), int) or isinstance(totals.get(key), bool) or totals.get(key) < 0:
            errors.append("totals.%s 必须是非负整数（布尔值也不算）" % key)
    if not isinstance(totals.get("elapsed_seconds"), (int, float)) or isinstance(totals.get("elapsed_seconds"), bool) or totals.get("elapsed_seconds", 0) <= 0:
        errors.append("totals.elapsed_seconds 必须是正数")
    triples = (("extracted_body_blocks", "expected_body_blocks"), ("translated_body_blocks", "expected_body_blocks"),
               ("quote_verified_blocks", "extracted_body_blocks"), ("protected_token_violations", "protected_tokens_total"),
               ("glossary_consistent_checks", "glossary_checks"))
    for top, bottom in triples:
        if isinstance(totals.get(top), int) and isinstance(totals.get(bottom), int) and totals[top] > totals[bottom]:
            errors.append("totals.%s 不得大于 %s" % (top, bottom))
    evidence = document.get("evidence") or {}
    evidence_report = {}
    for key in ("result_path", "log_path"):
        path = evidence.get(key)
        if not path or not os.path.isfile(path):
            errors.append("evidence.%s 不存在" % key)
        else:
            digest = _hash_file(path)
            evidence_report[key] = {"path": os.path.abspath(path), "sha256": digest}
            try:
                value = _load(path)
                if key == "result_path" and value.get("case_id") != document.get("case_id"):
                    errors.append("evidence.result_path 的 case_id 不一致")
                if key == "log_path" and not value.get("run_log"):
                    errors.append("evidence.log_path 无 run_log")
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                errors.append("evidence.%s 不可读: %s" % (key, exc))
    quality = {
        "extraction_completeness": _ratio(totals.get("extracted_body_blocks", 0), totals.get("expected_body_blocks", 0)),
        "translation_coverage": _ratio(totals.get("translated_body_blocks", 0), totals.get("expected_body_blocks", 0)),
        "quote_verifiability": _ratio(totals.get("quote_verified_blocks", 0), totals.get("extracted_body_blocks", 0)),
        "protected_token_fidelity": (1 - _ratio(totals.get("protected_token_violations", 0), totals.get("protected_tokens_total", 0))) if totals.get("protected_tokens_total", 0) else None,
        "glossary_consistency": _ratio(totals.get("glossary_consistent_checks", 0), totals.get("glossary_checks", 0)),
    }
    efficiency = {"manual_actions": totals.get("manual_actions"), "repeated_fetches": totals.get("repeated_fetches"),
                  "elapsed_seconds": totals.get("elapsed_seconds")}
    return errors, {"run_id": document.get("run_id"), "quality": quality, "efficiency": efficiency,
                    "raw_totals": copy.deepcopy(totals), "evidence": evidence_report}


def cmd_compare(args):
    try:
        baseline = _load(args.baseline)
        skill = _load(args.skill)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return _emit({"ok": False, "errors": [str(exc)]}, 1)
    errors = []
    base_errors, base_metrics = _run_metrics(baseline)
    skill_errors, skill_metrics = _run_metrics(skill)
    errors.extend("baseline: " + x for x in base_errors)
    errors.extend("skill: " + x for x in skill_errors)
    if baseline.get("case_id") != skill.get("case_id"):
        errors.append("两次运行 case_id 不同，不能作为同输入增益")
    if baseline.get("source_sha256") != skill.get("source_sha256"):
        errors.append("两次运行 source_sha256 不同，不能作为同页面版本增益")
    if sorted(baseline.get("permissions") or []) != sorted(skill.get("permissions") or []):
        errors.append("两次运行 permissions 不同，不是同权限对照")
    if baseline.get("run_id") == skill.get("run_id"):
        errors.append("baseline/skill run_id 相同，不能证明两次独立运行")
    bq, sq = base_metrics["quality"], skill_metrics["quality"]
    be, se = base_metrics["efficiency"], skill_metrics["efficiency"]
    delta_quality = {key: (sq[key] - bq[key] if sq[key] is not None and bq[key] is not None else None) for key in bq}
    delta_efficiency = {
        "manual_actions_saved": (be["manual_actions"] - se["manual_actions"]) if be["manual_actions"] is not None and se["manual_actions"] is not None else None,
        "repeated_fetches_reduced": (be["repeated_fetches"] - se["repeated_fetches"]) if be["repeated_fetches"] is not None and se["repeated_fetches"] is not None else None,
        "elapsed_seconds_saved": (be["elapsed_seconds"] - se["elapsed_seconds"]) if be["elapsed_seconds"] is not None and se["elapsed_seconds"] is not None else None,
    }
    gain = {"status": "measured", "same_input": baseline.get("case_id") == skill.get("case_id") and baseline.get("source_sha256") == skill.get("source_sha256"),
            "same_permissions": sorted(baseline.get("permissions") or []) == sorted(skill.get("permissions") or []),
            "comparison_method": "same_case_same_snapshot_same_permissions_two_recorded_runs",
            "case_id": baseline.get("case_id"), "source_sha256": baseline.get("source_sha256"),
            "baseline": base_metrics, "skill": skill_metrics, "delta": {"quality": delta_quality, "efficiency": delta_efficiency},
            "evidence": [base_metrics["evidence"], skill_metrics["evidence"]],
            "official_platform_comparison": False,
            "note": "这是所给两次实测记录的确定性算术对照；不是平台榜单成绩，不由工具推断语义翻译质量"}
    gain["comparison_hash"] = _canonical({k: v for k, v in gain.items() if k != "comparison_hash"})
    if not errors:
        parent = os.path.dirname(os.path.abspath(args.out))
        if parent and not os.path.isdir(parent):
            os.makedirs(parent, exist_ok=True)
        temp = args.out + ".tmp"
        with open(temp, "w", encoding="utf-8") as handle:
            json.dump(gain, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(temp, args.out)
    return _emit({"ok": not errors, "errors": errors, "out": args.out if not errors else None,
                  "gain": gain if not errors else None}, 0 if not errors else 1)


def _parser():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("trace", "resume", "schema"):
        item = sub.add_parser(name); item.add_argument("result")
    item = sub.add_parser("audit"); item.add_argument("result"); item.add_argument("bilingual")
    item.add_argument("--snapshot"); item.add_argument("--meta")
    item = sub.add_parser("compare"); item.add_argument("baseline"); item.add_argument("skill"); item.add_argument("--out", required=True)
    return parser


def main(argv=None):
    args = _parser().parse_args(argv)
    if args.command == "trace":
        return cmd_trace(args.result)
    if args.command == "resume":
        return cmd_resume(args.result)
    if args.command == "schema":
        return cmd_schema(args.result)
    if args.command == "audit":
        return cmd_audit(args)
    if args.command == "compare":
        return cmd_compare(args)
    return 2


def entrypoint():
    try:
        return main()
    except (OSError, ValueError, KeyError, TypeError, AttributeError, IndexError, json.JSONDecodeError) as exc:
        return _emit({"ok": False, "errors": ["输入结构/类型非法或运行失败: %s" % exc], "warnings": [],
                      "failure_kind": "field_type_error", "tool_version": TOOL_VERSION}, 1)


if __name__ == "__main__":
    sys.exit(entrypoint())
