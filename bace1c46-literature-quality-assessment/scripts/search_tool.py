#!/usr/bin/env python3
"""科研检索工具 v2：去重(精确+近似) / 计数闭合审计 / 双人一致性 / 结果校验。纯标准库。

命令:
  dedup     <records.json>        精确键去重 + 近似标题候选合并组（预印本/正式版）
  audit     <result.json>         PRISMA 式计数闭合审计，不闭合返回 1
  agreement <pairs.json>          双人独立标注一致率与 Cohen's kappa，列分歧
  schema    <result.json>         交付契约校验（协议/理由码/依据片段/计数）
"""
import json
import re
import sys
import unicodedata

STATUSES = {"pass", "issues", "partial", "failed"}
DECISIONS = {"include", "exclude", "maybe"}


def _norm_title(s):
    s = unicodedata.normalize("NFKC", str(s or "")).lower()
    s = re.sub(r"[^\w\u4e00-\u9fff]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _norm_author(s):
    s = str(s or "").strip()
    if not s:
        return ""
    first = re.split(r"[;,]", s)[0].strip()
    return first.split()[-1].lower() if first else ""


def _exact_key(r):
    doi = (r.get("doi") or "").strip().lower()
    if doi:
        return ("doi", doi)
    arx = (r.get("arxiv") or "").strip().lower()
    if arx:
        return ("arxiv", arx)
    t, a, y = _norm_title(r.get("title")), _norm_author(r.get("authors")), str(r.get("year") or "").strip()
    if t and a and y:
        return ("title", "%s|%s|%s" % (t, a, y))
    return ("title", t) if t else ("none", str(r.get("id", "")))


def _tokens(s):
    return {w for w in _norm_title(s).split() if len(w) > 2}


def _jaccard(a, b):
    if not a or not b:
        return 0.0
    return len(a & b) / float(len(a | b))


def cmd_dedup(path):
    try:
        recs = json.load(open(path, encoding="utf-8"))
    except Exception as e:
        print(json.dumps({"ok": False, "error": "json 解析失败: %s" % e}, ensure_ascii=False))
        return 1
    if isinstance(recs, dict):
        recs = recs.get("records", [])
    groups = {}
    for i, r in enumerate(recs):
        groups.setdefault(_exact_key(r), []).append(r.get("id") or r.get("title", "")[:40])
    exact_dup = [{"key": k[1], "members": ms} for k, ms in groups.items() if len(ms) > 1]

    # 近似候选：不同精确键、同年、标题 Jaccard>=0.55 -> 预印本/正式版候选，交由人工裁决，不自动合并
    near = []
    keys = list(groups)
    for i in range(len(keys)):
        for j in range(i + 1, len(keys)):
            ra = next(r for r in recs if (r.get("id") or r.get("title", "")[:40]) == groups[keys[i]][0])
            rb = next(r for r in recs if (r.get("id") or r.get("title", "")[:40]) == groups[keys[j]][0])
            if str(ra.get("year")) != str(rb.get("year")):
                continue
            sim = _jaccard(_tokens(ra.get("title")), _tokens(rb.get("title")))
            if sim >= 0.55:
                near.append({"a": groups[keys[i]][0], "b": groups[keys[j]][0],
                             "title_jaccard": round(sim, 3),
                             "reason": "标题近似且同年：疑预印本/正式版，需人工确认",
                             "doi_a": ra.get("doi") or "", "doi_b": rb.get("doi") or ""})
    print(json.dumps({"ok": True, "input": len(recs), "unique_exact": len(groups),
                      "exact_duplicate_groups": len(exact_dup), "exact_detail": exact_dup,
                      "near_duplicate_candidates": near}, ensure_ascii=False))
    return 0


def cmd_audit(path):
    try:
        d = json.load(open(path, encoding="utf-8"))
    except Exception as e:
        print(json.dumps({"ok": False, "errors": ["json 解析失败: %s" % e]}, ensure_ascii=False))
        return 1
    c = d.get("counts") or {}
    scr = d.get("screening") or []
    dec = {k: sum(1 for s in scr if s.get("decision") == k) for k in DECISIONS}
    raw = int(c.get("records_raw") or 0)
    ded = int(c.get("records_dedup") or 0)
    rows, errs = [], []
    rows.append(("raw→dedup", raw, ded, "去重不应增加记录"))
    if ded > raw:
        errs.append("去重后(%d) > 原始(%d)" % (ded, raw))
    rows.append(("dedup→screened", ded, sum(dec.values()), "每条去重后记录都应有判定"))
    if sum(dec.values()) != ded:
        errs.append("筛选合计(%d) != 去重后(%d)" % (sum(dec.values()), ded))
    if (c.get("included") is not None and int(c.get("included")) != dec["include"]):
        errs.append("counts.included(%s) != 实际 include(%d)" % (c.get("included"), dec["include"]))
    # 每条 include/exclude 必须有理由码与依据片段
    for i, s in enumerate(scr):
        if s.get("decision") in ("include", "exclude") and not (s.get("reason_code") and s.get("evidence_snippet")):
            errs.append("screening[%d] 缺理由码或依据片段" % i)
    # 理由码必须在使用字典内，且族别与判定方向一致（I=纳入码，E=排除码）
    rcd = d.get("reason_code_dict") or {}
    for i, s in enumerate(scr):
        rc = s.get("reason_code") or ""
        if rcd and rc and rc not in rcd:
            errs.append("screening[%d] 理由码 %s 不在字典内" % (i, rc))
        dv = s.get("decision")
        if rc[:1].upper() == "I" and dv == "exclude":
            errs.append("screening[%d] 用纳入码 %s 却判 exclude（码族与判定方向矛盾）" % (i, rc))
        if rc[:1].upper() == "E" and dv == "include":
            errs.append("screening[%d] 用排除码 %s 却判 include（码族与判定方向矛盾）" % (i, rc))
    table = [{"step": r[0], "input": r[1], "output": r[2], "note": r[3]} for r in rows]
    print(json.dumps({"ok": not errs, "closure_table": table, "decisions": dec, "errors": errs},
                     ensure_ascii=False))
    return 0 if not errs else 1


def cmd_agreement(path):
    try:
        d = json.load(open(path, encoding="utf-8"))
    except Exception as e:
        print(json.dumps({"ok": False, "error": "json 解析失败: %s" % e}, ensure_ascii=False))
        return 1
    pairs = d.get("pairs", d if isinstance(d, list) else [])
    pairs = [p for p in pairs if p.get("a") and p.get("b")]
    n = len(pairs)
    if n == 0:
        print(json.dumps({"ok": False, "error": "无有效 pairs"}, ensure_ascii=False))
        return 1
    agree = sum(1 for p in pairs if p["a"].get("decision") == p["b"].get("decision"))
    po = agree / float(n)
    cats = sorted({p["a"].get("decision") for p in pairs} | {p["b"].get("decision") for p in pairs})
    pe = 0.0
    for k in cats:
        pa = sum(1 for p in pairs if p["a"].get("decision") == k) / float(n)
        pb = sum(1 for p in pairs if p["b"].get("decision") == k) / float(n)
        pe += pa * pb
    kappa = 0.0 if pe == 1 else (po - pe) / (1 - pe)
    # 同为 include 时理由码一致性
    both_inc = [p for p in pairs if p["a"].get("decision") == p["b"].get("decision") == "include"]
    rc_ag = sum(1 for p in both_inc if p["a"].get("reason_code") == p["b"].get("reason_code"))
    disagree = [{"record_id": p.get("record_id"), "a": p["a"], "b": p["b"],
                 "type": "decision" if p["a"].get("decision") != p["b"].get("decision") else "reason_code"}
                for p in pairs
                if p["a"].get("decision") != p["b"].get("decision")
                or (p["a"].get("decision") == p["b"].get("decision") == "include"
                    and p["a"].get("reason_code") != p["b"].get("reason_code"))]
    print(json.dumps({"ok": True, "n": n, "decision_agreement": round(po, 4),
                      "cohen_kappa": round(kappa, 4),
                      "reason_code_agreement_on_includes": round(rc_ag / len(both_inc), 4) if both_inc else None,
                      "disagreements": disagree}, ensure_ascii=False))
    return 0


def cmd_schema(path):
    try:
        d = json.load(open(path, encoding="utf-8"))
    except Exception as e:
        print(json.dumps({"ok": False, "errors": ["json 解析失败: %s" % e]}, ensure_ascii=False))
        return 1
    if not isinstance(d, dict):
        print(json.dumps({"ok": False, "errors": ["顶层必须是对象"]}, ensure_ascii=False))
        return 1
    errs = []
    for k in ("case_id", "status", "research_question", "queries", "records",
              "screening", "counts", "coverage", "sources", "uncertainty", "change_log"):
        if k not in d:
            errs.append("缺顶层字段 %s" % k)
    if d.get("status") not in STATUSES:
        errs.append("status 非法: %s" % d.get("status"))
    for i, q in enumerate(d.get("queries", [])):
        for k in ("id", "query", "database", "run_date"):
            if k not in q:
                errs.append("queries[%d] 缺 %s" % (i, k))
    for i, r in enumerate(d.get("records", [])):
        for k in ("id", "title", "source"):
            if k not in r:
                errs.append("records[%d] 缺 %s" % (i, k))
    for i, s in enumerate(d.get("screening", [])):
        if s.get("decision") not in DECISIONS:
            errs.append("screening[%d] decision 非法" % i)
        if not s.get("reason_code") or not s.get("evidence_snippet"):
            errs.append("screening[%d] 缺理由码/依据片段" % i)
    if errs:
        print(json.dumps({"ok": False, "errors": errs}, ensure_ascii=False))
        return 1
    print(json.dumps({"ok": True, "queries": len(d.get("queries", [])),
                      "records": len(d.get("records", [])),
                      "screening": len(d.get("screening", []))}, ensure_ascii=False))
    return 0


CMDS = {"dedup": cmd_dedup, "audit": cmd_audit, "agreement": cmd_agreement, "schema": cmd_schema}

if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] in CMDS:
        sys.exit(CMDS[sys.argv[1]](sys.argv[2]))
    print(__doc__)
    sys.exit(2)
