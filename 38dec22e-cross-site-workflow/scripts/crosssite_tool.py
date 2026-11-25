#!/usr/bin/env python3
"""跨站工作流的可执行判对闸与证据工具（仅 Python 标准库）。

  flow_check <result.json>       DAG/状态/映射/权限/计数/幂等硬校验
  schema <result.json>           交付字段、原始 output_contract 保留与版本校验
  audit <result.json>            六要素证据审计：状态、操作、权限、传递、恢复、冲突
  resume <result.json>           只返回依赖已满足且未完成的步骤，不重复 done
  manifest <out.json> <file>...  为真实产物计算 size/sha256，生成可复核清单
  verify_manifest <manifest>     重读文件并重算 size/sha256；缺失或改动即失败
"""
import hashlib
import json
import os
import sys

PERM = {"green", "yellow", "red"}
STATE = {"pending", "done", "failed", "blocked", "skipped"}
STATUS = {"pass", "issues", "partial", "failed"}
FAILURE_CATEGORIES = {
    "login_state_expired", "mfa_required", "cross_origin", "element_missing",
    "timeout", "rate_limited", "permission_denied", "sync_conflict",
    "download_failed", "write_failed", "other",
}
REQUIRED_TOP = (
    "case_id", "status", "schema_version", "skill_version", "run_version",
    "input_contract", "steps", "state_history", "operations", "data_passing",
    "permissions", "failures", "sync_conflicts", "artifacts", "run_log",
    "gain", "unchecked", "sources", "uncertainty", "change_log",
)


def _load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _emit(payload, ok=True):
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0 if ok else 1


def _is_count(value):
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _cycle_paths(steps):
    adj = {s.get("id"): list(s.get("depends_on") or []) for s in steps}
    color, cycles = {}, []

    def dfs(node, path):
        color[node] = 1
        for dep in adj.get(node, []):
            if dep not in adj:
                continue
            if color.get(dep) == 1:
                cycles.append(path + [dep])
            elif color.get(dep, 0) == 0:
                dfs(dep, path + [dep])
        color[node] = 2

    for node in adj:
        if color.get(node, 0) == 0:
            dfs(node, [node])
    return cycles


def _flow_result(d):
    steps = d.get("steps", d.get("workflow", []))
    if not isinstance(steps, list):
        steps = []
    ids = [s.get("id") for s in steps]
    id_set = set(ids)
    errs = []
    if not steps:
        errs.append("steps 为空")
    if len(ids) != len(id_set) or None in id_set:
        errs.append("步骤 id 缺失或重复")
    for s in steps:
        sid = s.get("id")
        for dep in s.get("depends_on") or []:
            if dep not in id_set:
                errs.append("步骤 %s 依赖不存在的 %s" % (sid, dep))
        if s.get("state") not in STATE:
            errs.append("步骤 %s 状态非法: %s" % (sid, s.get("state")))
    cycles = _cycle_paths(steps)
    failed = [s.get("id") for s in steps if s.get("state") in {"failed", "blocked"}]
    if failed and not d.get("resume_point"):
        errs.append("有 failed/blocked 步骤但缺 resume_point")
    no_map, no_perm, mismatch, bad_counts = [], [], [], []
    passing = d.get("data_passing") or []
    for p in passing:
        label = "%s->%s" % (p.get("from") or "?", p.get("to") or "?")
        if not p.get("field_mapping"):
            no_map.append(label)
        if p.get("permission_scope") not in PERM:
            no_perm.append(label)
        source_count, target_count = p.get("source_count"), p.get("target_count")
        if not _is_count(source_count) or not _is_count(target_count):
            bad_counts.append(label)
        elif source_count != target_count and not p.get("expected_differences"):
            mismatch.append({"pass": label, "source": source_count, "target": target_count})
    keys = [x for x in (d.get("idempotency_keys") or []) if x]
    dup_keys = sorted(k for k in set(keys) if keys.count(k) > 1)
    out = {
        "ok": not (errs or cycles or no_map or no_perm or mismatch or bad_counts or dup_keys),
        "n_steps": len(steps), "cycles": cycles, "missing_field_mapping": no_map,
        "invalid_permission_scope": no_perm, "transfer_count_mismatch": mismatch,
        "invalid_transfer_counts": bad_counts, "duplicate_idempotency_keys": dup_keys,
        "errors": errs,
    }
    return out


def cmd_flow_check(path):
    out = _flow_result(_load(path))
    return _emit(out, out["ok"])


