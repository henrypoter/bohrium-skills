#!/usr/bin/env python3
"""文献阅读工具：证据逐字核验(回链原文) + 支持度分档统计 + 交付校验。纯标准库。

  support_check <answers.json> [--text source.txt]  每条答案的支持度 + 证据引文是否在原文
  schema <result.json>                              交付契约校验
"""
import json, re, sys, unicodedata

SUPPORT = {"full", "partial", "none", "unknown"}

def _norm(s):
    s = unicodedata.normalize("NFKC", str(s or ""))
    return re.sub(r"\s+", "", s)

def cmd_support_check(path, text_path=None):
    d = json.load(open(path, encoding="utf-8"))
    answers = d.get("answers", d if isinstance(d, list) else [])
    text = None
    if text_path:
        try:
            text = _norm(open(text_path, encoding="utf-8", errors="replace").read())
        except Exception as e:
            print(json.dumps({"ok": False, "error": "原文读取失败: %s" % e}, ensure_ascii=False)); return 1
    errs, not_found, no_support = [], [], []
    dist = {s: 0 for s in SUPPORT}
    for i, a in enumerate(answers):
        sup = a.get("support")
        if sup not in SUPPORT:
            no_support.append(a.get("id") or "answer[%d]" % i)
        else:
            dist[sup] += 1
        ev = a.get("evidence", [])
        if sup in ("full", "partial") and not ev:
            errs.append("answers[%d] 支持度为 %s 但无证据" % (i, sup))
        for j, e in enumerate(ev):
            if not e.get("location"):
                errs.append("answers[%d].evidence[%d] 缺 location" % (i, j))
            if text is not None:
                q = _norm(e.get("quote"))
                if not q:
                    errs.append("answers[%d].evidence[%d] quote 为空" % (i, j))
                elif q not in text:
                    not_found.append({"answer": a.get("id"), "quote": str(e.get("quote"))[:50]})
    out = {"ok": not errs and not not_found and not no_support, "n_answers": len(answers),
           "support_distribution": dist, "quote_not_in_source": not_found,
           "missing_support_level": no_support, "errors": errs}
    if text is None:
        out["note"] = "未提供 --text，跳过逐字核验"
    print(json.dumps(out, ensure_ascii=False))
    return 0 if out["ok"] else 1

def cmd_schema(path):
    d = json.load(open(path, encoding="utf-8"))
    errs = []
    for k in ("case_id", "status", "material_version", "answers", "gain",
              "unchecked", "sources", "uncertainty", "change_log"):
        if k not in d:
            errs.append("缺顶层字段 %s" % k)
    if d.get("status") not in {"pass", "issues", "partial", "failed"}:
        errs.append("status 非法")
    if not d.get("material_version"):
        errs.append("material_version 为空(材料版本须记录才能复核)")
    for i, a in enumerate(d.get("answers", [])):
        if not a.get("question") or not a.get("answer"):
            errs.append("answers[%d] 缺 question/answer" % i)
    if errs:
        print(json.dumps({"ok": False, "errors": errs}, ensure_ascii=False)); return 1
    print(json.dumps({"ok": True, "answers": len(d.get("answers", []))}, ensure_ascii=False))
    return 0

if __name__ == "__main__":
    a = sys.argv[1:]
    if not a:
        print(__doc__); sys.exit(2)
    if a[0] == "support_check":
        tp = a[a.index("--text") + 1] if "--text" in a else None
        sys.exit(cmd_support_check(a[1], tp))
    if a[0] == "schema":
        sys.exit(cmd_schema(a[1]))
    print(__doc__); sys.exit(2)
