#!/usr/bin/env python3
"""科研资料采集迁移：DAG、恢复、完整性与真实文件哈希判对闸（仅标准库）。

  trace <result.json>          DAG/状态/续跑点/幂等键/权限/输入输出校验
  resume <result.json>         仅列依赖 done 的未完成步骤；skipped 不算完成
  recovery_check <result.json> 登录失效、下载失败、写入报错等分类恢复硬校验
  migration_check <result.json> 采集-映射-去重-事务写入-计数/附件完整性闭合
  schema <result.json>         原 output_contract、版本及交付字段校验
  manifest <out.json> <file>... 生成真实文件 size/sha256 清单
  verify_manifest <manifest>   重算 size/sha256，文件缺失或改动即失败
"""
import hashlib
import json
import os
import sys

STATES = {"pending", "done", "failed", "blocked", "skipped"}
STATUS = {"pass", "issues", "partial", "failed"}
FAILURE_CATEGORIES = {
    "login_state_expired", "mfa_required", "download_failed", "field_missing",
    "write_failed", "permission_denied", "sync_conflict", "element_missing",
    "timeout", "rate_limited", "cross_origin", "other",
}
DEDUP_DECISIONS = {"exact_duplicate", "suspected_duplicate", "distinct", "same_name_different", "merged_duplicate"}
REQUIRED_TOP = (
    "case_id", "status", "schema_version", "skill_version", "run_version", "input_contract",
    "workflow", "state", "data_passing", "failures", "run_log", "collection",
    "field_mapping", "unmapped", "deduplication", "migration", "integrity", "artifacts",
    "permission_records", "sync_conflicts", "gain", "unchecked", "sources", "uncertainty", "change_log",
)


def _load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _emit(payload, ok=True):
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0 if ok else 1


def _count(value):
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _required(record, fields, label, errs):
    for field in fields:
        if field not in record or record.get(field) in (None, ""):
            errs.append("%s 缺 %s" % (label, field))


def _graph(steps):
    return {s.get("id"): (s.get("depends_on") or []) for s in steps}


def _cycle(graph):
    color = {}

    def dfs(node, stack):
        color[node] = 1
        for dep in graph.get(node, []):
            if dep not in graph:
                continue
            if color.get(dep) == 1:
                return stack + [node, dep]
            if color.get(dep, 0) == 0:
                found = dfs(dep, stack + [node])
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


def cmd_trace(path):
    d = _load(path)
    steps = d.get("workflow") or []
    graph = _graph(steps)
    errs, warnings = [], []
    ids = [s.get("id") for s in steps]
    if not steps:
        errs.append("workflow 为空")
    if len(ids) != len(set(ids)) or None in ids:
        errs.append("workflow 步骤 id 缺失或重复")
    for step in steps:
        sid = step.get("id")
        if step.get("state") not in STATES:
            errs.append("步骤 %s 状态非法: %s" % (sid, step.get("state")))
        for dep in step.get("depends_on") or []:
            if dep not in graph:
                errs.append("步骤 %s 依赖不存在的 %s" % (sid, dep))
        _required(step, ("input", "output"), "步骤 %s" % sid, errs)
    cycle = _cycle(graph)
    if cycle:
        errs.append("依赖成环: %s" % " -> ".join(cycle))
    state = d.get("state") or {}
    failed_steps = [s.get("id") for s in steps if s.get("state") in {"failed", "blocked"}]
    failed, resume_point = state.get("failed_step"), state.get("resume_point")
    if (failed or failed_steps) and not resume_point:
        errs.append("有失败步骤但缺 state.resume_point")
    if failed_steps and not failed:
        errs.append("workflow 有 failed/blocked 但 state.failed_step 为空")
    if resume_point and resume_point not in graph:
        errs.append("resume_point %s 不在步骤列表中" % resume_point)
    completed = state.get("completed_steps")
    if isinstance(completed, list):
        actual_done = {s.get("id") for s in steps if s.get("state") == "done"}
        if set(completed) != actual_done:
            errs.append("state.completed_steps 与 workflow done 集不一致")
    for i, failure in enumerate(d.get("failures") or []):
        _required(failure, ("step", "error", "recovery"), "failures[%d]" % i, errs)
    keys = [f.get("idempotency_key") for f in d.get("failures") or [] if f.get("idempotency_key")]
    if len(keys) != len(set(keys)):
        errs.append("不同失败记录复用同一 idempotency_key；同一逻辑失败请合并 attempts")
    for i, passing in enumerate(d.get("data_passing") or []):
        if not passing.get("permission_scope"):
            errs.append("data_passing[%d] 未声明 permission_scope" % i)
        if not passing.get("field_mapping"):
            errs.append("data_passing[%d] 未给 field_mapping" % i)
    out = {"ok": not errs, "n_steps": len(steps), "errors": errs, "warnings": warnings}
    return _emit(out, out["ok"])


