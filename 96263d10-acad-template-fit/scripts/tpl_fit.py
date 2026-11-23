#!/usr/bin/env python3
# tpl_fit.py -- one-command deliverable builder: template/guide -> editable manuscript + rendered PDF.
# Usage: tpl_fit.py --guide T1 [T2 ...] --source in.tex --out out.tex [--spec-out spec.json]
#                    [--changelog c.jsonl] [--render] [--workdir W]
#        tpl_fit.py --spec spec.json --source in.tex --out out.tex [...]
# Idempotent; never edits source. Writes <out>.fit.json (changes+unified diff+render+delivered PDF).
# Exit 0 whenever a deliverable was written (fit/compile problems are reported, never blocking).
import difflib, json, os, re, shutil, subprocess, sys, time

sys.dont_write_bytecode = True   # keep the installed skill dir clean (sibling imports below)

def get(k, d=None):
    return sys.argv[sys.argv.index(k) + 1] if k in sys.argv else d

def getmulti(k):
    """Values after --k up to the next --flag (file lists)."""
    if k not in sys.argv: return []
    out = []
    for a in sys.argv[sys.argv.index(k) + 1:]:
        if a.startswith("--"): break
        out.append(a)
    return out

def fnum(x):
    v = str(x.get("value", ""))
    if re.fullmatch(r"[\d.]+", v):
        return float(v)
    m = re.search(r"(\d+(?:\.\d+)?)", x.get("unit", "") or "")
    return float(m.group(1)) if m else None

def item(spec, key):
    for x in spec.get("items", []):
        if x["key"] == key:
            return x

STYLE = {"GB/T 7714": "gbt7714", "GB7714": "gbt7714", "gbt7714": "gbt7714", "IEEE": "IEEEtran",
         "IEEEtran": "IEEEtran", "APA": "apalike", "apalike": "apalike", "Vancouver": "unsrt",
         "unsrt": "unsrt", "numbered": "unsrt", "author-year": "apalike", "plainnat": "plainnat", "plain": "plain"}
PAPER = {"A4": "a4paper", "LETTER": "letterpaper", "B5": "b5paper"}

def set_docopt(text, add, remove):
    m = re.search(r"\\documentclass(?:\[([^\]]*)\])?\{([^}]*)\}", text)
    if not m:
        return text, None
    opts = [o.strip() for o in (m.group(1) or "").split(",") if o.strip()]
    old = ",".join(opts)
    keep = [o for o in opts if o not in remove or o in add]
    if any(o not in keep for o in add):
        keep += [o for o in add if o not in keep]
    if ",".join(keep) == old:
        return text, None
    body = "\\documentclass" + ("[" + ",".join(keep) + "]") + "{" + m.group(2) + "}"
    return text[:m.start()] + body + text[m.end():], (old, ",".join(keep))

def ins_doc(text, block):
    m = re.search(r"\\documentclass(?:\[[^\]]*\])?\{[^}]*\}[^\n]*", text)
    pos = m.end() if m else 0
    return text[:pos] + "\n" + block + text[pos:]

