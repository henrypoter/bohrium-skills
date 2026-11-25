#!/usr/bin/env python3
"""研究方法与统计审查的确定性闸门；仅使用 Python 标准库。

  verify    issues.json [--text manuscript.txt]       原句与重复项核验
  summary   issues.json                              六类问题的数量（不等于已检查）
  preflight --text manuscript.txt [--manifest m.json] 输入完整性/语言/版本预检
  coverage  result.json [--allow-partial]             五检查面+六类目显式覆盖闸
  statcheck stats.json                               p-CI、z-p、样本流一致性
  schema    result.json                              向后兼容的基础字段检查
  gate      result.json [--allow-partial]             可复核交付的严格总闸

所有定位从 1 开始；原文按换页符 \f 分页。coverage/statcheck 只检查模型提取的
结构化记录，不会把“未报告”自动判成“做错”。退出码 0=通过，1=审查失败，2=调用错误。
"""
import hashlib
import json
import math
import re
import sys
import unicodedata
from statistics import NormalDist

TOOL_VERSION = "3.0.0"
CATS = ["fact", "citation", "design", "statistics", "argument", "compliance"]
FACETS = ["design", "variables", "statistics", "sample_size", "reporting"]
SEV = ["critical", "major", "minor"]
DEFECTS = ["fact_error", "evidence_gap", "norm_issue", "suggestion"]
CHECK_STATES = ["checked", "not_applicable", "pending", "unchecked"]


def _emit(obj, rc=0):
    print(json.dumps(obj, ensure_ascii=False, sort_keys=True))
    return rc


def _read_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _norm(s):
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", str(s or "")))


def _quote_hash(s):
    canonical = re.sub(r"\s+", " ", unicodedata.normalize("NFKC", str(s or ""))).strip()
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _load_issues(path):
    d = _read_json(path)
    issues = d.get("issues", d) if isinstance(d, dict) else d
    if not isinstance(issues, list):
        raise ValueError("issues 必须是数组")
    return issues


def cmd_verify(path, text_path=None):
    issues = _load_issues(path)
    text = None
    if text_path:
        text = _norm(open(text_path, "r", encoding="utf-8", errors="strict").read())
    not_found, dup, errs = [], [], []
    seen = {}
    for i, it in enumerate(issues):
        q = _norm(it.get("quote"))
        if text is not None:
            if not q:
                errs.append("issues[%d] quote 为空，无法核验" % i)
            elif q not in text:
                not_found.append({"id": it.get("id"), "quote": it.get("quote", "")[:80]})
        supplied_hash = it.get("quote_sha256")
        if supplied_hash and supplied_hash != _quote_hash(it.get("quote")):
            errs.append("issues[%d] quote_sha256 与 quote 不匹配" % i)
        key = (_norm(it.get("location")), q)
        if key in seen:
            dup.append({"a": seen[key], "b": it.get("id"), "reason": "位置与引文完全相同"})
        else:
            seen[key] = it.get("id", "issues[%d]" % i)
    out = {"ok": not not_found and not errs, "total": len(issues),
           "quote_not_in_source": not_found, "duplicates": dup, "errors": errs}
    if text is None:
        out["note"] = "未提供 --text，仅做重复项与哈希核验；不能声称原文定位已验证"
    return _emit(out, 0 if out["ok"] else 1)


def cmd_summary(path):
    issues = _load_issues(path)
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
    zero_issue = [c for c in CATS if cat[c] == 0]
    return _emit({"ok": True, "total": len(issues), "by_category": cat,
                  "by_severity": sev, "categories_without_issues": zero_issue,
                  "unchecked_categories": zero_issue,
                  "warning": "零问题不等于未检查；最终覆盖以 coverage 的 categories/facets 为准",
                  "unknown_categories": sorted(set(other))})


