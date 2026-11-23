#!/usr/bin/env python3
"""科研自动化工具：步骤 DAG 与状态机校验 + 断点续跑可达集计算 + 交付校验。纯标准库。

  trace  <result.json>  依赖存在性/无环、状态合法、resume_point 可续、幂等键唯一、权限范围已声明
  resume <result.json>  由已完成状态计算下一批可执行步骤（断点续跑的实际动作）
  schema <result.json>  交付契约校验
"""
import json, sys

STATES = {"pending", "done", "failed", "skipped"}

def _load(p):
    return json.load(open(p, encoding="utf-8"))

def _graph(steps):
    return {s.get("id"): (s.get("depends_on") or []) for s in steps}

def _cycle(g):
    color = {}

    def dfs(n, stack):
        color[n] = 1
        for m in g.get(n, []):
            if m not in g:
                continue
            if color.get(m) == 1:
                return stack + [n, m]
            if color.get(m, 0) == 0:
                r = dfs(m, stack + [n])
                if r:
                    return r
        color[n] = 2
        return None
    for n in g:
        if color.get(n, 0) == 0:
            r = dfs(n, [])
            if r:
                return r
    return None

def cmd_trace(path):
    d = _load(path)
    steps = d.get("workflow") or []
    g = _graph(steps)
    errs, warn = [], []
    for s in steps:
        if s.get("state") not in STATES:
            errs.append("步骤 %s 状态非法: %s" % (s.get("id"), s.get("state")))
        for dep in (s.get("depends_on") or []):
            if dep not in g:
                errs.append("步骤 %s 依赖不存在的 %s" % (s.get("id"), dep))
        if not s.get("input") or not s.get("output"):
            errs.append("步骤 %s 缺 input/output(无法复跑)" % s.get("id"))
    cyc = _cycle(g)
    if cyc:
        errs.append("依赖成环: %s" % " -> ".join(cyc))
    st = d.get("state") or {}
    failed = st.get("failed_step")
    rp = st.get("resume_point")
    if failed and not rp:
        errs.append("有 failed_step 但缺 resume_point(断点续跑无从开始)")
    if rp and rp not in g:
        errs.append("resume_point %s 不在步骤列表中" % rp)
    for i, f in enumerate(d.get("failures") or []):
        for k in ("step", "error", "recovery"):
            if not f.get(k):
                errs.append("failures[%d] 缺 %s" % (i, k))
    keys = [f.get("idempotency_key") for f in (d.get("failures") or []) if f.get("idempotency_key")]
    if len(keys) != len(set(keys)):
        errs.append("idempotency_key 有重复(重跑可能二次推送)")
    for i, dp in enumerate(d.get("data_passing") or []):
        if not dp.get("permission_scope"):
            errs.append("data_passing[%d] 未声明 permission_scope(跨站数据边界不明)" % i)
        if not dp.get("field_mapping"):
            warn.append("data_passing[%d] 未给 field_mapping" % i)
    print(json.dumps({"ok": not errs, "n_steps": len(steps), "errors": errs, "warnings": warn},
                     ensure_ascii=False))
    return 0 if not errs else 1

def cmd_resume(path):
    d = _load(path)
    steps = d.get("workflow") or []
    done = {s.get("id") for s in steps if s.get("state") == "done"}
    blocked = {s.get("id") for s in steps if s.get("state") == "skipped"}
    runnable, waiting = [], []
    for s in steps:
        sid = s.get("id")
        if s.get("state") == "done":
            continue
        deps = s.get("depends_on") or []
        unmet = [x for x in deps if x not in done and x not in blocked]
        (waiting if unmet else runnable).append({"id": sid, "unmet_deps": unmet})
    print(json.dumps({"ok": True, "runnable_now": [r["id"] for r in runnable],
                      "waiting": waiting, "resume_point": (d.get("state") or {}).get("resume_point")},
                     ensure_ascii=False))
    return 0

def cmd_schema(path):
    d = _load(path)
    if not isinstance(d, dict):
        print(json.dumps({"ok": False, "errors": ["顶层必须是对象"]}, ensure_ascii=False)); return 1
    errs = []
    for k in ("case_id", "status", "workflow", "state", "data_passing", "failures",
              "run_log", "gain", "unchecked", "sources", "uncertainty", "change_log"):
        if k not in d:
            errs.append("缺顶层字段 %s" % k)
    if d.get("status") not in {"pass", "issues", "partial", "failed"}:
        errs.append("status 非法")
    if not d.get("run_log"):
        errs.append("run_log 为空(无逐步骤执行记录)")
    if errs:
        print(json.dumps({"ok": False, "errors": errs}, ensure_ascii=False)); return 1
    print(json.dumps({"ok": True, "steps": len(d.get("workflow", []))}, ensure_ascii=False))
    return 0

if __name__ == "__main__":
    a = sys.argv[1:]
    if not a:
        print(__doc__); sys.exit(2)
    if a[0] in ("trace", "resume", "schema"):
        sys.exit({"trace": cmd_trace, "resume": cmd_resume, "schema": cmd_schema}[a[0]](a[1]))
    print(__doc__); sys.exit(2)