def patch(spec, text):
    log = []
    x = item(spec, "page.size")
    if x:
        want = PAPER.get(str(x["value"]).upper())
        if want:
            text, bc = set_docopt(text, [want], list(PAPER.values()))
            if bc: log.append({"rule": "page.size", "before": bc[0] or "none", "after": want, "spec_id": x["id"]})
    x = item(spec, "body.font_size")
    if x:
        pt = fnum(x)
        if pt in (10, 11, 12):
            opt = "%dpt" % pt
            text, bc = set_docopt(text, [opt], ["10pt", "11pt", "12pt"])
            if bc: log.append({"rule": "body.font_size", "before": bc[0] or "none", "after": opt, "spec_id": x["id"]})
        else:
            log.append({"rule": "body.font_size", "before": str(x.get("value")), "after": "skipped: non-standard", "spec_id": x["id"]})
    x = item(spec, "page.columns")
    if x:
        if str(x["value"]) == "2":
            text, bc = set_docopt(text, ["twocolumn"], [])
            if bc: log.append({"rule": "page.columns", "before": bc[0] or "none", "after": "2", "spec_id": x["id"]})
        else:
            text, bc = set_docopt(text, [], ["twocolumn"])
            t2 = re.sub(r"\\twocolumn\b", "", text)
            if t2 != text: text, bc = t2, ("twocolumn", "")
            if bc: log.append({"rule": "page.columns", "before": bc[0] or "none", "after": "1", "spec_id": x["id"]})
    margs, mid = {}, None
    for k in ("top", "bottom", "left", "right"):
        x = item(spec, "page.margin_" + k)
        if x: margs[k] = (str(x["value"]), str(x.get("unit", "") or "")); mid = mid or x["id"]
    x = item(spec, "page.margin_margin")
    if x:
        v, u = str(x["value"]), str(x.get("unit", "") or "")
        for k in ("top", "bottom", "left", "right"): margs.setdefault(k, (v, u))
        mid = mid or x["id"]
    if margs:
        def cm(s):
            mm = re.fullmatch(r"\s*([\d.]+)\s*(cm|mm|in)?\s*", str(s))
            if not mm: return None
            f = {"cm": 1.0, "mm": 0.1, "in": 2.54, None: 1.0}[mm.group(2)]
            return round(float(mm.group(1)) * f, 4)
        cur = {}
        ex = re.search(r"\\usepackage\[([^\]]*)\]\{geometry\}|\\geometry\{([^}]*)\}", text)
        if ex:
            for k2, v2 in re.findall(r"(\w+)\s*=\s*([^,}]+)", ex.group(1) or ex.group(2) or ""):
                cur[k2] = v2
            if "margin" in cur:
                for k in ("top", "bottom", "left", "right"): cur.setdefault(k, cur["margin"])
        same = cur and all(k in cur and cm(cur[k]) is not None and cm(cur[k]) == cm(v + u)
                           for k, (v, u) in margs.items())
        if not same:
            opts = ",".join("%s=%s%s" % (k, v, u) for k, (v, u) in sorted(margs.items()))
            want = "\\usepackage[%s]{geometry}" % opts
            before = re.search(r"\\usepackage(?:\[[^\]]*\])?\{geometry\}|\\geometry\{[^}]*\}", text)
            text = re.sub(r"\\usepackage(?:\[[^\]]*\])?\{geometry\}[^\n]*\n?", "", text)
            text = re.sub(r"\\geometry\{[^}]*\}[^\n]*\n?", "", text)
            text = ins_doc(text, want)
            log.append({"rule": "page.margins", "before": (before.group(0)[:48] if before else "none"), "after": opts, "spec_id": mid})
    x = item(spec, "body.line_spacing")
    if x:
        v = fnum(x)
        if v and "\\linespread{%s}" % ("%g" % v) not in text:
            before = re.search(r"\\linespread\{[^}]*\}|\\(?:onehalfspacing|doublespacing)\b", text)
            text = re.sub(r"\\linespread\{[^}]*\}[^\n]*\n?", "", text)
            text = re.sub(r"\\(?:onehalfspacing|doublespacing)\b[^\n]*\n?", "", text)
            text = ins_doc(text, "\\linespread{%s}" % ("%g" % v))
            log.append({"rule": "body.line_spacing", "before": (before.group(0) if before else "none"), "after": "%g" % v, "spec_id": x["id"]})
    x = item(spec, "refs.style")
    if x:
        bst = STYLE.get(str(x["value"]).strip(), str(x["value"]).strip())
        want = "\\bibliographystyle{%s}" % bst
        if want not in text:
            before = re.search(r"\\bibliographystyle\{[^}]*\}", text)
            text = re.sub(r"\\bibliographystyle\{[^}]*\}", "\\\\bibliographystyle{%s}" % bst, text, count=1)
            if before is None and ("\\bibliography{" in text or "\\end{thebibliography}" in text):
                m = re.search(r"\\bibliography\{[^}]*\}", text) or re.search(r"\\end\{thebibliography\}", text)
                pos = m.start() if m else len(text)
                text = text[:pos] + want + "\n" + text[pos:]
            log.append({"rule": "refs.style", "before": (before.group(0) if before else "none"), "after": want, "spec_id": x["id"]})
        if "\\bibliographystyle{%s}" % bst in text:
            try:
                if subprocess.run(["kpsewhich", bst + ".bst"], capture_output=True, timeout=15).returncode != 0:
                    log.append({"rule": "refs.style.resource", "before": "none",
                                "after": bst + ".bst not installed; will not compile", "spec_id": x["id"]})
            except Exception: pass
    hit = [p for p in ("times", "mathptmx", "newtxtext") if re.search(r"\\usepackage\{" + p + r"\}", text)]
    if hit:
        for p in hit: text = re.sub(r"\\usepackage\{" + p + r"\}[^\n]*\n?", "", text)
        if "\\setmainfont" not in text and "\\usepackage{fontspec}" not in text and "\\usepackage{xeCJK}" not in text:
            text = ins_doc(text, "\\usepackage{fontspec}\n\\setmainfont{Liberation Serif}")
        log.append({"rule": "font.family", "before": ",".join(hit), "after": "Liberation Serif",
                    "spec_id": None, "reason": "organizer-revision3: Times -> Liberation Serif"})
    return text, log

