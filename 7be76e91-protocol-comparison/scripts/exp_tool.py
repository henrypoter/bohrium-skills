#!/usr/bin/env python3
"""实验方案比较工具（纯 Python 标准库）。

check <result.json>                       六要素与单方案字段检查（兼容原有流程）
params <result.json> --spec <spec.json>   单方案参数限值检查
compare <result.json>                     同口径矩阵、成本/时间算术、选择与敏感性硬闸
feasibility <result.json> --spec <spec.json>  设备/档期、耗材、预算、时间窗、参数交集检查
schema <result.json>                      可核验交付契约检查
退出码：0=检查通过；1=发现 scientific/contract 问题；2=调用或输入错误。
"""
import json
import math
import sys

TOOL_VERSION = "3.0.0"
NUM = (int, float)


def _load(path):
    with open(path, encoding="utf-8") as f:
        value = json.load(f)
    if not isinstance(value, dict):
        raise ValueError("顶层必须是 JSON 对象")
    return value


def _num(x):
    return isinstance(x, NUM) and not isinstance(x, bool) and math.isfinite(x)


def _out(ok, **kw):
    value = {"ok": ok, "tool_version": TOOL_VERSION}
    value.update(kw)
    print(json.dumps(value, ensure_ascii=False, sort_keys=True))
    return 0 if ok else 1


def _source_ok(x):
    if isinstance(x, dict):
        return bool(x.get("id") and x.get("locator") and x.get("version"))
    return False


def _breakdown_errors(obj, prefix):
    errs = []
    if not isinstance(obj, dict):
        return [prefix + " 必须是对象"]
    required = ("capital", "machine", "consumables", "labor", "rework") if prefix.endswith("cost_breakdown") else ("preparation", "execution", "queue", "characterization", "rework")
    for key in required:
        if not _num(obj.get(key)) or obj.get(key) < 0:
            errs.append("%s.%s 必须是非负有限数" % (prefix, key))
    total = obj.get("total")
    if not _num(total) or total < 0:
        errs.append(prefix + ".total 必须是非负有限数")
    elif all(_num(obj.get(k)) for k in required):
        expected = math.fsum(obj[k] for k in required)
        if not math.isclose(total, expected, rel_tol=1e-9, abs_tol=1e-6):
            errs.append("%s.total=%s 与分项和=%s 不一致" % (prefix, total, expected))
    if not obj.get("unit"):
        errs.append(prefix + ".unit 为空")
    if not obj.get("source_locator"):
        errs.append(prefix + ".source_locator 为空（成本/时间须可追溯）")
    return errs


def cmd_check(path):
    d = _load(path)
    errs, warn = [], []
    rg = d.get("research_goal") or {}
    if not rg.get("hypothesis"):
        errs.append("research_goal.hypothesis 为空(目标须落成可检验假设)")
    for i, v in enumerate(d.get("variables") or []):
        if v.get("type") not in ("independent", "dependent", "confounder"):
            errs.append("variables[%d] type 非法" % i)
        for key in ("operational_definition", "unit"):
            if not v.get(key):
                errs.append("variables[%d] 缺 %s" % (i, key))
        if not v.get("range"):
            warn.append("variables[%d] 未给取值范围" % i)
    for i, c in enumerate(d.get("controls") or []):
        if not c.get("confounder_excluded"):
            errs.append("controls[%d] 缺 confounder_excluded" % i)
    for i, r in enumerate(d.get("risks") or []):
        for key in ("trigger", "consequence", "mitigation", "stop_rule", "alternative_path"):
            if not r.get(key):
                errs.append("risks[%d] 缺 %s" % (i, key))
    for i, j in enumerate(d.get("judgments") or []):
        if not j.get("evidence") or not j.get("source") or not j.get("source_locator"):
            errs.append("judgments[%d] 缺 evidence/source/source_locator" % i)
    for i, p in enumerate(d.get("parameters") or []):
        value, lo, hi = p.get("value"), p.get("min"), p.get("max")
        if not _num(value):
            errs.append("parameters[%d] value 非有限数" % i)
            continue
        if not p.get("unit"):
            errs.append("parameters[%d] 缺单位" % i)
        if lo is not None and (not _num(lo) or value < lo):
            errs.append("parameters[%d] 取值低于自述下限或下限非法" % i)
        if hi is not None and (not _num(hi) or value > hi):
            errs.append("parameters[%d] 取值高于自述上限或上限非法" % i)
        if _num(lo) and _num(hi) and lo > hi:
            errs.append("parameters[%d] min>max，参数窗口为空" % i)
    res = d.get("resources") or {}
    six = {"假设与变量": bool(rg.get("hypothesis") and d.get("variables")),
           "对照组": bool(d.get("controls")), "设备材料": bool(d.get("steps") or res),
           "时间成本": bool(res.get("time_estimate")), "参数范围": bool(d.get("parameters")),
           "风险和异常": bool(d.get("risks"))}
    missing = [k for k, ok in six.items() if not ok]
    return _out(not errs and not missing, six_elements=six, missing_elements=missing,
                errors=errs, warnings=warn)