def cmd_resume(path):
    d = _load(path)
    steps = d.get("workflow") or []
    done = {s.get("id") for s in steps if s.get("state") == "done"}
    runnable, waiting, needs_intervention = [], [], []
    for step in steps:
        state = step.get("state")
        if state == "done":
            continue
        unmet = [dep for dep in step.get("depends_on") or [] if dep not in done]
        item = {"id": step.get("id"), "state": state, "unmet_deps": unmet}
        if state in {"blocked", "skipped"}:
            needs_intervention.append(item)
        elif unmet:
            waiting.append(item)
        else:
            runnable.append(step.get("id"))
    out = {"ok": True, "runnable_now": runnable, "waiting": waiting,
           "needs_intervention_not_replayed": needs_intervention,
           "already_done_not_replayed": sorted(done),
           "resume_point": (d.get("state") or {}).get("resume_point")}
    return _emit(out)


def _contract_errors(d):
    errs = []
    contract = d.get("input_contract")
    if not isinstance(contract, dict):
        return ["input_contract 必须是对象"]
    _required(contract, ("case_path", "task_path"), "input_contract", errs)
    required = contract.get("required_fields")
    preserved = contract.get("preserved_fields")
    if not isinstance(required, list) or not required:
        errs.append("input_contract.required_fields 必须是非空数组")
        required = []
    if not isinstance(preserved, list):
        errs.append("input_contract.preserved_fields 必须是数组")
        preserved = []
    for field in required:
        if field not in preserved:
            errs.append("原始 output_contract 字段未声明保留: %s" % field)
        if field not in d:
            errs.append("原始 output_contract 字段不在 result.json: %s" % field)
    expected_sources = contract.get("expected_source_count")
    if expected_sources is not None:
        if not _count(expected_sources):
            errs.append("input_contract.expected_source_count 必须是非负整数")
        elif len(d.get("collection") or []) != expected_sources:
            errs.append("实际来源数与 case 要求不符: expected=%s actual=%s" %
                        (expected_sources, len(d.get("collection") or [])))
    return errs


def cmd_schema(path):
    d = _load(path)
    if not isinstance(d, dict):
        return _emit({"ok": False, "errors": ["顶层必须是对象"]}, False)
    errs = ["缺顶层字段 %s" % key for key in REQUIRED_TOP if key not in d]
    if d.get("status") not in STATUS:
        errs.append("status 非法")
    for key in ("schema_version", "skill_version", "run_version"):
        if key in d and not d.get(key):
            errs.append("%s 为空" % key)
    if not d.get("run_log"):
        errs.append("run_log 为空(无逐步骤执行记录)")
    if "input_contract" in d:
        errs.extend(_contract_errors(d))
    if d.get("status") == "pass" and not d.get("artifacts"):
        errs.append("pass 状态缺 artifacts 证据清单")
    out = {"ok": not errs, "steps": len(d.get("workflow") or []), "errors": errs}
    return _emit(out, out["ok"])


