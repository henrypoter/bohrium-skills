#!/usr/bin/env python3
"""Integrated experiment-design router and executable workflows; standard library only.

Commands:
  route --task TASK --case CASE --out ROUTING  evidence-located generation/compare/feasibility/parameter/interpretation triage
  compare COMPARISON --out OUTPUT             normalized multi-plan ranking + one-at-a-time sensitivity
  resources RESULT                            four-state resources + sample/budget/schedule arithmetic
  optimize PROBLEM --out OPTIMIZATION         exhaustive finite grid + constraints + Pareto + cost
  replay PROBLEM RESULT                       recompute and byte-compare result.optimization
  interpret OBSERVATIONS --out OUTPUT         deterministic least squares + residual/MAD anomaly flags
  audit RESULT                                route-specific contract, versions, evidence, exceptions, gain
  params RESULT --spec LIMITS                 inverse-check limits, steps and selected values
  verify RESULT --source-root DIR             SHA-256 + JSON pointer/verbatim quote validation
  gain BASELINE SKILL --out OUTPUT            fair same-input measured quality/efficiency record
  schema RESULT                               alias for audit

Scientific responses must come from actual inputs or explicit declared models. No measured
value, causal explanation, approval or baseline score is invented. Arithmetic uses Decimal.
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
TOOL_VERSION = "integrated-exp-tool-3.0.0"
SCHEMA_VERSION = "integrated-result-3.0.0"
OPT_SCHEMA = "bounded-grid-optimization-1.0.0"
ROUTE_SCHEMA = "experiment-routing-1.0.0"
COMPARISON_SCHEMA = "plan-comparison-1.0.0"
INTERPRETATION_SCHEMA = "residual-interpretation-1.0.0"
ROUTES = {"generation", "comparison", "feasibility", "parameter", "interpretation"}
BASE_EXCEPTIONS = {"unsupported_input", "tool_error", "permission_denied", "missing_data", "execution_failed"}
ROUTE_EXCEPTIONS = {
    "generation": set(),
    "comparison": {"missing_data"},
    "feasibility": {"plan_missing_pages", "missing_parameters", "unknown_equipment", "ethics_undetermined",
                    "internal_contradiction", "oversized_document", "device_failure", "material_batch_variation",
                    "insufficient_sample", "parameter_out_of_range"},
    "parameter": {"no_feasible_solution", "conflicting_constraints", "equipment_error", "conflicting_metrics", "insufficient_permissions"},
    "interpretation": {"conflicting_metrics"},
}
CATEGORIES = ["假设与变量", "对照组", "设备材料", "时间成本", "参数范围", "风险与异常", "伦理与安全"]
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
    for i, row in enumerate((d.get("feasibility") or {}).get("checks") or []):
        if row.get("status") != "not_checked":
            yield "feasibility.checks[%d].evidence" % i, row.get("evidence")
    for i, row in enumerate((d.get("routing") or {}).get("routes") or []):
        yield "routing.routes[%d].evidence" % i, row.get("evidence")


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


ROUTE_RULES = {
    "generation": [r"实验方案生成", r"生成.{0,8}(实验)?方案", r"设计.{0,8}实验", r"制定.{0,8}方案", r"提出.{0,8}方案", r"design (an )?experiment"],
    "comparison": [r"方案比较", r"比较.{0,8}方案", r"多方案", r"候选方案", r"方案选择", r"取舍", r"compare", r"rank"],
    "feasibility": [r"可行性", r"资源核验", r"能不能做", r"能否实施", r"设备可用", r"伦理审批", r"feasib"],
    "parameter": [r"参数优化", r"优化.{0,6}参数", r"参数取值", r"参数建议", r"搜索策略", r"可行域", r"bounded.parameter", r"parameter.optim"],
    "interpretation": [r"结果解释", r"解释.{0,6}结果", r"异常分析", r"异常结果", r"趋势分析", r"残差", r"归因", r"interpret", r"root.cause"],
}
ROUTE_WORKFLOW = {
    "generation": ("generate_check", "audit", "research_goal/variables/controls/steps/parameters/risks"),
    "comparison": ("compare_then_select", "compare + audit", "comparison.ranking/sensitivity/rejected"),
    "feasibility": ("versioned_feasibility_review", "resources + params + audit + verify", "seven checks/four states/budget/schedule"),
    "parameter": ("bounded_parameter_optimization", "optimize + replay + params + audit", "responses/search/cost/stopping/replay"),
    "interpretation": ("result_residual_analysis", "interpret + audit + verify", "coefficients/residuals/anomalies/follow_up"),
}


def route_task(task_path, case_path):
    with open(task_path, encoding="utf-8") as handle:
        lines = handle.read().splitlines()
    case_data = load(case_path)
    task_hash, case_hash = file_hash(task_path), file_hash(case_path)
    matches = []
    for route, patterns in ROUTE_RULES.items():
        for number, line in enumerate(lines, 1):
            if any(re.search(pattern, line, re.I) for pattern in patterns):
                matches.append((route, {"source_id": "task", "location": "task.md#L%d" % number,
                                        "quote": line, "sha256": task_hash}))
    explicit = case_data.get("task_type") if isinstance(case_data, dict) else None
    if explicit in ROUTES:
        matches.append((explicit, {"source_id": "case", "location": "#/task_type", "quote": explicit, "sha256": case_hash}))
    grouped = {route: [] for route in ROUTES}
    scores = {route: 0 for route in ROUTES}
    for route, evidence in matches:
        if evidence not in grouped[route]:
            grouped[route].append(evidence)
            scores[route] += 100 if evidence["location"] == "#/task_type" else 1
    priority = {"comparison": 0, "feasibility": 1, "parameter": 2, "interpretation": 3, "generation": 4}
    present = [route for route in ROUTES if grouped[route]]
    present.sort(key=lambda route: (-scores[route], priority[route]))
    rows = []
    for route in present:
        workflow, command, outputs = ROUTE_WORKFLOW[route]
        rows.append({"route": route, "workflow": workflow, "required_command": command,
                     "required_outputs": outputs, "score": scores[route], "evidence": grouped[route]})
    return {"route_schema_version": ROUTE_SCHEMA, "tool_version": TOOL_VERSION,
            "case_id": case_data.get("case_id") if isinstance(case_data, dict) else None,
            "task_sha256": task_hash, "case_sha256": case_hash,
            "status": "routed" if rows else "unsupported", "primary": rows[0]["route"] if rows else "unsupported",
            "routes": rows, "unmatched_action": None if rows else "停止生成并请求明确任务类型；不得默认为生成方案"}


def compare_plans(spec):
    errors = []
    candidates = spec.get("candidates") or []
    metrics = spec.get("metrics") or {}
    if not spec.get("comparison_version") or len(candidates) < 2 or not metrics:
        raise ValueError("comparison_version、至少两个候选及 metrics 必填")
    ids = set()
    eligible, rejected = [], []
    for i, candidate in enumerate(candidates):
        if not candidate.get("id") or candidate["id"] in ids or not candidate.get("plan_version"):
            errors.append("candidates[%d] id 缺失/重复或 plan_version 缺失" % i)
        ids.add(candidate.get("id"))
        values, reasons = {}, []
        if set((candidate.get("metrics") or {})) != set(metrics):
            errors.append("candidate %s 指标集合不一致" % candidate.get("id"))
            continue
        for name, rule in metrics.items():
            value = dec(candidate["metrics"].get(name), "candidate.%s.%s" % (candidate.get("id"), name), errors)
            if value is None:
                continue
            values[name] = value
            if "min" in rule and value < Decimal(str(rule["min"])):
                reasons.append("metric_min:" + name)
            if "max" in rule and value > Decimal(str(rule["max"])):
                reasons.append("metric_max:" + name)
        row = {"id": candidate["id"], "plan_version": candidate["plan_version"], "metrics": {n: decimal_text(v) for n, v in values.items()}}
        if reasons:
            row["rejection_reasons"] = reasons; rejected.append(row)
        else:
            eligible.append((candidate["id"], candidate["plan_version"], values))
    for name, rule in metrics.items():
        if rule.get("direction") not in {"maximize", "minimize"}:
            errors.append("metrics.%s.direction 非法" % name)
        weight = dec(rule.get("weight"), "metrics.%s.weight" % name, errors)
        if weight is not None and weight <= 0:
            errors.append("metrics.%s.weight 必须>0" % name)
    if errors:
        raise ValueError("; ".join(errors))
    def rank(rows, weight_override=None):
        if not rows:
            return []
        ranges = {n: (min(v[n] for _, _, v in rows), max(v[n] for _, _, v in rows)) for n in metrics}
        weights = weight_override or {n: Decimal(str(metrics[n]["weight"])) for n in metrics}
        total_weight = sum(weights.values(), Decimal(0))
        ranked = []
        for cid, version, values in rows:
            utilities = {}
            total = Decimal(0)
            for name, rule in metrics.items():
                lo, hi = ranges[name]
                if hi == lo:
                    utility = Decimal(1)
                elif rule["direction"] == "maximize":
                    utility = (values[name] - lo) / (hi - lo)
                else:
                    utility = (hi - values[name]) / (hi - lo)
                utilities[name] = decimal_text(utility)
                total += weights[name] * utility
            ranked.append({"id": cid, "plan_version": version, "metrics": {n: decimal_text(v) for n, v in values.items()},
                           "desirability": utilities, "score": decimal_text(total / total_weight)})
        ranked.sort(key=lambda row: (-Decimal(row["score"]), row["id"]))
        return ranked
    ranking = rank(eligible)
    delta = Decimal(str(spec.get("sensitivity", {}).get("weight_delta", "0.1")))
    if delta < 0:
        raise ValueError("sensitivity.weight_delta 不得为负")
    sensitivity = []
    base_weights = {n: Decimal(str(metrics[n]["weight"])) for n in metrics}
    for name in metrics:
        for sign in (-1, 1):
            weights = dict(base_weights)
            weights[name] = max(Decimal(0), weights[name] + sign * delta)
            if sum(weights.values(), Decimal(0)) == 0:
                continue
            varied = rank(eligible, weights)
            sensitivity.append({"varied_metric": name, "delta": decimal_text(sign * delta),
                                "top_id": varied[0]["id"] if varied else None,
                                "stable": bool(ranking and varied and ranking[0]["id"] == varied[0]["id"])})
    return {"comparison_schema_version": COMPARISON_SCHEMA, "tool_version": TOOL_VERSION,
            "comparison_version": spec["comparison_version"], "input_sha256": object_hash(spec),
            "evaluated_count": len(candidates), "eligible_count": len(ranking), "ranking": ranking,
            "rejected": rejected, "recommended": ranking[0] if ranking else None,
            "sensitivity": sensitivity, "status": "complete" if ranking else "no_feasible_candidate"}


def interpret_observations(spec):
    rows = spec.get("observations") or []
    if not spec.get("dataset_version") or len(rows) < 2:
        raise ValueError("dataset_version 与至少两个 observations 必填")
    errors, points = [], []
    for i, row in enumerate(rows):
        x = dec(row.get("x"), "observations[%d].x" % i, errors)
        y = dec(row.get("y"), "observations[%d].y" % i, errors)
        if x is not None and y is not None:
            points.append((row.get("id", str(i)), x, y))
    if errors:
        raise ValueError("; ".join(errors))
    if len({x for _, x, _ in points}) < 2:
        raise ValueError("x 至少两个不同值，不能拟合")
    n = Decimal(len(points)); sx = sum((x for _, x, _ in points), Decimal(0)); sy = sum((y for _, _, y in points), Decimal(0))
    mean_x, mean_y = sx / n, sy / n
    denominator = sum(((x - mean_x) ** 2 for _, x, _ in points), Decimal(0))
    slope = sum(((x - mean_x) * (y - mean_y) for _, x, y in points), Decimal(0)) / denominator
    intercept = mean_y - slope * mean_x
    residuals = []
    for oid, x, y in points:
        predicted = intercept + slope * x
        residuals.append({"id": oid, "x": decimal_text(x), "observed_y": decimal_text(y),
                          "predicted_y": decimal_text(predicted), "residual": decimal_text(y - predicted)})
    absolute = sorted(abs(y - (intercept + slope * x)) for _, x, y in points)
    middle = len(absolute) // 2
    mad = absolute[middle] if len(absolute) % 2 else (absolute[middle - 1] + absolute[middle]) / 2
    declared = dec(spec.get("absolute_residual_threshold", 0), "absolute_residual_threshold", errors)
    if errors or declared < 0:
        raise ValueError("absolute_residual_threshold 必须为有限非负数")
    threshold = max(declared, Decimal(2) * mad)
    flagged = [row["id"] for row in residuals if abs(Decimal(row["residual"])) > threshold]
    sse = sum((Decimal(row["residual"]) ** 2 for row in residuals), Decimal(0))
    sst = sum(((y - mean_y) ** 2 for _, _, y in points), Decimal(0))
    r2 = Decimal(1) if sst == 0 and sse == 0 else Decimal(0) if sst == 0 else Decimal(1) - sse / sst
    return {"interpretation_schema_version": INTERPRETATION_SCHEMA, "tool_version": TOOL_VERSION,
            "dataset_version": spec["dataset_version"], "input_sha256": object_hash(spec),
            "model_status": "descriptive_linear_fit_not_causal", "n": len(points),
            "unit": spec.get("unit", "not_declared"), "coefficients": {"intercept": decimal_text(intercept), "slope": decimal_text(slope)},
            "r2": decimal_text(r2), "residuals": residuals, "mad": decimal_text(mad),
            "absolute_anomaly_threshold": decimal_text(threshold), "flagged_anomalies": flagged,
            "follow_up": [{"signal": "observation_id in flagged_anomalies", "action": "核对原始记录和仪器状态并独立重测；不自动删除异常点，不直接给因果结论"}]}


def integrated_resource_check(d):
    errors, computed = [], {}
    resources = d.get("resources") or {}
    states = {"available", "outsource", "purchase", "unavailable", "not_checked"}
    for i, eq in enumerate(resources.get("equipment") or []):
        label = "resources.equipment[%d]" % i
        if eq.get("availability") not in states:
            errors.append(label + ".availability 必须为四态或 not_checked")
        if eq.get("availability") == "not_checked" and not eq.get("reason"):
            errors.append(label + " not_checked 缺 reason")
        if eq.get("availability") == "available":
            for key in ("model", "precision", "unit", "required_accessories", "inventory_ref"):
                if eq.get(key) is None:
                    errors.append(label + " available 缺 " + key)
    leads = []
    for i, mat in enumerate(resources.get("materials") or []):
        if mat.get("availability") not in states:
            errors.append("materials[%d].availability 非法" % i)
        req = dec(mat.get("required_qty"), "materials[%d].required_qty" % i, errors)
        avail = dec(mat.get("available_qty"), "materials[%d].available_qty" % i, errors)
        lead = dec(mat.get("lead_time_hours"), "materials[%d].lead_time_hours" % i, errors)
        if req is not None and avail is not None and mat.get("availability") == "available" and avail < req:
            errors.append("materials[%d] available 但库存不足" % i)
        if mat.get("availability") == "purchase" and lead is not None:
            leads.append(lead)
    sample = resources.get("sample") or {}
    if sample.get("availability") != "not_checked":
        req = dec(sample.get("required"), "sample.required", errors)
        avail = dec(sample.get("available"), "sample.available", errors)
        if req is not None and avail is not None:
            computed["sample_shortage"] = decimal_text(max(Decimal(0), req - avail))
            if sample.get("availability") == "available" and avail < req:
                errors.append("样本不足却标 available")
    cost = resources.get("cost_estimate") or {}
    total = Decimal(0)
    for i, line in enumerate(cost.get("line_items") or []):
        qty = dec(line.get("quantity"), "cost[%d].quantity" % i, errors)
        unit = dec(line.get("unit_cost"), "cost[%d].unit_cost" % i, errors)
        subtotal = dec(line.get("subtotal"), "cost[%d].subtotal" % i, errors)
        if None not in (qty, unit, subtotal):
            if subtotal != qty * unit:
                errors.append("cost[%d].subtotal 应为 %s" % (i, decimal_text(qty * unit)))
            total += qty * unit
    declared = dec(cost.get("total"), "cost.total", errors)
    budget = dec(cost.get("budget"), "cost.budget", errors)
    if declared is not None and declared != total:
        errors.append("cost.total 应为 " + decimal_text(total))
    if budget is not None:
        computed["budget_remaining"] = decimal_text(budget - total)
        if cost.get("within_budget") is not (budget >= total):
            errors.append("cost.within_budget 与算术不符")
        if budget < total:
            errors.append("预算超支")
    schedule = resources.get("time_estimate") or {}
    groups = {}
    for i, step in enumerate(schedule.get("steps") or []):
        vals = {k: dec(step.get(k), "step[%d].%s" % (i, k), errors) for k in ("equipment_hours", "labor_hours", "wait_hours", "turnaround_hours")}
        if None not in vals.values():
            duration = max(vals["equipment_hours"], vals["labor_hours"]) + vals["wait_hours"] + vals["turnaround_hours"]
            actual = dec(step.get("duration_hours"), "step[%d].duration_hours" % i, errors)
            if actual is not None and actual != duration:
                errors.append("step[%d].duration_hours 应为 %s" % (i, decimal_text(duration)))
            group = str(step.get("parallel_group", i))
            groups[group] = max(duration, groups.get(group, Decimal(0)))
    if schedule:
        elapsed = max(leads) if leads else Decimal(0)
        elapsed += sum(groups.values(), Decimal(0))
        computed["elapsed_hours"] = decimal_text(elapsed)
        declared_elapsed = dec(schedule.get("elapsed_hours"), "schedule.elapsed_hours", errors)
        if declared_elapsed is not None and declared_elapsed != elapsed:
            errors.append("schedule.elapsed_hours 应为采购等待+并行组关键路径 " + decimal_text(elapsed))
    for key in ("ethics", "safety"):
        status = (resources.get(key) or {}).get("status")
        if status not in {"approved", "pending", "not_required", "not_checked"}:
            errors.append("resources.%s.status 非法" % key)
        if status in {"pending", "not_checked"} and not (resources.get(key) or {}).get("action"):
            errors.append("resources.%s 未决必须给 action 并停止放行" % key)
    return errors, computed


def validate_integrated(d):
    errors = []
    if not isinstance(d, dict):
        return ["顶层必须为对象"], {}
    required = ["case_id", "status", "plan_version", "result_schema_version", "tool_version", "input_digest",
                "permissions_digest", "routing", "research_goal", "variables", "controls", "steps", "resources",
                "parameters", "risks", "judgments", "expert_confirmation", "gain", "unchecked", "sources",
                "uncertainty", "change_log", "exception_register"]
    errors += ["缺顶层字段 " + key for key in required if key not in d]
    if d.get("status") not in {"pass", "issues", "partial", "failed"}:
        errors.append("status 非法")
    if d.get("result_schema_version") != SCHEMA_VERSION or d.get("tool_version") != TOOL_VERSION:
        errors.append("result_schema_version/tool_version 不匹配")
    for key in ("input_digest", "permissions_digest"):
        if not HEX64.match(str(d.get(key, ""))):
            errors.append(key + " 非法")
    if not d.get("plan_version"):
        errors.append("plan_version 为空")
    routing = d.get("routing") or {}
    if routing.get("route_schema_version") != ROUTE_SCHEMA:
        errors.append("routing.route_schema_version 不匹配")
    if not HEX64.match(str(routing.get("task_sha256", ""))) or not HEX64.match(str(routing.get("case_sha256", ""))):
        errors.append("routing 输入哈希非法")
    route_rows = routing.get("routes") or []
    routes = [row.get("route") for row in route_rows]
    if not route_rows or any(route not in ROUTES for route in routes) or len(set(routes)) != len(routes):
        errors.append("routing.routes 必须含唯一有效路由")
    if not routes or routing.get("primary") != routes[0]:
        errors.append("routing.primary 必须为排序后首路由")
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
        for ev in evidence or []:
            if isinstance(ev, dict) and ev.get("source_id") not in ids:
                errors.append(label + " source_id 未登记")
    for i, variable in enumerate(d.get("variables") or []):
        if variable.get("type") not in {"independent", "dependent", "confounder"}:
            errors.append("variables[%d].type 非法" % i)
        for key in ("operational_definition", "unit", "range"):
            if not variable.get(key):
                errors.append("variables[%d] 缺 %s" % (i, key))
    for i, control in enumerate(d.get("controls") or []):
        if not control.get("confounder_excluded"):
            errors.append("controls[%d] 缺 confounder_excluded" % i)
    for i, risk in enumerate(d.get("risks") or []):
        for key in ("trigger", "mitigation", "stop_rule"):
            if not risk.get(key):
                errors.append("risks[%d] 缺 %s" % (i, key))
    if "generation" in routes:
        if not (d.get("research_goal") or {}).get("hypothesis") or not d.get("steps") or not d.get("parameters"):
            errors.append("generation 路由缺 hypothesis/steps/parameters")
    if "comparison" in routes:
        comparison = d.get("comparison") or {}
        if comparison.get("comparison_schema_version") != COMPARISON_SCHEMA:
            errors.append("comparison_schema_version 不匹配")
        ranking = comparison.get("ranking") or []
        if comparison.get("evaluated_count") != len(ranking) + len(comparison.get("rejected") or []):
            errors.append("comparison.evaluated_count 算术不符")
        if comparison.get("recommended") != (ranking[0] if ranking else None):
            errors.append("comparison.recommended 非首项")
        if not comparison.get("sensitivity"):
            errors.append("comparison 缺权重敏感性")
    if "feasibility" in routes:
        checks = (d.get("feasibility") or {}).get("checks") or []
        found = [row.get("category") for row in checks]
        for category in CATEGORIES:
            if found.count(category) != 1:
                errors.append("feasibility 缺或重复 " + category)
        for i, row in enumerate(checks):
            if row.get("status") not in {"pass", "fail", "conditional", "not_checked"} or not row.get("target"):
                errors.append("feasibility.checks[%d] 状态/定位非法" % i)
            if row.get("status") == "not_checked" and not row.get("reason"):
                errors.append("feasibility not_checked 缺 reason")
            if row.get("status") == "conditional" and not row.get("conditions"):
                errors.append("feasibility conditional 缺 conditions")
        if (d.get("feasibility") or {}).get("overall") == "conditionally_feasible" and not (d.get("feasibility") or {}).get("conditions"):
            errors.append("有条件可行未列 conditions")
    if "parameter" in routes:
        optimization = d.get("optimization") or {}
        if optimization.get("optimization_schema_version") != OPT_SCHEMA or optimization.get("tool_version") != TOOL_VERSION:
            errors.append("optimization 版本不匹配")
        feasible = optimization.get("feasible_candidates") or []
        if optimization.get("evaluated_count") != len(feasible) + len(optimization.get("rejected_candidates") or []):
            errors.append("optimization.evaluated_count 算术不符")
        if optimization.get("feasible_count") != len(feasible):
            errors.append("optimization.feasible_count 算术不符")
        if optimization.get("recommended") != (feasible[0] if feasible else None):
            errors.append("optimization.recommended 非确定首项")
        if not d.get("response_metrics"):
            errors.append("parameter 路由缺 response_metrics")
        for i, row in enumerate(d.get("response_metrics") or []):
            for key in ("name", "unit", "measurement_method", "direction", "acceptable_variation", "model_ref"):
                if not row.get(key):
                    errors.append("response_metrics[%d] 缺 %s" % (i, key))
            if not isinstance(row.get("uncertainty"), dict) or row["uncertainty"].get("value") is None:
                errors.append("response_metrics[%d] 缺不确定度" % i)
        if (d.get("search") or {}).get("stop_reason") != optimization.get("stopping_reason"):
            errors.append("search.stop_reason 与 optimization 不一致")
        if not d.get("cost_budget"):
            errors.append("parameter 路由缺 cost_budget")
    if "interpretation" in routes:
        interpretation = d.get("interpretation") or {}
        if interpretation.get("interpretation_schema_version") != INTERPRETATION_SCHEMA:
            errors.append("interpretation 版本不匹配")
        if interpretation.get("n") != len(interpretation.get("residuals") or []):
            errors.append("interpretation.n 与 residual 数不符")
        if not interpretation.get("follow_up"):
            errors.append("interpretation 缺异常复核动作")
    required_exceptions = set(BASE_EXCEPTIONS)
    for route in routes:
        required_exceptions |= ROUTE_EXCEPTIONS.get(route, set())
    codes = {}
    for i, row in enumerate(d.get("exception_register") or []):
        code = row.get("code"); codes[code] = codes.get(code, 0) + 1
        for key in ("signal", "action", "owner"):
            if not row.get(key):
                errors.append("exception_register[%d] 缺 %s" % (i, key))
        if row.get("disposition") not in {"downgrade", "label", "manual", "stop"} or not row.get("linked_fields"):
            errors.append("exception_register[%d] 处置或绑定字段非法" % i)
    for code in sorted(required_exceptions):
        if codes.get(code) != 1:
            errors.append("当前路由异常必须且仅一次: " + code)
    gain = d.get("gain") or {}
    design = gain.get("design") or {}
    if design.get("same_case_id") != d.get("case_id") or design.get("same_input_digest") != d.get("input_digest") or design.get("same_permissions") is not True:
        errors.append("gain 未绑定同 case/input/permissions")
    if not isinstance(design.get("repetitions"), int) or design.get("repetitions") < 1:
        errors.append("gain.design.repetitions 非法")
    if gain.get("status") not in {"completed", "not_run"} or (gain.get("status") == "not_run" and not gain.get("reason")):
        errors.append("gain.status/reason 非法")
    if not isinstance(gain.get("quality"), dict) or not isinstance(gain.get("efficiency"), dict):
        errors.append("gain.quality/efficiency 必须为对象")
    if gain.get("status") == "completed" and gain.get("quality", {}).get("same_rubric") is not True:
        errors.append("completed gain 缺 same_rubric")
    return errors, {"routes": routes, "required_exceptions": sorted(required_exceptions), "exception_coverage": codes}


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
    routes = [row.get("route") for row in (d.get("routing") or {}).get("routes") or []]
    sections = ["research_goal", "variables", "controls", "steps", "resources", "parameters", "risks", "routing"]
    for route, key in (("comparison", "comparison"), ("feasibility", "feasibility"), ("parameter", "optimization"), ("interpretation", "interpretation")):
        if route in routes:
            sections.append(key)
    present = sum(bool(d.get(key)) for key in sections)
    located = sum(not evidence_errors(row.get("evidence"), "evidence") for row in d.get("judgments") or [])
    required = set(BASE_EXCEPTIONS)
    for route in routes:
        required |= ROUTE_EXCEPTIONS.get(route, set())
    exceptions = len({row.get("code") for row in d.get("exception_register") or []} & required)
    completed_outputs = sum(bool(d.get(key)) for key in ("comparison", "feasibility", "optimization", "interpretation") if key in sections)
    return {"sections_present": present, "located_judgments": located, "exceptions_covered": exceptions,
            "route_outputs_present": completed_outputs, "required_sections": len(sections)}


def make_gain(base, skill):
    if base.get("case_id") != skill.get("case_id"):
        raise ValueError("case_id 不同，拒绝不公平对照")
    if base.get("input_digest") != skill.get("input_digest"):
        raise ValueError("input_digest 不同，拒绝不公平对照")
    if base.get("permissions_digest") != skill.get("permissions_digest"):
        raise ValueError("permissions_digest 不同，拒绝不公平对照")
    b, s = quality(base), quality(skill)
    q = {"same_rubric": True, "rubric": "routed required sections + evidence + route-specific exceptions + outputs"}
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
        if command == "route":
            out_path = argv[argv.index("--out") + 1]
            routing = route_task(argv[argv.index("--task") + 1], argv[argv.index("--case") + 1])
            with open(out_path, "w", encoding="utf-8") as handle:
                json.dump(routing, handle, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)
                handle.write("\n")
            emit({"ok": routing["status"] == "routed", "out": out_path, "primary": routing["primary"],
                  "routes": [row["route"] for row in routing["routes"]]})
            return 0 if routing["status"] == "routed" else 1
        if command == "compare":
            out_path = argv[argv.index("--out") + 1]
            comparison = compare_plans(load(argv[1]))
            with open(out_path, "w", encoding="utf-8") as handle:
                json.dump(comparison, handle, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)
                handle.write("\n")
            emit({"ok": comparison["status"] == "complete", "out": out_path, "recommended": comparison["recommended"],
                  "evaluated_count": comparison["evaluated_count"]})
            return 0 if comparison["status"] == "complete" else 1
        if command == "interpret":
            out_path = argv[argv.index("--out") + 1]
            interpretation = interpret_observations(load(argv[1]))
            with open(out_path, "w", encoding="utf-8") as handle:
                json.dump(interpretation, handle, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)
                handle.write("\n")
            emit({"ok": True, "out": out_path, "n": interpretation["n"], "flagged_anomalies": interpretation["flagged_anomalies"]})
            return 0
        if command == "resources":
            errors, computed = integrated_resource_check(load(argv[1]))
            emit({"ok": not errors, "computed": computed, "errors": errors})
            return 0 if not errors else 1
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
            errors, details = validate_integrated(load(argv[1]))
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
