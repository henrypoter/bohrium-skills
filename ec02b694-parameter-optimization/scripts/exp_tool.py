#!/usr/bin/env python3
"""Constraint-aware bounded parameter optimization; standard library only.

Commands:
  optimize PROBLEM --out OPTIMIZATION   exhaustive finite grid + constraints + Pareto + cost
  replay PROBLEM RESULT                 recompute and byte-compare result.optimization
  audit RESULT                          versions, evidence, metrics/search/cost/exceptions/gain
  params RESULT --spec LIMITS           inverse-check limits, steps and selected values
  verify RESULT --source-root DIR       SHA-256 + JSON pointer/verbatim quote validation
  gain BASELINE SKILL --out OUTPUT      fair same-input measured quality/efficiency record
  schema RESULT                         alias for audit

The optimizer evaluates only models explicitly supplied in PROBLEM. It does not invent
scientific responses or call measured predictions observations. All arithmetic uses Decimal.
"""
import copy
import hashlib
import itertools
import json
import os
import re
import sys
from decimal import Decimal, InvalidOperation, getcontext

getcontext().prec = 28
TOOL_VERSION = "parameter-exp-tool-3.0.0"
SCHEMA_VERSION = "parameter-result-3.0.0"
OPT_SCHEMA = "bounded-grid-optimization-1.0.0"
EXCEPTIONS = {"no_feasible_solution", "conflicting_constraints", "missing_data",
              "equipment_error", "conflicting_metrics", "insufficient_permissions"}
HEX64 = re.compile(r"^[0-9a-f]{64}$")


def reject_constant(value):
    raise ValueError("non-finite JSON number: " + value)


def load(path):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle, parse_constant=reject_constant)


def emit(value):
    print(json.dumps(value, ensure_ascii=False, sort_keys=True))


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def object_hash(value):
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def file_hash(path):
    h = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1048576), b""):
            h.update(block)
    return h.hexdigest()


def dec(value, label, errors):
    if value is None or isinstance(value, bool):
        errors.append(label + " 必须为有限数值")
        return None
    try:
        number = Decimal(str(value))
        if not number.is_finite():
            raise InvalidOperation
        return number
    except (InvalidOperation, ValueError, TypeError):
        errors.append(label + " 必须为有限数值")
        return None


def decimal_text(value):
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def linear(model, values, label, errors):
    if not isinstance(model, dict):
        errors.append(label + " 缺显式线性模型")
        return None
    answer = dec(model.get("intercept"), label + ".intercept", errors)
    coefficients = model.get("coefficients")
    if not isinstance(coefficients, dict):
        errors.append(label + ".coefficients 必须为对象")
        return answer
    for name, coefficient in coefficients.items():
        if name not in values:
            errors.append(label + " 引用了未声明参数 " + name)
            continue
        c = dec(coefficient, label + ".coefficients." + name, errors)
        if answer is not None and c is not None:
            answer += c * values[name]
    return answer


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
            errors.append(where + ".sha256 非法")
    return errors


def evidence_items(d):
    for i, row in enumerate(d.get("judgments") or []):
        yield "judgments[%d].evidence" % i, row.get("evidence")
    for i, row in enumerate(d.get("parameters") or []):
        yield "parameters[%d].evidence" % i, row.get("evidence")
    for i, row in enumerate(d.get("response_metrics") or []):
        yield "response_metrics[%d].evidence" % i, row.get("evidence")


