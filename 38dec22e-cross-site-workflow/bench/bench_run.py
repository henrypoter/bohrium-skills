#!/usr/bin/env python3
"""crosssite_tool 自测：DAG/状态/字段映射/权限/迁移完整性/幂等。"""
import json, os, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL = os.path.join(HERE, "..", "scripts", "crosssite_tool.py")
TMP = tempfile.mkdtemp()
checks = []


def run(*a):
    r = subprocess.run([sys.executable, TOOL, *a], capture_output=True, text=True)
    try:
        return r.returncode, json.loads(r.stdout)
    except Exception:
        return r.returncode, {"raw": r.stdout[:150]}


def dump(n, o):
    p = os.path.join(TMP, n); json.dump(o, open(p, "w", encoding="utf-8"), ensure_ascii=False); return p


def add(n, c, d=""):
    checks.append((n, c, d))


GOOD = {"case_id": "c1", "status": "issues", "run_version": "v1",
        "steps": [{"id": "W1", "depends_on": [], "state": "done"},
                  {"id": "W2", "depends_on": ["W1"], "state": "done"},
                  {"id": "W3", "depends_on": ["W2"], "state": "pending"}],
        "data_passing": [{"from": "W1", "to": "W2", "field_mapping": {"title": "name"},
                          "permission_scope": "green", "source_count": 10, "target_count": 10}],
        "idempotency_keys": ["k1", "k2"], "resume_point": "",
        "run_log": [{"step": "W1", "result": "ok"}],
        "gain": {}, "unchecked": [], "sources": [], "uncertainty": [], "change_log": []}

rc, d = run("flow_check", dump("g.json", GOOD))
add("flow正向:DAG无环且闭合", rc == 0 and d.get("ok"), str(d)[:150])

bad = json.loads(json.dumps(GOOD)); bad["steps"][1]["depends_on"] = ["W3"]
rc, d = run("flow_check", dump("b1.json", bad))
add("flow变异:成环被抓", rc == 1 and d.get("cycles"), str(d.get("cycles")))

bad = json.loads(json.dumps(GOOD)); bad["steps"][0]["depends_on"] = ["W9"]
rc, d = run("flow_check", dump("b2.json", bad))
add("flow变异:依赖不存在被抓", rc == 1 and any("不存在" in e for e in d.get("errors", [])), str(d.get("errors")))

bad = json.loads(json.dumps(GOOD)); bad["data_passing"][0].pop("field_mapping")
rc, d = run("flow_check", dump("b3.json", bad))
add("flow变异:缺字段映射被抓", rc == 1 and d.get("missing_field_mapping"), str(d.get("missing_field_mapping")))

bad = json.loads(json.dumps(GOOD)); bad["data_passing"][0]["permission_scope"] = "public"
rc, d = run("flow_check", dump("b4.json", bad))
add("flow变异:权限级别非法被抓", rc == 1 and d.get("invalid_permission_scope"), str(d.get("invalid_permission_scope")))

bad = json.loads(json.dumps(GOOD)); bad["data_passing"][0]["target_count"] = 7
rc, d = run("flow_check", dump("b5.json", bad))
add("flow变异:迁移条数不符被抓", rc == 1 and d.get("transfer_count_mismatch"), str(d.get("transfer_count_mismatch")))

bad = json.loads(json.dumps(GOOD)); bad["steps"][2]["state"] = "failed"
rc, d = run("flow_check", dump("b6.json", bad))
add("flow变异:失败无续跑点被抓", rc == 1 and any("resume_point" in e for e in d.get("errors", [])), str(d.get("errors")))

bad = json.loads(json.dumps(GOOD)); bad["idempotency_keys"] = ["k1", "k1"]
rc, d = run("flow_check", dump("b7.json", bad))
add("flow变异:幂等键重复被抓", rc == 1 and d.get("duplicate_idempotency_keys"), str(d.get("duplicate_idempotency_keys")))

rc, d = run("schema", dump("g.json", GOOD))
add("schema正向:合规零误杀", rc == 0 and d.get("ok"), str(d.get("errors")))

bad = json.loads(json.dumps(GOOD)); bad["run_log"] = []
rc, d = run("schema", dump("b8.json", bad))
add("schema变异:run_log为空->失败", rc == 1, str(d.get("errors"))[:120])

ok = sum(1 for _, c, _ in checks if c)
for n, c, dd in checks:
    print(("PASS" if c else "FAIL"), n, ("| " + dd if not c else ""))
print("total %d/%d" % (ok, len(checks)))
sys.exit(0 if ok == len(checks) else 1)