def cmd_recovery_check(path):
    d = _load(path)
    errs = []
    steps = {s.get("id"): s for s in d.get("workflow") or []}
    failures = d.get("failures") or []
    failure_steps = set()
    for i, failure in enumerate(failures):
        label = "failures[%d]" % i
        _required(failure, ("step", "category", "error", "detection", "action", "recovery",
                            "disposition", "outcome", "occurred_at", "resume_point", "idempotency_key"),
                  label, errs)
        category = failure.get("category")
        failure_steps.add(failure.get("step"))
        if failure.get("step") not in steps:
            errs.append("%s.step 不在 workflow" % label)
        if category not in FAILURE_CATEGORIES:
            errs.append("%s.category 非法：登录/下载/写入等必须明确分类" % label)
        if failure.get("disposition") not in {"retry", "fallback", "manual", "rollback", "skip_declared"}:
            errs.append("%s.disposition 非法" % label)
        if failure.get("outcome") not in {"open", "recovered", "blocked", "awaiting_manual"}:
            errs.append("%s.outcome 非法" % label)
        if category in {"login_state_expired", "mfa_required"}:
            _required(failure, ("site", "auth_state"), label, errs)
            if failure.get("human_required") is not True:
                errs.append("%s 登录失效/二次认证必须 human_required=true" % label)
            if failure.get("disposition") != "manual":
                errs.append("%s 登录失效必须停止转人工，不得自动绕过" % label)
            if failure.get("credential_material_logged") is not False:
                errs.append("%s 必须声明 credential_material_logged=false" % label)
        if category == "download_failed":
            _required(failure, ("source_locator", "artifact", "content_check"), label, errs)
            if not isinstance(failure.get("partial_file_retained"), bool):
                errs.append("%s.partial_file_retained 必须是布尔值" % label)
            check = failure.get("content_check") if isinstance(failure.get("content_check"), dict) else {}
            _required(check, ("expected", "observed"), label + ".content_check", errs)
            if failure.get("outcome") == "recovered" and not failure.get("verification"):
                errs.append("%s 下载恢复后缺 checksum/size+content_type 验证" % label)
        if category == "write_failed":
            _required(failure, ("target", "batch_id", "transaction_id"), label, errs)
            counts = [failure.get(k) for k in ("attempted_count", "accepted_count", "rejected_count")]
            if not all(_count(v) for v in counts):
                errs.append("%s 写入 attempted/accepted/rejected_count 必须是非负整数" % label)
            elif counts[0] != counts[1] + counts[2]:
                errs.append("%s 写入计数不闭合: attempted != accepted + rejected" % label)
            if not isinstance(failure.get("transactional"), bool):
                errs.append("%s.transactional 必须显式为布尔值" % label)
            if failure.get("disposition") == "rollback" and not failure.get("rollback_ref"):
                errs.append("%s 回滚缺 rollback_ref" % label)
        if category == "field_missing":
            _required(failure, ("source_field", "record_locator"), label, errs)
            if failure.get("substitute_value_used") is not False:
                errs.append("%s 字段缺失不得填假值，须 substitute_value_used=false" % label)
        if category == "permission_denied":
            _required(failure, ("required_permission",), label, errs)
            if failure.get("disposition") != "manual":
                errs.append("%s 权限不足必须转人工申请授权" % label)
        if category == "sync_conflict":
            _required(failure, ("left_version_ref", "right_version_ref"), label, errs)
            if failure.get("both_versions_retained") is not True:
                errs.append("%s 冲突双方版本必须保留" % label)
    failed_steps = {s.get("id") for s in steps.values() if s.get("state") in {"failed", "blocked"}}
    for sid in sorted(failed_steps - failure_steps):
        errs.append("workflow 步骤 %s failed/blocked 但缺恢复记录" % sid)
    for i, log in enumerate((d.get("migration") or {}).get("write_log") or []):
        counts = [log.get(k) for k in ("attempted_count", "accepted_count", "rejected_count")]
        if not all(_count(v) for v in counts) or counts[0] != counts[1] + counts[2]:
            errs.append("migration.write_log[%d] 写入计数不闭合" % i)
        _required(log, ("batch_id", "idempotency_key"), "migration.write_log[%d]" % i, errs)
    out = {"ok": not errs, "errors": errs, "checked_failures": len(failures),
           "categories": sorted({f.get("category") for f in failures if f.get("category")})}
    return _emit(out, out["ok"])


