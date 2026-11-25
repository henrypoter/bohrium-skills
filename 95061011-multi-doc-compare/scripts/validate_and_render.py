#!/usr/bin/env python3
"""multi-doc-compare v4 validator/renderer (stdlib only).
validate|render|result --work W [result needs --out O]. Work dir:
corpus_index.json, evidence_cards.jsonl, relations.json, case_meta.json.
Card checks: four-state/caliber, forced-merge, missing blocking_dims,
missing attribution, absence-as-negative-vote; renders matrix/coverage/
comparability/attribution. Schema/locator errors exit 1; judgment issues
advisory (exit 0). See SKILL.md 2-5. Never invents values.
"""
import argparse, hashlib, json, os, re, shutil, sys, unicodedata
from collections import defaultdict

SKILL_VERSION = "4.0.0"
RESULT_SCHEMA_VERSION = "2.0.0"

FIELDS = ["research_object", "data_source", "method", "condition", "metric",
  "metric_value", "main_conclusion", "limitation"]
DIMS6 = ["task", "metric", "unit", "object", "condition", "budget"]
STATES = {"reported-positive", "reported-negative", "not-applicable"}
CMP = {"comparable", "comparable_subset", "noncomparable", "unreported"}
VOTE = {"consistent", "partially_consistent", "conflicting"}
RELS = CMP | VOTE | {"complementary"}
ATTR = {"sample", "method", "condition", "metric", "unit", "unattributable"}
XCHK = ("unit", "metric")
ORD = {"not-applicable": 0, "reported-negative": 1, "reported-positive": 2}
MARK = {"reported-positive": "+", "reported-negative": "-",
  "not-applicable": "NA", "not-reported": "NR"}


def norm(v):
 return " ".join(str(v or "").lower().split())


def quote_norm(v):
 return re.sub(r"\s+", "", unicodedata.normalize("NFKC", str(v or "")))


def file_sha256(path):
 h = hashlib.sha256()
 with open(path, "rb") as f:
  for block in iter(lambda: f.read(1024 * 1024), b""):
   h.update(block)
 return h.hexdigest()


def load(work):
 def j(n, d):
  p = os.path.join(work, n)
  if os.path.exists(p):
   with open(p, encoding="utf-8") as f:
    return json.load(f)
  return d
 cards = []
 p = os.path.join(work, "evidence_cards.jsonl")
 if os.path.exists(p):
  with open(p, encoding="utf-8") as f:
   for i, ln in enumerate(f, 1):
    ln = ln.strip()
    if not ln:
     continue
    try:
     c = json.loads(ln)
     c["_line"] = i
     cards.append(c)
    except json.JSONDecodeError as e:
     cards.append({"_line": i, "_parse_error": str(e)})
 return (j("corpus_index.json", {"documents": []}), cards,
   j("relations.json", []), j("case_meta.json", {}))


def states_of(cards):
 st = {}
 for c in cards:
  if "_parse_error" in c:
   continue
  k = (c.get("source_document_id"), c.get("field"))
  if ORD.get(c.get("value_state"), -1) > ORD.get(st.get(k), -1):
   st[k] = c.get("value_state")
 return st