def cmd_preflight(text_path, manifest_path=None):
    raw = open(text_path, "rb").read()
    text = raw.decode("utf-8", errors="replace")
    manifest = _read_json(manifest_path) if manifest_path else {}
    pages = text.split("\f")
    if pages and pages[-1] == "":
        pages.pop()
    expected = manifest.get("expected_pages", [])
    present = set(range(1, len(pages) + 1))
    missing = sorted(set(expected) - present)
    replacement = text.count("\ufffd")
    nul = text.count("\x00")
    visible = max(1, sum(not ch.isspace() for ch in text))
    bad_ratio = (replacement + nul) / visible
    cjk = len(re.findall(r"[\u3400-\u9fff]", text))
    latin_words = len(re.findall(r"[A-Za-z]{2,}", text))
    if not text.strip():
        language = "empty"
    elif cjk >= 20 and latin_words >= 20:
        language = "mixed"
    elif cjk > latin_words:
        language = "zh"
    elif latin_words:
        language = "en"
    else:
        language = "other"
    blockers, warnings = [], []
    usable_text = re.search(r"[A-Za-z0-9\u3400-\u9fff]", text) is not None
    if not text.strip():
        blockers.append("empty_text")
    if not usable_text:
        blockers.append("no_usable_text")
    if bad_ratio > 0.02:
        blockers.append("excessive_decode_errors")
    if missing:
        blockers.append("missing_pages")
    unreadable = manifest.get("unreadable_pages", [])
    if unreadable:
        blockers.append("unreadable_pages")
    for key in ("unresolved_figures", "missing_statistical_outputs", "missing_materials"):
        if manifest.get(key):
            warnings.append(key)
    if language == "mixed":
        warnings.append("mixed_language")
    status = "failed" if not usable_text else ("partial" if blockers or warnings else "ready")
    out = {"ok": not blockers, "status": status, "text_sha256": hashlib.sha256(raw).hexdigest(),
           "char_count": len(text), "detected_pages": len(pages), "expected_pages": expected,
           "missing_pages": missing, "unreadable_pages": unreadable,
           "decode_error_ratio": round(bad_ratio, 6), "language_profile": {
               "class": language, "cjk_chars": cjk, "latin_words": latin_words},
           "unresolved_figures": manifest.get("unresolved_figures", []),
           "missing_statistical_outputs": manifest.get("missing_statistical_outputs", []),
           "missing_materials": manifest.get("missing_materials", []),
           "blockers": blockers, "warnings": warnings,
           "next_action": "仅将受影响页面/图表/统计面标 pending；不得据缺失材料下确定结论" if status != "ready" else "可进入五面审查"}
    return _emit(out, 0 if out["ok"] else 1)


def _coverage_errors(d):
    errs, incomplete = [], []
    for group, required in (("facets", FACETS), ("categories", CATS)):
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
            if state in ("pending", "unchecked"):
                incomplete.append("%s.%s" % (group, name))
            if state != "checked" and not str(rec.get("reason", "")).strip():
                errs.append("%s.%s 非 checked 时必须给 reason" % (group, name))
            if state == "checked" and not str(rec.get("notes", "")).strip():
                errs.append("%s.%s checked 时必须给 notes（查了什么）" % (group, name))
    return errs, incomplete


def cmd_coverage(path, allow_partial=False):
    d = _read_json(path)
    errs, incomplete = _coverage_errors(d)
    if incomplete and not allow_partial:
        errs.append("仍有未完成检查面: " + ", ".join(incomplete))
    out = {"ok": not errs, "errors": errs, "incomplete": incomplete,
           "facets": FACETS, "categories": CATS,
           "rule": "逐面记录 checked/not_applicable；零 issue 不能替代检查记录"}
    return _emit(out, 0 if out["ok"] else 1)


def _p_value(value):
    if isinstance(value, bool):
        raise ValueError("布尔值不是 p 值")
    if isinstance(value, (int, float)):
        return float(value), "exact"
    m = re.fullmatch(r"\s*([<>]=?)\s*([0-9]*\.?[0-9]+)\s*", str(value))
    if not m:
        raise ValueError("p 必须为数值或 <0.001 形式")
    return float(m.group(2)), m.group(1)


def _stat_row(row, default_alpha):
    rid = row.get("id", "<missing>")
    errs = []
    exact_p = None
    p_kind = None
    if "p" in row:
        try:
            exact_p, p_kind = _p_value(row["p"])
            if not 0 <= exact_p <= 1:
                errs.append("p 超出 [0,1]")
        except (ValueError, TypeError) as e:
            errs.append(str(e))
    alpha = float(row.get("alpha", default_alpha))
    if not 0 < alpha < 1:
        errs.append("alpha 必须在 (0,1)")
    if exact_p is not None and "z" in row:
        if p_kind != "exact":
            errs.append("z-p 复算要求精确数值 p")
        else:
            try:
                z = float(row["z"])
                calculated = 2 * (1 - NormalDist().cdf(abs(z)))
                tolerance = float(row.get("tolerance", max(0.0005, calculated * 0.02)))
                if abs(calculated - exact_p) > tolerance:
                    errs.append("z-p 不一致: calculated=%.8g tolerance=%.8g" % (calculated, tolerance))
            except (ValueError, TypeError):
                errs.append("z 或 tolerance 非法")
    if "df" in row and (not isinstance(row["df"], int) or isinstance(row["df"], bool) or row["df"] <= 0):
        errs.append("df 必须为正整数")
    lo, hi = row.get("ci_low"), row.get("ci_high")
    if (lo is None) != (hi is None):
        errs.append("置信区间必须同时给 ci_low/ci_high")
    if lo is not None and hi is not None:
        try:
            lo, hi = float(lo), float(hi)
            if not math.isfinite(lo) or not math.isfinite(hi) or lo > hi:
                errs.append("置信区间端点非法")
            null = float(row.get("null", 1.0 if row.get("scale") == "ratio" else 0.0))
            if exact_p is not None and p_kind in ("exact", "<", "<=") and not errs:
                significant = exact_p < alpha
                ci_excludes = lo > null or hi < null
                if significant != ci_excludes:
                    errs.append("p 与 CI 对 alpha=%g 的双侧显著性方向冲突" % alpha)
        except (ValueError, TypeError):
            errs.append("置信区间或 null 必须为数值")
    keys = ("n_enrolled", "n_excluded", "n_analyzed")
    if all(k in row for k in keys):
        try:
            enrolled, excluded, analyzed = (int(row[k]) for k in keys)
            if min(enrolled, excluded, analyzed) < 0:
                errs.append("样本量不能为负")
            elif enrolled - excluded != analyzed and not row.get("accounting_incomplete", False):
                errs.append("样本流不守恒: n_enrolled-n_excluded != n_analyzed")
        except (ValueError, TypeError):
            errs.append("样本量必须为整数")
    return {"id": rid, "errors": errs}


