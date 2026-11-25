#!/usr/bin/env python3
"""Versioned feasibility review; Python standard library only.

Commands:
  audit RESULT                        seven checks, evidence, exceptions and gain contract
  resources RESULT                    equipment/material/sample/time/budget arithmetic
  params RESULT --spec LIMITS         intersect limits and inverse-check recommended values
  verify RESULT --source-root DIR     verify SHA-256, JSON pointers and verbatim quotes
  gain BASELINE SKILL --out OUTPUT    same-input/same-permission measured comparison
  schema RESULT                       alias for audit
"""
import copy
import hashlib
import json
import math
import os
import re
import sys
from decimal import Decimal, InvalidOperation

TOOL_VERSION = "feasibility-exp-tool-3.0.0"
SCHEMA_VERSION = "feasibility-result-3.0.0"
CATEGORIES = ["假设与变量", "对照组", "设备材料", "时间成本", "参数范围", "风险与异常", "伦理与安全"]
EXCEPTIONS = {
    "plan_missing_pages", "missing_parameters", "unknown_equipment",
    "ethics_undetermined", "internal_contradiction", "oversized_document",
    "device_failure", "material_batch_variation", "insufficient_sample",
    "parameter_out_of_range",
}
HEX64 = re.compile(r"^[0-9a-f]{64}$")


def _bad_constant(value):
    raise ValueError("non-finite JSON number: " + value)


def load(path):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle, parse_constant=_bad_constant)


def dump_line(obj):
    print(json.dumps(obj, ensure_ascii=False, sort_keys=True))


def dec(value, label, errors):
    if isinstance(value, bool) or value is None:
        errors.append(label + " 必须为有限数值")
        return None
    try:
        result = Decimal(str(value))
        if not result.is_finite():
            raise InvalidOperation
        return result
    except (InvalidOperation, ValueError, TypeError):
        errors.append(label + " 必须为有限数值")
        return None


def sha_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1048576), b""):
            h.update(block)
    return h.hexdigest()


def evidence_errors(evidence, label):
    errors = []
    if not isinstance(evidence, list) or not evidence:
        return [label + " 至少一条 evidence"]
    for i, ev in enumerate(evidence):
        where = "%s[%d]" % (label, i)
        if not isinstance(ev, dict):
            errors.append(where + " 必须为对象")
            continue
        for key in ("source_id", "location", "quote", "sha256"):
            if not isinstance(ev.get(key), str) or not ev.get(key):
                errors.append(where + "." + key + " 缺失")
        if not HEX64.match(str(ev.get("sha256", ""))):
            errors.append(where + ".sha256 必须为64位小写十六进制")
    return errors


def all_evidence(d):
    for i, item in enumerate(d.get("judgments") or []):
        yield "judgments[%d].evidence" % i, item.get("evidence")
    for i, item in enumerate((d.get("feasibility") or {}).get("checks") or []):
        if item.get("status") != "not_checked":
            yield "feasibility.checks[%d].evidence" % i, item.get("evidence")
    resources = d.get("resources") or {}
    for key in ("equipment", "materials"):
        for i, item in enumerate(resources.get(key) or []):
            if item.get("availability") != "not_checked":
                yield "resources.%s[%d].evidence" % (key, i), item.get("evidence")


def gain_errors(d):
    errors = []
    gain = d.get("gain")
    if not isinstance(gain, dict):
        return ["gain 必须为对象"]
    design = gain.get("design") or {}
    if design.get("same_case_id") != d.get("case_id"):
        errors.append("gain.design.same_case_id 必须等于 case_id")
    if design.get("same_input_digest") != d.get("input_digest"):
        errors.append("gain.design.same_input_digest 必须等于 input_digest")
    if design.get("same_permissions") is not True:
        errors.append("gain.design.same_permissions 必须为 true")
    if not isinstance(design.get("repetitions"), int) or design.get("repetitions") < 1:
        errors.append("gain.design.repetitions 必须为正整数")
    status = gain.get("status")
    if status not in ("completed", "not_run"):
        errors.append("gain.status 必须为 completed|not_run")
    if status == "not_run" and not gain.get("reason"):
        errors.append("gain.status=not_run 时必须填 reason")
    for section in ("quality", "efficiency"):
        if not isinstance(gain.get(section), dict):
            errors.append("gain." + section + " 必须为对象")
    if status == "completed":
        for key in ("baseline_review_coverage", "skill_review_coverage",
                    "baseline_located_judgments", "skill_located_judgments"):
            if dec(gain.get("quality", {}).get(key), "gain.quality." + key, []) is None:
                errors.append("completed gain 缺质量实测值 " + key)
        if gain.get("quality", {}).get("same_rubric") is not True:
            errors.append("completed gain 必须 same_rubric=true")
    return errors


