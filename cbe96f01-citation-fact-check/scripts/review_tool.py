#!/usr/bin/env python3
"""引用与事实核验的确定性工具；仅使用 Python 标准库。

  verify     issues.json [--text manuscript.txt]       稿件原句与重复项核验
  summary    issues.json                              六类问题计数（不等于已检查）
  locate     claims.json --manuscript m.txt --sources sources.json [--allow-partial]
                                                     稿件+引文双侧页/段定位与锚点
  align      claims.json [--allow-unknown]            支持标签与保守语义线索一致性
  provenance sources.json --registry registry.json [--allow-incomplete]
                                                     离线版本/更正/撤稿/权限核验
  coverage   result.json [--allow-partial]            六类+方法/结果/讨论覆盖闸
  schema     result.json                              向后兼容的基础检查
  gate       result.json [--allow-partial]            可复核交付严格总闸

页码/段落/occurrence 从 1 开始，换页符为 \f。locate/provenance 的 --allow-* 仅允许
诚实部分交付，不会把未解决证据变成 confirmed。退出码 0=通过，1=核验失败，2=调用错误。
"""
import hashlib
import json
import os
import re
import sys
import unicodedata

TOOL_VERSION = "3.0.0"
CATS = ["fact", "citation", "design", "statistics", "argument", "compliance"]
SECTIONS = ["methods", "results", "discussion"]
SEV = ["critical", "major", "minor"]
DEFECTS = ["fact_error", "evidence_gap", "norm_issue", "suggestion", "source_version"]
SUPPORT = ["full", "partial", "none", "unknown"]
CHECK_STATES = ["checked", "not_applicable", "pending", "unchecked"]


def _emit(obj, rc=0):
    print(json.dumps(obj, ensure_ascii=False, sort_keys=True))
    return rc


def _read_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _read_bytes(path):
    with open(path, "rb") as f:
        return f.read()


def _norm(s):
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", str(s or "")))


def _canonical(s):
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", str(s or ""))).strip()


def _quote_hash(s):
    return hashlib.sha256(_canonical(s).encode("utf-8")).hexdigest()


def _valid_hash(value):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _claims(payload):
    claims = payload.get("claims", payload) if isinstance(payload, dict) else payload
    if not isinstance(claims, list):
        raise ValueError("claims 必须为数组")
    return claims


def _issues(payload):
    issues = payload.get("issues", payload) if isinstance(payload, dict) else payload
    if not isinstance(issues, list):
        raise ValueError("issues 必须为数组")
    return issues


def cmd_verify(path, text_path=None):
    issues = _issues(_read_json(path))
    text = _norm(_read_bytes(text_path).decode("utf-8")) if text_path else None
    not_found, dup, errs = [], [], []
    seen = {}
    for i, it in enumerate(issues):
        q = _norm(it.get("quote"))
        if text is not None:
            if not q:
                errs.append("issues[%d] quote 为空" % i)
            elif q not in text:
                not_found.append({"id": it.get("id"), "quote": it.get("quote", "")[:80]})
        if it.get("quote_sha256") and it["quote_sha256"] != _quote_hash(it.get("quote")):
            errs.append("issues[%d] quote_sha256 与 quote 不匹配" % i)
        key = (_norm(it.get("location")), q)
        if key in seen:
            dup.append({"a": seen[key], "b": it.get("id"), "reason": "位置与引文完全相同"})
        else:
            seen[key] = it.get("id", "issues[%d]" % i)
    out = {"ok": not not_found and not errs, "total": len(issues),
           "quote_not_in_source": not_found, "duplicates": dup, "errors": errs}
    if text is None:
        out["note"] = "未提供 --text，仅做重复项与哈希检查，不能声称原文已定位"
    return _emit(out, 0 if out["ok"] else 1)


def cmd_summary(path):
    issues = _issues(_read_json(path))
    cat = {c: 0 for c in CATS}
    sev = {s: 0 for s in SEV}
    other = []
    for it in issues:
        c = it.get("category")
        if c in cat:
            cat[c] += 1
        elif c:
            other.append(c)
        if it.get("severity") in sev:
            sev[it["severity"]] += 1
    zero = [c for c in CATS if cat[c] == 0]
    return _emit({"ok": True, "total": len(issues), "by_category": cat, "by_severity": sev,
                  "categories_without_issues": zero, "unchecked_categories": zero,
                  "unknown_categories": sorted(set(other)),
                  "warning": "零问题不等于未检查；覆盖以 coverage 记录为准"})