def cmd_statcheck(path, alpha=0.05):
    payload = _read_json(path)
    rows = payload.get("statistics", payload) if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        raise ValueError("statcheck 输入必须是数组或含 statistics 数组")
    results = [_stat_row(row, alpha) for row in rows]
    failures = [r for r in results if r["errors"]]
    return _emit({"ok": not failures, "total": len(results), "failed": len(failures),
                  "results": results, "boundary": "p-CI 只做双侧一致性检查；特殊区间/单尾检验须标 pending 人工复核"},
                 0 if not failures else 1)


def _valid_hash(value):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _anchor_errors(anchor, prefix, quote):
    errs = []
    if not isinstance(anchor, dict):
        return [prefix + " 必须为定位对象"]
    if not str(anchor.get("section", anchor.get("table", anchor.get("figure", "")))).strip():
        errs.append(prefix + " 缺 section/table/figure")
    if not any(k in anchor for k in ("page", "paragraph", "table", "figure", "item")):
        errs.append(prefix + " 缺细粒度定位 page/paragraph/table/figure/item")
    if not _valid_hash(anchor.get("quote_sha256")):
        errs.append(prefix + " 缺有效 quote_sha256")
    elif anchor["quote_sha256"] != _quote_hash(quote):
        errs.append(prefix + " quote_sha256 与 quote 不匹配")
    return errs


def cmd_schema(path):
    d = _read_json(path)
    if not isinstance(d, dict):
        return _emit({"ok": False, "errors": ["顶层必须是对象"]}, 1)
    errs = []
    for k in ("case_id", "status", "manuscript_version", "issues", "checked_scope",
              "gain", "unchecked", "sources", "uncertainty", "change_log"):
        if k not in d:
            errs.append("缺顶层字段 %s" % k)
    if d.get("status") not in {"pass", "issues", "partial", "failed"}:
        errs.append("status 非法")
    if not d.get("manuscript_version"):
        errs.append("manuscript_version 为空")
    for i, it in enumerate(d.get("issues", [])):
        for k in ("id", "category", "severity", "location", "quote", "claim", "fix"):
            if k not in it:
                errs.append("issues[%d] 缺 %s" % (i, k))
        if it.get("category") not in CATS:
            errs.append("issues[%d] category 非法" % i)
        if it.get("severity") not in SEV:
            errs.append("issues[%d] severity 非法" % i)
    return _emit({"ok": not errs, "errors": errs, "issues": len(d.get("issues", []))}, 0 if not errs else 1)