def validate_result(d):
    errors = []
    if not isinstance(d, dict):
        return ["顶层必须为对象"], {"seven_checks": {}, "exception_coverage": {}}
    required = ["case_id", "status", "plan_version", "result_schema_version", "tool_version",
                "input_digest", "permissions_digest", "research_goal", "variables", "controls",
                "steps", "resources", "parameters", "risks", "judgments", "expert_confirmation",
                "gain", "unchecked", "sources", "uncertainty", "change_log", "feasibility",
                "exception_register"]
    errors += ["缺顶层字段 " + key for key in required if key not in d]
    if d.get("status") not in {"pass", "issues", "partial", "failed"}:
        errors.append("status 非法")
    if d.get("result_schema_version") != SCHEMA_VERSION:
        errors.append("result_schema_version 必须为 " + SCHEMA_VERSION)
    if d.get("tool_version") != TOOL_VERSION:
        errors.append("tool_version 必须为 " + TOOL_VERSION)
    if not d.get("plan_version"):
        errors.append("plan_version 为空")
    for key in ("input_digest", "permissions_digest"):
        if not HEX64.match(str(d.get(key, ""))):
            errors.append(key + " 必须为64位SHA-256十六进制")
    sources = d.get("sources") or []
    ids = set()
    for i, source in enumerate(sources):
        sid = source.get("source_id") if isinstance(source, dict) else None
        if not sid or sid in ids:
            errors.append("sources[%d].source_id 缺失或重复" % i)
        ids.add(sid)
        if not HEX64.match(str(source.get("sha256", "")) if isinstance(source, dict) else ""):
            errors.append("sources[%d].sha256 非法" % i)
    for label, evidence in all_evidence(d):
        errors += evidence_errors(evidence, label)
        if isinstance(evidence, list):
            for ev in evidence:
                if isinstance(ev, dict) and ev.get("source_id") not in ids:
                    errors.append(label + " 引用了未登记 source_id")
    checks = (d.get("feasibility") or {}).get("checks") or []
    found = {}
    for i, check in enumerate(checks):
        category = check.get("category")
        found[category] = found.get(category, 0) + 1
        if check.get("status") not in {"pass", "fail", "conditional", "not_checked"}:
            errors.append("feasibility.checks[%d].status 非法" % i)
        if not check.get("target"):
            errors.append("feasibility.checks[%d].target 缺定位" % i)
        if not check.get("conclusion"):
            errors.append("feasibility.checks[%d].conclusion 缺失" % i)
        if check.get("status") == "not_checked" and not check.get("reason"):
            errors.append("feasibility.checks[%d] not_checked 缺 reason" % i)
        if check.get("status") == "conditional" and not check.get("conditions"):
            errors.append("feasibility.checks[%d] conditional 缺可执行 conditions" % i)
    for category in CATEGORIES:
        if found.get(category) != 1:
            errors.append("七类检查必须且仅一次: " + category)
    feasibility = d.get("feasibility") or {}
    if feasibility.get("overall") not in {"feasible", "conditionally_feasible", "infeasible", "partial"}:
        errors.append("feasibility.overall 非法")
    if feasibility.get("overall") == "conditionally_feasible" and not feasibility.get("conditions"):
        errors.append("有条件可行必须写 conditions")
    if any(c.get("status") == "fail" for c in checks) and feasibility.get("overall") == "feasible":
        errors.append("存在 fail 时 overall 不能为 feasible")
    if any(c.get("status") == "not_checked" for c in checks) and feasibility.get("overall") in {"feasible", "conditionally_feasible"}:
        errors.append("存在 not_checked 时 overall 必须为 partial|infeasible")
    register = d.get("exception_register") or []
    codes = {}
    for i, item in enumerate(register):
        code = item.get("code")
        codes[code] = codes.get(code, 0) + 1
        for key in ("signal", "action", "owner"):
            if not item.get(key):
                errors.append("exception_register[%d] 缺 %s" % (i, key))
        if item.get("disposition") not in {"downgrade", "label", "manual", "stop"}:
            errors.append("exception_register[%d].disposition 非法" % i)
        targets = item.get("linked_checks")
        if not isinstance(targets, list) or not targets or any(t not in CATEGORIES for t in targets):
            errors.append("exception_register[%d].linked_checks 必须绑定七类检查" % i)
    for code in sorted(EXCEPTIONS):
        if codes.get(code) != 1:
            errors.append("异常必须且仅登记一次: " + code)
    for i, risk in enumerate(d.get("risks") or []):
        for key in ("trigger", "mitigation", "stop_rule"):
            if not risk.get(key):
                errors.append("risks[%d] 缺 %s" % (i, key))
    for i, variable in enumerate(d.get("variables") or []):
        if variable.get("type") not in {"independent", "dependent", "confounder"}:
            errors.append("variables[%d].type 非法" % i)
        for key in ("operational_definition", "unit", "range"):
            if not variable.get(key):
                errors.append("variables[%d] 缺 %s" % (i, key))
    for i, control in enumerate(d.get("controls") or []):
        if not control.get("confounder_excluded"):
            errors.append("controls[%d] 缺 confounder_excluded" % i)
    errors += gain_errors(d)
    return errors, {"seven_checks": found, "exception_coverage": codes}


