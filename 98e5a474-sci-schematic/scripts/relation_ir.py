#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""relation_ir.py — 文字到“实体—关系”候选 IR 的保守抽取与漂移审计。

用法：
  python3 scripts/relation_ir.py extract SOURCE.txt DRAFT.json [--report REPORT.json]
  python3 scripts/relation_ir.py audit SOURCE.txt ELEMENTS.json

extract 只识别明确词法模式（activates/inhibits/binds/phosphorylates/drives、
is converted to，以及 激活/抑制/促进/上调/下调/转化为/生成）。输出始终是
status=draft_requires_review 的候选 elements.json；未识别句子进 uncertainties，
不得把无匹配当成“没有关系”。实体 kind 统一 entity，不猜生物类型。
audit 重新抽取并对齐 from/to/type，可抓关系类型、上下游方向和额外实体漂移。
抽取/审计不是科学语义证明，最终仍须材料双通道校验与人工/LLM Judge。

退出：0=已抽取/审计一致；1=audit 漂移；2=输入错误；3=无可抽取关系（不写 DRAFT）。
纯 Python 标准库，无外部模型或服务。
"""
import argparse
import hashlib
import json
import os
import re
import sys

VERSION = "1.0.0"
WORD = r"[A-Za-z][A-Za-z0-9_-]*"
LEFT = WORD + r"(?:\s+" + WORD + r"){0,4}"
VERB = r"activates|inhibits|binds|phosphorylates|drives"
PATTERNS = [
    (re.compile(r"(?P<left>" + LEFT + r")\s+(?P<verb>" + VERB + r")\s+(?:the\s+)?(?P<right>" + WORD + r")", re.I), "english"),
    (re.compile(r"(?P<left>" + LEFT + r")\s+(?P<verb>is converted to)\s+(?:the\s+)?(?P<right>" + WORD + r")", re.I), "english"),
    (re.compile(r"(?P<left>[一-鿿A-Za-z0-9_-]{1,30}?)(?P<verb>激活|抑制|促进|上调|下调|转化为|生成)(?P<right>[一-鿿A-Za-z0-9_-]{1,30})"), "chinese"),
]
TYPE = {"activates": "activates", "drives": "activates", "phosphorylates": "activates",
        "激活": "activates", "促进": "activates", "上调": "activates",
        "inhibits": "inhibits", "抑制": "inhibits", "下调": "inhibits",
        "binds": "flows", "is converted to": "flows", "转化为": "flows", "生成": "flows"}


def digest(raw):
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def clean_entity(text):
    value = str(text).strip(" \t\r\n.,;:!?，。；：！？()[]{}（）")
    value = re.sub(r"^(?:the|a|an)\s+", "", value, flags=re.I)
    value = re.sub(r"^(?:and|then|thus|while)\s+", "", value, flags=re.I)
    value = re.sub(r"^(?:因此|所以|然后|随后|并且|而|和|并)", "", value)
    return value.strip()


def short_quote(text):
    value = re.sub(r"\s+", " ", str(text)).strip(" \t\r\n.,;:!?，。；：！？")
    if len(value) <= 30:
        return value
    # Keep a verbatim prefix that includes the relation whenever possible.
    return value[:30].rstrip()


def safe_ids(labels):
    ids, used = {}, set()
    for label in labels:
        base = re.sub(r"[^A-Za-z0-9_-]+", "_", label).strip("_") or "entity"
        candidate, n = base, 2
        while candidate in used:
            candidate = "%s_%d" % (base, n)
            n += 1
        used.add(candidate)
        ids[label] = candidate
    return ids


def extract_text(raw, filename):
    relations, unmatched = [], []
    lines = raw.splitlines()
    for line_no, line in enumerate(lines, 1):
        if not line.strip():
            continue
        found = []
        occupied = []
        for pattern, language in PATTERNS:
            for match in pattern.finditer(line):
                # Avoid nested English matches from the generic left-entity pattern.
                span = match.span()
                if any(not (span[1] <= a or span[0] >= b) for a, b in occupied):
                    continue
                left, right = clean_entity(match.group("left")), clean_entity(match.group("right"))
                verb = match.group("verb")
                if not left or not right or left == right:
                    continue
                occupied.append(span)
                found.append({"from_label": left, "to_label": right, "type": TYPE[verb.lower()],
                              "label": verb, "quote": short_quote(match.group(0)), "line": line_no,
                              "language": language})
        if found:
            relations.extend(found)
        else:
            unmatched.append({"line": line_no, "text": line.strip(),
                              "locator": "%s:L%d" % (filename, line_no)})
    labels = list(dict.fromkeys([r[k] for r in relations for k in ("from_label", "to_label")]))
    ids = safe_ids(labels)
    nodes = [{"id": ids[label], "label": label, "kind": "entity",
              "source": {"locator": "%s:L%d" % (filename, next(r["line"] for r in relations
                         if label in (r["from_label"], r["to_label"]))), "quote": short_quote(label)}}
             for label in labels]
    edges = [{"from": ids[r["from_label"]], "to": ids[r["to_label"]], "type": r["type"],
              "label": r["label"],
              "source": {"locator": "%s:L%d" % (filename, r["line"]), "quote": r["quote"]}}
             for r in relations]
    pairs = {}
    for r in relations:
        pairs.setdefault((r["from_label"], r["to_label"]), set()).add(r["type"])
    ambiguous = [{"from": a, "to": b, "types": sorted(types)} for (a, b), types in pairs.items() if len(types) > 1]
    uncertainties = [{"code": "no_supported_relation_pattern", "status": "needs_review", **row}
                     for row in unmatched]
    uncertainties += [{"code": "conflicting_relation_wording", "status": "needs_review", **row}
                      for row in ambiguous]
    report = {"schema_version": "sci-schematic-relation-ir/1.0", "tool_version": VERSION,
              "source_file": filename, "source_sha256": digest(raw),
              "relations": len(relations), "entities": len(nodes), "unmatched_lines": unmatched,
              "ambiguous_pairs": ambiguous, "review_required": True,
              "scope": "literal lexical patterns only; not scientific validation"}
    spec = {"schema_version": "sci-schematic-elements/1.0", "status": "draft_requires_review",
            "title": "DRAFT: source-bound relation candidates", "canvas": {"width": 900, "height": 560},
            "nodes": nodes, "edges": edges, "groups": [], "legend": "auto", "required": [],
            "units_notes": [], "uncertainties": uncertainties,
            "change_log": [{"item": "relation_extraction", "decision": "deterministic lexical candidates; review required",
                            "confirmed_by": "not_confirmed"}], "extraction": report}
    return spec, report


def relation_signatures(spec):
    labels = {n.get("id"): n.get("label") for n in spec.get("nodes") or []}
    result = []
    for edge in spec.get("edges") or []:
        result.append((labels.get(edge.get("from"), edge.get("from")),
                       labels.get(edge.get("to"), edge.get("to")), edge.get("type")))
    return result


def audit(raw, filename, spec):
    expected, report = extract_text(raw, filename)
    errors = []
    extraction = spec.get("extraction") or {}
    if extraction.get("source_sha256") != digest(raw):
        errors.append({"code": "source_digest_mismatch", "message": "spec 未绑定当前材料 SHA-256，须重新 extract/audit"})
    want = sorted(relation_signatures(expected))
    got = sorted(relation_signatures(spec))
    missing = [x for x in want if x not in got]
    extra = [x for x in got if x not in want]
    # Remove one-to-one matches so duplicates cannot hide drift.
    remaining = list(got)
    for item in want:
        if item in remaining:
            remaining.remove(item)
    if missing:
        errors.append({"code": "relation_missing_or_direction_type_drift", "relations": missing})
    if remaining:
        errors.append({"code": "relation_extra_or_direction_type_drift", "relations": remaining})
    expected_labels = {n.get("label") for n in expected.get("nodes", [])}
    actual_labels = {n.get("label") for n in spec.get("nodes", [])}
    fabricated = sorted(actual_labels - expected_labels)
    if fabricated:
        errors.append({"code": "entity_not_extracted_from_text", "entities": fabricated})
    return {"ok": not errors, "errors": errors, "expected_relations": len(want),
            "actual_relations": len(got), "source_sha256": digest(raw),
            "unmatched_lines": report["unmatched_lines"],
            "note": "literal relation drift audit; scientific judgement remains external"}


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="command", required=True)
    ex = sub.add_parser("extract")
    ex.add_argument("source")
    ex.add_argument("out")
    ex.add_argument("--report")
    au = sub.add_parser("audit")
    au.add_argument("source")
    au.add_argument("elements")
    args = ap.parse_args()
    try:
        with open(args.source, encoding="utf-8") as f:
            raw = f.read()
        filename = os.path.basename(args.source)
        if args.command == "extract":
            spec, report = extract_text(raw, filename)
            if not spec["edges"]:
                print(json.dumps({"ok": False, "reason": "no_supported_relation_pattern",
                                  "unmatched_lines": report["unmatched_lines"]}, ensure_ascii=False))
                return 3
            with open(args.out, "w", encoding="utf-8") as f:
                json.dump(spec, f, ensure_ascii=False, indent=2)
            if args.report:
                with open(args.report, "w", encoding="utf-8") as f:
                    json.dump(report, f, ensure_ascii=False, indent=2)
            print(json.dumps({"ok": True, "status": spec["status"], "out": args.out,
                              "entities": len(spec["nodes"]), "relations": len(spec["edges"]),
                              "unmatched_lines": len(report["unmatched_lines"]),
                              "review_required": True}, ensure_ascii=False))
            return 0
        with open(args.elements, encoding="utf-8") as f:
            spec = json.load(f)
        result = audit(raw, filename, spec)
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result["ok"] else 1
    except (OSError, ValueError, TypeError) as exc:
        print(json.dumps({"ok": False, "input_error": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    sys.exit(main())