def validate_problem(problem):
    errors = []
    if not isinstance(problem, dict):
        return ["problem 顶层必须为对象"]
    for key in ("problem_version", "parameters", "limits", "responses", "costs", "search"):
        if key not in problem:
            errors.append("problem 缺 " + key)
    parameters = problem.get("parameters") or {}
    if not parameters:
        errors.append("至少一个有限参数域")
    domains = {}
    total = 1
    for name, row in parameters.items():
        values = row.get("values") if isinstance(row, dict) else None
        if not isinstance(values, list) or not values:
            errors.append("parameters.%s.values 必须为非空有限数组" % name)
            continue
        if not row.get("unit"):
            errors.append("parameters.%s.unit 缺失" % name)
        domain = []
        seen = set()
        for i, value in enumerate(values):
            number = dec(value, "parameters.%s.values[%d]" % (name, i), errors)
            if number is not None:
                key = decimal_text(number)
                if key in seen:
                    errors.append("parameters.%s.values 重复 %s" % (name, key))
                seen.add(key)
                domain.append(number)
        domains[name] = domain
        total *= len(domain)
    maximum = (problem.get("search") or {}).get("max_evaluations")
    if not isinstance(maximum, int) or isinstance(maximum, bool) or maximum < 1:
        errors.append("search.max_evaluations 必须为正整数")
    elif total > maximum:
        errors.append("网格规模 %d 超过 max_evaluations=%d；拒绝静默截断" % (total, maximum))
    if (problem.get("search") or {}).get("strategy") != "exhaustive_grid":
        errors.append("本版本仅支持 strategy=exhaustive_grid，完整枚举后才可声明收敛")
    limits = problem.get("limits") or {}
    for name, domain in domains.items():
        limit = limits.get(name)
        if not isinstance(limit, dict):
            errors.append("limits.%s 缺失" % name)
            continue
        if limit.get("unit") != parameters[name].get("unit"):
            errors.append("limits.%s 单位与参数域不一致" % name)
        lo = dec(limit.get("min"), "limits.%s.min" % name, errors)
        hi = dec(limit.get("max"), "limits.%s.max" % name, errors)
        step = dec(limit.get("step"), "limits.%s.step" % name, errors)
        if not limit.get("source"):
            errors.append("limits.%s.source 缺失" % name)
        if lo is not None and hi is not None and lo > hi:
            errors.append("limits.%s min>max" % name)
        if step is not None and step <= 0:
            errors.append("limits.%s.step 必须>0" % name)
    for i, constraint in enumerate(problem.get("constraints") or []):
        label = "constraints[%d]" % i
        if not constraint.get("id") or constraint.get("op") not in {"<=", ">=", "=="}:
            errors.append(label + " 缺 id 或 op 非法")
        coefficients = constraint.get("coefficients")
        if not isinstance(coefficients, dict) or not coefficients:
            errors.append(label + ".coefficients 必须非空")
            continue
        for name, coefficient in coefficients.items():
            if name not in domains:
                errors.append(label + " 未声明参数 " + name)
            dec(coefficient, label + "." + name, errors)
        dec(constraint.get("value"), label + ".value", errors)
        if not constraint.get("source"):
            errors.append(label + ".source 缺失")
    responses = problem.get("responses") or {}
    if not responses:
        errors.append("至少一个响应指标")
    for name, response in responses.items():
        if response.get("direction") not in {"maximize", "minimize"}:
            errors.append("responses.%s.direction 非法" % name)
        weight = dec(response.get("weight"), "responses.%s.weight" % name, errors)
        if weight is not None and weight <= 0:
            errors.append("responses.%s.weight 必须>0" % name)
        if not response.get("unit"):
            errors.append("responses.%s.unit 缺失" % name)
        # Validate model shape with zero values; real evaluation repeats the arithmetic.
        linear(response.get("model"), {key: Decimal(0) for key in domains}, "responses.%s.model" % name, errors)
        for key in ("acceptable_min", "acceptable_max"):
            if key in response:
                dec(response[key], "responses.%s.%s" % (name, key), errors)
    costs = problem.get("costs") or {}
    for name in ("time_hours", "money", "samples"):
        cost = costs.get(name)
        if not isinstance(cost, dict):
            errors.append("costs.%s 缺失；时间/费用/样本必须共同权衡" % name)
            continue
        dec(cost.get("max"), "costs.%s.max" % name, errors)
        linear(cost.get("model"), {key: Decimal(0) for key in domains}, "costs.%s.model" % name, errors)
    return errors


