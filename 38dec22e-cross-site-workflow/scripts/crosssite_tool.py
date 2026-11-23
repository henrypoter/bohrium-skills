#!/usr/bin/env python3
"""跨网站工作流自动化工具：DAG/状态/字段映射/权限分级/迁移完整性/幂等。纯标准库。

  flow_check <result.json>  依赖无环、状态合法、字段映射显式、权限分级、迁移条数闭合、幂等键唯一、失败有续跑点
  schema <result.json>      交付契约校验
"""
import json, sys

PERM = {"green", "yellow", "red"}
STATE = {"pending", "done", "failed", "blocked", "skipped"}


def _load(p):
    return json.load(open(p, encoding="utf-8"))


def cmd_flow_check(path):
    d = _load(path)
    steps = d.get("steps", d.get("workflow", []))
    ids = {s.get("id") for s in steps}
    errs, cycles = [], []
    # 依赖存在 + 无环（DFS）
    if not steps:
        errs.append("steps 为空")
    for s in steps:
        for dep in s.get("depends_on", []):
            if dep not in ids:
                errs.append("步骤 %s 依赖不存在的 %s" % (s.get("id"), dep))
        if s.get("state") not in STATE:
            errs.append("步骤 %s 状态非法: %s" % (s.get("id"), s.get("state")))
    # 环检测
    adj = {s.get("id"): s.get("depends_on", []) for s in steps}
    color = {}
    def dfs(u, path):
        color[u] = 1
        for v in adj.get(u, []):
            if color.get(v) == 1:
                cycles.append(path + [v]); continue
            if color.get(v) == 0:
                dfs(v, path + [v])
        color[u] = 2
    for u in adj:
        color.setdefault(u, 0)
    for u in adj:
        if color[u] == 0:
            dfs(u, [u])
    # 失败有续跑点
    failed = [s.get("id") for s in steps if s.get("state") == "failed"]
    if failed and not d.get("resume_point"):
        errs.append("有 failed 步骤但缺 resume_point")
    # 字段映射 + 权限分级 + 迁移完整性
    no_map, no_perm, mismatch = [], [], []
    for i, p in enumerate(d.get("data_passing", [])):
        if not p.get("field_mapping"):
            no_map.append(p.get("from") + "->" + p.get("to"))
        if p.get("permission_scope") not in PERM:
            no_perm.append(p.get("from") + "->" + p.get("to"))
        s_cnt = p.get("source_count"); t_cnt = p.get("target_count")
        if s_cnt is not None and t_cnt is not None and s_cnt != t_cnt:
            mismatch.append({"pass": p.get("from") + "->" + p.get("to"),
                             "source": s_cnt, "target": t_cnt})
    # 幂等键唯一
    keys = [x for x in (d.get("idempotency_keys") or []) if x]
    dup_keys = [k for k in set(keys) if keys.count(k) > 1]
    out = {"ok": not errs and not cycles and not no_map and not no_perm and not mismatch and not dup_keys,
           "n_steps": len(steps), "cycles": cycles, "missing_field_mapping": no_map,
           "invalid_permission_scope": no_perm, "transfer_count_mismatch": mismatch,
           "duplicate_idempotency_keys": dup_keys, "errors": errs}
    print(json.dumps(out, ensure_ascii=False))
    return 0 if out["ok"] else 1


def cmd_schema(path):
    d = _load(path)
    errs = []
    for k in ("case_id", "status", "run_version", "steps", "data_passing", "run_log",
              "gain", "unchecked", "sources", "uncertainty", "change_log"):
        if k not in d:
            errs.append("缺顶层字段 %s" % k)
    if d.get("status") not in {"pass", "issues", "partial", "failed"}:
        errs.append("status 非法")
    if not d.get("run_log"):
        errs.append("run_log 为空(状态须随手记录)")
    if errs:
        print(json.dumps({"ok": False, "errors": errs}, ensure_ascii=False)); return 1
    print(json.dumps({"ok": True, "steps": len(d.get("steps", [])),
                      "passing": len(d.get("data_passing", []))}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    a = sys.argv[1:]
    if not a:
        print(__doc__); sys.exit(2)
    if a[0] == "flow_check":
        sys.exit(cmd_flow_check(a[1]))
    if a[0] == "schema":
        sys.exit(cmd_schema(a[1]))
    print(__doc__); sys.exit(2)
