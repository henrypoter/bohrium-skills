#!/usr/bin/env python3
# clean_tabular.py - 纯标准库清洗引擎 + result.json 装配。
# 原则：原值不改写、每次变更写 change_log（row_ref+source_ref+rule_id 留痕）、不编造。用法见 SKILL.md。
import argparse, csv, json, os, re
HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_RES = os.path.normpath(os.path.join(HERE, "..", "resources"))
MISSING_TOKENS = {"", "-", "--", "null", "none", "nan", "n/a", "na"}
NOT_REPORTED_TOKENS = {"nr", "n.r.", "n/r", "not reported", "not_reported", "未报告"}
MOJIBAKE = {"Âµ": "µ", "Î¼": "µ", "Î©": "Ω", "Â°C": "°C", "â„ƒ": "°C", "Â±": "±", "Â": ""}
NUM = r"[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?"
SUP = {"⁻": "-", "⁰": "0", "¹": "1", "²": "2", "³": "3"}
def read_text(path):
    with open(path, encoding="utf-8-sig", errors="replace") as f:
        t = f.read()
    fixed = [k for k in MOJIBAKE if k in t]
    for k in fixed:
        t = t.replace(k, MOJIBAKE[k])
    return t, fixed
def load_records(path, listkey=None):
    text, fixed = read_text(path)
    if path.lower().endswith(".csv"):
        return [dict(r) for r in csv.DictReader(text.splitlines())], fixed, "csv"
    data = json.loads(text)
    if listkey and isinstance(data, dict) and isinstance(data.get(listkey), list):
        return data[listkey], fixed, "json:" + listkey
    if isinstance(data, list):
        return data, fixed, "json"
    if isinstance(data, dict):
        for k in ("records", "data", "rows", "items", "table"):
            if isinstance(data.get(k), list):
                return data[k], fixed, "json:" + k
    return [], fixed, "json:empty"
def norm_key_name(k):
    return re.sub(r"[\s_\-]+", "_", str(k).strip().lower())
def build_field_map(dic):
    """列名同义映射；同写法命中多条规则时 priority 高者胜。"""
    m = {}
    for r in dic.get("rules", []):
        for a in r.get("match", []):
            e = (r.get("priority", 0), r)
            k = norm_key_name(a)
            if k not in m or m[k][0] < e[0]:
                m[k] = e
    return m
def map_record(rec, fmap, unmapped):
    out = {}
    for k, v in rec.items():
        nk = norm_key_name(k)
        if nk in fmap:
            canon = fmap[nk][1]["canonical"]
            if canon not in out:
                out[canon] = v
            elif out[canon] != v:
                out[canon] = "%s ; %s" % (out[canon], v)
        else:
            unmapped.setdefault(nk, k)
            out.setdefault("extra_" + nk, v)
    return out
def parse_value(v):
    if v is None:
        return {"kind": "missing"}
    if isinstance(v, (int, float)):
        return {"kind": "scalar", "num": float(v)}
    t = str(v).strip()
    tl = t.lower()
    if tl in MISSING_TOKENS:
        return {"kind": "missing"}
    if tl in NOT_REPORTED_TOKENS:
        return {"kind": "not_reported"}
    m = re.fullmatch(r"\s*(≤|≥|<|>|~|≈|约|ca\.?)?\s*(" + NUM + r")\s*(?:±\s*(" + NUM + r"))?\s*", t)
    if m:
        num = float(m.group(2))
        if m.group(3):
            return {"kind": "pm", "num": num, "err": float(m.group(3))}
        if m.group(1):
            return {"kind": "ineq", "op": m.group(1), "num": num}
        return {"kind": "scalar", "num": num}
    m = re.fullmatch(r"(" + NUM + r")\s*[–—~\-]\s*(" + NUM + r")", t)
    if m:
        return {"kind": "range", "lo": float(m.group(1)), "hi": float(m.group(2))}
    return {"kind": "unparsed"}
def norm_unit(u):
    u = str(u).strip()
    for a, b in SUP.items():
        u = u.replace(a, b)
    u = u.replace("⋅", " ").replace("·", " ").replace("*", " ").replace("μ", "µ")
    u = re.sub(r"\s*/\s*", "/", u)
    return re.sub(r"\s+", " ", u)
