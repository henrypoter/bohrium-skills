#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""validate_result.py - result.json 契约校验 + 原文双重核对 + 缺口汇总。纯标准库。
用法: python3 validate_result.py <result.json> [paper_text.txt]; 退出码 0=通过, 1=失败(FAIL 自明原因)。not_reported 是合法答案。
契约: 顶层 7 键; status 四值且有 extraction_failed 时不得 success; 记录 12 键
齐全、field_id 不重复、status 四态互斥、非 reported 时 value=null(猜的值不是
抽取,缺席不是 0)、reported 必须 value+quote+页/段定位; source_type 四值;
inferred 的 note 必须含推算过程(数字+算式); claims 三类型带 quote+定位,
speculation 的 quote 必含情态词、limitation 必含限定词; gaps 三键与记录一致。
带 paper_text(pdf_text.py 输出, 含 === PAGE n === 标记)追加: Q1 quote 必须是
原文子串且命中所标页; N1 value 的每个数字串必须出现在 quote 中;
N2 statistic 数字与 unit 必须在原文中存在。
"""
import json
import re
import sys

TOP_REQUIRED = ["case_id", "status", "results", "sources", "uncertainty",
                "gaps", "change_records"]
RUN_STATUS = {"success", "partial", "cannot_determine", "refused"}
FIELD_STATUS = {"reported", "not_reported", "source_conflict", "extraction_failed"}
CLAIM_TYPE = {"conclusion", "limitation", "speculation"}
SOURCE_TYPE = {"text", "table", "figure_caption", "supplement"}
REC_REQUIRED = ["field_id", "question", "value", "unit", "statistic", "condition",
                "comparator", "basis", "status", "source_type", "evidence", "note"]
NUM_RE = re.compile(r"\d+(?:\.\d+)?")
HEDGE = ["may", "might", "could", "suggest", "possibly", "likely",
         "speculat", "indicate", "可能", "提示", "推测", "有望"]
LIMIT = ["limit", "only", "under these", "restricted",
         "限于", "仅", "局限", "限制", "不足"]
DERIVE = ["=", "＝", "→", "差", "推算", "算式", "%", "百分点"]


def norm(s):
    return re.sub(r"\s+", " ", str(s)).strip().lower()


def nums(s):
    return NUM_RE.findall(str(s))


def load_paper(path):
    """归一化全文 + {页号: 页文本}。"""
    raw = open(path, encoding="utf-8", errors="replace").read()
    parts = re.split(r"===\s*PAGE\s+(\d+)\s*[^=]*===", raw)
    pages = None
    if len(parts) > 2:
        pages = {}
        for i in range(1, len(parts) - 1, 2):
            pages[int(parts[i])] = norm(parts[i + 1])
    return norm(raw), pages


def quote_check(ev, tag, full, pages, errors):
    q = norm((ev or {}).get("quote") or "")
    if not q:
        return
    if q not in full:
        errors.append("%s quote 未逐字命中原文（编造/改写?）" % tag)
        return
    pg = (ev or {}).get("page")
    if pages and isinstance(pg, int):
        if pg not in pages:
            errors.append("%s 页码 %s 超出页标记范围" % (tag, pg))
        elif q not in pages[pg]:
            errors.append("%s quote 不在所标第 %s 页（页码错配）" % (tag, pg))


def numeric_check(rec, tag, full, errors):
    q = norm((rec.get("evidence") or {}).get("quote") or "")
    for n in nums(rec.get("value")):
        if n not in q:
            errors.append("%s value 数字 %s 不在 quote 中（数值≠引文）" % (tag, n))
    for n in nums(rec.get("statistic")):
        if n not in full:
            errors.append("%s statistic 数字 %s 原文不存在（编造?）" % (tag, n))
    u = norm(rec.get("unit") or "")
    if u and u not in full:
        errors.append("%s unit %r 原文不存在（自补?）" % (tag, u))


def check(rpath, ppath=None):
    errors = []
    try:
        doc = json.load(open(rpath, encoding="utf-8"))
    except Exception as e:
        return ["result.json 不是合法 JSON: %s" % e], None
    full = pages = None
    if ppath:
        full, pages = load_paper(ppath)
    for k in TOP_REQUIRED:
        if k not in doc:
            errors.append("缺顶层键: %s" % k)
    if doc.get("status") not in RUN_STATUS:
        errors.append("status 非法: %r" % doc.get("status"))
    recs = doc.get("results") or []
    if not isinstance(recs, list) or not recs:
        errors.append("results 必须是非空数组")
    if doc.get("status") == "success" and any(
            r.get("status") == "extraction_failed" for r in recs):
        errors.append("有 extraction_failed 时顶层 status 不得为 success")
    seen = set()
    for i, rec in enumerate(recs):
        tag = "results[%d](%s)" % (i, rec.get("field_id", "?"))
        for k in REC_REQUIRED:
            if k not in rec:
                errors.append("%s 缺键: %s" % (tag, k))
        fid = rec.get("field_id")
        if fid in seen:
            errors.append("%s field_id 重复" % tag)
        seen.add(fid)
        st = rec.get("status")
        if st not in FIELD_STATUS:
            errors.append("%s status 非法: %r" % (tag, st))
            continue
        if rec.get("source_type") not in SOURCE_TYPE:
            errors.append("%s source_type 非法: %r" % (tag, rec.get("source_type")))
        ev = rec.get("evidence") or {}
        if st == "reported":
            if rec.get("value") is None:
                errors.append("%s reported 但 value 为 null" % tag)
            if not (ev.get("quote") or "").strip():
                errors.append("%s reported 但 evidence.quote 为空" % tag)
            if ev.get("page") is None and not ev.get("paragraph_id"):
                errors.append("%s reported 但缺页/段定位" % tag)
        elif rec.get("value") is not None:
            errors.append("%s status=%s 时 value 必须为 null" % (tag, st))
        if rec.get("basis") not in ("direct", "inferred"):
            errors.append("%s basis 必须为 direct/inferred" % tag)
        if rec.get("basis") == "inferred":
            note = str(rec.get("note") or "")
            if not (nums(note) and any(d in note for d in DERIVE)):
                errors.append("%s inferred 的 note 缺推算过程（需数字+算式）" % tag)
        if full is not None:
            quote_check(ev, tag, full, pages, errors)
            if st == "reported":
                numeric_check(rec, tag, full, errors)
    for i, cl in enumerate(doc.get("claims") or []):
        tag = "claims[%d]" % i
        ct = cl.get("type")
        if ct not in CLAIM_TYPE:
            errors.append("%s type 非法: %r" % (tag, ct))
        ev = cl.get("evidence") or {}
        q = norm(ev.get("quote") or "")
        if not q:
            errors.append("%s 缺 quote" % tag)
        if ev.get("page") is None and not ev.get("paragraph_id"):
            errors.append("%s 缺页码/段落定位" % tag)
        if ct == "speculation" and q and not any(c in q for c in HEDGE):
            errors.append("%s speculation 的 quote 无情态词（推测当实测?）" % tag)
        if ct == "limitation" and q and not any(c in q for c in LIMIT):
            errors.append("%s limitation 的 quote 无限定词" % tag)
        if full is not None:
            quote_check(ev, tag, full, pages, errors)
    # 缺口汇总：三态分列，与记录一致性核对
    gaps = {"not_reported": [], "source_conflict": [], "extraction_failed": []}
    for rec in recs:
        if rec.get("status") in gaps:
            gaps[rec["status"]].append(rec.get("field_id"))
    declared = doc.get("gaps") or {}
    for k, v in gaps.items():
        if sorted(declared.get(k, [])) != sorted(v):
            errors.append("gaps.%s 与记录不一致: 声明%r 实际%r" % (k, declared.get(k), v))
    return errors, gaps


def main():
    if len(sys.argv) not in (2, 3):
        sys.stderr.write("usage: validate_result.py <result.json> [paper_text.txt]\n")
        return 1
    errors, gaps = check(sys.argv[1], sys.argv[2] if len(sys.argv) == 3 else None)
    if gaps is not None:
        sys.stderr.write("GAP_SUMMARY %s\n" % json.dumps(gaps, ensure_ascii=False))
    if errors:
        for e in errors:
            sys.stderr.write("FAIL: %s\n" % e)
        return 1
    sys.stderr.write("OK: 契约校验通过%s\n" % ("（含原文双重核对）" if len(sys.argv) == 3 else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
