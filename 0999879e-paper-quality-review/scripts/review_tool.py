#!/usr/bin/env python3
"""论文质量审查工具：引文逐字核验(误报抑制) + 分面覆盖统计 + 交付校验。纯标准库。

  verify  <issues.json> [--text manuscript.txt]   每条问题的 quote 是否真在原文中逐字存在；重复问题检测
  summary <issues.json>                          六类检查项覆盖矩阵 + 严重度分布
  schema  <result.json>                          交付契约校验
"""
import json, re, sys, unicodedata

CATS = ["fact", "citation", "design", "statistics", "argument", "compliance"]
SEV = ["critical", "major", "minor"]


def _norm(s):
    s = unicodedata.normalize("NFKC", str(s or ""))
    s = re.sub(r"\s+", "", s)
    return s


def _load(p):
    d = json.load(open(p, encoding="utf-8"))
    return d.get("issues", d) if isinstance(d, dict) else d


def cmd_verify(path, text_path=None):
    issues = _load(path)
    text = None
    if text_path:
        try:
            text = _norm(open(text_path, encoding="utf-8", errors="replace").read())
        except Exception as e:
            print(json.dumps({"ok": False, "error": "原文读取失败: %s" % e}, ensure_ascii=False))
            return 1
    not_found, dup, errs = [], [], []
    seen = {}
    for i, it in enumerate(issues):
        q = _norm(it.get("quote"))
        if text is not None:
            if not q:
                errs.append("issues[%d] quote 为空，无法核验" % i)
            elif q not in text:
                not_found.append({"id": it.get("id"), "quote": it.get("quote", "")[:60]})
        key = (_norm(it.get("location")), q)
        if key in seen:
            dup.append({"a": seen[key], "b": it.get("id"), "reason": "位置与引文完全相同"})
        else:
            seen[key] = it.get("id")
    out = {"ok": not not_found and not errs, "total": len(issues),
           "quote_not_in_source": not_found, "duplicates": dup, "errors": errs}
    if text is None:
        out["note"] = "未提供 --text，跳过逐字核验（仅做重复检测）"
        out["ok"] = not errs
    print(json.dumps(out, ensure_ascii=False))
    return 0 if out["ok"] else 1


def cmd_summary(path):
    issues = _load(path)
    cat = {c: 0 for c in CATS}
    sev = {s: 0 for s in SEV}
    other = []
    for it in issues:
        c = it.get("category")
        if c in cat:
            cat[c] += 1
        elif c:
            other.append(c)
        s = it.get("severity")
        if s in sev:
            sev[s] += 1
    missing = [c for c in CATS if cat[c] == 0]
    print(json.dumps({"ok": True, "total": len(issues), "by_category": cat, "by_severity": sev,
                      "unchecked_categories": missing, "unknown_categories": sorted(set(other)),
                      "category_coverage": round(1 - len(missing) / float(len(CATS)), 3)},
                     ensure_ascii=False))
    return 0


def cmd_schema(path):
    d = json.load(open(path, encoding="utf-8")) if True else None
    if not isinstance(d, dict):
        print(json.dumps({"ok": False, "errors": ["顶层必须是对象"]}, ensure_ascii=False)); return 1
    errs = []
    for k in ("case_id", "status", "manuscript_version", "issues", "checked_scope",
              "gain", "unchecked", "sources", "uncertainty", "change_log"):
        if k not in d:
            errs.append("缺顶层字段 %s" % k)
    if d.get("status") not in {"pass", "issues", "partial", "failed"}:
        errs.append("status 非法")
    if not d.get("manuscript_version"):
        errs.append("manuscript_version 为空(必须记录稿件版本才能复核)")
    for i, it in enumerate(d.get("issues", [])):
        for k in ("id", "category", "severity", "location", "quote", "claim", "fix"):
            if k not in it:
                errs.append("issues[%d] 缺 %s" % (i, k))
        if it.get("category") not in CATS:
            errs.append("issues[%d] category 非法: %s" % (i, it.get("category")))
        if it.get("severity") not in SEV:
            errs.append("issues[%d] severity 非法: %s" % (i, it.get("severity")))
    if not d.get("checked_scope"):
        errs.append("checked_scope 为空(须写明查了哪些检查项、哪些未查)")
    if errs:
        print(json.dumps({"ok": False, "errors": errs}, ensure_ascii=False)); return 1
    print(json.dumps({"ok": True, "issues": len(d.get("issues", []))}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    a = sys.argv[1:]
    if not a:
        print(__doc__); sys.exit(2)
    if a[0] == "verify":
        tp = a[a.index("--text") + 1] if "--text" in a else None
        sys.exit(cmd_verify(a[1], tp))
    if a[0] == "summary":
        sys.exit(cmd_summary(a[1]))
    if a[0] == "schema":
        sys.exit(cmd_schema(a[1]))
    print(__doc__); sys.exit(2)
