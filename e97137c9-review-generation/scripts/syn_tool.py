#!/usr/bin/env python3
"""文献综述机检（纯 Python 标准库，tool_version=2.0.0）。

  cite_check <result.json>       论断引用、清单成员、定位与纳排理由
  theme_check <result.json>      主题是否都有带引用论断
  screen_check <result.json>     筛选判据引用、逐条决定、重复与计数闭合
  evidence_check <result.json>   原文摘录、证据强度、事实/推断/未定区分
  grounding_check <result.json>  主题归纳依据、覆盖、冲突与有据空白
  provenance_check <result.json> --input <case.json> --source-root <dir>
                                 复算输入及每份原始材料的 SHA-256，查版本字段
  schema <result.json>           顶层交付契约、版本字段与计数初检

退出码：0=结构检查通过；1=发现交付问题；2=调用或输入文件错误。
这些命令检查可复核结构，不替代人工判断引文是否真正支持论断。
"""
import hashlib
import json
import os
import re
import sys

TOOL_VERSION = "2.0.0"
HEX64 = re.compile(r"^[0-9a-f]{64}$")


def _load(path):
    with open(path, encoding="utf-8") as f:
        value = json.load(f)
    if not isinstance(value, dict):
        raise ValueError("result.json 顶层必须是对象")
    return value


def _present(value):
    return value is not None and value != "" and value != [] and value != {}


def _ids(items, key="id"):
    return {x.get(key) for x in items if isinstance(x, dict) and _present(x.get(key))}


def _emit(ok, **payload):
    print(json.dumps({"ok": ok, **payload}, ensure_ascii=False))
    return 0 if ok else 1


def _run_errors(d):
    errs = []
    run = d.get("run")
    if not isinstance(run, dict):
        return ["缺 run 对象（版本与输入指纹）"]
    for key in ("skill_version", "tool_version", "input_sha256", "generated_at", "source_snapshot"):
        if not _present(run.get(key)):
            errs.append("run.%s 为空" % key)
    if not HEX64.match(str(run.get("input_sha256", ""))):
        errs.append("run.input_sha256 须为 64 位小写十六进制")
    if run.get("tool_version") != TOOL_VERSION:
        errs.append("run.tool_version 须为 %s" % TOOL_VERSION)
    if run.get("case_id") and run.get("case_id") != d.get("case_id"):
        errs.append("run.case_id 与顶层 case_id 不一致")
    return errs


def cmd_cite_check(path):
    d = _load(path)
    recs = _ids(d.get("records", d.get("included", [])))
    errs, uncited, dangling = [], [], []
    claims = d.get("claims", [])
    if not claims:
        errs.append("claims 为空(综述必须输出论断)")
    for i, claim in enumerate(claims):
        citations = claim.get("citations", [])
        if not citations:
            uncited.append(claim.get("id") or "claim[%d]" % i)
        for j, citation in enumerate(citations):
            rid = citation.get("record_id")
            if not citation.get("location"):
                errs.append("claims[%d].citations[%d] 缺 location(须定位到页/段)" % (i, j))
            if recs and rid and rid not in recs:
                dangling.append({"claim": claim.get("id"), "record_id": rid})
    for i, record in enumerate(d.get("included", [])):
        if not record.get("screening_reason"):
            errs.append("included[%d] 缺 screening_reason" % i)
    if not d.get("screening_criteria"):
        errs.append("screening_criteria 为空(筛选标准须先于写作写明)")
    ok = not errs and not dangling and not uncited
    return _emit(ok, n_claims=len(claims), uncited_claims=uncited,
                 dangling_citations=dangling, errors=errs)