def validate(work):
 index, cards, relations, _ = load(work)
 dids = {d["source_document_id"] for d in index["documents"]}
 ptexts = {p["paragraph_id"]: p.get("text", "")
           for d in index["documents"] for p in d["paragraphs"]}
 powner = {p["paragraph_id"]: d["source_document_id"]
           for d in index["documents"] for p in d["paragraphs"]}
 pids = set(ptexts)
 errors, issues, good = [], [], []
 E = errors.append
 I = issues.append
 for c in cards:
  t = "line %s" % c.get("_line", "?")
  if "_parse_error" in c:
   E(t + ": JSON parse error: " + c["_parse_error"]); continue
  if c.get("field") not in FIELDS: E("%s: bad field %r" % (t, c.get("field")))
  if c.get("source_document_id") not in dids:
   E("%s: unknown document %r" % (t, c.get("source_document_id")))
  elif c.get("paragraph_id") not in pids:
   E("%s: paragraph_id %r not in index" % (t, c.get("paragraph_id")))
  elif powner.get(c.get("paragraph_id")) != c.get("source_document_id"):
   E("%s: paragraph belongs to another document" % t)
  else:
   quote = quote_norm(c.get("quote"))
   if not quote:
    E(t + ": quote required for source verification")
   elif quote not in quote_norm(ptexts.get(c.get("paragraph_id"), "")):
    E(t + ": quote not found in cited paragraph")
  if c.get("value_state") not in STATES:
   E("%s: value_state not in %s" % (t, sorted(STATES)))
  if c.get("field") == "metric_value":
   if not c.get("unit"): E(t + ": metric_value without unit")
   cal = c.get("caliber")
   if not isinstance(cal, dict) or set(cal) - set(DIMS6):
    E("%s: caliber must be a dict over %s" % (t, DIMS6))
   elif not (norm(cal.get("metric")) and norm(cal.get("object"))):
    E(t + ": caliber.metric/object required")
  good.append(c)
 cpara = {(c.get("source_document_id"), c.get("paragraph_id")) for c in good}

 def calib(d):
  o = defaultdict(set)
  for c in good:
   if c.get("source_document_id") != d:
    continue
   cal = c.get("caliber") or {}
   for k in XCHK:
    v = norm(c.get("unit")) if k == "unit" else norm(cal.get(k))
    if v: o[k].add(v)
  return o

 for i, r in enumerate(relations):
  t = "relations[%d]" % i
  rel = r.get("relation")
  if rel not in RELS:
   E("%s: bad relation %r" % (t, rel)); continue
  rdocs = r.get("documents", [])
  expl = " ".join(str(r.get(k, "")) for k in ("explanation", "reason", "subset"))
  evd = set()
  for e in r.get("evidence", []):
   if e.get("paragraph_id") not in pids:
    E("%s: bad evidence locator %r" % (t, e.get("paragraph_id")))
   elif powner.get(e.get("paragraph_id")) != e.get("source_document_id"):
    E("%s: evidence locator belongs to another document" % t)
   evd.add(e.get("source_document_id"))
  diff = set()
  if len(rdocs) >= 2:
   vs = [calib(d) for d in rdocs]
   for k in XCHK:
    if len(set().union(*[v[k] for v in vs])) > 1: diff.add(k)
  if rel == "comparable":
   for k in sorted(diff):
    if k not in expl:
     I("%s: comparable but caliber %s differs %s: forced merge?" % (t, k, rdocs))
  elif rel == "comparable_subset":
   if not norm(r.get("subset")): I(t + ": comparable_subset requires subset")
   for k in sorted(diff):
    if k not in expl: I("%s: subset hides differing caliber %s" % (t, k))
  elif rel == "noncomparable":
   bd = r.get("blocking_dims")
   if not isinstance(bd, list) or not bd or set(bd) - set(DIMS6):
    I("%s: noncomparable requires blocking_dims (subset of %s)" % (t, DIMS6))
   elif diff - set(bd):
    I("%s: caliber diff %s missing from blocking_dims" % (t, sorted(diff - set(bd))))
   if len(str(r.get("explanation", "")).strip()) < 10:
    I(t + ": noncomparable needs a reason (>=10 chars)")
  if rel in VOTE:
   for d in rdocs:
    cited = {e.get("paragraph_id") for e in r.get("evidence", [])
      if e.get("source_document_id") == d}
    if not any((d, p) in cpara for p in cited):
     I("%s: %s lists %s without backing card: absence is not a negative vote" % (t, rel, d))
  if rel == "conflicting":
   if r.get("attribution") not in ATTR:
    I("%s: conflicting needs attribution in %s" % (t, sorted(ATTR)))
   if len(evd & set(rdocs)) < 2:
    I(t + ": conflicting needs evidence from >=2 docs")
   need = 20 if r.get("attribution") == "unattributable" else 10
   if len(str(r.get("explanation", "")).strip()) < need:
    I("%s: conflicting explanation must be >= %d chars" % (t, need))
 st = states_of(good)
 gaps = [{"source_document_id": d, "field": f, "reason": "unreported"}
   for d in sorted(dids) for f in FIELDS if (d, f) not in st]
 per = {}
 for d in sorted(dids):
  ss = [st.get((d, f), "not-reported") for f in FIELDS]
  rep = sum(s in ("reported-positive", "reported-negative") for s in ss)
  per[d] = {"reported": rep, "total": len(FIELDS),
    "coverage_pct": round(100.0 * rep / len(FIELDS), 1),
    "negative": ss.count("reported-negative"),
    "not_applicable": ss.count("not-applicable"),
    "not_reported": ss.count("not-reported")}
 try:
  from intake_audit import audit_work
  document_audit = audit_work(work)
  errors.extend(document_audit["errors"])
 except Exception as exc:
  document_audit = {"ok": False, "errors": ["document audit failed: %s" % exc]}
  errors.extend(document_audit["errors"])
 gaps.extend({"source_document_id": g.get("source_document_id"),
   "field": "figure:" + str(g.get("figure_id")),
   "reason": "figure_" + str(g.get("reason", "unreadable"))}
  for g in document_audit.get("visual_gaps", []))
 rep = {"validator_version": SKILL_VERSION,
  "document_audit": document_audit,
  "errors": errors, "issues": issues, "gaps": gaps,
  "cards": len(cards), "documents": len(dids),
  "coverage": {"matrix": {f: {d: st.get((d, f), "not-reported")
          for d in sorted(dids)} for f in FIELDS},
      "per_document": per}}
 with open(os.path.join(work, "validation_report.json"), "w", encoding="utf-8") as f:
  json.dump(rep, f, ensure_ascii=False, indent=1)
 print(json.dumps(rep, ensure_ascii=False, indent=1))
 return 1 if errors else 0