def docx_deliver(spec, src, out):
    """docx: copy the editable source to out and render a real PDF preview (soffice). No style rewrite."""
    if os.path.abspath(src) != os.path.abspath(out):
        os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
        shutil.copy2(src, out)
    r = {"attempted": True, "compiler": None, "ok": False, "pdf": None, "log_findings": []}
    exe = shutil.which("soffice") or shutil.which("libreoffice")
    if not exe:
        r.update(attempted=False); r["log_findings"].append("no soffice -- docx copied without preview")
    else:
        r["compiler"] = exe
        try:
            subprocess.run([exe, "--headless", "--convert-to", "pdf", "--outdir",
                            os.path.dirname(out) or ".", out],
                           capture_output=True, text=True, timeout=240)
            pdf = os.path.splitext(out)[0] + ".pdf"
            r["ok"] = os.path.exists(pdf)
            r["pdf"] = pdf if r["ok"] else None
            if not r["ok"]: r["log_findings"].append("soffice produced no PDF -- inspect the docx manually")
        except Exception as e:
            r["log_findings"].append("soffice failed: %s" % e)
    rep = {"source": src, "out": out, "spec": None, "mode": "docx-passthrough", "applied": 0,
           "changes": [], "diff": [], "diff_plus": 0, "diff_minus": 0, "render": r,
           "unverified": [{"key": x["key"], "expected": x["value"],
                           "reason": "docx style-level item: apply in the document styles, then re-render"}
                          for x in (spec or {}).get("items", [])]}
    return rep


def main():
    guide = getmulti("--guide")
    spec_path = get("--spec")
    if guide:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import tpl_parse
        spec = tpl_parse.build_spec(guide)
        if get("--spec-out"):
            p = get("--spec-out"); os.makedirs(os.path.dirname(p) or ".", exist_ok=True)
            open(p, "w", encoding="utf-8").write(json.dumps(spec, ensure_ascii=False, indent=1))
        spec_path = get("--spec-out") or "(in-process from --guide)"
    elif spec_path:
        spec = json.load(open(spec_path, encoding="utf-8"))
    else:
        print("need --guide <template...> or --spec spec.json, plus --source --out"); sys.exit(2)
    src, out = get("--source"), get("--out")
    if not src or not out:
        print("need --source and --out"); sys.exit(2)
    if os.path.abspath(src) == os.path.abspath(out):
        print("refusing to overwrite source"); sys.exit(2)
    os.makedirs(os.path.dirname(os.path.abspath(out)) or ".", exist_ok=True)
    if os.path.splitext(src)[1].lower() in (".docx", ".dotx", ".doc"):
        rep = docx_deliver(spec, src, out)
        open(out + ".fit.json", "w", encoding="utf-8").write(json.dumps(rep, ensure_ascii=False, indent=1))
        print("mode=docx-passthrough unverified=%d render=%s -> %s | pdf=%s" %
              (len(rep["unverified"]), rep["render"]["ok"], out, rep["render"].get("pdf")))
        return
    a = open(src, encoding="utf-8", errors="replace").read()
    b, log = patch(spec, a)
    open(out, "w", encoding="utf-8").write(b)
    d = list(difflib.unified_diff(a.splitlines(), b.splitlines(), fromfile=src, tofile=out, lineterm=""))
    rep = {"source": src, "out": out, "spec": spec_path, "mode": "tex-fit", "applied": len(log), "changes": log,
           "diff_plus": sum(1 for l in d if l[:1] == "+" and not l.startswith("+++")),
           "diff_minus": sum(1 for l in d if l[:1] == "-" and not l.startswith("---")), "diff": d}
    if not spec.get("items"):
        rep["warning"] = "no checkable spec items extracted from guide -- manuscript copied as-is; state this in uncertainty"
    if "--changelog" in sys.argv:
        cf = get("--changelog"); os.makedirs(os.path.dirname(cf) or ".", exist_ok=True)
        ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        with open(cf, "a", encoding="utf-8") as f:
            for c in log:
                c = dict(c); c.update(ts=ts, file=out,
                                       reason=c.get("reason") or ("spec:%s" % c["spec_id"] if c.get("spec_id") else "deterministic-fit"))
                f.write(json.dumps(c, ensure_ascii=False) + "\n")
    if "--render" in sys.argv:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        try:
            from fit_check import compile_tex
            rep["render"] = compile_tex(os.path.abspath(out), get("--workdir", "/app/work"))
        except Exception as e:
            rep["render"] = {"attempted": False, "ok": False, "log_findings": ["render unavailable: %s" % e]}
        r = rep["render"]
        if r.get("ok") and r.get("pdf") and os.path.exists(r["pdf"]):
            dst = os.path.splitext(out)[0] + ".pdf"          # deliverable PDF lives next to the manuscript
            try:
                if os.path.abspath(dst) != os.path.abspath(r["pdf"]): shutil.copy2(r["pdf"], dst)
                r["pdf_delivered"] = dst
            except Exception as e:
                r["log_findings"] = r.get("log_findings", []) + ["pdf copy failed: %s" % e]
    open(out + ".fit.json", "w", encoding="utf-8").write(json.dumps(rep, ensure_ascii=False, indent=1))
    print("applied=%d diff(+%d/-%d) render=%s -> %s | pdf=%s" %
          (len(log), rep["diff_plus"], rep["diff_minus"], rep.get("render", {}).get("ok"), out,
           rep.get("render", {}).get("pdf_delivered")))

if __name__ == "__main__":
    main()
