#!/usr/bin/env python3
"""Standard-library-only, deterministic guards for source-bound scientific figures.

Commands (JSON on stdout; 0=pass, 1=validation failure, 2=usage/I/O error):
  preflight --spec chart_spec.json
      Fail before drawing on ambiguous/missing mappings; report actionable warnings.
  lookup --mapping FIG_mapping_report.json (--element N | --source FILE --row N)
      Forward glyph->source and reverse source row->glyph lookup with cell evidence.
  edit-svg --input in.svg --operations edits.json --output out.svg --log edit_log.json
      Preconditioned, non-destructive SVG text/attribute editing; source is never overwritten.
  compare --baseline run.json --candidate run.json [--result result.json]
      Fair measured baseline/Skill comparison; never invents a baseline or score.
  contract --result result.json [--case /input/case.json]
      Preserve original output_contract fields and validate status/output/gain honesty.

No third-party imports, network access, wall-clock timestamps, or fabricated measurements.
"""
import argparse
import csv
import hashlib
import json
import math
import os
import re
import sys
import tempfile
import xml.etree.ElementTree as ET

EMPTY = {"", "-", "--", "NA", "N/A", "NaN", "nan", "null", "None"}


def dump(obj):
    print(json.dumps(obj, ensure_ascii=False, sort_keys=True))


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(65536), b""):
            h.update(block)
    return h.hexdigest()


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def atomic_json(path, obj):
    parent = os.path.dirname(os.path.abspath(path))
    os.makedirs(parent, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".guard-", suffix=".json", dir=parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=2, sort_keys=True)
            f.write("\n")
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def norm(s):
    return " ".join(str(s).replace("µ", "μ").replace("-\n", "").split())


def number(value):
    if value is None or str(value).strip() in EMPTY:
        return None
    try:
        v = float(str(value).strip().replace(",", ""))
        return v if math.isfinite(v) else None
    except (TypeError, ValueError):
        return None


def table(path, delimiter=None):
    if not delimiter:
        with open(path, encoding="utf-8-sig", errors="replace") as f:
            first = f.readline()
        delimiter = "\t" if path.lower().endswith((".tsv", ".tab")) or first.count("\t") > first.count(",") else ","
    with open(path, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f, delimiter=delimiter)
        rows = list(reader)
        return rows, list(reader.fieldnames or [])


def mappings(panel):
    for key in ("x", "y", "series", "error", "significance", "value"):
        value = panel.get(key)
        if isinstance(value, dict) and value.get("column"):
            yield key, value


