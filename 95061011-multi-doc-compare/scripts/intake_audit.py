#!/usr/bin/env python3
"""Scope/figure/conflict hard gate for multi-doc-compare (stdlib only).

Usage: python3 scripts/intake_audit.py audit --work /app/work
Reads corpus_index.json, evidence_cards.jsonl, relations.json and
case_meta.json; writes document_audit.json. Exit 1 means a scope exclusion,
unreadable-figure boundary, or unresolved-conflict declaration was violated.
This command never infers topical relevance or invents a figure reading.
"""
import argparse
import json
import os
import sys

AUDIT_VERSION = "1.0.0"
RELEVANCE = {"relevant", "irrelevant", "uncertain"}
VERSION_STATES = {"selected", "only", "superseded", "duplicate", "unknown"}
VISUAL_REASONS = {"unreadable", "parse_failed", "not_supplied", "no_text_layer"}
REQUIRED_CHECKED = {"sample", "method", "condition", "metric", "unit"}


def _load(work, name, default):
    path = os.path.join(work, name)
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def audit_work(work, output_path=None):
    """Return a JSON-serializable report; optionally persist it."""
    errors, warnings = [], []
    index = _load(work, "corpus_index.json", {"documents": []})
    meta = _load(work, "case_meta.json", {})
    relations = _load(work, "relations.json", [])
    docs = {d.get("source_document_id"): d for d in index.get("documents", [])}
    paragraphs = {
        p.get("paragraph_id"): did
        for did, doc in docs.items() for p in doc.get("paragraphs", [])
    }
    assessments_list = meta.get("document_assessments", [])
    if not isinstance(assessments_list, list):
        assessments_list = []
        errors.append("document_assessments must be an array")
    assessments = {}
    for i, a in enumerate(assessments_list):
        if not isinstance(a, dict):
            errors.append("document_assessments[%d] must be an object" % i)
            continue
        did = a.get("source_document_id")
        if did not in docs:
            errors.append("assessment has unknown source_document_id: %r" % did)
            continue
        if did in assessments:
            errors.append("duplicate document assessment: %s" % did)
        assessments[did] = a
        relevance = a.get("relevance")
        if relevance not in RELEVANCE:
            errors.append("%s: relevance must be one of %s" % (did, sorted(RELEVANCE)))
        if a.get("version_state", "selected") not in VERSION_STATES:
            errors.append("%s: invalid version_state" % did)
        if relevance in {"irrelevant", "uncertain"}:
            if len(str(a.get("reason", "")).strip()) < 8:
                errors.append("%s: excluded/uncertain scope needs a concrete reason" % did)
            pid = a.get("paragraph_id")
            if pid not in paragraphs or paragraphs.get(pid) != did:
                errors.append("%s: scope decision needs a same-document paragraph_id" % did)
    for did in sorted(docs):
        if did not in assessments:
            errors.append("scope_missing:%s (explicit relevance/version assessment required)" % did)

    expected = meta.get("expected_document_ids")
    if isinstance(expected, list):
        missing = sorted(set(expected) - set(docs))
        if missing:
            errors.append("workorder documents missing from corpus_index: %s" % missing)
    if len(docs) >= 2 and not any(r.get("relation") in {
            "comparable", "comparable_subset", "noncomparable", "unreported"}
            for r in relations if isinstance(r, dict)):
        errors.append("multi-document task has no comparability relation")

    excluded = {
        did for did, a in assessments.items()
        if a.get("relevance") in {"irrelevant", "uncertain"}
        or a.get("version_state") in {"superseded", "duplicate"}
    }
    for i, r in enumerate(relations):
        if not isinstance(r, dict):
            errors.append("relations[%d] must be an object" % i)
            continue
        used = excluded.intersection(r.get("documents", []))
        if used:
            errors.append("relations[%d] uses excluded documents: %s" % (i, sorted(used)))

    visual_gaps = meta.get("visual_gaps", [])
    if not isinstance(visual_gaps, list):
        visual_gaps = []
        errors.append("visual_gaps must be an array")
    unreadable = set()
    for i, gap in enumerate(visual_gaps):
        if not isinstance(gap, dict):
            errors.append("visual_gaps[%d] must be an object" % i)
            continue
        did, fid = gap.get("source_document_id"), gap.get("figure_id")
        if did not in docs or not fid:
            errors.append("visual_gaps[%d] needs a known document and figure_id" % i)
            continue
        if gap.get("reason") not in VISUAL_REASONS:
            errors.append("visual_gaps[%d] invalid reason" % i)
        unreadable.add((did, str(fid)))

    cards = []
    cards_path = os.path.join(work, "evidence_cards.jsonl")
    if os.path.exists(cards_path):
        with open(cards_path, encoding="utf-8") as f:
            for line_no, line in enumerate(f, 1):
                if not line.strip():
                    continue
                try:
                    cards.append((line_no, json.loads(line)))
                except json.JSONDecodeError:
                    # The main schema validator reports the detailed parse error.
                    continue
    for line_no, card in cards:
        if card.get("source_kind") != "figure":
            continue
        did, fid = card.get("source_document_id"), str(card.get("figure_id") or "")
        if not fid:
            errors.append("evidence_cards line %d: figure card needs figure_id" % line_no)
        if card.get("confidence") != "inferred":
            errors.append("evidence_cards line %d: figure reading must be inferred" % line_no)
        if (did, fid) in unreadable:
            errors.append("evidence_cards line %d: unreadable figure used as evidence: %s@%s" %
                          (line_no, did, fid))

    unresolved = []
    for i, r in enumerate(relations):
        if not isinstance(r, dict) or r.get("relation") != "conflicting":
            continue
        if r.get("attribution") != "unattributable":
            continue
        item = {"relation_index": i, "documents": r.get("documents", []),
                "resolution_status": r.get("resolution_status")}
        unresolved.append(item)
        if r.get("resolution_status") != "unresolved":
            errors.append("relations[%d]: unattributable conflict must remain resolution_status=unresolved" % i)
        checked = r.get("checked_dims")
        if not isinstance(checked, list) or not REQUIRED_CHECKED.issubset(set(checked)):
            errors.append("relations[%d]: unattributable conflict must record checks of %s" %
                          (i, sorted(REQUIRED_CHECKED)))
        if len(str(r.get("explanation", "")).strip()) < 20:
            errors.append("relations[%d]: unresolved conflict needs >=20-char search explanation" % i)

    report = {
        "audit_version": AUDIT_VERSION,
        "ok": not errors,
        "documents": len(docs),
        "assessed_documents": len(assessments),
        "excluded_documents": sorted(excluded),
        "visual_gaps": visual_gaps,
        "unresolved_conflicts": unresolved,
        "errors": errors,
        "warnings": warnings,
    }
    path = output_path or os.path.join(work, "document_audit.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=1)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    audit = sub.add_parser("audit")
    audit.add_argument("--work", required=True)
    args = parser.parse_args()
    try:
        report = audit_work(args.work)
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        report = {"audit_version": AUDIT_VERSION, "ok": False,
                  "errors": ["audit input error: %s" % exc]}
        print(json.dumps(report, ensure_ascii=False, indent=1))
        return 1
    print(json.dumps(report, ensure_ascii=False, indent=1))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
