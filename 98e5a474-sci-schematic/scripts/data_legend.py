#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""data_legend.py — CSV 分类表驱动的节点 kind / 自动图例同步与漂移审计。

用法：
  python3 scripts/data_legend.py sync ELEMENTS.json TABLE.csv SYNCED.json \
      --entity-column entity --category-column category [--report BINDING.json]
  python3 scripts/data_legend.py audit SYNCED.json TABLE.csv \
      --entity-column entity --category-column category

CSV 必须有表头；entity 对应 node.id 或 node.label，同一实体重复/分类冲突、空值、
缺列、类别漂移、表 SHA-256 漂移均为错误。sync 更新已有节点 kind，缺失实体则
新增带来源节点，并强制 legend=auto；随后用 build_svg.py 重绘即可同步图例。
audit 用于重绘前证明“表→node.kind→auto legend”未漂移。
错误时 sync 不写 SYNCED/REPORT，不留下貌似成功的半成品。纯标准库。
"""
import argparse
import csv
import hashlib
import json
import os
import re
import sys

VERSION = "1.0.0"


def sha256_bytes(raw):
    return hashlib.sha256(raw).hexdigest()


def load_table(path, entity_column, category_column):
    with open(path, "rb") as f:
        raw = f.read()
    text = raw.decode("utf-8-sig")
    reader = csv.DictReader(text.splitlines())
    errors = []
    if not reader.fieldnames:
        return None, [], [{"code": "csv_header_missing"}]
    if len(reader.fieldnames) != len(set(reader.fieldnames)):
        errors.append({"code": "csv_duplicate_header", "fields": reader.fieldnames})
    for col in (entity_column, category_column):
        if col not in reader.fieldnames:
            errors.append({"code": "csv_column_missing", "column": col})
    rows = []
    if errors:
        return raw, rows, errors
    for row in reader:
        entity = (row.get(entity_column) or "").strip()
        category = (row.get(category_column) or "").strip()
        record = {"entity": entity, "category": category, "line": reader.line_num}
        if not entity or not category:
            errors.append({"code": "csv_empty_required_cell", **record})
        if "\n" in entity or "\r" in entity or "\n" in category or "\r" in category:
            errors.append({"code": "csv_multiline_binding", **record})
        rows.append(record)
    if not rows:
        errors.append({"code": "csv_no_data_rows"})
    return raw, rows, errors


def find_node(nodes, entity):
    hits = [n for n in nodes if n.get("id") == entity or n.get("label") == entity]
    return hits


def validate_rows(rows):
    errors = []
    seen = {}
    for row in rows:
        entity = row["entity"]
        if entity in seen:
            code = "csv_conflicting_category" if seen[entity] != row["category"] else "csv_duplicate_entity"
            errors.append({"code": code, "entity": entity, "first_category": seen[entity],
                           "category": row["category"], "line": row["line"]})
        seen[entity] = row["category"]
    return errors


def audit_binding(spec, rows, raw, entity_column, category_column):
    errors = validate_rows(rows)
    binding = spec.get("data_binding") or {}
    expected = {"table": binding.get("table"), "entity_column": entity_column,
                "category_column": category_column, "sha256": sha256_bytes(raw)}
    if not binding:
        errors.append({"code": "data_binding_missing"})
    else:
        if binding.get("sha256") != expected["sha256"]:
            errors.append({"code": "data_table_digest_mismatch", "spec": binding.get("sha256"),
                           "actual": expected["sha256"]})
        if binding.get("entity_column") != entity_column or binding.get("category_column") != category_column:
            errors.append({"code": "data_binding_columns_mismatch"})
    if spec.get("legend") != "auto":
        errors.append({"code": "legend_not_auto_derived"})
    nodes = spec.get("nodes") or []
    mappings = []
    for row in rows:
        hits = find_node(nodes, row["entity"])
        if len(hits) > 1:
            errors.append({"code": "entity_node_ambiguous", "entity": row["entity"]})
            continue
        if not hits:
            errors.append({"code": "entity_node_missing", "entity": row["entity"]})
            continue
        node = hits[0]
        if node.get("kind") != row["category"]:
            errors.append({"code": "node_category_drift", "entity": row["entity"],
                           "node": node.get("id"), "actual": node.get("kind"), "expected": row["category"]})
        mappings.append({"entity": row["entity"], "node": node.get("id"),
                         "category_expected": row["category"], "category_actual": node.get("kind")})
    stored = spec.get("data_mapping") or []
    if len(stored) != len(rows):
        errors.append({"code": "data_mapping_row_count_mismatch", "stored": len(stored), "table": len(rows)})
    return errors, mappings


def new_id(entity, used):
    base = re.sub(r"[^A-Za-z0-9_-]+", "_", entity).strip("_") or "entity"
    candidate, i = base, 2
    while candidate in used:
        candidate = "%s_%d" % (base, i)
        i += 1
    return candidate


def synchronize(spec, table_path, raw, rows, entity_column, category_column):
    errors = validate_rows(rows)
    nodes = list(spec.get("nodes") or [])
    used = {n.get("id") for n in nodes}
    created, updated = [], []
    filename = os.path.basename(table_path)
    mapping = []
    for row in rows:
        entity, category, line = row["entity"], row["category"], row["line"]
        hits = find_node(nodes, entity)
        if len(hits) > 1:
            errors.append({"code": "entity_node_ambiguous", "entity": entity})
            continue
        data_source = {"locator": "%s:L%d" % (filename, line), "quote": entity}
        if hits:
            node = hits[0]
            if node.get("kind") != category:
                updated.append({"node": node.get("id"), "from": node.get("kind"), "to": category})
            node["kind"] = category
            node["data_source"] = data_source
        else:
            nid = new_id(entity, used)
            used.add(nid)
            node = {"id": nid, "label": entity, "kind": category, "source": data_source,
                    "data_source": data_source}
            nodes.append(node)
            created.append(nid)
        mapping.append({"entity": entity, "node": node["id"], "category": category,
                        "source": data_source, "table_sha256": sha256_bytes(raw)})
    if errors:
        return None, errors, {"created": created, "updated": updated}
    out = dict(spec)
    out["nodes"] = nodes
    out["legend"] = "auto"
    out["data_binding"] = {"schema_version": "sci-schematic-data-binding/1.0",
                           "tool_version": VERSION, "table": filename,
                           "sha256": sha256_bytes(raw), "entity_column": entity_column,
                           "category_column": category_column,
                           "row_count": len(rows), "review_required": True}
    out["data_mapping"] = mapping
    out["status"] = "data_synchronized_requires_render"
    changes = list(out.get("change_log") or [])
    changes.append({"item": "data_legend_sync", "decision": "CSV rows -> node.kind; legend:auto; redraw required",
                    "table_sha256": sha256_bytes(raw), "confirmed_by": "not_confirmed"})
    out["change_log"] = changes
    return out, [], {"created": created, "updated": updated, "rows": len(rows),
                     "categories": sorted({r["category"] for r in rows})}


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="command", required=True)
    sy = sub.add_parser("sync")
    sy.add_argument("spec")
    sy.add_argument("table")
    sy.add_argument("out")
    sy.add_argument("--entity-column", default="entity")
    sy.add_argument("--category-column", default="category")
    sy.add_argument("--report")
    au = sub.add_parser("audit")
    au.add_argument("spec")
    au.add_argument("table")
    au.add_argument("--entity-column", default="entity")
    au.add_argument("--category-column", default="category")
    args = ap.parse_args()
    try:
        with open(args.spec, encoding="utf-8") as f:
            spec = json.load(f)
        raw, rows, errors = load_table(args.table, args.entity_column, args.category_column)
        if args.command == "sync":
            synced = None
            if not errors:
                synced, errors, summary = synchronize(spec, args.table, raw, rows,
                                                       args.entity_column, args.category_column)
            else:
                summary = {}
            if errors or synced is None:
                print(json.dumps({"ok": False, "errors": errors, "outputs_written": False}, ensure_ascii=False))
                return 1
            with open(args.out, "w", encoding="utf-8") as f:
                json.dump(synced, f, ensure_ascii=False, indent=2)
            if args.report:
                with open(args.report, "w", encoding="utf-8") as f:
                    json.dump({"ok": True, "binding": synced["data_binding"], **summary}, f,
                              ensure_ascii=False, indent=2)
            print(json.dumps({"ok": True, "out": args.out, "binding": synced["data_binding"],
                              **summary, "next": "run build_svg.py then data_legend.py audit"}, ensure_ascii=False))
            return 0
        if not errors:
            errors, mappings = audit_binding(spec, rows, raw, args.entity_column, args.category_column)
        else:
            mappings = []
        print(json.dumps({"ok": not errors, "errors": errors, "rows": len(rows),
                          "mappings": mappings, "table_sha256": sha256_bytes(raw)}, ensure_ascii=False))
        return 0 if not errors else 1
    except (OSError, ValueError, TypeError, csv.Error) as exc:
        print(json.dumps({"ok": False, "input_error": str(exc), "outputs_written": False}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    sys.exit(main())