def optimize_problem(problem):
    errors = validate_problem(problem)
    if errors:
        raise ValueError("; ".join(errors))
    names = sorted(problem["parameters"])
    domains = [[Decimal(str(v)) for v in problem["parameters"][n]["values"]] for n in names]
    rejected, feasible = [], []
    index = 0
    for combo in itertools.product(*domains):
        values = dict(zip(names, combo))
        reasons = []
        for name in names:
            limit = problem["limits"][name]
            lo, hi, step = Decimal(str(limit["min"])), Decimal(str(limit["max"])), Decimal(str(limit["step"]))
            if values[name] < lo or values[name] > hi:
                reasons.append("parameter_range:" + name)
            if (values[name] - lo) % step != 0:
                reasons.append("parameter_step:" + name)
        for constraint in problem.get("constraints") or []:
            left = sum((Decimal(str(c)) * values[n] for n, c in constraint["coefficients"].items()), Decimal(0))
            right = Decimal(str(constraint["value"]))
            op = constraint["op"]
            valid = left <= right if op == "<=" else left >= right if op == ">=" else left == right
            if not valid:
                reasons.append("constraint:" + constraint["id"])
        responses = {}
        response_values = {}
        for name, response in problem["responses"].items():
            local_errors = []
            value = linear(response["model"], values, "responses." + name, local_errors)
            if local_errors:
                raise ValueError("; ".join(local_errors))
            response_values[name] = value
            responses[name] = decimal_text(value)
            if "acceptable_min" in response and value < Decimal(str(response["acceptable_min"])):
                reasons.append("response_min:" + name)
            if "acceptable_max" in response and value > Decimal(str(response["acceptable_max"])):
                reasons.append("response_max:" + name)
        costs, cost_values = {}, {}
        for name in ("time_hours", "money", "samples"):
            row = problem["costs"][name]
            value = linear(row["model"], values, "costs." + name, [])
            cost_values[name] = value
            costs[name] = decimal_text(value)
            if value > Decimal(str(row["max"])):
                reasons.append("budget:" + name)
        row = {"index": index, "parameters": {n: decimal_text(values[n]) for n in names},
               "responses": responses, "costs": costs}
        if reasons:
            row["rejection_reasons"] = sorted(set(reasons))
            rejected.append(row)
        else:
            feasible.append((row, response_values, cost_values))
        index += 1
    response_names = sorted(problem["responses"])
    ranges = {}
    for name in response_names:
        vals = [item[1][name] for item in feasible]
        ranges[name] = (min(vals), max(vals)) if vals else (Decimal(0), Decimal(0))
    weight_sum = sum((Decimal(str(problem["responses"][n]["weight"])) for n in response_names), Decimal(0))
    scored = []
    for row, response_values, cost_values in feasible:
        desirability = {}
        utility = Decimal(0)
        for name in response_names:
            lo, hi = ranges[name]
            value = response_values[name]
            if hi == lo:
                score = Decimal(1)
            elif problem["responses"][name]["direction"] == "maximize":
                score = (value - lo) / (hi - lo)
            else:
                score = (hi - value) / (hi - lo)
            desirability[name] = decimal_text(score)
            utility += Decimal(str(problem["responses"][name]["weight"])) * score
        utility /= weight_sum
        new_row = copy.deepcopy(row)
        new_row["desirability"] = desirability
        new_row["score"] = decimal_text(utility)
        scored.append((new_row, response_values, cost_values))
    scored.sort(key=lambda item: (-Decimal(item[0]["score"]), canonical(item[0]["parameters"])))
    feasible_rows = [item[0] for item in scored]
    pareto = []
    for i, candidate in enumerate(scored):
        dominated = False
        for j, other in enumerate(scored):
            if i == j:
                continue
            better_or_equal = True
            strictly_better = False
            for name in response_names:
                a, b = candidate[1][name], other[1][name]
                direction = problem["responses"][name]["direction"]
                if direction == "maximize":
                    better_or_equal &= b >= a
                    strictly_better |= b > a
                else:
                    better_or_equal &= b <= a
                    strictly_better |= b < a
            for name in ("time_hours", "money", "samples"):
                a, b = candidate[2][name], other[2][name]
                better_or_equal &= b <= a
                strictly_better |= b < a
            if better_or_equal and strictly_better:
                dominated = True
                break
        if not dominated:
            pareto.append(candidate[0]["index"])
    recommended = feasible_rows[0] if feasible_rows else None
    return {
        "optimization_schema_version": OPT_SCHEMA,
        "tool_version": TOOL_VERSION,
        "problem_version": problem["problem_version"],
        "problem_sha256": object_hash(problem),
        "model_status": "explicit_declared_models_not_measurements",
        "search": {"strategy": "exhaustive_grid", "initial_design": "all_declared_finite_domain_points",
                   "next_round_rule": "none_after_complete_grid", "stopping_rule": "evaluated_count==domain_size"},
        "evaluated_count": index, "feasible_count": len(feasible_rows),
        "status": "complete" if recommended else "no_feasible_solution",
        "stopping_reason": "exhaustive_grid_complete" if recommended else "no_feasible_solution_after_complete_grid",
        "feasible_candidates": feasible_rows, "rejected_candidates": rejected,
        "pareto_indices": pareto, "recommended": recommended,
    }


