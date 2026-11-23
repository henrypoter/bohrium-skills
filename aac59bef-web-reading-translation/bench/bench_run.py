#!/usr/bin/env python3
"""auto_tool 自测：依赖 DAG/无环、状态机、断点续跑可达集、权限与幂等、交付校验。"""
import json, os, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL = os.path.join(HERE, "..", "scripts", "auto_tool.py")
TMP = tempfile.mkdtemp()
checks = []


def run(*a):
    r = subprocess.run([sys.executable, TOOL, *a], capture_output=True, text=True)
    try:
        return r.returncode, json.loads(r.stdout)
    except Exception:
        return r.returncode, {"raw": r.stdout[:200]}


def dump(name, obj):
    p = os.path.join(TMP, name)
    json.dump(obj, open(p, "w", encoding="utf-8"), ensure_ascii=False)
    return p


def add(n, c, d=""):
    checks.append((n, c, d))


BASE = {
    "case_id": "c1", "status": "issues",
    "workflow": [
        {"id": "W1", "step": "检索并下载", "depends_on": [], "input": "query", "output": "files[]", "state": "done"},
        {"id": "W2", "step": "字段抽取", "depends_on": ["W1"], "input": "files[]", "output": "rows[]", "state": "done"},
        {"id": "W3", "step": "写入目标系统", "depends_on": ["W2"], "input": "rows[]", "output": "record_ids[]", "state": "failed"},
    ],
    "state": {"completed_steps": ["W1", "W2"], "failed_step": "W3", "resume_point": "W3"},
    "data_passing": [{"from": "W2", "to": "W3", "field_mapping": {"title": "name"}, "permission_scope": "green"}],
    "failures": [{"step": "W3", "error": "接口 502", "recovery": "指数退避重试 3 次", "retry": 3,
                  "idempotency_key": "W3-2026-11-20-001"}],
    "run_log": [{"step": "W1", "start": "2026-11-20T10:00Z", "end": "2026-11-20T10:03Z", "result": "ok"}],
    "gain": {"baseline_success_rate": 0.4, "skill_success_rate": 0.85, "manual_steps_saved": 12},
    "unchecked": [], "sources": ["site logs"], "uncertainty": [], "change_log": [],
}

# 1) trace 正向
rc, d = run("trace", dump("a1.json", BASE))
add("trace:合规DAG零误杀", rc == 0 and d.get("ok"), str(d.get("errors"))[:160])

# 2) 依赖不存在
bad = json.loads(json.dumps(BASE)); bad["workflow"][2]["depends_on"] = ["W9"]
rc, d = run("trace", dump("a2.json", bad))
add("trace:依赖不存在被抓", rc == 1 and any("不存在" in e for e in d.get("errors", [])), str(d.get("errors"))[:140])

# 3) 依赖成环
bad = json.loads(json.dumps(BASE)); bad["workflow"][0]["depends_on"] = ["W3"]
rc, d = run("trace", dump("a3.json", bad))
add("trace:依赖成环被抓", rc == 1 and any("成环" in e for e in d.get("errors", [])), str(d.get("errors"))[:140])

# 4) 有失败步骤却无续跑点
bad = json.loads(json.dumps(BASE)); bad["state"]["resume_point"] = ""
rc, d = run("trace", dump("a4.json", bad))
add("trace:失败缺续跑点被抓", rc == 1 and any("resume_point" in e for e in d.get("errors", [])), str(d.get("errors"))[:140])

# 5) 幂等键重复
bad = json.loads(json.dumps(BASE))
bad["failures"].append({"step": "W3", "error": "超时", "recovery": "重试", "idempotency_key": "W3-2026-11-20-001"})
rc, d = run("trace", dump("a5.json", bad))
add("trace:幂等键重复被抓", rc == 1 and any("idempotency_key" in e for e in d.get("errors", [])), str(d.get("errors"))[:140])

# 6) 跨站数据未声明权限
bad = json.loads(json.dumps(BASE)); bad["data_passing"][0].pop("permission_scope")
rc, d = run("trace", dump("a6.json", bad))
add("trace:未声明权限范围被抓", rc == 1 and any("permission_scope" in e for e in d.get("errors", [])), str(d.get("errors"))[:140])

# 7) resume：只剩 W3 可跑
rc, d = run("resume", dump("a1.json", BASE))
add("resume:可续跑集正确", rc == 0 and d.get("runnable_now") == ["W3"], str(d)[:140])

# 8) resume：上游未完成时下游等待
bad = json.loads(json.dumps(BASE)); bad["workflow"][1]["state"] = "failed"
rc, d = run("resume", dump("a7.json", bad))
add("resume:下游等待上游", rc == 0 and d.get("runnable_now") == ["W2"]
    and any(w["id"] == "W3" for w in d.get("waiting", [])), str(d)[:160])

# 9) schema 正向
rc, d = run("schema", dump("a1b.json", BASE))
add("schema正向:合规零误杀", rc == 0 and d.get("ok"), str(d.get("errors"))[:150])

# 10) schema 变异：缺运行日志
bad = json.loads(json.dumps(BASE)); bad["run_log"] = []
rc, d = run("schema", dump("a8.json", bad))
add("schema变异:缺run_log->失败", rc == 1 and any("run_log" in e for e in d.get("errors", [])), str(d.get("errors"))[:140])

ok = sum(1 for _, c, _ in checks if c)
for n, c, dd in checks:
    print(("PASS" if c else "FAIL"), n, ("| " + dd if not c else ""))
print("total %d/%d" % (ok, len(checks)))
sys.exit(0 if ok == len(checks) else 1)