def _parameter_violations(parameters, limits, prefix=""):
    bad = []
    for i, p in enumerate(parameters or []):
        name, value = p.get("name"), p.get("value")
        loc = "%sparameters[%d]" % (prefix, i)
        lim = limits.get(name)
        if lim is None:
            bad.append({"param": name, "issue": "spec 未声明该参数限值", "path": loc})
            continue
        if not lim.get("source_locator"):
            bad.append({"param": name, "issue": "限值缺 source_locator", "path": loc})
        if not p.get("unit") or lim.get("unit") != p.get("unit"):
            bad.append({"param": name, "issue": "单位不一致或缺失", "spec_unit": lim.get("unit"),
                        "doc_unit": p.get("unit"), "path": loc})
            continue
        if not _num(value):
            bad.append({"param": name, "issue": "value 非有限数", "path": loc})
            continue
        if _num(lim.get("max")) and value > lim["max"]:
            bad.append({"param": name, "issue": "超出设备/材料上限", "value": value,
                        "limit_max": lim["max"], "path": loc})
        if _num(lim.get("min")) and value < lim["min"]:
            bad.append({"param": name, "issue": "低于设备/材料下限", "value": value,
                        "limit_min": lim["min"], "path": loc})
        pmin, pmax = p.get("min"), p.get("max")
        if _num(pmin) and _num(pmax) and _num(lim.get("min")) and _num(lim.get("max")):
            lo, hi = max(pmin, lim["min"]), min(pmax, lim["max"])
            if lo > hi:
                bad.append({"param": name, "issue": "参数窗口与设备量程交集为空",
                            "intersection": None, "path": loc})
    return bad


def cmd_params(path, spec_path):
    d, spec = _load(path), _load(spec_path)
    bad = _parameter_violations(d.get("parameters"), spec.get("limits") or {})
    return _out(not bad, checked=len(d.get("parameters") or []), violations=bad)


def _schema_errors(d):
    errs = []
    for key in ("case_id", "input_id", "status", "plan_version", "comparison_schema_version",
                "source_version", "comparison_basis", "candidates", "selection", "exceptions",
                "recovery", "expert_confirmation", "unchecked", "sources", "uncertainty", "change_log", "run_record"):
        if key not in d:
            errs.append("缺顶层字段 %s" % key)
    if d.get("status") not in {"pass", "issues", "partial", "failed"}:
        errs.append("status 非法")
    for key in ("case_id", "input_id", "plan_version", "comparison_schema_version", "source_version"):
        if key in d and not d.get(key):
            errs.append(key + " 为空")
    run = d.get("run_record")
    if not isinstance(run, dict) or not run.get("tool_version") or not isinstance(run.get("commands"), list):
        errs.append("run_record 须含 tool_version 与 commands[]")
    sources = d.get("sources")
    if not isinstance(sources, list) or not sources:
        errs.append("sources 必须是非空来源登记表")
    else:
        for i, source in enumerate(sources):
            if not _source_ok(source):
                errs.append("sources[%d] 缺 id/version/locator" % i)
    if not isinstance(d.get("change_log"), list) or not d.get("change_log"):
        errs.append("change_log 至少记录一次版本变化")
    return errs


def cmd_schema(path):
    d = _load(path)
    errs = _schema_errors(d)
    return _out(not errs, errors=errs, candidates=len(d.get("candidates") or []))