def validate_result(d):
    errors = []
    if not isinstance(d, dict):
        return ["顶层必须为对象"], {}
    required = ["case_id", "status", "plan_version", "result_schema_version", "tool_version",
                "input_digest", "permissions_digest", "research_goal", "variables", "controls", "steps",
                "resources", "parameters", "response_metrics", "search", "cost_budget", "optimization",
                "risks", "judgments", "expert_confirmation", "gain", "unchecked", "sources",
                "uncertainty", "change_log", "exception_register"]
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
            errors.append(key + " 必须为64位SHA-256")
    ids = set()
    for i, source in enumerate(d.get("sources") or []):
        sid = source.get("source_id") if isinstance(source, dict) else None
        if not sid or sid in ids:
            errors.append("sources[%d].source_id 缺失或重复" % i)
        ids.add(sid)
        if not isinstance(source, dict) or not HEX64.match(str(source.get("sha256", ""))):
            errors.append("sources[%d].sha256 非法" % i)
    for label, evidence in evidence_items(d):
        errors += evidence_errors(evidence, label)
        if isinstance(evidence, list):
            for ev in evidence:
                if isinstance(ev, dict) and ev.get("source_id") not in ids:
                    errors.append(label + " 引用未登记 source_id")
    responses = d.get("response_metrics") or []
    if not responses:
        errors.append("response_metrics 不得为空")
    response_names = set()
    for i, response in enumerate(responses):
        label = "response_metrics[%d]" % i
        response_names.add(response.get("name"))
        for key in ("name", "unit", "measurement_method", "direction", "acceptable_variation", "model_ref"):
            if not response.get(key):
                errors.append(label + " 缺 " + key)
        if response.get("direction") not in {"maximize", "minimize"}:
            errors.append(label + ".direction 非法")
        uncertainty = response.get("uncertainty")
        if not isinstance(uncertainty, dict) or not uncertainty.get("method") or uncertainty.get("value") is None:
            errors.append(label + ".uncertainty 必须含 method/value")
    optimization = d.get("optimization") or {}
    if optimization.get("optimization_schema_version") != OPT_SCHEMA:
        errors.append("optimization_schema_version 不匹配")
    if optimization.get("tool_version") != TOOL_VERSION:
        errors.append("optimization.tool_version 不匹配")
    if not HEX64.match(str(optimization.get("problem_sha256", ""))):
        errors.append("optimization.problem_sha256 非法")
    if optimization.get("status") not in {"complete", "no_feasible_solution"}:
        errors.append("optimization.status 非法")
    if optimization.get("evaluated_count") != len(optimization.get("feasible_candidates") or []) + len(optimization.get("rejected_candidates") or []):
        errors.append("optimization.evaluated_count 与候选记录数不符")
    if optimization.get("feasible_count") != len(optimization.get("feasible_candidates") or []):
        errors.append("optimization.feasible_count 算术不符")
    if optimization.get("status") == "complete":
        recommended = optimization.get("recommended")
        if not recommended:
            errors.append("complete 但 recommended 为空")
        else:
            if set((recommended.get("responses") or {})) != response_names:
                errors.append("推荐响应与 response_metrics 名称不一致")
            if not optimization.get("feasible_candidates") or optimization["feasible_candidates"][0] != recommended:
                errors.append("recommended 必须为确定排序后的首条可行候选")
    elif optimization.get("recommended") is not None:
        errors.append("无可行解时 recommended 必须为 null")
    search = d.get("search") or {}
    for key in ("strategy", "initial_design", "stopping_rule", "stop_reason"):
        if not search.get(key):
            errors.append("search 缺 " + key)
    if search.get("evaluated_count") != optimization.get("evaluated_count"):
        errors.append("search.evaluated_count 与 optimization 不一致")
    if search.get("stop_reason") != optimization.get("stopping_reason"):
        errors.append("search.stop_reason 与 optimization 不一致")
    cost = d.get("cost_budget") or {}
    for key in ("currency", "budget", "time_budget_hours", "sample_budget"):
        if cost.get(key) is None:
            errors.append("cost_budget 缺 " + key)
    if optimization.get("recommended"):
        selected = optimization["recommended"].get("costs") or {}
        for final_key, candidate_key in (("selected_time_hours", "time_hours"), ("selected_cost", "money"), ("selected_samples", "samples")):
            if dec(cost.get(final_key), "cost_budget." + final_key, []) != dec(selected.get(candidate_key), "candidate." + candidate_key, []):
                errors.append("cost_budget.%s 与推荐候选不一致" % final_key)
    codes = {}
    for i, row in enumerate(d.get("exception_register") or []):
        code = row.get("code"); codes[code] = codes.get(code, 0) + 1
        for key in ("signal", "action", "owner"):
            if not row.get(key):
                errors.append("exception_register[%d] 缺 %s" % (i, key))
        if row.get("disposition") not in {"downgrade", "label", "manual", "stop"}:
            errors.append("exception_register[%d].disposition 非法" % i)
        targets = row.get("linked_fields")
        if not isinstance(targets, list) or not targets:
            errors.append("exception_register[%d].linked_fields 为空" % i)
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
    gain = d.get("gain") or {}
    design = gain.get("design") or {}
    if design.get("same_case_id") != d.get("case_id") or design.get("same_input_digest") != d.get("input_digest") or design.get("same_permissions") is not True:
        errors.append("gain 未绑定同 case/input/permissions")
    if not isinstance(design.get("repetitions"), int) or design.get("repetitions") < 1:
        errors.append("gain.design.repetitions 必须为正整数")
    if gain.get("status") not in {"completed", "not_run"}:
        errors.append("gain.status 非法")
    if gain.get("status") == "not_run" and not gain.get("reason"):
        errors.append("gain not_run 缺 reason")
    if not isinstance(gain.get("quality"), dict) or not isinstance(gain.get("efficiency"), dict):
        errors.append("gain.quality/efficiency 必须为对象")
    if gain.get("status") == "completed" and gain.get("quality", {}).get("same_rubric") is not True:
        errors.append("completed gain 必须 same_rubric=true")
    return errors, {"response_count": len(responses), "exception_coverage": codes,
                    "evaluated_count": optimization.get("evaluated_count"), "feasible_count": optimization.get("feasible_count")}


