#!/usr/bin/env python3
"""按设计/样本量/分布筛查选检验，计算效应量与区间，并审计结论绑定。仅标准库。

  recommend DATA.csv --spec ANALYSIS.json
  infer     DATA.csv --spec ANALYSIS.json [--out ANALYSIS_RESULT.json]
  audit     RESULT.json --analysis ANALYSIS_RESULT.json

支持：独立两组 Welch t / Mann–Whitney U；独立多组单因素 ANOVA / Kruskal–Wallis；
配对/单样本（后者对 mu0 的差值）paired t / Wilcoxon signed-rank。
正态性为偏度/峰度/IQR 筛查而非“证明正态”；非参数区间标明近似或固定种子 bootstrap。
退出码：0=通过；1=阻断或审计失败；2=用法错误。不要把筛查输出当因果证明。
"""
import csv
import hashlib
import io
import json
import math
import os
import random
import statistics
import sys
import tempfile

TOOL_VERSION = "3.0.0"
Z975 = 1.959963984540054


def emit(obj, code=0):
    try:
        print(json.dumps(obj, ensure_ascii=False, allow_nan=False))
    except (TypeError, ValueError) as exc:
        print(json.dumps({"ok": False, "error_code": "NON_JSON_RESULT", "error": str(exc)}, ensure_ascii=False))
        return 1
    return code


def fail(code, message, **extra):
    out = {"ok": False, "tool_version": TOOL_VERSION, "error_code": code, "error": message}
    out.update(extra)
    return out


def load_json(path):
    with open(path, encoding="utf-8") as fh:
        obj = json.load(fh)
    if not isinstance(obj, dict):
        raise ValueError("JSON 顶层必须为对象")
    return obj


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(65536), b""):
            h.update(block)
    return h.hexdigest()


def read_csv(path):
    raw = open(path, "rb").read()
    if b"\x00" in raw[:4096] and not raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        raise ValueError("FILE_CORRUPT: 含 NUL 字节")
    attempts = ["utf-16"] if raw.startswith((b"\xff\xfe", b"\xfe\xff")) else ["utf-8-sig", "gb18030"]
    last = None
    for enc in attempts:
        try:
            text = raw.decode(enc, errors="strict")
            if "\ufffd" in text:
                raise ValueError("ENCODING_CORRUPT: 文本含替换字符")
            reader = csv.DictReader(io.StringIO(text, newline=""), strict=True)
            fields = reader.fieldnames
            if not fields or len(fields) != len(set(fields)):
                raise ValueError("FILE_CORRUPT: 表头为空或重复")
            rows = []
            for line, row in enumerate(reader, 2):
                if None in row:
                    raise ValueError("FILE_CORRUPT: 第 %d 行字段过多" % line)
                row["_line"] = line
                rows.append(row)
            if not rows:
                raise ValueError("EMPTY_TABLE: 空表")
            return rows, fields, enc
        except UnicodeDecodeError as exc:
            last = exc
        except csv.Error as exc:
            raise ValueError("FILE_CORRUPT: %s" % exc)
    raise ValueError("ENCODING_UNKNOWN: 严格解码失败: %s" % last)


