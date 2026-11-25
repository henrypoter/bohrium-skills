#!/usr/bin/env python3
"""Material preflight and independent answer-anchor binding audit (stdlib only).

python3 scripts/delivery_guard.py inspect FILE [--max-file-mib 64]
python3 scripts/delivery_guard.py audit --workdir SESSION [--result result_draft.json]

inspect exits 1 for missing/encrypted/oversized input and returns a stable code.
audit independently re-reads the source, page store, session and optional export.
It checks document/answer hashes, exact or whitespace-normalized quote binding,
page identity, answer/evidence ids and exported W3C annotations. Fuzzy and
page/line fallbacks never pass as verified. Exit 1 identifies binding defects.
"""
import argparse
import hashlib
import json
import os
import re
import sys

GUARD_VERSION = "1.0.0"
VERIFIED = {"verbatim", "normalized"}


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def digest_text(text):
    return hashlib.sha256(str(text).encode("utf-8")).hexdigest()


def canonical_digest(obj):
    raw = json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return digest_text(raw)


def norm(text):
    return re.sub(r"\s+", " ", str(text or "")).strip()


def nows(text):
    return re.sub(r"\s+", "", str(text or ""))


def material_version(path, with_hash=True):
    stat = os.stat(path)
    return {"path": os.path.abspath(path), "bytes": stat.st_size,
            "sha256": sha256_file(path) if with_hash else None,
            "format": "pdf" if path.lower().endswith(".pdf") else "text"}


def inspect_material(path, max_file_mib=64.0):
    """Return preflight metadata; no PDF renderer or third-party package needed."""
    if not os.path.isfile(path):
        return {"ok": False, "code": "material_missing", "status": "failed",
                "action": "检查 case.json 的材料路径；缺失不得猜测原文", "path": path}
    version = material_version(path, with_hash=False)
    limit = float(max_file_mib)
    if limit <= 0:
        return {"ok": False, "code": "invalid_size_limit", "status": "failed",
                "action": "--max-file-mib 必须大于 0"}
    if version["bytes"] > limit * 1024 * 1024:
        version["limit_mib"] = limit
        return {"ok": False, "code": "oversized_file", "status": "partial",
                "action": "请求可复制文本/分卷；提高显式限额后重试；不得假装已读",
                "material_version": version}
    version["sha256"] = sha256_file(path)
    if path.lower().endswith(".pdf"):
        # A trailer/dictionary /Encrypt reference is a reliable preflight signal
        # for the minimal PDFs handled here; pdftotext stderr remains the second
        # line of defence for nonstandard encryption dictionaries.
        encrypted = False
        with open(path, "rb") as f:
            raw = f.read()
        encrypted = bool(re.search(rb"/Encrypt\s+\d+\s+\d+\s+R\b", raw))
        if not encrypted:
            encrypted = bool(re.search(rb"/Encrypt\s*<<", raw))
        if encrypted:
            return {"ok": False, "code": "encrypted_pdf", "status": "partial",
                    "action": "请求无密码可读副本或合法解密后重试；不猜测内容",
                    "material_version": version}
    return {"ok": True, "code": None, "status": "readable",
            "material_version": version}