def resource_check(d):
    errors, computed = [], {}
    resources = d.get("resources") or {}
    allowed = {"available", "outsource", "purchase", "unavailable", "not_checked"}
    for i, eq in enumerate(resources.get("equipment") or []):
        label = "resources.equipment[%d]" % i
        state = eq.get("availability")
        if state not in allowed:
            errors.append(label + ".availability 非法")
        if state == "not_checked":
            if not eq.get("reason"):
                errors.append(label + " not_checked 缺 reason")
        else:
            for key in ("requirement", "model", "inventory_ref"):
                if not eq.get(key):
                    errors.append(label + " 缺 " + key)
            if state == "available" and (eq.get("precision") is None or not eq.get("unit") or "required_accessories" not in eq):
                errors.append(label + " available 必须给 precision/unit/required_accessories")
            errors += evidence_errors(eq.get("evidence"), label + ".evidence")
    purchase_leads = []
    for i, mat in enumerate(resources.get("materials") or []):
        label = "resources.materials[%d]" % i
        state = mat.get("availability")
        if state not in allowed:
            errors.append(label + ".availability 非法")
        if state == "not_checked":
            if not mat.get("reason"):
                errors.append(label + " not_checked 缺 reason")
            continue
        errors += evidence_errors(mat.get("evidence"), label + ".evidence")
        req = dec(mat.get("required_qty"), label + ".required_qty", errors)
        avail = dec(mat.get("available_qty"), label + ".available_qty", errors)
        lead = dec(mat.get("lead_time_hours"), label + ".lead_time_hours", errors)
        if not mat.get("unit"):
            errors.append(label + " 缺 unit")
        if req is not None and avail is not None:
            computed[label + ".shortage"] = str(max(Decimal(0), req - avail))
            if state == "available" and avail < req:
                errors.append(label + " 标 available 但库存不足")
        if state == "purchase" and lead is not None:
            purchase_leads.append(lead)
    sample = resources.get("sample") or {}
    if sample.get("availability") == "not_checked":
        if not sample.get("reason"):
            errors.append("resources.sample not_checked 缺 reason")
    else:
        req = dec(sample.get("required"), "resources.sample.required", errors)
        avail = dec(sample.get("available"), "resources.sample.available", errors)
        if not sample.get("unit") or not sample.get("source") or not sample.get("storage"):
            errors.append("resources.sample 缺 unit/source/storage")
        if req is not None and avail is not None:
            computed["sample_shortage"] = str(max(Decimal(0), req - avail))
            if sample.get("availability") == "available" and avail < req:
                errors.append("样本标 available 但数量不足")
    cost = resources.get("cost_estimate") or {}
    currency = cost.get("currency")
    if not currency:
        errors.append("cost_estimate.currency 缺失")
    total = Decimal(0)
    for i, line in enumerate(cost.get("line_items") or []):
        label = "cost_estimate.line_items[%d]" % i
        qty = dec(line.get("quantity"), label + ".quantity", errors)
        unit = dec(line.get("unit_cost"), label + ".unit_cost", errors)
        subtotal = dec(line.get("subtotal"), label + ".subtotal", errors)
        if None not in (qty, unit, subtotal):
            expected = qty * unit
            if subtotal != expected:
                errors.append(label + ".subtotal 算术错误，应为 " + str(expected))
            total += expected
    declared_total = dec(cost.get("total"), "cost_estimate.total", errors)
    if declared_total is not None and declared_total != total:
        errors.append("cost_estimate.total 应为 " + str(total))
    budget = dec(cost.get("budget"), "cost_estimate.budget", errors)
    if budget is not None:
        computed["budget_remaining"] = str(budget - total)
        if cost.get("within_budget") is not (budget >= total):
            errors.append("cost_estimate.within_budget 与真值不符")
        if budget < total:
            errors.append("预算超支")
    schedule = resources.get("time_estimate") or {}
    if schedule.get("status") == "not_checked":
        if not schedule.get("reason"):
            errors.append("time_estimate not_checked 缺 reason")
    else:
        groups = {}
        labor = Decimal(0)
        equipment = Decimal(0)
        for i, step in enumerate(schedule.get("steps") or []):
            label = "time_estimate.steps[%d]" % i
            vals = {}
            for key in ("equipment_hours", "labor_hours", "wait_hours", "turnaround_hours"):
                vals[key] = dec(step.get(key), label + "." + key, errors)
            if None not in vals.values():
                duration = max(vals["equipment_hours"], vals["labor_hours"]) + vals["wait_hours"] + vals["turnaround_hours"]
                actual = dec(step.get("duration_hours"), label + ".duration_hours", errors)
                if actual is not None and actual != duration:
                    errors.append(label + ".duration_hours 应为 " + str(duration))
                group = str(step.get("parallel_group", step.get("id", i)))
                groups[group] = max(groups.get(group, Decimal(0)), duration)
                labor += vals["labor_hours"]
                equipment += vals["equipment_hours"]
        procurement = max(purchase_leads) if purchase_leads else Decimal(0)
        expected_elapsed = procurement + sum(groups.values(), Decimal(0))
        computed.update({"procurement_wait_hours": str(procurement), "serial_group_hours": {k: str(v) for k, v in groups.items()},
                         "labor_hours": str(labor), "equipment_hours": str(equipment), "expected_elapsed_hours": str(expected_elapsed)})
        elapsed = dec(schedule.get("elapsed_hours"), "time_estimate.elapsed_hours", errors)
        if elapsed is not None and elapsed != expected_elapsed:
            errors.append("time_estimate.elapsed_hours 应为采购最长等待+并行组关键路径=" + str(expected_elapsed))
        deadline = dec(schedule.get("deadline_hours"), "time_estimate.deadline_hours", errors)
        if deadline is not None:
            computed["deadline_remaining_hours"] = str(deadline - expected_elapsed)
            if schedule.get("within_deadline") is not (expected_elapsed <= deadline):
                errors.append("time_estimate.within_deadline 与真值不符")
            if expected_elapsed > deadline:
                errors.append("预计工期超截止时间")
    for key in ("ethics", "safety"):
        item = resources.get(key) or {}
        if item.get("status") not in {"approved", "pending", "not_required", "not_checked"}:
            errors.append("resources.%s.status 非法" % key)
        if item.get("status") in {"pending", "not_checked"} and not item.get("action"):
            errors.append("resources.%s 未批准/未知时缺 action，禁止放行" % key)
    return errors, computed