def _resolve_anchor(text, quote, source_sha256, occurrence=None):
    """Return page/paragraph occurrence; repeated quote requires explicit occurrence."""
    q = _norm(quote)
    matches = []
    if q:
        for page_no, page in enumerate(text.split("\f"), 1):
            paragraphs = re.split(r"(?:\r?\n)[ \t]*(?:\r?\n)+", page)
            for para_no, para in enumerate(paragraphs, 1):
                normalized = _norm(para)
                start = 0
                while q and q in normalized[start:]:
                    local = normalized.index(q, start)
                    matches.append({"page": page_no, "paragraph": para_no,
                                    "offset_in_paragraph_normalized": local})
                    start = local + max(1, len(q))
    if not matches:
        return None, "quote_not_in_source"
    if occurrence is None:
        if len(matches) != 1:
            return {"candidates": matches}, "ambiguous_quote_occurrence"
        occurrence = 1
    if not isinstance(occurrence, int) or isinstance(occurrence, bool) or not 1 <= occurrence <= len(matches):
        return {"candidates": matches}, "invalid_occurrence"
    anchor = dict(matches[occurrence - 1])
    anchor.update({"occurrence": occurrence, "candidate_count": len(matches),
                   "quote_sha256": _quote_hash(quote), "source_sha256": source_sha256})
    return anchor, None


def _source_texts(manifest_path):
    payload = _read_json(manifest_path)
    records = payload.get("sources", payload) if isinstance(payload, dict) else payload
    if not isinstance(records, list):
        raise ValueError("sources manifest 必须为数组或含 sources 数组")
    root = os.path.dirname(os.path.abspath(manifest_path))
    result = {}
    for rec in records:
        sid = rec.get("source_id")
        if not sid:
            result["<missing>"] = (None, None, "source_id 为空")
            continue
        try:
            if "text" in rec:
                raw = str(rec["text"]).encode("utf-8")
            else:
                path = rec.get("path")
                if not path:
                    raise ValueError("缺 path/text")
                full = path if os.path.isabs(path) else os.path.join(root, path)
                raw = _read_bytes(full)
            result[sid] = (raw.decode("utf-8"), hashlib.sha256(raw).hexdigest(), None)
        except (OSError, UnicodeError, ValueError) as e:
            result[sid] = (None, None, "%s: %s" % (type(e).__name__, str(e)))
    return result


def cmd_locate(path, manuscript_path, sources_path, allow_partial=False):
    payload = _read_json(path)
    claims = _claims(payload)
    manuscript_raw = _read_bytes(manuscript_path)
    manuscript = manuscript_raw.decode("utf-8")
    manuscript_sha = hashlib.sha256(manuscript_raw).hexdigest()
    sources = _source_texts(sources_path)
    resolved, errors = [], []
    for i, claim in enumerate(claims):
        cid = claim.get("id", "claims[%d]" % i)
        claim_quote = claim.get("claim_quote", "")
        anchor, err = _resolve_anchor(manuscript, claim_quote, manuscript_sha,
                                      claim.get("claim_occurrence"))
        if err:
            errors.append({"claim_id": cid, "side": "manuscript", "error": err,
                           "candidates": anchor.get("candidates", []) if isinstance(anchor, dict) else []})
        supplied = claim.get("claim_quote_sha256")
        if supplied and supplied != _quote_hash(claim_quote):
            errors.append({"claim_id": cid, "side": "manuscript", "error": "quote_sha256_mismatch"})
        sid = claim.get("source_id")
        source_text, source_sha, source_err = sources.get(sid, (None, None, "source_not_registered"))
        source_anchor = None
        if source_err:
            errors.append({"claim_id": cid, "side": "source", "source_id": sid, "error": source_err})
        else:
            source_anchor, err = _resolve_anchor(source_text, claim.get("source_quote", ""), source_sha,
                                                 claim.get("source_occurrence"))
            if err:
                errors.append({"claim_id": cid, "side": "source", "source_id": sid, "error": err,
                               "candidates": source_anchor.get("candidates", []) if isinstance(source_anchor, dict) else []})
            supplied = claim.get("source_quote_sha256")
            if supplied and supplied != _quote_hash(claim.get("source_quote")):
                errors.append({"claim_id": cid, "side": "source", "error": "quote_sha256_mismatch"})
        resolved.append({"id": cid, "source_id": sid, "claim_anchor": anchor if not err or (anchor and "page" in anchor) else None,
                         "source_anchor": source_anchor if source_anchor and "page" in source_anchor else None})
    complete = not errors
    out = {"ok": complete or allow_partial, "complete": complete, "tool_version": TOOL_VERSION,
           "manuscript_sha256": manuscript_sha, "claims": resolved, "errors": errors,
           "status": "verified" if complete else "partial",
           "locator_rule": "重复 quote 必须显式给 claim_occurrence/source_occurrence；禁止默认取第一次"}
    return _emit(out, 0 if out["ok"] else 1)