def preflight(args):
    spec = load_json(args.spec)
    errors, warnings, sources = [], [], {}
    cache = {}

    def err(code, message, panel="*"):
        errors.append({"code": code, "panel": panel, "message": message})

    def warn(code, message, action, panel="*"):
        warnings.append({"code": code, "panel": panel, "message": message, "action": action})

    panels = spec.get("panels")
    if not isinstance(panels, list) or not panels:
        err("panels_missing", "panels must be a non-empty list")
        panels = []
    for p in panels:
        pid = str(p.get("panel_id", "?"))
        src = p.get("source") or {}
        path = src.get("file")
        if not path or not os.path.isfile(path):
            err("source_missing", "source.file is missing or unreadable: %s" % path, pid)
            continue
        if path not in cache:
            try:
                cache[path] = table(path, src.get("delimiter"))
                sources[os.path.abspath(path)] = {"sha256": sha256(path), "rows": len(cache[path][0])}
            except Exception as exc:
                err("source_read", "%s: %s" % (path, exc), pid)
                continue
        rows, header = cache[path]
        for key, m in mappings(p):
            col = m.get("column")
            if col not in header:
                err("missing_column", "%s.column %r not in verbatim header %r" % (key, col, header), pid)
            quote = m.get("quote")
            if quote is not None:
                with open(path, encoding="utf-8-sig", errors="replace") as f:
                    head = norm(f.read(8192))
                if norm(col) not in norm(quote) or norm(quote) not in head:
                    err("quote_mismatch", "%s.quote must occur in source head and contain its column" % key, pid)
        x, y = (p.get("x") or {}).get("column"), (p.get("y") or {}).get("column")
        value_col = (p.get("value") or {}).get("column") if p.get("chart_type") == "heatmap" else y
        series_col = (p.get("series") or {}).get("column")
        if value_col in header:
            invalid, empty, vals = [], [], []
            for i, row in enumerate(rows, 2):
                raw = row.get(value_col)
                val = number(raw)
                if val is None:
                    (empty if raw is None or str(raw).strip() in EMPTY else invalid).append(i)
                else:
                    vals.append(val)
            if invalid:
                err("nonnumeric_value", "%s has non-numeric cells at source rows %s" % (value_col, invalid[:12]), pid)
            if empty:
                warn("empty_value", "%s has %d empty cells at rows %s" % (value_col, len(empty), empty[:12]),
                     "Keep them missing; report counts and do not interpolate or treat them as zero.", pid)
            if vals:
                mx = max(abs(v) for v in vals)
                if mx >= 1e6 or (mx and mx < 1e-3):
                    warn("magnitude", "%s max absolute value is %.6g" % (value_col, mx),
                         "State the source scale and use scientific notation/unit prefix only with an explicit change_log.", pid)
        if x in header:
            for label in sorted({str(r.get(x, "")) for r in rows}):
                visual_len = sum(2 if ord(c) > 255 else 1 for c in label)
                if visual_len > 32:
                    warn("long_label", "x label is %d display cells: %r" % (visual_len, label[:80]),
                         "Rotate/wrap without changing the source entity spelling; rerun overlap/export checks.", pid)
        seen = {}
        if p.get("chart_type") in ("bar", "heatmap") and x in header and value_col in header:
            for i, row in enumerate(rows, 2):
                key = (row.get(x), row.get(y)) if p.get("chart_type") == "heatmap" else (row.get(x), row.get(series_col) if series_col else None)
                if key in seen:
                    err("duplicate_glyph_key", "rows %s and %s map to the same %s glyph key %r" % (seen[key], i, p.get("chart_type"), key), pid)
                else:
                    seen[key] = i
        error = p.get("error") or {}
        ecol = error.get("column")
        if ecol in header:
            for i, row in enumerate(rows, 2):
                raw = row.get(ecol)
                val = number(raw)
                if val is None or val < 0:
                    err("invalid_errorbar", "%s row %d must be a finite non-negative number, got %r" % (ecol, i, raw), pid)
            caption = str(spec.get("caption", "")).lower()
            if not re.search(r"error\s*bar|误差线|标准差|标准误|置信区间|\bsd\b|\bsem?\b|\bci(?:90|95|99)?\b", caption):
                err("errorbar_caption", "caption must define the selected error-bar meaning (%s)" % error.get("kind"), pid)
            if (spec.get("statistics") or {}).get("n") in (None, ""):
                err("sample_size", "statistics.n is required when error bars are drawn", pid)
        if p.get("significance"):
            if not (spec.get("statistics") or {}).get("test"):
                err("significance_test", "statistics.test is required for significance labels", pid)
            if not re.search(r"\bp\s*[<≤=]|显著性|\*\s*p", str(spec.get("caption", "")), re.I):
                warn("significance_convention", "caption does not state the p/significance convention",
                     "Copy the source convention; never calculate or relabel significance here.", pid)
        if y in header and p.get("chart_type") != "heatmap" and not (p.get("y") or {}).get("unit"):
            warn("unit_missing", "y mapping %s has no explicit unit" % y,
                 "Copy the source unit; use '1' for dimensionless or record 'unknown' in uncertainty, never guess.", pid)
    report = {"ok": not errors, "command": "preflight", "spec": os.path.abspath(args.spec),
              "errors": errors, "warnings": warnings, "source_versions": sources,
              "policy": "errors stop drawing; warnings require an explicit disposition in change_log/uncertainty"}
    dump(report)
    return 0 if not errors else 1


def source_evidence(element):
    src = element.get("source") or {}
    path = src.get("file")
    rows, header = table(path)
    out = []
    for row_number in src.get("rows") or []:
        index = int(row_number) - 2
        if not 0 <= index < len(rows):
            raise ValueError("source row %s out of range" % row_number)
        out.append({"row": int(row_number), "cells": {c: rows[index].get(c) for c in src.get("columns") or header}})
    return out


def lookup(args):
    mapping = load_json(args.mapping)
    elements = mapping.get("elements") or []
    if args.element is not None:
        if not 0 <= args.element < len(elements):
            dump({"ok": False, "error": "element index out of range", "n_elements": len(elements)})
            return 1
        element = elements[args.element]
        result = {"ok": True, "direction": "glyph_to_source", "element_index": args.element,
                  "element": element, "source_evidence": source_evidence(element)}
    else:
        target = os.path.realpath(args.source)
        hits = []
        for i, element in enumerate(elements):
            src = element.get("source") or {}
            if os.path.realpath(src.get("file", "")) == target and args.row in (src.get("rows") or []):
                hits.append({"element_index": i, "panel": element.get("panel"), "glyph": element.get("glyph"),
                             "series": element.get("series"), "value": element.get("value")})
        if not hits:
            dump({"ok": False, "direction": "source_to_glyphs", "source": args.source, "row": args.row,
                  "error": "no glyph maps to this source row"})
            return 1
        rows, header = table(args.source)
        if not 2 <= args.row <= len(rows) + 1:
            dump({"ok": False, "error": "source row out of range"})
            return 1
        result = {"ok": True, "direction": "source_to_glyphs", "source": os.path.abspath(args.source),
                  "row": args.row, "cells": rows[args.row - 2], "glyphs": hits}
    dump(result)
    return 0