def parameter_check(d, spec):
    violations, derived = [], {}
    limits = spec.get("limits") or {}
    parameters = d.get("parameters") or []
    selected = {p.get("name") for p in parameters if p.get("selected", True)}
    for i, p in enumerate(parameters):
        name = p.get("name")
        label = "parameters[%d]" % i
        raw = limits.get(name)
        rows = raw if isinstance(raw, list) else ([raw] if raw else [])
        if not rows:
            violations.append({"param": name, "issue": "spec 未声明限值，not_checked；须补设备/材料/安全来源"})
            continue
        lows, highs = [], []
        unit = p.get("unit")
        for j, lim in enumerate(rows):
            where = "%s.limit[%d]" % (name, j)
            if lim.get("unit") != unit:
                violations.append({"param": name, "issue": where + " 单位不一致", "spec_unit": lim.get("unit"), "doc_unit": unit})
            if not lim.get("source"):
                violations.append({"param": name, "issue": where + " 缺来源"})
            lo = dec(lim.get("min"), where + ".min", violations)
            hi = dec(lim.get("max"), where + ".max", violations)
            if lo is not None:
                lows.append(lo)
            if hi is not None:
                highs.append(hi)
        if not lows or not highs:
            violations.append({"param": name, "issue": "上下限必须均为有限数值"})
            continue
        lo, hi = max(lows), min(highs)
        derived[name] = {"min": str(lo), "max": str(hi)}
        if lo > hi:
            violations.append({"param": name, "issue": "约束交集为空", "derived_min": str(lo), "derived_max": str(hi)})
        value = dec(p.get("value"), label + ".value", violations)
        declared_lo = dec(p.get("derived_min"), label + ".derived_min", violations)
        declared_hi = dec(p.get("derived_max"), label + ".derived_max", violations)
        if declared_lo is not None and declared_lo != lo:
            violations.append({"param": name, "issue": "derived_min 反推错误", "expected": str(lo)})
        if declared_hi is not None and declared_hi != hi:
            violations.append({"param": name, "issue": "derived_max 反推错误", "expected": str(hi)})
        if value is not None:
            if value < lo or value > hi:
                violations.append({"param": name, "issue": "推荐值越出多约束交集", "value": str(value), "interval": [str(lo), str(hi)]})
            for lim in rows:
                step = dec(lim.get("step", 0), name + ".step", violations)
                base = dec(lim.get("min"), name + ".min", violations)
                if step is not None and base is not None:
                    if step <= 0:
                        violations.append({"param": name, "issue": "step 必须>0"})
                    elif (value - base) % step != 0:
                        violations.append({"param": name, "issue": "不满足步进", "step": str(step), "anchor": str(base)})
        errors = evidence_errors(p.get("evidence"), label + ".evidence")
        violations += [{"param": name, "issue": e} for e in errors]
        for lim in rows:
            for other in lim.get("mutex_with") or []:
                if other in selected and p.get("selected", True):
                    violations.append({"param": name, "issue": "与已选参数互斥", "other": other})
    return violations, derived