def _has_any(text, phrases):
    lowered = unicodedata.normalize("NFKC", str(text or "")).lower()
    return any(p.lower() in lowered for p in phrases)


def _sample_numbers(text):
    s = unicodedata.normalize("NFKC", str(text or ""))
    patterns = [r"\bn\s*=\s*(\d+)", r"(?:样本量|样本|纳入|共入选)\s*(?:为|是|共)?\s*(\d+)",
                r"(\d+)\s*(?:例|名|个受试者|patients|participants|subjects)(?![A-Za-z])"]
    values = set()
    for pattern in patterns:
        values.update(int(x) for x in re.findall(pattern, s, flags=re.I))
    return values


def _semantic_conflicts(claim):
    if claim.get("support") != "full":
        return []
    c, s = claim.get("claim_quote", ""), claim.get("source_quote", "")
    flags = []
    negative_source = ["no significant", "not significant", "no evidence", "did not", "failed to",
                       "无显著", "未见显著", "没有证据", "未发现", "不能证明", "无效"]
    positive_claim = ["effective", "significant", "demonstrate", "prove", "improve", "有效", "显著", "证明", "改善"]
    if _has_any(s, negative_source) and _has_any(c, positive_claim) and not _has_any(c, negative_source + ["不", "未"]):
        flags.append({"type": "direction_conflict", "detail": "来源含否定/无效应，稿件为肯定且 support=full"})
    universal = ["all patients", "every patient", "always", "universally", "cure", "所有患者", "所有", "任何", "必然", "完全有效", "治愈"]
    limited = ["some", "may", "might", "associated", "pilot", "preliminary", "subgroup", "部分", "可能", "相关", "初步", "亚组", "小样本"]
    if _has_any(c, universal) and _has_any(s, limited):
        flags.append({"type": "scope_overreach", "detail": "稿件全称/治愈结论超出受限来源且 support=full"})
    causal = ["causes", "caused by", "leads to", "prove", "导致", "因果", "证明"]
    associational = ["associated", "correlated", "association", "相关", "关联"]
    causal_design = ["randomized", "randomised", "causal", "随机", "工具变量", "自然实验"]
    if _has_any(c, causal) and _has_any(s, associational) and not _has_any(s, causal_design):
        flags.append({"type": "causal_overreach", "detail": "相关来源被标为完整支持因果结论"})
    c_nums, s_nums = _sample_numbers(c), _sample_numbers(s)
    if len(c_nums) == 1 and len(s_nums) == 1 and c_nums != s_nums:
        flags.append({"type": "sample_size_mismatch", "detail": "显式样本量不同且 support=full",
                      "claim_n": sorted(c_nums), "source_n": sorted(s_nums)})
    return flags


def cmd_align(path, allow_unknown=False):
    claims = _claims(_read_json(path))
    missing, mismatches, needs_review = [], [], []
    for i, claim in enumerate(claims):
        cid = claim.get("id", "claims[%d]" % i)
        for key in ("id", "source_id", "claim_quote", "source_quote", "support", "support_rationale"):
            if not str(claim.get(key, "")).strip():
                missing.append({"claim_id": cid, "field": key})
        if claim.get("support") not in SUPPORT:
            missing.append({"claim_id": cid, "field": "support_enum"})
        if claim.get("support") == "unknown":
            needs_review.append(cid)
        for flag in _semantic_conflicts(claim):
            mismatches.append(dict(flag, claim_id=cid))
    ok = not missing and not mismatches and (allow_unknown or not needs_review)
    return _emit({"ok": ok, "complete": not needs_review and not missing and not mismatches,
                  "total": len(claims), "missing_fields": missing,
                  "support_label_mismatches": mismatches, "needs_review": needs_review,
                  "boundary": "只拦截保守的方向/范围/因果/显式样本量矛盾；通过不等于完整语义蕴含证明"},
                 0 if ok else 1)