def cmd_theme_check(path):
    d = _load(path)
    claims = d.get("claims", [])
    themes = d.get("themes", [])
    by_theme = {}
    for claim in claims:
        theme = claim.get("theme") or "(未归类)"
        by_theme.setdefault(theme, []).append(bool(claim.get("citations")))
    uncovered = [t for t in (x.get("name") for x in themes) if t not in by_theme]
    weak = [t for t, values in by_theme.items() if not any(values)]
    unclassified = len(by_theme.get("(未归类)", []))
    ok = not uncovered and not weak and not unclassified and bool(themes)
    return _emit(ok, themes_declared=len(themes), themes_with_claims=len(by_theme),
                 themes_without_claims=uncovered, themes_without_cited_claim=weak,
                 unclassified_claims=unclassified)


def cmd_screen_check(path):
    d = _load(path)
    errs = []
    criteria = d.get("screening_criteria", [])
    criterion_ids = _ids(criteria)
    records = d.get("records", [])
    record_ids = _ids(records)
    if len(criterion_ids) != len(criteria) or not criterion_ids:
        errs.append("screening_criteria 必须非空且每条有唯一 id")
    if len(record_ids) != len(records) or not records:
        errs.append("records 必须非空且每条有唯一 id")
    decided = {"include": set(), "exclude": set(), "pending": set()}
    for i, record in enumerate(records):
        rid = record.get("id", "records[%d]" % i)
        decision = record.get("decision")
        if decision not in decided:
            errs.append("%s decision 须为 include/exclude/pending" % rid)
        else:
            decided[decision].add(rid)
        refs = record.get("criterion_ids", [])
        if not refs or any(ref not in criterion_ids for ref in refs):
            errs.append("%s criterion_ids 未完整引用已声明判据" % rid)
        if not _present(record.get("screening_reason")):
            errs.append("%s 缺 screening_reason" % rid)
        if record.get("fulltext_status") not in {"available", "abstract_only", "unavailable"}:
            errs.append("%s fulltext_status 非法" % rid)
        if record.get("duplicate_of"):
            if decision != "exclude" or record.get("duplicate_of") not in record_ids:
                errs.append("%s 重复文献须 exclude 且 duplicate_of 指向有效记录" % rid)
    for key, expected in (("included", decided["include"]), ("excluded", decided["exclude"])):
        actual = _ids(d.get(key, []))
        if actual != expected:
            errs.append("%s 与 records.decision 不一致" % key)
    duplicates = d.get("duplicates")
    if not isinstance(duplicates, list):
        errs.append("duplicates 须为数组（无重复也为空数组）")
    else:
        for group in duplicates:
            canonical = group.get("canonical_record_id")
            if canonical not in record_ids or not group.get("duplicate_record_ids") or not group.get("match_basis"):
                errs.append("duplicates 组须含有效 canonical_record_id、duplicate_record_ids、match_basis")
            for rid in group.get("duplicate_record_ids", []):
                match = next((r for r in records if r.get("id") == rid), None)
                if not match or match.get("duplicate_of") != canonical:
                    errs.append("重复记录 %s 未反向指向 %s" % (rid, canonical))
    counts = d.get("counts", {})
    expected_counts = {"records_raw": len(records), "included": len(decided["include"]),
                       "excluded": len(decided["exclude"]), "pending": len(decided["pending"])}
    for key, expected in expected_counts.items():
        if counts.get(key) != expected:
            errs.append("counts.%s=%r，应为 %d" % (key, counts.get(key), expected))
    return _emit(not errs, errors=errs, decisions={k: len(v) for k, v in decided.items()})