def _contract_errors(d):
    errs = []
    contract = d.get("input_contract")
    if not isinstance(contract, dict):
        return ["input_contract 必须是对象"]
    for key in ("case_path", "task_path"):
        if not contract.get(key):
            errs.append("input_contract 缺 %s" % key)
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
        if not _is_count(expected_sources):
            errs.append("input_contract.expected_source_count 必须是非负整数")
        elif len(d.get("sources") or []) != expected_sources:
            errs.append("实际来源数与 case 要求不符: expected=%s actual=%s" %
                        (expected_sources, len(d.get("sources") or [])))
    return errs


def cmd_schema(path):
    d = _load(path)
    if not isinstance(d, dict):
        return _emit({"ok": False, "errors": ["顶层必须是对象"]}, False)
    errs = ["缺顶层字段 %s" % k for k in REQUIRED_TOP if k not in d]
    if d.get("status") not in STATUS:
        errs.append("status 非法")
    for key in ("schema_version", "skill_version", "run_version"):
        if key in d and not d.get(key):
            errs.append("%s 为空" % key)
    if not d.get("run_log"):
        errs.append("run_log 为空(状态须随手记录)")
    if "input_contract" in d:
        errs.extend(_contract_errors(d))
    if d.get("status") == "pass" and not d.get("artifacts"):
        errs.append("pass 状态缺 artifacts 证据清单")
    out = {"ok": not errs, "errors": errs, "steps": len(d.get("steps") or [])}
    return _emit(out, out["ok"])


def _require_fields(record, fields, label, errs):
    for field in fields:
        if field not in record or record.get(field) in (None, ""):
            errs.append("%s 缺 %s" % (label, field))


def cmd_audit(path):
    d = _load(path)
    errs = []
    steps = d.get("steps") or []
    step_by_id = {s.get("id"): s for s in steps}
    operations = d.get("operations") or []
    operation_steps = set()
    for i, op in enumerate(operations):
        label = "operations[%d]" % i
        _require_fields(op, ("step", "kind", "action", "evidence", "locator"), label, errs)
        step, kind = op.get("step"), op.get("kind")
        operation_steps.add(step)
        if step not in step_by_id:
            errs.append("%s 指向未知步骤 %s" % (label, step))
        locator = op.get("locator") if isinstance(op.get("locator"), dict) else {}
        if kind == "browser":
            _require_fields(locator, ("url", "page_version", "selector"), label + ".locator", errs)
        elif kind == "software":
            _require_fields(locator, ("software", "version", "window_or_document"), label + ".locator", errs)
        elif kind == "api":
            _require_fields(locator, ("url",), label + ".locator", errs)
            if not _is_count(locator.get("http_status")):
                errs.append("%s.locator.http_status 必须是非负整数" % label)
        else:
            errs.append("%s.kind 必须是 browser/software/api" % label)
    for step in steps:
        if step.get("state") in {"done", "failed", "blocked"} and step.get("id") not in operation_steps:
            errs.append("步骤 %s 已执行但缺 browser/software/api 操作证据" % step.get("id"))
        _require_fields(step, ("id", "input", "output", "state"), "步骤", errs)
    history = d.get("state_history") or []
    done_in_history = set()
    for i, event in enumerate(history):
        _require_fields(event, ("step", "from", "to", "at"), "state_history[%d]" % i, errs)
        if event.get("to") not in STATE:
            errs.append("state_history[%d].to 非法" % i)
        if event.get("step") not in step_by_id:
            errs.append("state_history[%d] 指向未知步骤" % i)
        if event.get("to") == "done":
            done_in_history.add(event.get("step"))
    for step in steps:
        if step.get("state") == "done" and step.get("id") not in done_in_history:
            errs.append("done 步骤 %s 缺到 done 的状态快照" % step.get("id"))
    permissions = d.get("permissions") or []
    permission_by_id = {p.get("id"): p for p in permissions}
    for i, permission in enumerate(permissions):
        _require_fields(permission, ("id", "site", "account_ref", "role", "scopes", "status"),
                        "permissions[%d]" % i, errs)
        if permission.get("account_ref") and any(x in str(permission.get("account_ref")).lower()
                                                for x in ("password", "token", "secret")):
            errs.append("permissions[%d].account_ref 疑似包含凭据" % i)
    for i, passing in enumerate(d.get("data_passing") or []):
        label = "data_passing[%d]" % i
        _require_fields(passing, ("from", "to", "field_mapping", "source_snapshot",
                                  "target_snapshot", "permission_ref", "permission_scope"), label, errs)
        mapping = passing.get("field_mapping") if isinstance(passing.get("field_mapping"), dict) else {}
        for source, spec in mapping.items():
            if not isinstance(spec, dict) or not spec.get("target") or not spec.get("transform"):
                errs.append("%s.field_mapping.%s 必须含 target/transform（单位编码格式也在此声明）" % (label, source))
        permission = permission_by_id.get(passing.get("permission_ref"))
        if permission is None:
            errs.append("%s.permission_ref 无对应权限记录" % label)
        elif passing.get("target_count", 0) and permission.get("status") != "active":
            errs.append("%s 有实际传输但权限不是 active" % label)
        if passing.get("permission_scope") == "yellow" and not passing.get("deidentification"):
            errs.append("%s yellow 数据缺 deidentification" % label)
        if passing.get("permission_scope") == "red" and passing.get("handling") not in {"hash_or_id_only", "blocked"}:
            errs.append("%s red 数据只能 hash_or_id_only/blocked" % label)
    failures = d.get("failures") or []
    failure_steps = set()
    for i, failure in enumerate(failures):
        label = "failures[%d]" % i
        _require_fields(failure, ("step", "category", "detection", "action", "disposition",
                                  "outcome", "resume_point", "idempotency_key"), label, errs)
        failure_steps.add(failure.get("step"))
        if failure.get("category") not in FAILURE_CATEGORIES:
            errs.append("%s.category 未归类" % label)
        if failure.get("disposition") not in {"retry", "fallback", "skip_declared", "manual", "rollback"}:
            errs.append("%s.disposition 非法" % label)
        if failure.get("category") in {"login_state_expired", "mfa_required", "permission_denied", "cross_origin"} \
                and failure.get("disposition") != "manual":
            errs.append("%s 必须停止转人工，不得自动绕过" % label)
    for step in steps:
        if step.get("state") in {"failed", "blocked"} and step.get("id") not in failure_steps:
            errs.append("步骤 %s failed/blocked 但缺分类恢复记录" % step.get("id"))
    for i, conflict in enumerate(d.get("sync_conflicts") or []):
        label = "sync_conflicts[%d]" % i
        _require_fields(conflict, ("record_id", "left", "right", "resolution"), label, errs)
        for side in ("left", "right"):
            value = conflict.get(side) if isinstance(conflict.get(side), dict) else {}
            _require_fields(value, ("version", "value_ref", "retained_path"), label + "." + side, errs)
        if conflict.get("resolution") == "pending" and d.get("status") == "pass":
            errs.append("%s 未裁决时不得 status=pass" % label)
    for i, artifact in enumerate(d.get("artifacts") or []):
        _require_fields(artifact, ("path", "sha256", "kind", "step"), "artifacts[%d]" % i, errs)
        digest = artifact.get("sha256", "")
        if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest.lower()):
            errs.append("artifacts[%d].sha256 不是 SHA-256" % i)
    if d.get("status") == "pass" and any(s.get("state") != "done" for s in steps):
        errs.append("status=pass 但仍有非 done 步骤")
    out = {"ok": not errs, "errors": errs,
           "coverage": {"steps": len(steps), "operations": len(operations),
                        "state_events": len(history), "transfers": len(d.get("data_passing") or []),
                        "failures": len(failures), "conflicts": len(d.get("sync_conflicts") or [])}}
    return _emit(out, out["ok"])


