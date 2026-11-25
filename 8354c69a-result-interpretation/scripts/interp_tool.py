#!/usr/bin/env python3
"""实验结果解释与异常分析工具：五段结论结构核验 + 异常维度绑定 + 原因可检验性排序 + 可执行复核。纯标准库。

  interp_check <result.json>  五段(趋势/异常/原因/复核/后续)完整性、异常绑定维度、原因按可检验性排序、复核可执行
  schema       <result.json>  交付契约(数据文件/字段/阈值/版本可复算)
"""
import json, sys

DIMS = {"sample", "batch", "channel", "well", "timepoint", "group", "plate", "row", "column"}


def _load(p):
    return json.load(open(p, encoding="utf-8"))


def cmd_interp_check(path):
    d = _load(path)
    errs = []
    # 1. 趋势：方向/拐点/偏离 + 区间/对照/拟合
    for i, t in enumerate(d.get("trends", [])):
        for k in ("direction", "interval", "control", "fitting"):
            if not t.get(k):
                errs.append("trends[%d] 缺 %s(判据须可复算)" % (i, k))
    # 2. 异常点：绑定维度 + 阈值 + 偏离
    for i, a in enumerate(d.get("anomalies", [])):
        dim = a.get("dimension")
        if not dim:
            errs.append("anomalies[%d] 缺 dimension(须绑定批次/通道/孔位/样本/时间点)" % i)
        elif not any(k in str(dim) for k in DIMS):
            errs.append("anomalies[%d] dimension 未落到样本/批次/通道/孔位/时间点等维度: %s" % (i, dim))
        if not a.get("threshold"):
            errs.append("anomalies[%d] 缺 threshold(判定阈值)" % i)
        if not a.get("deviation"):
            errs.append("anomalies[%d] 缺 deviation(与对照/重复的偏离关系)" % i)
    # 3. 可能原因：证据支撑/排除 + 相关误因果风险 + 可检验性排序
    causes = d.get("causes", [])
    for i, c in enumerate(causes):
        if not c.get("evidence_support"):
            errs.append("causes[%d] 缺 evidence_support(支撑证据)" % i)
        if c.get("testability") is None:
            errs.append("causes[%d] 缺 testability(可检验性，用于排序)" % i)
        if "correlation_risk" not in c:
            errs.append("causes[%d] 缺 correlation_risk(相关误当因果的风险说明)" % i)
    vals = [c.get("testability") for c in causes if c.get("testability") is not None]
    if len(vals) >= 2 and vals != sorted(vals, reverse=True):
        errs.append("causes 未按可检验性(testability)降序排序")
    # 4. 复核步骤：可执行(具体文件/字段/日志/对照动作)
    for i, r in enumerate(d.get("recheck_steps", [])):
        if not r.get("action"):
            errs.append("recheck_steps[%d] 缺 action(核查动作)" % i)
        if not r.get("target"):
            errs.append("recheck_steps[%d] 缺 target(回查的具体文件/字段/日志)" % i)
    # 5. 后续实验建议：依据
    for i, e in enumerate(d.get("next_experiments", [])):
        if not e.get("rationale"):
            errs.append("next_experiments[%d] 缺 rationale(依据的原因/证据缺口)" % i)
    out = {"ok": not errs, "trends": len(d.get("trends", [])), "anomalies": len(d.get("anomalies", [])),
           "causes": len(causes), "recheck_steps": len(d.get("recheck_steps", [])),
           "next_experiments": len(d.get("next_experiments", [])), "errors": errs}
    print(json.dumps(out, ensure_ascii=False))
    return 0 if not errs else 1


def cmd_schema(path):
    d = _load(path)
    if not isinstance(d, dict):
        print(json.dumps({"ok": False, "errors": ["顶层必须是对象"]}, ensure_ascii=False)); return 1
    errs = []
    for k in ("case_id", "status", "analysis_version", "data_sources", "trends", "anomalies",
              "causes", "recheck_steps", "next_experiments", "unexplained", "gain",
              "unchecked", "uncertainty", "change_log"):
        if k not in d:
            errs.append("缺顶层字段 %s" % k)
    if d.get("status") not in {"pass", "issues", "partial", "failed"}:
        errs.append("status 非法")
    if not d.get("analysis_version"):
        errs.append("analysis_version 为空(分析须可版本化复算)")
    for i, s in enumerate(d.get("data_sources", [])):
        if not s.get("file") or not s.get("field"):
            errs.append("data_sources[%d] 缺 file/field(结论须回指到具体数据文件与字段)" % i)
    if errs:
        print(json.dumps({"ok": False, "errors": errs}, ensure_ascii=False)); return 1
    print(json.dumps({"ok": True, "trends": len(d.get("trends", [])),
                      "anomalies": len(d.get("anomalies", [])),
                      "causes": len(d.get("causes", []))}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    a = sys.argv[1:]
    if not a:
        print(__doc__); sys.exit(2)
    if a[0] == "interp_check":
        sys.exit(cmd_interp_check(a[1]))
    if a[0] == "schema":
        sys.exit(cmd_schema(a[1]))
    print(__doc__); sys.exit(2)