def validate_operation_source(source, value):
    if not source:
        return None
    path, row_number, col = source.get("file"), source.get("row"), source.get("column")
    rows, header = table(path)
    if col not in header or not isinstance(row_number, int) or not 2 <= row_number <= len(rows) + 1:
        raise ValueError("invalid source file/row/column: %r" % source)
    actual = rows[row_number - 2].get(col)
    if str(value) != str(actual):
        raise ValueError("edited value %r does not equal source %s row %s column %s value %r" %
                         (value, path, row_number, col, actual))
    quote = source.get("quote")
    if quote:
        with open(path, encoding="utf-8-sig", errors="replace") as f:
            text = norm(f.read())
        if norm(col) not in norm(quote) or norm(quote) not in text:
            raise ValueError("source quote is not verbatim or does not contain its column")
    return {"file": os.path.abspath(path), "row": row_number, "column": col, "value": actual,
            "sha256": sha256(path)}


def edit_svg(args):
    original_hash = sha256(args.input)
    log = {"ok": False, "input": os.path.abspath(args.input), "input_sha256": original_hash,
           "output": os.path.abspath(args.output), "operations": [], "errors": []}
    try:
        if os.path.realpath(args.input) == os.path.realpath(args.output):
            raise ValueError("output must differ from input; the original SVG is immutable")
        instruction = load_json(args.operations)
        if instruction.get("input_sha256") != original_hash:
            raise ValueError("input_sha256 precondition failed: source SVG changed or was not hashed")
        operations = instruction.get("operations")
        if not isinstance(operations, list) or not operations:
            raise ValueError("operations must be a non-empty list")
        namespaces = {}
        for event, item in ET.iterparse(args.input, events=("start-ns",)):
            prefix, uri = item
            namespaces[prefix] = uri
        for prefix, uri in namespaces.items():
            ET.register_namespace(prefix, uri)
        parser = ET.XMLParser(target=ET.TreeBuilder(insert_comments=True))
        tree = ET.parse(args.input, parser=parser)
        root = tree.getroot()
        for i, op in enumerate(operations):
            oid, action = op.get("id"), op.get("op")
            if not oid or action not in ("set_text", "set_attr", "remove_attr"):
                raise ValueError("operation %d needs id and op=set_text/set_attr/remove_attr" % i)
            if not op.get("reason"):
                raise ValueError("operation %d lacks a human-auditable reason" % i)
            hits = [el for el in root.iter() if el.get("id") == oid]
            if len(hits) != 1:
                raise ValueError("operation %d id %r matched %d elements; require exactly one" % (i, oid, len(hits)))
            el = hits[0]
            if action == "set_text":
                if list(el):
                    raise ValueError("set_text on %r with child nodes is refused; target a leaf <text>/<tspan>" % oid)
                before = "".join(el.itertext())
                after = str(op.get("value", ""))
                evidence = validate_operation_source(op.get("source"), after)
                if "expected" not in op or before != str(op["expected"]):
                    raise ValueError("text precondition failed for %r: expected %r, found %r" % (oid, op.get("expected"), before))
                el.text = after
                attr = None
            else:
                attr = op.get("attribute")
                if not attr or attr == "id":
                    raise ValueError("attribute is required and id cannot be edited")
                before = el.get(attr)
                expected = op.get("expected")
                if "expected" not in op or before != (None if expected is None else str(expected)):
                    raise ValueError("attribute precondition failed for %r/%s: expected %r, found %r" % (oid, attr, expected, before))
                after = None if action == "remove_attr" else str(op.get("value", ""))
                evidence = validate_operation_source(op.get("source"), after) if action == "set_attr" else None
                if action == "remove_attr":
                    del el.attrib[attr]
                else:
                    el.set(attr, after)
            log["operations"].append({"index": i, "id": oid, "op": action, "attribute": attr,
                                      "before": before, "after": after, "reason": op["reason"], "source": evidence})
        parent = os.path.dirname(os.path.abspath(args.output))
        os.makedirs(parent, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix=".svg-edit-", suffix=".svg", dir=parent)
        os.close(fd)
        try:
            tree.write(tmp, encoding="utf-8", xml_declaration=True)
            os.replace(tmp, args.output)
        except Exception:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
        if sha256(args.input) != original_hash:
            raise ValueError("input changed during editing")
        log.update({"ok": True, "output_sha256": sha256(args.output),
                    "original_preserved": True,
                    "exports": "SVG only: rerender PNG/PDF from this exact SVG; old raster/PDF exports are stale"})
    except Exception as exc:
        log["errors"].append(str(exc))
        dump(log)
        atomic_json(args.log, log)
        return 1
    atomic_json(args.log, log)
    dump(log)
    return 0


