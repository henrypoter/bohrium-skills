#!/usr/bin/env python3
"""科研检索工具 v3：去重 / 计数闭合 / 一致性 / 契约 / 覆盖率闭环复算。纯标准库。

命令:
  dedup      <records.json>        精确键去重 + 近似标题候选合并组（预印本/正式版）
  audit      <result.json>         PRISMA 式计数闭合审计，不闭合返回 1
  agreement  <pairs.json>          双人独立标注一致率与 Cohen's kappa，列分歧
  schema     <result.json>         基础交付契约校验
  covercheck <result.json>         冻结参考集、逐条命中、漏检归因与补检增量硬校验
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


def _coverage_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def cmd_covercheck(path):
    """Recompute coverage from frozen references; reject empty incremental searches."""
    try:
        with open(path, encoding="utf-8") as fh:
            d = json.load(fh)
    except Exception as e:
        print(json.dumps({"ok": False, "errors": ["json 解析失败: %s" % e]}, ensure_ascii=False))
        return 1
    if not isinstance(d, dict):
        print(json.dumps({"ok": False, "errors": ["顶层必须是对象"]}, ensure_ascii=False))
        return 1

    errs, notes = [], []
    for key in ("artifact_version", "method_version", "protocol_version", "reference_set",
                "hit_matrix", "search_rounds", "miss_attributions", "coverage", "stop_rule"):
        if key not in d:
            errs.append("covercheck 缺顶层字段 %s" % key)
    if d.get("artifact_version") != "coverage-result/v3":
        errs.append("artifact_version 必须为 coverage-result/v3")
    if d.get("method_version") != "frozen-reference-incremental-coverage/v3":
        errs.append("method_version 必须为 frozen-reference-incremental-coverage/v3")
    if not d.get("protocol_version"):
        errs.append("protocol_version 不能为空")
    if not d.get("stop_rule"):
        errs.append("stop_rule 必须明确补检停止条件")

    refset = d.get("reference_set") or {}
    for key in ("version", "frozen_at", "source", "denominator_rule"):
        if not refset.get(key):
            errs.append("reference_set.%s 缺失" % key)
    if (refset.get("denominator_rule") or {}).get("unavailable_fulltext_remains_eligible") is not True:
        errs.append("分母规则必须预先声明 unavailable_fulltext_remains_eligible=true")
    refs = refset.get("records") or []
    ref_by_id = {}
    for i, ref in enumerate(refs):
        rid = ref.get("ref_id")
        if not rid or rid in ref_by_id:
            errs.append("reference_set.records[%d] ref_id 缺失或重复" % i)
            continue
        ref_by_id[rid] = ref
        if not ref.get("inclusion_reason"):
            errs.append("reference %s 缺 inclusion_reason" % rid)
        if not isinstance(ref.get("countable"), bool):
            errs.append("reference %s 必须显式 countable=true/false" % rid)
        if not ref.get("countable"):
            if not ref.get("exclusion_reason"):
                errs.append("reference %s 不计分母必须写 exclusion_reason" % rid)
            # Lack of full text is an availability issue, never a reason to shrink N.
            if (ref.get("fulltext_status") == "unavailable"
                    and ref.get("retraction_status") != "retracted"):
                errs.append("reference %s 无全文不得移出覆盖率分母" % rid)
        if ref.get("fulltext_status") not in ("available", "unavailable", "unknown"):
            errs.append("reference %s fulltext_status 必须为 available/unavailable/unknown" % rid)
        retracted = ref.get("retraction_status") == "retracted"
        if retracted:
            if ref.get("countable"):
                errs.append("reference %s 已撤稿却仍计入分母" % rid)
            if not ref.get("retraction_evidence") or not ref.get("retraction_source"):
                errs.append("reference %s 撤稿缺 retraction_evidence/source" % rid)
            if (refset.get("denominator_rule") or {}).get("exclude_retracted") is not True:
                errs.append("分母规则未预先声明 exclude_retracted，却排除了撤稿 %s" % rid)
        elif ref.get("retraction_status") not in ("not_retracted", "unknown"):
            errs.append("reference %s retraction_status 必须为 not_retracted/unknown/retracted" % rid)
        if ref.get("identifier_status") == "conflict":
            conflicts = ref.get("identifier_conflicts") or []
            if not conflicts:
                errs.append("reference %s 标识冲突缺 identifier_conflicts" % rid)
            for conflict in conflicts:
                for key in ("field", "values", "resolution_status"):
                    if not conflict.get(key):
                        errs.append("reference %s 标识冲突缺 %s" % (rid, key))
                if conflict.get("resolution_status") == "resolved" and not conflict.get("resolution"):
                    errs.append("reference %s 标识冲突已解决但无 resolution" % rid)
                elif conflict.get("resolution_status") not in ("resolved", "unresolved"):
                    errs.append("reference %s resolution_status 非法" % rid)
        elif ref.get("identifier_status") not in ("ok", "missing", "unverified"):
            errs.append("reference %s identifier_status 非法" % rid)
    if not refs:
        errs.append("参考集为空：不得用候选检索结果临时构造分母")
    if not ref_by_id:
        # Avoid follow-on KeyErrors while still reporting all top-level contract errors.
        refs = []

    eligible = {rid for rid, ref in ref_by_id.items() if ref.get("countable") is True}
    excluded = set(ref_by_id) - eligible
    unresolved_ids = set()
    for rid, ref in ref_by_id.items():
        for conflict in ref.get("identifier_conflicts") or []:
            if conflict.get("resolution_status") == "unresolved":
                unresolved_ids.add(rid)
        if ref.get("retraction_status") == "unknown":
            unresolved_ids.add(rid)
    if unresolved_ids and d.get("status") == "pass":
        errs.append("标识/撤稿状态未解决时 status 不得为 pass: %s" % sorted(unresolved_ids))

    matrix = d.get("hit_matrix") or []
    matrix_by_id = {}
    for row in matrix:
        rid = row.get("ref_id")
        if rid in matrix_by_id:
            errs.append("hit_matrix 重复 ref_id %s" % rid)
        matrix_by_id[rid] = row
    if set(matrix_by_id) != set(ref_by_id):
        errs.append("hit_matrix 必须恰好覆盖冻结参考集每条记录（含撤稿/无全文）")
    for rid, row in matrix_by_id.items():
        for key in ("baseline_hit", "final_hit"):
            if not isinstance(row.get(key), bool):
                errs.append("hit_matrix %s 的 %s 必须为布尔值" % (rid, key))
        if rid in excluded and (row.get("baseline_hit") or row.get("final_hit")):
            errs.append("不计分母参考 %s 不得计为命中" % rid)
        if row.get("baseline_hit") and not row.get("final_hit") and not row.get("status_change_reason"):
            errs.append("参考 %s 从命中变漏检，必须给 status_change_reason" % rid)
        for stage in ("baseline", "final"):
            if row.get(stage + "_hit"):
                for key in (stage + "_match_rule", stage + "_evidence", stage + "_matched_record_id"):
                    if not row.get(key):
                        errs.append("参考 %s %s 命中缺 %s" % (rid, stage, key))
                if row.get(stage + "_match_rule") not in ("identifier", "title_author_year", "manual"):
                    errs.append("参考 %s %s_match_rule 必须为 identifier/title_author_year/manual" % (rid, stage))
                if rid in unresolved_ids and row.get(stage + "_match_rule") == "identifier":
                    errs.append("参考 %s 标识未决，不得仅凭标识判 %s 命中" % (rid, stage))
        if row.get("final_hit") and not row.get("baseline_hit") and not row.get("discovered_in_round"):
            errs.append("参考 %s 为补检新增命中但缺 discovered_in_round" % rid)

    rounds = d.get("search_rounds") or []
    round_by_id = {}
    new_hit_owner = {}
    failed_sources = set()
    for i, row in enumerate(rounds):
        qid = row.get("round_id")
        if not qid or qid in round_by_id:
            errs.append("search_rounds[%d] round_id 缺失或重复" % i)
            continue
        round_by_id[qid] = row
        for key in ("query", "fields", "source", "run_date", "status", "new_hit_ids"):
            if key not in row or (key != "new_hit_ids" and not row.get(key)):
                errs.append("search_round %s 缺 %s" % (qid, key))
        if row.get("status") not in ("ok", "empty", "timeout", "error", "permission_denied"):
            errs.append("search_round %s status 非法" % qid)
        if row.get("status") in ("timeout", "error", "permission_denied"):
            failed_sources.add(row.get("source"))
            if row.get("new_hit_ids"):
                errs.append("失败/超时查询 %s 不得报告新增命中" % qid)
            if not row.get("detail") or not row.get("next_action"):
                errs.append("异常查询 %s 缺 detail/next_action" % qid)
        for rid in row.get("new_hit_ids") or []:
            if rid not in eligible:
                errs.append("search_round %s 的新增命中 %s 不在有效参考集" % (qid, rid))
                continue
            hit = matrix_by_id.get(rid) or {}
            if not hit.get("final_hit") or hit.get("baseline_hit"):
                errs.append("search_round %s 把非真实新增 %s 计为增量" % (qid, rid))
            if hit.get("discovered_in_round") != qid:
                errs.append("参考 %s discovered_in_round 与 %s 不一致" % (rid, qid))
            if rid in new_hit_owner:
                errs.append("新增命中 %s 被 %s/%s 重复计收益" % (rid, new_hit_owner[rid], qid))
            new_hit_owner[rid] = qid
        if row.get("status") == "ok" and not row.get("target_miss_codes"):
            errs.append("补检查询 %s 缺 target_miss_codes，无法证明定向补检" % qid)
    recovered = {rid for rid in eligible
                 if (matrix_by_id.get(rid) or {}).get("final_hit")
                 and not (matrix_by_id.get(rid) or {}).get("baseline_hit")}
    if recovered != set(new_hit_owner):
        errs.append("补检新增并集 %s 与 hit_matrix 恢复集合 %s 不一致" %
                    (sorted(new_hit_owner), sorted(recovered)))
    if failed_sources and d.get("status") == "pass":
        errs.append("来源超时/错误/权限不足时 status 不得为 pass")

    baseline_hits = {rid for rid in eligible if (matrix_by_id.get(rid) or {}).get("baseline_hit")}
    final_hits = {rid for rid in eligible if (matrix_by_id.get(rid) or {}).get("final_hit")}
    baseline_missed, final_missed = eligible - baseline_hits, eligible - final_hits
    denominator = len(eligible)
    baseline_rate = len(baseline_hits) / float(denominator) if denominator else None
    final_rate = len(final_hits) / float(denominator) if denominator else None
    coverage = d.get("coverage") or {}
    expected_counts = {
        "reference_total": len(ref_by_id), "eligible_total": denominator,
        "excluded_total": len(excluded), "baseline_retrieved": len(baseline_hits),
        "baseline_missed": len(baseline_missed), "retrieved": len(final_hits),
        "missed": len(final_missed), "incremental_new_hits": len(recovered)
    }
    for key, expected in expected_counts.items():
        if coverage.get(key) != expected:
            errs.append("coverage.%s 复算应为 %s，实际 %s" % (key, expected, coverage.get(key)))
    for key, expected in (("baseline_rate", baseline_rate), ("coverage_rate", final_rate)):
        actual = coverage.get(key)
        if expected is None:
            if actual is not None:
                errs.append("有效分母为 0 时 %s 必须为 null，不得报 100%%" % key)
        elif not _coverage_number(actual) or abs(float(actual) - expected) > 1e-8:
            errs.append("coverage.%s 复算应为 %s，实际 %s" % (key, expected, actual))
    if not isinstance(coverage.get("complete"), bool):
        errs.append("coverage.complete 必须为布尔值")
    elif failed_sources and coverage.get("complete"):
        errs.append("来源异常未决时 coverage.complete 不得为 true")
    elif unresolved_ids and coverage.get("complete"):
        errs.append("标识/撤稿状态未决时 coverage.complete 不得为 true")
    if set(coverage.get("unresolved_sources") or []) != failed_sources:
        errs.append("coverage.unresolved_sources 必须精确列出异常来源")

    attributions = d.get("miss_attributions") or []
    attribution_by_id = {}
    for row in attributions:
        rid = row.get("ref_id")
        if rid in attribution_by_id:
            errs.append("miss_attributions 重复 ref_id %s" % rid)
        attribution_by_id[rid] = row
    if set(attribution_by_id) != final_missed:
        errs.append("每条最终漏检必须且只能有一条 miss_attribution；期望 %s" % sorted(final_missed))
    for rid, row in attribution_by_id.items():
        code = row.get("miss_reason_code")
        if code not in ("M1", "M2", "M3", "M4", "M5"):
            errs.append("漏检 %s miss_reason_code 非法" % rid)
        attribution = row.get("attribution") or {}
        if not attribution.get("evidence"):
            errs.append("漏检 %s 缺具体判定 evidence" % rid)
        if code in ("M1", "M2", "M3") and not attribution.get("query_id"):
            errs.append("漏检 %s/%s 必须指到具体 query_id" % (rid, code))
        if code == "M2" and not attribution.get("field"):
            errs.append("漏检 %s/M2 必须指到具体 field" % rid)
        if code == "M4" and not attribution.get("source"):
            errs.append("漏检 %s/M4 必须指到具体 source" % rid)
        if code == "M5" and not attribution.get("field"):
            errs.append("漏检 %s/M5 必须指到异常标识 field" % rid)
    computed_codes = {}
    for row in attributions:
        code = row.get("miss_reason_code")
        computed_codes[code] = computed_codes.get(code, 0) + 1
    if coverage.get("missed_by_code") != computed_codes:
        errs.append("coverage.missed_by_code 与逐条归因复算不符：应为 %s" % computed_codes)

    out = {"ok": not errs, "reference_version": refset.get("version"),
           "denominator": denominator, "baseline": {"hit": len(baseline_hits), "miss": len(baseline_missed),
                                                     "coverage_rate": baseline_rate},
           "final": {"hit": len(final_hits), "miss": len(final_missed), "coverage_rate": final_rate},
           "true_incremental_hits": sorted(recovered), "unresolved_sources": sorted(failed_sources),
           "notes": notes, "errors": errs}
    print(json.dumps(out, ensure_ascii=False))
    return 0 if not errs else 1


CMDS = {"dedup": cmd_dedup, "audit": cmd_audit, "agreement": cmd_agreement,
        "schema": cmd_schema, "covercheck": cmd_covercheck}

if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] in CMDS:
        sys.exit(CMDS[sys.argv[1]](sys.argv[2]))
    print(__doc__)
    sys.exit(2)
