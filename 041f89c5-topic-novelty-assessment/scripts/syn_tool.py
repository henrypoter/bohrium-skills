#!/usr/bin/env python3
"""科研选题与创新性评估机检（纯 Python 标准库，tool_version=2.0.0）。

  cite_check <result.json>       基础引用回路、定位与纳入理由
  theme_check <result.json>      兼容检查：主题是否都有带引用论断
  question_check <result.json>   对象/变量/基线/结局/证伪条件是否可检验
  search_check <result.json>     检索式、时间窗、命中量、覆盖与失败状态
  novelty_check <result.json>    最近邻工作逐维比较及有界创新陈述
  feasibility_check <result.json> 数据/算力/实验/时间/人员前提及假设验证
  decision_check <result.json>   冲突证据、研究空白与综合结论一致性
  provenance_check <result.json> --input <case.json> --source-root <dir>
                                 复算输入及每份原始材料 SHA-256，查版本字段
  schema <result.json>           顶层交付契约、版本字段与计数初检

退出码：0=结构检查通过；1=发现交付问题；2=调用或输入文件错误。
机检证明字段闭合而非科学语义正确；文献支持与创新性仍须人工核对原文。
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


def _citation_errors(citations, included, owner):
    errs = []
    if not citations:
        return ["%s 缺 citations/evidence" % owner]
    for citation in citations:
        rid = citation.get("record_id")
        if rid not in included:
            errs.append("%s 引用未纳入或未知记录 %s" % (owner, rid))
        for key in ("location", "quote"):
            if not _present(citation.get(key)):
                errs.append("%s/%s 缺 %s" % (owner, rid, key))
    return errs


def cmd_cite_check(path):
    d = _load(path)
    recs = _ids(d.get("records", d.get("included", [])))
    errs, uncited, dangling = [], [], []
    claims = d.get("claims", [])
    if not claims:
        errs.append("claims 为空(评估必须输出证据论断)")
    for i, claim in enumerate(claims):
        citations = claim.get("citations", [])
        if not citations:
            uncited.append(claim.get("id") or "claim[%d]" % i)
        for j, citation in enumerate(citations):
            rid = citation.get("record_id")
            if not citation.get("location"):
                errs.append("claims[%d].citations[%d] 缺 location" % (i, j))
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
    by_theme = {}
    for claim in d.get("claims", []):
        theme = claim.get("theme") or "(未归类)"
        by_theme.setdefault(theme, []).append(bool(claim.get("citations")))
    themes = d.get("themes", [])
    uncovered = [t for t in (x.get("name") for x in themes) if t not in by_theme]
    weak = [t for t, values in by_theme.items() if not any(values)]
    unclassified = len(by_theme.get("(未归类)", []))
    ok = not uncovered and not weak and not unclassified and bool(themes)
    return _emit(ok, themes_declared=len(themes), themes_with_claims=len(by_theme),
                 themes_without_claims=uncovered, themes_without_cited_claim=weak,
                 unclassified_claims=unclassified)


def cmd_question_check(path):
    d = _load(path)
    question = d.get("research_question", {})
    errs = []
    for key in ("id", "statement", "object", "expected_outcome", "scope"):
        if not _present(question.get(key)):
            errs.append("research_question.%s 为空" % key)
    variables = question.get("variables", [])
    if not variables:
        errs.append("至少定义一个可操作变量")
    for variable in variables:
        for key in ("name", "role", "measure"):
            if not _present(variable.get(key)):
                errs.append("变量 %s 缺 %s" % (variable.get("name"), key))
        if variable.get("role") not in {"independent", "dependent", "covariate", "constraint"}:
            errs.append("变量 %s role 非法" % variable.get("name"))
    for key in ("comparators", "falsification_conditions", "success_criteria"):
        if not question.get(key) or any(not _present(x) for x in question.get(key, [])):
            errs.append("research_question.%s 须为非空数组" % key)
    if not isinstance(question.get("scope"), dict) or not question.get("scope", {}).get("time_window"):
        errs.append("research_question.scope.time_window 为空")
    return _emit(not errs, errors=errs, variables_checked=len(variables))


def _nonnegative_int(value):
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def cmd_search_check(path):
    d = _load(path)
    errs = []
    logs = d.get("search_log", [])
    records = d.get("records", [])
    record_ids = _ids(records)
    included = _ids(d.get("included", []))
    if not logs:
        errs.append("search_log 为空；检索失败也须保留失败日志")
    selected_all = set()
    failed = False
    total_hits = 0
    for i, log in enumerate(logs):
        label = "search_log[%d]" % i
        for key in ("source", "query", "executed_at", "time_window", "status"):
            if not _present(log.get(key)):
                errs.append("%s.%s 为空" % (label, key))
        status = log.get("status")
        if status not in {"completed", "failed", "permission_denied"}:
            errs.append("%s.status 非法" % label)
        if status != "completed":
            failed = True
            if not _present(log.get("error")):
                errs.append("%s 失败/权限不足须记录 error" % label)
        for key in ("hits", "returned", "screened"):
            if status == "completed" and not _nonnegative_int(log.get(key)):
                errs.append("%s.%s 须为非负整数" % (label, key))
        if status == "completed":
            total_hits += log.get("hits", 0)
            if log.get("returned", 0) > log.get("hits", 0) or log.get("screened", 0) > log.get("returned", 0):
                errs.append("%s hits/returned/screened 数量不闭合" % label)
        selected = set(log.get("selected_record_ids", []))
        if not selected <= record_ids:
            errs.append("%s.selected_record_ids 含未知记录" % label)
        if status == "completed" and len(selected) > log.get("screened", 0):
            errs.append("%s 选择数大于筛查数" % label)
        selected_all |= selected
    for record in records:
        if record.get("origin") == "search" and record.get("id") not in selected_all:
            errs.append("检索来源记录 %s 未在任何 search_log 中回链" % record.get("id"))
    coverage = d.get("coverage", {})
    for key in ("databases", "time_window", "languages", "limitations", "evidence_sufficiency"):
        if not _present(coverage.get(key)):
            errs.append("coverage.%s 为空" % key)
    if coverage.get("evidence_sufficiency") not in {"sufficient", "limited", "empty"}:
        errs.append("coverage.evidence_sufficiency 非法")
    if len(included) < 2:
        if d.get("status") == "pass":
            errs.append("纳入文献过少时 status 不得为 pass")
        if coverage.get("evidence_sufficiency") == "sufficient":
            errs.append("纳入文献过少时不得标 sufficient")
    if total_hits == 0 and coverage.get("evidence_sufficiency") != "empty":
        errs.append("检索命中为零时 evidence_sufficiency 须为 empty")
    if failed and (d.get("status") == "pass" or not d.get("uncertainty")):
        errs.append("接口异常/权限不足时须降级 status 并登记 uncertainty")
    return _emit(not errs, errors=errs, searches_checked=len(logs), records_selected=len(selected_all))


def cmd_novelty_check(path):
    d = _load(path)
    errs = []
    included = _ids(d.get("included", []))
    comparisons = d.get("comparisons", [])
    comparison_ids = set()
    dimensions = {"task", "method", "data", "evaluation", "conclusion"}
    for comparison in comparisons:
        rid = comparison.get("record_id")
        comparison_ids.add(rid)
        if rid not in included:
            errs.append("comparison %s 不在纳入清单" % rid)
        fields = comparison.get("dimensions", {})
        if set(fields) != dimensions or any(not _present(fields.get(k)) for k in dimensions):
            errs.append("comparison %s 须完整比较 task/method/data/evaluation/conclusion" % rid)
        if comparison.get("comparability") not in {"comparable", "partial", "not_comparable"}:
            errs.append("comparison %s comparability 非法" % rid)
        if comparison.get("comparability") != "comparable" and not _present(comparison.get("comparability_reason")):
            errs.append("comparison %s 须说明不可直接比较原因" % rid)
        errs += _citation_errors(comparison.get("citations"), included, "comparison %s" % rid)
    claims = d.get("novelty_claims", [])
    banned = ("尚无人研究", "完全没有先例", "no prior work", "globally novel")
    for claim in claims:
        nid = claim.get("id")
        for key in ("statement", "bounded_claim", "status", "innovation_type", "recency_rationale", "limitations"):
            if not _present(claim.get(key)):
                errs.append("novelty %s 缺 %s" % (nid, key))
        if claim.get("innovation_type") not in {"method", "data", "scene_transfer", "conclusion_correction"}:
            errs.append("novelty %s innovation_type 非法" % nid)
        if claim.get("status") not in {"supported", "contested", "covered", "unknown"}:
            errs.append("novelty %s status 非法" % nid)
        nearest = set(claim.get("nearest_record_ids", []))
        if not nearest or not nearest <= comparison_ids or not nearest <= included:
            errs.append("novelty %s nearest_record_ids 未回链比较矩阵" % nid)
        differences = claim.get("differences", [])
        if not differences:
            errs.append("novelty %s 缺逐条 differences" % nid)
        for diff in differences:
            if diff.get("record_id") not in nearest or not _present(diff.get("dimension")):
                errs.append("novelty %s difference 未指向最近邻或缺维度" % nid)
            for key in ("existing", "proposed"):
                if not _present(diff.get(key)):
                    errs.append("novelty %s difference 缺 %s" % (nid, key))
            errs += _citation_errors(diff.get("citations"), included, "novelty %s difference" % nid)
        if claim.get("absolute_novelty_claimed") is not False:
            errs.append("novelty %s absolute_novelty_claimed 必须为 false" % nid)
        combined = str(claim.get("statement", "")) + " " + str(claim.get("bounded_claim", ""))
        if any(term in combined for term in banned):
            errs.append("novelty %s 含超出检索范围的绝对新颖性措辞" % nid)
        if claim.get("innovation_type") == "scene_transfer" and claim.get("method_novelty_claimed") is not False:
            errs.append("场景迁移不得同时声称方法创新")
    return _emit(not errs and bool(comparisons) and bool(claims), errors=errs,
                 comparisons_checked=len(comparisons), novelty_claims_checked=len(claims))


def cmd_feasibility_check(path):
    d = _load(path)
    feasibility = d.get("feasibility", {})
    premises = feasibility.get("premises", [])
    included = _ids(d.get("included", []))
    errs = []
    required_categories = {"data", "compute", "experiment", "time", "personnel"}
    seen = set()
    for premise in premises:
        pid = premise.get("id")
        category = premise.get("category")
        seen.add(category)
        if category not in required_categories:
            errs.append("premise %s category 非法" % pid)
        if not _present(premise.get("statement")):
            errs.append("premise %s statement 为空" % pid)
        if premise.get("applicable") is False:
            if not _present(premise.get("not_applicable_reason")):
                errs.append("premise %s 不适用须写原因" % pid)
            continue
        if premise.get("applicable") is not True:
            errs.append("premise %s applicable 须为布尔值" % pid)
        status = premise.get("status")
        if status not in {"verified", "assumption", "unknown"}:
            errs.append("premise %s status 非法" % pid)
        if status == "verified":
            evidence = premise.get("evidence", [])
            if not evidence:
                errs.append("verified premise %s 缺 evidence" % pid)
            for source in evidence:
                for key in ("type", "location", "quote"):
                    if not _present(source.get(key)):
                        errs.append("premise %s evidence 缺 %s" % (pid, key))
                if source.get("type") == "literature" and source.get("record_id") not in included:
                    errs.append("premise %s 文献前提未回链纳入记录" % pid)
                if source.get("type") not in {"literature", "case_input"}:
                    errs.append("premise %s evidence.type 非法" % pid)
        else:
            for key in ("assumption_reason", "validation"):
                if not _present(premise.get(key)):
                    errs.append("假设/未知前提 %s 缺 %s" % (pid, key))
        for key in ("failure_risk", "mitigation"):
            if not _present(premise.get(key)):
                errs.append("premise %s 缺 %s" % (pid, key))
    if seen != required_categories:
        errs.append("数据/算力/实验/时间/人员五类前提必须逐项回应（可不适用但需理由）")
    decision = feasibility.get("decision")
    if decision not in {"feasible", "conditional", "infeasible", "unknown"}:
        errs.append("feasibility.decision 非法")
    if not _present(feasibility.get("rationale")):
        errs.append("feasibility.rationale 为空")
    applicable = [p for p in premises if p.get("applicable") is True]
    if decision == "feasible" and any(p.get("status") != "verified" for p in applicable):
        errs.append("仍有假设/未知前提时不得判 feasible")
    if decision == "conditional" and applicable and all(p.get("status") == "verified" for p in applicable):
        errs.append("全部前提已核实时不应无依据判 conditional")
    return _emit(not errs, errors=errs, premises_checked=len(premises))


def cmd_decision_check(path):
    d = _load(path)
    errs = []
    included = _ids(d.get("included", []))
    claims = _ids(d.get("claims", []))
    comparison_ids = _ids(d.get("comparisons", []), "record_id")
    novelty_ids = _ids(d.get("novelty_claims", []))
    conflicts = d.get("conflicts", [])
    for conflict in conflicts:
        if not _present(conflict.get("topic")):
            errs.append("conflict %s 缺 topic" % conflict.get("id"))
        positions = conflict.get("positions", [])
        if len({p.get("record_id") for p in positions}) < 2:
            errs.append("conflict %s 须并列至少两篇文献立场" % conflict.get("id"))
        for position in positions:
            rid = position.get("record_id")
            if rid not in included or not _present(position.get("statement")):
                errs.append("conflict %s 立场记录无效" % conflict.get("id"))
            errs += _citation_errors(position.get("citations"), included, "conflict %s" % conflict.get("id"))
        for key in ("treatment", "effect_on_decision"):
            if not _present(conflict.get(key)):
                errs.append("conflict %s 缺 %s" % (conflict.get("id"), key))
    if not conflicts:
        review = d.get("conflict_review", {})
        if review.get("searched") is not True or not _present(review.get("note")):
            errs.append("无冲突时须填 conflict_review.searched/note")
    gaps = d.get("research_gaps", [])
    for gap in gaps:
        basis_c = set(gap.get("basis_comparison_ids", []))
        basis_n = set(gap.get("basis_novelty_claim_ids", []))
        if (not basis_c and not basis_n) or not basis_c <= comparison_ids or not basis_n <= novelty_ids:
            errs.append("gap %s 未回链比较矩阵或创新判断" % gap.get("id"))
        if gap.get("bounded_to_search") is not True:
            errs.append("gap %s 须限定于本次检索" % gap.get("id"))
        for key in ("statement", "next_step"):
            if not _present(gap.get(key)):
                errs.append("gap %s 缺 %s" % (gap.get("id"), key))
    conclusion = d.get("conclusion", {})
    for key in ("summary", "recommendation", "research_question_id", "feasibility_decision"):
        if not _present(conclusion.get(key)):
            errs.append("conclusion.%s 为空" % key)
    if conclusion.get("research_question_id") != d.get("research_question", {}).get("id"):
        errs.append("综合结论未回链 research_question.id")
    supporting = set(conclusion.get("supporting_claim_ids", []))
    novelty_used = set(conclusion.get("novelty_claim_ids", []))
    if not supporting or not supporting <= claims:
        errs.append("conclusion.supporting_claim_ids 无效")
    if not novelty_used or not novelty_used <= novelty_ids:
        errs.append("conclusion.novelty_claim_ids 无效")
    if conclusion.get("feasibility_decision") != d.get("feasibility", {}).get("decision"):
        errs.append("综合结论与 feasibility.decision 不一致")
    if not conclusion.get("residual_uncertainties"):
        errs.append("conclusion.residual_uncertainties 为空")
    recommendation = conclusion.get("recommendation")
    if recommendation not in {"pursue", "pursue_conditionally", "revise", "defer", "reject", "unknown"}:
        errs.append("conclusion.recommendation 非法")
    if recommendation == "pursue_conditionally" and not conclusion.get("conditions"):
        errs.append("有条件推进必须列 conditions")
    feasibility_decision = d.get("feasibility", {}).get("decision")
    if recommendation == "pursue" and feasibility_decision != "feasible":
        errs.append("可行性非 feasible 时不得直接 pursue")
    if feasibility_decision == "infeasible" and recommendation in {"pursue", "pursue_conditionally"}:
        errs.append("不可行前提未解决时不得建议推进")
    novelty_by_id = {x.get("id"): x for x in d.get("novelty_claims", [])}
    if all(novelty_by_id[n].get("status") == "covered" for n in novelty_used if n in novelty_by_id):
        if recommendation in {"pursue", "pursue_conditionally"}:
            errs.append("创新点均已被覆盖时须 revise/defer/reject")
    return _emit(not errs, errors=errs, conflicts_checked=len(conflicts), gaps_checked=len(gaps))


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
    if _ids(sources, "record_id") != records:
        errs.append("sources.record_id 集合须与 records 完全一致")
    checked = 0
    for source in sources:
        rid, rel, expected = source.get("record_id"), source.get("path"), source.get("sha256")
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
                "included", "excluded", "search_log", "coverage", "comparisons", "novelty_claims",
                "feasibility", "claims", "themes", "research_gaps", "conflicts", "conclusion",
                "counts", "gain", "unchecked", "sources", "uncertainty", "change_log", "run"):
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
                    "question_check": cmd_question_check, "search_check": cmd_search_check,
                    "novelty_check": cmd_novelty_check, "feasibility_check": cmd_feasibility_check,
                    "decision_check": cmd_decision_check, "schema": cmd_schema}
        if command not in handlers:
            print(__doc__)
            return 2
        return handlers[command](args[1])
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        return _emit(False, errors=["%s: %s" % (type(exc).__name__, exc)])


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
