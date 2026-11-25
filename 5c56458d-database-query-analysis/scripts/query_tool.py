#!/usr/bin/env python3
"""科研数据库查询与分析工具：查询在授权快照上执行 + 金标准/独立复算 + 字段字典与关联路径可复核。纯标准库。

  query_check <result.json>  每条查询有快照版本+可执行SQL+金标准比对；字段有字典；关联有路径与膨胀控制
  schema       <result.json>  交付契约校验
"""
import json, sys


def _load(p):
    return json.load(open(p, encoding="utf-8"))


def cmd_query_check(path):
    d = _load(path)
    errs, warn = [], []
    queries = d.get("queries", [])
    if not queries:
        errs.append("queries 为空(数据库查询任务须有可执行查询)")
    for i, q in enumerate(queries):
        for k in ("snapshot", "sql", "connection", "result"):
            if not q.get(k):
                errs.append("queries[%d] 缺 %s" % (i, k))
        if not (q.get("golden") or q.get("recheck")):
            errs.append("queries[%d] 缺 golden/recheck(结果须与金标准或独立复算对上)" % i)
        conn = q.get("connection") or {}
        if not conn.get("permission"):
            warn.append("queries[%d] 未声明权限范围(读写/只读)" % i)
    for i, f in enumerate(d.get("field_dict", [])):
        if not f.get("field") or not f.get("meaning"):
            errs.append("field_dict[%d] 缺 field/meaning(字段含义须可复核)" % i)
    for i, j in enumerate(d.get("joins", [])):
        if not j.get("left") or not j.get("right") or not j.get("on"):
            errs.append("joins[%d] 缺 left/right/on(关联路径)" % i)
        if "one_to_many" not in j:
            warn.append("joins[%d] 未声明一对多膨胀控制" % i)
    out = {"ok": not errs, "n_queries": len(queries), "n_fields": len(d.get("field_dict", [])),
           "n_joins": len(d.get("joins", [])), "errors": errs, "warnings": warn}
    print(json.dumps(out, ensure_ascii=False))
    return 0 if not errs else 1


def cmd_schema(path):
    d = _load(path)
    if not isinstance(d, dict):
        print(json.dumps({"ok": False, "errors": ["顶层必须是对象"]}, ensure_ascii=False)); return 1
    errs = []
    for k in ("case_id", "status", "query_version", "queries", "field_dict", "joins",
              "results", "gain", "unchecked", "sources", "uncertainty", "change_log"):
        if k not in d:
            errs.append("缺顶层字段 %s" % k)
    if d.get("status") not in {"pass", "issues", "partial", "failed"}:
        errs.append("status 非法")
    if not d.get("query_version"):
        errs.append("query_version 为空(查询须可版本化复算)")
    if errs:
        print(json.dumps({"ok": False, "errors": errs}, ensure_ascii=False)); return 1
    print(json.dumps({"ok": True, "queries": len(d.get("queries", []))}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    a = sys.argv[1:]
    if not a:
        print(__doc__); sys.exit(2)
    if a[0] == "query_check":
        sys.exit(cmd_query_check(a[1]))
    if a[0] == "schema":
        sys.exit(cmd_schema(a[1]))
    print(__doc__); sys.exit(2)