def cmd_migration_check(path):
    d = _load(path)
    errs = []
    collection = d.get("collection") or []
    if not collection:
        errs.append("collection 为空：未保留真实来源快照")
    source_total = 0
    source_ids = set()
    for i, source in enumerate(collection):
        label = "collection[%d]" % i
        _required(source, ("source_id", "locator", "retrieved_at", "retained_file", "sha256",
                           "attribution", "record_count"), label, errs)
        if source.get("source_id") in source_ids:
            errs.append("%s.source_id 重复" % label)
        source_ids.add(source.get("source_id"))
        digest = source.get("sha256", "")
        if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest.lower()):
            errs.append("%s.sha256 非法" % label)
        if not _count(source.get("record_count")):
            errs.append("%s.record_count 必须是非负整数" % label)
        else:
            source_total += source["record_count"]
    mapping = d.get("field_mapping") or []
    if not mapping:
        errs.append("field_mapping 为空")
    targets = set()
    for i, item in enumerate(mapping):
        _required(item, ("source_field", "target_field", "transform", "on_missing"),
                  "field_mapping[%d]" % i, errs)
        if item.get("target_field") in targets:
            errs.append("field_mapping[%d].target_field 重复，可能静默覆盖" % i)
        targets.add(item.get("target_field"))
    for i, item in enumerate(d.get("unmapped") or []):
        _required(item, ("source_field", "reason", "action"), "unmapped[%d]" % i, errs)
    dedup = d.get("deduplication") if isinstance(d.get("deduplication"), dict) else {}
    exact_removed = merged_removed = 0
    for i, decision in enumerate(dedup.get("decisions") or []):
        label = "deduplication.decisions[%d]" % i
        _required(decision, ("record_refs", "decision", "reason", "evidence", "removed_count"), label, errs)
        if decision.get("decision") not in DEDUP_DECISIONS:
            errs.append("%s.decision 非法" % label)
        if not isinstance(decision.get("record_refs"), list) or len(decision.get("record_refs") or []) < 2:
            errs.append("%s.record_refs 至少两条，才能复核合并/误判" % label)
        if not _count(decision.get("removed_count")):
            errs.append("%s.removed_count 必须是非负整数" % label)
        elif decision.get("decision") == "exact_duplicate":
            exact_removed += decision["removed_count"]
        elif decision.get("decision") == "merged_duplicate":
            merged_removed += decision["removed_count"]
        elif decision["removed_count"]:
            errs.append("%s distinct/suspected/same_name 不得自动删除" % label)
    integrity = d.get("integrity") if isinstance(d.get("integrity"), dict) else {}
    for key in ("source_count", "target_count", "exact_duplicates", "merged_duplicates",
                "skipped_count", "added_count", "source_attachments", "target_attachments"):
        if not _count(integrity.get(key)):
            errs.append("integrity.%s 必须是非负整数" % key)
    if collection and integrity.get("source_count") != source_total:
        errs.append("来源快照 record_count 总和不等于 integrity.source_count")
    if integrity.get("exact_duplicates") != exact_removed:
        errs.append("exact_duplicates 与去重决策 removed_count 不一致")
    if integrity.get("merged_duplicates") != merged_removed:
        errs.append("merged_duplicates 与合并决策 removed_count 不一致")
    if all(_count(integrity.get(k)) for k in ("source_count", "target_count", "exact_duplicates",
                                              "merged_duplicates", "skipped_count", "added_count")):
        expected = (integrity["target_count"] + integrity["exact_duplicates"] +
                    integrity["merged_duplicates"] + integrity["skipped_count"] - integrity["added_count"])
        if integrity["source_count"] != expected:
            errs.append("记录恒等式不闭合: source != target + exact + merged + skipped - added")
    if _count(integrity.get("source_attachments")) and _count(integrity.get("target_attachments")):
        missing = integrity["source_attachments"] - integrity["target_attachments"]
        if missing != len(integrity.get("expected_missing_attachments") or []) + len(integrity.get("unexpected_missing_attachments") or []):
            errs.append("附件差值未逐项列入 expected/unexpected_missing_attachments")
    if integrity.get("unexpected_differences") or integrity.get("unexpected_missing_attachments"):
        if d.get("status") == "pass":
            errs.append("存在非预期字段/附件差异时不得 status=pass")
    migration = d.get("migration") if isinstance(d.get("migration"), dict) else {}
    _required(migration, ("target", "transaction_id", "checkpoint", "rollback_ref"), "migration", errs)
    if migration.get("transactional") is not True:
        errs.append("migration.transactional 必须为 true")
    out = {"ok": not errs, "errors": errs,
           "counts": {"sources": len(collection), "source_records": source_total,
                      "mapping": len(mapping), "dedup_decisions": len(dedup.get("decisions") or [])}}
    return _emit(out, out["ok"])