def cmd_evidence_check(path):
    d = _load(path)
    errs = []
    included = _ids(d.get("included", []))
    claims = d.get("claims", [])
    for claim in claims:
        cid = claim.get("id", "(无 id)")
        if claim.get("claim_kind") not in {"material_fact", "inference", "unresolved"}:
            errs.append("%s claim_kind 须区分 material_fact/inference/unresolved" % cid)
        if claim.get("certainty") not in {"established", "suggestive", "disputed", "unknown"}:
            errs.append("%s certainty 非法" % cid)
        if claim.get("claim_kind") == "inference" and not _present(claim.get("inference_basis")):
            errs.append("%s 推断须写 inference_basis" % cid)
        for citation in claim.get("citations", []):
            rid = citation.get("record_id")
            if rid not in included:
                errs.append("%s 引用了未纳入或未知记录 %s" % (cid, rid))
            for key in ("location", "quote"):
                if not _present(citation.get(key)):
                    errs.append("%s/%s 缺 %s" % (cid, rid, key))
            if citation.get("support") not in {"supports", "contradicts", "context"}:
                errs.append("%s/%s support 非法" % (cid, rid))
            strength = citation.get("evidence_strength")
            if strength not in {"fulltext", "abstract_only", "indirect"}:
                errs.append("%s/%s evidence_strength 非法" % (cid, rid))
            if strength != "fulltext" and claim.get("certainty") == "established":
                errs.append("%s 仅摘要/间接证据不得标 established" % cid)
    return _emit(not errs and bool(claims), errors=errs, claims_checked=len(claims))


def cmd_grounding_check(path):
    d = _load(path)
    errs = []
    included = _ids(d.get("included", []))
    claims = {c.get("id"): c for c in d.get("claims", []) if c.get("id")}
    themes = d.get("themes", [])
    mapped, theme_names = set(), set()
    for theme in themes:
        name = theme.get("name")
        theme_names.add(name)
        evidence = set(theme.get("evidence", []))
        if not evidence or not evidence <= included:
            errs.append("主题 %s evidence 须为纳入记录 id" % name)
        if not _present(theme.get("derivation")) or not _present(theme.get("boundary")):
            errs.append("主题 %s 缺 derivation 或 boundary" % name)
        mapped |= evidence
    for claim in claims.values():
        if claim.get("theme") not in theme_names:
            errs.append("论断 %s 使用未声明主题" % claim.get("id"))
    unmapped = d.get("unmapped_records", [])
    unmapped_ids = set()
    for item in unmapped:
        rid = item.get("record_id")
        if rid not in included or not _present(item.get("reason")):
            errs.append("unmapped_records 每项须含纳入 record_id 与 reason")
        unmapped_ids.add(rid)
    if mapped & unmapped_ids:
        errs.append("同一记录不得同时 mapped 与 unmapped")
    if mapped | unmapped_ids != included:
        errs.append("纳入记录未全部进入主题或说明不归类原因")
    for left in themes:
        for right in themes:
            if left.get("name", "") >= right.get("name", ""):
                continue
            if set(left.get("evidence", [])) & set(right.get("evidence", [])):
                if not _present(left.get("overlap_note")) or not _present(right.get("overlap_note")):
                    errs.append("重叠主题 %s/%s 须写 overlap_note" % (left.get("name"), right.get("name")))
    gaps = d.get("research_gaps", [])
    for gap in gaps:
        basis = gap.get("basis_claim_ids", [])
        if not basis or any(cid not in claims for cid in basis):
            errs.append("研究空白 %s basis_claim_ids 无有效论断锚点" % gap.get("id"))
        if gap.get("gap_type") not in {"evidence_absence", "method_limit", "conflict", "search_limit"}:
            errs.append("研究空白 %s gap_type 非法" % gap.get("id"))
        if gap.get("bounded_to_search") is not True or not _present(gap.get("next_evidence")):
            errs.append("研究空白 %s 须 bounded_to_search=true 并写 next_evidence" % gap.get("id"))
    if not gaps:
        review = d.get("gap_review", {})
        if review.get("searched") is not True or not _present(review.get("note")):
            errs.append("无研究空白时须填 gap_review.searched/note")
    conflicts = d.get("conflicts", [])
    for conflict in conflicts:
        cids = conflict.get("claim_ids", [])
        if len(set(cids)) < 2 or any(cid not in claims for cid in cids):
            errs.append("冲突 %s 须关联至少两条有效 claim_ids" % conflict.get("id"))
        if conflict.get("resolution") not in {"unresolved", "explained_by_methods", "weighted"}:
            errs.append("冲突 %s resolution 非法" % conflict.get("id"))
        if not _present(conflict.get("rationale")):
            errs.append("冲突 %s 缺取舍/保留理由" % conflict.get("id"))
    if not conflicts:
        review = d.get("conflict_review", {})
        if review.get("searched") is not True or not _present(review.get("note")):
            errs.append("无冲突时须填 conflict_review.searched/note")
    return _emit(not errs, errors=errs, themes_checked=len(themes),
                 gaps_checked=len(gaps), conflicts_checked=len(conflicts))


