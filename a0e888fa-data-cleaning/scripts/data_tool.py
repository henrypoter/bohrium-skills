#!/usr/bin/env python3
"""科研数据分析工具：数据画像(缺失/重复/异常值/单位不一致) + 聚合结果独立复算 + 交付校验。纯标准库。

  profile <data.csv>                    行列/类型/缺失/重复行/异常值/量级不一致
  recheck <result.json> --csv data.csv  用原始数据重算 result.json 里的聚合值，不一致即报错
  schema  <result.json>                 交付契约校验
"""
import csv, json, math, os, sys

def _read(path):
    for enc in ("utf-8-sig", "utf-8", "gbk", "latin-1"):
        try:
            with open(path, encoding=enc, newline="") as fh:
                rows = list(csv.DictReader(fh))
            return rows, enc, None
        except UnicodeDecodeError:
            continue
        except Exception as e:
            return [], None, str(e)
    return [], None, "无法解码"

def _num(s):
    try:
        v = float(str(s).strip().replace(",", ""))
        return v if math.isfinite(v) else None
    except Exception:
        return None

def cmd_profile(path):
    rows, enc, err = _read(path)
    if err:
        print(json.dumps({"ok": False, "error": err}, ensure_ascii=False)); return 1
    if not rows:
        print(json.dumps({"ok": False, "error": "空表"}, ensure_ascii=False)); return 1
    cols = list(rows[0].keys())
    prof = []
    for c in cols:
        vals = [r.get(c, "") for r in rows]
        nonempty = [v for v in vals if str(v).strip() != ""]
        nums = [_num(v) for v in nonempty]
        numeric = [n for n in nums if n is not None]
        is_num = len(nonempty) > 0 and len(numeric) == len(nonempty)
        item = {"column": c, "missing": len(vals) - len(nonempty),
                "missing_pct": round(100.0 * (len(vals) - len(nonempty)) / len(vals), 2),
                "n_unique": len(set(nonempty)), "numeric": is_num}
        if is_num and numeric:
            item["min"] = min(numeric); item["max"] = max(numeric)
            s = sorted(numeric)
            def q(p):
                k = (len(s) - 1) * p; f = int(k); c2 = min(f + 1, len(s) - 1)
                return s[f] + (s[c2] - s[f]) * (k - f)
            q1, q3 = q(0.25), q(0.75); iqr = q3 - q1
            lo, hi = q1 - 1.5 * iqr, q3 + 1.5 * iqr
            out = [x for x in numeric if x < lo or x > hi]
            item["outliers_iqr"] = len(out)
            if out:
                item["outlier_examples"] = out[:5]
            if item["min"] != 0 and abs(item["max"] / item["min"]) >= 1000:
                item["scale_warning"] = "同列量级跨 >=3 个数量级，疑单位不一致"
        elif nonempty and len(numeric) != len(nonempty):
            item["dirty_numeric_count"] = len(nonempty) - len(numeric)
        prof.append(item)
    dup = len(rows) - len({tuple(sorted((k, str(v)) for k, v in r.items())) for r in rows})
    print(json.dumps({"ok": True, "encoding": enc, "rows": len(rows), "cols": len(cols),
                      "duplicate_rows": dup, "columns": prof}, ensure_ascii=False))
    return 0

def cmd_recheck(path, csv_path):
    d = json.load(open(path, encoding="utf-8"))
    rows, enc, err = _read(csv_path)
    if err:
        print(json.dumps({"ok": False, "error": err}, ensure_ascii=False)); return 1
    bad, checked = [], 0
    for ag in d.get("aggregates", []):
        col, op, claimed = ag.get("column"), (ag.get("op") or "").lower(), ag.get("value")
        vals = [_num(r.get(col)) for r in rows]
        nums = [v for v in vals if v is not None]
        gb = ag.get("group_by")
        if gb:
            groups = {}
            for r in rows:
                v = _num(r.get(col))
                if v is None:
                    continue
                groups.setdefault(r.get(gb), []).append(v)
            for g, vs in groups.items():
                v = {"sum": sum(vs), "count": len(vs), "mean": sum(vs) / len(vs),
                     "min": min(vs), "max": max(vs)}.get(op)
                want = (claimed or {}).get(g) if isinstance(claimed, dict) else None
                checked += 1
                if v is not None and want is not None and abs(v - float(want)) > max(1e-3, abs(v) * 1e-3):
                    bad.append({"column": col, "op": op, "group": g, "recomputed": round(v, 6), "reported": want})
            continue
        calc = {"sum": sum(nums), "count": len(nums), "mean": (sum(nums) / len(nums)) if nums else None,
                "min": min(nums) if nums else None, "max": max(nums) if nums else None}.get(op)
        checked += 1
        try:
            rep = float(claimed)
        except Exception:
            bad.append({"column": col, "op": op, "error": "reported value 非数值", "reported": claimed}); continue
        if calc is None:
            bad.append({"column": col, "op": op, "error": "不支持的 op", "op_given": op}); continue
        if abs(calc - rep) > max(1e-3, abs(calc) * 1e-3):
            bad.append({"column": col, "op": op, "recomputed": round(calc, 6), "reported": rep,
                        "rel_diff": round(abs(calc - rep) / (abs(calc) or 1), 6)})
    print(json.dumps({"ok": not bad, "checked": checked, "mismatches": bad}, ensure_ascii=False))
    return 0 if not bad else 1

def cmd_schema(path):
    d = json.load(open(path, encoding="utf-8"))
    if not isinstance(d, dict):
        print(json.dumps({"ok": False, "errors": ["顶层必须是对象"]}, ensure_ascii=False)); return 1
    errs = []
    for k in ("case_id", "status", "questions", "aggregates", "data_dictionary", "lineage",
              "gain", "unchecked", "sources", "uncertainty", "change_log"):
        if k not in d:
            errs.append("缺顶层字段 %s" % k)
    if d.get("status") not in {"pass", "issues", "partial", "failed"}:
        errs.append("status 非法")
    for i, q in enumerate(d.get("questions", [])):
        if not q.get("id") or not q.get("answer"):
            errs.append("questions[%d] 缺 id/answer" % i)
        if not q.get("evidence"):
            errs.append("questions[%d] 缺 evidence(结论须可回指)" % i)
    for i, ag in enumerate(d.get("aggregates", [])):
        for k in ("column", "op", "value"):
            if k not in ag:
                errs.append("aggregates[%d] 缺 %s" % (i, k))
    if not d.get("lineage"):
        errs.append("lineage 为空(须记录数据快照版本/表/筛选条件)")
    if errs:
        print(json.dumps({"ok": False, "errors": errs}, ensure_ascii=False)); return 1
    print(json.dumps({"ok": True, "questions": len(d.get("questions", [])),
                      "aggregates": len(d.get("aggregates", []))}, ensure_ascii=False))
    return 0

if __name__ == "__main__":
    a = sys.argv[1:]
    if not a:
        print(__doc__); sys.exit(2)
    if a[0] == "profile":
        sys.exit(cmd_profile(a[1]))
    if a[0] == "recheck":
        cp = a[a.index("--csv") + 1] if "--csv" in a else None
        if not cp:
            print(json.dumps({"ok": False, "error": "recheck 需要 --csv"}, ensure_ascii=False)); sys.exit(2)
        sys.exit(cmd_recheck(a[1], cp))
    if a[0] == "schema":
        sys.exit(cmd_schema(a[1]))
    print(__doc__); sys.exit(2)