def parameter_check(d, spec):
    violations, derived = [], {}
    limits = spec.get("limits") or {}
    for i, parameter in enumerate(d.get("parameters") or []):
        name = parameter.get("name")
        raw = limits.get(name)
        rows = raw if isinstance(raw, list) else ([raw] if raw else [])
        if not rows:
            violations.append({"param": name, "issue": "未声明限值"})
            continue
        lows, highs = [], []
        for row in rows:
            if row.get("unit") != parameter.get("unit"):
                violations.append({"param": name, "issue": "单位不一致"})
            if not row.get("source"):
                violations.append({"param": name, "issue": "限值缺来源"})
            lo = dec(row.get("min"), name + ".min", violations)
            hi = dec(row.get("max"), name + ".max", violations)
            if lo is not None: lows.append(lo)
            if hi is not None: highs.append(hi)
        if not lows or not highs:
            violations.append({"param": name, "issue": "限值不完整"})
            continue
        lo, hi = max(lows), min(highs)
        derived[name] = {"min": decimal_text(lo), "max": decimal_text(hi)}
        if lo > hi:
            violations.append({"param": name, "issue": "约束交集为空"})
        value = dec(parameter.get("value"), name + ".value", violations)
        dlo = dec(parameter.get("derived_min"), name + ".derived_min", violations)
        dhi = dec(parameter.get("derived_max"), name + ".derived_max", violations)
        if dlo is not None and dlo != lo:
            violations.append({"param": name, "issue": "derived_min 反推错误", "expected": decimal_text(lo)})
        if dhi is not None and dhi != hi:
            violations.append({"param": name, "issue": "derived_max 反推错误", "expected": decimal_text(hi)})
        if value is not None and (value < lo or value > hi):
            violations.append({"param": name, "issue": "推荐值越出可行交集"})
        for row in rows:
            step = dec(row.get("step"), name + ".step", violations)
            base = dec(row.get("min"), name + ".min", violations)
            if value is not None and step is not None and base is not None:
                if step <= 0:
                    violations.append({"param": name, "issue": "step 必须>0"})
                elif (value - base) % step != 0:
                    violations.append({"param": name, "issue": "不满足步进"})
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
    errors, checked, cache = [], 0, {}
    root = os.path.realpath(root)
    for source in d.get("sources") or []:
        sid = source.get("source_id")
        full = os.path.realpath(os.path.join(root, source.get("path", "")))
        if os.path.commonpath([root, full]) != root:
            errors.append(sid + " 路径越界")
            continue
        try:
            actual = file_hash(full)
            if actual != source.get("sha256"):
                errors.append(sid + " 源 SHA-256 不匹配")
            text_full = os.path.realpath(os.path.join(root, source.get("text_path", source.get("path", ""))))
            if os.path.commonpath([root, text_full]) != root:
                errors.append(sid + " text_path 越界")
                continue
            with open(text_full, encoding="utf-8") as handle:
                raw = handle.read()
            parsed = json.loads(raw) if text_full.endswith(".json") else None
            cache[sid] = raw, parsed, actual
        except (OSError, ValueError, UnicodeError) as exc:
            errors.append(sid + " 不可读: " + str(exc))
    for label, evidence in evidence_items(d):
        for ev in evidence or []:
            if not isinstance(ev, dict) or ev.get("source_id") not in cache:
                errors.append(label + " source 不可核验")
                continue
            raw, parsed, actual = cache[ev["source_id"]]
            if ev.get("sha256") != actual:
                errors.append(label + " evidence SHA-256 不匹配")
            try:
                if ev.get("location", "").startswith("#/") and parsed is not None:
                    value = pointer(parsed, ev["location"])
                    expected = value if isinstance(value, str) else canonical(value)
                    if ev.get("quote") != expected:
                        errors.append(label + " quote 与 JSON 指针值不同")
                elif ev.get("quote", "") not in raw:
                    errors.append(label + " quote 不是逐字子串")
                checked += 1
            except (ValueError, KeyError, IndexError, TypeError) as exc:
                errors.append(label + " 定位失败: " + str(exc))
    return errors, checked