def _sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def cmd_provenance_check(path, input_path, source_root):
    d = _load(path)
    errs = _run_errors(d)
    if not input_path or not source_root:
        return _emit(False, errors=["须提供 --input 与 --source-root"])
    actual_input = _sha256(input_path)
    if d.get("run", {}).get("input_sha256") != actual_input:
        errs.append("输入 SHA-256 不匹配")
    root = os.path.realpath(source_root)
    records = _ids(d.get("records", []))
    sources = d.get("sources", [])
    source_ids = _ids(sources, "record_id")
    if source_ids != records:
        errs.append("sources.record_id 集合须与 records 完全一致")
    checked = 0
    for source in sources:
        rid = source.get("record_id")
        rel = source.get("path")
        expected = source.get("sha256")
        if not rel or not HEX64.match(str(expected or "")):
            errs.append("来源 %s 缺 path 或合法 sha256" % rid)
            continue
        full = os.path.realpath(os.path.join(root, rel))
        if os.path.commonpath([root, full]) != root:
            errs.append("来源 %s path 越过 source-root" % rid)
            continue
        if not os.path.isfile(full):
            errs.append("来源 %s 文件不存在" % rid)
            continue
        if _sha256(full) != expected:
            errs.append("来源 %s SHA-256 不匹配" % rid)
        checked += 1
    return _emit(not errs, errors=errs, input_sha256=actual_input, sources_checked=checked)


def cmd_schema(path):
    d = _load(path)
    errs = _run_errors(d)
    for key in ("case_id", "status", "research_question", "screening_criteria", "records",
                "included", "excluded", "duplicates", "claims", "themes", "unmapped_records",
                "research_gaps", "conflicts", "counts", "gain", "unchecked", "sources",
                "uncertainty", "change_log", "run"):
        if key not in d:
            errs.append("缺顶层字段 %s" % key)
    if d.get("status") not in {"pass", "issues", "partial", "failed"}:
        errs.append("status 非法")
    counts = d.get("counts", {})
    if counts.get("included", 0) + counts.get("excluded", 0) > counts.get("records_raw", 10**9):
        errs.append("counts 矛盾: 纳入+排除 > 原始")
    return _emit(not errs, errors=errs, claims=len(d.get("claims", [])),
                 included=len(d.get("included", [])))


def _options(args):
    result = {}
    i = 0
    while i < len(args):
        if args[i] not in {"--input", "--source-root"} or i + 1 >= len(args):
            raise ValueError("provenance_check 参数应为 --input FILE --source-root DIR")
        result[args[i]] = args[i + 1]
        i += 2
    return result


def main(args):
    if not args:
        print(__doc__)
        return 2
    command = args[0]
    try:
        if command == "provenance_check":
            if len(args) < 2:
                raise ValueError("缺 result.json")
            opts = _options(args[2:])
            return cmd_provenance_check(args[1], opts.get("--input"), opts.get("--source-root"))
        if len(args) != 2:
            raise ValueError("用法：%s <result.json>" % command)
        handlers = {"cite_check": cmd_cite_check, "theme_check": cmd_theme_check,
                    "screen_check": cmd_screen_check, "evidence_check": cmd_evidence_check,
                    "grounding_check": cmd_grounding_check, "schema": cmd_schema}
        if command not in handlers:
            print(__doc__)
            return 2
        return handlers[command](args[1])
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        return _emit(False, errors=["%s: %s" % (type(exc).__name__, exc)])


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
