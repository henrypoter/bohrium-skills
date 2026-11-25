#!/usr/bin/env python3
"""合成资料迁移自测：正向零误杀 + 变异必命中；不属于官方案例或预填答案。"""
import copy
import hashlib
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL = os.path.join(HERE, "..", "scripts", "auto_tool.py")
TMP = tempfile.mkdtemp()
checks = []


def run(*args):
    proc = subprocess.run([sys.executable, TOOL, *args], capture_output=True, text=True)
    try:
        return proc.returncode, json.loads(proc.stdout)
    except Exception:
        return proc.returncode, {"raw": proc.stdout[:200], "stderr": proc.stderr[:200]}


def dump(name, obj):
    path = os.path.join(TMP, name)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False)
    return path


def add(name, condition, detail=""):
    checks.append((name, condition, detail))


def check_mutant(group, index, name, obj, command, text):
    rc, data = run(command, dump("%s-%d.json" % (group, index), obj))
    matched = (not text) or any(text in error for error in data.get("errors", []))
    add(name, rc == 1 and not data.get("ok") and matched, str(data))


DIGEST = hashlib.sha256(b"synthetic-source").hexdigest()
BASE = {
    "case_id": "synthetic-migration", "status": "issues", "main_result": {"target": "organizer.sqlite"},
    "schema_version": "2.0", "skill_version": "2.0.0", "run_version": "run-synthetic-001",
    "input_contract": {"case_path": "/input/case.json", "task_path": "/input/task.md",
                       "required_fields": ["case_id", "status", "main_result"],
                       "preserved_fields": ["case_id", "status", "main_result"], "expected_source_count": 3},
    "workflow": [
        {"id": "W1", "step": "分页采集并保留原文", "depends_on": [], "input": "case sources", "output": "raw/*", "state": "done"},
        {"id": "W2", "step": "映射和去重", "depends_on": ["W1"], "input": "raw/*", "output": "mapped.jsonl", "state": "done"},
        {"id": "W3", "step": "事务写入SQLite", "depends_on": ["W2"], "input": "mapped.jsonl", "output": "record_ids[]", "state": "failed"},
    ],
    "state": {"completed_steps": ["W1", "W2"], "failed_step": "W3", "resume_point": "W3"},
    "data_passing": [{"from": "W2", "to": "W3", "field_mapping": {"title": "name"},
                      "permission_scope": "green", "permission_ref": "P1"}],
    "permission_records": [{"id": "P1", "site": "organizer.local", "role": "writer", "status": "active"}],
    "collection": [
        {"source_id": "S1", "locator": "http://organizer.local/s1", "retrieved_at": "2026-01-01T00:00:00Z",
         "retained_file": "raw/s1.html", "sha256": DIGEST, "attribution": "Synthetic Publisher A / CC-BY",
         "record_count": 4},
        {"source_id": "S2", "locator": "http://organizer.local/s2", "retrieved_at": "2026-01-01T00:01:00Z",
         "retained_file": "raw/s2.csv", "sha256": DIGEST, "attribution": "Synthetic Publisher B / CC0",
         "record_count": 3},
        {"source_id": "S3", "locator": "http://organizer.local/s3", "retrieved_at": "2026-01-01T00:02:00Z",
         "retained_file": "raw/s3.html", "sha256": DIGEST, "attribution": "Synthetic Publisher C / CC-BY",
         "record_count": 3},
    ],
    "field_mapping": [
        {"source_field": "title", "target_field": "name", "transform": "strip_html", "on_missing": "mark_unmapped"},
        {"source_field": "doi", "target_field": "identifier", "transform": "normalize_doi", "on_missing": "allow_null"},
    ],
    "unmapped": [{"source_field": "legacy_note", "reason": "目标契约无此字段", "action": "retain_raw_only"}],
    "deduplication": {"decisions": [
        {"record_refs": ["S1:r1", "S2:r1"], "decision": "exact_duplicate", "reason": "规范化DOI完全相同",
         "evidence": "dedup.jsonl#d1", "removed_count": 1},
        {"record_refs": ["S1:r4", "S3:r4"], "decision": "merged_duplicate", "reason": "DOI别名经来源原始记录确认",
         "evidence": "dedup.jsonl#d2", "removed_count": 1},
    ]},
    "migration": {"target": "/app/output/organizer.sqlite", "transaction_id": "tx-001", "transactional": True,
                  "checkpoint": "W3:batch-001", "rollback_ref": "backups/pre-W3.sqlite",
                  "write_log": [{"batch_id": "batch-001", "idempotency_key": "W3-batch-001",
                                 "attempted_count": 10, "accepted_count": 8, "rejected_count": 2}]},
    "integrity": {"source_count": 10, "target_count": 8, "exact_duplicates": 1, "merged_duplicates": 1,
                  "skipped_count": 0, "added_count": 0, "expected_differences": [],
                  "unexpected_differences": [], "source_attachments": 3, "target_attachments": 2,
                  "expected_missing_attachments": [{"record_ref": "S2:r2", "reason": "来源本身无附件"}],
                  "unexpected_missing_attachments": []},
    "artifacts": [{"path": "/app/output/mapped.jsonl", "sha256": DIGEST, "kind": "intermediate"}],
    "failures": [
        {"step": "W1", "category": "login_state_expired", "error": "302登录页", "detection": "响应跳转登录页",
         "action": "暂停并请求人工认证", "recovery": "人工认证后从page=2续跑", "disposition": "manual",
         "outcome": "recovered", "occurred_at": "2026-01-01T00:00:10Z", "resume_point": "W1",
         "idempotency_key": "W1-auth-001", "site": "organizer.local", "auth_state": "expired",
         "human_required": True, "credential_material_logged": False},
        {"step": "W2", "category": "download_failed", "error": "PDF返回HTML", "detection": "content-type=text/html",
         "action": "分段续传", "recovery": "保留.part并在恢复后校验", "disposition": "retry", "outcome": "recovered",
         "occurred_at": "2026-01-01T00:01:10Z", "resume_point": "W2", "idempotency_key": "W2-download-001",
         "source_locator": "http://organizer.local/s2/paper.pdf", "artifact": "raw/paper.pdf",
         "content_check": {"expected": "application/pdf+publisher-sha256", "observed": "text/html"},
         "partial_file_retained": True, "verification": "publisher_checksum"},
        {"step": "W3", "category": "write_failed", "error": "两行约束冲突", "detection": "SQLite constraint error",
         "action": "保留成功批次，失败行隔离", "recovery": "从事务checkpoint修复后幂等续写", "disposition": "retry",
         "outcome": "open", "occurred_at": "2026-01-01T00:03:00Z", "resume_point": "W3",
         "idempotency_key": "W3-batch-001", "target": "organizer.sqlite", "batch_id": "batch-001",
         "transaction_id": "tx-001", "transactional": True, "attempted_count": 10,
         "accepted_count": 8, "rejected_count": 2},
    ],
    "sync_conflicts": [],
    "run_log": [{"step": "W1", "start": "2026-01-01T00:00:00Z", "end": "2026-01-01T00:01:00Z", "result": "ok"},
                {"step": "W2", "start": "2026-01-01T00:01:00Z", "end": "2026-01-01T00:02:00Z", "result": "ok"},
                {"step": "W3", "start": "2026-01-01T00:02:00Z", "end": "2026-01-01T00:03:00Z", "result": "failed"}],
    "gain": {"baseline_success_rate": None, "skill_success_rate": None, "manual_steps_saved": None},
    "unchecked": ["W3两行尚未修复"], "sources": ["raw/s1.html", "raw/s2.csv", "raw/s3.html"],
    "uncertainty": [], "change_log": [],
}

