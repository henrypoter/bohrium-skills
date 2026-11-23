#!/usr/bin/env python3
"""实验方案设计工具：六要素覆盖 + 参数可行域核验(设备量程/安全阈值) + 交付校验。纯标准库。

  check  <result.json>                  六要素完整性、参数区间自洽、对照-混杂映射、风险三件套
  params <result.json> --spec spec.json 逐参数与设备/材料限值比对，越界即报错
  schema <result.json>                  交付契约校验
"""
import json, sys

def _load(p):
    return json.load(open(p, encoding="utf-8"))

def cmd_check(path):
    d = _load(path)
    errs, warn = [], []
    rg = d.get("research_goal") or {}
    if not rg.get("hypothesis"):
        errs.append("research_goal.hypothesis 为空(目标须落成可检验假设)")
    for i, v in enumerate(d.get("variables") or []):
        if v.get("type") not in ("independent", "dependent", "confounder"):
            errs.append("variables[%d] type 非法" % i)
        if not v.get("operational_definition"):
            errs.append("variables[%d] 缺操作定义" % i)
        if not v.get("unit"):
            errs.append("variables[%d] 缺单位" % i)
        if not v.get("range"):
            warn.append("variables[%d] 未给取值范围" % i)
    for i, c in enumerate(d.get("controls") or []):
        if not c.get("confounder_excluded"):
            errs.append("controls[%d] 缺 confounder_excluded(未说明排除哪类混杂)" % i)
    for i, r in enumerate(d.get("risks") or []):
        for k in ("trigger", "mitigation", "stop_rule"):
            if not r.get(k):
                errs.append("risks[%d] 缺 %s" % (i, k))
    for i, j in enumerate(d.get("judgments") or []):
        if not j.get("evidence") or not j.get("source"):
            errs.append("judgments[%d] 缺 evidence/source" % i)
    for i, p in enumerate(d.get("parameters") or []):
        v, lo, hi = p.get("value"), p.get("min"), p.get("max")
        if v is None:
            errs.append("parameters[%d] 缺 value" % i); continue
        if not p.get("unit"):
            errs.append("parameters[%d] 缺单位" % i)
        if lo is not None and v < lo:
            errs.append("parameters[%d] 取值 %s 低于自述下限 %s" % (i, v, lo))
        if hi is not None and v > hi:
            errs.append("parameters[%d] 取值 %s 高于自述上限 %s" % (i, v, hi))
    six = {"假设与变量": bool(rg.get("hypothesis") and d.get("variables")),
           "对照组": bool(d.get("controls")), "设备材料": bool(d.get("steps") or d.get("resources")),
           "时间成本": bool((d.get("resources") or {}).get("time_estimate")),
           "参数范围": bool(d.get("parameters")), "风险和异常": bool(d.get("risks"))}
    missing = [k for k, ok in six.items() if not ok]
    print(json.dumps({"ok": not errs, "six_elements": six, "missing_elements": missing,
                      "errors": errs, "warnings": warn}, ensure_ascii=False))
    return 0 if not errs and not missing else 1

def cmd_params(path, spec_path):
    d, spec = _load(path), _load(spec_path)
    limits = spec.get("limits") or {}
    bad = []
    for p in d.get("parameters") or []:
        name, v = p.get("name"), p.get("value")
        lim = limits.get(name)
        if lim is None:
            bad.append({"param": name, "issue": "spec 未声明该参数限值，无法核验（须补设备手册来源）"})
            continue
        if lim.get("unit") and p.get("unit") and lim["unit"] != p["unit"]:
            bad.append({"param": name, "issue": "单位不一致", "spec_unit": lim["unit"], "doc_unit": p["unit"]})
        if v is None:
            continue
        if lim.get("max") is not None and v > lim["max"]:
            bad.append({"param": name, "issue": "超出设备/材料上限", "value": v, "limit_max": lim["max"]})
        if lim.get("min") is not None and v < lim["min"]:
            bad.append({"param": name, "issue": "低于设备/材料下限", "value": v, "limit_min": lim["min"]})
        if lim.get("mutex_with") and p.get("name") in lim["mutex_with"]:
            bad.append({"param": name, "issue": "与互斥条件冲突"})
    print(json.dumps({"ok": not bad, "checked": len(d.get("parameters") or []), "violations": bad},
                     ensure_ascii=False))
    return 0 if not bad else 1

def cmd_schema(path):
    d = _load(path)
    if not isinstance(d, dict):
        print(json.dumps({"ok": False, "errors": ["顶层必须是对象"]}, ensure_ascii=False)); return 1
    errs = []
    for k in ("case_id", "status", "plan_version", "research_goal", "variables", "controls", "steps",
              "resources", "parameters", "risks", "judgments", "expert_confirmation",
              "gain", "unchecked", "sources", "uncertainty", "change_log"):
        if k not in d:
            errs.append("缺顶层字段 %s" % k)
    if d.get("status") not in {"pass", "issues", "partial", "failed"}:
        errs.append("status 非法")
    if not d.get("plan_version"):
        errs.append("plan_version 为空(方案须可版本化复核)")
    if errs:
        print(json.dumps({"ok": False, "errors": errs}, ensure_ascii=False)); return 1
    print(json.dumps({"ok": True, "variables": len(d.get("variables", [])),
                      "parameters": len(d.get("parameters", [])),
                      "risks": len(d.get("risks", []))}, ensure_ascii=False))
    return 0

if __name__ == "__main__":
    a = sys.argv[1:]
    if not a:
        print(__doc__); sys.exit(2)
    if a[0] == "check":
        sys.exit(cmd_check(a[1]))
    if a[0] == "params":
        sp = a[a.index("--spec") + 1] if "--spec" in a else None
        if not sp:
            print(json.dumps({"ok": False, "error": "params 需要 --spec"}, ensure_ascii=False)); sys.exit(2)
        sys.exit(cmd_params(a[1], sp))
    if a[0] == "schema":
        sys.exit(cmd_schema(a[1]))
    print(__doc__); sys.exit(2)
