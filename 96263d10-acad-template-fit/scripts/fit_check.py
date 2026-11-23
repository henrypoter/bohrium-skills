#!/usr/bin/env python3
# fit_check.py -- verify adapted manuscript vs spec; optional compile; never edits. Stdlib.
# Usage: --spec spec.json --target out.tex [--source in.tex] [--compile] [--out compliance.json]
# Readiness is advisory: deliver regardless; failed/missing items are labelled, never blocking.
import json, os, re, shutil, subprocess, sys

def get(k, d=None):
    return sys.argv[sys.argv.index(k) + 1] if k in sys.argv else d

CN = {"初号": 42, "小初": 36, "一号": 26, "小一": 24, "二号": 22, "小二": 18, "三号": 16, "小三": 15,
      "四号": 14, "小四": 12, "五号": 10.5, "小五": 9, "六号": 7.5}
def alnum(v): return re.sub(r"[^0-9a-z]", "", str(v).lower())
def close(a, b, tol=0.05):
    try: return abs(float(a) - float(b)) <= tol
    except (TypeError, ValueError): return False

UNIT_CM = {"cm": 1.0, "mm": 0.1, "in": 2.54}
def len_cm(v, u):
    """length value+unit -> cm; None if unit unknown (caller falls back conservatively)."""
    f = UNIT_CM.get(str(u).strip().lower())
    try: return float(v) * f if f else None
    except (TypeError, ValueError): return None

def check_tex(text, items):
    out, remain = [], []
    for x in items:
        key, exp = x["key"], x["value"]
        v = {"key": key, "requirement": x.get("requirement", ""), "expected": exp, "status": None, "evidence": ""}
        if key.startswith("page.margin_"):
            k = key.rsplit("_", 1)[1]
            m = re.search(k + r"\s*=\s*([\d.]+)\s*(\w+)", text) or re.search(r"margin\s*=\s*([\d.]+)\s*(\w+)", text)
            if m:
                su = str(x.get("unit", "")).split("(")[0]
                got_cm, exp_cm = len_cm(m.group(1), m.group(2)), len_cm(exp, su)
                if got_cm is not None and exp_cm is not None:
                    ok = close(got_cm, exp_cm)
                    conv = " (= %.4gcm vs %.4gcm)" % (got_cm, exp_cm) if m.group(2) != su else ""
                else:  # unknown unit: conservative value+unit match
                    ok = close(m.group(1), exp) and (not su or m.group(2).startswith(su[:2])); conv = " (unit not converted)"
                v["status"] = "pass" if ok else "fail"
                v["evidence"] = "geometry %s=%s%s vs spec %s%s%s" % (k, m.group(1), m.group(2), exp, x.get("unit", ""), conv)
            else: v["status"], v["evidence"] = "uncertain", "no geometry setting for %s" % k
        elif key == "page.size":
            got = next((c for c in ("a4paper", "letterpaper", "b5paper") if c in text), None)
            want = {"A4": "a4paper", "LETTER": "letterpaper", "B5": "b5paper"}.get(str(exp).upper())
            v["status"] = "pass" if got and want and got == want else ("fail" if got else "uncertain")
            v["evidence"] = "paper=%s vs spec %s" % (got, exp)
        elif key == "body.font_size":
            m = re.search(r"\\documentclass\[([^\]]*)\]", text)
            got = re.search(r"(10|11|12)pt", m.group(1)) if m else None
            g = float(got.group(1)) if got else None
            e = CN.get(str(exp), exp)
            v["status"] = "pass" if g and close(g, e) else ("fail" if g else "uncertain")
            v["evidence"] = "base font=%s vs spec %s%s" % (g, exp, ("=%gpt" % e if e != exp else ""))
        elif key == "page.columns":
            two = "twocolumn" in text or "\\twocolumn" in text
            v["status"] = "pass" if (str(exp) == "2") == two else "fail"; v["evidence"] = "twocolumn present=%s" % two
        elif key == "body.line_spacing":
            m = re.search(r"\\linespread\{([\d.]+)\}", text)
            val = m.group(1) if m else ("2.0" if "\\doublespacing" in text else ("1.5" if "\\onehalfspacing" in text else None))
            v["status"] = ("pass" if close(val, exp, 0.01) else "fail") if val else "uncertain"
            v["evidence"] = "linespread=%s vs spec %s" % (val, exp)
        elif key == "refs.style":
            m = re.search(r"\\bibliographystyle\{([^}]+)\}", text) or re.search(r"style\s*=\s*([\w-]+)[^\n]*biblatex", text)
            got = m.group(1) if m else None
            same = got and alnum(exp) and (alnum(got) in alnum(exp) or alnum(exp) in alnum(got))
            v["status"] = ("pass" if same else "fail") if got else "uncertain"
            v["evidence"] = "manuscript style=%s vs spec %s" % (got, exp)
        elif key == "caption.figure.position":
            m = re.search(r"\\begin\{figure\}(.*?)\\end\{figure\}", text, re.S)
            if m:
                b = m.group(1)
                pos = "below" if b.find("\\caption") > b.find("\\includegraphics") >= 0 else "above"
                v["status"] = "pass" if pos == exp or exp == "unspecified" else "fail"
                v["evidence"] = "first figure caption %s vs spec %s" % (pos, exp)
            else: v["status"], v["evidence"] = "uncertain", "no figure env found"
        elif key == "caption.table.position":
            m = re.search(r"\\begin\{table\}(.*?)\\end\{table\}", text, re.S)
            if m:
                b = m.group(1)
                pos = "above" if (b.find("\\caption") >= 0 and (b.find("\\caption") < b.find("\\begin{tabular}") or "tabular" not in b)) else "below"
                v["status"] = "pass" if pos == exp or exp == "unspecified" else "fail"
                v["evidence"] = "first table caption %s vs spec %s" % (pos, exp)
            else: v["status"], v["evidence"] = "uncertain", "no table env found"
        else: remain.append(x); continue
        out.append(v)
    return out, remain