def cmd_resume(path):
    d = _load(path)
    steps = d.get("steps", d.get("workflow", []))
    done = {s.get("id") for s in steps if s.get("state") == "done"}
    runnable, waiting, needs_intervention = [], [], []
    for step in steps:
        state = step.get("state")
        if state == "done":
            continue
        deps = step.get("depends_on") or []
        unmet = [dep for dep in deps if dep not in done]
        item = {"id": step.get("id"), "state": state, "unmet_deps": unmet}
        if state in {"blocked", "skipped"}:
            needs_intervention.append(item)
        elif unmet:
            waiting.append(item)
        else:
            runnable.append(step.get("id"))
    out = {"ok": True, "runnable_now": runnable, "waiting": waiting,
           "needs_intervention_not_replayed": needs_intervention,
           "already_done_not_replayed": sorted(done), "resume_point": d.get("resume_point", "")}
    return _emit(out)


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
    out_path, paths = args[0], args[1:]
    payload = {"manifest_version": "1", "algorithm": "sha256", "artifacts": _manifest_rows(paths)}
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")
    return _emit({"ok": True, "manifest": os.path.abspath(out_path), "artifacts": payload["artifacts"]})


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
        if command in {"flow_check", "schema", "audit", "resume", "verify_manifest"}:
            if len(rest) != 1:
                return _emit({"ok": False, "errors": ["该命令只需一个 JSON 路径"]}, False)
            return {
                "flow_check": cmd_flow_check, "schema": cmd_schema, "audit": cmd_audit,
                "resume": cmd_resume, "verify_manifest": cmd_verify_manifest,
            }[command](rest[0])
        if command == "manifest":
            return cmd_manifest(rest)
        print(__doc__)
        return 2
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        return _emit({"ok": False, "errors": ["读取或执行失败: %s" % exc]}, False)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