def pointer(root, location):
    if not location.startswith("#/"):
        raise ValueError("not a JSON pointer")
    node = root
    for token in location[2:].split("/"):
        token = token.replace("~1", "/").replace("~0", "~")
        node = node[int(token)] if isinstance(node, list) else node[token]
    return node


def verify_files(d, root):
    errors, checked = [], 0
    root = os.path.realpath(root)
    source_map = {s.get("source_id"): s for s in d.get("sources") or [] if isinstance(s, dict)}
    cache = {}
    for sid, source in source_map.items():
        path = source.get("path")
        if not path:
            errors.append("source %s 缺相对 path" % sid)
            continue
        full = os.path.realpath(os.path.join(root, path))
        if os.path.commonpath([root, full]) != root:
            errors.append("source %s 路径越出 source-root" % sid)
            continue
        try:
            actual = sha_file(full)
            if actual != source.get("sha256"):
                errors.append("source %s SHA-256 不匹配" % sid)
            text_path = source.get("text_path", path)
            text_full = os.path.realpath(os.path.join(root, text_path))
            if os.path.commonpath([root, text_full]) != root:
                errors.append("source %s text_path 越界" % sid)
                continue
            with open(text_full, encoding="utf-8") as handle:
                raw = handle.read()
            parsed = json.loads(raw) if text_full.endswith(".json") else None
            cache[sid] = (raw, parsed, actual)
        except (OSError, UnicodeError, ValueError) as exc:
            errors.append("source %s 不可读/不可解析: %s" % (sid, exc))
    for label, evidence in all_evidence(d):
        for ev in evidence or []:
            if not isinstance(ev, dict):
                continue
            sid = ev.get("source_id")
            if sid not in cache:
                errors.append(label + " source 不可核验: " + str(sid))
                continue
            raw, parsed, source_hash = cache[sid]
            if ev.get("sha256") != source_hash:
                errors.append(label + " evidence SHA-256 与源文件不符")
            quote = ev.get("quote", "")
            location = ev.get("location", "")
            try:
                if location.startswith("#/") and parsed is not None:
                    value = pointer(parsed, location)
                    if isinstance(value, str):
                        match = value == quote
                    else:
                        match = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) == quote
                    if not match:
                        errors.append(label + " JSON指针值不等于逐字 quote: " + location)
                elif quote not in raw:
                    errors.append(label + " quote 不是源文本逐字子串: " + location)
                checked += 1
            except (KeyError, IndexError, TypeError, ValueError) as exc:
                errors.append(label + " 定位失败: " + str(exc))
    return errors, checked


