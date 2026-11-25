#!/usr/bin/env python3
"""合成样例自测：每个命令均有合规零误杀与变异必命中；不是正式案例答案。"""
import copy
import hashlib
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL = os.path.join(HERE, "..", "scripts", "crosssite_tool.py")
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


def mutate(name, source, command, expected):
    path = dump(name + ".json", source)
    rc, data = run(command, path)
    return rc, data, expected(data)


GOOD = {
    "case_id": "synthetic-c1", "status": "issues", "main_result": {"record_ids": ["r1"]},
    "schema_version": "2.0", "skill_version": "2.0.0", "run_version": "run-synthetic-001",
    "input_contract": {"case_path": "/input/case.json", "task_path": "/input/task.md",
                       "required_fields": ["case_id", "status", "main_result"],
                       "preserved_fields": ["case_id", "status", "main_result"], "expected_source_count": 1},
    "steps": [
        {"id": "W1", "depends_on": [], "input": "query-v1", "output": "source.json", "state": "done"},
        {"id": "W2", "depends_on": ["W1"], "input": "source.json", "output": "mapped.json", "state": "done"},
        {"id": "W3", "depends_on": ["W2"], "input": "mapped.json", "output": "target.json", "state": "pending"},
    ],
    "state_history": [
        {"step": "W1", "from": "pending", "to": "done", "at": "2026-01-01T00:01:00Z"},
        {"step": "W2", "from": "pending", "to": "done", "at": "2026-01-01T00:02:00Z"},
    ],
    "operations": [
        {"step": "W1", "kind": "browser", "action": "extract", "evidence": "logs/W1.jsonl",
         "locator": {"url": "http://organizer.local/source?page=1", "page_version": "dom-sha256:abc",
                     "selector": "article[data-record-id]"}},
        {"step": "W2", "kind": "api", "action": "normalize", "evidence": "logs/W2.jsonl",
         "locator": {"url": "http://organizer.local/api/records", "http_status": 200}},
    ],
    "data_passing": [{"from": "W2", "to": "W3", "source_snapshot": "source.json#sha256:abc",
                      "target_snapshot": "mapped.json#sha256:def", "permission_ref": "P1",
                      "permission_scope": "green", "source_count": 10, "target_count": 10,
                      "field_mapping": {"title": {"target": "name", "transform": "strip_html",
                                                  "encoding": "utf-8", "unit": "none"}}}],
    "permissions": [{"id": "P1", "site": "organizer.local", "account_ref": "vault://case-account",
                     "role": "editor", "scopes": ["records:write"], "status": "active"}],
    "failures": [], "sync_conflicts": [],
    "artifacts": [{"path": "/app/output/mapped.json", "kind": "intermediate", "step": "W2",
                   "sha256": hashlib.sha256(b"synthetic").hexdigest()}],
    "idempotency_keys": ["W1-run1", "W2-run1", "W3-run1"], "resume_point": "W3",
    "run_log": [{"step": "W1", "start": "2026-01-01T00:00:00Z", "result": "ok"}],
    "gain": {"baseline_success_rate": None, "skill_success_rate": None},
    "unchecked": [], "sources": [{"locator": "http://organizer.local/source", "version": "v1"}],
    "uncertainty": [], "change_log": [],
}

# 既有 flow/schema 正向与变异。
rc, d = run("flow_check", dump("flow-good.json", GOOD))
add("flow正向:DAG无环且闭合", rc == 0 and d.get("ok"), str(d))
mutants = [
    ("flow变异:成环", lambda x: x["steps"][1].update(depends_on=["W3"]), lambda d: bool(d.get("cycles"))),
    ("flow变异:依赖不存在", lambda x: x["steps"][0].update(depends_on=["W9"]),
     lambda d: any("不存在" in e for e in d.get("errors", []))),
    ("flow变异:缺字段映射", lambda x: x["data_passing"][0].pop("field_mapping"),
     lambda d: bool(d.get("missing_field_mapping"))),
    ("flow变异:权限非法", lambda x: x["data_passing"][0].update(permission_scope="public"),
     lambda d: bool(d.get("invalid_permission_scope"))),
    ("flow变异:迁移条数不符", lambda x: x["data_passing"][0].update(target_count=7),
     lambda d: bool(d.get("transfer_count_mismatch"))),
    ("flow变异:缺计数也得抓", lambda x: x["data_passing"][0].pop("source_count"),
     lambda d: bool(d.get("invalid_transfer_counts"))),
    ("flow变异:失败无续跑点", lambda x: (x["steps"][2].update(state="failed"), x.update(resume_point="")),
     lambda d: any("resume_point" in e for e in d.get("errors", []))),
    ("flow变异:幂等键重复", lambda x: x.update(idempotency_keys=["k", "k"]),
     lambda d: bool(d.get("duplicate_idempotency_keys"))),
]
for i, (name, change, expected) in enumerate(mutants):
    bad = copy.deepcopy(GOOD)
    change(bad)
    rc, d = run("flow_check", dump("flow-bad-%d.json" % i, bad))
    add(name, rc == 1 and expected(d), str(d))