def cmd_gate(path, allow_partial=False):
    d = _read_json(path)
    errs = [] if isinstance(d, dict) else ["顶层必须是对象"]
    if errs:
        return _emit({"ok": False, "errors": errs}, 1)
    for k in ("schema_version", "case_id", "status", "manuscript_version", "run", "contract",
              "issues", "sources", "checked_scope", "gain", "unchecked", "uncertainty", "change_log"):
        if k not in d:
            errs.append("缺顶层字段 %s" % k)
    if d.get("schema_version") != "3.0":
        errs.append("schema_version 必须为 3.0")
    if d.get("status") not in {"pass", "issues", "partial", "failed"}:
        errs.append("status 非法")
    version = d.get("manuscript_version", {})
    if not isinstance(version, dict) or not _valid_hash(version.get("sha256")):
        errs.append("manuscript_version.sha256 必须为 64 位小写 sha256")
    if not isinstance(version, dict) or not version.get("files"):
        errs.append("manuscript_version.files 不能为空")
    run = d.get("run", {})
    if not isinstance(run, dict) or run.get("tool_version") != TOOL_VERSION or not run.get("run_id"):
        errs.append("run 必须含实际 run_id 与 tool_version=%s" % TOOL_VERSION)
    contract = d.get("contract", {})
    if not isinstance(contract, dict) or not contract.get("source") or "preserved_fields" not in contract:
        errs.append("contract 必须记录原始 output_contract 来源及 preserved_fields")
    errs.extend(_coverage_errors(d)[0])
    coverage_errs, incomplete = _coverage_errors(d)
    if incomplete and not (allow_partial or d.get("status") == "partial"):
        errs.append("非 partial 交付仍有 incomplete: " + ", ".join(incomplete))
    source_ids = set()
    for i, src in enumerate(d.get("sources", [])):
        if not isinstance(src, dict) or not src.get("source_id") or not _valid_hash(src.get("sha256")):
            errs.append("sources[%d] 必须含 source_id 与内容 sha256" % i)
        else:
            source_ids.add(src["source_id"])
    pending_ids = []
    issue_ids = set()
    issues = d.get("issues", [])
    if not isinstance(issues, list):
        errs.append("issues 必须为数组")
        issues = []
    for i, it in enumerate(issues):
        p = "issues[%d]" % i
        if not isinstance(it, dict):
            errs.append(p + " 必须为对象")
            continue
        for k in ("id", "category", "facet", "severity", "defect_type", "review_status",
                  "location", "quote", "claim", "fix", "evidence"):
            if k not in it:
                errs.append(p + " 缺 " + k)
        if it.get("id") in issue_ids:
            errs.append(p + " id 重复")
        issue_ids.add(it.get("id"))
        if it.get("category") not in CATS:
            errs.append(p + " category 非法")
        if it.get("facet") not in FACETS:
            errs.append(p + " facet 非法")
        if it.get("severity") not in SEV:
            errs.append(p + " severity 非法")
        if it.get("defect_type") not in DEFECTS:
            errs.append(p + " defect_type 非法")
        if it.get("defect_type") == "suggestion" and it.get("severity") != "minor":
            errs.append(p + " suggestion 只能为 minor，不能放大为硬伤")
        if it.get("review_status") not in {"confirmed", "pending"}:
            errs.append(p + " review_status 非法")
        if it.get("review_status") == "pending":
            pending_ids.append(it.get("id"))
        errs.extend(_anchor_errors(it.get("location"), p + ".location", it.get("quote")))
        evidence = it.get("evidence")
        if not isinstance(evidence, list) or not evidence:
            errs.append(p + ".evidence 至少一条")
            evidence = []
        for j, ev in enumerate(evidence):
            ep = "%s.evidence[%d]" % (p, j)
            if not isinstance(ev, dict):
                errs.append(ep + " 必须为对象")
                continue
            if ev.get("source_id") not in source_ids:
                errs.append(ep + ".source_id 未在 sources 注册")
            if not str(ev.get("basis", "")).strip():
                errs.append(ep + ".basis 为空")
            errs.extend(_anchor_errors(ev.get("locator"), ep + ".locator", ev.get("quote")))
    if d.get("status") == "pass" and issues:
        errs.append("pass 状态不能含 issues")
    if d.get("status") == "issues" and not issues:
        errs.append("issues 状态至少一条 issue；无问题应使用 pass")
    if d.get("status") == "partial" and not (d.get("unchecked") or d.get("uncertainty") or incomplete):
        errs.append("partial 必须说明 unchecked/uncertainty/incomplete")
    if pending_ids and not d.get("uncertainty"):
        errs.append("pending issue 必须在 uncertainty 中记录")
    if d.get("status") == "failed" and not str(d.get("error", "")).strip():
        errs.append("failed 必须给 error；不得以空 issues 代替失败原因")
    out = {"ok": not errs, "errors": errs, "issues": len(issues), "incomplete": incomplete,
           "tool_version": TOOL_VERSION}
    return _emit(out, 0 if not errs else 1)


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
        if cmd == "preflight":
            return cmd_preflight(argv[argv.index("--text") + 1],
                                 argv[argv.index("--manifest") + 1] if "--manifest" in argv else None)
        if cmd == "coverage":
            return cmd_coverage(argv[1], "--allow-partial" in argv)
        if cmd == "statcheck":
            return cmd_statcheck(argv[1])
        if cmd == "gate":
            return cmd_gate(argv[1], "--allow-partial" in argv)
    except (IndexError, OSError, ValueError, TypeError, json.JSONDecodeError) as e:
        return _emit({"ok": False, "error": "%s: %s" % (type(e).__name__, str(e))}, 2)
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