def quality(d):
    sections = ["research_goal", "variables", "controls", "steps", "resources", "parameters", "response_metrics", "search", "cost_budget", "risks"]
    present = sum(bool(d.get(key)) for key in sections)
    located = sum(not evidence_errors(row.get("evidence"), "evidence") for row in d.get("judgments") or [])
    exceptions = len({row.get("code") for row in d.get("exception_register") or []} & EXCEPTIONS)
    feasible = int(bool((d.get("optimization") or {}).get("recommended")))
    return {"sections_present": present, "located_judgments": located, "exceptions_covered": exceptions, "feasible_recommendation": feasible}


def make_gain(base, skill):
    if base.get("case_id") != skill.get("case_id"):
        raise ValueError("case_id 不同，拒绝不公平对照")
    if base.get("input_digest") != skill.get("input_digest"):
        raise ValueError("input_digest 不同，拒绝不公平对照")
    if base.get("permissions_digest") != skill.get("permissions_digest"):
        raise ValueError("permissions_digest 不同，拒绝不公平对照")
    b, s = quality(base), quality(skill)
    q = {"same_rubric": True, "rubric": "ten sections + evidence + six exceptions + feasible recommendation"}
    for key in b:
        q["baseline_" + key], q["skill_" + key] = b[key], s[key]
    efficiency = {"measurement_status": "not_measured", "baseline_runtime_s": None, "skill_runtime_s": None,
                  "baseline_candidate_rework": None, "skill_candidate_rework": None,
                  "baseline_rework_rounds": None, "skill_rework_rounds": None}
    bt, st = base.get("telemetry") or {}, skill.get("telemetry") or {}
    for key in ("runtime_s", "candidate_rework", "rework_rounds"):
        if isinstance(bt.get(key), (int, float)) and not isinstance(bt.get(key), bool) and isinstance(st.get(key), (int, float)) and not isinstance(st.get(key), bool):
            efficiency["baseline_" + key], efficiency["skill_" + key] = bt[key], st[key]
            efficiency["measurement_status"] = "measured"
    return {"status": "completed", "reason": None,
            "design": {"same_case_id": skill.get("case_id"), "same_input_digest": skill.get("input_digest"),
                       "same_permissions": True, "permissions_digest": skill.get("permissions_digest"), "repetitions": 1},
            "quality": q, "efficiency": efficiency}