# trace：保留既有能力并补硬约束。
rc, d = run("trace", dump("trace-good.json", BASE))
add("trace正向:完整DAG零误杀", rc == 0 and d.get("ok"), str(d))
trace_mutants = [
    ("trace变异:依赖不存在", lambda x: x["workflow"][2].update(depends_on=["W9"]), "不存在"),
    ("trace变异:依赖成环", lambda x: x["workflow"][0].update(depends_on=["W3"]), "成环"),
    ("trace变异:失败缺续跑点", lambda x: x["state"].update(resume_point=""), "resume_point"),
    ("trace变异:幂等键重复", lambda x: x["failures"].append(copy.deepcopy(x["failures"][2])), "idempotency_key"),
    ("trace变异:权限未声明", lambda x: x["data_passing"][0].pop("permission_scope"), "permission_scope"),
    ("trace变异:字段映射未声明", lambda x: x["data_passing"][0].pop("field_mapping"), "field_mapping"),
    ("trace变异:completed与done不一致", lambda x: x["state"].update(completed_steps=["W1"]), "completed_steps"),
    ("trace变异:步骤缺输入输出", lambda x: x["workflow"][0].pop("output"), "output"),
]
for i, (name, change, text) in enumerate(trace_mutants):
    bad = copy.deepcopy(BASE); change(bad); check_mutant("trace-bad", i, name, bad, "trace", text)