def cmd_compare(path):
    d = _load(path)
    errs = _schema_errors(d)
    candidates = d.get("candidates") or []
    if not isinstance(candidates, list) or len(candidates) < 2:
        errs.append("至少两个候选方案；固定案例有3个版本化候选时须全部保留")
        candidates = candidates if isinstance(candidates, list) else []
    basis = d.get("comparison_basis") or {}
    required_fields = {"hypothesis", "variables", "controls", "steps", "parameters", "resources",
                       "decision_criteria", "risks", "evidence", "cost_breakdown", "time_breakdown",
                       "hard_constraints"}
    fields = set(basis.get("fields") or [])
    if not required_fields.issubset(fields):
        errs.append("comparison_basis.fields 未固定全部比较口径")
    for key in ("cost_currency", "time_unit", "hard_constraint_rule"):
        if not basis.get(key):
            errs.append("comparison_basis.%s 为空" % key)
    ids, eligible, ineligible = [], [], []
    source_ids = {s.get("id") for s in d.get("sources") or [] if isinstance(s, dict)}
    candidate_required = required_fields | {"id", "plan_version", "resource_requirements"}
    for i, c in enumerate(candidates):
        if not isinstance(c, dict):
            errs.append("candidates[%d] 不是对象" % i)
            continue
        cid = c.get("id") or "candidates[%d]" % i
        ids.append(c.get("id"))
        for key in sorted(candidate_required):
            if key not in c or c.get(key) in (None, "", []):
                errs.append("%s 缺可比字段 %s" % (cid, key))
        for key in ("variables", "controls", "steps", "parameters", "decision_criteria", "risks", "evidence"):
            if key in c and not isinstance(c.get(key), list):
                errs.append("%s.%s 必须是数组" % (cid, key))
        for j, v in enumerate(c.get("variables") or []):
            if v.get("type") not in ("independent", "dependent", "confounder"):
                errs.append("%s.variables[%d] type 非法" % (cid, j))
            for key in ("operational_definition", "unit", "range"):
                if not v.get(key):
                    errs.append("%s.variables[%d] 缺 %s" % (cid, j, key))
        for j, control in enumerate(c.get("controls") or []):
            if not control.get("confounder_excluded") or not control.get("type"):
                errs.append("%s.controls[%d] 缺 type/confounder_excluded" % (cid, j))
        for j, risk in enumerate(c.get("risks") or []):
            for key in ("trigger", "consequence", "mitigation", "stop_rule", "alternative_path"):
                if not risk.get(key):
                    errs.append("%s.risks[%d] 缺 %s" % (cid, j, key))
        for j, criterion in enumerate(c.get("decision_criteria") or []):
            if not criterion.get("criterion") or not criterion.get("source_locator"):
                errs.append("%s.decision_criteria[%d] 缺 criterion/source_locator" % (cid, j))
        for j, evidence in enumerate(c.get("evidence") or []):
            if not evidence.get("claim") or not evidence.get("source_id") or not evidence.get("locator"):
                errs.append("%s.evidence[%d] 缺 claim/source_id/locator" % (cid, j))
            elif evidence.get("source_id") not in source_ids:
                errs.append("%s.evidence[%d].source_id 未在 sources 登记" % (cid, j))
        for j, parameter in enumerate(c.get("parameters") or []):
            value, lo, hi = parameter.get("value"), parameter.get("min"), parameter.get("max")
            if not parameter.get("unit") or not all(_num(x) for x in (value, lo, hi)) or lo > hi or not lo <= value <= hi:
                errs.append("%s.parameters[%d] 单位/有限值/自述区间不合法" % (cid, j))
        errs.extend(_breakdown_errors(c.get("cost_breakdown"), cid + ".cost_breakdown"))
        errs.extend(_breakdown_errors(c.get("time_breakdown"), cid + ".time_breakdown"))
        if (c.get("cost_breakdown") or {}).get("unit") != basis.get("cost_currency"):
            errs.append(cid + " 成本单位与 comparison_basis 不一致")
        if (c.get("time_breakdown") or {}).get("unit") != basis.get("time_unit"):
            errs.append(cid + " 时间单位与 comparison_basis 不一致")
        constraints = c.get("hard_constraints") or []
        blocker = False
        for j, h in enumerate(constraints):
            if h.get("status") not in {"pass", "fail", "unknown"}:
                errs.append("%s.hard_constraints[%d] status 非法" % (cid, j))
            if h.get("status") != "pass":
                blocker = True
            if not h.get("id") or not h.get("type") or not h.get("source_locator"):
                errs.append("%s.hard_constraints[%d] 缺 id/type/source_locator" % (cid, j))
        (ineligible if blocker or not constraints else eligible).append(c.get("id"))
    if len(ids) != len(set(ids)) or any(x is None for x in ids):
        errs.append("候选 id 必须非空且唯一")
    selection = d.get("selection") or {}
    selected = selection.get("selected_candidate_id")
    rejected = selection.get("rejected") or []
    rejected_ids = [r.get("candidate_id") for r in rejected if isinstance(r, dict)]
    if not selection.get("rationale") or not selection.get("evidence"):
        errs.append("selection 缺 rationale/evidence")
    for i, evidence in enumerate(selection.get("evidence") or []):
        if evidence.get("source_id") not in source_ids or not evidence.get("locator"):
            errs.append("selection.evidence[%d] 未在 sources 登记或缺 locator" % i)
    for i, r in enumerate(rejected):
        if not isinstance(r, dict) or not r.get("candidate_id") or not r.get("reason"):
            errs.append("selection.rejected[%d] 缺 candidate_id/reason" % i)
    if set(rejected_ids) != set(x for x in ids if x != selected) or len(rejected_ids) != len(set(rejected_ids)):
        errs.append("每个未选候选必须且只能有一条具体舍弃理由")
    if selected is not None and selected in ineligible:
        errs.append("选择了硬约束 fail/unknown 的候选，禁止放行")
    if selected is not None and selected not in ids:
        errs.append("selected_candidate_id 不在候选矩阵中")
    if eligible and selected is None:
        errs.append("存在可行候选时必须明确选择，或将全部不可选原因写入硬约束后重跑")
    if not eligible:
        if selected is not None:
            errs.append("候选全部不可行时 selected_candidate_id 必须为 null")
        recovery = d.get("recovery") or {}
        if recovery.get("status") != "blocked" or not recovery.get("action") or not recovery.get("decision_owner"):
            errs.append("候选全部不可行：recovery 须为 blocked 并含 action/decision_owner")
        if not any(e.get("type") == "all_candidates_infeasible" and e.get("action") for e in d.get("exceptions") or []):
            errs.append("候选全部不可行：缺 all_candidates_infeasible 异常及 action")
    sensitivity = selection.get("sensitivity") or []
    if not sensitivity:
        errs.append("selection.sensitivity 为空：须说明结论翻转条件")
    for i, s in enumerate(sensitivity):
        if not isinstance(s, dict) or not all(s.get(k) for k in ("assumption", "threshold", "effect", "evidence")):
            errs.append("selection.sensitivity[%d] 缺 assumption/threshold/effect/evidence" % i)
    valid_exceptions = {"equipment_unavailable", "material_unavailable", "budget_exceeded",
                        "time_window_conflict", "parameter_window_conflict", "all_candidates_infeasible",
                        "missing_input", "uncertain_content"}
    for i, e in enumerate(d.get("exceptions") or []):
        if e.get("type") not in valid_exceptions:
            errs.append("exceptions[%d].type 非法" % i)
        for key in ("trigger", "action", "impact", "decision_owner", "status"):
            if not e.get(key):
                errs.append("exceptions[%d] 缺 %s" % (i, key))
    return _out(not errs, errors=errs, candidate_ids=ids, eligible_candidate_ids=eligible,
                ineligible_candidate_ids=ineligible)