def main(argv):
    if not argv:
        print(__doc__); return 2
    command = argv[0]
    try:
        if command == "optimize":
            out_path = argv[argv.index("--out") + 1]
            problem = load(argv[1])
            result = optimize_problem(problem)
            with open(out_path, "w", encoding="utf-8") as handle:
                json.dump(result, handle, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)
                handle.write("\n")
            emit({"ok": result["status"] == "complete", "out": out_path, "evaluated_count": result["evaluated_count"],
                  "feasible_count": result["feasible_count"], "recommended": result["recommended"], "stopping_reason": result["stopping_reason"]})
            return 0 if result["status"] == "complete" else 1
        if command == "replay":
            problem, result = load(argv[1]), load(argv[2])
            actual = result.get("optimization", result)
            expected = optimize_problem(problem)
            same = canonical(actual) == canonical(expected)
            emit({"ok": same, "expected_sha256": object_hash(expected), "actual_sha256": object_hash(actual),
                  "recommended_match": actual.get("recommended") == expected.get("recommended")})
            return 0 if same else 1
        if command in {"audit", "check", "schema"}:
            errors, details = validate_result(load(argv[1]))
            emit({"ok": not errors, **details, "errors": errors})
            return 0 if not errors else 1
        if command == "params":
            violations, derived = parameter_check(load(argv[1]), load(argv[argv.index("--spec") + 1]))
            emit({"ok": not violations, "derived_intersections": derived, "violations": violations})
            return 0 if not violations else 1
        if command == "verify":
            errors, checked = verify_files(load(argv[1]), argv[argv.index("--source-root") + 1])
            emit({"ok": not errors, "verified_evidence": checked, "errors": errors})
            return 0 if not errors else 1
        if command == "gain":
            out_path = argv[argv.index("--out") + 1]
            result = copy.deepcopy(load(argv[2]))
            result["gain"] = make_gain(load(argv[1]), result)
            with open(out_path, "w", encoding="utf-8") as handle:
                json.dump(result, handle, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)
                handle.write("\n")
            emit({"ok": True, "out": out_path, "gain": result["gain"]})
            return 0
        print(__doc__); return 2
    except (OSError, ValueError, KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
        emit({"ok": False, "command": command, "error": str(exc), "action": "标 failed/not_checked；禁止静默截断或编造响应"})
        return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