REQUIRED_METRICS = ("glyph_total", "glyph_value_errors", "legend_total", "legend_errors",
                    "annotation_total", "annotation_errors", "export_total", "export_errors")


def checked_record(record, expected_condition):
    if record.get("condition") != expected_condition:
        raise ValueError("condition must be %s" % expected_condition)
    if not record.get("case_id") or not record.get("input_sha256") or not isinstance(record.get("export_spec"), dict):
        raise ValueError("case_id/input_sha256/export_spec are required")
    for key in ("elapsed_seconds", "model_requests", "manual_edits", "redraw_rounds"):
        value = record.get(key)
        if not isinstance(value, (int, float)) or isinstance(value, bool) or value < 0:
            raise ValueError("%s must be a measured non-negative number" % key)
    metrics = record.get("metrics") or {}
    for key in REQUIRED_METRICS:
        value = metrics.get(key)
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise ValueError("metrics.%s must be a non-negative integer" % key)
    for total, errors in (("glyph_total", "glyph_value_errors"), ("legend_total", "legend_errors"),
                          ("annotation_total", "annotation_errors"), ("export_total", "export_errors")):
        if metrics[errors] > metrics[total]:
            raise ValueError("%s exceeds %s" % (errors, total))
    if not isinstance(record.get("editable_source"), bool):
        raise ValueError("editable_source must be observed true/false")
    return metrics


def rate(total, errors):
    return None if total == 0 else round((total - errors) / total, 6)


def compare(args):
    try:
        baseline, candidate = load_json(args.baseline), load_json(args.candidate)
        bm, cm = checked_record(baseline, "baseline"), checked_record(candidate, "skill")
        for key in ("case_id", "input_sha256", "export_spec"):
            if baseline.get(key) != candidate.get(key):
                raise ValueError("unfair comparison: %s differs" % key)
        quality = {}
        for name, total, errors in (("glyph_value_accuracy", "glyph_total", "glyph_value_errors"),
                                    ("legend_accuracy", "legend_total", "legend_errors"),
                                    ("annotation_completeness", "annotation_total", "annotation_errors"),
                                    ("export_compliance", "export_total", "export_errors")):
            br, cr = rate(bm[total], bm[errors]), rate(cm[total], cm[errors])
            quality[name] = {"baseline": br, "skill": cr,
                             "delta": None if br is None or cr is None else round(cr - br, 6)}
        quality["editable_source"] = {"baseline": baseline["editable_source"], "skill": candidate["editable_source"],
                                      "delta": int(candidate["editable_source"]) - int(baseline["editable_source"])}
        efficiency = {}
        for key in ("elapsed_seconds", "model_requests", "manual_edits", "redraw_rounds"):
            b, c = baseline[key], candidate[key]
            efficiency[key] = {"baseline": b, "skill": c, "reduction": b - c,
                               "relative_reduction": None if b == 0 else round((b - c) / b, 6)}
        gain = {"status": "measured", "comparison": {"case_id": baseline["case_id"],
                "input_sha256": baseline["input_sha256"], "export_spec": baseline["export_spec"],
                "conditions": ["baseline", "skill"]}, "quality": quality, "efficiency": efficiency,
                "evidence": {"baseline": baseline, "candidate": candidate},
                "interpretation": "Rates/deltas only; no unmeasured aggregate score is claimed."}
        if args.result:
            result = load_json(args.result)
            if result.get("case_id") != baseline["case_id"]:
                raise ValueError("result case_id does not match comparison")
            result["gain"] = gain
            atomic_json(args.result, result)
        dump({"ok": True, "gain": gain})
        return 0
    except Exception as exc:
        dump({"ok": False, "command": "compare", "error": str(exc),
              "action": "Provide two actual same-input run records; otherwise gain.status='not_run'."})
        return 1


