#!/usr/bin/env python3
"""实验方案生成与优化工具（纯 Python 标准库）。

check <result.json>                        六要素、变量、对照、风险替代路径检查
params <result.json> --spec <spec.json>    参数与设备/材料限值检查
controls <result.json>                     研究目标→混杂→对照反向覆盖检查
optimize <result.json> --spec <spec.json>  预算/时间窗/样本量/设备/货期/参数优化闸
schema <result.json>                       版本、来源定位与运行记录交付检查
退出码：0=通过；1=方案或契约问题；2=调用或输入错误。工具只给裁剪区间和处置建议，不静默改方案。
"""
import json
import math
import sys

TOOL_VERSION = "3.0.0"


def _load(path):
    with open(path, encoding="utf-8") as f:
        value = json.load(f)
    if not isinstance(value, dict):
        raise ValueError("顶层必须是 JSON 对象")
    return value


def _num(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def _out(ok, **kw):
    value = {"ok": ok, "tool_version": TOOL_VERSION}
    value.update(kw)
    print(json.dumps(value, ensure_ascii=False, sort_keys=True))
    return 0 if ok else 1


def _parameter_violations(parameters, limits):
    bad = []
    for i, p in enumerate(parameters or []):
        name, value = p.get("name"), p.get("value")
        lim = limits.get(name)
        if lim is None:
            bad.append({"param": name, "issue": "spec 未声明该参数限值，无法核验"})
            continue
        if not lim.get("source_locator"):
            bad.append({"param": name, "issue": "设备/材料限值缺 source_locator"})
        if not p.get("source") or not p.get("source_locator"):
            bad.append({"param": name, "issue": "参数取值缺 source/source_locator"})
        if lim.get("unit") != p.get("unit") or not p.get("unit"):
            bad.append({"param": name, "issue": "单位不一致或缺失", "spec_unit": lim.get("unit"),
                        "doc_unit": p.get("unit")})
            continue
        if not _num(value):
            bad.append({"param": name, "issue": "value 非有限数"})
            continue
        lo, hi = p.get("min"), p.get("max")
        if not _num(lo) or not _num(hi) or lo > hi:
            bad.append({"param": name, "issue": "自述参数区间非法或缺失"})
            continue
        if value < lo or value > hi:
            bad.append({"param": name, "issue": "取值越出自述区间", "value": value})
        lmin, lmax = lim.get("min"), lim.get("max")
        if not _num(lmin) or not _num(lmax) or lmin > lmax:
            bad.append({"param": name, "issue": "spec 参数限值非法"})
            continue
        if value < lmin or value > lmax:
            bad.append({"param": name, "issue": "超出设备/材料允许范围", "allowed": [lmin, lmax]})
        new_lo, new_hi = max(lo, lmin), min(hi, lmax)
        if new_lo > new_hi:
            bad.append({"param": name, "issue": "参数窗口与设备量程交集为空"})
    return bad


def _breakdown_errors(obj, kind):
    if not isinstance(obj, dict):
        return ["resources.%s 必须是对象" % kind]
    keys = ("capital", "machine", "consumables", "labor", "rework") if kind == "cost_breakdown" else ("preparation", "execution", "queue", "characterization", "rework")
    errs = []
    for key in keys:
        if not _num(obj.get(key)) or obj.get(key) < 0:
            errs.append("resources.%s.%s 必须为非负有限数" % (kind, key))
    if not _num(obj.get("total")) or obj.get("total") < 0:
        errs.append("resources.%s.total 非法" % kind)
    elif all(_num(obj.get(k)) for k in keys):
        expected = math.fsum(obj[k] for k in keys)
        if not math.isclose(obj["total"], expected, rel_tol=1e-9, abs_tol=1e-6):
            errs.append("resources.%s.total=%s 与分项和=%s 不一致" % (kind, obj["total"], expected))
    for key in ("unit", "source_locator"):
        if not obj.get(key):
            errs.append("resources.%s.%s 为空" % (kind, key))
    return errs


def cmd_check(path):
    d = _load(path)
    errs, warn = [], []
    rg = d.get("research_goal") or {}
    if not rg.get("hypothesis"):
        errs.append("research_goal.hypothesis 为空(目标须落成可检验假设)")
    types = []
    for i, v in enumerate(d.get("variables") or []):
        types.append(v.get("type"))
        if v.get("type") not in ("independent", "dependent", "confounder"):
            errs.append("variables[%d] type 非法" % i)
        for key in ("operational_definition", "unit", "range", "measurement_method"):
            if not v.get(key):
                errs.append("variables[%d] 缺 %s" % (i, key))
    if "independent" not in types or "dependent" not in types:
        warn.append("建议至少各有 independent/dependent 变量；controls 命令将作硬检查")
    for i, c in enumerate(d.get("controls") or []):
        for key in ("purpose", "confounder_excluded", "maps_requirement"):
            if not c.get(key):
                errs.append("controls[%d] 缺 %s" % (i, key))
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
            errs.append("parameters[%d] 参数窗口为空" % i)
    res = d.get("resources") or {}
    six = {"假设与变量": bool(rg.get("hypothesis") and d.get("variables")),
           "对照组": bool(d.get("controls")), "设备材料": bool(d.get("steps") or res),
           "时间成本": bool(res.get("time_estimate") and res.get("cost_estimate")),
           "参数范围": bool(d.get("parameters")), "风险和异常": bool(d.get("risks"))}
    missing = [key for key, ok in six.items() if not ok]
    return _out(not errs and not missing, six_elements=six, missing_elements=missing,
                errors=errs, warnings=warn)


def cmd_params(path, spec_path):
    d, spec = _load(path), _load(spec_path)
    bad = _parameter_violations(d.get("parameters"), spec.get("limits") or {})
    return _out(not bad, checked=len(d.get("parameters") or []), violations=bad)


def _schema_errors(d):
    errs = []
    for key in ("case_id", "input_id", "status", "plan_version", "schema_version", "source_version",
                "research_goal", "decision_criteria", "variables", "control_requirements", "controls",
                "steps", "resources", "parameters", "risks", "judgments", "assumptions",
                "expert_confirmation", "exceptions", "unchecked", "sources", "uncertainty",
                "change_log", "run_record"):
        if key not in d:
            errs.append("缺顶层字段 %s" % key)
    if d.get("status") not in {"pass", "issues", "partial", "failed"}:
        errs.append("status 非法")
    for key in ("case_id", "input_id", "plan_version", "schema_version", "source_version"):
        if key in d and not d.get(key):
            errs.append(key + " 为空")
    run = d.get("run_record")
    if not isinstance(run, dict) or not run.get("tool_version") or not isinstance(run.get("commands"), list):
        errs.append("run_record 须含 tool_version 与 commands[]")
    sources = d.get("sources")
    if not isinstance(sources, list) or not sources:
        errs.append("sources 必须是非空来源登记表")
    else:
        ids = []
        for i, source in enumerate(sources):
            if not isinstance(source, dict) or not all(source.get(k) for k in ("id", "version", "locator")):
                errs.append("sources[%d] 缺 id/version/locator" % i)
            else:
                ids.append(source["id"])
        if len(ids) != len(set(ids)):
            errs.append("sources.id 必须唯一")
    log = d.get("change_log")
    if not isinstance(log, list) or not log:
        errs.append("change_log 至少记录一次版本变化")
    else:
        for i, change in enumerate(log):
            if not isinstance(change, dict) or not all(change.get(k) for k in ("plan_version", "change", "reason")):
                errs.append("change_log[%d] 缺 plan_version/change/reason" % i)
    return errs


def cmd_schema(path):
    d = _load(path)
    errs = _schema_errors(d)
    return _out(not errs, errors=errs, variables=len(d.get("variables") or []),
                parameters=len(d.get("parameters") or []), risks=len(d.get("risks") or []))


def cmd_controls(path):
    d = _load(path)
    errs, warnings = [], []
    variables = d.get("variables") or []
    types = [v.get("type") for v in variables]
    if "independent" not in types:
        errs.append("缺 independent 变量，无法从研究目标操作化干预")
    if "dependent" not in types:
        errs.append("缺 dependent 变量，无法判读研究目标")
    requirements = d.get("control_requirements") or []
    controls = d.get("controls") or []
    if not requirements:
        errs.append("control_requirements 为空：未从研究目标反推所需对照")
    req_ids = []
    for i, req in enumerate(requirements):
        rid = req.get("id") or "control_requirements[%d]" % i
        req_ids.append(req.get("id"))
        for key in ("research_goal", "confounder", "required_control_types", "rationale", "source_locator"):
            if not req.get(key):
                errs.append("%s 缺 %s" % (rid, key))
        if not isinstance(req.get("required_control_types"), list):
            errs.append(rid + ".required_control_types 必须是数组")
        matches = [c for c in controls if c.get("maps_requirement") == req.get("id")]
        if not matches:
            errs.append(rid + " 没有任何 controls.maps_requirement 覆盖")
        for c in matches:
            if c.get("type") not in (req.get("required_control_types") or []):
                errs.append("%s 由对照 %s 覆盖，但 type=%s 不符合所需类型" % (rid, c.get("id"), c.get("type")))
            if not c.get("confounder_excluded") or not c.get("purpose"):
                errs.append("对照 %s 缺排除的混杂/目的" % c.get("id"))
    if len(req_ids) != len(set(req_ids)) or any(x is None for x in req_ids):
        errs.append("control_requirements.id 必须非空且唯一")
    known = set(req_ids)
    for i, c in enumerate(controls):
        if c.get("maps_requirement") not in known:
            errs.append("controls[%d].maps_requirement 未指向有效需求" % i)
    if not any(c.get("type") in {"positive", "negative", "blank"} for c in controls):
        warnings.append("未设空白/阳性/阴性对照；若梯度设计足够，请在 rationale 解释而非机械补组")
    return _out(not errs, errors=errs, warnings=warnings, requirements=len(requirements),
                controls=len(controls))


def _refs(items):
    result = []
    for item in items or []:
        result.append(item.get("id") if isinstance(item, dict) else item)
    return [x for x in result if x]


def cmd_optimize(path, spec_path):
    d, spec = _load(path), _load(spec_path)
    issues = _schema_errors(d)
    violations, recommendations = [], []
    res = d.get("resources") or {}
    cost, timing = res.get("cost_breakdown") or {}, res.get("time_breakdown") or {}
    issues.extend(_breakdown_errors(res.get("cost_breakdown"), "cost_breakdown"))
    issues.extend(_breakdown_errors(res.get("time_breakdown"), "time_breakdown"))
    budget, window = spec.get("budget"), spec.get("time_window")
    if not isinstance(budget, dict) or not _num(budget.get("amount")) or not budget.get("currency"):
        violations.append({"type": "missing_input", "detail": "无有效预算或币种",
                           "action": "resources.budget_status=unknown；列确认项，不编造价格或自动降样本量"})
    elif _num(cost.get("total")):
        if cost.get("unit") != budget.get("currency"):
            violations.append({"type": "budget_exceeded", "detail": "成本/预算币种不一致"})
        elif cost["total"] > budget["amount"]:
            violations.append({"type": "budget_exceeded", "detail": "成本超预算", "delta": cost["total"] - budget["amount"],
                               "action": "先裁剪非关键消耗；涉及样本量/对照删减须重估统计目标并人工确认"})
        else:
            recommendations.append({"type": "budget_headroom", "value": budget["amount"] - cost["total"],
                                    "unit": budget.get("currency"), "requires_confirmation": False})
    if not isinstance(window, dict) or not _num(window.get("value")) or not window.get("unit"):
        violations.append({"type": "missing_input", "detail": "无有效排期时间窗或单位",
                           "action": "time_status=unknown；确认设备档期与总窗口"})
    elif _num(timing.get("total")):
        if timing.get("unit") != window.get("unit"):
            violations.append({"type": "time_window_conflict", "detail": "时间单位不一致"})
        elif timing["total"] > window["value"]:
            violations.append({"type": "time_window_conflict", "detail": "时间窗与样本量/排期冲突", "delta": timing["total"] - window["value"],
                               "action": "给并行/分批/缩样本三个显式选项及影响，由 decision_owner 选择"})
    sample_size, capacity, batches = res.get("sample_size"), res.get("capacity_per_batch"), res.get("batches")
    supplied = [x is not None for x in (sample_size, capacity, batches)]
    if any(supplied) and not all(supplied):
        violations.append({"type": "missing_input", "detail": "sample_size/capacity_per_batch/batches 必须同时给出"})
    elif all(supplied):
        if not all(_num(x) and x > 0 for x in (sample_size, capacity, batches)):
            violations.append({"type": "constraint_conflict", "detail": "样本量/单批容量/批次数必须为正有限数"})
        else:
            minimum = int(math.ceil(sample_size / capacity))
            if batches < minimum:
                violations.append({"type": "time_window_conflict", "detail": "批次数不足",
                                   "minimum_batches": minimum, "actual_batches": batches,
                                   "action": "增加批次或重估 sample_size；不得静默丢弃样本"})
            else:
                recommendations.append({"type": "minimum_batches", "value": minimum, "requires_confirmation": False})
    equipment, materials = spec.get("equipment") or {}, spec.get("materials") or {}
    for eid in _refs(res.get("equipment")):
        item = equipment.get(eid)
        if not isinstance(item, dict):
            violations.append({"type": "missing_input", "detail": "设备 %s 参数/可用性未提供" % eid})
        elif item.get("available") is not True or item.get("booking_status") != "open":
            violations.append({"type": "equipment_unavailable", "detail": "设备 %s 不可得或排期已满" % eid,
                               "action": "登记例外；使用有来源的替代设备或改期，给成本/参数影响"})
        elif not item.get("source_locator"):
            violations.append({"type": "missing_input", "detail": "设备 %s 合同缺 source_locator" % eid})
    for mid in _refs(res.get("materials")):
        item = materials.get(mid)
        if not isinstance(item, dict):
            violations.append({"type": "missing_input", "detail": "试剂/耗材 %s 库存未提供" % mid})
        elif item.get("available") is not True:
            violations.append({"type": "material_unavailable", "detail": "试剂/耗材 %s 缺货" % mid,
                               "action": "登记例外；给替代试剂验证要求、货期与成本影响"})
        elif not item.get("source_locator"):
            violations.append({"type": "missing_input", "detail": "耗材 %s 合同缺 source_locator" % mid})
        elif isinstance(window, dict) and _num(window.get("value")) and _num(item.get("lead_time")):
            if item.get("unit") != window.get("unit"):
                violations.append({"type": "time_window_conflict", "detail": "耗材 %s 货期单位不一致" % mid})
            elif item["lead_time"] > window["value"]:
                violations.append({"type": "time_window_conflict", "detail": "耗材 %s 货期超过时间窗" % mid})
    clipped = []
    parameter_costs = spec.get("parameter_costs") or {}
    for p in d.get("parameters") or []:
        lim = (spec.get("limits") or {}).get(p.get("name"))
        if not isinstance(lim, dict):
            violations.append({"type": "missing_input", "detail": "参数 %s 无设备/材料限值" % p.get("name")})
            continue
        if all(_num(x) for x in (p.get("min"), p.get("max"), lim.get("min"), lim.get("max"))) and p.get("unit") == lim.get("unit"):
            lo, device_hi = max(p["min"], lim["min"]), min(p["max"], lim["max"])
            hi = device_hi
            budget_cap = None
            model = parameter_costs.get(p.get("name"))
            if model is not None:
                if (not isinstance(model, dict) or not _num(model.get("fixed_other_cost")) or
                        not _num(model.get("cost_per_unit")) or model.get("cost_per_unit") <= 0 or
                        not model.get("source_locator") or not model.get("currency")):
                    violations.append({"type": "missing_input", "detail": "参数 %s 预算成本模型不完整" % p.get("name")})
                elif isinstance(budget, dict) and _num(budget.get("amount")):
                    if model.get("currency") != budget.get("currency"):
                        violations.append({"type": "missing_input", "detail": "参数 %s 成本模型与预算币种不一致" % p.get("name")})
                    else:
                        budget_cap = (budget["amount"] - model["fixed_other_cost"]) / model["cost_per_unit"]
                        hi = min(hi, budget_cap)
            item = {"parameter": p.get("name"), "allowed_range": [lo, hi] if lo <= hi else None,
                    "unit": p.get("unit"), "source_locator": lim.get("source_locator"),
                    "device_max": device_hi, "requires_confirmation": True}
            if budget_cap is not None:
                item.update(budget_max=budget_cap, cost_source_locator=model.get("source_locator"))
            clipped.append(item)
            budget_binding = budget_cap is not None and budget_cap <= device_hi
            kind = "budget_exceeded" if budget_binding else "parameter_window_conflict"
            if lo > hi:
                violations.append({"type": kind, "detail": "参数 %s 可行域交集为空" % p.get("name"),
                                   "action": "更换设备/参数路线或调整预算；不能仅把 value 截到边界后宣称等效"})
            elif not _num(p.get("value")) or p.get("value") < lo or p.get("value") > hi:
                violations.append({"type": kind, "detail": "参数 %s 当前值被设备/预算约束阻断" % p.get("name"),
                                   "action": "仅在 allowed_range 内重取样并复核科学等效性；变更须人工确认"})
    for item in _parameter_violations(d.get("parameters"), spec.get("limits") or {}):
        if "未声明" not in item.get("issue", ""):
            violations.append({"type": "parameter_window_conflict", "detail": item})
    exception_types = {e.get("type"): e for e in d.get("exceptions") or [] if isinstance(e, dict)}
    for v in violations:
        if v["type"] in {"equipment_unavailable", "material_unavailable", "time_window_conflict", "budget_exceeded", "parameter_window_conflict"}:
            record = exception_types.get(v["type"])
            if not record:
                issues.append("缺 exceptions.%s 处置记录" % v["type"])
            else:
                for key in ("trigger", "action", "alternative_path", "impact", "decision_owner", "status"):
                    if not record.get(key):
                        issues.append("exceptions.%s 缺 %s" % (v["type"], key))
    return _out(not issues and not violations, errors=issues, violations=violations,
                clipped_parameter_domains=clipped, recommendations=recommendations,
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
        if argv[0] == "controls" and len(argv) == 2:
            return cmd_controls(argv[1])
        if argv[0] == "optimize" and len(argv) == 4 and argv[2] == "--spec":
            return cmd_optimize(argv[1], argv[3])
        if argv[0] == "schema" and len(argv) == 2:
            return cmd_schema(argv[1])
        print(__doc__)
        return 2
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        _out(False, errors=["输入/调用错误：%s" % exc])
        return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
