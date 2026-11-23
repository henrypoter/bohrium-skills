#!/usr/bin/env python3
"""make_result.py: assemble the standardized result.json for one case. Stdlib only.

Usage:
  make_result.py case.json trace_report.json result.json
      [--elements elements.json] [--svg figure.svg] [--png preview.png]
      [--pdf figure.pdf] [--render render_evidence.json]

Layout (role-keyed, nothing invented, contract keys FILLED with real artifacts):
  deliverables (== outputs) by role: editable_source / preview / export / mapping /
      report -- each entry is a real path + bytes (or explicit null + reason).
  sources       coverage summary: entity text-token hits/total, numeric+unit hits,
                per-element source-attr coverage, quote dual-channel verified/total,
                required coverage (declared/missing).
  changes       uncertainties + change_log (human confirmations live here as
                {item, decision, confirmed_by}) + trade_offs, read from elements.json.
  uncertainty / change_log   mirrored at top level for the runtime contract.
  output_contract            original case.json contract preserved for reference.
  CONTRACT ALIGNMENT         every original output_contract KEY is emitted at top
                level and FILLED with the matching actual deliverable (keyword
                role mapping); keys we cannot fill stay null and are listed in
                output_contract_null_fields -- never the contract's type-hint text.
status follows trace_report's status_ceiling and is NEVER upgraded here.
Exit 0 on assembly, 2 on unreadable inputs.
"""
import argparse, json, os, re, sys


def load(p):
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def file_entry(path, role):
    if path and os.path.isfile(path):
        return {"path": os.path.basename(path), "bytes": os.path.getsize(path)}
    return {"path": None, "status": "missing",
            "reason": f"{role} not produced; do not claim it exists"}


def norm_key(k):
    return re.sub(r"[^a-z0-9]+", "", str(k).lower())