def cmd_provenance(path, registry_path, allow_incomplete=False):
    payload = _read_json(path)
    records = payload.get("sources", payload) if isinstance(payload, dict) else payload
    registry = _read_json(registry_path)
    if isinstance(registry, dict) and "sources" in registry:
        registry = registry["sources"]
    if not isinstance(records, list) or not isinstance(registry, dict):
        raise ValueError("sources 必须为数组，registry 必须是以 source_id 为键的对象")
    results, blocking, incomplete = [], [], []
    for i, src in enumerate(records):
        sid = src.get("source_id", "sources[%d]" % i)
        errors, warnings = [], []
        if src.get("role", "reference") != "reference":
            results.append({"source_id": sid, "status": "not_applicable", "errors": [], "warnings": []})
            continue
        for key in ("version", "publication_status", "retraction_status", "checked_at", "evidence_url", "access"):
            if not str(src.get(key, "")).strip():
                errors.append("missing_" + key)
        if not (src.get("doi") or src.get("url")):
            errors.append("missing_doi_or_url")
        reg = registry.get(sid)
        if not isinstance(reg, dict):
            errors.append("registry_record_unavailable")
            reg = {}
        if reg:
            if src.get("doi") and reg.get("canonical_doi") and src["doi"].lower() != reg["canonical_doi"].lower():
                errors.append("identifier_mismatch")
            if src.get("version") and reg.get("current_version") and src["version"] != reg["current_version"]:
                if src.get("version_difference_disclosed"):
                    warnings.append("version_difference_disclosed")
                else:
                    errors.append("version_mismatch")
            if src.get("publication_status") and reg.get("publication_status") and src["publication_status"] != reg["publication_status"]:
                if src.get("version_difference_disclosed"):
                    warnings.append("publication_status_difference_disclosed")
                else:
                    errors.append("publication_status_mismatch")
            registry_status = reg.get("retraction_status", "unknown")
            if registry_status == "retracted" or src.get("retraction_status") == "retracted":
                errors.append("retracted_source")
            if registry_status in {"corrected", "expression_of_concern"}:
                warnings.append(registry_status)
            if registry_status == "unknown" or src.get("retraction_status") == "unknown":
                warnings.append("retraction_status_unknown")
                incomplete.append(sid)
            if (src.get("retraction_status") not in {None, "unknown", registry_status}
                    and registry_status != "retracted"):
                errors.append("retraction_status_mismatch")
        if src.get("access") in {"paywalled", "permission_denied", "unavailable"}:
            warnings.append("full_text_" + str(src.get("access")))
            incomplete.append(sid)
        blocking.extend({"source_id": sid, "reason": e} for e in errors)
        status = "retracted" if "retracted_source" in errors else ("needs_review" if errors else "checked")
        results.append({"source_id": sid, "status": status, "errors": errors, "warnings": warnings,
                        "registry_evidence": reg.get("evidence_url")})
    ok = not blocking and (allow_incomplete or not incomplete)
    return _emit({"ok": ok, "complete": not blocking and not incomplete, "sources": results,
                  "blocking": blocking, "incomplete_sources": sorted(set(incomplete)),
                  "boundary": "registry 是带来的离线快照；输出仅声称该快照状态，不冒充实时数据库核验"},
                 0 if ok else 1)