# resume：正向和等待/M跳过变异。
rc, d = run("resume", dump("resume-good.json", BASE))
add("resume正向:只续跑W3", rc == 0 and d.get("runnable_now") == ["W3"], str(d))
bad = copy.deepcopy(BASE); bad["workflow"][1]["state"] = "failed"
rc, d = run("resume", dump("resume-wait.json", bad))
add("resume变异:下游等待未完成上游", rc == 0 and d.get("runnable_now") == ["W2"]
    and any(w["id"] == "W3" for w in d.get("waiting", [])), str(d))
bad = copy.deepcopy(BASE); bad["workflow"][0]["state"] = "skipped"; bad["workflow"][1]["state"] = "pending"
rc, d = run("resume", dump("resume-skipped.json", bad))
add("resume变异:skipped不算done", rc == 0 and not d.get("runnable_now")
    and any(w["id"] == "W2" for w in d.get("waiting", [])), str(d))

# schema：原契约、来源数、版本均可机检。
rc, d = run("schema", dump("schema-good.json", BASE))
add("schema正向:契约版本与三来源零误杀", rc == 0 and d.get("ok"), str(d))
schema_mutants = [
    ("schema变异:缺run_log", lambda x: x.update(run_log=[]), "run_log"),
    ("schema变异:缺run_version", lambda x: x.pop("run_version"), "run_version"),
    ("schema变异:原字段丢失", lambda x: x["input_contract"].update(preserved_fields=["case_id", "status"]), "main_result"),
    ("schema变异:来源数与case不符", lambda x: x.update(collection=x["collection"][:2]), "来源数"),
]
for i, (name, change, text) in enumerate(schema_mutants):
    bad = copy.deepcopy(BASE); change(bad); check_mutant("schema-bad", i, name, bad, "schema", text)

# recovery_check：三类自评缺口正向均覆盖，逐项变异。
rc, d = run("recovery_check", dump("recovery-good.json", BASE))
add("recovery正向:登录/下载/写入合规零误杀", rc == 0 and d.get("ok") and d.get("checked_failures") == 3, str(d))
recovery_mutants = [
    ("recovery变异:登录失效仍自动重试", lambda x: x["failures"][0].update(disposition="retry"), "转人工"),
    ("recovery变异:认证记录疑似记录凭据", lambda x: x["failures"][0].update(credential_material_logged=True), "credential_material_logged"),
    ("recovery变异:下载内容类型未核验", lambda x: x["failures"][1]["content_check"].pop("observed"), "observed"),
    ("recovery变异:恢复下载无完整性验证", lambda x: x["failures"][1].pop("verification"), "验证"),
    ("recovery变异:写入计数不闭合", lambda x: x["failures"][2].update(rejected_count=1), "计数不闭合"),
    ("recovery变异:写入缺事务ID", lambda x: x["failures"][2].pop("transaction_id"), "transaction_id"),
    ("recovery变异:事务标志不明", lambda x: x["failures"][2].pop("transactional"), "transactional"),
    ("recovery变异:失败未分类", lambda x: x["failures"][2].update(category="something"), "category"),
]
for i, (name, change, text) in enumerate(recovery_mutants):
    bad = copy.deepcopy(BASE); change(bad); check_mutant("recovery-bad", i, name, bad, "recovery_check", text)