def units(text):
    pats = {"figures": r"\\begin\{figure", "tables": r"\\begin\{table", "footnotes": r"\\footnote\{",
            "citations": r"\\cite[a-z]*\{", "sections": r"\\(?:sub)*section\{"}
    u = {k: len(re.findall(p, text)) for k, p in pats.items()}
    u["equations"] = len(re.findall(r"\\begin\{equation", text)) + len(re.findall(r"\\\[", text))
    return u

def compile_tex(target, workdir):
    r = {"attempted": True, "compiler": None, "ok": False, "pages": None, "log_findings": []}
    cjk = bool(re.search(r"[\u4e00-\u9fff]", open(target, encoding="utf-8", errors="replace").read()))
    exe = next((e for e in ("latexmk", "xelatex", "pdflatex") if shutil.which(e)), None)
    if not exe:
        r.update(attempted=False); r["log_findings"].append("no latex compiler -- static checks only"); return r
    r["compiler"] = exe + (" (CJK)" if cjk else "")
    cmd = [exe, "-pdf", "-xelatex", "-interaction=nonstopmode", "-output-directory=" + workdir, target] if exe == "latexmk" \
        else [exe, "-interaction=nonstopmode", "-output-directory", workdir, target]
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=240, cwd=workdir)
    except Exception as e:
        r["log_findings"].append("compile failed to run: %s" % e); return r
    logf = os.path.join(workdir, os.path.splitext(os.path.basename(target))[0] + ".log")
    log = open(logf, encoding="utf-8", errors="replace").read() if os.path.exists(logf) else (p.stdout + p.stderr)
    pdf = os.path.join(workdir, os.path.splitext(os.path.basename(target))[0] + ".pdf")
    r["ok"] = os.path.exists(pdf)
    m = re.search(r"Output written on .*?\((\d+) page", log)
    if m: r["pages"] = int(m.group(1))
    for pat, tag in ((r"^! .*", "latex-error"),
                     (r"LaTeX Warning: (?:Reference|Citation)[^\n]*undefined[^\n]*", "undefined-ref"),
                     (r"Missing character[^\n]*", "missing-glyph(font)")):
        for h in sorted(set(re.findall(pat, log, re.M)))[:5]:
            r["log_findings"].append("%s: %s" % (tag, h))
    if r["ok"] and any(f.startswith("latex-error:") for f in r["log_findings"]): r["ok"] = False
    if r["ok"]: r["pdf"] = pdf
    else: r["log_findings"].append("no valid PDF produced")
    return r