class UTable:
    """别名->factor/offset；否则 SI 前缀、指数单位、复合 a/b、a b-N 递归解析。"""
    def __init__(self, cfg):
        self.prefixes = cfg.get("prefixes", {})
        self.alias = {}
        for r in cfg.get("rules", []):
            for a in r.get("from", []):
                self.alias[norm_unit(a)] = r
    def lookup(self, u, depth=0):
        """(factor,offset,unit_to,rule_id,rule) 或 None；std=raw*factor+offset。"""
        u = norm_unit(u)
        r = self.alias.get(u)
        if r:
            return (r.get("factor", 1.0), r.get("offset", 0.0), r["to"], r["rule_id"], r)
        if depth >= 4:
            return None
        if "/" not in u and " " not in u:
            em = re.fullmatch(r"(.+?)(-?\d+)$", u)
            if em:
                base, exp = em.group(1), int(em.group(2))
                sb = self.lookup(base, depth + 1)
                if sb and sb[1] == 0:
                    return (sb[0] ** exp, 0.0, "%s%d" % (sb[2], exp),
                            sb[3] + "+exp%d" % exp, sb[4])
            for p in sorted(self.prefixes, key=len, reverse=True):
                if u.startswith(p) and len(u) > len(p):
                    sub = self.lookup(u[len(p):], depth + 1)
                    if sub and sub[1] == 0 and sub[4].get("prefixable", False):
                        return (sub[0] * self.prefixes[p], 0.0, sub[2], sub[3] + "+prefix", sub[4])
        m = re.fullmatch(r"([^/\s]+)[/\s]([^/\s]+)", u)
        if m:
            a, b, exp = m.group(1), m.group(2), 1
            eb = re.fullmatch(r"(.+)-(\d+)", b)
            if eb:
                b, exp = eb.group(1), int(eb.group(2))
            ra, rb = self.lookup(a, depth + 1), self.lookup(b, depth + 1)
            if ra and rb and ra[1] == 0 and rb[1] == 0:
                f = ra[0] / (rb[0] ** exp)
                return (f, 0.0, "%s %s-%d" % (ra[2], rb[2], exp), ra[3] + "+" + rb[3], ra[4])
        return None
def apply_conv(pv, f, o):
    r6 = lambda x: float("%.6g" % x)  # 6 位有效数字，避免 round(x,6) 抹掉量级
    if pv["kind"] == "scalar":
        return r6(pv["num"] * f + o)
    if pv["kind"] == "ineq":
        return {"op": pv["op"], "value": r6(pv["num"] * f + o)}
    if pv["kind"] == "pm":
        return {"value": r6(pv["num"] * f + o), "error": r6(pv["err"] * abs(f))}
    if pv["kind"] == "range":
        lo, hi = sorted((pv["lo"] * f + o, pv["hi"] * f + o))
        return [r6(lo), r6(hi)]
    return None
def norm_cond(c):
    if c is None:
        return ""
    if isinstance(c, (dict, list)):
        return json.dumps(c, sort_keys=True, ensure_ascii=False)
    return re.sub(r"\s+", " ", str(c).strip().lower())
def j(x):
    if x is None:
        return ""
    return json.dumps(x, ensure_ascii=False) if isinstance(x, (dict, list)) else str(x)
ap = argparse.ArgumentParser()
ap.add_argument("--input", required=True)  # case.json 或 CSV
ap.add_argument("--outdir", required=True)
ap.add_argument("--list", default=None, help="记录列表所在 JSON 键名")
ap.add_argument("--case", default="/input/case.json")
ap.add_argument("--answers", default=None, help="答案字段 JSON，并入 result.json")
ap.add_argument("--task-status", default=None,
                choices=["success", "partial", "failed", "indeterminate", "refused"])
a = ap.parse_args()
os.makedirs(a.outdir, exist_ok=True)
dic = json.load(open(os.path.join(DEFAULT_RES, "field_dictionary.json"), encoding="utf-8"))
ucfg = json.load(open(os.path.join(DEFAULT_RES, "unit_rules.json"), encoding="utf-8"))
scfg = json.load(open(os.path.join(DEFAULT_RES, "synonyms.json"), encoding="utf-8"))
fmap, synmap, utab = build_field_map(dic), {}, UTable(ucfg)
for r in scfg.get("rules", []):
    for al in r.get("match", []):
        synmap[al.strip().lower()] = (r["canonical"], r["rule_id"])
ranges = {k.lower(): v for k, v in ucfg.get("ranges", {}).items()}
try:
    records, enc_fixed, kind = load_records(a.input, a.list)
except Exception as e:
    records, enc_fixed, kind = [], [], "unreadable:" + str(e)
changelog, cleaned, unmapped = [], [], {}
anomaly = {k: [] for k in ("missing", "not_reported", "unknown_units", "unparsed_values",
                           "out_of_range", "duplicates", "possible_replicates",
                           "needs_review", "unmapped_fields", "encoding_notes")}
if enc_fixed:
    anomaly["encoding_notes"].append({"mojibake_tokens_repaired": enc_fixed})
rule_counts, sources_seen = {}, set()
def log(row_ref, sref, field, before, after, rid, note):
    changelog.append({"row_ref": row_ref, "source_ref": sref, "field": field,
                      "original": j(before), "result": j(after), "rule_id": rid, "note": note})
    rule_counts[rid] = rule_counts.get(rid, 0) + 1
