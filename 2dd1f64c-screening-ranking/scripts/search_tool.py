#!/usr/bin/env python3
"""科研检索工具 v3：去重 / 计数闭合 / 一致性 / 契约 / 可复算排序。纯标准库。

命令:
  dedup     <records.json>        精确键去重 + 近似标题候选合并组（预印本/正式版）
  audit     <result.json>         PRISMA 式计数闭合审计，不闭合返回 1
  agreement <pairs.json>          双人独立标注一致率与 Cohen's kappa，列分歧
  schema    <result.json>         基础交付契约校验
  rankcheck <result.json>         全量评分复算、证据/阈值/Top-k/稳定平局及异常闸
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


def _finite_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def cmd_rankcheck(path):
    """Validate and independently recompute the final, finite-snapshot ranking."""
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
    for key in ("artifact_version", "method_version", "protocol_version", "snapshot",
                "dimensions", "ranking_policy", "scores", "ranking", "top_k",
                "metadata_issues", "criteria_conflicts", "source_status"):
        if key not in d:
            errs.append("rankcheck 缺顶层字段 %s" % key)
    if d.get("artifact_version") != "screening-result/v3":
        errs.append("artifact_version 必须为 screening-result/v3")
    if d.get("method_version") != "evidence-weighted-stable-rank/v3":
        errs.append("method_version 必须为 evidence-weighted-stable-rank/v3")
    if not d.get("protocol_version"):
        errs.append("protocol_version 不能为空")

    records = d.get("records") or []
    record_ids = [r.get("id") for r in records if isinstance(r, dict)]
    if len(record_ids) != len(records) or any(not x for x in record_ids):
        errs.append("每条 record 必须有非空 id")
    if len(set(record_ids)) != len(record_ids):
        errs.append("records 存在重复 id")

    # Empty input is a declared terminal state, never a successful zero-row ranking.
    if not records:
        empty = d.get("empty_result")
        if not isinstance(empty, dict):
            errs.append("候选集为空：必须提供 empty_result，不得交付空成功排序")
        else:
            for key in ("reason", "queries_examined", "completed_parts", "not_completed", "next_action"):
                if key not in empty or empty.get(key) in (None, "", []):
                    errs.append("empty_result.%s 不能为空" % key)
        if d.get("status") == "pass":
            errs.append("候选集为空时 status 不得为 pass")

    snapshot = d.get("snapshot") or {}
    for key in ("id", "created_at", "source", "record_count"):
        if key not in snapshot or snapshot.get(key) in (None, ""):
            errs.append("snapshot.%s 缺失" % key)
    if snapshot.get("record_count") != len(records):
        errs.append("snapshot.record_count 与 records 数不一致")

    # Missing fields are declared and scored as unknown; they are never silently zero.
    metadata_rows = d.get("metadata_issues") or []
    metadata_by_id = {}
    for i, row in enumerate(metadata_rows):
        if not isinstance(row, dict) or not row.get("record_id"):
            errs.append("metadata_issues[%d] 缺 record_id" % i)
            continue
        if row["record_id"] not in record_ids:
            errs.append("metadata_issues[%d] 指向不存在记录 %s" % (i, row["record_id"]))
        metadata_by_id.setdefault(row["record_id"], []).append(row)
        if not row.get("fields") or not row.get("action"):
            errs.append("metadata_issues[%d] 缺 fields/action" % i)
    for rec in records:
        rid = rec.get("id")
        missing = [k for k in ("abstract", "year") if rec.get(k) in (None, "")]
        declared = set()
        for row in metadata_by_id.get(rid, []):
            declared.update(row.get("fields") or [])
        for key in missing:
            if key not in declared:
                errs.append("%s 缺 %s 但未在 metadata_issues 声明" % (rid, key))
        if "year" in declared and "year" not in missing:
            errs.append("%s 的 year 并未缺失，不得伪造 metadata_issue" % rid)
        if "abstract" in declared and "abstract" not in missing:
            errs.append("%s 的 abstract 并未缺失，不得伪造 metadata_issue" % rid)

    # Interface failures and permissions are unresolved coverage, not empty relevance.
    bad_sources = []
    source_rows = d.get("source_status") or []
    reported_sources = {row.get("source") for row in source_rows if isinstance(row, dict)}
    expected_sources = ({r.get("source") for r in records if r.get("source")} |
                        {q.get("database") for q in (d.get("queries") or []) if q.get("database")})
    if expected_sources - reported_sources:
        errs.append("以下来源缺 source_status：%s" % sorted(expected_sources - reported_sources))
    for i, row in enumerate(source_rows):
        if not isinstance(row, dict) or not row.get("source") or not row.get("status"):
            errs.append("source_status[%d] 缺 source/status" % i)
            continue
        state = row.get("status")
        if state not in ("ok", "empty", "timeout", "error", "permission_denied"):
            errs.append("source_status[%d] status 非法" % i)
        if state == "empty" and row.get("source") in {r.get("source") for r in records}:
            errs.append("source_status[%d] 报 empty 却提供该源记录" % i)
        if state in ("timeout", "error", "permission_denied"):
            bad_sources.append(row.get("source"))
            if not row.get("detail") or not row.get("next_action"):
                errs.append("source_status[%d] 异常缺 detail/next_action" % i)
    if bad_sources and d.get("status") == "pass":
        errs.append("接口异常/权限不足时 status 不得为 pass: %s" % ",".join(bad_sources))

    # Declared rubric conflicts must be versioned and either resolved or quarantined.
    unresolved_conflicts = []
    for i, row in enumerate(d.get("criteria_conflicts") or []):
        for key in ("rule_ids", "conflict", "status", "affected_record_ids"):
            if key not in row or row.get(key) in (None, "", []):
                errs.append("criteria_conflicts[%d] 缺 %s" % (i, key))
        if not set(row.get("affected_record_ids") or []).issubset(set(record_ids)):
            errs.append("criteria_conflicts[%d] affected_record_ids 含未知记录" % i)
        if row.get("status") == "resolved":
            if not row.get("resolution") or row.get("resolved_in_version") != d.get("protocol_version"):
                errs.append("criteria_conflicts[%d] 解决版本/resolution 不闭合" % i)
        elif row.get("status") == "unresolved":
            unresolved_conflicts.extend(row.get("affected_record_ids") or [])
            if not row.get("next_action"):
                errs.append("criteria_conflicts[%d] 未解决但没有 next_action" % i)
        else:
            errs.append("criteria_conflicts[%d] status 必须为 resolved/unresolved" % i)
    if unresolved_conflicts and d.get("status") == "pass":
        errs.append("存在未解决标注标准冲突时 status 不得为 pass")

    dimensions = d.get("dimensions") or []
    dim_by_id, weights = {}, {}
    for i, dim in enumerate(dimensions):
        did = dim.get("id")
        if not did or did in dim_by_id:
            errs.append("dimensions[%d] id 缺失或重复" % i)
            continue
        dim_by_id[did] = dim
        weight = dim.get("weight")
        if not _finite_number(weight) or weight <= 0:
            errs.append("dimension %s weight 必须为正数" % did)
        else:
            weights[did] = float(weight)
        anchors = dim.get("anchors") or {}
        if any(str(k) not in anchors for k in (0, 1, 2)):
            errs.append("dimension %s 缺 0/1/2 打分锚点" % did)
    if not dimensions:
        errs.append("至少一个相关性维度")
    elif abs(sum(weights.values()) - 1.0) > 1e-8 or len(weights) != len(dimensions):
        errs.append("维度权重必须齐全且总和为 1")

    scores = d.get("scores") or []
    score_by_id = {}
    for row in scores:
        rid = row.get("record_id")
        if rid in score_by_id:
            errs.append("scores 重复记录 %s" % rid)
        score_by_id[rid] = row
    if set(score_by_id) != set(record_ids):
        errs.append("scores 必须恰好覆盖全部候选 records（含排除项）")

    totals = {}
    for rid, row in score_by_id.items():
        dim_scores = row.get("dim_scores") or {}
        if set(dim_scores) != set(dim_by_id):
            errs.append("%s 的 dim_scores 必须逐维完整" % rid)
            continue
        unknown = set(row.get("unknown_dimensions") or [])
        unknown_details = row.get("unknown_details") or {}
        evidence = {}
        for ev in row.get("evidence") or []:
            evidence.setdefault(ev.get("dim"), []).append(ev)
        known_weight, weighted = 0.0, 0.0
        for did in dim_by_id:
            value = dim_scores.get(did)
            if value is None:
                if did not in unknown or not unknown_details.get(did):
                    errs.append("%s/%s 为 null 时必须声明 unknown_dimensions 与原因" % (rid, did))
                continue
            if did in unknown:
                errs.append("%s/%s 已有分值却仍列 unknown" % (rid, did))
            if not _finite_number(value) or value < 0 or value > 2:
                errs.append("%s/%s 分值必须为 0..2 或 null" % (rid, did))
                continue
            if did in weights:
                weighted += float(value) * weights[did]
                known_weight += weights[did]
            evs = evidence.get(did) or []
            if not any(ev.get("snippet") and ev.get("location") for ev in evs):
                errs.append("%s/%s 缺可定位证据 snippet/location" % (rid, did))
        expected = weighted / known_weight if known_weight else None
        totals[rid] = expected
        actual = row.get("total")
        if expected is None:
            if actual is not None:
                errs.append("%s 全维 unknown 时 total 必须为 null" % rid)
        elif not _finite_number(actual) or abs(float(actual) - expected) > 1e-8:
            errs.append("%s total 复算不符：期望 %s，实际 %s" % (rid, expected, actual))
        if unknown and row.get("confidence") == "high":
            errs.append("%s 有 unknown 维度时 confidence 不得为 high" % rid)

    policy = d.get("ranking_policy") or {}
    for key in ("version", "score_formula", "include_min", "exclude_max", "k", "tie_breakers"):
        if key not in policy:
            errs.append("ranking_policy 缺 %s" % key)
    if not policy.get("version"):
        errs.append("ranking_policy.version 不能为空")
    if policy.get("score_formula") != "known_weight_renormalized":
        errs.append("score_formula 必须为 known_weight_renormalized")
    if policy.get("tie_breakers") != ["unknown_last", "total_desc", "record_id_asc"]:
        errs.append("tie_breakers 必须固定为 unknown_last,total_desc,record_id_asc")
    include_min, exclude_max = policy.get("include_min"), policy.get("exclude_max")
    if not (_finite_number(include_min) and _finite_number(exclude_max)
            and 0 <= exclude_max < include_min <= 2):
        errs.append("阈值须满足 0 <= exclude_max < include_min <= 2")

    ranking = d.get("ranking") or []
    rank_by_id = {}
    for row in ranking:
        rid = row.get("record_id")
        if rid in rank_by_id:
            errs.append("ranking 重复记录 %s" % rid)
        rank_by_id[rid] = row
    if set(rank_by_id) != set(record_ids):
        errs.append("ranking 必须恰好覆盖全部候选 records（含排除项）")

    bucket_by_id = {}
    for row in ranking:
        rid, bucket = row.get("record_id"), row.get("bucket")
        bucket_by_id[rid] = bucket
        if bucket not in ("include", "borderline", "exclude"):
            errs.append("%s bucket 非法" % rid)
        if rid in totals:
            actual = row.get("total")
            expected = totals[rid]
            if expected is None:
                if actual is not None or bucket != "borderline":
                    errs.append("%s 全 unknown 必须 total=null 且 borderline" % rid)
            elif not _finite_number(actual) or abs(float(actual) - expected) > 1e-8:
                errs.append("%s ranking.total 与复算分不一致" % rid)
            elif _finite_number(include_min) and _finite_number(exclude_max):
                expected_bucket = ("borderline" if rid in unresolved_conflicts else
                                   "include" if expected >= include_min else
                                   "exclude" if expected <= exclude_max else "borderline")
                if bucket != expected_bucket:
                    errs.append("%s bucket 与先验阈值不符，应为 %s" % (rid, expected_bucket))
        if not row.get("reason"):
            errs.append("%s 缺逐条排序/筛选 reason" % rid)
    for rid in unresolved_conflicts:
        if bucket_by_id.get(rid) != "borderline":
            errs.append("%s 标准冲突未解决，必须隔离为 borderline" % rid)

    expected_order = sorted(record_ids, key=lambda rid: (
        totals.get(rid) is None,
        -(totals.get(rid) if totals.get(rid) is not None else 0.0),
        str(rid)))
    actual_order = [row.get("record_id") for row in ranking]
    if records and actual_order != expected_order:
        errs.append("排序不符稳定键：期望 %s，实际 %s" % (expected_order, actual_order))
    for i, row in enumerate(ranking, 1):
        if row.get("rank") != i:
            errs.append("rank 必须从 1 连续编号：位置 %d" % i)

    # Large ties stay visible; record_id only fixes presentation, not scientific merit.
    tie_groups = {}
    for row in ranking:
        tie_groups.setdefault(repr(row.get("total")), []).append(row)
    for members in tie_groups.values():
        if len(members) > 1:
            for row in members:
                if not row.get("tie_group") or not row.get("tie_resolution"):
                    errs.append("同分组必须逐条保留 tie_group/tie_resolution: %s" % row.get("record_id"))
    tie_sizes = {key: len(members) for key, members in tie_groups.items()}
    largest_tie = max(tie_sizes.values()) if tie_sizes else 0
    if largest_tie >= 3:
        notes.append("检测到大量同分（最大 %d 条）；稳定次序不代表组内科学差异" % largest_tie)

    k = policy.get("k")
    if not isinstance(k, int) or isinstance(k, bool) or k < 1 or (records and k > len(records)):
        errs.append("ranking_policy.k 必须为 1..N 的整数")
    elif d.get("top_k") != actual_order[:k]:
        errs.append("top_k 必须等于稳定排序前 k 个 record_id，且 k 可见")

    # Final screening is the consolidated row, not two independent annotation rows.
    screening = d.get("screening") or []
    final_by_id = {row.get("record_id"): row for row in screening}
    if len(final_by_id) != len(screening) or set(final_by_id) != set(record_ids):
        errs.append("screening 必须为每条候选一条最终合并判定")
    decision_bucket = {"include": "include", "maybe": "borderline", "exclude": "exclude"}
    for rid, row in final_by_id.items():
        if decision_bucket.get(row.get("decision")) != bucket_by_id.get(rid):
            errs.append("%s screening.decision 与 ranking.bucket 不一致" % rid)
        if row.get("rule_version") != d.get("protocol_version"):
            errs.append("%s screening.rule_version 必须等于 protocol_version" % rid)

    out = {"ok": not errs, "records": len(records), "computed_totals": totals,
           "stable_order": actual_order, "largest_tie": largest_tie,
           "unresolved_sources": bad_sources, "notes": notes, "errors": errs}
    print(json.dumps(out, ensure_ascii=False))
    return 0 if not errs else 1


CMDS = {"dedup": cmd_dedup, "audit": cmd_audit, "agreement": cmd_agreement,
        "schema": cmd_schema, "rankcheck": cmd_rankcheck}

if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] in CMDS:
        sys.exit(CMDS[sys.argv[1]](sys.argv[2]))
    print(__doc__)
    sys.exit(2)