def cmd_feasibility(path, spec_path):
    d, spec = _load(path), _load(spec_path)
    violations = []
    budget = spec.get("budget")
    window = spec.get("time_window")
    if not isinstance(budget, dict) or not _num(budget.get("amount")) or not budget.get("currency"):
        violations.append({"candidate_id": None, "type": "missing_input", "detail": "缺有效预算/币种",
                           "action": "标 unknown，向用户确认预算；不得编造报价"})
    if not isinstance(window, dict) or not _num(window.get("value")) or not window.get("unit"):
        violations.append({"candidate_id": None, "type": "missing_input", "detail": "缺有效时间窗/单位",
                           "action": "标 unknown，确认排期窗口后再判定可行"})
    equipment = spec.get("equipment") or {}
    materials = spec.get("materials") or {}
    limits = spec.get("limits") or {}
    basis = d.get("comparison_basis") or {}
    states = {}
    for c in d.get("candidates") or []:
        cid = c.get("id")
        cv = []
        cost = c.get("cost_breakdown") or {}
        timing = c.get("time_breakdown") or {}
        if isinstance(budget, dict) and _num(budget.get("amount")) and _num(cost.get("total")):
            if cost.get("unit") != budget.get("currency"):
                cv.append({"type": "budget_exceeded", "detail": "成本币种与预算币种不一致，禁止直接比较"})
            elif cost["total"] > budget["amount"]:
                cv.append({"type": "budget_exceeded", "detail": "总成本 %.6g 超预算 %.6g" % (cost["total"], budget["amount"]),
                           "delta": cost["total"] - budget["amount"]})
        if isinstance(window, dict) and _num(window.get("value")) and _num(timing.get("total")):
            if timing.get("unit") != window.get("unit"):
                cv.append({"type": "time_window_conflict", "detail": "时间单位不一致，禁止直接比较"})
            elif timing["total"] > window["value"]:
                cv.append({"type": "time_window_conflict", "detail": "总时间 %.6g 超时间窗 %.6g" % (timing["total"], window["value"]),
                           "delta": timing["total"] - window["value"]})
        req = c.get("resource_requirements") or {}
        for eid in req.get("equipment") or []:
            item = equipment.get(eid)
            if not isinstance(item, dict):
                cv.append({"type": "missing_input", "detail": "设备 %s 无可用性/档期合同" % eid})
            elif item.get("available") is not True or item.get("booking_status") != "open":
                cv.append({"type": "equipment_unavailable", "detail": "设备 %s 不可得或排期已满" % eid})
            elif not item.get("source_locator"):
                cv.append({"type": "missing_input", "detail": "设备 %s 可用性缺 source_locator" % eid})
        for mid in req.get("materials") or []:
            item = materials.get(mid)
            if not isinstance(item, dict):
                cv.append({"type": "missing_input", "detail": "耗材 %s 无库存/货期合同" % mid})
            elif item.get("available") is not True:
                cv.append({"type": "material_unavailable", "detail": "耗材 %s 缺货" % mid})
            elif not item.get("source_locator"):
                cv.append({"type": "missing_input", "detail": "耗材 %s 库存缺 source_locator" % mid})
            elif isinstance(window, dict) and _num(window.get("value")) and _num(item.get("lead_time")):
                if item.get("unit") != window.get("unit"):
                    cv.append({"type": "time_window_conflict", "detail": "耗材 %s 货期单位与时间窗不一致" % mid})
                elif item["lead_time"] > window["value"]:
                    cv.append({"type": "time_window_conflict", "detail": "耗材 %s 货期超时间窗" % mid})
        for p in _parameter_violations(c.get("parameters"), limits, cid + "."):
            kind = "parameter_window_conflict" if p.get("issue") != "spec 未声明该参数限值" else "missing_input"
            cv.append({"type": kind, "detail": p})
        for v in cv:
            v["candidate_id"] = cid
            v.setdefault("action", "记录 exceptions；给有依据的替代路径、影响和 decision_owner；不可行则 blocked")
        violations.extend(cv)
        states[cid] = "infeasible" if cv else "resource_checks_pass"
    if states and all(x == "infeasible" for x in states.values()):
        violations.append({"candidate_id": None, "type": "all_candidates_infeasible",
                           "detail": "所有候选均有资源/参数阻断",
                           "action": "selection.selected_candidate_id=null；recovery=blocked；列放宽项交人工决策"})
    return _out(not violations, violations=violations, candidate_status=states,
                spec_version=spec.get("spec_version"))


def main(argv):
    if not argv:
        print(__doc__)
        return 2
    try:
        if argv[0] == "check" and len(argv) == 2:
            return cmd_check(argv[1])
        if argv[0] == "params" and len(argv) == 4 and argv[2] == "--spec":
            return cmd_params(argv[1], argv[3])
        if argv[0] == "compare" and len(argv) == 2:
            return cmd_compare(argv[1])
        if argv[0] == "feasibility" and len(argv) == 4 and argv[2] == "--spec":
            return cmd_feasibility(argv[1], argv[3])
        if argv[0] == "schema" and len(argv) == 2:
            return cmd_schema(argv[1])
        print(__doc__)
        return 2
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        _out(False, errors=["输入/调用错误：%s" % exc])
        return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
