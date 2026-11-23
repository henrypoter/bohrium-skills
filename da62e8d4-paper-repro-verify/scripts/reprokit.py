#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""reprokit.py — 论文复现验证（仅标准库，不联网）。子命令：env/params/card/compare/stats/sensitivity/attribution/init。
判定：数值等级(复现一致/定性一致/不一致/无法验证)×证据等级(T1仅文本/T2公开数据/T3公开代码/T4代码+数据+固化环境)。"""
import importlib.util, json, os, platform, statistics, sys, time

V_OK, V_QUAL, V_DIFF, V_NA = "复现一致", "定性一致", "不一致", "无法验证（材料不足）"
SRC_CLASSES = ("paper", "code", "self")
EVIDENCE_GRADES = ("T1", "T2", "T3", "T4")
EVIDENCE_LABEL = {"T1": "仅文本", "T2": "公开数据", "T3": "公开代码(或独立重实现+固定种子)",
                  "T4": "公开代码+数据+固化环境"}
ATTR_CAUSES = ("环境/依赖漂移", "随机性/种子", "参数缺失或漏抽", "口径不一致",
               "原文笔误（疑似）", "实现差异", "统计波动", "无法判定")
_T95 = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365, 8: 2.306,
        9: 2.262, 10: 2.228, 11: 2.201, 12: 2.179, 13: 2.16, 14: 2.145, 15: 2.131, 16: 2.12,
        17: 2.11, 18: 2.101, 19: 2.093, 20: 2.086, 21: 2.08, 22: 2.074, 23: 2.069, 24: 2.064,
        25: 2.06, 26: 2.056, 27: 2.052, 28: 2.048, 29: 2.045, 30: 2.042}


def load(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def dump(obj, p):
    os.makedirs(os.path.dirname(os.path.abspath(p)), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
    print("written:", p)


def norm(s):
    return " ".join(str(s).lower().split())


def _rel_err(p, r):
    return abs(r - p) if p == 0 else abs(r - p) / abs(p)


def _grade(paper, repro, tol, qf, at):
    if paper is None or repro is None:
        return V_NA, None, None, "原文未给出或缺少运行值；登记 missing_materials"
    p, r = float(paper), float(repro)
    if p == 0:
        a = float(at if at is not None else tol)
        e = abs(r - p)
        if e <= a:
            return V_OK, e, None, "paper=0，按绝对容差判定"
        return (V_QUAL if e <= a * qf else V_DIFF), e, None, "paper=0，绝对容差判定"
    rel = _rel_err(p, r)
    if rel <= tol:
        return V_OK, abs(r - p), rel, ""
    if rel <= tol * qf:
        return V_QUAL, abs(r - p), rel, ""
    return V_DIFF, abs(r - p), rel, ""


def _causes(g, rel, paper, repro):
    if g == V_NA:
        return ["无法判定"]
    if g == V_OK:
        return ["随机性/种子", "统计波动"]
    if g == V_QUAL:
        return ["实现差异", "参数缺失或漏抽", "环境/依赖漂移"]
    return ["口径不一致", "原文笔误（疑似）", "实现差异"]


def cmd_env(out):
    snap = {"timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "python": sys.version.split()[0], "platform": platform.platform(),
            "machine": platform.machine(), "pythonhashseed": os.environ.get("PYTHONHASHSEED", "unset"),
            "cwd": os.getcwd(), "optional_libs": {}}
    for lib in ("numpy", "matplotlib"):
        try:
            m = __import__(lib)
            snap["optional_libs"][lib] = getattr(m, "__version__", "present")
        except Exception:
            snap["optional_libs"][lib] = "unavailable"
    dump(snap, out)


def cmd_params(table, md=None):
    data = load(table)
    ps = data.get("parameters", [])
    problems, counts, seen = [], {c: 0 for c in SRC_CLASSES}, {}
    for i, p in enumerate(ps):
        for k in ("name", "value", "source_class", "location"):
            if k not in p or p[k] in (None, ""):
                problems.append("条目%d 缺字段 %s" % (i, k))
        sc = p.get("source_class")
        if sc in counts:
            counts[sc] += 1
        elif sc is not None:
            problems.append("条目%d source_class 非法: %r" % (i, sc))
        key = (p.get("method", ""), p.get("name", ""))
        if key in seen and seen[key] != p.get("value"):
            problems.append("冲突：%s.%s %r 与 %r 不一致，notes 需说明取舍"
                            % (key[0], key[1], seen[key], p.get("value")))
        seen[key] = p.get("value")
    tips = []
    if counts["self"]:
        tips.append("%d 个 self(缺失/自设)参数：建议 sensitivity 扫描量化其影响" % counts["self"])
    print(json.dumps({"total": len(ps), "by_source_class": counts, "problems": problems,
                      "tips": tips, "ok": not problems}, ensure_ascii=False, indent=2))
    if md:
        lines = ["| method | parameter | value | source_class | location | notes |",
                 "|---|---|---|---|---|---|"]
        for p in ps:
            lines.append("| %s | %s | %s | %s | %s | %s |" % (
                p.get("method", ""), p.get("name", ""), p.get("value", ""),
                p.get("source_class", ""), p.get("location", ""),
                str(p.get("notes", "")).replace("|", "/")))
        with open(md, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        print("written:", md)
    if problems:
        sys.exit(2)


def cmd_card(spec_path, out):
    spec = load(spec_path)
    fields = spec.get("check_fields", ["definition", "data_split", "aggregation", "precision"])
    mismatches, missing, n = [], [], 0
    for m in spec.get("metrics", []):
        n += 1
        paper, repro = m.get("paper") or {}, m.get("repro") or {}
        for side, d in (("paper", paper), ("repro", repro)):
            for k in fields:
                if k not in d or d[k] in (None, ""):
                    missing.append("指标 %s %s 侧缺口径字段 %s" % (m.get("metric"), side, k))
        for f in fields:
            pv, rv = paper.get(f), repro.get(f)
            if pv not in (None, "") and rv not in (None, "") and norm(pv) != norm(rv):
                mismatches.append("指标 %s 口径不一致：%s paper=%r vs repro=%r"
                                  % (m.get("metric"), f, pv, rv))
    ok = not mismatches and not missing
    dump({"ok": ok, "checked_metrics": n, "check_fields": fields, "mismatches": mismatches,
          "missing_fields": missing, "note": "口径一致才可进入数值比较；不一致先纠正口径再 compare"}, out)
    if not ok:
        print("口径卡校验失败：%d 不一致 / %d 缺失" % (len(mismatches), len(missing)))
        sys.exit(2)
    print("口径卡校验通过：%d 个指标口径一致" % n)


def cmd_compare(spec_path, out):
    spec = load(spec_path)
    tol0 = float(spec.get("default_tolerance", 0.02))
    qf = float(spec.get("qualitative_factor", 5))
    at0 = spec.get("abs_tolerance")
    ev0 = spec.get("default_evidence_grade", "T3")
    if ev0 not in EVIDENCE_GRADES:
        print("default_evidence_grade 非法: %r（应为 %s）" % (ev0, "/".join(EVIDENCE_GRADES)))
        sys.exit(2)
    rows, counts, evc = [], {V_OK: 0, V_QUAL: 0, V_DIFF: 0, V_NA: 0}, {g: 0 for g in EVIDENCE_GRADES}
    for m in spec.get("metrics", []):
        ev = m.get("evidence_grade", ev0)
        if ev not in EVIDENCE_GRADES:
            print("指标 %r evidence_grade 非法: %r" % (m.get("metric"), ev))
            sys.exit(2)
        tol = float(m.get("tolerance") or tol0)
        at = m.get("abs_tolerance", at0)
        g, ae, re, note = _grade(m.get("paper"), m.get("repro"), tol, qf, at)
        row = {"metric": m.get("metric"), "method": m.get("method"), "paper": m.get("paper"),
               "repro": m.get("repro"), "tolerance": tol, "abs_tolerance": at,
               "location": m.get("location", ""), "abs_err": ae, "rel_err": re,
               "numerical_grade": g, "evidence_grade": ev, "evidence_label": EVIDENCE_LABEL[ev],
               "verdict": "%s × %s" % (g, ev), "cause_candidates": _causes(g, re, m.get("paper"), m.get("repro"))}
        if note:
            row["note"] = note
        counts[g] += 1
        evc[ev] += 1
        rows.append(row)
    dump({"default_tolerance": tol0, "qualitative_factor": qf, "abs_tolerance_default": at0,
          "default_evidence_grade": ev0,
          "note": "二维判定=数值等级×证据等级；容差须运行前声明；" + spec.get("tolerance_basis", "未注明容差依据"),
          "verdict_counts": counts, "evidence_counts": evc, "rows": rows}, out)


def cmd_stats(runs_path, out):
    runs = load(runs_path)
    paper_map = runs.get("paper") or {}
    rows = []
    for m in runs.get("metrics", []):
        vals = [float(v) for v in (m.get("values") or []) if v is not None]
        n = len(vals)
        row = {"metric": m.get("metric"), "method": m.get("method"), "n": n}
        if n >= 2:
            mean = statistics.fmean(vals)
            sd = statistics.stdev(vals)
            sem = sd / (n ** 0.5)
            tc = _T95.get(n - 1, 1.96)
            lo, hi = mean - tc * sem, mean + tc * sem
            row.update(mean=mean, std=sd, sem=sem, ci95=[lo, hi],
                       ci_width_rel=(hi - lo) / abs(mean) if mean else None)
            if m.get("metric") in paper_map and paper_map[m.get("metric")] is not None:
                pv = float(paper_map[m.get("metric")])
                row.update(paper=pv, paper_in_ci=(lo <= pv <= hi),
                           conclusion=("原文值在 95% CI 内（统计波动范围）" if lo <= pv <= hi
                                       else "原文值在 95% CI 外（超出统计波动，需归因，勿直接判失败）"))
            else:
                row["conclusion"] = "原文未给出该指标值"
        else:
            row["conclusion"] = "有效样本数不足（n<2）"
        if n < 5:
            row["warning"] = "统计协议要求 ≥5 种子，当前 n=%d" % n
        rows.append(row)
    dump({"protocol": "多种子 ≥5；报告均值±标准差与 95% CI；判定原文值是否入 CI",
          "note": "CI 用 t 临界值近似表；方差估计有偏，结论须保留不确定性（Tang et al. 2020 警示）",
          "rows": rows}, out)


def cmd_sensitivity(method_path, grid_path, out):
    spec = load(grid_path)
    fn_name = spec.get("func", "evaluate")
    baseline = spec.get("baseline") or {}
    metrics = spec.get("metrics") or []
    tol = float(spec.get("tolerance", 0.02))
    if not os.path.isfile(method_path):
        print("method 文件不存在: %s" % method_path)
        sys.exit(2)
    mspec = importlib.util.spec_from_file_location("candidate_method", method_path)
    mod = importlib.util.module_from_spec(mspec)
    mspec.loader.exec_module(mod)
    fn = getattr(mod, fn_name, None)
    if fn is None:
        print("方法文件 %s 未提供 %s(**params)->dict" % (method_path, fn_name))
        sys.exit(2)
    try:
        base_vals = fn(dict(baseline))
    except Exception as e:
        print("baseline 运行失败: %r" % e)
        sys.exit(2)
    results = []
    for p in spec.get("params", []):
        name, values = p.get("name"), p.get("values") or []
        runs = []
        for v in values:
            cfg = dict(baseline)
            cfg[name] = v
            try:
                runs.append({"value": v, "metrics": fn(cfg)})
            except Exception as e:
                runs.append({"value": v, "error": repr(e)})
        pm = {}
        for mt in metrics:
            okv = [r["metrics"].get(mt) for r in runs if "metrics" in r and mt in r["metrics"]]
            if len(okv) >= 2:
                spread = max(okv) - min(okv)
                bv = base_vals.get(mt)
                rel = (spread / abs(bv)) if bv not in (None, 0) else (spread if bv == 0 else None)
                pm[mt] = {"spread": spread, "rel_range": rel, "values": okv}
        mx = max((pm[m]["rel_range"] for m in pm if pm[m]["rel_range"] is not None), default=None)
        level = "无法评估" if mx is None else ("不敏感" if mx <= tol else
                                              ("中等敏感" if mx <= tol * 10 else "高敏感"))
        results.append({"parameter": name, "level": level, "max_rel_range": mx,
                        "dominates_conclusion": (mx is not None and mx > tol),
                        "per_metric": pm, "runs": runs})
    results.sort(key=lambda r: (r.get("max_rel_range") is None, -(r.get("max_rel_range") or 0)))
    dump({"func": fn_name, "baseline": baseline, "baseline_metrics": base_vals, "tolerance": tol,
          "note": "扫描 self/缺失参数的小网格；max_rel_range>容差 → 结论受该参数主导；仅作敏感性证据",
          "sensitivity_ranking": results}, out)


def cmd_attribution(table_path, out):
    data = load(table_path)
    rows = data.get("attribution", [])
    problems, counts = [], {c: 0 for c in ATTR_CAUSES}
    for i, r in enumerate(rows):
        if r.get("cause") not in ATTR_CAUSES:
            problems.append("条目%d cause 非法: %r" % (i, r.get("cause")))
        else:
            counts[r.get("cause")] += 1
        if not str(r.get("evidence", "")).strip():
            problems.append("条目%d 缺 evidence（归因必须附判定依据）" % i)
    dump({"ok": not problems, "total": len(rows), "by_cause": counts, "problems": problems,
          "note": "8 类归因：%s；每条归因须附 evidence（环境指纹/敏感性/原文一致性/CI 结果）"
                 % "、".join(ATTR_CAUSES)}, out)
    if problems:
        sys.exit(2)
    print("归因单校验通过：%d 条归因均已归类并附证据" % len(rows))


def cmd_init(case_id, fields, out):
    obj = {"case_id": case_id, "status": "partial",
           "status_reason": "骨架先行写入，随后按工作流增量补全",
           "sources": [], "uncertainty": [], "missing_materials": [],
           "change_log": [{"time_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                           "change": "init skeleton"}]}
    for f in [x for x in fields.split(",") if x]:
        obj.setdefault(f, None)
    dump(obj, out)


def main():
    a = sys.argv[1:]

    def opt(flag, default=None):
        return a[a.index(flag) + 1] if flag in a else default

    if not a or a[0] in ("-h", "--help"):
        print(__doc__)
        return
    c = a[0]
    if c == "env":
        cmd_env(opt("--out", "env.json"))
    elif c == "params":
        cmd_params(opt("--table", "params.json"), opt("--md"))
    elif c == "card":
        cmd_card(opt("--spec", "card.json"), opt("--out", "card_out.json"))
    elif c == "compare":
        cmd_compare(opt("--spec", "spec.json"), opt("--out", "compare.json"))
    elif c == "stats":
        cmd_stats(opt("--runs", "runs.json"), opt("--out", "stats.json"))
    elif c == "sensitivity":
        cmd_sensitivity(opt("--method", "methods.py"), opt("--grid", "grid.json"), opt("--out", "sensitivity.json"))
    elif c == "attribution":
        cmd_attribution(opt("--table", "attribution.json"), opt("--out", "attribution_out.json"))
    elif c == "init":
        cmd_init(opt("--case-id", "unknown"), opt("--fields", ""), opt("--out", "result.json"))
    else:
        print("unknown subcommand:", c)
        sys.exit(1)


if __name__ == "__main__":
    main()
