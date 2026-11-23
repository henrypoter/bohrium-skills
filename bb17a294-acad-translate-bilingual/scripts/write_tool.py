#!/usr/bin/env python3
"""学术写作工具：论断-引用回路核验 + 结构完整性 + 数值论断引用覆盖。纯标准库。

  claim_check <result.json>  每条论断挂引用、引用 ref 在参考文献表、数值论断有引用
  structure   <result.json>  章节完整性（对照模板必需章节）
  schema      <result.json>  交付契约校验
"""
import json, re, sys

NUM = re.compile(r"(\d+(\.\d+)?\s*(%|例|个|篇|年|mg|ml|μM|°C|倍|天|h|min))|(n\s*=\s*\d+)|(p\s*[<=>]\s*0?\.\d+)|(\d+\s*/\s*\d+)", re.I)

def _load(p):
    return json.load(open(p, encoding="utf-8"))

def cmd_claim_check(path):
    d = _load(path)
    refs = {r.get("ref_id") for r in d.get("references", [])}
    errs, uncited, dangling, numeric_no_cite = [], [], [], []
    claims = []
    for sec in d.get("sections", []):
        for c in sec.get("claims", []):
            claims.append((sec.get("id"), c))
    if not claims:
        errs.append("sections[].claims 为空(须有结构化论断)")
    for sec, c in claims:
        cits = c.get("citations", [])
        if not cits:
            uncited.append(c.get("id") or (sec or "?"))
        for j, ct in enumerate(cits):
            if not ct.get("location"):
                errs.append("claim %s 引用[%d] 缺 location" % (c.get("id"), j))
            rid = ct.get("ref_id")
            if refs and rid and rid not in refs:
                dangling.append({"claim": c.get("id"), "ref_id": rid})
        txt = str(c.get("text", ""))
        if NUM.search(txt) and not cits and not c.get("is_common_knowledge"):
            numeric_no_cite.append({"claim": c.get("id"), "text": txt[:50]})
    for i, r in enumerate(d.get("references", [])):
        if not r.get("ref_id") or not (r.get("title") or r.get("doi")):
            errs.append("references[%d] 缺 ref_id 或 title/doi" % i)
    print(json.dumps({"ok": not errs and not dangling and not numeric_no_cite,
                      "n_claims": len(claims), "n_refs": len(refs),
                      "uncited_claims": uncited, "dangling_citations": dangling,
                      "numeric_claims_without_citation": numeric_no_cite, "errors": errs},
                     ensure_ascii=False))
    return 0 if not errs and not dangling and not numeric_no_cite else 1

def cmd_structure(path):
    d = _load(path)
    required = d.get("required_sections") or ["title", "abstract", "introduction", "methods",
                                              "results", "discussion", "references"]
    have = {s.get("id") for s in d.get("sections", [])}
    missing = [s for s in required if s not in have]
    empty = [s.get("id") for s in d.get("sections", []) if not str(s.get("content", "")).strip()]
    wc = sum(len(str(s.get("content", ""))) for s in d.get("sections", []))
    print(json.dumps({"ok": not missing and not empty, "required": required,
                      "present": sorted(have), "missing_sections": missing,
                      "empty_sections": empty, "word_count": wc}, ensure_ascii=False))
    return 0 if not missing and not empty else 1

def cmd_schema(path):
    d = _load(path)
    errs = []
    for k in ("case_id", "status", "draft_version", "sections", "references",
              "gain", "unchecked", "sources", "uncertainty", "change_log"):
        if k not in d:
            errs.append("缺顶层字段 %s" % k)
    if d.get("status") not in {"pass", "issues", "partial", "failed"}:
        errs.append("status 非法")
    if not d.get("draft_version"):
        errs.append("draft_version 为空(稿件须可版本化)")
    if errs:
        print(json.dumps({"ok": False, "errors": errs}, ensure_ascii=False)); return 1
    print(json.dumps({"ok": True, "sections": len(d.get("sections", [])),
                      "references": len(d.get("references", []))}, ensure_ascii=False))
    return 0

if __name__ == "__main__":
    a = sys.argv[1:]
    if not a:
        print(__doc__); sys.exit(2)
    if a[0] == "claim_check":
        sys.exit(cmd_claim_check(a[1]))
    if a[0] == "structure":
        sys.exit(cmd_structure(a[1]))
    if a[0] == "schema":
        sys.exit(cmd_schema(a[1]))
    print(__doc__); sys.exit(2)