cols = []
for rec in records:
    if isinstance(rec, dict):
        for k in rec:
            if k not in cols:
                cols.append(k)
colmap = []
for k in cols:
    nk = norm_key_name(k)
    hit = fmap.get(nk)
    colmap.append({"column": k, "canonical": hit[1]["canonical"] if hit else None,
                   "rule_id": hit[1]["rule_id"] if hit else None})
for i, rec in enumerate(records):
    m = map_record(rec if isinstance(rec, dict) else {"value": rec}, fmap, unmapped)
    rid = str(m.get("record_id") or "row#%d" % (i + 1))
    sref = str(m.get("source_ref") or m.get("page_ref") or "")
    if sref:
        sources_seen.add(sref)
    subst_raw = m.get("substance")
    subst, used = None, []
    if subst_raw is not None and str(subst_raw).strip():
        s = str(subst_raw).strip()
        hit = synmap.get(s.lower())
        if hit:
            subst = hit[0]
            if s != hit[0]:
                log(rid, sref, "substance", s, hit[0], hit[1], "同义名归一（修饰词差异已留痕，待确认口径）")
                used.append(hit[1])
        else:
            subst = s
    prop = str(m.get("property") or "").strip() or None
    cond = m.get("condition")
    pv = parse_value(m.get("value_raw"))
    unit_raw = m.get("unit_raw")
    unit_raw = None if unit_raw is None else str(unit_raw).strip()
    status, flags = "ok", []
    value_std = unit_std = None
    if pv["kind"] == "missing":
        status = "missing"
        anomaly["missing"].append({"row_ref": rid, "source_ref": sref, "property": prop})
    elif pv["kind"] == "not_reported":
        status = "not_reported"
        anomaly["not_reported"].append({"row_ref": rid, "source_ref": sref, "property": prop})
    elif pv["kind"] == "unparsed":
        status = "unparsed"
        flags.append("value_unparsed")
        anomaly["unparsed_values"].append({"row_ref": rid, "source_ref": sref, "raw": j(m.get("value_raw"))})
        anomaly["needs_review"].append({"row_ref": rid, "issue": "value_unparsed", "raw": j(m.get("value_raw"))})
    else:
        if unit_raw:
            hit = utab.lookup(unit_raw)
            if hit:
                f, o, unit_std, rule_u, _ = hit
                value_std = apply_conv(pv, f, o)
                used.append(rule_u)
                formula = "std = raw * %g" % f + (" + (%g)" % o if o else "")
                if norm_unit(unit_raw) != norm_unit(unit_std) or f != 1.0 or o != 0.0:
                    log(rid, sref, "value/unit", "%s %s" % (m.get("value_raw"), unit_raw),
                        "%s %s" % (j(value_std), unit_std), rule_u, formula)
            else:
                status = "unknown_unit"
                flags.append("unit_unknown_kept_raw")
                anomaly["unknown_units"].append({"row_ref": rid, "source_ref": sref, "unit": unit_raw})
                anomaly["needs_review"].append({"row_ref": rid, "issue": "unit_not_recognized",
                                                "unit": unit_raw, "action": "原值保留，待人工确认"})
        else:
            flags.append("no_unit_reported")
        probe = value_std if isinstance(value_std, float) else \
            (value_std.get("value") if isinstance(value_std, dict) else
             (value_std[0] if isinstance(value_std, list) else None))
        rng = ranges.get((prop or "").lower())
        if probe is not None and rng and \
                ((rng.get("lo") is not None and probe < rng["lo"]) or
                 (rng.get("hi") is not None and probe > rng["hi"])):
            flags.append("out_of_range")
            anomaly["out_of_range"].append({"row_ref": rid, "source_ref": sref,
                                            "property": prop, "value_std": probe, "limit": rng})
            anomaly["needs_review"].append({"row_ref": rid, "issue": "out_of_range",
                                            "value_std": probe, "limit": rng})
    cleaned.append({"row_ref": rid, "source_ref": sref, "substance_raw": j(subst_raw), "substance": j(subst),
                    "property": j(prop), "condition": "" if cond is None else j(cond),
                    "value_raw": j(m.get("value_raw")), "unit_raw": j(unit_raw),
                    "value_std": j(value_std), "unit_std": j(unit_std),
                    "status": status, "flags": "|".join(flags), "condition_norm": norm_cond(cond),
                    "rule_ids": "|".join(used)})
groups = {}
for c in cleaned:
    if c["status"] == "ok":
        groups.setdefault((c["substance"].lower(), (c["property"] or "").lower(), c["condition_norm"]), []).append(c)