def _coverage_errors(d):
    errs, incomplete = [], []
    for group, required in (("categories", CATS), ("sections", SECTIONS)):
        records = d.get(group)
        if not isinstance(records, dict):
            errs.append("缺 %s 对象" % group)
            continue
        for name in required:
            rec = records.get(name)
            if not isinstance(rec, dict):
                errs.append("%s.%s 缺检查记录" % (group, name))
                continue
            state = rec.get("status")
            if state not in CHECK_STATES:
                errs.append("%s.%s.status 非法" % (group, name))
            if state in {"pending", "unchecked"}:
                incomplete.append("%s.%s" % (group, name))
            if state == "checked" and not str(rec.get("notes", "")).strip():
                errs.append("%s.%s checked 时必须写 notes" % (group, name))
            if state != "checked" and not str(rec.get("reason", "")).strip():
                errs.append("%s.%s 非 checked 时必须写 reason" % (group, name))
    return errs, incomplete


def cmd_coverage(path, allow_partial=False):
    d = _read_json(path)
    errs, incomplete = _coverage_errors(d)
    if incomplete and not allow_partial:
        errs.append("仍有未完成范围: " + ", ".join(incomplete))
    return _emit({"ok": not errs, "errors": errs, "incomplete": incomplete,
                  "rule": "六类和方法/结果/讨论均显式记录；零 issue 不等于未检查"}, 0 if not errs else 1)


def _anchor_errors(anchor, prefix, quote):
    errs = []
    if not isinstance(anchor, dict):
        return [prefix + " 必须为定位对象"]
    if not isinstance(anchor.get("page"), int) or anchor.get("page", 0) < 1:
        errs.append(prefix + " 缺从1开始的 page")
    paragraph = anchor.get("paragraph")
    if not ((isinstance(paragraph, int) and not isinstance(paragraph, bool) and paragraph >= 1)
            or (isinstance(paragraph, str) and paragraph.strip())):
        errs.append(prefix + " 缺 paragraph/entry")
    if not _valid_hash(anchor.get("quote_sha256")):
        errs.append(prefix + " 缺有效 quote_sha256")
    elif anchor["quote_sha256"] != _quote_hash(quote):
        errs.append(prefix + " quote_sha256 与 quote 不匹配")
    if not _valid_hash(anchor.get("source_sha256")):
        errs.append(prefix + " 缺来源全文 source_sha256")
    return errs


def cmd_schema(path):
    d = _read_json(path)
    if not isinstance(d, dict):
        return _emit({"ok": False, "errors": ["顶层必须是对象"]}, 1)
    errs = []
    for key in ("case_id", "status", "manuscript_version", "issues", "checked_scope",
                "gain", "unchecked", "sources", "uncertainty", "change_log"):
        if key not in d:
            errs.append("缺顶层字段 " + key)
    if d.get("status") not in {"pass", "issues", "partial", "failed"}:
        errs.append("status 非法")
    if not d.get("manuscript_version"):
        errs.append("manuscript_version 为空")
    for i, issue in enumerate(d.get("issues", [])):
        for key in ("id", "category", "severity", "location", "quote", "claim", "fix"):
            if key not in issue:
                errs.append("issues[%d] 缺 %s" % (i, key))
        if issue.get("category") not in CATS:
            errs.append("issues[%d] category 非法" % i)
        if issue.get("severity") not in SEV:
            errs.append("issues[%d] severity 非法" % i)
    return _emit({"ok": not errs, "errors": errs, "issues": len(d.get("issues", []))}, 0 if not errs else 1)