SEV = {"fail": "error", "uncertain": "warning"}

def main():
    spec = json.load(open(get("--spec"), encoding="utf-8"))
    target, source = get("--target"), get("--source")
    workdir = os.path.abspath(get("--workdir", "/app/work")); os.makedirs(workdir, exist_ok=True)
    res = {"target": target, "checks": [], "fidelity": [], "compile": {"attempted": False}, "summary": {}}
    ext = os.path.splitext(target)[1].lower()
    if ext == ".tex":
        text = open(target, encoding="utf-8", errors="replace").read()
        seen, items = set(), []
        for x in spec.get("items", []):
            if x["key"] not in seen: seen.add(x["key"]); items.append(x)
        done, remain = check_tex(text, items)
        res["checks"] = done
        tpk = set(re.findall(r"\\usepackage(?:\[[^\]]*\])?\{([^}]+)\}", text))
        spk = set(spec.get("packages", []))
        res["conflict_precheck"] = [{"packages": sorted(set(c["packages"])), "note": c["note"]}
            for c in spec.get("pkg_conflicts", []) if set(c.get("packages", [])) <= (tpk | spk)]
        if source and os.path.exists(source):
            u0 = units(open(source, encoding="utf-8", errors="replace").read()); u1 = units(text)
            for k in u0:
                if u0[k] != u1[k]:
                    res["fidelity"].append("%s: source=%d target=%d -- unit count changed; investigate" % (k, u0[k], u1[k]))
        if "--compile" in sys.argv:
            res["compile"] = compile_tex(os.path.abspath(target), workdir)
            lim = next((x["value"] for x in spec.get("items", []) if x["key"] == "page.count"), None)
            if lim and res["compile"].get("pages") is not None:
                res["checks"].append({"key": "page.count", "expected": lim,
                    "status": "pass" if res["compile"]["pages"] <= int(lim) else "fail",
                    "evidence": "compiled pages=%d" % res["compile"]["pages"]})
        done_keys = {c["key"] for c in res["checks"]}
        res["unverified_items"] = [{"key": x["key"], "expected": x["value"],
            "reason": "no auto rule; verify manually"} for x in remain if x["key"] not in done_keys]
    elif ext in (".docx", ".dotx"):
        res["checks"].append({"key": "target.docx", "status": "uncertain",
            "evidence": "docx: run tpl_parse.py on target, diff vs spec, verify soffice PDF preview"})
    else:
        res["checks"].append({"key": "target.type", "status": "uncertain", "evidence": "unsupported type %s" % ext})
    for c in res["checks"]: c["severity"] = SEV.get(c["status"], "info")
    sm = {}
    for c in res["checks"]: sm[c["status"]] = sm.get(c["status"], 0) + 1
    res["summary"] = sm
    errs = [c["key"] for c in res["checks"] if c["status"] == "fail"] + res["fidelity"] + \
           ([] if res["compile"].get("ok", True) else ["compile failed"])
    warns = [c["key"] for c in res["checks"] if c["status"] == "uncertain"] + res["compile"].get("log_findings", []) + \
            ["unverified:%s" % x["key"] for x in res.get("unverified_items", [])]
    level = "ready" if (not errs and not warns) else ("partial" if res["checks"] else "undeterminable")
    res["readiness"] = {"ready": not errs, "level": level, "deliver": True, "errors": errs, "warnings": warns}
    out = get("--out"); s = json.dumps(res, ensure_ascii=False, indent=1)
    if out:
        os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
        open(out, "w", encoding="utf-8").write(s)
    print("summary:", sm, "| fidelity issues:", len(res["fidelity"]), "| ready:", res["readiness"]["ready"], "->", out or "stdout")

if __name__ == "__main__":
    main()
