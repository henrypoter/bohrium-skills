#!/usr/bin/env python3
"""文献综述工具：论断-引用回路核验 + 主题覆盖 + 计数闭合。纯标准库。

  cite_check <result.json>   每条论断是否挂引用、引用的 record 是否在清单、纳入文献是否都有理由
  theme_check <result.json>  主题覆盖矩阵：每主题是否至少有 1 条带引用的论断
  schema <result.json>       交付契约校验
"""
import json, sys

def _load(p):
    return json.load(open(p, encoding="utf-8"))

def cmd_cite_check(path):
    d = _load(path)
    recs = {r.get("id") for r in d.get("records", d.get("included", []))}
    errs, uncited, dangling = [], [], []
    claims = d.get("claims", [])
    if not claims:
        errs.append("claims 为空(综述必须输出论断)")
    for i, c in enumerate(claims):
        cits = c.get("citations", [])
        if not cits:
            uncited.append(c.get("id") or "claim[%d]" % i)
        for j, ct in enumerate(cits):
            rid = ct.get("record_id")
            if not ct.get("location"):
                errs.append("claims[%d].citations[%d] 缺 location(须定位到页/段)" % (i, j))
            if recs and rid and rid not in recs:
                dangling.append({"claim": c.get("id"), "record_id": rid})
    for i, r in enumerate(d.get("included", [])):
        if not r.get("screening_reason"):
            errs.append("included[%d] 缺 screening_reason" % i)
    if not d.get("screening_criteria"):
        errs.append("screening_criteria 为空(筛选标准须先于写作写明)")
    print(json.dumps({"ok": not errs and not dangling and not uncited, "n_claims": len(claims),
                      "uncited_claims": uncited, "dangling_citations": dangling, "errors": errs},
                     ensure_ascii=False))
    return 0 if not errs and not dangling and not uncited else 1

def cmd_theme_check(path):
    d = _load(path)
    claims = d.get("claims", [])
    themes = d.get("themes", [])
    by_theme = {}
    for c in claims:
        t = c.get("theme") or "(未归类)"
        by_theme.setdefault(t, []).append(bool(c.get("citations")))
    uncovered = [t for t in (x.get("name") for x in themes) if t not in by_theme]
    weak = [t for t, v in by_theme.items() if not any(v)]
    print(json.dumps({"ok": not uncovered and not weak,
                      "themes_declared": len(themes), "themes_with_claims": len(by_theme),
                      "themes_without_claims": uncovered,
                      "themes_without_cited_claim": weak,
                      "unclassified_claims": len(by_theme.get("(未归类)", []))}, ensure_ascii=False))
    return 0 if not uncovered and not weak else 1

def cmd_schema(path):
    d = _load(path)
    errs = []
    for k in ("case_id", "status", "screening_criteria", "included", "claims", "themes",
              "counts", "gain", "unchecked", "sources", "uncertainty", "change_log"):
        if k not in d:
            errs.append("缺顶层字段 %s" % k)
    if d.get("status") not in {"pass", "issues", "partial", "failed"}:
        errs.append("status 非法")
    c = d.get("counts", {})
    if c.get("included", 0) + c.get("excluded", 0) > c.get("records_raw", 10**9):
        errs.append("counts 矛盾: 纳入+排除 > 原始")
    if errs:
        print(json.dumps({"ok": False, "errors": errs}, ensure_ascii=False)); return 1
    print(json.dumps({"ok": True, "claims": len(d.get("claims", [])),
                      "included": len(d.get("included", []))}, ensure_ascii=False))
    return 0

if __name__ == "__main__":
    a = sys.argv[1:]
    if not a:
        print(__doc__); sys.exit(2)
    if a[0] == "cite_check":
        sys.exit(cmd_cite_check(a[1]))
    if a[0] == "theme_check":
        sys.exit(cmd_theme_check(a[1]))
    if a[0] == "schema":
        sys.exit(cmd_schema(a[1]))
    print(__doc__); sys.exit(2)