def fill_contract(k, ctx):
    """Map an output_contract field name to the matching actual deliverable.

    Priority order keeps ambiguous names safe: 'editable_source' -> editable SVG,
    'source_trace' -> figure_map (trace keyword beats generic source), 'sources'
    -> coverage summary. Returns None when no deliverable matches (caller keeps
    the key as null and records it honestly).
    """
    n = norm_key(k)

    def has(*ws):
        return any(w in n for w in ws)

    if has("caseid") or n == "case":
        return ctx["case_id"]
    if has("status"):
        return ctx["status"]
    if has("editable", "svg"):
        return ctx["editable_source"]
    if has("map", "trace", "locat", "provenance", "evidence"):
        return ctx["mapping"]
    if has("png", "preview", "image", "thumbnail"):
        return ctx["preview"]
    if has("pdf", "export", "vector"):
        return ctx["export"]
    if has("report", "check", "validation", "audit"):
        return ctx["report"]
    if has("uncertain"):
        return ctx["uncertainty"]
    if has("change", "log"):
        return ctx["change_log"]
    if has("source"):
        return ctx["sources"]
    if has("deliverable", "output"):
        return ctx["deliverables"]
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("case")
    ap.add_argument("trace_report")
    ap.add_argument("out")
    ap.add_argument("--elements")
    ap.add_argument("--svg")
    ap.add_argument("--png")
    ap.add_argument("--pdf")
    ap.add_argument("--render", help="JSON evidence printed by render_preview.py")
    a = ap.parse_args()

    case = load(a.case)
    rep = load(a.trace_report)
    if case is None or rep is None:
        sys.exit(2)
    spec = load(a.elements) if a.elements else {}
    render = load(a.render) if a.render else None

    tdir = os.path.dirname(os.path.abspath(a.trace_report))
    fmap = os.path.join(tdir, "figure_map.md")
    ck = rep.get("checkpoints", {})
    ent, src = ck.get("entity", {}), ck.get("source", {})
    qc = src.get("quote_check", {})

    # ---- role-keyed deliverables -------------------------------------------
    svg_entry = {**file_entry(a.svg, "editable source"), "format": "svg",
                 "editable_text_elements": ck.get("export", {}).get("editable_text_elements")}
    png_entry = file_entry(a.png, "preview") if a.png else None
    pdf_entry = file_entry(a.pdf, "export") if a.pdf else None
    preview = {"render_evidence": render} if render else {
        "status": "preview_unavailable",
        "reason": "no render evidence supplied (render_preview.py exit 3?)"}
    if render and png_entry and png_entry.get("path"):
        preview["png"] = png_entry
    if render and pdf_entry and pdf_entry.get("path"):
        preview["pdf"] = pdf_entry
    mapping_entry = ({"path": "figure_map.md", "bytes": os.path.getsize(fmap)}
                     if os.path.isfile(fmap) else
                     {"path": None, "status": "missing",
                      "reason": "run check_figure.py to regenerate"})
    deliverables = {
        "editable_source": svg_entry,
        "preview": preview,
        "export": pdf_entry,
        "mapping": mapping_entry,
        "report": {"path": os.path.basename(a.trace_report)},
    }

    sources = {
        "files_read": rep.get("sources_read", []),
        "entity_text_tokens": ent.get("text_tokens"),
        "numeric_unit_tokens": ent.get("numeric_unit_tokens"),
        "elements_with_source_attr": src.get("elements_with_source_attr"),
        "quote_dual_channel": {"verified_in_interval": qc.get("verified_in_interval", 0),
                               "total_with_quote": qc.get("total_with_quote", 0),
                               "quote_not_found": qc.get("quote_not_found", []),
                               "locator_mismatch": qc.get("locator_mismatch", [])},
        "required_coverage": src.get("required_coverage"),
    }
    uncertainty = spec.get("uncertainties", [])
    change_log = spec.get("change_log", [])
    changes = {"uncertainties": uncertainty,
               "change_log": change_log,
               "trade_offs": spec.get("trade_offs", [])}
    status = "partial" if rep.get("status_ceiling") == "partial" else "answered"

    out = {
        "case_id": case.get("case_id") or case.get("id"),
        "status": status,
        "status_rule": rep.get("status_rule"),
        "figure_score": rep.get("figure_score"),
        "verdict": rep.get("verdict"),
        "deliverables": deliverables,
        "outputs": deliverables,
        "sources": sources,
        "changes": changes,
        "uncertainty": uncertainty,
        "change_log": change_log,
        "checks": ck,
        "warnings": rep.get("warnings", []),
    }

    # ---- contract per-key alignment -----------------------------------------
    oc = case.get("output_contract", {})
    contract_keys = []
    if isinstance(oc, dict):
        contract_keys = list(oc)
    elif isinstance(oc, list):
        contract_keys = [str(k) for k in oc]
        oc = {str(k): None for k in oc}
    out["output_contract"] = oc

    ctx = {"case_id": out["case_id"], "status": status,
           "editable_source": svg_entry, "preview": preview,
           "export": pdf_entry, "mapping": mapping_entry,
           "report": deliverables["report"], "sources": sources,
           "uncertainty": uncertainty, "change_log": change_log,
           "deliverables": deliverables}
    null_fields = []
    for k in contract_keys:
        if k in out and out[k] is not None:
            continue  # standard field already filled (case_id/status/sources/...)
        val = fill_contract(k, ctx)
        out[k] = val
        if val is None:
            null_fields.append(k)
    if null_fields:
        out["output_contract_null_fields"] = null_fields

    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(json.dumps({"result": a.out, "case_id": out["case_id"], "status": status,
                      "score": (rep.get("figure_score") or {}).get("score"),
                      "outputs": {k: ((v or {}).get("path") or (v or {}).get("status") or "ok")
                                  for k, v in deliverables.items()},
                      "contract_fields": len(contract_keys),
                      "contract_null_fields": null_fields},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