def render(work):
 index, cards, relations, meta = load(work)
 excluded = {a.get("source_document_id") for a in meta.get("document_assessments", [])
   if a.get("relevance") in {"irrelevant", "uncertain"}
   or a.get("version_state") in {"superseded", "duplicate"}}
 docs = [d["source_document_id"] for d in index["documents"]
         if d["source_document_id"] not in excluded]
 cards = [c for c in cards if c.get("source_document_id") not in excluded]
 cell = defaultdict(list)
 for c in cards:
  if "_parse_error" in c:
   continue
  v = str(c.get("value", ""))
  if c.get("unit"): v += " " + c["unit"]
  if c.get("context"): v += " (%s)" % c["context"]
  s = c.get("value_state")
  if s == "reported-negative": v = "【阴性】" + v
  elif s == "not-applicable": v = "【不适用】" + v
  if c.get("confidence") == "inferred": v += " [推断]"
  cell[(c.get("field"), c.get("source_document_id"))].append(
   v + " [%s]" % c.get("paragraph_id", "?"))
 st = states_of(cards)
 L = ["# 比较矩阵 v4（维度 x 文档；[...] 为原文定位）", ""]
 if excluded:
  L += ["排除文档（不进入比较/结论）：" + ", ".join(sorted(excluded)), ""]

 def table(head, rows):
  L.append("| " + " | ".join(head) + " |")
  L.append("|" + "---|" * len(head))
  L.extend("| " + " | ".join(r) + " |" for r in rows)

 table(["字段"] + docs, [[f] + ["<br>".join(cell.get((f, d), [])) or "—(not-reported)"
         for d in docs] for f in FIELDS])
 L += ["", "## 覆盖度报告（+ 阳性 / - 阴性 / NA 不适用 / NR 未报告）", ""]
 table(["字段"] + docs, [[f] + [MARK[st.get((d, f), "not-reported")]
         for d in docs] for f in FIELDS])
 for d in docs:
  ss = [st.get((d, f), "not-reported") for f in FIELDS]
  rep = sum(s in ("reported-positive", "reported-negative") for s in ss)
  L.append("- **%s** 覆盖 %d/%d（%.0f%%）；阴性 %d，不适用 %d，未报告 %d"
      % (d, rep, len(FIELDS), 100.0 * rep / len(FIELDS),
       ss.count("reported-negative"), ss.count("not-applicable"),
       ss.count("not-reported")))
 L += ["", "## 可比性判定表", ""]
 rows = [[str(r.get("dimension", "?")), r.get("relation", ""),
   ",".join(r.get("documents", [])),
   ",".join(r.get("blocking_dims", [])) or "-", str(r.get("score", "-")),
   r.get("explanation", "")] for r in relations if r.get("relation") in CMP]
 table(["维度", "判定", "文档", "阻断维度", "score", "说明"],
   rows or [["-", "（无记录）", "", "", "", ""]])
 L += ["", "## 分歧归因表（其余关系见 result.json）", ""]
 rows = [[str(r.get("dimension", "?")), str(r.get("attribution", "?")),
   ",".join(r.get("documents", [])), r.get("explanation", ""),
   "; ".join("%s@%s" % (e.get("source_document_id"), e.get("paragraph_id"))
      for e in r.get("evidence", []))]
   for r in relations if r.get("relation") == "conflicting"]
 table(["维度", "归因", "文档", "解释", "证据"],
   rows or [["-", "（无 conflicting 记录）", "", "", ""]])
 out = os.path.join(work, "comparison_matrix.md")
 with open(out, "w", encoding="utf-8") as f:
  rp = os.path.join(work, "validation_report.json")
  if os.path.exists(rp):
   with open(rp, encoding="utf-8") as rf:
    iss = json.load(rf).get("issues") or []
   if iss:
    L += ["", "## 问题与告警（advisory，不阻断定稿）", ""]
    L += ["- " + str(i) for i in iss]
  f.write("\n".join(L) + "\n")
 print(out)
 return 0


