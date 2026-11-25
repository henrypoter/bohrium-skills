#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""coverage_guard.py — 必做图面要素的“声明→实际 SVG”覆盖审计。

用法：
  python3 scripts/coverage_guard.py audit ELEMENTS.json FIGURE.svg [--task task.md] [--out REPORT.json]

继承 elements.required[]，并支持结构化 required_elements[]：
  {"id":"req-temp","category":"unit","text":"25 °C","task_quote":"25 °C"}
  {"id":"req-panel-a","category":"panel","svg_id":"panel-a","task_quote":"panel a"}
category 可为 entity/relationship/group/legend/annotation/unit/panel。
required 字符串必须命中实际 SVG 的可编辑文本或元素 id，而非只命中 spec；
结构化项按 svg_id/text 精确核验。传 --task 时，结构化项必须给 task_quote 且逐字
（空白/NFKC 归一）命中 task.md，防止把并非题面要求的内容冒充必做项。
legend=auto 时 layer-legend 缺失直接 fail。退出 0=全覆盖，1=缺项/错配，2=输入坏。
"""
import argparse
import json
import re
import sys
import unicodedata
import xml.etree.ElementTree as ET

VERSION = "1.0.0"
CATEGORIES = {"entity", "relationship", "group", "legend", "annotation", "unit", "panel"}
PREFIX = {"entity": "node-", "relationship": "edge-", "group": "group-", "panel": "panel-"}


def norm(text):
    value = unicodedata.normalize("NFKC", str(text))
    return re.sub(r"\s+", " ", value).strip().lower()


def audit_coverage(spec, svg_text, task_text=None):
    errors, warnings, rows = [], [], []
    try:
        root = ET.fromstring(svg_text)
    except ET.ParseError as exc:
        return {"ok": False, "errors": [{"code": "svg_not_well_formed", "message": str(exc)}],
                "warnings": [], "items": [], "coverage": {"matched": 0, "total": 0, "percent": 0.0}}
    ids = {el.get("id") for el in root.iter() if el.get("id")}
    texts = []
    for el in root.iter():
        if el.tag.split("}")[-1] in ("text", "textPath"):
            content = " ".join("".join(el.itertext()).split())
            if content:
                texts.append(content)
    text_hay = norm(" ".join(texts))
    id_hay = norm(" ".join(sorted(ids)))
    required = spec.get("required")
    if required is None:
        errors.append({"code": "required_undeclared", "message": "required 必须声明；题面无点名时才为 []"})
        required = []
    if not isinstance(required, list):
        errors.append({"code": "required_type", "message": "required 必须是数组"})
        required = []
    for i, item in enumerate(required):
        needle = norm(item)
        hit = bool(needle) and (needle in text_hay or needle in id_hay)
        row = {"id": "required[%d]" % i, "category": "legacy_required", "requirement": str(item),
               "matched": hit}
        rows.append(row)
        if not hit:
            errors.append({"code": "required_not_in_actual_svg", "item": str(item)})

    structured = spec.get("required_elements") or []
    if not isinstance(structured, list):
        errors.append({"code": "required_elements_type"})
        structured = []
    # panels[] is a convenience declaration converted into typed requirements.
    for panel in spec.get("panels") or []:
        if isinstance(panel, dict) and panel.get("id"):
            structured = list(structured) + [{"id": "panel:%s" % panel["id"], "category": "panel",
                                              "svg_id": panel["id"]}]
    seen = set()
    for i, item in enumerate(structured):
        if not isinstance(item, dict):
            errors.append({"code": "required_element_type", "index": i})
            continue
        rid, category = item.get("id"), item.get("category")
        if not rid or category not in CATEGORIES:
            errors.append({"code": "required_element_fields", "index": i, "allowed": sorted(CATEGORIES)})
            continue
        if rid in seen:
            errors.append({"code": "required_element_duplicate", "id": rid})
        seen.add(rid)
        svg_id, wanted_text = item.get("svg_id"), item.get("text")
        if not svg_id and not wanted_text:
            errors.append({"code": "required_element_no_matcher", "id": rid})
            continue
        id_hit = svg_id in ids if svg_id else True
        text_hit = norm(wanted_text) in text_hay if wanted_text else True
        semantic_hit = True
        if svg_id and category in PREFIX and not str(svg_id).startswith(PREFIX[category]):
            semantic_hit = False
        if category == "legend" and svg_id and svg_id != "layer-legend":
            semantic_hit = False
        task_hit = True
        if task_text is not None:
            task_quote = item.get("task_quote")
            task_hit = bool(task_quote) and norm(task_quote) in norm(task_text)
            if not task_hit:
                errors.append({"code": "task_quote_missing_or_mismatch", "id": rid})
        hit = id_hit and text_hit and semantic_hit and task_hit
        rows.append({"id": rid, "category": category, "svg_id": svg_id, "text": wanted_text,
                     "matched": hit, "id_hit": id_hit, "text_hit": text_hit,
                     "semantic_hit": semantic_hit, "task_hit": task_hit})
        if not id_hit:
            errors.append({"code": "svg_id_missing", "id": rid, "svg_id": svg_id})
        if not text_hit:
            errors.append({"code": "svg_text_missing", "id": rid, "text": wanted_text})
        if not semantic_hit:
            errors.append({"code": "category_svg_id_mismatch", "id": rid, "category": category})

    if spec.get("legend") == "auto" and "layer-legend" not in ids:
        errors.append({"code": "automatic_legend_missing"})
    if task_text is None and structured:
        warnings.append({"code": "task_not_cross_checked", "message": "传 --task task.md 可核 task_quote"})
    matched = sum(1 for row in rows if row.get("matched")) + (1 if spec.get("legend") == "auto" and "layer-legend" in ids else 0)
    total = len(rows) + (1 if spec.get("legend") == "auto" else 0)
    return {"schema_version": "sci-schematic-coverage/1.0", "tool_version": VERSION,
            "ok": not errors, "errors": errors, "warnings": warnings, "items": rows,
            "coverage": {"matched": matched, "total": total,
                         "percent": round(100.0 * matched / total, 2) if total else 100.0},
            "categories_checked": sorted(set(CATEGORIES) | {"legacy_required"}),
            "editable_text_elements": len(texts), "svg_ids": len(ids),
            "note": "coverage proves declared items exist in actual SVG; completeness of declaration requires task review"}


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="command", required=True)
    au = sub.add_parser("audit")
    au.add_argument("spec")
    au.add_argument("svg")
    au.add_argument("--task")
    au.add_argument("--out")
    args = ap.parse_args()
    try:
        spec = json.load(open(args.spec, encoding="utf-8"))
        svg_text = open(args.svg, encoding="utf-8").read()
        task_text = open(args.task, encoding="utf-8").read() if args.task else None
    except (OSError, ValueError, TypeError) as exc:
        print(json.dumps({"ok": False, "input_error": str(exc)}, ensure_ascii=False))
        return 2
    report = audit_coverage(spec, svg_text, task_text)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
    print(json.dumps({"ok": report["ok"], "coverage": report["coverage"],
                      "errors": report["errors"], "warnings": report["warnings"],
                      "report": args.out}, ensure_ascii=False))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