def cmd_gate(path, allow_partial=False):
    d = _read_json(path)
    if not isinstance(d, dict):
        return _emit({"ok": False, "errors": ["顶层必须是对象"]}, 1)
    errs = []
    for key in ("schema_version", "case_id", "status", "manuscript_version", "run", "contract",
                "claims", "issues", "sources", "checked_scope", "gain", "unchecked", "uncertainty", "change_log"):
        if key not in d:
            errs.append("缺顶层字段 " + key)
    if d.get("schema_version") != "3.0":
        errs.append("schema_version 必须为 3.0")
    if d.get("status") not in {"pass", "issues", "partial", "failed"}:
        errs.append("status 非法")
    version = d.get("manuscript_version", {})
    if not isinstance(version, dict) or not _valid_hash(version.get("sha256")) or not version.get("files"):
        errs.append("manuscript_version 必须含 files 与有效 sha256")
    run = d.get("run", {})
    if not isinstance(run, dict) or run.get("tool_version") != TOOL_VERSION or not run.get("run_id"):
        errs.append("run 必须含实际 run_id 与 tool_version=%s" % TOOL_VERSION)
    contract = d.get("contract", {})
    if not isinstance(contract, dict) or not contract.get("source") or "preserved_fields" not in contract:
        errs.append("contract 必须记录原始 output_contract 来源及 preserved_fields")
    _, incomplete = _coverage_errors(d)
    coverage_errs, _ = _coverage_errors(d)
    errs.extend(coverage_errs)
    if incomplete and not (allow_partial or d.get("status") == "partial"):
        errs.append("非 partial 交付仍有 incomplete: " + ", ".join(incomplete))
    sources = d.get("sources", [])
    source_records, source_ids, retracted, unknown_status = {}, set(), set(), set()
    for i, src in enumerate(sources if isinstance(sources, list) else []):
        if not isinstance(src, dict) or not src.get("source_id") or not _valid_hash(src.get("sha256")):
            errs.append("sources[%d] 必须含 source_id 和内容 sha256" % i)
            continue
        sid = src["source_id"]
        source_ids.add(sid)
        source_records[sid] = src
        role = src.get("role", "reference")
        if role == "reference":
            for key in ("version", "publication_status", "retraction_status", "checked_at", "evidence_url", "access"):
                if not str(src.get(key, "")).strip():
                    errs.append("sources[%d].%s 为空" % (i, key))
            if not (src.get("doi") or src.get("url")):
                errs.append("sources[%d] 缺 doi/url" % i)
        if src.get("retraction_status") == "retracted":
            retracted.add(sid)
        if src.get("retraction_status") == "unknown" or src.get("access") in {"paywalled", "permission_denied", "unavailable"}:
            unknown_status.add(sid)
    claims = d.get("claims", [])
    if not isinstance(claims, list):
        errs.append("claims 必须为数组")
        claims = []
    claim_ids, needs_review = set(), []
    for i, claim in enumerate(claims):
        p = "claims[%d]" % i
        if not isinstance(claim, dict):
            errs.append(p + " 必须为对象")
            continue
        for key in ("id", "source_id", "claim_quote", "claim_locator", "source_quote",
                    "source_locator", "support", "support_rationale"):
            if key not in claim:
                errs.append(p + " 缺 " + key)
        cid = claim.get("id")
        if cid in claim_ids:
            errs.append(p + " id 重复")
        claim_ids.add(cid)
        if claim.get("source_id") not in source_ids:
            errs.append(p + ".source_id 未注册")
        if claim.get("support") not in SUPPORT:
            errs.append(p + ".support 非法")
        if claim.get("support") == "unknown":
            needs_review.append(cid)
        if not str(claim.get("support_rationale", "")).strip():
            errs.append(p + ".support_rationale 为空")
        errs.extend(_anchor_errors(claim.get("claim_locator"), p + ".claim_locator", claim.get("claim_quote")))
        errs.extend(_anchor_errors(claim.get("source_locator"), p + ".source_locator", claim.get("source_quote")))
        claim_anchor = claim.get("claim_locator", {})
        if isinstance(claim_anchor, dict) and claim_anchor.get("source_sha256") != version.get("sha256"):
            errs.append(p + ".claim_locator.source_sha256 与 manuscript_version 不一致")
        source_anchor = claim.get("source_locator", {})
        registered = source_records.get(claim.get("source_id"), {})
        if isinstance(source_anchor, dict) and source_anchor.get("source_sha256") != registered.get("sha256"):
            errs.append(p + ".source_locator.source_sha256 与注册来源全文哈希不一致")
    issues = d.get("issues", [])
    issue_claims, issue_sources, pending_ids = set(), set(), []
    for i, issue in enumerate(issues if isinstance(issues, list) else []):
        p = "issues[%d]" % i
        for key in ("id", "category", "severity", "defect_type", "review_status", "location", "quote",
                    "claim", "fix", "evidence", "claim_id"):
            if key not in issue:
                errs.append(p + " 缺 " + key)
        if issue.get("category") not in CATS:
            errs.append(p + " category 非法")
        if issue.get("severity") not in SEV:
            errs.append(p + " severity 非法")
        if issue.get("defect_type") not in DEFECTS:
            errs.append(p + " defect_type 非法")
        if issue.get("defect_type") == "suggestion" and issue.get("severity") != "minor":
            errs.append(p + " suggestion 只能为 minor")
        if issue.get("review_status") not in {"confirmed", "pending"}:
            errs.append(p + " review_status 非法")
        if issue.get("review_status") == "pending":
            pending_ids.append(issue.get("id"))
        if issue.get("claim_id"):
            issue_claims.add(issue["claim_id"])
            if issue["claim_id"] not in claim_ids:
                errs.append(p + ".claim_id 未注册")
        if issue.get("source_id"):
            issue_sources.add(issue["source_id"])
        errs.extend(_anchor_errors(issue.get("location"), p + ".location", issue.get("quote")))
        issue_anchor = issue.get("location", {})
        if isinstance(issue_anchor, dict) and issue_anchor.get("source_sha256") != version.get("sha256"):
            errs.append(p + ".location.source_sha256 与 manuscript_version 不一致")
        evidence = issue.get("evidence")
        if not isinstance(evidence, list) or not evidence:
            errs.append(p + ".evidence 至少一条")
            evidence = []
        for j, ev in enumerate(evidence):
            ep = "%s.evidence[%d]" % (p, j)
            if ev.get("source_id") not in source_ids:
                errs.append(ep + ".source_id 未注册")
            if not str(ev.get("basis", "")).strip():
                errs.append(ep + ".basis 为空")
            errs.extend(_anchor_errors(ev.get("locator"), ep + ".locator", ev.get("quote")))
            ev_anchor = ev.get("locator", {})
            ev_source = source_records.get(ev.get("source_id"), {})
            if isinstance(ev_anchor, dict) and ev_anchor.get("source_sha256") != ev_source.get("sha256"):
                errs.append(ep + ".locator.source_sha256 与注册来源全文哈希不一致")
    for claim in claims:
        if claim.get("support") in {"partial", "none"} and claim.get("id") not in issue_claims:
            errs.append("claims.%s 为 %s 但没有关联 issue" % (claim.get("id"), claim.get("support")))
    for sid in sorted(retracted):
        if sid not in issue_sources:
            errs.append("撤稿来源 %s 没有带 source_id 的关联 issue" % sid)
    if (needs_review or pending_ids or unknown_status) and not d.get("uncertainty"):
        errs.append("unknown claim/source、权限受限来源或 pending issue 必须写入 uncertainty")
    if d.get("status") == "pass" and issues:
        errs.append("pass 状态不能含 issues")
    if d.get("status") == "issues" and not issues:
        errs.append("issues 状态至少一条 issue；无问题应使用 pass")
    if d.get("status") == "partial" and not (d.get("unchecked") or d.get("uncertainty") or incomplete):
        errs.append("partial 必须说明 unchecked/uncertainty/incomplete")
    if d.get("status") == "failed" and not str(d.get("error", "")).strip():
        errs.append("failed 必须给 error")
    return _emit({"ok": not errs, "errors": errs, "claims": len(claims), "issues": len(issues),
                  "incomplete": incomplete, "tool_version": TOOL_VERSION}, 0 if not errs else 1)


def main(argv):
    if not argv:
        print(__doc__)
        return 2
    cmd = argv[0]
    try:
        if cmd == "verify":
            return cmd_verify(argv[1], argv[argv.index("--text") + 1] if "--text" in argv else None)
        if cmd == "summary":
            return cmd_summary(argv[1])
        if cmd == "schema":
            return cmd_schema(argv[1])
        if cmd == "locate":
            return cmd_locate(argv[1], argv[argv.index("--manuscript") + 1],
                              argv[argv.index("--sources") + 1], "--allow-partial" in argv)
        if cmd == "align":
            return cmd_align(argv[1], "--allow-unknown" in argv)
        if cmd == "provenance":
            return cmd_provenance(argv[1], argv[argv.index("--registry") + 1],
                                  "--allow-incomplete" in argv)
        if cmd == "coverage":
            return cmd_coverage(argv[1], "--allow-partial" in argv)
        if cmd == "gate":
            return cmd_gate(argv[1], "--allow-partial" in argv)
    except (IndexError, OSError, ValueError, TypeError, KeyError, UnicodeError, json.JSONDecodeError) as e:
        return _emit({"ok": False, "error": "%s: %s" % (type(e).__name__, str(e))}, 2)
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
