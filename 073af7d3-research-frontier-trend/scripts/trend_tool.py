#!/usr/bin/env python3
"""研究前沿与趋势分析工具：趋势论断的时间证据回路 + 主题演化 + 代表作覆盖 + 空白证据。纯标准库。

  trend_check <result.json>  每条趋势论断有年份/区间+引用+定位；时间演化有阶段；空白有排除证据
  schema <result.json>       交付契约校验
"""
import json, sys


def _load(p):
    return json.load(open(p, encoding="utf-8"))


def cmd_trend_check(path):
    d = _load(path)
    recs = {r.get("id") for r in d.get("records", [])}
    errs, no_time, dangling, no_loc = [], [], [], []
    trends = d.get("trends", [])
    if not trends:
        errs.append("trends 为空(趋势分析须有趋势论断)")
    for i, t in enumerate(trends):
        if not t.get("year_range") and not t.get("period"):
            no_time.append(t.get("id") or "trend[%d]" % i)
        cits = t.get("citations", [])
        if not cits:
            errs.append("trend[%d] 无引用(趋势判断须挂文献)" % i)
        for j, c in enumerate(cits):
            if not c.get("location"):
                no_loc.append({"trend": t.get("id"), "citation": j})
            rid = c.get("record_id")
            if recs and rid and rid not in recs:
                dangling.append({"trend": t.get("id"), "record_id": rid})
    # 主题演化阶段
    evo = d.get("evolution", [])
    for i, e in enumerate(evo):
        if not e.get("stage") or not e.get("period"):
            errs.append("evolution[%d] 缺 stage/period(演化要有阶段与时期)" % i)
    # 空白证据
    for i, g in enumerate(d.get("gaps", [])):
        if not g.get("evidence"):
            errs.append("gaps[%d] 缺 evidence(空白须有排除证据而非检索遗漏)" % i)
    out = {"ok": not errs and not no_time and not dangling and not no_loc,
           "n_trends": len(trends), "trends_without_time": no_time,
           "dangling_citations": dangling, "citations_without_location": no_loc,
           "n_evolution_stages": len(evo), "n_gaps": len(d.get("gaps", [])),
           "errors": errs}
    print(json.dumps(out, ensure_ascii=False))
    return 0 if out["ok"] else 1


def cmd_schema(path):
    d = _load(path)
    errs = []
    for k in ("case_id", "status", "analysis_version", "trends", "evolution", "gaps",
              "representative_works", "gain", "unchecked", "sources", "uncertainty", "change_log"):
        if k not in d:
            errs.append("缺顶层字段 %s" % k)
    if d.get("status") not in {"pass", "issues", "partial", "failed"}:
        errs.append("status 非法")
    for i, w in enumerate(d.get("representative_works", [])):
        if not w.get("period") or not w.get("record_id"):
            errs.append("representative_works[%d] 缺 period/record_id" % i)
    if errs:
        print(json.dumps({"ok": False, "errors": errs}, ensure_ascii=False)); return 1
    print(json.dumps({"ok": True, "trends": len(d.get("trends", [])),
                      "works": len(d.get("representative_works", []))}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    a = sys.argv[1:]
    if not a:
        print(__doc__); sys.exit(2)
    if a[0] == "trend_check":
        sys.exit(cmd_trend_check(a[1]))
    if a[0] == "schema":
        sys.exit(cmd_schema(a[1]))
    print(__doc__); sys.exit(2)