def finite(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def quantile(values, p):
    s = sorted(values)
    if not s:
        return None
    k = (len(s) - 1) * p
    lo = int(k)
    hi = min(lo + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def describe(values):
    n = len(values)
    mean = statistics.fmean(values) if values else None
    sd = statistics.stdev(values) if n > 1 else 0.0
    skew = excess = 0.0
    if n > 2 and sd > 0:
        skew = sum(((x - mean) / sd) ** 3 for x in values) / n
        excess = sum(((x - mean) / sd) ** 4 for x in values) / n - 3.0
    q1, q3 = quantile(values, .25), quantile(values, .75)
    iqr = q3 - q1
    lo, hi = q1 - 1.5 * iqr, q3 + 1.5 * iqr
    return {"n": n, "mean": mean, "sd": sd, "median": quantile(values, .5),
            "q1": q1, "q3": q3, "min": min(values), "max": max(values),
            "skewness": skew, "excess_kurtosis": excess,
            "iqr_outliers": sum(x < lo or x > hi for x in values)}


def normal_screen(values):
    d = describe(values)
    reasons = []
    if d["n"] < 8:
        reasons.append("n<8: 不用低功效正态性检验证明参数法合理")
    if d["sd"] == 0:
        reasons.append("zero variance: t/ANOVA 分母可能为 0")
    if abs(d["skewness"]) > 1:
        reasons.append("|skewness|>1")
    if abs(d["excess_kurtosis"]) > 3:
        reasons.append("|excess_kurtosis|>3")
    return {"parametric_screen_pass": not reasons, "reasons": reasons,
            "n": d["n"], "skewness": d["skewness"], "excess_kurtosis": d["excess_kurtosis"],
            "declaration": "这是分布筛查，不是正态性的证明"}


def num(value, tokens):
    text = str(value if value is not None else "").strip()
    if text in {str(x) for x in tokens}:
        return None
    try:
        x = float(text)
        return x if math.isfinite(x) else None
    except ValueError:
        return None


def prepare(csv_path, spec):
    for key in ("spec_version", "dictionary_version", "analysis_id", "design", "value", "unit"):
        if spec.get(key) in (None, ""):
            return {"blockers": [{"code": "SPEC_FIELD_MISSING", "field": key,
                                  "question": "请提供 %s；字段口径未明前不硬算" % key}], "spec": spec}
    unit = str(spec.get("unit")).strip()
    if unit.lower() in {"?", "unknown", "未知", "none"}:
        return {"blockers": [{"code": "UNIT_UNKNOWN", "field": spec["value"],
                              "question": "请确认数值字段单位、换算方向和有效数字；确认前不计算"}], "spec": spec}
    design = spec.get("design")
    if design not in {"independent", "paired", "one_sample"}:
        return {"blockers": [{"code": "DESIGN_INVALID", "question": "design 须为 independent/paired/one_sample"}], "spec": spec}
    rows, fields, encoding = read_csv(csv_path)
    blockers, warnings = [], []
    value_field = spec["value"]
    if value_field not in fields:
        blockers.append({"code": "FIELD_NOT_FOUND", "field": value_field})
        return {"blockers": blockers, "spec": spec}
    tokens = spec.get("missing_tokens", ["", "NA", "N/A", "-999"])
    max_missing = float(spec.get("max_missing_fraction", .20))
    if not 0 <= max_missing < 1:
        blockers.append({"code": "SPEC_INVALID", "field": "max_missing_fraction"})
    alpha = float(spec.get("alpha", .05))
    if not 0 < alpha < 1:
        blockers.append({"code": "SPEC_INVALID", "field": "alpha"})
    duplicate_rows = len(rows) - len({tuple((k, str(v)) for k, v in sorted(r.items()) if k != "_line") for r in rows})
    if duplicate_rows:
        warnings.append({"code": "DUPLICATE_ROWS", "count": duplicate_rows,
                         "action": "不自动删；按真实主键和溯源裁决后才可排除"})
    groups, descriptions, differences = {}, {}, None
    pair_exclusions = []
    if design == "independent":
        group_field = spec.get("group")
        if not group_field or group_field not in fields:
            blockers.append({"code": "GROUP_FIELD_MISSING", "question": "请指定实际分组字段"})
            groups = {}
        else:
            totals, missing = {}, {}
            for row in rows:
                group = str(row.get(group_field, "")).strip()
                if not group:
                    blockers.append({"code": "GROUP_MISSING", "row": row["_line"]})
                    continue
                totals[group] = totals.get(group, 0) + 1
                x = num(row.get(value_field), tokens)
                if x is None:
                    missing[group] = missing.get(group, 0) + 1
                else:
                    groups.setdefault(group, []).append(x)
            for group in sorted(totals):
                values = groups.get(group, [])
                descriptions[group] = describe(values) if values else {"n": 0}
                descriptions[group]["missing_count"] = missing.get(group, 0)
                descriptions[group]["missing_fraction"] = missing.get(group, 0) / totals[group]
                if descriptions[group]["missing_fraction"] > max_missing:
                    blockers.append({"code": "HIGH_MISSING", "group": group,
                                     "fraction": descriptions[group]["missing_fraction"],
                                     "question": "缺失超过阈值；请确认缺失机制/敏感性分析，不置零"})
                if len(values) < 3:
                    blockers.append({"code": "SAMPLE_TOO_SMALL", "group": group, "n": len(values),
                                     "question": "每组至少 3 个有效观测；补充数据或改为描述性结果"})
                if len(values) > 1 and statistics.stdev(values) == 0:
                    warnings.append({"code": "ZERO_WITHIN_GROUP_VARIANCE", "group": group,
                                     "action": "切换秩检验并保留零方差说明"})
            if len(totals) < 2:
                blockers.append({"code": "TOO_FEW_GROUPS", "question": "独立设计至少两组"})
    elif design == "paired":
        group_field, pair_field = spec.get("group"), spec.get("pair")
        if not group_field or not pair_field or group_field not in fields or pair_field not in fields:
            blockers.append({"code": "PAIR_DESIGN_MISSING", "question": "paired 需要 group 与 pair 字段"})
        else:
            pair_names = sorted({str(r.get(group_field, "")).strip() for r in rows})
            if len(pair_names) != 2:
                blockers.append({"code": "PAIRED_GROUPS_NOT_TWO", "groups": pair_names})
            cells = {}
            for row in rows:
                key = (str(row.get(pair_field, "")).strip(), str(row.get(group_field, "")).strip())
                if key in cells:
                    blockers.append({"code": "PAIR_CONFLICT", "pair": key[0], "group": key[1], "row": row["_line"]})
                cells[key] = num(row.get(value_field), tokens)
            pair_ids = sorted({k[0] for k in cells})
            differences = []
            for pair_id in pair_ids:
                vals = [cells.get((pair_id, g)) for g in pair_names] if len(pair_names) == 2 else []
                if len(vals) != 2 or any(v is None for v in vals):
                    pair_exclusions.append(pair_id)
                else:
                    differences.append(vals[0] - vals[1])
            missing_fraction = len(pair_exclusions) / len(pair_ids) if pair_ids else 1.0
            descriptions[ "%s-%s" % tuple(pair_names) if len(pair_names) == 2 else "paired_difference"] = dict(
                describe(differences) if differences else {"n": 0},
                missing_count=len(pair_exclusions), missing_fraction=missing_fraction)
            groups = {descriptions and next(iter(descriptions)): differences}
            if missing_fraction > max_missing:
                blockers.append({"code": "HIGH_MISSING", "fraction": missing_fraction,
                                 "question": "不完整配对过多；不得把未配对值填入 0"})
            if len(differences) < 3:
                blockers.append({"code": "SAMPLE_TOO_SMALL", "n": len(differences),
                                 "question": "至少 3 个完整配对才能推断"})
            if differences and statistics.stdev(differences) == 0:
                warnings.append({"code": "ZERO_DIFFERENCE_VARIANCE", "action": "使用 Wilcoxon；t 检验不适用"})
    else:
        values = [num(r.get(value_field), tokens) for r in rows]
        observed = [x for x in values if x is not None]
        missing_count = len(values) - len(observed)
        fraction = missing_count / len(values)
        mu0 = float(spec.get("mu0", 0.0))
        differences = [x - mu0 for x in observed]
        groups = {"difference_from_mu0": differences}
        descriptions = {"difference_from_mu0": dict(describe(differences) if differences else {"n": 0},
                                                       missing_count=missing_count, missing_fraction=fraction)}
        if fraction > max_missing:
            blockers.append({"code": "HIGH_MISSING", "fraction": fraction,
                             "question": "缺失过多；先核查缺失机制，不能用 0 填补"})
        if len(differences) < 3:
            blockers.append({"code": "SAMPLE_TOO_SMALL", "n": len(differences)})
        if differences and statistics.stdev(differences) == 0:
            warnings.append({"code": "ZERO_DIFFERENCE_VARIANCE", "action": "使用 Wilcoxon；t 检验不适用"})
    duplicate_keys = [row["_line"] for row in rows if str(row.get(value_field, "")).strip() not in {str(x) for x in tokens}
                      and num(row.get(value_field), tokens) is None]
    if duplicate_keys:
        blockers.append({"code": "DIRTY_NUMERIC", "rows": duplicate_keys,
                         "question": "非数值单元格须先按字典裁决，不能静默删除或置零"})
    return {"blockers": blockers, "warnings": warnings, "spec": spec, "rows": rows,
            "encoding": encoding, "groups": groups, "descriptions": descriptions,
            "differences": differences, "pair_exclusions": pair_exclusions,
            "quality": {"rows_input": len(rows), "duplicate_rows": duplicate_rows,
                        "missing_by_group": {k: v.get("missing_count") for k, v in descriptions.items()},
                        "iqr_outliers_by_group": {k: v.get("iqr_outliers") for k, v in descriptions.items()}}}


def recommendation(prep):
    spec = prep["spec"]
    design = spec["design"]
    if design == "independent":
        groups = prep["groups"]
        screens = {k: normal_screen(v) for k, v in groups.items()}
        variances = {k: statistics.variance(v) for k, v in groups.items()}
        positive_variances = [v for v in variances.values() if v > 0]
        ratio = max(variances.values()) / min(positive_variances) if positive_variances else float("inf")
        homogeneity_pass = ratio <= 4.0
        variance_screen = {"group_variances": variances, "max_min_ratio": ratio if math.isfinite(ratio) else None,
                           "anova_homogeneity_screen_pass": homogeneity_pass,
                           "rule": "max/min<=4 heuristic for ANOVA only; Welch does not assume equal variances"}
        parametric = bool(screens) and all(s["parametric_screen_pass"] for s in screens.values())
        if len(groups) == 2:
            test = "welch_t" if parametric else "mann_whitney_u"
        else:
            parametric = parametric and homogeneity_pass
            test = "one_way_anova" if parametric else "kruskal_wallis"
        reason = ("所有组通过 n>=8、偏度、峰度与非零方差筛查" + ("；方差比通过 ANOVA 筛查" if len(groups) > 2 else "；Welch 不要求方差齐性")) if parametric else "至少一组未过参数法筛查，或多组方差比>4，采用秩检验"
    else:
        differences = prep.get("differences") or []
        screen = normal_screen(differences)
        parametric = screen["parametric_screen_pass"]
        test = "paired_t" if design == "paired" and parametric else "one_sample_t" if parametric else "wilcoxon_signed_rank"
        screens = {"differences": screen}
        reason = "差值通过参数法筛查" if parametric else "差值未通过参数法筛查，采用符号秩检验"
    return {"test": test, "reason": reason, "distribution_screen": screens,
            "variance_screen": variance_screen if design == "independent" else {"difference_variance": statistics.variance(prep["differences"]), "note": "zero difference variance excludes t test"},
            "multiplicity": "Holm across all requested pairwise tests" if design == "independent" and len(prep["groups"]) > 2 and spec.get("pairwise") else "not_applicable",
            "alpha": float(spec.get("alpha", .05))}


# 以下分布函数用连分式/级数计算，避免第三方统计包。
def betacf(a, b, x):
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c = 1.0
    d = 1.0 - qab * x / qap
    if abs(d) < 1e-300:
        d = 1e-300
    d = 1.0 / d
    h = d
    for m in range(1, 201):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        if abs(d) < 1e-300:
            d = 1e-300
        c = 1.0 + aa / c
        if abs(c) < 1e-300:
            c = 1e-300
        d = 1.0 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        if abs(d) < 1e-300:
            d = 1e-300
        c = 1.0 + aa / c
        if abs(c) < 1e-300:
            c = 1e-300
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < 3e-14:
            return h
    raise ArithmeticError("incomplete beta 未收敛")


def beta_inc(a, b, x):
    if x <= 0:
        return 0.0
    if x >= 1:
        return 1.0
    bt = math.exp(math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
                  + a * math.log(x) + b * math.log1p(-x))
    if x < (a + 1) / (a + b + 2):
        return bt * betacf(a, b, x) / a
    return 1.0 - bt * betacf(b, a, 1 - x) / b


def t_cdf(t, df):
    x = df / (df + t * t)
    ib = beta_inc(df / 2.0, .5, x)
    return 1.0 - .5 * ib if t >= 0 else .5 * ib


def t_critical(df, probability=.975):
    lo, hi = 0.0, 100.0
    for _ in range(100):
        mid = (lo + hi) / 2
        if t_cdf(mid, df) < probability:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def f_cdf(f, d1, d2):
    if f <= 0:
        return 0.0
    x = d1 * f / (d1 * f + d2)
    return beta_inc(d1 / 2.0, d2 / 2.0, x)


def gamma_q(a, x):
    if x < 0 or a <= 0:
        raise ValueError("gamma 参数非法")
    if x == 0:
        return 1.0
    if x < a + 1:
        term = total = 1.0 / a
        for n in range(1, 1000):
            term *= x / (a + n)
            total += term
            if abs(term) < abs(total) * 3e-14:
                break
        return 1.0 - total * math.exp(-x + a * math.log(x) - math.lgamma(a))
    b = x + 1 - a
    c = 1e300
    d = 1.0 / b
    h = d
    for i in range(1, 1000):
        an = -i * (i - a)
        b += 2
        d = an * d + b
        if abs(d) < 1e-300:
            d = 1e-300
        c = b + an / c
        if abs(c) < 1e-300:
            c = 1e-300
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1) < 3e-14:
            break
    return math.exp(-x + a * math.log(x) - math.lgamma(a)) * h


def ranks(values):
    ordered = sorted((x, i) for i, x in enumerate(values))
    result = [0.0] * len(values)
    ties = []
    i = 0
    while i < len(ordered):
        j = i + 1
        while j < len(ordered) and ordered[j][0] == ordered[i][0]:
            j += 1
        rank = (i + 1 + j) / 2.0
        for _, original_index in ordered[i:j]:
            result[original_index] = rank
        if j - i > 1:
            ties.append(j - i)
        i = j
    return result, ties


def normal_ci(value, se, clip=None):
    if se == 0:
        return [value, value]
    lo, hi = value - Z975 * se, value + Z975 * se
    if clip:
        lo, hi = max(clip[0], lo), min(clip[1], hi)
    return [lo, hi]


def percentile(values, p):
    return quantile(values, p)


def bootstrap_groups(groups, function, seed, reps=300):
    rng = random.Random(seed)
    names = list(groups)
    samples = []
    for _ in range(reps):
        resampled = {name: [groups[name][rng.randrange(len(groups[name]))] for _ in groups[name]] for name in names}
        try:
            value = function(resampled)
            if finite(value):
                samples.append(value)
        except (ValueError, ZeroDivisionError, statistics.StatisticsError):
            pass
    if not samples:
        return [None, None], 0
    return [percentile(samples, .025), percentile(samples, .975)], len(samples)


def eta_squared(groups):
    names = list(groups)
    all_values = [x for name in names for x in groups[name]]
    grand = statistics.fmean(all_values)
    ssb = sum(len(groups[name]) * (statistics.fmean(groups[name]) - grand) ** 2 for name in names)
    sst = sum((x - grand) ** 2 for x in all_values)
    return ssb / sst if sst else 0.0


def kruskal_stat(groups):
    names = list(groups)
    all_values = [x for name in names for x in groups[name]]
    rr, ties = ranks(all_values)
    n = len(all_values)
    offsets, offset = {}, 0
    for name in names:
        offsets[name] = offset
        offset += len(groups[name])
    h = 0.0
    for name in names:
        part = rr[offsets[name]:offsets[name] + len(groups[name])]
        h += sum(part) ** 2 / len(part)
    h = 12.0 * h / (n * (n + 1)) - 3 * (n + 1)
    correction = 1.0 - sum(t ** 3 - t for t in ties) / (n ** 3 - n) if n > 1 else 1.0
    h = h / correction if correction else 0.0
    epsilon = max(0.0, min(1.0, (h - len(names) + 1) / (n - len(names)))) if n > len(names) else 0.0
    return h, len(names) - 1, gamma_q((len(names) - 1) / 2.0, h / 2.0) if h else 1.0, epsilon


def independent_test(groups, chosen, unit, alpha, seed, pairwise=False):
    names = list(groups)
    if len(names) == 2 and chosen == "welch_t":
        a, b = groups[names[0]], groups[names[1]]
        n0, n1 = len(a), len(b)
        m0, m1 = statistics.fmean(a), statistics.fmean(b)
        v0, v1 = statistics.variance(a), statistics.variance(b)
        difference = m0 - m1
        se2 = v0 / n0 + v1 / n1
        se = math.sqrt(se2)
        df = se2 ** 2 / ((v0 / n0) ** 2 / (n0 - 1) + (v1 / n1) ** 2 / (n1 - 1))
        stat = difference / se
        p = beta_inc(df / 2.0, .5, df / (df + stat * stat))
        critical = t_critical(df)
        sp2 = ((n0 - 1) * v0 + (n1 - 1) * v1) / (n0 + n1 - 2)
        d = difference / math.sqrt(sp2)
        correction = 1.0 - 3.0 / (4.0 * (n0 + n1 - 2) - 1.0)
        g = correction * d
        se_g = correction * math.sqrt((n0 + n1) / (n0 * n1) + d * d / (2.0 * (n0 + n1 - 2)))
        return {"test": {"name": chosen, "statistic": stat, "df": df, "p_value": p},
                "effect": {"name": "hedges_g", "value": g, "ci": normal_ci(g, se_g),
                           "ci_method": "normal approximation", "direction": "%s-%s" % tuple(names)},
                "estimate": {"name": "mean_difference", "value": difference, "unit": unit,
                             "ci": [difference - critical * se, difference + critical * se], "ci_method": "Welch t interval"}}
    if len(names) == 2:
        a, b = groups[names[0]], groups[names[1]]
        n0, n1 = len(a), len(b)
        combined = a + b
        rr, ties = ranks(combined)
        u0 = sum(rr[:n0]) - n0 * (n0 + 1) / 2.0
        mean_u = n0 * n1 / 2.0
        n = n0 + n1
        var_u = n0 * n1 / 24.0 * (n + 1 - sum(t ** 3 - t for t in ties) / (n * (n - 1)))
        sd_u = math.sqrt(var_u)
        diff = u0 - mean_u
        z = 0.0 if sd_u == 0 else (diff - .5 * (1 if diff > 0 else -1 if diff < 0 else 0)) / sd_u
        p = 1.0 if sd_u == 0 else math.erfc(abs(z) / math.sqrt(2.0))
        effect = 2.0 * u0 / (n0 * n1) - 1.0
        se_effect = math.sqrt((n0 + n1 + 1.0) / (3.0 * n0 * n1)) if var_u else 0.0
        reps = 150 if pairwise else 400
        ci, actual_reps = bootstrap_groups(groups, lambda g: quantile(g[names[0]], .5) - quantile(g[names[1]], .5), seed, reps)
        return {"test": {"name": "mann_whitney_u", "statistic": u0, "df": None, "p_value": p,
                         "z_approximation": z, "tie_correction": True, "continuity_correction": True},
                "effect": {"name": "rank_biserial_correlation", "value": effect,
                           "ci": normal_ci(effect, se_effect, (-1.0, 1.0)), "ci_method": "normal approximation under tie-adjusted U",
                           "direction": "%s-%s; positive favors larger values in %s" % (names[0], names[1], names[0])},
                "estimate": {"name": "median_difference", "value": quantile(a, .5) - quantile(b, .5), "unit": unit,
                             "ci": ci, "ci_method": "fixed-seed percentile bootstrap within groups", "bootstrap_reps": actual_reps},
                "randomness": {"seed": seed, "bootstrap_reps": actual_reps}}
    if chosen == "one_way_anova":
        all_values = [x for values in groups.values() for x in values]
        n, k = len(all_values), len(names)
        grand = statistics.fmean(all_values)
        ssb = sum(len(groups[name]) * (statistics.fmean(groups[name]) - grand) ** 2 for name in names)
        ssw = sum((x - statistics.fmean(groups[name])) ** 2 for name in names for x in groups[name])
        dfb, dfw = k - 1, n - k
        msb, msw = ssb / dfb, ssw / dfw
        f = msb / msw
        p = beta_inc(dfw / 2.0, dfb / 2.0, dfw / (dfw + dfb * f))
        effect = eta_squared(groups)
        ci, actual_reps = bootstrap_groups(groups, eta_squared, seed, 200)
        means = {name: statistics.fmean(groups[name]) for name in names}
        mean_cis = {}
        for name in names:
            vals = groups[name]
            se = statistics.stdev(vals) / math.sqrt(len(vals))
            tc = t_critical(len(vals) - 1)
            mean_cis[name] = [means[name] - tc * se, means[name] + tc * se]
        return {"test": {"name": chosen, "statistic": f, "df": [dfb, dfw], "p_value": p},
                "effect": {"name": "eta_squared", "value": effect, "ci": ci,
                           "ci_method": "fixed-seed percentile bootstrap within groups", "direction": "proportion of total variance between groups"},
                "estimate": {"name": "group_means", "value": means, "unit": unit, "ci": mean_cis, "ci_method": "one-group t intervals"},
                "randomness": {"seed": seed, "bootstrap_reps": actual_reps}}
    h, df, p, epsilon = kruskal_stat(groups)
    ci, actual_reps = bootstrap_groups(groups, lambda g: kruskal_stat(g)[3], seed, 200)
    medians = {name: quantile(values, .5) for name, values in groups.items()}
    return {"test": {"name": "kruskal_wallis", "statistic": h, "df": df, "p_value": p, "tie_correction": True},
            "effect": {"name": "epsilon_squared", "value": epsilon, "ci": ci,
                       "ci_method": "fixed-seed percentile bootstrap within groups", "direction": "larger means stronger group separation"},
            "estimate": {"name": "group_medians", "value": medians, "unit": unit, "ci": None,
                         "ci_method": "use effect CI and per-group descriptive quantiles; no location shift assumed"},
            "randomness": {"seed": seed, "bootstrap_reps": actual_reps}}


def paired_test(differences, chosen, unit, seed):
    n = len(differences)
    if chosen in {"paired_t", "one_sample_t"}:
        mean = statistics.fmean(differences)
        sd = statistics.stdev(differences)
        se = sd / math.sqrt(n)
        stat = mean / se
        p = beta_inc((n - 1) / 2.0, .5, (n - 1) / (n - 1 + stat * stat))
        correction = 1.0 - 3.0 / (4.0 * (n - 1) - 1.0)
        effect = correction * mean / sd
        se_effect = correction * math.sqrt(1.0 / n + (mean / sd) ** 2 / (2.0 * (n - 1)))
        critical = t_critical(n - 1)
        return {"test": {"name": chosen, "statistic": stat, "df": n - 1, "p_value": p},
                "effect": {"name": "hedges_dz", "value": effect, "ci": normal_ci(effect, se_effect),
                           "ci_method": "normal approximation", "direction": "positive means first/observed minus second/mu0"},
                "estimate": {"name": "mean_difference", "value": mean, "unit": unit,
                             "ci": [mean - critical * se, mean + critical * se], "ci_method": "paired/one-sample t interval"}}
    nonzero = [x for x in differences if x != 0]
    rr, ties = ranks([abs(x) for x in nonzero])
    wplus = sum(rank for rank, value in zip(rr, nonzero) if value > 0)
    total = len(nonzero) * (len(nonzero) + 1) / 2.0
    wminus = total - wplus
    expected = total / 2.0
    m = len(nonzero)
    variance = m * (m + 1) * (2 * m + 1) / 24.0 - sum(t ** 3 - t for t in ties) / 48.0
    delta = wplus - expected
    z = 0.0 if variance == 0 else (delta - .5 * (1 if delta > 0 else -1 if delta < 0 else 0)) / math.sqrt(variance)
    p = 1.0 if m == 0 or variance == 0 else math.erfc(abs(z) / math.sqrt(2.0))
    effect = (wplus - wminus) / total if total else 0.0
    se_effect = math.sqrt((2.0 * m + 1.0) / (3.0 * m * (m + 1.0))) if m else 0.0
    rng = random.Random(seed)
    medians = []
    for _ in range(400):
        sample = [differences[rng.randrange(n)] for _ in range(n)]
        medians.append(quantile(sample, .5))
    median_value = quantile(differences, .5)
    median_ci = [percentile(medians, .025), percentile(medians, .975)]
    return {"test": {"name": "wilcoxon_signed_rank", "statistic": wplus, "df": None, "p_value": p,
                     "nonzero_differences": m, "zero_differences": n - m, "z_approximation": z,
                     "tie_correction": True, "continuity_correction": True},
            "effect": {"name": "matched_pairs_rank_biserial", "value": effect,
                       "ci": normal_ci(effect, se_effect, (-1.0, 1.0)), "ci_method": "normal approximation",
                       "direction": "positive means positive first/observed minus second/mu0"},
            "estimate": {"name": "median_difference", "value": median_value, "unit": unit,
                         "ci": median_ci, "ci_method": "fixed-seed percentile bootstrap of paired differences; descriptive location interval",
                         "bootstrap_reps": 400},
            "randomness": {"seed": seed, "bootstrap_reps": 400},
            "warning": "非参数效应区间是近似区间；不把 Wilcoxon 自动解释为中位数检验"}


def practical_importance(effect, spec):
    threshold = spec.get("minimum_important_effect")
    if threshold is None:
        return {"label": "not_assessed", "question": "请提供与该效应量同口径的最小实际重要阈值；不能由 p 值替代"}
    threshold = float(threshold)
    return {"label": "potentially_important" if abs(effect["value"]) >= threshold else "below_prespecified_threshold",
            "minimum_important_effect": threshold, "effect_metric": effect["name"],
            "caveat": "阈值比较不等于临床/工程重要性已被领域专家确认"}


def perform(prep):
    spec = prep["spec"]
    rec = recommendation(prep)
    alpha = rec["alpha"]
    seed = int(spec.get("random_seed", 20261125))
    design = spec["design"]
    if design == "independent":
        core = independent_test(prep["groups"], rec["test"], str(spec["unit"]), alpha, seed)
        group_names = list(prep["groups"])
    else:
        core = paired_test(prep["differences"], rec["test"], str(spec["unit"]), seed)
        group_names = list(prep["descriptions"])
    pairwise = []
    if design == "independent" and len(group_names) > 2 and spec.get("pairwise"):
        for i in range(len(group_names)):
            for j in range(i + 1, len(group_names)):
                pair = {name: prep["groups"][name] for name in (group_names[i], group_names[j])}
                screens = {name: normal_screen(values) for name, values in pair.items()}
                choice = "welch_t" if all(s["parametric_screen_pass"] for s in screens.values()) else "mann_whitney_u"
                item = {"pair": list(pair), **independent_test(pair, choice, str(spec["unit"]), alpha, seed + i * 100 + j, True)}
                pairwise.append(item)
        ordered = sorted(range(len(pairwise)), key=lambda idx: pairwise[idx]["test"]["p_value"])
        running = 0.0
        m = len(pairwise)
        for rank, idx in enumerate(ordered):
            adjusted = min(1.0, (m - rank) * pairwise[idx]["test"]["p_value"])
            running = max(running, adjusted)
            pairwise[idx]["test"]["p_adjusted_holm"] = running
        for item in pairwise:
            item["test"]["significance_uses"] = "p_adjusted_holm"
     
    
    effect = core["effect"]
    p = core["test"]["p_value"]
    significant = p < alpha
    practical = practical_importance(effect, spec)
    analysis_id = str(spec["analysis_id"])
    conclusion = {"analysis_id": analysis_id, "effect_ref": analysis_id + ".effect", "ci_ref": analysis_id + ".effect.ci",
                  "effect_metric": effect["name"], "effect_value": effect["value"], "effect_ci": effect["ci"],
                  "statistically_significant": significant, "alpha": alpha,
                  "interpretation": "%s；%s=%.6g，95%% CI [%s, %s]；p=%.6g。p 值不表示效应大小，也不是因果证明。" % (
                      "达到统计显著阈值" if significant else "未达到统计显著阈值（不等于证明无效）",
                      effect["name"], effect["value"], effect["ci"][0], effect["ci"][1], p),
                  "practical_importance": practical,
                  "limitations": ["结论仅适用于当前字段口径、设计和已记录排除规则", "区间不是个体取值范围", "分布筛查不证明正态性"]}
    core.update({"analysis_id": analysis_id, "status": "completed", "design": design,
                 "spec_version": spec["spec_version"], "dictionary_version": spec["dictionary_version"],
                 "value_field": spec["value"], "unit": spec["unit"], "alpha": alpha,
                 "groups": group_names, "descriptive_statistics": prep["descriptions"],
                 "assumptions": rec, "sample_quality": prep["quality"],
                 "excluded_pairs": prep.get("pair_exclusions", []), "warnings": prep.get("warnings", []),
                 "multiplicity": {"method": "holm" if pairwise else "not_applicable", "family_size": len(pairwise)},
                 "pairwise": pairwise, "conclusion": conclusion})
    return core


def command_analyze(csv_path, spec_path, do_infer, out_path=None):
    try:
        spec = load_json(spec_path)
        prep = prepare(csv_path, spec)
        if prep.get("blockers"):
            result = {"ok": False, "tool_version": TOOL_VERSION, "blockers": prep["blockers"],
                      "warnings": prep.get("warnings", []), "status": "blocked",
                      "questions": [x.get("question") for x in prep["blockers"] if x.get("question")]}
            return emit(result, 1)
        rec = recommendation(prep)
        if not do_infer:
            return emit({"ok": True, "tool_version": TOOL_VERSION, "analysis_id": spec.get("analysis_id"),
                         "input": {"path": csv_path, "sha256": sha256(csv_path)},
                         "recommendation": rec, "descriptive_statistics": prep["descriptions"],
                         "quality": prep["quality"], "warnings": prep.get("warnings", [])})
        analysis = perform(prep)
        result = {"ok": True, "tool_version": TOOL_VERSION,
                  "input": {"path": csv_path, "sha256": sha256(csv_path), "encoding": prep["encoding"]},
                  "analysis": analysis}
        if out_path:
            target = os.path.abspath(out_path)
            os.makedirs(os.path.dirname(target) or ".", exist_ok=True)
            fd, tmp = tempfile.mkstemp(prefix=".stats-", dir=os.path.dirname(target) or ".")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as fh:
                    json.dump(result, fh, ensure_ascii=False, indent=2, allow_nan=False)
                    fh.write("\n")
                os.replace(tmp, target)
            except Exception:
                try:
                    os.unlink(tmp)
                except OSError:
                    pass
                raise
        return emit(result)
    except (OSError, ValueError, ArithmeticError, json.JSONDecodeError) as exc:
        code = "PERMISSION_DENIED" if isinstance(exc, PermissionError) else "ANALYSIS_INPUT_INVALID"
        return emit(fail(code, str(exc)), 1)


def audit_ci(errors, ci, point, path):
    if not isinstance(ci, list) or len(ci) != 2 or not all(finite(x) for x in ci):
        errors.append({"code": "CI_MISSING", "path": path})
    elif finite(point) and not min(ci) - 1e-12 <= point <= max(ci) + 1e-12:
        errors.append({"code": "CI_DOES_NOT_CONTAIN_ESTIMATE", "path": path, "ci": ci, "point": point})


def command_audit(result_path, analysis_path):
    try:
        result, external = load_json(result_path), load_json(analysis_path)
        errors = []
        for key in ("case_id", "status", "questions", "statistics", "data_dictionary", "lineage", "run",
                    "quality", "unchecked", "sources", "uncertainty", "change_log", "artifacts"):
            if key not in result:
                errors.append({"code": "RESULT_FIELD_MISSING", "field": key})
        run = result.get("run") or {}
        for key in ("skill_version", "tool_version", "ruleset_version", "dictionary_version", "python_version",
                    "started_at", "random_seed"):
            if run.get(key) in (None, ""):
                errors.append({"code": "VERSION_FIELD_MISSING", "field": "run." + key})
        if not (result.get("lineage") or {}).get("snapshot"):
            errors.append({"code": "SNAPSHOT_MISSING"})
        def verify_record(item, kind):
            if not isinstance(item, dict) or not item.get("path") or not item.get("sha256"):
                errors.append({"code": kind + "_HASH_MISSING", "item": item})
                return
            path = item["path"]
            candidate = path if os.path.isabs(path) else os.path.join(os.path.dirname(os.path.abspath(result_path)), path)
            if not os.path.isfile(candidate):
                errors.append({"code": kind + "_FILE_NOT_FOUND", "path": path})
            elif sha256(candidate) != item["sha256"]:
                errors.append({"code": kind + "_HASH_MISMATCH", "path": path})
        for item in (result.get("lineage") or {}).get("inputs", []):
            verify_record(item, "INPUT")
        for item in result.get("artifacts", []):
            verify_record(item, "ARTIFACT")
        for i, question in enumerate(result.get("questions", [])):
            if not question.get("evidence"):
                errors.append({"code": "EVIDENCE_MISSING", "index": i})
        stats = result.get("statistics") or []
        if not stats:
            errors.append({"code": "STATISTICS_MISSING"})
        analysis = external.get("analysis")
        if not isinstance(analysis, dict):
            errors.append({"code": "EXTERNAL_ANALYSIS_MISSING"})
            analysis = {}
        if external.get("tool_version") and run.get("tool_version") != external.get("tool_version"):
            errors.append({"code": "RUN_ANALYSIS_TOOL_VERSION_MISMATCH"})
        if analysis.get("dictionary_version") and run.get("dictionary_version") != analysis.get("dictionary_version"):
            errors.append({"code": "RUN_ANALYSIS_DICTIONARY_VERSION_MISMATCH"})
        by_id = {str(x.get("analysis_id")): x for x in analysis and stats or []}
        if analysis.get("analysis_id") and str(analysis["analysis_id"]) not in by_id:
            errors.append({"code": "ANALYSIS_ID_NOT_IN_RESULT"})
        elif analysis and by_id[str(analysis["analysis_id"])] != analysis:
            errors.append({"code": "RESULT_ANALYSIS_MISMATCH", "action": "不得手改外部 infer 产出"})
        for i, item in enumerate(stats):
            path = "statistics[%d]" % i
            test, effect, conclusion = item.get("test") or {}, item.get("effect") or {}, item.get("conclusion") or {}
            for key in ("name", "statistic", "p_value"):
                if test.get(key) is None:
                    errors.append({"code": "TEST_FIELD_MISSING", "path": path + ".test." + key})
            if not finite(test.get("p_value")) or not 0 <= test["p_value"] <= 1:
                errors.append({"code": "P_VALUE_INVALID", "path": path})
            if item.get("test", {}).get("name") in {"welch_t", "paired_t", "one_sample_t", "one_way_anova", "kruskal_wallis"} and test.get("df") is None:
                errors.append({"code": "DF_MISSING", "path": path})
            if not effect.get("name") or not finite(effect.get("value")):
                errors.append({"code": "EFFECT_MISSING", "path": path})
            audit_ci(errors, effect.get("ci"), effect.get("value"), path + ".effect.ci")
            estimate = item.get("estimate") or {}
            if finite(estimate.get("value")) and estimate.get("ci") is not None:
                audit_ci(errors, estimate.get("ci"), estimate.get("value"), path + ".estimate.ci")
            evidence_ids = [e for q in result.get("questions", []) for e in q.get("evidence", [])]
            if not any(str(item.get("analysis_id")) in str(e) for e in evidence_ids):
                errors.append({"code": "QUESTION_NOT_BOUND_TO_ANALYSIS", "analysis_id": item.get("analysis_id")})
            expected_significant = test.get("p_value") < item.get("alpha", .05) if finite(test.get("p_value")) else None
            if conclusion.get("analysis_id") != item.get("analysis_id"):
                errors.append({"code": "CONCLUSION_ID_MISMATCH", "path": path})
            if conclusion.get("statistically_significant") is not expected_significant:
                errors.append({"code": "P_VALUE_CONCLUSION_MISMATCH", "path": path})
            if conclusion.get("effect_value") != effect.get("value") or conclusion.get("effect_ci") != effect.get("ci"):
                errors.append({"code": "EFFECT_CI_NOT_BOUND_TO_CONCLUSION", "path": path})
            if conclusion.get("effect_ref") != str(item.get("analysis_id")) + ".effect":
                errors.append({"code": "EFFECT_REFERENCE_INVALID", "path": path})
            if not (conclusion.get("practical_importance") or {}).get("label"):
                errors.append({"code": "PRACTICAL_IMPORTANCE_MISSING", "path": path})
            pairwise = item.get("pairwise") or []
            if len(pairwise) > 1:
                if (item.get("multiplicity") or {}).get("method") != "holm":
                    errors.append({"code": "MULTIPLICITY_METHOD_MISSING", "path": path})
                for j, pair in enumerate(pairwise):
                    if not finite((pair.get("test") or {}).get("p_adjusted_holm")):
                        errors.append({"code": "HOLM_ADJUSTMENT_MISSING", "path": path + ".pairwise[%d]" % j})
        out = {"ok": not errors, "tool_version": TOOL_VERSION, "case_id": result.get("case_id"),
               "analyses_checked": len(stats), "errors": errors,
               "verified": ["external infer copy", "p/df/effect/CI", "question-analysis-effect-CI binding",
                            "p/significance coherence", "Holm family", "versions/snapshot/input hashes"]}
        return emit(out, 0 if not errors else 1)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        code = "PERMISSION_DENIED" if isinstance(exc, PermissionError) else "AUDIT_INPUT_INVALID"
        return emit(fail(code, str(exc)), 1)


def main(argv):
    if not argv:
        print(__doc__)
        return 2
    try:
        if argv[0] in {"recommend", "infer"} and len(argv) >= 2 and "--spec" in argv:
            spec = argv[argv.index("--spec") + 1]
            out = argv[argv.index("--out") + 1] if "--out" in argv else None
            return command_analyze(argv[1], spec, argv[0] == "infer", out)
        if argv[0] == "audit" and len(argv) >= 2 and "--analysis" in argv:
            return command_audit(argv[1], argv[argv.index("--analysis") + 1])
        print(__doc__)
        return 2
    except (ValueError, IndexError) as exc:
        return emit(fail("USAGE_ERROR", str(exc)), 2)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