rc, d = run("schema", dump("schema-good.json", GOOD))
add("schema正向:契约与版本零误杀", rc == 0 and d.get("ok"), str(d))
bad = copy.deepcopy(GOOD); bad["run_log"] = []
rc, d = run("schema", dump("schema-no-log.json", bad))
add("schema变异:run_log为空", rc == 1 and any("run_log" in e for e in d.get("errors", [])), str(d))
bad = copy.deepcopy(GOOD); bad["input_contract"]["preserved_fields"] = ["case_id", "status"]
rc, d = run("schema", dump("schema-contract-drop.json", bad))
add("schema变异:原output_contract字段丢失", rc == 1 and any("main_result" in e for e in d.get("errors", [])), str(d))
bad = copy.deepcopy(GOOD); bad.pop("skill_version")
rc, d = run("schema", dump("schema-no-version.json", bad))
add("schema变异:缺skill_version", rc == 1 and any("skill_version" in e for e in d.get("errors", [])), str(d))
bad = copy.deepcopy(GOOD); bad["input_contract"]["expected_source_count"] = 3
rc, d = run("schema", dump("schema-source-count.json", bad))
add("schema变异:实际来源数与case不符", rc == 1 and any("来源数" in e for e in d.get("errors", [])), str(d))

# audit 正向与六要素变异。
rc, d = run("audit", dump("audit-good.json", GOOD))
add("audit正向:六要素证据零误杀", rc == 0 and d.get("ok"), str(d))
audit_mutants = [
    ("audit变异:浏览器缺页面版本", lambda x: x["operations"][0]["locator"].pop("page_version"), "page_version"),
    ("audit变异:已执行步骤无操作轨迹", lambda x: x.update(operations=x["operations"][:1]), "W2"),
    ("audit变异:done无状态快照", lambda x: x.update(state_history=x["state_history"][:1]), "W2"),
    ("audit变异:映射未声明转换", lambda x: x["data_passing"][0].update(field_mapping={"title": "name"}), "target/transform"),
    ("audit变异:权限引用不存在", lambda x: x["data_passing"][0].update(permission_ref="P9"), "permission_ref"),
    ("audit变异:yellow未脱敏", lambda x: x["data_passing"][0].update(permission_scope="yellow"), "deidentification"),
    ("audit变异:red原文外传", lambda x: x["data_passing"][0].update(permission_scope="red", handling="raw"), "red"),
    ("audit变异:失败无分类恢复记录", lambda x: x["steps"][2].update(state="failed"), "分类恢复"),
    ("audit变异:登录失效仍自动重试", lambda x: (x["steps"][2].update(state="failed"), x["failures"].append(
        {"step": "W3", "category": "login_state_expired", "detection": "302 login", "action": "retry",
         "disposition": "retry", "outcome": "open", "resume_point": "W3", "idempotency_key": "W3-run1"})), "转人工"),
    ("audit变异:伪SHA256", lambda x: x["artifacts"][0].update(sha256="abc"), "SHA-256"),
]
for i, (name, change, text) in enumerate(audit_mutants):
    bad = copy.deepcopy(GOOD); change(bad)
    rc, d = run("audit", dump("audit-bad-%d.json" % i, bad))
    add(name, rc == 1 and any(text in e for e in d.get("errors", [])), str(d))
bad = copy.deepcopy(GOOD)
bad["status"] = "pass"
bad["sync_conflicts"] = [{"record_id": "r1", "resolution": "pending",
                          "left": {"version": "a", "value_ref": "left.json#r1", "retained_path": "left.json"},
                          "right": {"version": "b", "value_ref": "right.json#r1", "retained_path": "right.json"}}]
rc, d = run("audit", dump("audit-conflict.json", bad))
add("audit变异:未裁决冲突不得pass", rc == 1 and any("未裁决" in e for e in d.get("errors", [])), str(d))

# resume 正向与依赖变异。
rc, d = run("resume", dump("resume-good.json", GOOD))
add("resume正向:只续跑W3且不重放done", rc == 0 and d.get("runnable_now") == ["W3"]
    and d.get("already_done_not_replayed") == ["W1", "W2"], str(d))
bad = copy.deepcopy(GOOD); bad["steps"][0]["state"] = "pending"; bad["steps"][1]["state"] = "pending"
rc, d = run("resume", dump("resume-wait.json", bad))
add("resume变异:上游未完成下游必须等待", rc == 0 and d.get("runnable_now") == ["W1"]
    and [w["id"] for w in d.get("waiting", [])] == ["W2", "W3"], str(d))

# manifest/verify_manifest 均测正向与真实字节变异。
artifact = os.path.join(TMP, "artifact.txt")
with open(artifact, "wb") as f:
    f.write(b"evidence-v1\n")
manifest = os.path.join(TMP, "manifest.json")
rc, d = run("manifest", manifest, artifact)
add("manifest正向:真实文件生成SHA256", rc == 0 and d.get("ok") and
    d.get("artifacts", [{}])[0].get("size") == 12, str(d))
rc, d = run("verify_manifest", manifest)
add("verify_manifest正向:未改文件零误杀", rc == 0 and d.get("ok") and d.get("checked") == 1, str(d))
with open(artifact, "ab") as f:
    f.write(b"tampered")
rc, d = run("verify_manifest", manifest)
add("verify_manifest变异:文件改动必命中", rc == 1 and any("不符" in e for e in d.get("errors", [])), str(d))
rc, d = run("manifest", os.path.join(TMP, "bad-manifest.json"))
add("manifest变异:零文件调用拒绝", rc == 1 and not d.get("ok"), str(d))

ok = sum(1 for _, passed, _ in checks if passed)
for name, passed, detail in checks:
    print(("PASS" if passed else "FAIL"), name, ("| " + detail if not passed else ""))
print("total %d/%d" % (ok, len(checks)))
sys.exit(0 if ok == len(checks) else 1)