def required_contract_fields(case):
    contract = (case or {}).get("output_contract") or {}
    required = set()
    if isinstance(contract, list):
        required.update(str(x) for x in contract)
    elif isinstance(contract, dict):
        if isinstance(contract.get("required"), list):
            required.update(str(x) for x in contract["required"])
        fields = contract.get("fields")
        if isinstance(fields, list):
            required.update(str(x) for x in fields)
        elif isinstance(fields, dict):
            required.update(str(x) for x in fields)
        properties = contract.get("properties")
        if isinstance(properties, dict) and not required:
            required.update(str(x) for x in properties)
    required.update(("case_id", "status", "sources", "uncertainty", "change_log"))
    return sorted(required)


def output_paths(result):
    paths = []
    def walk(value, key=None):
        if isinstance(value, dict):
            for k, v in value.items():
                walk(v, k)
        elif isinstance(value, list):
            for v in value:
                walk(v, key)
        elif isinstance(value, str) and key in ("svg", "png", "pdf", "editable_source", "preview", "mapping", "report"):
            paths.append(value)
    walk(result.get("outputs"))
    for figure in result.get("figures", []) if isinstance(result.get("figures"), list) else []:
        if isinstance(figure, dict):
            for key in ("svg", "png", "pdf", "editable_source"):
                if figure.get(key):
                    paths.append(figure[key])
    return paths


def contract(args):
    try:
        result = load_json(args.result)
        case = load_json(args.case) if args.case else None
        errors = []
        for key in required_contract_fields(case):
            if key not in result:
                errors.append("missing original output_contract field: %s" % key)
        if case and result.get("case_id") != case.get("case_id"):
            errors.append("case_id differs from /input/case.json")
        if result.get("status") not in ("complete", "answered", "partial", "failed", "issues", "ok", "done", "success"):
            errors.append("invalid or missing honest status")
        base = os.path.dirname(os.path.abspath(args.result))
        paths = output_paths(result)
        if result.get("status") in ("complete", "answered", "ok", "done", "success") and not paths:
            errors.append("complete status requires actual output paths")
        for path in paths:
            resolved = path if os.path.isabs(path) else os.path.join(base, path)
            if not os.path.isfile(resolved) or os.path.getsize(resolved) == 0:
                errors.append("output missing/empty: %s" % path)
        validation = result.get("validation") or {}
        if result.get("status") in ("complete", "answered", "ok", "done", "success"):
            if validation.get("missing_required"):
                errors.append("complete status contradicts validation.missing_required")
            for fid, item in (validation.get("verify_map") or {}).items():
                if item.get("problems"):
                    errors.append("complete status contradicts verify_map problems for %s" % fid)
        gain = result.get("gain")
        if not isinstance(gain, dict) or gain.get("status") not in ("not_run", "measured", "platform_provided"):
            errors.append("gain must be honest: status=not_run, measured, or platform_provided")
        elif gain["status"] == "measured" and not (gain.get("evidence") and gain.get("comparison")):
            errors.append("measured gain lacks run evidence/comparison identity")
        dump({"ok": not errors, "command": "contract", "required_fields": required_contract_fields(case),
              "checked_output_paths": len(paths), "errors": errors})
        return 0 if not errors else 1
    except Exception as exc:
        dump({"ok": False, "command": "contract", "error": str(exc)})
        return 1


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)
    q = sub.add_parser("preflight"); q.add_argument("--spec", required=True); q.set_defaults(func=preflight)
    q = sub.add_parser("lookup"); q.add_argument("--mapping", required=True)
    q.add_argument("--element", type=int); q.add_argument("--source"); q.add_argument("--row", type=int); q.set_defaults(func=lookup)
    q = sub.add_parser("edit-svg"); q.add_argument("--input", required=True); q.add_argument("--operations", required=True)
    q.add_argument("--output", required=True); q.add_argument("--log", required=True); q.set_defaults(func=edit_svg)
    q = sub.add_parser("compare"); q.add_argument("--baseline", required=True); q.add_argument("--candidate", required=True)
    q.add_argument("--result"); q.set_defaults(func=compare)
    q = sub.add_parser("contract"); q.add_argument("--result", required=True); q.add_argument("--case"); q.set_defaults(func=contract)
    return p


def main():
    args = parser().parse_args()
    if args.command == "lookup" and ((args.element is None) == (args.source is None or args.row is None)):
        dump({"ok": False, "error": "choose exactly one: --element N OR --source FILE --row N"})
        return 2
    try:
        return args.func(args)
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        dump({"ok": False, "command": args.command, "error": str(exc)})
        return 2


if __name__ == "__main__":
    sys.exit(main())