def _manifest_rows(paths):
    rows = []
    for path in paths:
        absolute = os.path.abspath(path)
        digest = hashlib.sha256()
        size = 0
        with open(absolute, "rb") as f:
            while True:
                chunk = f.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                digest.update(chunk)
        rows.append({"path": absolute, "size": size, "sha256": digest.hexdigest()})
    return rows


def cmd_manifest(args):
    if len(args) < 2:
        return _emit({"ok": False, "errors": ["用法: manifest <out.json> <file>..."]}, False)
    out_path = args[0]
    rows = _manifest_rows(args[1:])
    payload = {"manifest_version": "1", "algorithm": "sha256", "artifacts": rows}
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")
    return _emit({"ok": True, "manifest": os.path.abspath(out_path), "artifacts": rows})


def cmd_verify_manifest(path):
    payload = _load(path)
    rows = payload.get("artifacts") if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        return _emit({"ok": False, "errors": ["manifest 必须是数组或含 artifacts 数组"]}, False)
    errs, checked = [], 0
    for i, row in enumerate(rows):
        try:
            actual = _manifest_rows([row["path"]])[0]
            checked += 1
            if actual["size"] != row.get("size"):
                errs.append("artifacts[%d] size 不符" % i)
            if actual["sha256"] != row.get("sha256"):
                errs.append("artifacts[%d] sha256 不符" % i)
        except (OSError, KeyError, TypeError) as exc:
            errs.append("artifacts[%d] 无法复核: %s" % (i, exc))
    out = {"ok": not errs, "checked": checked, "errors": errs}
    return _emit(out, out["ok"])


def main(args):
    if not args:
        print(__doc__)
        return 2
    command, rest = args[0], args[1:]
    try:
        single = {
            "trace": cmd_trace, "resume": cmd_resume, "schema": cmd_schema,
            "recovery_check": cmd_recovery_check, "migration_check": cmd_migration_check,
            "verify_manifest": cmd_verify_manifest,
        }
        if command in single:
            if len(rest) != 1:
                return _emit({"ok": False, "errors": ["该命令只需一个 JSON 路径"]}, False)
            return single[command](rest[0])
        if command == "manifest":
            return cmd_manifest(rest)
        print(__doc__)
        return 2
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        return _emit({"ok": False, "errors": ["读取或执行失败: %s" % exc]}, False)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
