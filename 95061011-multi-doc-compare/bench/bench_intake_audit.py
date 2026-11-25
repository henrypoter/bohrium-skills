#!/usr/bin/env python3
"""Mutation bench for intake scope, unreadable figures, conflicts and provenance."""
import copy
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
AUDIT = os.path.join(ROOT, "scripts", "intake_audit.py")
VALIDATE = os.path.join(ROOT, "scripts", "validate_and_render.py")
TMP = tempfile.mkdtemp(prefix="mdc-audit-bench-")
checks = []


def invoke(command, work, out=None):
    args = [sys.executable, command]
    if command == AUDIT:
        args += ["audit", "--work", work]
    elif out:
        args += ["result", "--work", work, "--out", out]
    else:
        args += ["validate", "--work", work]
    proc = subprocess.run(args, capture_output=True, text=True)
    if out:
        return proc.returncode, proc.stdout.strip()
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError:
        payload = {"raw": proc.stdout[-300:], "stderr": proc.stderr[-300:]}
    return proc.returncode, payload


def payload():
    docs = [
        {"source_document_id": "P1", "source_file": "P1.txt",
         "content_sha256": "1" * 64, "content_bytes": 100,
         "paragraph_count": 2,
         "paragraphs": [{"paragraph_id": "P1::p001", "text": "Methyl orange removal reached 80 percent."},
                        {"paragraph_id": "P1::p002", "text": "Figure 1 could not be read."}]},
        {"source_document_id": "P2", "source_file": "P2.txt",
         "content_sha256": "2" * 64, "content_bytes": 100,
         "paragraph_count": 1,
         "paragraphs": [{"paragraph_id": "P2::p001", "text": "Methyl orange removal reached 20 percent."}]},
        {"source_document_id": "P3", "source_file": "P3.txt",
         "content_sha256": "3" * 64, "content_bytes": 100,
         "paragraph_count": 1,
         "paragraphs": [{"paragraph_id": "P3::p001", "text": "Urban traffic noise was surveyed."}]}]
    index = {"index_version": "2.0.0", "documents": docs, "warnings": []}
    cards = [
        {"source_document_id": "P1", "field": "metric_value", "value": "80", "unit": "%",
         "paragraph_id": "P1::p001", "quote": "removal reached 80 percent", "confidence": "direct",
         "value_state": "reported-positive",
         "caliber": {"task": "degradation", "metric": "removal", "unit": "%", "object": "methyl orange"}},
        {"source_document_id": "P2", "field": "metric_value", "value": "20", "unit": "%",
         "paragraph_id": "P2::p001", "quote": "removal reached 20 percent", "confidence": "direct",
         "value_state": "reported-positive",
         "caliber": {"task": "degradation", "metric": "removal", "unit": "%", "object": "methyl orange"}}]
    relations = [
        {"dimension": "metric", "relation": "noncomparable", "documents": ["P1", "P2"],
         "blocking_dims": ["condition"], "explanation": "实验条件不同因此只允许保留原值而禁止合并",
         "evidence": [{"source_document_id": "P1", "paragraph_id": "P1::p001"},
                      {"source_document_id": "P2", "paragraph_id": "P2::p001"}]},
        {"dimension": "main_conclusion", "relation": "conflicting", "documents": ["P1", "P2"],
         "attribution": "unattributable", "resolution_status": "unresolved",
         "checked_dims": ["sample", "method", "condition", "metric", "unit"],
         "explanation": "逐项排查样本方法条件和指标单位后仍缺少可核验原因保留未解决冲突",
         "evidence": [{"source_document_id": "P1", "paragraph_id": "P1::p001"},
                      {"source_document_id": "P2", "paragraph_id": "P2::p001"}]}]
    meta = {"case_id": "synthetic-boundary", "status": "partial", "contract_fields": {},
            "document_assessments": [
                {"source_document_id": "P1", "relevance": "relevant", "version_state": "selected"},
                {"source_document_id": "P2", "relevance": "relevant", "version_state": "selected"},
                {"source_document_id": "P3", "relevance": "irrelevant", "version_state": "only",
                 "reason": "研究城市噪声而非催化降解", "paragraph_id": "P3::p001"}],
            "visual_gaps": [{"source_document_id": "P1", "figure_id": "Fig1", "reason": "unreadable"}],
            "uncertainty": [], "change_records": []}
    return index, cards, relations, meta