def coverage(d):
    checks = (d.get("feasibility") or {}).get("checks") or []
    complete = sum(1 for c in checks if c.get("category") in CATEGORIES and c.get("status") in {"pass", "fail", "conditional"})
    located = sum(1 for j in d.get("judgments") or [] if not evidence_errors(j.get("evidence"), "evidence"))
    exceptions = len({e.get("code") for e in d.get("exception_register") or []} & EXCEPTIONS)
    return {"review_coverage": complete, "located_judgments": located, "exceptions_covered": exceptions}


def make_gain(base, skill):
    if base.get("case_id") != skill.get("case_id"):
        raise ValueError("baseline 与 Skill 的 case_id 不同，拒绝不公平对照")
    if base.get("input_digest") != skill.get("input_digest"):
        raise ValueError("input_digest 不同，拒绝不公平对照")
    if base.get("permissions_digest") != skill.get("permissions_digest"):
        raise ValueError("permissions_digest 不同，拒绝不公平对照")
    b, s = coverage(base), coverage(skill)
    quality = {"same_rubric": True, "rubric": "seven checks + evidence syntax + ten named exceptions",
               "baseline_review_coverage": b["review_coverage"], "skill_review_coverage": s["review_coverage"],
               "baseline_located_judgments": b["located_judgments"], "skill_located_judgments": s["located_judgments"],
               "baseline_exceptions_covered": b["exceptions_covered"], "skill_exceptions_covered": s["exceptions_covered"]}
    efficiency = {"measurement_status": "not_measured", "baseline_runtime_s": None, "skill_runtime_s": None,
                  "baseline_rework_rounds": None, "skill_rework_rounds": None}
    bt, st = base.get("telemetry") or {}, skill.get("telemetry") or {}
    for key, target in (("runtime_s", "runtime_s"), ("rework_rounds", "rework_rounds"), ("material_request_rounds", "material_request_rounds")):
        if isinstance(bt.get(key), (int, float)) and not isinstance(bt.get(key), bool) and isinstance(st.get(key), (int, float)) and not isinstance(st.get(key), bool):
            efficiency["baseline_" + target] = bt[key]
            efficiency["skill_" + target] = st[key]
            efficiency["measurement_status"] = "measured"
    return {"status": "completed", "reason": None,
            "design": {"same_case_id": skill.get("case_id"), "same_input_digest": skill.get("input_digest"),
                       "same_permissions": True, "permissions_digest": skill.get("permissions_digest"), "repetitions": 1},
            "quality": quality, "efficiency": efficiency}


def main(argv):
    if not argv:
        print(__doc__)
        return 2
    cmd = argv[0]
    try:
        if cmd in {"audit", "check", "schema"}:
            d = load(argv[1])
            errors, coverage_data = validate_result(d)
            dump_line({"ok": not errors, "tool_version": TOOL_VERSION, **coverage_data, "errors": errors})
            return 0 if not errors else 1
        if cmd == "resources":
            errors, computed = resource_check(load(argv[1]))
            dump_line({"ok": not errors, "computed": computed, "errors": errors})
            return 0 if not errors else 1
        if cmd == "params":
            if "--spec" not in argv:
                dump_line({"ok": False, "errors": ["params 需要 --spec"]})
                return 2
            violations, derived = parameter_check(load(argv[1]), load(argv[argv.index("--spec") + 1]))
            dump_line({"ok": not violations, "derived_intersections": derived, "violations": violations})
            return 0 if not violations else 1
        if cmd == "verify":
            if "--source-root" not in argv:
                dump_line({"ok": False, "errors": ["verify 需要 --source-root"]})
                return 2
            errors, checked = verify_files(load(argv[1]), argv[argv.index("--source-root") + 1])
            dump_line({"ok": not errors, "verified_evidence": checked, "errors": errors})
            return 0 if not errors else 1
        if cmd == "gain":
            out = argv[argv.index("--out") + 1]
            result = copy.deepcopy(load(argv[2]))
            result["gain"] = make_gain(load(argv[1]), result)
            with open(out, "w", encoding="utf-8") as handle:
                json.dump(result, handle, ensure_ascii=False, indent=2, sort_keys=True)
                handle.write("\n")
            dump_line({"ok": True, "out": out, "gain": result["gain"]})
            return 0
        print(__doc__)
        return 2
    except (OSError, ValueError, KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
        dump_line({"ok": False, "command": cmd, "error": str(exc), "action": "标记 failed/not_checked，不猜测输入"})
        return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
