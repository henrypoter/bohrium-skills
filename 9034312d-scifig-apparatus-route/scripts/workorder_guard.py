#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""workorder_guard.py — 装置/路线输入工单一致性与异常登记审计（纯标准库）。

用法：
  python3 scripts/workorder_guard.py audit SPEC.json [材料.txt ...] [--require] [--out REPORT.json]

审计 spec.workorder（schema_version=scifig-workorder/1.0）：
- parameters：题面要求的部件参数必须显式 stated/not_stated/not_applicable/conflicted；
  stated 必须有 value+unit（无单位参数 unit=""）+source；缺失/冲突不得静默补值。
- interfaces：接口 id/node/port/medium/direction/source；边用 from_interface/to_interface
  引用。检查重复接口、悬空引用、介质冲突、in/out 方向冲突和未指定接口。
- order_assertions：{before,after,source}；检查直接矛盾与依赖环。
- ambiguities：resolved 要 decision+source；conservative_choice/unresolved 必须进入
  limitations，completion_ceiling=partial，禁止伪装成完全确定。
- 所有出现的 source={locator,quote} 同时验证“材料中存在+locator 区间内”。

退出：0=无 error（可带 limitation），1=发现问题，2=输入无法读取。
--require 将 workorder 未声明视为 error；无 --require 时仅 warning，兼容旧 spec。
REPORT 在输入可解析时总是写出（含 fail 证据），不会创建 SVG/结果等下游交付。
"""
import argparse
import json
import os
import re
import sys
import unicodedata

VERSION = "1.0.0"
SCHEMA = "scifig-workorder/1.0"
LOC_LINE = re.compile(r"^L?0*(\d+)(?:\s*[-–—~]\s*L?0*(\d+))?$", re.I)
LOC_SENT = re.compile(r"^(?:句|S)\s*0*(\d+)(?:\s*[-–—~]\s*(?:句|S)?\s*0*(\d+))?$", re.I)


def qnorm(text):
    s = unicodedata.normalize("NFKC", str(text)).replace("µ", "μ").replace("−", "-")
    s = s.replace("-\r\n", "").replace("-\n", "")
    return re.sub(r"\s+", " ", s).strip().lower()


def spans(raw):
    return raw.split("\n"), [s for s in re.split(r"(?<=[。；;！!？?])|\n", raw) if s.strip()]


def resolve(locator, lines, sentences):
    loc = str(locator or "").strip()
    m = LOC_SENT.match(loc)
    if m:
        a, b = int(m.group(1)), int(m.group(2) or m.group(1))
        return "".join(sentences[a - 1:b]) if 1 <= a <= b <= len(sentences) else None
    m = LOC_LINE.match(loc)
    if m:
        a, b = int(m.group(1)), int(m.group(2) or m.group(1))
        tagged = [(int(re.match(r"^L(\d+)", ln).group(1)), ln)
                  for ln in lines if re.match(r"^L\d{3,}\s", ln)]
        if tagged:
            selected = [ln for n, ln in tagged if a <= n <= b]
            return "\n".join(selected) if selected else None
        return "\n".join(lines[a - 1:b]) if 1 <= a <= b <= len(lines) else None
    return None


def audit_workorder(spec, material_paths=(), require=False):
    errors, limitations, warnings, anchors = [], [], [], []

    def issue(bucket, code, path, message):
        row = {"code": code, "path": path, "message": message}
        if row not in bucket:
            bucket.append(row)

    wo = spec.get("workorder")
    if wo is None:
        code = "workorder_not_declared"
        msg = "未声明 spec.workorder；参数/接口/工艺歧义未经过专项审计"
        issue(errors if require else warnings, code, "workorder", msg)
        return {"schema_version": SCHEMA, "tool_version": VERSION, "status": "not_declared",
                "ok": not require, "completion_ceiling": "partial" if require else "answered",
                "errors": errors, "limitations": limitations, "warnings": warnings,
                "source_anchors": anchors,
                "counts": {"parameters": 0, "interfaces": 0, "order_assertions": 0, "ambiguities": 0}}
    if not isinstance(wo, dict):
        issue(errors, "workorder_type", "workorder", "workorder 必须是对象")
        wo = {}
    if wo.get("schema_version") != SCHEMA:
        issue(errors, "workorder_schema", "workorder.schema_version",
              "必须逐字为 %s" % SCHEMA)

    lines, sentences = [], []
    raw = ""
    for path in material_paths or []:
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                raw += "\n" + f.read()
        except OSError as exc:
            issue(errors, "material_unreadable", str(path), str(exc))
    lines, sentences = spans(raw)
    hay = qnorm(raw)

    def anchor(owner, path, required=False):
        src = owner.get("source") if isinstance(owner, dict) else None
        if not src:
            if required:
                issue(errors, "source_required", path + ".source", "必须提供 {locator,quote} 来源锚点")
            return
        if not isinstance(src, dict):
            issue(errors, "source_schema", path + ".source", "只接受 {locator,quote}，旧字符串不得用于工单")
            return
        loc, quote = str(src.get("locator", "") or ""), str(src.get("quote", "") or "")
        row = {"path": path, "locator": loc, "quote": quote, "status": "pending"}
        if not loc or not quote:
            issue(errors, "source_fields", path + ".source", "locator 与 quote 均须非空")
            row["status"] = "invalid"
        elif not raw.strip():
            issue(errors, "material_required", path + ".source", "有来源锚点时必须传实际材料文件")
            row["status"] = "unverified"
        elif qnorm(quote) not in hay:
            issue(errors, "quote_not_found", path + ".source.quote", "quote 不在材料中，疑似补造")
            row["status"] = "quote_not_found"
        else:
            excerpt = resolve(loc, lines, sentences)
            if excerpt is None:
                issue(errors, "locator_invalid", path + ".source.locator", "locator 无法解析或越界")
                row["status"] = "locator_invalid"
            elif qnorm(quote) not in qnorm(excerpt):
                issue(errors, "locator_mismatch", path + ".source.locator", "quote 在材料他处，不在声明区间")
                row["status"] = "locator_mismatch"
            else:
                row["status"] = "verified"
        anchors.append(row)

    nodes = {n.get("id") for n in spec.get("nodes") or [] if isinstance(n, dict)}
    params = wo.get("parameters") or []
    if not isinstance(params, list):
        issue(errors, "parameters_type", "workorder.parameters", "parameters 必须是数组")
        params = []
    seen_params, stated_values = set(), {}
    for i, param in enumerate(params):
        path = "workorder.parameters[%d]" % i
        if not isinstance(param, dict):
            issue(errors, "parameter_type", path, "参数记录必须是对象；空记录不算已处置")
            continue
        for key in ("id", "node", "name", "status"):
            if param.get(key) in (None, ""):
                issue(errors, "parameter_fields", path + "." + key, "必填字段缺失")
        pid, node, name, status = (param.get(k) for k in ("id", "node", "name", "status"))
        key = (node, name)
        if pid in seen_params:
            issue(errors, "parameter_duplicate", path + ".id", "重复参数 id: %s" % pid)
        seen_params.add(pid)
        if node not in nodes:
            issue(errors, "parameter_node_unknown", path + ".node", "node 不在 spec.nodes: %r" % node)
        if status == "stated":
            if param.get("value") in (None, "") or "unit" not in param:
                issue(errors, "parameter_value_missing", path, "stated 参数必须有 value 和 unit（无单位用空串）")
            anchor(param, path, required=True)
            value_key = qnorm("%s %s" % (param.get("value", ""), param.get("unit", "")))
            if key in stated_values and stated_values[key] != value_key:
                issue(errors, "parameter_value_conflict", path,
                      "同一 node/name 出现不同 stated 值；须改 status=conflicted 并列 candidates")
            stated_values[key] = value_key
        elif status in ("not_stated", "conflicted"):
            if not str(param.get("reason", "") or "").strip():
                issue(errors, "exception_reason_missing", path + ".reason", "缺失/冲突参数必须说明原因与后续限制")
            issue(limitations, "parameter_" + status, path,
                  "部件参数%s，禁止静默默认：%s" % ("未给出" if status == "not_stated" else "冲突", param.get("reason", "")))
            anchor(param, path, required=False)
        elif status == "not_applicable":
            if not str(param.get("reason", "") or "").strip():
                issue(errors, "exception_reason_missing", path + ".reason", "not_applicable 必须说明依据")
            anchor(param, path, required=False)
        else:
            issue(errors, "parameter_status", path + ".status",
                  "status 仅允许 stated/not_stated/not_applicable/conflicted")
        candidates = param.get("candidates") or []
        if status == "conflicted":
            normalized = {qnorm("%s %s" % (c.get("value", ""), c.get("unit", "")))
                          for c in candidates if isinstance(c, dict)}
            if len(normalized) < 2:
                issue(errors, "conflict_candidates", path + ".candidates", "conflicted 至少列两个不同候选值及来源")
            for j, candidate in enumerate(candidates):
                anchor(candidate, path + ".candidates[%d]" % j, required=True)

    interfaces = wo.get("interfaces") or []
    if not isinstance(interfaces, list):
        issue(errors, "interfaces_type", "workorder.interfaces", "interfaces 必须是数组")
        interfaces = []
    by_id, by_node_port = {}, {}
    for i, interface in enumerate(interfaces):
        path = "workorder.interfaces[%d]" % i
        if not isinstance(interface, dict):
            issue(errors, "interface_type", path, "接口记录必须是对象；空记录不算已处置")
            continue
        for key in ("id", "node", "port", "medium", "direction"):
            if interface.get(key) in (None, ""):
                issue(errors, "interface_fields", path + "." + key, "必填字段缺失")
        iid = interface.get("id")
        if iid in by_id:
            issue(errors, "interface_duplicate", path + ".id", "重复接口 id: %s" % iid)
        by_id[iid] = interface
        np = (interface.get("node"), interface.get("port"))
        if np in by_node_port:
            issue(errors, "interface_port_duplicate", path, "同一 node/port 重复声明: %r" % (np,))
        by_node_port[np] = interface
        if interface.get("node") not in nodes:
            issue(errors, "interface_node_unknown", path + ".node", "node 不在 spec.nodes")
        if interface.get("direction") not in ("in", "out", "bidirectional", "unknown"):
            issue(errors, "interface_direction", path + ".direction", "仅允许 in/out/bidirectional/unknown")
        if interface.get("direction") == "unknown" or qnorm(interface.get("medium")) == "unknown":
            issue(limitations, "interface_unknown", path, "接口方向或介质未知，需人工确认")
        anchor(interface, path, required=True)

    edges = spec.get("edges") or []
    if interfaces:
        for i, edge in enumerate(edges):
            path = "edges[%d]" % i
            fi, ti = edge.get("from_interface"), edge.get("to_interface")
            if not fi or not ti:
                issue(limitations, "interface_unspecified", path,
                      "接口清单已声明但边未同时引用 from_interface/to_interface")
                continue
            if fi not in by_id or ti not in by_id:
                issue(errors, "interface_reference_unknown", path, "边引用了不存在的接口: %r/%r" % (fi, ti))
                continue
            a, b = by_id[fi], by_id[ti]
            if a.get("node") != edge.get("from") or b.get("node") != edge.get("to"):
                issue(errors, "interface_endpoint_mismatch", path, "接口所属 node 与边 from/to 不一致")
            if qnorm(a.get("medium")) != qnorm(b.get("medium")) and "unknown" not in (qnorm(a.get("medium")), qnorm(b.get("medium"))):
                issue(errors, "interface_medium_conflict", path,
                      "接口介质冲突: %s != %s" % (a.get("medium"), b.get("medium")))
            da, db = a.get("direction"), b.get("direction")
            if da not in ("out", "bidirectional", "unknown") or db not in ("in", "bidirectional", "unknown"):
                issue(errors, "interface_direction_conflict", path,
                      "连接必须为 out→in（或 bidirectional），实际 %s→%s" % (da, db))

    assertions = wo.get("order_assertions") or []
    if not isinstance(assertions, list):
        issue(errors, "order_type", "workorder.order_assertions", "order_assertions 必须是数组")
        assertions = []
    pairs = set()
    for i, assertion in enumerate(assertions):
        path = "workorder.order_assertions[%d]" % i
        if not isinstance(assertion, dict):
            issue(errors, "order_assertion_type", path, "顺序断言必须是对象；空记录不算已声明")
            continue
        before, after = assertion.get("before"), assertion.get("after")
        if before not in nodes or after not in nodes or before == after:
            issue(errors, "order_endpoint", path, "before/after 必须是两个不同的 spec.nodes id")
        pair = (before, after)
        if (after, before) in pairs:
            issue(errors, "process_order_conflict", path, "与先前断言形成 A→B 和 B→A 直接矛盾")
        pairs.add(pair)
        anchor(assertion, path, required=True)
    adjacency = {}
    for a, b in pairs:
        adjacency.setdefault(a, set()).add(b)
    visiting, visited = set(), set()

    def cyclic(node):
        if node in visiting:
            return True
        if node in visited:
            return False
        visiting.add(node)
        if any(cyclic(nxt) for nxt in adjacency.get(node, ())):
            return True
        visiting.remove(node)
        visited.add(node)
        return False

    if any(cyclic(n) for n in list(adjacency)):
        issue(errors, "process_order_cycle", "workorder.order_assertions", "工艺先后依赖存在环，不能自动编号")

    ambiguities = wo.get("ambiguities") or []
    if not isinstance(ambiguities, list):
        issue(errors, "ambiguities_type", "workorder.ambiguities", "ambiguities 必须是数组")
        ambiguities = []
    seen_amb = set()
    for i, ambiguity in enumerate(ambiguities):
        path = "workorder.ambiguities[%d]" % i
        if not isinstance(ambiguity, dict):
            issue(errors, "ambiguity_type", path, "歧义记录必须是对象；空记录不算已处置")
            continue
        aid, status = ambiguity.get("id"), ambiguity.get("status")
        if not aid or not str(ambiguity.get("description", "") or "").strip():
            issue(errors, "ambiguity_fields", path, "id 与 description 必填")
        if aid in seen_amb:
            issue(errors, "ambiguity_duplicate", path + ".id", "重复歧义 id: %s" % aid)
        seen_amb.add(aid)
        if status == "resolved":
            if not str(ambiguity.get("decision", "") or "").strip():
                issue(errors, "ambiguity_decision", path + ".decision", "resolved 必须记录取舍")
            anchor(ambiguity, path, required=True)
        elif status == "conservative_choice":
            if not str(ambiguity.get("decision", "") or "").strip():
                issue(errors, "ambiguity_decision", path + ".decision", "保守选择必须写明，不得默认串行而不留痕")
            issue(limitations, "process_conservative_choice", path,
                  "工艺歧义采用保守选择，需人工确认：%s" % ambiguity.get("decision", ""))
            anchor(ambiguity, path, required=False)
        elif status == "unresolved":
            issue(limitations, "process_unresolved", path, "工艺描述歧义未解决，completion_ceiling=partial")
            anchor(ambiguity, path, required=False)
        else:
            issue(errors, "ambiguity_status", path + ".status",
                  "status 仅允许 resolved/conservative_choice/unresolved")

    return {"schema_version": SCHEMA, "tool_version": VERSION,
            "status": "issues" if errors else ("pass_with_limitations" if limitations else "pass"),
            "ok": not errors, "completion_ceiling": "partial" if errors or limitations else "answered",
            "errors": errors, "limitations": limitations, "warnings": warnings,
            "source_anchors": anchors,
            "counts": {"parameters": len(params), "interfaces": len(interfaces),
                       "order_assertions": len(assertions), "ambiguities": len(ambiguities),
                       "errors": len(errors), "limitations": len(limitations)}}


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="command", required=True)
    p = sub.add_parser("audit")
    p.add_argument("spec")
    p.add_argument("materials", nargs="*")
    p.add_argument("--require", action="store_true")
    p.add_argument("--out")
    args = ap.parse_args()
    try:
        with open(args.spec, encoding="utf-8") as f:
            spec = json.load(f)
    except Exception as exc:
        print(json.dumps({"ok": False, "input_error": str(exc)}, ensure_ascii=False))
        return 2
    report = audit_workorder(spec, args.materials, args.require)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
    print(json.dumps({"ok": report["ok"], "status": report["status"],
                      "completion_ceiling": report["completion_ceiling"],
                      "errors": report["errors"], "limitations": report["limitations"],
                      "warnings": report["warnings"], "counts": report["counts"],
                      "report": args.out}, ensure_ascii=False))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