def result(work, outdir):
 index, cards, relations, meta = load(work)
 rp = os.path.join(work, "validation_report.json")
 report = {}
 if os.path.exists(rp):
  with open(rp, encoding="utf-8") as f:
   report = json.load(f)
 os.makedirs(outdir, exist_ok=True)
 for name in ("comparison_matrix.md", "evidence_cards.jsonl", "relations.json",
        "corpus_index.json", "document_audit.json", "validation_report.json"):
  src = os.path.join(work, name)
  if os.path.exists(src):
   shutil.copyfile(src, os.path.join(outdir, name))
 cited = defaultdict(set)
 for c in cards:
  if "_parse_error" not in c and c.get("paragraph_id"):
   cited[c.get("source_document_id")].add(c["paragraph_id"])
 sources = [{"source_document_id": d["source_document_id"],
    "source_file": d.get("source_file"),
     "content_sha256": d.get("content_sha256"),
     "content_bytes": d.get("content_bytes"),
    "paragraph_count": d.get("paragraph_count"),
    "paragraph_ids_cited": sorted(cited.get(d["source_document_id"], []))}
   for d in index["documents"]]
 contract = dict(meta.get("contract_fields", {}))
 missing = [k for k, v in contract.items() if v in (None, "", [])]
 uncertainty = list(meta.get("uncertainty", []))
 if missing:
  uncertainty.append("output_contract 字段未完成: " + ",".join(missing))
 document_audit = report.get("document_audit", {})
 for item in document_audit.get("unresolved_conflicts", []):
  uncertainty.append("relations[%d] 结论冲突且无法归因，保持 unresolved" %
                     item.get("relation_index", -1))
 for did in document_audit.get("excluded_documents", []):
  uncertainty.append("文档 %s 因主题/版本边界不参与比较" % did)
 work_manifest = {name: file_sha256(os.path.join(work, name))
   for name in ("corpus_index.json", "evidence_cards.jsonl", "relations.json",
                "case_meta.json") if os.path.exists(os.path.join(work, name))}
 artifact_manifest = {name: file_sha256(os.path.join(outdir, name))
   for name in os.listdir(outdir)
   if name != "result.json" and os.path.isfile(os.path.join(outdir, name))}
 run_material = json.dumps({"case_id": meta.get("case_id", "unknown"),
   "inputs": work_manifest}, ensure_ascii=False, sort_keys=True).encode("utf-8")
 res = {"schema_version": RESULT_SCHEMA_VERSION,
  "skill_version": SKILL_VERSION,
  "run_id": "mdc-" + hashlib.sha256(run_material).hexdigest()[:16],
  "case_id": meta.get("case_id", "unknown"),
  "status": meta.get("status", "partial"),
  "status_reason": meta.get("status_reason", ""),
  "contract": contract, "sources": sources, "uncertainty": uncertainty,
  "comparison_matrix_file": "comparison_matrix.md",
  "evidence_cards_file": "evidence_cards.jsonl",
  "coverage": report.get("coverage", {}),
  "document_audit": document_audit,
  "input_artifact_manifest": work_manifest,
  "output_artifact_manifest": artifact_manifest,
  "relations": relations, "gaps": report.get("gaps", []),
  "validation_errors": report.get("errors", []),
  "validation_issues": report.get("issues", []),
  "change_records": meta.get("change_records", [])}
 with open(os.path.join(outdir, "result.json"), "w", encoding="utf-8") as f:
  json.dump(res, f, ensure_ascii=False, indent=1)
 print(os.path.join(outdir, "result.json"))
 return 0


def main():
 ap = argparse.ArgumentParser()
 sub = ap.add_subparsers(dest="cmd", required=True)
 for name in ("validate", "render", "result"):
  p = sub.add_parser(name)
  p.add_argument("--work", required=True)
  if name == "result": p.add_argument("--out", required=True)
 a = ap.parse_args()
 if a.cmd == "validate": return validate(a.work)
 if a.cmd == "render": return render(a.work)
 return result(a.work, a.out)


if __name__ == "__main__":
 sys.exit(main())