def make_work(name, mutate=None):
    index, cards, relations, meta = payload()
    if mutate:
        mutate(index, cards, relations, meta)
    work = os.path.join(TMP, name)
    os.makedirs(work)
    json.dump(index, open(os.path.join(work, "corpus_index.json"), "w", encoding="utf-8"))
    with open(os.path.join(work, "evidence_cards.jsonl"), "w", encoding="utf-8") as f:
        for card in cards:
            f.write(json.dumps(card, ensure_ascii=False) + "\n")
    json.dump(relations, open(os.path.join(work, "relations.json"), "w", encoding="utf-8"), ensure_ascii=False)
    json.dump(meta, open(os.path.join(work, "case_meta.json"), "w", encoding="utf-8"), ensure_ascii=False)
    return work


def add(name, condition, detail=None):
    checks.append((name, bool(condition), str(detail or "")[:180]))


good = make_work("good")
rc, report = invoke(AUDIT, good)
add("audit正向:相关/不相关/图缺口/未解决冲突均合规", rc == 0 and report.get("ok"), report.get("errors"))
rc, report = invoke(VALIDATE, good)
add("validate正向:引文真实且异常被保留零误杀", rc == 0, report.get("errors"))

work = make_work("missing_scope", lambda i, c, r, m: m["document_assessments"].pop(1))
rc, report = invoke(AUDIT, work)
add("audit变异:漏做主题/版本分诊必命中", rc == 1 and any("scope_missing:P2" in e for e in report.get("errors", [])), report.get("errors"))

def irrelevant_in_relation(i, c, r, m):
    r[0]["documents"] = ["P2", "P3"]
invoke_result = invoke(AUDIT, make_work("irrelevant_used", irrelevant_in_relation))
add("audit变异:不相关论文进入关系必命中", invoke_result[0] == 1 and any("excluded documents" in e for e in invoke_result[1].get("errors", [])), invoke_result[1].get("errors"))

def unreadable_used(i, c, r, m):
    c.append({"source_document_id": "P1", "field": "metric_value", "value": "99", "unit": "%",
              "paragraph_id": "P1::p002", "quote": "Figure 1 could not be read", "source_kind": "figure",
              "figure_id": "Fig1", "confidence": "inferred", "value_state": "reported-positive",
              "caliber": {"metric": "removal", "object": "methyl orange"}})
rc, report = invoke(AUDIT, make_work("figure_used", unreadable_used))
add("audit变异:不可读图表仍被取值必命中", rc == 1 and any("unreadable figure" in e for e in report.get("errors", [])), report.get("errors"))

rc, report = invoke(AUDIT, make_work("resolved", lambda i, c, r, m: r[1].update(resolution_status="resolved")))
add("audit变异:无法归因却标已解决必命中", rc == 1 and any("must remain" in e for e in report.get("errors", [])), report.get("errors"))

rc, report = invoke(AUDIT, make_work("unchecked", lambda i, c, r, m: r[1].update(checked_dims=["sample"])))
add("audit变异:未记录归因排查维度必命中", rc == 1 and any("must record checks" in e for e in report.get("errors", [])), report.get("errors"))

rc, report = invoke(VALIDATE, make_work("cross_doc", lambda i, c, r, m: c[0].update(paragraph_id="P2::p001", quote="removal reached 20 percent")))
add("validate变异:跨文档错位定位必命中", rc == 1 and any("another document" in e for e in report.get("errors", [])), report.get("errors"))

rc, report = invoke(VALIDATE, make_work("bad_quote", lambda i, c, r, m: c[0].update(quote="not present in source")))
add("validate变异:证据引文不在所标段落必命中", rc == 1 and any("quote not found" in e for e in report.get("errors", [])), report.get("errors"))

out = os.path.join(TMP, "output")
rc, path = invoke(VALIDATE, good, out=out)
result = json.load(open(path, encoding="utf-8")) if rc == 0 else {}
required = {"schema_version", "skill_version", "run_id", "document_audit",
            "input_artifact_manifest", "output_artifact_manifest"}
add("result正向:版本/run_id/清单/异常审计字段齐备", rc == 0 and required.issubset(result)
    and all(s.get("content_sha256") for s in result.get("sources", [])), result)

ok = sum(c for _, c, _ in checks)
for name, passed, detail in checks:
    print(("PASS" if passed else "FAIL"), name, ("| " + detail if not passed else ""))
print("total %d/%d" % (ok, len(checks)))
sys.exit(0 if ok == len(checks) else 1)