def _load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def audit_bindings(workdir, result_path=None):
    errors, answer_reports = [], []
    session_path = os.path.join(workdir, "session.json")
    pages_path = os.path.join(workdir, "pages.jsonl")
    session = _load_json(session_path)
    pages = {}
    if os.path.exists(pages_path):
        with open(pages_path, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    page = json.loads(line)
                    pages[page.get("page")] = page.get("text", "")
    expected_version = session.get("material_version") or {}
    expected_doc_sha = expected_version.get("sha256")
    source = session.get("doc")
    if source and expected_doc_sha:
        if not os.path.isfile(source):
            errors.append("source_missing:%s" % source)
        elif sha256_file(source) != expected_doc_sha:
            errors.append("source_hash_mismatch: document changed after answers were bound")
    elif not session.get("last_open_error"):
        errors.append("material_version_missing")

    exported = _load_json(result_path) if result_path else None
    if exported is not None:
        if exported.get("material_version") != expected_version:
            errors.append("result_material_version_mismatch")
        if not exported.get("tool_version") or not exported.get("schema_version"):
            errors.append("result_tool_or_schema_version_missing")
        exported_answers = {a.get("answer_id"): a for a in exported.get("answers", [])}
    else:
        exported_answers = {}

    expected_annotation_ids = set()
    for qa in session.get("qa", []):
        qid = qa.get("answer_id")
        aid_errors = []
        answer = qa.get("answer", "")
        if not qid:
            aid_errors.append("answer_id_missing")
        if qa.get("answer_sha256") != digest_text(answer):
            aid_errors.append("answer_hash_mismatch")
        if expected_doc_sha and qa.get("document_sha256") != expected_doc_sha:
            aid_errors.append("answer_document_hash_mismatch")
        if qa.get("selection_sha256") != canonical_digest(qa.get("selection")):
            aid_errors.append("selection_hash_mismatch")
        if not qa.get("evidence"):
            aid_errors.append("answer_has_no_evidence")
        for i, evidence in enumerate(qa.get("evidence", []), 1):
            eid = evidence.get("evidence_id")
            expected_annotation_ids.add(eid)
            if evidence.get("answer_id") != qid or not eid:
                aid_errors.append("evidence_parent_binding_missing:%d" % i)
            if evidence.get("document_sha256") != expected_doc_sha:
                aid_errors.append("evidence_document_hash_mismatch:%d" % i)
            anchor = evidence.get("anchor") or {}
            exact = anchor.get("exact", "")
            if norm(exact) != norm(evidence.get("quote", "")):
                aid_errors.append("quote_anchor_mismatch:%d" % i)
            if anchor.get("confidence") not in VERIFIED:
                aid_errors.append("anchor_not_verified:%d" % i)
            page_no = anchor.get("physical_page")
            text = pages.get(page_no)
            if text is None:
                aid_errors.append("anchor_page_missing:%d" % i)
            else:
                raw_hit = exact and exact in text
                normalized_hit = nows(exact) and nows(exact) in nows(text)
                if not (raw_hit or normalized_hit):
                    aid_errors.append("quote_not_on_anchor_page:%d" % i)
            if not all(k in anchor for k in ("prefix", "exact", "suffix")):
                aid_errors.append("text_quote_selector_incomplete:%d" % i)
        if exported is not None:
            out_answer = exported_answers.get(qid)
            if out_answer is None:
                aid_errors.append("answer_missing_from_export")
            else:
                if out_answer.get("answer") != answer:
                    aid_errors.append("exported_answer_mismatch")
                if out_answer.get("answer_sha256") != qa.get("answer_sha256"):
                    aid_errors.append("exported_answer_hash_mismatch")
        answer_reports.append({"answer_id": qid, "evidence": len(qa.get("evidence", [])),
                               "bound": not aid_errors, "errors": sorted(set(aid_errors))})
        errors.extend("%s:%s" % (qid or "answer?", e) for e in sorted(set(aid_errors)))

    if exported is not None:
        extra = sorted(set(exported_answers) - {qa.get("answer_id") for qa in session.get("qa", [])})
        if extra:
            errors.append("export_contains_unbound_answers:%s" % extra)
        annotations_path = os.path.join(os.path.dirname(os.path.abspath(result_path)),
                                        "annotations.json")
        if os.path.exists(annotations_path):
            annotations = _load_json(annotations_path)
            if annotations.get("material_version") != expected_version:
                errors.append("annotations_material_version_mismatch")
            by_id = {a.get("id"): a for a in annotations.get("annotations", [])}
            for qid in expected_annotation_ids - set(by_id):
                errors.append("annotation_missing:%s" % qid)
            out_by_qid = {q.get("answer_id"): q for q in session.get("qa", [])}
            for eid in expected_annotation_ids.intersection(by_id):
                ann = by_id[eid]
                qid = (ann.get("body") or {}).get("answer_id")
                source_answer = out_by_qid.get(qid)
                if not qid or source_answer is None:
                    errors.append("annotation_answer_parent_missing:%s" % eid)
                    continue
                if (ann.get("body") or {}).get("answer") != source_answer.get("answer"):
                    errors.append("annotation_answer_mismatch:%s" % eid)
                if ann.get("answer_sha256") != source_answer.get("answer_sha256"):
                    errors.append("annotation_answer_hash_mismatch:%s" % eid)

    report = {"guard_version": GUARD_VERSION, "ok": not errors,
              "document_sha256": expected_doc_sha, "answers": len(answer_reports),
              "bound_answers": sum(a["bound"] for a in answer_reports),
              "answer_bindings": answer_reports, "errors": errors}
    out_path = os.path.join(workdir, "binding_audit.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=1)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    inspect = sub.add_parser("inspect")
    inspect.add_argument("file")
    inspect.add_argument("--max-file-mib", type=float, default=64.0)
    audit = sub.add_parser("audit")
    audit.add_argument("--workdir", required=True)
    audit.add_argument("--result")
    args = parser.parse_args()
    try:
        if args.command == "inspect":
            report = inspect_material(args.file, args.max_file_mib)
        else:
            report = audit_bindings(args.workdir, args.result)
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        report = {"guard_version": GUARD_VERSION, "ok": False,
                  "errors": ["guard input error: %s" % exc]}
    print(json.dumps(report, ensure_ascii=False, indent=1))
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