extra_cases = [
    ({"step": "W2", "category": "field_missing", "error": "DOI列缺失", "detection": "header检查",
      "action": "标unmapped", "recovery": "补映射后续跑", "disposition": "skip_declared", "outcome": "open",
      "occurred_at": "2026-01-01T00:01:20Z", "resume_point": "W2", "idempotency_key": "W2-field-001",
      "source_field": "doi", "record_locator": "S2:r9", "substitute_value_used": True}, "不得填假值", "字段缺失填假值"),
    ({"step": "W3", "category": "permission_denied", "error": "403", "detection": "HTTP 403",
      "action": "申请writer角色", "recovery": "人工授权后续跑", "disposition": "retry", "outcome": "blocked",
      "occurred_at": "2026-01-01T00:03:10Z", "resume_point": "W3", "idempotency_key": "W3-perm-001",
      "required_permission": "records:write"}, "转人工", "权限不足自动重试"),
    ({"step": "W3", "category": "sync_conflict", "error": "两端均修改", "detection": "etag不同",
      "action": "保留双方", "recovery": "人工裁决", "disposition": "manual", "outcome": "awaiting_manual",
      "occurred_at": "2026-01-01T00:03:20Z", "resume_point": "W3", "idempotency_key": "W3-conflict-001",
      "left_version_ref": "source.json#v2", "right_version_ref": "target.json#v7",
      "both_versions_retained": False}, "双方版本", "同步冲突覆盖一方"),
]
for i, (record, text, label) in enumerate(extra_cases):
    bad = copy.deepcopy(BASE); bad["failures"].append(record)
    check_mutant("recovery-extra", i, "recovery变异:" + label, bad, "recovery_check", text)

# migration_check：全链计数与去重/附件/事务。
rc, d = run("migration_check", dump("migration-good.json", BASE))
add("migration正向:采集到事务写入闭合", rc == 0 and d.get("ok") and d.get("counts", {}).get("sources") == 3, str(d))
migration_mutants = [
    ("migration变异:来源无attribution", lambda x: x["collection"][0].pop("attribution"), "attribution"),
    ("migration变异:来源哈希伪造", lambda x: x["collection"][0].update(sha256="abc"), "sha256"),
    ("migration变异:来源记录数不闭合", lambda x: x["collection"][0].update(record_count=5), "总和"),
    ("migration变异:重复目标字段静默覆盖", lambda x: x["field_mapping"][1].update(target_field="name"), "静默覆盖"),
    ("migration变异:unmapped无理由", lambda x: x["unmapped"][0].pop("reason"), "reason"),
    ("migration变异:疑似重复被自动删除", lambda x: x["deduplication"]["decisions"][0].update(decision="suspected_duplicate"), "不得自动删除"),
    ("migration变异:记录恒等式不闭合", lambda x: x["integrity"].update(target_count=7), "恒等式"),
    ("migration变异:去重计数与决策不符", lambda x: x["integrity"].update(exact_duplicates=0), "去重决策"),
    ("migration变异:附件缺失未列清单", lambda x: x["integrity"].update(expected_missing_attachments=[]), "附件差值"),
    ("migration变异:非预期差异仍pass", lambda x: (x.update(status="pass"), x["integrity"]["unexpected_differences"].append({"record_ref": "S1:r1"})), "不得 status=pass"),
    ("migration变异:非事务写入", lambda x: x["migration"].update(transactional=False), "transactional"),
    ("migration变异:缺回滚引用", lambda x: x["migration"].pop("rollback_ref"), "rollback_ref"),
]
for i, (name, change, text) in enumerate(migration_mutants):
    bad = copy.deepcopy(BASE); change(bad); check_mutant("migration-bad", i, name, bad, "migration_check", text)

# manifest 与 verify_manifest：真实文件而非自报哈希。
artifact = os.path.join(TMP, "retained-source.txt")
with open(artifact, "wb") as f:
    f.write(b"source-v1\n")
manifest = os.path.join(TMP, "manifest.json")
rc, d = run("manifest", manifest, artifact)
add("manifest正向:计算真实SHA256", rc == 0 and d.get("ok") and d.get("artifacts", [{}])[0].get("size") == 10, str(d))
rc, d = run("verify_manifest", manifest)
add("verify_manifest正向:原文件零误杀", rc == 0 and d.get("ok") and d.get("checked") == 1, str(d))
with open(artifact, "ab") as f:
    f.write(b"changed")
rc, d = run("verify_manifest", manifest)
add("verify_manifest变异:字节改动必命中", rc == 1 and any("不符" in e for e in d.get("errors", [])), str(d))
rc, d = run("manifest", os.path.join(TMP, "empty.json"))
add("manifest变异:无文件输入拒绝", rc == 1 and not d.get("ok"), str(d))

ok = sum(1 for _, passed, _ in checks if passed)
for name, passed, detail in checks:
    print(("PASS" if passed else "FAIL"), name, ("| " + detail if not passed else ""))
print("total %d/%d" % (ok, len(checks)))
sys.exit(0 if ok == len(checks) else 1)