for key, g in groups.items():
    if len(g) < 2:
        continue
    buckets = {}
    for c in g:
        buckets.setdefault(c["value_std"] + "|" + c["unit_std"], []).append(c)
    rows = [c["row_ref"] for c in g]
    if len(buckets) == 1:
        anomaly["duplicates"].append({"rows": rows, "key": list(key),
                                      "suggestion": "疑似重复录入（同键且换算后等值），待人工确认合并"})
        for c in g[1:]:
            anomaly["needs_review"].append({"row_ref": c["row_ref"], "issue": "duplicate_candidate", "group": rows})
    else:
        anomaly["possible_replicates"].append({"rows": rows, "key": list(key),
                                               "note": "同键但取值不同：疑似不同实验/口径冲突，全部保留"})
anomaly["unmapped_fields"] = sorted(unmapped.values())
if unmapped:
    anomaly["needs_review"].append({"issue": "unmapped_columns", "columns": sorted(unmapped.values())})
fields = [k for k in (cleaned[0] if cleaned else {}) if k != "condition_norm"]
with open(os.path.join(a.outdir, "cleaned_table.csv"), "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=fields)
    w.writeheader()
    for c in cleaned:
        w.writerow({k: c.get(k, "") for k in fields})
with open(os.path.join(a.outdir, "change_log.csv"), "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=["row_ref", "source_ref", "field", "original", "result", "rule_id", "note"])
    w.writeheader()
    w.writerows(changelog)
with open(os.path.join(a.outdir, "anomaly_report.json"), "w", encoding="utf-8") as f:
    json.dump(anomaly, f, ensure_ascii=False, indent=1)
summary = {"input_kind": kind, "rows_in": len(records),
           "rows_out": len(cleaned), "status_counts": {k: sum(1 for c in cleaned if c["status"] == k) for k in sorted({c["status"] for c in cleaned})},
           "rule_counts": dict(rule_counts), "column_mapping": colmap,
           "sources_seen": sorted(sources_seen), "change_log_rows": len(changelog),
           "anomaly_counts": {k: len(v) for k, v in anomaly.items()}}
with open(os.path.join(a.outdir, "cleaning_summary.json"), "w", encoding="utf-8") as f:
    json.dump(summary, f, ensure_ascii=False, indent=1)
case = {}
if os.path.exists(a.case):
    try:
        case = json.load(open(a.case, encoding="utf-8"))
    except Exception:
        case = {}
case_id = case.get("case_id") or case.get("id") or case.get("caseId") or "unknown"
answers = {}
if a.answers and os.path.exists(a.answers):
    answers = json.load(open(a.answers, encoding="utf-8"))
needs_review = anomaly["needs_review"]
if a.task_status:
    status = a.task_status
elif not records:
    status = "failed" if kind.startswith("unreadable") else "partial"
elif needs_review:
    status = "partial"
else:
    status = "success"
if status == "success":
    reason = "全部记录按规则库处理完成，无待确认项"
elif needs_review:
    reason = "存在待人工确认项（见 uncertainty）：%s" % \
        ", ".join(sorted({str(x.get("issue", x)) for x in needs_review}))
elif status == "partial":
    reason = "未解析到任何记录（input_kind=%s）；可指定 --list 键名重跑，不编造数据" % kind
else:
    reason = "输入不可读（input_kind=%s）；检查编码与结构后人工接管重跑" % kind
result = {
    "case_id": case_id,
    "status": status,
    "status_reason": reason,
    "answer": answers or {"cleaned_table": "cleaned_table.csv",
                          "note": "answer 应含 output_contract 要求的答案，待 Agent 填充"},
    "sources": sorted(sources_seen),
    "uncertainty": needs_review,
    "change_log": {"file": "change_log.csv", "records": len(changelog)},
    "cleaning_summary": {"rows_in": len(records), "rows_out": len(cleaned),
                         "status_counts": summary["status_counts"],
                         "anomaly_counts": summary["anomaly_counts"],
                         "rule_counts": summary["rule_counts"]},
    "artifacts": {"cleaned_table": "cleaned_table.csv", "change_log": "change_log.csv",
                  "anomaly_report": "anomaly_report.json", "cleaning_summary": "cleaning_summary.json"},
    "generated_by": "lit-rec-clean/1.0",
    "honesty_note": "原始值未改写：value_raw/unit_raw 为原文；value_std/unit_std 为按 rule_id 公式（std=raw*factor+offset）的换算值；缺失与未报告留空，未编造",
}
with open(os.path.join(a.outdir, "result.json"), "w", encoding="utf-8") as f:
    json.dump(result, f, ensure_ascii=False, indent=1)
print("rows=%d changes=%d review=%d status=%s" %
      (len(records), len(changelog), len(needs_review), status))
